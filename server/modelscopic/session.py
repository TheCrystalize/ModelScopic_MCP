"""Single-session lifecycle and circuit breaker."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from .audit import SESSIONS_ROOT, AuditLog


class SessionError(RuntimeError):
    pass


class NoActiveSession(SessionError):
    pass


class SessionAlreadyActive(SessionError):
    pass


class SessionPaused(SessionError):
    """Raised when a tool is called while the session is paused."""


@dataclass
class Limits:
    max_actions: int = 500
    error_window: int = 3  # consecutive errors that trip the breaker


@dataclass
class _State:
    consecutive_errors: int = 0
    actions: int = 0
    paused: bool = False
    paused_reason: str = ""
    keep: bool = False
    keep_reason: str = ""
    target_hwnd: int | None = None
    target_title: str | None = None
    target_class: str | None = None
    target_pid: int | None = None
    retargets: int = 0


class SessionManager:
    def __init__(self, limits: Limits | None = None) -> None:
        self._limits = limits or Limits()
        self._audit: AuditLog | None = None
        self._state = _State()

    @property
    def active(self) -> bool:
        return self._audit is not None

    @property
    def audit(self) -> AuditLog:
        if self._audit is None:
            raise NoActiveSession("no active session")
        return self._audit

    def start(self) -> dict[str, str]:
        if self._audit is not None:
            raise SessionAlreadyActive("a session is already active")
        session_id = uuid.uuid4().hex[:12]
        self._audit = AuditLog(session_id)
        self._state = _State()
        return {"session_id": session_id, "dir": str(self._audit.dir)}

    def set_target(self, *, hwnd: int, title: str, class_name: str, pid: int) -> None:
        if self._audit is None:
            raise NoActiveSession("no active session")
        if self._state.target_hwnd is not None and self._state.target_hwnd != hwnd:
            self._state.retargets += 1
        self._state.target_hwnd = hwnd
        self._state.target_title = title
        self._state.target_class = class_name
        self._state.target_pid = pid
        self._audit.manifest.window_title = title

    @property
    def target_hwnd(self) -> int | None:
        return self._state.target_hwnd

    def require_target(self) -> int:
        if self._state.target_hwnd is None:
            raise SessionError("no target window set — call session_retarget or session_start with a picker")
        return self._state.target_hwnd

    def end(self, *, keep: bool, reason: str, ended_via: str = "session_end") -> dict[str, object]:
        audit = self.audit
        keep_final = keep or self._state.keep
        keep_reason_final = reason or self._state.keep_reason
        if keep_final and not keep_reason_final:
            raise SessionError("keep=true requires a non-empty reason")
        audit.finalize(ended_via=ended_via, keep=keep_final, keep_reason=keep_reason_final)
        path = str(audit.dir)
        wiped = False
        if not keep_final:
            audit.wipe()
            wiped = True
        self._audit = None
        self._state = _State()
        return {"kept": keep_final, "wiped": wiped, "dir": path}

    def mark_keep(self, reason: str) -> None:
        if not reason:
            raise SessionError("reason required")
        self.audit  # raises if no session
        self._state.keep = True
        self._state.keep_reason = reason

    def status(self) -> dict[str, object]:
        if self._audit is None:
            return {"active": False, "sessions_root": str(SESSIONS_ROOT)}
        return {
            "active": True,
            "session_id": self._audit.session_id,
            "dir": str(self._audit.dir),
            "paused": self._state.paused,
            "paused_reason": self._state.paused_reason,
            "consecutive_errors": self._state.consecutive_errors,
            "tool_calls": self._audit.manifest.totals["tool_calls"],
            "errors": self._audit.manifest.totals["errors"],
            "keep_marked": self._state.keep,
            "target": (
                None
                if self._state.target_hwnd is None
                else {
                    "hwnd": self._state.target_hwnd,
                    "title": self._state.target_title,
                    "class_name": self._state.target_class,
                    "pid": self._state.target_pid,
                    "retargets": self._state.retargets,
                }
            ),
            "limits": {
                "max_actions": self._limits.max_actions,
                "error_window": self._limits.error_window,
            },
        }

    def resume(self) -> dict[str, object]:
        if self._audit is None:
            raise NoActiveSession("no active session")
        if not self._state.paused:
            return {"paused": False}
        self._state.paused = False
        self._state.paused_reason = ""
        self._state.consecutive_errors = 0
        return {"paused": False, "resumed": True}

    def trip(self, reason: str) -> None:
        """External trip (e.g. kill switch)."""
        if self._audit is None:
            return
        self._state.paused = True
        self._state.paused_reason = reason
        self._audit.manifest.breaker_trips += 1

    def before_tool(self) -> None:
        if self._audit is None:
            raise NoActiveSession("call session_start first")
        if self._state.paused:
            raise SessionPaused(
                f"session paused: {self._state.paused_reason}; call session_resume to continue"
            )
        if self._state.actions >= self._limits.max_actions:
            self._state.paused = True
            self._state.paused_reason = f"max_actions ({self._limits.max_actions}) reached"
            self._audit.manifest.breaker_trips += 1
            raise SessionPaused(self._state.paused_reason)
        self._state.actions += 1

    def after_tool(self, *, error: bool) -> None:
        if error:
            self._state.consecutive_errors += 1
            if self._state.consecutive_errors >= self._limits.error_window:
                self._state.paused = True
                self._state.paused_reason = (
                    f"{self._limits.error_window} consecutive tool errors"
                )
                if self._audit is not None:
                    self._audit.manifest.breaker_trips += 1
        else:
            self._state.consecutive_errors = 0
