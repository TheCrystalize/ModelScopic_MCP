"""Windows top-level window enumeration, geometry, and foreground picker.

Wraps Win32 calls behind a small dataclass-based API so the rest of the codebase
can stay platform-agnostic. Imports of ``win32gui`` etc. are deferred to function
bodies so the module still imports on non-Windows environments — calls just raise.
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass


WINDOWS = sys.platform == "win32"


@dataclass(frozen=True)
class WindowRect:
    x: int
    y: int
    width: int
    height: int

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    process_id: int
    rect: WindowRect


class WindowsOnly(RuntimeError):
    """Raised when a Win32-only function is called on another platform."""


def _require_win32() -> None:
    if not WINDOWS:
        raise WindowsOnly("this operation requires Windows")


def set_dpi_awareness() -> None:
    """Opt into per-monitor V2 DPI awareness so coordinates match physical pixels."""
    if not WINDOWS:
        return
    import ctypes

    # PROCESS_PER_MONITOR_DPI_AWARE = 2 ; per-monitor v2 ctx = -4
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def list_windows(*, visible_only: bool = True, min_area: int = 100) -> list[WindowInfo]:
    """Enumerate top-level windows. Skips minimized windows (positioned at the Win32
    sentinel -32000,-32000) and cloaked windows (e.g. UWP background hosts)."""
    _require_win32()
    import ctypes
    from ctypes import wintypes
    import win32gui
    import win32process

    # DwmGetWindowAttribute for DWMWA_CLOAKED -- non-zero means the compositor
    # is hiding this window (UWP background hosts, virtual desktop spillover).
    DWMWA_CLOAKED = 14
    dwmapi = ctypes.WinDLL("dwmapi")
    dwmapi.DwmGetWindowAttribute.argtypes = (
        wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
    )
    dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long

    def _is_cloaked(hwnd: int) -> bool:
        val = wintypes.DWORD(0)
        hr = dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_CLOAKED, ctypes.byref(val), ctypes.sizeof(val),
        )
        return hr == 0 and val.value != 0

    out: list[WindowInfo] = []

    def _cb(hwnd: int, _ctx: object) -> bool:
        if visible_only and not win32gui.IsWindowVisible(hwnd):
            return True
        if win32gui.IsIconic(hwnd):  # minimized
            return True
        if _is_cloaked(hwnd):
            return True
        rect = _get_window_rect(hwnd)
        # Win32 minimized sentinel; also filter clearly-offscreen windows.
        if rect.x <= -30000 or rect.y <= -30000:
            return True
        if rect.width * rect.height < min_area:
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title:
            cls = win32gui.GetClassName(hwnd)
            if cls in {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}:
                return True
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            pid = 0
        out.append(WindowInfo(
            hwnd=hwnd,
            title=title,
            class_name=win32gui.GetClassName(hwnd),
            process_id=pid,
            rect=rect,
        ))
        return True

    win32gui.EnumWindows(_cb, None)
    return out


def get_window(hwnd: int) -> WindowInfo:
    """Refresh metadata for a single HWND. Raises if the window no longer exists."""
    _require_win32()
    import win32gui
    import win32process

    if not win32gui.IsWindow(hwnd):
        raise LookupError(f"hwnd {hwnd} no longer exists")
    title = win32gui.GetWindowText(hwnd)
    cls = win32gui.GetClassName(hwnd)
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
    except Exception:
        pid = 0
    return WindowInfo(hwnd=hwnd, title=title, class_name=cls, process_id=pid, rect=_get_window_rect(hwnd))


def _get_window_rect(hwnd: int) -> WindowRect:
    import win32gui

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    return WindowRect(x=left, y=top, width=right - left, height=bottom - top)


# ---- Move / resize -----------------------------------------------------------

# SWP flags
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_ASYNCWINDOWPOS = 0x4000

# SW_ flags
_SW_RESTORE = 9


def restore_window(hwnd: int) -> WindowInfo:
    """Un-minimize / un-maximize a window so subsequent move/resize works predictably."""
    _require_win32()
    import win32gui
    win32gui.ShowWindow(hwnd, _SW_RESTORE)
    return get_window(hwnd)


def move_window(hwnd: int, x: int, y: int) -> WindowInfo:
    """Move a window's top-left corner to (x, y) in screen coords. Size unchanged."""
    _require_win32()
    import ctypes
    info = get_window(hwnd)
    # SWP_NOSIZE = 0x0001
    if not ctypes.windll.user32.SetWindowPos(
        hwnd, 0, int(x), int(y), 0, 0,
        0x0001 | _SWP_NOZORDER | _SWP_NOACTIVATE,
    ):
        raise OSError(f"SetWindowPos failed: {ctypes.get_last_error()}")
    return get_window(hwnd)


