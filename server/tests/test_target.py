from __future__ import annotations

from pathlib import Path

import pytest

from modelscopic import audit as audit_mod
from modelscopic.session import SessionError, SessionManager


@pytest.fixture(autouse=True)
def _isolate_sessions_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit_mod, "SESSIONS_ROOT", tmp_path)


def test_require_target_errors_when_unset() -> None:
    mgr = SessionManager()
    mgr.start()
    with pytest.raises(SessionError):
        mgr.require_target()


def test_set_target_stores_metadata_and_status() -> None:
    mgr = SessionManager()
    mgr.start()
    mgr.set_target(hwnd=12345, title="My App", class_name="Tk", pid=999)
    assert mgr.require_target() == 12345
    status = mgr.status()
    assert status["target"] == {
        "hwnd": 12345, "title": "My App", "class_name": "Tk", "pid": 999, "retargets": 0,
    }
    # manifest updated too
    assert mgr.audit.manifest.window_title == "My App"


def test_retarget_to_different_hwnd_increments_counter() -> None:
    mgr = SessionManager()
    mgr.start()
    mgr.set_target(hwnd=1, title="A", class_name="X", pid=10)
    mgr.set_target(hwnd=2, title="B", class_name="X", pid=11)
    assert mgr.status()["target"]["retargets"] == 1  # type: ignore[index]


def test_retarget_same_hwnd_does_not_increment() -> None:
    mgr = SessionManager()
    mgr.start()
    mgr.set_target(hwnd=1, title="A", class_name="X", pid=10)
    mgr.set_target(hwnd=1, title="A renamed", class_name="X", pid=10)
    assert mgr.status()["target"]["retargets"] == 0  # type: ignore[index]


def test_set_target_requires_active_session() -> None:
    mgr = SessionManager()
    with pytest.raises(Exception):  # NoActiveSession
        mgr.set_target(hwnd=1, title="A", class_name="X", pid=10)
