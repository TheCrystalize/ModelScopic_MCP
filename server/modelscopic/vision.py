"""Window capture, screenshot persistence, and OCR.

Soft-imports heavy deps (`mss`, `PIL`, `pytesseract`) so the server still starts
when only M1 is installed; the first call surfaces an actionable error.
"""

from __future__ import annotations

import base64
import hashlib
import io
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .windows import WindowInfo, WindowRect, get_window

if TYPE_CHECKING:
    from .audit import AuditLog


class VisionUnavailable(RuntimeError):
    """Raised when a required vision dep is missing."""


def _import_mss():
    try:
        import mss  # noqa: PLC0415
    except ImportError as exc:
        raise VisionUnavailable("mss is not installed — `pip install mss`") from exc
    return mss


def _import_pil():
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError as exc:
        raise VisionUnavailable("Pillow is not installed — `pip install pillow`") from exc
    return Image


def _import_pytesseract():
    try:
        import pytesseract  # noqa: PLC0415
    except ImportError as exc:
        raise VisionUnavailable(
            "pytesseract is not installed — `pip install pytesseract` AND install Tesseract OCR "
            "binary (https://github.com/UB-Mannheim/tesseract/wiki)"
        ) from exc
    import os
    cmd = os.environ.get("TESSERACT_CMD")
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    return pytesseract


@dataclass(frozen=True)
class CaptureResult:
    image_id: str
    path: str  # absolute path on disk (under the active session dir)
    width: int
    height: int
    window_rect: WindowRect
    region: WindowRect  # absolute screen rect that was captured
    base64_png: str


@dataclass(frozen=True)
class OcrBox:
    text: str
    confidence: float
    # bounding box in image-local coords (origin = top-left of captured region)
    x: int
    y: int
    width: int
    height: int


def capture_window(
    hwnd: int,
    *,
    audit: "AuditLog",
    region: WindowRect | None = None,
    include_base64: bool = True,
) -> CaptureResult:
    """Capture the target window (or a region relative to it) and persist a PNG."""
    mss = _import_mss()
    info: WindowInfo = get_window(hwnd)
    wrect = info.rect

    if region is None:
        abs_rect = wrect
    else:
        # region is window-relative; clip to window bounds
        x = max(0, min(region.x, wrect.width))
        y = max(0, min(region.y, wrect.height))
        w = max(1, min(region.width, wrect.width - x))
        h = max(1, min(region.height, wrect.height - y))
        abs_rect = WindowRect(x=wrect.x + x, y=wrect.y + y, width=w, height=h)

    with mss.MSS() as sct:
        raw = sct.grab({
            "left": abs_rect.x,
            "top": abs_rect.y,
            "width": abs_rect.width,
            "height": abs_rect.height,
        })
        png_bytes = _to_png(raw)

    image_id = hashlib.sha256(png_bytes).hexdigest()[:16]
    out_path = Path(audit.dir) / "screenshots" / f"{int(time.time() * 1000)}_{image_id}.png"
    out_path.write_bytes(png_bytes)

    return CaptureResult(
        image_id=image_id,
        path=str(out_path),
        width=abs_rect.width,
        height=abs_rect.height,
        window_rect=wrect,
        region=abs_rect,
        base64_png=base64.b64encode(png_bytes).decode("ascii") if include_base64 else "",
    )


def _to_png(raw: Any) -> bytes:
    Image = _import_pil()
    # mss returns a ScreenShot with .rgb (BGRA bytes via .raw) and .size
    img = Image.frombytes("RGB", raw.size, raw.rgb)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


# ---- OCR ---------------------------------------------------------------------

_ocr_cache: dict[str, list[OcrBox]] = {}
_OCR_CACHE_MAX = 32


def ocr_image_path(path: str) -> list[OcrBox]:
    """Run Tesseract on an image, with a tiny LRU keyed on file hash."""
    pyt = _import_pytesseract()
    Image = _import_pil()
    data = Path(path).read_bytes()
    key = hashlib.sha256(data).hexdigest()
    cached = _ocr_cache.get(key)
    if cached is not None:
        return cached

    img = Image.open(io.BytesIO(data))
    raw = pyt.image_to_data(img, output_type=pyt.Output.DICT)
    boxes: list[OcrBox] = []
    for i, text in enumerate(raw["text"]):
        text = (text or "").strip()
        if not text:
            continue
        try:
            conf = float(raw["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if conf < 0:
            continue
        boxes.append(OcrBox(
            text=text,
            confidence=conf,
            x=int(raw["left"][i]),
            y=int(raw["top"][i]),
            width=int(raw["width"][i]),
            height=int(raw["height"][i]),
        ))
    if len(_ocr_cache) >= _OCR_CACHE_MAX:
        _ocr_cache.pop(next(iter(_ocr_cache)))
    _ocr_cache[key] = boxes
    return boxes
