"""End-to-end environment self-check.

Run with: ``python -m modelscopic.doctor``

Exits 0 if every check passes, 1 otherwise. Designed to be safe to run anytime --
does not start the MCP server or open any windows.
"""

from __future__ import annotations

import importlib
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

from .handshake import HANDSHAKE_PATH


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _check_python() -> CheckResult:
    v = sys.version_info
    ok = v >= (3, 11)
    return CheckResult("python >= 3.11", ok, f"running {v.major}.{v.minor}.{v.micro}")


def _check_package(mod: str, *, label: str | None = None) -> CheckResult:
    name = label or mod
    try:
        m = importlib.import_module(mod)
    except ImportError as exc:
        return CheckResult(f"package: {name}", False, str(exc))
    version = getattr(m, "__version__", "(unknown)")
    return CheckResult(f"package: {name}", True, f"v{version}")


def _check_pywin32() -> CheckResult:
    if sys.platform != "win32":
        return CheckResult("package: pywin32", True, "skipped (non-Windows)")
    try:
        importlib.import_module("win32gui")
        importlib.import_module("win32process")
    except ImportError as exc:
        return CheckResult("package: pywin32", False, str(exc))
    return CheckResult("package: pywin32", True, "win32gui + win32process importable")


def _check_tesseract() -> CheckResult:
    try:
        import pytesseract  # noqa: PLC0415
    except ImportError as exc:
        return CheckResult("tesseract binary", False, f"pytesseract not installed: {exc}")
    cmd = os.environ.get("TESSERACT_CMD")
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        version = pytesseract.get_tesseract_version()
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            "tesseract binary",
            False,
            f"could not run tesseract: {exc}\n"
            "       Install from https://github.com/UB-Mannheim/tesseract/wiki\n"
            "       Then set TESSERACT_CMD env var or add it to PATH.",
        )
    return CheckResult("tesseract binary", True, f"v{version} via {pytesseract.pytesseract.tesseract_cmd}")


def _check_ocr_roundtrip() -> CheckResult:
    try:
        import pytesseract  # noqa: PLC0415
        from PIL import Image, ImageDraw  # noqa: PLC0415
    except ImportError as exc:
        return CheckResult("ocr roundtrip", False, str(exc))
    cmd = os.environ.get("TESSERACT_CMD")
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    img = Image.new("RGB", (260, 60), "white")
    d = ImageDraw.Draw(img)
    needle = "ModelScopic"
    d.text((10, 15), f"{needle} OCR 12345", fill="black")
    try:
        out = pytesseract.image_to_string(img).strip()
    except Exception as exc:  # noqa: BLE001
        return CheckResult("ocr roundtrip", False, f"OCR raised: {exc}")
    ok = needle.lower() in out.lower()
    return CheckResult("ocr roundtrip", ok, f"got {out!r}")


def _check_screen_capture() -> CheckResult:
    try:
        import mss  # noqa: PLC0415
    except ImportError as exc:
        return CheckResult("screen capture", False, str(exc))
    try:
        with mss.MSS() as sct:
            monitors = sct.monitors
    except Exception as exc:  # noqa: BLE001
        return CheckResult("screen capture", False, f"mss failed: {exc}")
    return CheckResult("screen capture", True, f"{len(monitors) - 1} monitor(s) detected")


def _check_handshake() -> CheckResult:
    if HANDSHAKE_PATH.exists():
        return CheckResult(
            "vscode bridge handshake",
            True,
            f"found at {HANDSHAKE_PATH} -- extension is running",
        )
    return CheckResult(
        "vscode bridge handshake",
        False,
        f"not found at {HANDSHAKE_PATH} -- start the ModelScopic VSCode extension (F5 in vscode-extension/)",
    )


def _check_sessions_dir() -> CheckResult:
    p = Path.home() / ".modelscopic"
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".write_probe"
        probe.write_text("ok", encoding="utf8")
        probe.unlink()
    except Exception as exc:  # noqa: BLE001
        return CheckResult("sessions dir writable", False, f"{p}: {exc}")
    return CheckResult("sessions dir writable", True, str(p))


CHECKS = [
    _check_python,
    lambda: _check_package("mcp"),
    lambda: _check_package("websockets"),
    lambda: _check_package("mss"),
    lambda: _check_package("PIL", label="pillow"),
    lambda: _check_package("pytesseract"),
    _check_pywin32,
    _check_tesseract,
    _check_ocr_roundtrip,
    _check_screen_capture,
    _check_handshake,
    _check_sessions_dir,
]


def main() -> int:
    results: list[CheckResult] = []
    for c in CHECKS:
        try:
            results.append(c())
        except Exception as exc:  # noqa: BLE001
            results.append(CheckResult(c.__name__, False, "unhandled: " + "".join(traceback.format_exception_only(type(exc), exc))))

    width = max(len(r.name) for r in results) + 2
    failed = 0
    for r in results:
        mark = "[OK]" if r.ok else "[!!]"
        print(f"{mark} {r.name.ljust(width)} {r.detail}")
        if not r.ok:
            failed += 1

    print()
    print(f"{len(results) - failed}/{len(results)} checks passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
