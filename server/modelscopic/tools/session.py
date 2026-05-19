"""Session lifecycle tools. These are NOT gated by the breaker."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pathlib import Path

from ..audit import list_orphan_sessions, wipe_session_dir
from ..session import SessionManager

if TYPE_CHECKING:
    from . import ToolRegistry


def register(reg: "ToolRegistry", *, manager: SessionManager) -> None:
    from . import ToolSpec  # avoid circular import at module load

    async def _start(_: dict[str, Any]) -> Any:
        return manager.start()

    async def _end(args: dict[str, Any]) -> Any:
        return manager.end(keep=bool(args.get("keep", False)), reason=str(args.get("reason", "")))

    async def _status(_: dict[str, Any]) -> Any:
        return manager.status()

    async def _resume(_: dict[str, Any]) -> Any:
        return manager.resume()

    async def _mark_keep(args: dict[str, Any]) -> Any:
        manager.mark_keep(str(args.get("reason", "")))
        return {"ok": True}

    async def _cleanup(args: dict[str, Any]) -> Any:
        dry_run = bool(args.get("dry_run", True))
        active_id = manager.status().get("session_id") if manager.active else None
        orphans = list_orphan_sessions(active_id=active_id)
        wiped: list[str] = []
        if not dry_run:
            for o in orphans:
                wipe_session_dir(Path(o["dir"]))
                wiped.append(o["session_id"])
        return {"orphans": orphans, "wiped": wiped, "dry_run": dry_run}

    reg.add(ToolSpec(
        name="session_start",
        description=(
            "Start a new session. Initializes the audit log under ~/.modelscopic/sessions/<id>/. "
            "After this, call `session_pick_window` (interactive: user clicks the target window) "
            "or `session_retarget` with an explicit hwnd from `list_windows`."
        ),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_start, gated=False,
    ))
    reg.add(ToolSpec(
        name="session_end",
        description=(
            "End the active session. By default the audit folder is wiped. Pass keep=true with "
            "a non-empty reason to retain it."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "keep": {"type": "boolean", "default": False},
                "reason": {"type": "string", "default": ""},
            },
            "additionalProperties": False,
        },
        handler=_end, gated=False,
    ))
    reg.add(ToolSpec(
        name="session_status",
        description="Report active-session state, counters, and breaker status.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_status, gated=False,
    ))
    reg.add(ToolSpec(
        name="session_resume",
        description="Resume a paused session (breaker or max-actions trip).",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_resume, gated=False,
    ))
    reg.add(ToolSpec(
        name="cleanup_sessions",
        description=(
            "List orphaned session folders (manifest exists but never reached session_end -- typical "
            "of a server crash) and optionally wipe them. dry_run defaults to true."
        ),
        input_schema={
            "type": "object",
            "properties": {"dry_run": {"type": "boolean", "default": True}},
            "additionalProperties": False,
        },
        handler=_cleanup, gated=False,
    ))
    reg.add(ToolSpec(
        name="session_mark_keep",
        description=(
            "Mark the active session as worth keeping before session_end is called. Requires a "
            "non-empty reason explaining why."
        ),
        input_schema={
            "type": "object",
            "properties": {"reason": {"type": "string", "minLength": 1}},
            "required": ["reason"],
            "additionalProperties": False,
        },
        handler=_mark_keep, gated=False,
    ))
