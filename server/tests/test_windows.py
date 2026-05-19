"""Cross-platform tests for the windows module's pure logic."""

from __future__ import annotations

from modelscopic.windows import WindowRect, _is_excluded_class


def test_window_rect_contains() -> None:
    r = WindowRect(x=10, y=20, width=100, height=50)
    assert r.contains(10, 20)
    assert r.contains(109, 69)
    assert not r.contains(9, 20)
    assert not r.contains(10, 70)
    assert not r.contains(110, 20)


def test_vscode_class_excluded() -> None:
    assert _is_excluded_class("Chrome_WidgetWin_1")
    assert _is_excluded_class("Chrome_WidgetWin_2")
    assert not _is_excluded_class("Tk")
    assert not _is_excluded_class("Qt5QWindow")
    assert not _is_excluded_class("Notepad")
