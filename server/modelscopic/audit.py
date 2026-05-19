"""Per-session audit log writer."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SESSIONS_ROOT = Path.home() / ".modelscopic" / "sessions"


@dataclass
class SessionManifest:
    session_id: str
    started_at: str
    ended_at: str | None = None
    ended_via: str | None = None  # "session_end" | "breaker" | "kill_switch" | "crash"
    keep: bool = False
    keep_reason: str = ""
    window_title: str | None = None
    totals: dict[str, int] = field(default_factory=lambda: {"tool_calls": 0, "errors": 0})
    breaker_trips: int = 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_orphan_sessions(*, root: Path = SESSIONS_ROOT, active_id: str | None = None) -> list[dict]:
    """Inspect SESSIONS_ROOT for session folders whose manifest indicates they were never ended.

    A 'kept' session that has `ended_at != None` is NOT an orphan — it was explicitly retained.
    A folder is an orphan if its manifest has `ended_at == None` AND it isn't the active session.
    """
    if not root.exists():
        return []
    out: list[dict] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        if active_id is not None and child.name == active_id:
            continue
        manifest = child / "manifest.json"
        if not manifest.exists():
            out.append({"session_id": child.name, "dir": str(child), "reason": "no manifest"})
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf8"))
        except (OSError, json.JSONDecodeError):
            out.append({"session_id": child.name, "dir": str(child), "reason": "manifest unreadable"})
            continue
        if data.get("ended_at") is None:
            out.append({
                "session_id": child.name,
                "dir": str(child),
                "started_at": data.get("started_at"),
                "tool_calls": (data.get("totals") or {}).get("tool_calls", 0),
                "reason": "no ended_at (likely crashed)",
            })
    return out


def wipe_session_dir(session_dir: Path) -> None:
    shutil.rmtree(session_dir, ignore_errors=True)


class AuditLog:
    def __init__(self, session_id: str, root: Path = SESSIONS_ROOT) -> None:
        self.session_id = session_id
        self.dir = root / session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "screenshots").mkdir(exist_ok=True)
        self.log_path = self.dir / "log.jsonl"
        self.manifest_path = self.dir / "manifest.json"
        self.manifest = SessionManifest(session_id=session_id, started_at=_now_iso())
        self.last_screenshot: str | None = None
        self._flush_manifest()

    def record(self, tool: str, args: dict[str, Any], result_summary: Any, *, screenshot: str | None = None, error: str | None = None) -> None:
        entry = {
            "ts": _now_iso(),
            "tool": tool,
            "args": args,
            "result_summary": result_summary,
            "screenshot": screenshot,
            "error": error,
        }
        with self.log_path.open("a", encoding="utf8") as f:
            f.write(json.dumps(entry) + "\n")
        self.manifest.totals["tool_calls"] += 1
        if error is not None:
            self.manifest.totals["errors"] += 1
        self._flush_manifest()

    def finalize(self, *, ended_via: str, keep: bool, keep_reason: str) -> None:
        self.manifest.ended_at = _now_iso()
        self.manifest.ended_via = ended_via
        self.manifest.keep = keep
        self.manifest.keep_reason = keep_reason
        self._flush_manifest()

    def wipe(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def _flush_manifest(self) -> None:
        self.manifest_path.write_text(json.dumps(asdict(self.manifest), indent=2), encoding="utf8")
