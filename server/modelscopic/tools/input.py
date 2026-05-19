"""Input injection tools. Every action returns a post-action screenshot."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from .. import input as inp, vision
from ..safety import check_key_chord
from ..session import SessionManager

if TYPE_CHECKING:
    from . import ToolRegistry


def register(reg: "ToolRegistry", *, manager: SessionManager) -> None:
    from . import ToolSpec
    from .vision import serialize_capture

    async def _post_screenshot() -> dict[str, Any]:
        hwnd = manager.require_target()
        cap = await asyncio.to_thread(
            vision.capture_window, hwnd, audit=manager.audit, region=None, include_base64=True,
        )
        return serialize_capture(cap, manager=manager)

    async def _move(args: dict[str, Any]) -> Any:
        hwnd = manager.require_target()
        pt = await asyncio.to_thread(inp.move_mouse, hwnd, int(args["x"]), int(args["y"]))
        return {"screen": {"x": pt.x, "y": pt.y}, "after": await _post_screenshot()}

    async def _click(args: dict[str, Any]) -> Any:
        hwnd = manager.require_target()
        pt = await asyncio.to_thread(
            inp.click_mouse, hwnd,
            int(args["x"]), int(args["y"]),
            button=args.get("button", "left"),
            clicks=int(args.get("clicks", 1)),
        )
        return {"screen": {"x": pt.x, "y": pt.y}, "after": await _post_screenshot()}

    async def _scroll(args: dict[str, Any]) -> Any:
        hwnd = manager.require_target()
        pt = await asyncio.to_thread(
            inp.scroll, hwnd, int(args["x"]), int(args["y"]),
            dy=int(args.get("dy", 0)), dx=int(args.get("dx", 0)),
        )
        return {"screen": {"x": pt.x, "y": pt.y}, "after": await _post_screenshot()}

    async def _drag(args: dict[str, Any]) -> Any:
        hwnd = manager.require_target()
        p1, p2 = await asyncio.to_thread(
            inp.drag, hwnd,
            int(args["x1"]), int(args["y1"]), int(args["x2"]), int(args["y2"]),
            button=args.get("button", "left"),
        )
        return {
            "from": {"x": p1.x, "y": p1.y},
            "to": {"x": p2.x, "y": p2.y},
            "after": await _post_screenshot(),
        }

    async def _type_text(args: dict[str, Any]) -> Any:
        # Type-text doesn't require the cursor to be in the session window —
        # focus is the caller's responsibility (usually they click first).
        manager.require_target()  # still must have a session
        n = await asyncio.to_thread(inp.type_text, str(args["text"]),
                                    per_char_delay_ms=int(args.get("per_char_delay_ms", 60)))
        return {"chars_sent": n, "after": await _post_screenshot()}

    async def _send_keys(args: dict[str, Any]) -> Any:
        manager.require_target()
        spec = str(args["keys"])
        check_key_chord(spec)
        await asyncio.to_thread(inp.send_chord, spec)
        return {"keys": spec, "after": await _post_screenshot()}

    rect_args: dict[str, Any] = {
        "x": {"type": "integer", "minimum": 0},
        "y": {"type": "integer", "minimum": 0},
    }

    reg.add(ToolSpec(
        name="move",
        description="Move the mouse to (x, y) in window-relative coords.",
        input_schema={
            "type": "object",
            "properties": rect_args,
            "required": ["x", "y"],
            "additionalProperties": False,
        },
        handler=_move, gated=True,
    ))
    reg.add(ToolSpec(
        name="click",
        description=(
            "Click at (x, y) in window-relative coords. Returns a post-action screenshot of the "
            "session window. button: left|right|middle. clicks: 1 or 2."
        ),
        input_schema={
            "type": "object",
            "properties": {
                **rect_args,
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "clicks": {"type": "integer", "minimum": 1, "maximum": 3, "default": 1},
            },
            "required": ["x", "y"],
            "additionalProperties": False,
        },
        handler=_click, gated=True,
    ))
    reg.add(ToolSpec(
        name="scroll",
        description="Scroll at (x, y). dy: vertical notches (positive = up). dx: horizontal (positive = right).",
        input_schema={
            "type": "object",
            "properties": {
                **rect_args,
                "dy": {"type": "integer", "default": 0},
                "dx": {"type": "integer", "default": 0},
            },
            "required": ["x", "y"],
            "additionalProperties": False,
        },
        handler=_scroll, gated=True,
    ))
    reg.add(ToolSpec(
        name="drag",
        description="Drag from (x1, y1) to (x2, y2) with the specified mouse button held.",
        input_schema={
            "type": "object",
            "properties": {
                "x1": {"type": "integer", "minimum": 0},
                "y1": {"type": "integer", "minimum": 0},
                "x2": {"type": "integer", "minimum": 0},
                "y2": {"type": "integer", "minimum": 0},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
            },
            "required": ["x1", "y1", "x2", "y2"],
            "additionalProperties": False,
        },
        handler=_drag, gated=True,
    ))
    reg.add(ToolSpec(
        name="type_text",
        description=(
            "Type Unicode text into whatever has keyboard focus. Call `click` first to focus the "
            "session window if needed."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "per_char_delay_ms": {"type": "integer", "minimum": 0, "default": 60},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        handler=_type_text, gated=True,
    ))
    reg.add(ToolSpec(
        name="send_keys",
        description=(
            "Press a key chord like 'ctrl+s' or 'shift+tab'. Window-closing chords (alt+f4, ctrl+q, "
            "etc.) are rejected — those would end the iteration loop unexpectedly."
        ),
        input_schema={
            "type": "object",
            "properties": {"keys": {"type": "string", "minLength": 1}},
            "required": ["keys"],
            "additionalProperties": False,
        },
        handler=_send_keys, gated=True,
    ))
