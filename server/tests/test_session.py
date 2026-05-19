from __future__ import annotations

from pathlib import Path

import pytest

from modelscopic import audit as audit_mod
from modelscopic.session import (
    Limits,
    NoActiveSession,
    SessionAlreadyActive,
    SessionError,
    SessionManager,
    SessionPaused,
)


@pytest.fixture(autouse=True)
def _isolate_sessions_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit_mod, "SESSIONS_ROOT", tmp_path)


def test_start_creates_dir_and_status_reflects_active() -> None:
    mgr = SessionManager()
    info = mgr.start()
    assert Path(info["dir"]).is_dir()
    status = mgr.status()
    assert status["active"] is True
    assert status["tool_calls"] == 0


def test_double_start_rejected() -> None:
    mgr = SessionManager()
    mgr.start()
    with pytest.raises(SessionAlreadyActive):
        mgr.start()


def test_end_default_wipes_folder() -> None:
    mgr = SessionManager()
    info = mgr.start()
    result = mgr.end(keep=False, reason="")
    assert result["wiped"] is True
    assert not Path(info["dir"]).exists()


def test_end_keep_requires_reason() -> None:
    mgr = SessionManager()
    mgr.start()
    with pytest.raises(SessionError):
        mgr.end(keep=True, reason="")


def test_end_keep_with_reason_retains_folder() -> None:
    mgr = SessionManager()
    info = mgr.start()
    result = mgr.end(keep=True, reason="useful: caught an OCR bug")
    assert result["kept"] is True and result["wiped"] is False
    assert Path(info["dir"]).is_dir()


def test_mark_keep_persisted_through_end() -> None:
    mgr = SessionManager()
    info = mgr.start()
    mgr.mark_keep("session led to a reproducible repro")
    result = mgr.end(keep=False, reason="")
    assert result["kept"] is True
    assert Path(info["dir"]).is_dir()


def test_breaker_trips_after_consecutive_errors() -> None:
    mgr = SessionManager(Limits(error_window=3, max_actions=500))
    mgr.start()
    for _ in range(2):
        mgr.before_tool()
        mgr.after_tool(error=True)
    mgr.before_tool()
    mgr.after_tool(error=True)  # third error trips the breaker
    with pytest.raises(SessionPaused):
        mgr.before_tool()


def test_breaker_resets_on_success() -> None:
    mgr = SessionManager(Limits(error_window=3, max_actions=500))
    mgr.start()
    for _ in range(2):
        mgr.before_tool()
        mgr.after_tool(error=True)
    mgr.before_tool()
    mgr.after_tool(error=False)
    # back to zero; another two errors should NOT trip
    for _ in range(2):
        mgr.before_tool()
        mgr.after_tool(error=True)
    # next call should still work
    mgr.before_tool()


def test_max_actions_pauses() -> None:
    mgr = SessionManager(Limits(max_actions=2, error_window=10))
    mgr.start()
    mgr.before_tool(); mgr.after_tool(error=False)
    mgr.before_tool(); mgr.after_tool(error=False)
    with pytest.raises(SessionPaused):
        mgr.before_tool()


def test_resume_clears_pause() -> None:
    mgr = SessionManager(Limits(error_window=1, max_actions=500))
    mgr.start()
    mgr.before_tool()
    mgr.after_tool(error=True)
    with pytest.raises(SessionPaused):
        mgr.before_tool()
    mgr.resume()
    mgr.before_tool()  # works again


def test_no_active_session_errors() -> None:
    mgr = SessionManager()
    with pytest.raises(NoActiveSession):
        mgr.before_tool()
    with pytest.raises(NoActiveSession):
        mgr.end(keep=False, reason="")
