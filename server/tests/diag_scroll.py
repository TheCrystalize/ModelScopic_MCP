"""Scroll diagnostic v3: resize Notepad to a tiny window so 15 lines overflow,
then verify wheel events change visible pixels.

Run: ``python tests/diag_scroll.py``

What you see:
  1. Notepad opens, resizes to 600x400.
  2. ~15 short lines typed (~13 seconds).
  3. ctrl+home, screenshot A.
  4. wheel down, screenshot B.
  5. wheel up, screenshot C.
  6. Pixel-diff A vs B vs C to confirm scroll moved content.

Don't touch keyboard/mouse during the run.
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


def find_notepad() -> windows.WindowInfo:
    for _ in range(20):
        for w in windows.list_windows():
            if w.class_name in {"Notepad", "ApplicationFrameWindow"} and (
                "Notepad" in w.title or "Text Document" in w.title
            ):
                return w
        time.sleep(0.25)
    raise RuntimeError("Notepad not found")


def pixel_diff_fraction(path_a: str, path_b: str) -> float:
    from PIL import Image, ImageChops  # noqa: PLC0415
    a = Image.open(path_a).convert("RGB")
    b = Image.open(path_b).convert("RGB")
    if a.size != b.size:
        return 1.0
    diff = ImageChops.difference(a, b)
    if diff.getbbox() is None:
        return 0.0
    total = a.size[0] * a.size[1]
    differing = sum(1 for px in diff.getdata() if max(px) > 5)
    return differing / total


import re as _re

_NUM_RE = _re.compile(r"^[@0]?(\d{1,2})[:.]?$")  # Tesseract often reads '0' as '@'


def visible_line_numbers(boxes: list) -> list[int]:
    """OCR boxes -> sorted list of line numbers visible.

    Notepad renders 'Line 01: row' but Tesseract splits it into separate boxes
    ['Line', '01:', 'row']. We pair each 'Line' box with whatever number-like
    box is immediately to its right on the same row.
    """
    boxes = [b for b in boxes if b.confidence >= 40]
    # group by approximate row
    rows: dict[int, list] = {}
    for b in boxes:
        row_key = b.y // 8  # tolerate small y jitter
        rows.setdefault(row_key, []).append(b)
    nums: set[int] = set()
    for row_boxes in rows.values():
        row_boxes.sort(key=lambda b: b.x)
        for i, b in enumerate(row_boxes):
            if b.text.strip().lower() != "line":
                continue
            # Look at the next 1-2 boxes for a digit-like token
            for j in range(i + 1, min(i + 3, len(row_boxes))):
                m = _NUM_RE.match(row_boxes[j].text.strip())
                if m:
                    try:
                        n = int(m.group(1))
                        if 1 <= n <= 99:
                            nums.add(n)
                            break
                    except ValueError:
                        pass
    return sorted(nums)


def main() -> int:
    windows.set_dpi_awareness()
    proc = subprocess.Popen(["notepad.exe"])
    try:
        info = find_notepad()
        print(f"found notepad hwnd={info.hwnd}  initial rect={info.rect}")
        audit = AuditLog("diag_scroll")

        # Shrink the window so 15 lines overflow it.
        info = windows.set_window_bounds(info.hwnd, x=100, y=100, width=600, height=400)
        print(f"resized to: {info.rect}")
        time.sleep(0.3)

        def _lock_size():
            return windows.set_window_bounds(info.hwnd, x=100, y=100, width=600, height=400)

        ctypes.windll.user32.SetForegroundWindow(info.hwnd)
        time.sleep(0.4)

        body = "".join(f"Line {n:02d}: row\n" for n in range(1, 16))
        print(f"typing {len(body)} chars (~{int(len(body) * 0.06)}s)...")
        inp.type_text(body, per_char_delay_ms=60)
        time.sleep(0.4)

        # Cursor to top so the initial view is deterministic.
        inp.send_chord("ctrl+home")
        time.sleep(0.3)

        # Re-lock size right before capture (Notepad may have grown the window).
        _lock_size()
        time.sleep(0.2)
        cap_a = vision.capture_window(info.hwnd, audit=audit, include_base64=False)
        print(f"[A] before scroll: {cap_a.path}  ({cap_a.width}x{cap_a.height})")

        cx, cy = 300, 200  # known coordinates inside 600x400 window
        print(f"\nscrolling DOWN 3 notches at window-rel ({cx},{cy})...")
        inp.scroll(info.hwnd, cx, cy, dy=-3)
        time.sleep(0.6)

        _lock_size()
        time.sleep(0.2)
        cap_b = vision.capture_window(info.hwnd, audit=audit, include_base64=False)
        print(f"[B] after DOWN:   {cap_b.path}  ({cap_b.width}x{cap_b.height})")

        print(f"\nscrolling UP 3 notches...")
        inp.scroll(info.hwnd, cx, cy, dy=3)
        time.sleep(0.6)

        _lock_size()
        time.sleep(0.2)
        cap_c = vision.capture_window(info.hwnd, audit=audit, include_base64=False)
        print(f"[C] after UP:     {cap_c.path}  ({cap_c.width}x{cap_c.height})")

        # OCR-based verdict: find which line numbers are visible in each snapshot
        lines_a = visible_line_numbers(vision.ocr_image_path(cap_a.path))
        lines_b = visible_line_numbers(vision.ocr_image_path(cap_b.path))
        lines_c = visible_line_numbers(vision.ocr_image_path(cap_c.path))

        print()
        print(f"visible lines [A]:  {lines_a}")
        print(f"visible lines [B]:  {lines_b}")
        print(f"visible lines [C]:  {lines_c}")

        def top(xs: list[int]) -> int | None:
            return xs[0] if xs else None

        top_a, top_b, top_c = top(lines_a), top(lines_b), top(lines_c)

        down_worked = top_a is not None and top_b is not None and top_b > top_a
        up_worked = top_b is not None and top_c is not None and top_c < top_b

        print()
        print(f"scroll DOWN moved viewport forward (top {top_a} -> {top_b}): {'PASS' if down_worked else 'FAIL'}")
        print(f"scroll UP moved viewport backward (top {top_b} -> {top_c}):  {'PASS' if up_worked else 'FAIL'}")

        return 0 if (down_worked and up_worked) else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
