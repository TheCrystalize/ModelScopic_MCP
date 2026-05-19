"""Diagnostic: type a known string at varying delays and report what Notepad gets back.

Run: ``python tests/diag_typing.py``

This launches Notepad, types `Hello world 12345.` at delays of 15/30/60ms,
then OCRs each result to see which delay actually works on this machine.

You'll see Notepad appear, fill, clear, fill, clear, fill. Don't touch anything.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modelscopic import input as inp, vision, windows  # noqa: E402
from modelscopic.audit import AuditLog  # noqa: E402


TEST_STRING = "Hello world 12345."


def find_notepad() -> windows.WindowInfo:
    for _ in range(20):
        for w in windows.list_windows():
            if w.class_name in {"Notepad", "ApplicationFrameWindow"} and (
                "Notepad" in w.title or "Untitled" in w.title or "Text Document" in w.title
            ):
                if w.rect.width > 100:
                    return w
        time.sleep(0.25)
    raise RuntimeError("Notepad not found")


def clear_notepad(hwnd: int) -> None:
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.2)
    inp.send_chord("ctrl+a")
    time.sleep(0.1)
    inp.send_chord("delete")
    time.sleep(0.2)


def main() -> int:
    windows.set_dpi_awareness()
    proc = subprocess.Popen(["notepad.exe"])
    try:
        info = find_notepad()
        print(f"found notepad hwnd={info.hwnd}")
        audit = AuditLog("diag_typing")

        ctypes.windll.user32.SetForegroundWindow(info.hwnd)
        time.sleep(0.5)

        for delay in (15, 30, 60, 120):
            clear_notepad(info.hwnd)
            print(f"\n--- per_char_delay_ms={delay} ---")
            print(f"sending: {TEST_STRING!r}")
            inp.type_text(TEST_STRING, per_char_delay_ms=delay)
            time.sleep(0.6)
            cap = vision.capture_window(info.hwnd, audit=audit, include_base64=False)
            boxes = vision.ocr_image_path(cap.path)
            # find boxes likely inside the text area (skip title bar / menu)
            body = [b for b in boxes if b.y > 100 and b.confidence > 30]
            body.sort(key=lambda b: (b.y, b.x))
            seen = " ".join(b.text for b in body)
            print(f"OCR saw in body: {seen!r}")
            ok = "Hello world 12345" in seen or "Hello world 12345." in seen
            print(f"{'PASS' if ok else 'FAIL'} at {delay}ms")

        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
