"""Vision tools: window enumeration, screenshot, region screenshot, OCR, wait_for_text.

All gated by the session breaker except `list_windows` (read-only, used during setup).
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import TYPE_CHECKING, Any

from .. import vision, windows
from ..session import SessionManager

if TYPE_CHECKING:
    from . import ToolRegistry


def register(reg: "ToolRegistry", *, manager: SessionManager) -> None:
    from . import ToolSpec

    async def _list_windows(_: dict[str, Any]) -> Any:
        wins = await asyncio.to_thread(windows.list_windows)
        return {
            "windows": [
                {
                    "hwnd": w.hwnd,
                    "title": w.title,
                    "class_name": w.class_name,
                    "pid": w.process_id,
                    "rect": {"x": w.rect.x, "y": w.rect.y, "width": w.rect.width, "height": w.rect.height},
                }
                for w in wins
            ]
        }

    async def _screenshot(args: dict[str, Any]) -> Any:
        hwnd = manager.require_target()
        include_b64 = bool(args.get("include_base64", True))
        result = await asyncio.to_thread(
            vision.capture_window, hwnd, audit=manager.audit, region=None, include_base64=include_b64
        )
        return serialize_capture(result, manager=manager)

    async def _screenshot_region(args: dict[str, Any]) -> Any:
        hwnd = manager.require_target()
        region = windows.WindowRect(
            x=int(args["x"]), y=int(args["y"]), width=int(args["width"]), height=int(args["height"]),
        )
        include_b64 = bool(args.get("include_base64", True))
        result = await asyncio.to_thread(
            vision.capture_window, hwnd, audit=manager.audit, region=region, include_base64=include_b64,
        )
        return serialize_capture(result, manager=manager)

    async def _ocr(args: dict[str, Any]) -> Any:
        hwnd = manager.require_target()
        region = _opt_region(args)
        cap = await asyncio.to_thread(
            vision.capture_window, hwnd, audit=manager.audit, region=region, include_base64=False,
        )
        boxes = await asyncio.to_thread(vision.ocr_capture, cap)
        min_conf = float(args.get("min_confidence", 50.0))
        return {
            "image_id": cap.image_id,
            "path": cap.path,
            "boxes": [
                {
                    "text": b.text, "confidence": b.confidence,
                    "x": b.x, "y": b.y, "width": b.width, "height": b.height,
                }
                for b in boxes if b.confidence >= min_conf
            ],
        }

    async def _wait_for_text(args: dict[str, Any]) -> Any:
        hwnd = manager.require_target()
        pattern_src = str(args["pattern"])
        flags = re.IGNORECASE if args.get("case_insensitive", True) else 0
        pattern = re.compile(pattern_src, flags)
        timeout_ms = int(args.get("timeout_ms", 5000))
        poll_ms = int(args.get("poll_ms", 250))
        min_conf = float(args.get("min_confidence", 50.0))
        region = _opt_region(args)

        deadline = time.monotonic() + timeout_ms / 1000.0
        while time.monotonic() < deadline:
            cap = await asyncio.to_thread(
                vision.capture_window, hwnd, audit=manager.audit, region=region, include_base64=False,
            )
            boxes = await asyncio.to_thread(vision.ocr_capture, cap)
            for b in boxes:
                if b.confidence >= min_conf and pattern.search(b.text):
                    return {
                        "found": True,
                        "image_id": cap.image_id,
                        "match": {"text": b.text, "x": b.x, "y": b.y, "width": b.width, "height": b.height},
                    }
            await asyncio.sleep(poll_ms / 1000.0)
        return {"found": False, "timeout_ms": timeout_ms}

    async def _session_pick(args: dict[str, Any]) -> Any:
        timeout = float(args.get("timeout_s", 30.0))
        info = await windows.pick_window_by_foreground(timeout_s=timeout)
        manager.set_target(
            hwnd=info.hwnd, title=info.title, class_name=info.class_name, pid=info.process_id,
        )
        return _serialize_window(info)

    async def _session_retarget(args: dict[str, Any]) -> Any:
        # Two modes: explicit hwnd OR re-pick via foreground
        if "hwnd" in args and args["hwnd"] is not None:
            info = await asyncio.to_thread(windows.get_window, int(args["hwnd"]))
        else:
            timeout = float(args.get("timeout_s", 30.0))
            info = await windows.pick_window_by_foreground(timeout_s=timeout)
        manager.set_target(
            hwnd=info.hwnd, title=info.title, class_name=info.class_name, pid=info.process_id,
        )
        return {"retargeted": True, "window": _serialize_window(info)}

    async def _window_resize(args: dict[str, Any]) -> Any:
        hwnd = manager.require_target()
        info = await asyncio.to_thread(
            windows.resize_window, hwnd, int(args["width"]), int(args["height"]),
        )
        return _serialize_window(info)

    async def _window_move(args: dict[str, Any]) -> Any:
        hwnd = manager.require_target()
        info = await asyncio.to_thread(windows.move_window, hwnd, int(args["x"]), int(args["y"]))
        return _serialize_window(info)

    async def _window_set_bounds(args: dict[str, Any]) -> Any:
        hwnd = manager.require_target()
        info = await asyncio.to_thread(
            windows.set_window_bounds, hwnd,
            int(args["x"]), int(args["y"]), int(args["width"]), int(args["height"]),
        )
        return _serialize_window(info)

    async def _window_restore(_: dict[str, Any]) -> Any:
        hwnd = manager.require_target()
        info = await asyncio.to_thread(windows.restore_window, hwnd)
        return _serialize_window(info)

    reg.add(ToolSpec(
        name="list_windows",
        description="Enumerate top-level visible windows. Use to find the HWND of an app that just launched.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_list_windows, gated=False,
    ))
    reg.add(ToolSpec(
        name="session_pick_window",
        description=(
            "Block until the user clicks a window other than the current foreground; bind it as the "
            "session target. Use this right after session_start."
        ),
        input_schema={
            "type": "object",
            "properties": {"timeout_s": {"type": "number", "default": 30.0, "minimum": 1.0}},
            "additionalProperties": False,
        },
        handler=_session_pick, gated=False,
    ))
    reg.add(ToolSpec(
        name="session_retarget",
        description=(
            "Re-bind the session to a different window. Pass `hwnd` to target directly (use after "
            "`list_windows`), or omit to re-run the foreground-click picker. Use this when the app "
            "under test restarted and got a new HWND."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "hwnd": {"type": ["integer", "null"]},
                "timeout_s": {"type": "number", "default": 30.0, "minimum": 1.0},
            },
            "additionalProperties": False,
        },
        handler=_session_retarget, gated=False,
    ))
    reg.add(ToolSpec(
        name="window_resize",
        description=(
            "Resize the session window to (width, height). Position unchanged. Restores the window "
            "first if it was minimized. Useful for shrinking a window to make screenshot + OCR "
            "cheaper, or when you need scrolling to actually happen."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "width": {"type": "integer", "minimum": 100},
                "height": {"type": "integer", "minimum": 50},
            },
            "required": ["width", "height"],
            "additionalProperties": False,
        },
        handler=_window_resize, gated=False,
    ))
    reg.add(ToolSpec(
        name="window_move",
        description="Move the session window's top-left corner to (x, y) in screen coords. Size unchanged.",
        input_schema={
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            },
            "required": ["x", "y"],
            "additionalProperties": False,
        },
        handler=_window_move, gated=False,
    ))
    reg.add(ToolSpec(
        name="window_set_bounds",
        description="Move + resize the session window in one atomic call.",
        input_schema={
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "width": {"type": "integer", "minimum": 100},
                "height": {"type": "integer", "minimum": 50},
            },
            "required": ["x", "y", "width", "height"],
            "additionalProperties": False,
        },
        handler=_window_set_bounds, gated=False,
    ))
    reg.add(ToolSpec(
        name="window_restore",
        description="Restore the session window if it's minimized or maximized.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_window_restore, gated=False,
    ))
    reg.add(ToolSpec(
        name="screenshot",
        description="Capture the full session window. Returns image metadata + base64 PNG by default.",
        input_schema={
            "type": "object",
            "properties": {"include_base64": {"type": "boolean", "default": True}},
            "additionalProperties": False,
        },
        handler=_screenshot, gated=True,
    ))
    reg.add(ToolSpec(
        name="screenshot_region",
        description="Capture a region (window-relative coordinates) of the session window.",
        input_schema={
            "type": "object",
            "properties": {
                "x": {"type": "integer", "minimum": 0},
                "y": {"type": "integer", "minimum": 0},
                "width": {"type": "integer", "minimum": 1},
                "height": {"type": "integer", "minimum": 1},
                "include_base64": {"type": "boolean", "default": True},
            },
            "required": ["x", "y", "width", "height"],
            "additionalProperties": False,
        },
        handler=_screenshot_region, gated=True,
    ))
    reg.add(ToolSpec(
        name="ocr",
        description=(
            "Run OCR on the session window (or a region). Returns boxes with text + confidence + "
            "window-relative coords."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "x": {"type": "integer", "minimum": 0},
                "y": {"type": "integer", "minimum": 0},
                "width": {"type": "integer", "minimum": 1},
                "height": {"type": "integer", "minimum": 1},
                "min_confidence": {"type": "number", "minimum": 0, "maximum": 100, "default": 50.0},
            },
            "additionalProperties": False,
        },
        handler=_ocr, gated=True,
    ))
    reg.add(ToolSpec(
        name="wait_for_text",
        description=(
            "Poll OCR until `pattern` (regex) appears in the session window, or timeout. Returns the "
            "first matching box."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "minLength": 1},
                "timeout_ms": {"type": "integer", "minimum": 100, "default": 5000},
                "poll_ms": {"type": "integer", "minimum": 50, "default": 250},
                "case_insensitive": {"type": "boolean", "default": True},
                "min_confidence": {"type": "number", "minimum": 0, "maximum": 100, "default": 50.0},
                "x": {"type": "integer", "minimum": 0},
                "y": {"type": "integer", "minimum": 0},
                "width": {"type": "integer", "minimum": 1},
                "height": {"type": "integer", "minimum": 1},
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
        handler=_wait_for_text, gated=True,
    ))


def _opt_region(args: dict[str, Any]) -> windows.WindowRect | None:
    if all(k in args for k in ("x", "y", "width", "height")):
        return windows.WindowRect(
            x=int(args["x"]), y=int(args["y"]), width=int(args["width"]), height=int(args["height"]),
        )
    return None


def serialize_capture(r: vision.CaptureResult, *, manager: SessionManager | None = None) -> dict[str, Any]:
    if manager is not None and manager.active:
        manager.audit.last_screenshot = r.path
    return {
        "image_id": r.image_id,
        "path": r.path,
        "width": r.width,
        "height": r.height,
        "window_rect": {
            "x": r.window_rect.x, "y": r.window_rect.y,
            "width": r.window_rect.width, "height": r.window_rect.height,
        },
        "region": {
            "x": r.region.x, "y": r.region.y,
            "width": r.region.width, "height": r.region.height,
        },
        "base64_png": r.base64_png,
    }


def _serialize_window(w: windows.WindowInfo) -> dict[str, Any]:
    return {
        "hwnd": w.hwnd,
        "title": w.title,
        "class_name": w.class_name,
        "pid": w.process_id,
        "rect": {"x": w.rect.x, "y": w.rect.y, "width": w.rect.width, "height": w.rect.height},
    }
