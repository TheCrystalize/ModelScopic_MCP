"""Window capture, screenshot persistence, and OCR.

Soft-imports heavy deps (`mss`, `PIL`, `pytesseract`) so the server still starts
when only M1 is installed; the first call surfaces an actionable error.

Performance notes (see commit history for the OCR-speedup pass):
- Screenshot capture is fast (~25ms) -- the cost is PNG encoding + disk write.
  Writes use compress_level=0 (uncompressed) for ~5x faster save on a typical
  desktop screenshot. Files get larger (~3-5x), but session folders are
  ephemeral and local, so disk usage is not the bottleneck.
- OCR is the wall-clock dominator (~1.5s on a 2560x1440 capture). The cache
  is keyed on image_id (content hash from capture), so re-OCR of the same
  capture is free without a disk re-read.
- Tested RapidOCR (ONNX) as an alternative: actually 2x SLOWER than Tesseract
  on this stack. Tesseract is the right default.
"""

from __future__ import annotations

import base64
import hashlib
import io
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .windows import WindowInfo, WindowRect, get_window

if TYPE_CHECKING:
    from .audit import AuditLog
    from PIL import Image as _PILImage  # for type hints only


class VisionUnavailable(RuntimeError):
    """Raised when a required vision dep is missing."""


def _import_mss():
    try:
        import mss  # noqa: PLC0415
    except ImportError as exc:
        raise VisionUnavailable("mss is not installed -- `pip install mss`") from exc
    return mss


def _import_pil():
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError as exc:
        raise VisionUnavailable("Pillow is not installed -- `pip install pillow`") from exc
    return Image


def _import_pytesseract():
    try:
        import pytesseract  # noqa: PLC0415
    except ImportError as exc:
        raise VisionUnavailable(
            "pytesseract is not installed -- `pip install pytesseract` AND install Tesseract OCR "
            "binary (https://github.com/UB-Mannheim/tesseract/wiki)"
        ) from exc
    import os
    cmd = os.environ.get("TESSERACT_CMD")
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    return pytesseract


@dataclass
class CaptureResult:
    image_id: str
    path: str  # absolute path on disk (under the active session dir)
    width: int
    height: int
    window_rect: WindowRect
    region: WindowRect  # absolute screen rect that was captured
    base64_png: str
    # In-memory image so OCR doesn't have to re-read + re-decode from disk.
    # Excluded from the public dataclass display.
    image: Any = field(default=None, repr=False, compare=False)


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
    Image = _import_pil()
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
        # Keep the PIL Image in memory -- the same object feeds both the PNG
        # encoder for persistence and the OCR engine without a re-decode.
        img = Image.frombytes("RGB", raw.size, raw.rgb)

    # Compress level 0 = no zlib compression. Faster save, larger files;
    # session folders are ephemeral so disk usage doesn't matter.
    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=0)
    png_bytes = buf.getvalue()

    # image_id only needs to be unique-within-session for the OCR cache and
    # for clickable filenames. Skip the SHA256 of a multi-MB buffer.
    image_id = f"{int(time.perf_counter() * 1_000_000):016x}"

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
        image=img,
    )


# ---- OCR ---------------------------------------------------------------------

_ocr_cache: dict[str, list[OcrBox]] = {}
_OCR_CACHE_MAX = 32


def _store_cached(key: str, boxes: list[OcrBox]) -> list[OcrBox]:
    if len(_ocr_cache) >= _OCR_CACHE_MAX:
        _ocr_cache.pop(next(iter(_ocr_cache)))
    _ocr_cache[key] = boxes
    return boxes


def _run_tesseract(img: "_PILImage.Image") -> list[OcrBox]:
    pyt = _import_pytesseract()
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
    return boxes


def ocr_capture(cap: CaptureResult) -> list[OcrBox]:
    """Preferred OCR entry point: no disk re-read, image_id-keyed cache."""
    cached = _ocr_cache.get(cap.image_id)
    if cached is not None:
        return cached
    Image = _import_pil()
    img = cap.image
    if img is None:
        # Fallback: capture didn't carry the in-memory image (older callers, replay)
        img = Image.open(cap.path)
    return _store_cached(cap.image_id, _run_tesseract(img))


def ocr_image_path(path: str) -> list[OcrBox]:
    """Compatibility entry: OCR a PNG on disk. Cached by file hash."""
    Image = _import_pil()
    data = Path(path).read_bytes()
    key = hashlib.sha256(data).hexdigest()
    cached = _ocr_cache.get(key)
    if cached is not None:
        return cached
    img = Image.open(io.BytesIO(data))
    return _store_cached(key, _run_tesseract(img))
