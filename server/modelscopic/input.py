"""Mouse + keyboard injection via Win32 SendInput.

Coordinates are always **window-relative**. The caller passes (x, y) in the
target window's client space; we convert to absolute screen coords using a
fresh ``GetWindowRect`` so window moves between actions are tolerated. Inputs
outside the window bounds are rejected.

Why SendInput directly instead of pyautogui/pydirectinput:
- pyautogui uses keybd_event/mouse_event (legacy); some games ignore them.
- pydirectinput patches pyautogui but is an extra dep and we already need ctypes
  for kill-switch hotkeys.
- SendInput is one ctypes call, very small surface, no opaque dependency.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass

from .windows import WindowsOnly, WindowRect, get_window

WINDOWS = sys.platform == "win32"


# ---- Win32 plumbing ---------------------------------------------------------

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x01000

# Window messages for PostMessage-based scrolling
WM_MOUSEWHEEL = 0x020A
WM_MOUSEHWHEEL = 0x020E
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0001

WHEEL_DELTA = 120


if WINDOWS:
    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]

    user32 = ctypes.windll.user32
    user32.SendInput.restype = wintypes.UINT
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
    user32.SetCursorPos.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user32.PostMessageW.restype = wintypes.BOOL
    user32.WindowFromPoint.argtypes = (wintypes.POINT,)
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.ChildWindowFromPointEx.argtypes = (wintypes.HWND, wintypes.POINT, wintypes.UINT)
    user32.ChildWindowFromPointEx.restype = wintypes.HWND
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79
    SM_XVIRTUALSCREEN = 76
    SM_YVIRTUALSCREEN = 77


def _require_win32() -> None:
    if not WINDOWS:
        raise WindowsOnly("input injection requires Windows")


@dataclass(frozen=True)
class ScreenPoint:
    x: int
    y: int


def window_to_screen(hwnd: int, x: int, y: int) -> ScreenPoint:
    """Convert window-relative coords to absolute screen coords. Raises if OOB."""
    info = get_window(hwnd)
    r: WindowRect = info.rect
    if not (0 <= x < r.width and 0 <= y < r.height):
        raise ValueError(
            f"({x}, {y}) is outside window bounds {r.width}x{r.height}"
        )
    return ScreenPoint(r.x + x, r.y + y)


def _send(inputs: list) -> None:
    _require_win32()
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    sent = user32.SendInput(n, arr, ctypes.sizeof(INPUT))
    if sent != n:
        raise OSError(f"SendInput sent {sent}/{n} events; GetLastError={ctypes.get_last_error()}")


# ---- Mouse ------------------------------------------------------------------


def _mouse_input(dx: int, dy: int, flags: int, data: int = 0) -> "INPUT":
    return INPUT(type=INPUT_MOUSE, u=_INPUT_UNION(mi=MOUSEINPUT(dx, dy, data, flags, 0, 0)))


def _absolute_mouse_move(screen: ScreenPoint) -> "INPUT":
    """Build an absolute-move input across the virtual desktop."""
    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN) or 1
    vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN) or 1
    # SendInput absolute coords are 0..65535 across the virtual screen
    nx = int(((screen.x - vx) * 65535) / vw)
    ny = int(((screen.y - vy) * 65535) / vh)
    return _mouse_input(nx, ny, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK)


_BUTTON_DOWN = {
    "left": MOUSEEVENTF_LEFTDOWN,
    "right": MOUSEEVENTF_RIGHTDOWN,
    "middle": MOUSEEVENTF_MIDDLEDOWN,
}
_BUTTON_UP = {
    "left": MOUSEEVENTF_LEFTUP,
    "right": MOUSEEVENTF_RIGHTUP,
    "middle": MOUSEEVENTF_MIDDLEUP,
}


def move_mouse(hwnd: int, x: int, y: int) -> ScreenPoint:
    _require_win32()
    pt = window_to_screen(hwnd, x, y)
    _send([_absolute_mouse_move(pt)])
    return pt


def click_mouse(
    hwnd: int, x: int, y: int, *, button: str = "left", clicks: int = 1, delay_ms: int = 40,
) -> ScreenPoint:
    _require_win32()
    if button not in _BUTTON_DOWN:
        raise ValueError(f"unknown button: {button}")
    pt = window_to_screen(hwnd, x, y)
    move = _absolute_mouse_move(pt)
    down = _mouse_input(0, 0, _BUTTON_DOWN[button])
    up = _mouse_input(0, 0, _BUTTON_UP[button])
    for _ in range(clicks):
        _send([move, down, up])
        time.sleep(delay_ms / 1000.0)
    return pt


def scroll(hwnd: int, x: int, y: int, *, dy: int = 0, dx: int = 0) -> ScreenPoint:
    """Scroll at (x, y) by `dy` notches (positive = up) and `dx` notches (positive = right).

    Wheel routing on Windows is annoyingly complex:
    - SendInput(MOUSEEVENTF_WHEEL) goes to the window under the OS cursor, with
      no way to override. Races with focus/cursor changes and often fails.
    - PostMessage(top-level hwnd, WM_MOUSEWHEEL) is ignored by many modern apps
      because the actual scrollable control is a deep child (UWP hosts, Electron,
      anything with WebView2 -- including Win11 Notepad).
    - Resolving the child via WindowFromPoint and posting THERE works reliably.

    We do all three -- WindowFromPoint -> child, then post the message; if the
    deepest child is the same as hwnd we still post once; and as belt-and-braces
    we also queue a SendInput wheel after moving the cursor.
    """
    _require_win32()
    pt = window_to_screen(hwnd, x, y)
    # POINT for WindowFromPoint
    pt_struct = wintypes.POINT(pt.x, pt.y)
    target = user32.WindowFromPoint(pt_struct) or hwnd
    # Walk down to the deepest child at this point
    while True:
        child = user32.ChildWindowFromPointEx(target, pt_struct, 0)  # CWP_ALL = 0
        if not child or child == target:
            break
        target = child

    lparam = ((pt.y & 0xFFFF) << 16) | (pt.x & 0xFFFF)

    if dy:
        delta = dy * WHEEL_DELTA
        wparam = ((delta & 0xFFFF) << 16) & 0xFFFFFFFF
        user32.PostMessageW(target, WM_MOUSEWHEEL, wparam, lparam)
    if dx:
        delta = dx * WHEEL_DELTA
        wparam = ((delta & 0xFFFF) << 16) & 0xFFFFFFFF
        user32.PostMessageW(target, WM_MOUSEHWHEEL, wparam, lparam)

    # Belt-and-braces: also dispatch via SendInput in case the target ignores
    # PostMessage (some apps only honor synthesized hardware input).
    user32.SetCursorPos(pt.x, pt.y)
    time.sleep(0.02)
    if dy:
        _send([_mouse_input(0, 0, MOUSEEVENTF_WHEEL, dy * WHEEL_DELTA)])
    if dx:
        _send([_mouse_input(0, 0, MOUSEEVENTF_HWHEEL, dx * WHEEL_DELTA)])
    return pt


def drag(
    hwnd: int, x1: int, y1: int, x2: int, y2: int, *, button: str = "left", hold_ms: int = 80,
) -> tuple[ScreenPoint, ScreenPoint]:
    _require_win32()
    if button not in _BUTTON_DOWN:
        raise ValueError(f"unknown button: {button}")
    p1 = window_to_screen(hwnd, x1, y1)
    p2 = window_to_screen(hwnd, x2, y2)
    _send([_absolute_mouse_move(p1), _mouse_input(0, 0, _BUTTON_DOWN[button])])
    time.sleep(hold_ms / 1000.0)
    _send([_absolute_mouse_move(p2)])
    time.sleep(hold_ms / 1000.0)
    _send([_mouse_input(0, 0, _BUTTON_UP[button])])
    return p1, p2


# ---- Keyboard ---------------------------------------------------------------


def type_text(text: str, *, per_char_delay_ms: int = 60) -> int:
    """Type Unicode text. Returns number of characters sent.

    Implementation notes -- learned the hard way:
    - down + up MUST be two separate SendInput calls. Batching them in one call
      lets Windows coalesce them, which can drop spaces and trigger autorepeat
      on the previous character.
    - Newlines go via VK_RETURN (with EXTENDEDKEY) rather than Unicode 0x0A;
      most apps treat 0x0A as a literal LF glyph or ignore it.
    - Chars outside the BMP (>= 0x10000) are sent as UTF-16 surrogate pairs.
    """
    _require_win32()
    sent = 0
    for ch in text:
        if ch in ("\n", "\r"):
            _press_vk(0x0D, extended=True)
        else:
            _type_unicode_char(ch)
        if per_char_delay_ms:
            time.sleep(per_char_delay_ms / 1000.0)
        sent += 1
    return sent


def _type_unicode_char(ch: str) -> None:
    cp = ord(ch)
    if cp <= 0xFFFF:
        _press_unicode(cp)
        return
    # Encode as a surrogate pair
    cp -= 0x10000
    high = 0xD800 | (cp >> 10)
    low = 0xDC00 | (cp & 0x3FF)
    _press_unicode(high)
    _press_unicode(low)


def _press_unicode(code: int) -> None:
    down = INPUT(type=INPUT_KEYBOARD, u=_INPUT_UNION(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, 0)))
    up = INPUT(type=INPUT_KEYBOARD, u=_INPUT_UNION(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)))
    _send([down])
    _send([up])


def _press_vk(vk: int, *, extended: bool = False) -> None:
    flags_down = KEYEVENTF_EXTENDEDKEY if extended else 0
    flags_up = flags_down | KEYEVENTF_KEYUP
    down = INPUT(type=INPUT_KEYBOARD, u=_INPUT_UNION(ki=KEYBDINPUT(vk, 0, flags_down, 0, 0)))
    up = INPUT(type=INPUT_KEYBOARD, u=_INPUT_UNION(ki=KEYBDINPUT(vk, 0, flags_up, 0, 0)))
    _send([down])
    _send([up])


# Virtual-key codes for chord parsing
_VK = {
    "ctrl": 0x11, "control": 0x11,
    "alt": 0x12, "menu": 0x12,
    "shift": 0x10,
    "win": 0x5B, "meta": 0x5B, "cmd": 0x5B,
    "enter": 0x0D, "return": 0x0D,
    "esc": 0x1B, "escape": 0x1B,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08, "back": 0x08,
    "delete": 0x2E, "del": 0x2E,
    "insert": 0x2D, "ins": 0x2D,
    "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pgup": 0x21,
    "pagedown": 0x22, "pgdn": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "capslock": 0x14,
}
for i in range(1, 13):
    _VK[f"f{i}"] = 0x6F + i  # F1=0x70 .. F12=0x7B; 0x6F+1=0x70 ✓
for i in range(10):
    _VK[str(i)] = 0x30 + i
for i in range(26):
    _VK[chr(ord("a") + i)] = 0x41 + i

# Keys that require the EXTENDED flag for correct delivery
_EXTENDED = {0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22, 0x26, 0x28, 0x25, 0x27, 0x5B}


def parse_chord(spec: str) -> list[int]:
    """Parse a chord like 'ctrl+shift+s' or 'alt+f4' into a list of VK codes."""
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError("empty key chord")
    vks: list[int] = []
    for p in parts:
        if p not in _VK:
            raise ValueError(f"unknown key: {p}")
        vks.append(_VK[p])
    return vks


def send_chord(spec: str) -> None:
    """Press keys in order, then release in reverse order."""
    _require_win32()
    vks = parse_chord(spec)
    down_inputs: list = []
    up_inputs: list = []
    for vk in vks:
        flags_down = KEYEVENTF_EXTENDEDKEY if vk in _EXTENDED else 0
        flags_up = flags_down | KEYEVENTF_KEYUP
        down_inputs.append(INPUT(type=INPUT_KEYBOARD, u=_INPUT_UNION(ki=KEYBDINPUT(vk, 0, flags_down, 0, 0))))
        up_inputs.append(INPUT(type=INPUT_KEYBOARD, u=_INPUT_UNION(ki=KEYBDINPUT(vk, 0, flags_up, 0, 0))))
    _send(down_inputs)
    _send(list(reversed(up_inputs)))