def resize_window(hwnd: int, width: int, height: int) -> WindowInfo:
    """Resize a window to the given dimensions. Position unchanged. Auto-restores if minimized."""
    _require_win32()
    import ctypes
    import win32gui
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, _SW_RESTORE)
    if width < 100 or height < 50:
        raise ValueError("refusing to resize window below 100x50 -- unusable")
    # SWP_NOMOVE = 0x0002
    if not ctypes.windll.user32.SetWindowPos(
        hwnd, 0, 0, 0, int(width), int(height),
        0x0002 | _SWP_NOZORDER | _SWP_NOACTIVATE,
    ):
        raise OSError(f"SetWindowPos failed: {ctypes.get_last_error()}")
    return get_window(hwnd)


def set_window_bounds(hwnd: int, x: int, y: int, width: int, height: int) -> WindowInfo:
    """Move and resize in one call (atomic; avoids two repaints)."""
    _require_win32()
    import ctypes
    import win32gui
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, _SW_RESTORE)
    if width < 100 or height < 50:
        raise ValueError("refusing to resize window below 100x50 -- unusable")
    if not ctypes.windll.user32.SetWindowPos(
        hwnd, 0, int(x), int(y), int(width), int(height),
        _SWP_NOZORDER | _SWP_NOACTIVATE,
    ):
        raise OSError(f"SetWindowPos failed: {ctypes.get_last_error()}")
    return get_window(hwnd)


async def pick_window_by_foreground(
    *,
    timeout_s: float = 30.0,
    poll_interval_s: float = 0.25,
    settle_s: float = 0.75,
) -> WindowInfo:
    """Wait for the user to click on a target window, then return it.

    Algorithm: capture the foreground HWND right now (this MCP server's caller),
    then poll until a *different* foreground window stays in front for ``settle_s``
    seconds. Returns that window. The settle window prevents capturing transient
    focuses (alt-tab, dropdown previews).

    Excludes VSCode itself by default (any window whose class starts with "Chrome_WidgetWin"
    is treated as Electron and skipped — VSCode is Electron).
    """
    _require_win32()
    import win32gui

    deadline = time.monotonic() + timeout_s
    baseline = win32gui.GetForegroundWindow()
    candidate: int | None = None
    stable_since: float | None = None
    while time.monotonic() < deadline:
        await asyncio.sleep(poll_interval_s)
        cur = win32gui.GetForegroundWindow()
        if cur == 0 or cur == baseline:
            candidate = None
            stable_since = None
            continue
        cls = win32gui.GetClassName(cur)
        if _is_excluded_class(cls):
            continue
        if candidate != cur:
            candidate = cur
            stable_since = time.monotonic()
            continue
        assert stable_since is not None
        if time.monotonic() - stable_since >= settle_s:
            return get_window(cur)
    raise TimeoutError("window picker timed out before a stable foreground window was selected")


_EXCLUDED_PREFIXES = ("Chrome_WidgetWin",)  # VSCode / Electron host windows


def _is_excluded_class(cls: str) -> bool:
    return any(cls.startswith(p) for p in _EXCLUDED_PREFIXES)
