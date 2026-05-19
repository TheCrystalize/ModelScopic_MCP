"""Full-stack smoke test: launches Notepad, captures it, OCRs it, types text, screenshots again.

Run: ``python tests/smoke_full.py``

This drives the SessionManager + vision + input + audit log directly -- the same
code paths the MCP server uses, but without the MCP client. The VSCode bridge is
NOT required for this test (we don't touch the extension).

What you should see while it runs:
  1. Notepad opens.
  2. The script focuses it and types text into it.
  3. The script reports the OCR'd contents of the window.
  4. PNGs land in ~/.modelscopic/sessions/<id>/screenshots/
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path

# allow running this file directly without an editable install
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modelscopic import input as inp, vision, windows  # noqa: E402
from modelscopic.session import SessionManager  # noqa: E402


def find_notepad(retries: int = 20, delay: float = 0.25) -> windows.WindowInfo:
    """Poll list_windows for a Notepad window."""
    for _ in range(retries):
        for w in windows.list_windows():
            if w.class_name in {"Notepad", "ApplicationFrameWindow"} and (
                "Notepad" in w.title or "Untitled" in w.title
            ):
                if w.rect.width > 100 and w.rect.height > 100:
                    return w
        time.sleep(delay)
    raise RuntimeError("could not find Notepad window")


async def main() -> int:
    windows.set_dpi_awareness()
    manager = SessionManager()

    print("=== launching Notepad ===")
    proc = subprocess.Popen(["notepad.exe"])
    try:
        info = find_notepad()
        print(f"OK   found {info.title!r} hwnd={info.hwnd} rect={info.rect}")

        print()
        print("=== session_start ===")
        s = manager.start()
        print(f"OK   session_id={s['session_id']}")
        print(f"     dir={s['dir']}")
        manager.set_target(
            hwnd=info.hwnd, title=info.title, class_name=info.class_name, pid=info.process_id,
        )
        print(f"OK   target bound: hwnd={info.hwnd}")

        # focus the window before typing
        import ctypes
        ctypes.windll.user32.SetForegroundWindow(info.hwnd)
        time.sleep(0.5)

        print()
        print("=== type_text ===")
        body = "Hello from ModelScopic smoke test!\nLine 2 with digits 12345.\n"
        n = inp.type_text(body)
        print(f"OK   sent {n} chars")
        time.sleep(0.5)

        print()
        print("=== screenshot ===")
        cap = vision.capture_window(info.hwnd, audit=manager.audit, include_base64=False)
        print(f"OK   captured {cap.width}x{cap.height} -> {cap.path}")

        print()
        print("=== ocr ===")
        boxes = vision.ocr_image_path(cap.path)
        print(f"OK   {len(boxes)} OCR boxes (showing top 10 by confidence)")
        boxes_sorted = sorted(boxes, key=lambda b: -b.confidence)[:10]
        for b in boxes_sorted:
            print(f"     {b.confidence:5.1f}%  {b.text!r}  @ ({b.x},{b.y}) {b.width}x{b.height}")

        # Verification: does at least one box contain text we typed?
        typed_words = {"Hello", "ModelScopic", "smoke", "12345"}
        seen = {w for b in boxes for w in typed_words if w.lower() in b.text.lower()}
        print()
        if seen:
            print(f"PASS: OCR recognised typed words: {sorted(seen)}")
            result = 0
        else:
            print("FAIL: none of the typed words appeared in OCR output")
            result = 1

        print()
        print("=== click ===")
        # click roughly center of the window
        cx, cy = info.rect.width // 2, info.rect.height // 2
        pt = inp.click_mouse(info.hwnd, cx, cy)
        print(f"OK   clicked window-rel ({cx},{cy}) -> screen ({pt.x},{pt.y})")

        print()
        print("=== session_end (wipe) ===")
        ended = manager.end(keep=False, reason="")
        print(f"OK   wiped={ended['wiped']} dir={ended['dir']}")
        print()
        print(f"Note: session folder was wiped. Re-run with `keep=True` in the script to inspect screenshots.")

        return result
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
