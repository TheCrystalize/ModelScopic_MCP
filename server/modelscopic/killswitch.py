"""Global hotkey kill switch.

Registers Ctrl+Alt+Esc via Win32 RegisterHotKey on a dedicated daemon thread
that runs a GetMessage loop. When pressed, it sets an asyncio.Event the rest of
the server polls (cheap; checked once per gated tool call).
"""

from __future__ import annotations

import asyncio
import ctypes
import sys
import threading
from ctypes import wintypes
from dataclasses import dataclass

WINDOWS = sys.platform == "win32"

# Modifiers for RegisterHotKey
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000

VK_ESCAPE = 0x1B

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


@dataclass
class KillSwitch:
    triggered: asyncio.Event
    reason: str = ""

    def __init__(self) -> None:
        self.triggered = asyncio.Event()
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.reason = ""

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if not WINDOWS:
            return
        if self._thread is not None:
            return
        self._loop = loop
        self._thread = threading.Thread(target=self._run, name="killswitch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        if self._thread_id is not None and WINDOWS:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread.join(timeout=1.0)
        self._thread = None
        self._thread_id = None

    def consume(self) -> bool:
        """Return True (and clear) if a trigger is pending."""
        if self.triggered.is_set():
            self.triggered.clear()
            self.reason = ""
            return True
        return False

    def _trip(self, reason: str) -> None:
        self.reason = reason
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self.triggered.set)

    def _run(self) -> None:
        assert WINDOWS
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        HOTKEY_ID = 0xC0DE
        if not user32.RegisterHotKey(
            None, HOTKEY_ID, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_ESCAPE,
        ):
            return  # already registered by someone else; silently no-op
        try:
            msg = wintypes.MSG()
            while True:
                bRet = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if bRet == 0 or bRet == -1:  # WM_QUIT or error
                    return
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    self._trip("user pressed Ctrl+Alt+Esc")
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)
