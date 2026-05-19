"""Escape-hatch tools for actions blocked by deny patterns.

These tools always go through a VSCode modal confirmation. The MODEL cannot
bypass that prompt -- only the user clicking "Proceed" lets the action through.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from .. import input as inp, vision
from ..session import SessionManager
from ..vscode_client import VSCodeClient

if TYPE_CHECKING:
    from . import ToolRegistry


def register(reg: "ToolRegistry", *, manager: SessionManager, vscode: VSCodeClient | None) -> None:
    from . import ToolSpec
    from .vision import serialize_capture

    async def _confirm(title: str, detail: str, proceed_label: str = "Proceed") -> bool:
        if vscode is None:
            raise RuntimeError("VSCode bridge required for unsafe_* tools (need confirmation UI)")
        reply = await vscode.call("confirm.request", {
            "title": title, "detail": detail, "proceedLabel": proceed_label,
        })
        return bool(reply.get("confirmed", False))

    async def _unsafe_terminal_run(args: dict[str, Any]) -> Any:
        if vscode is None:
            raise RuntimeError("VSCode bridge not connected")
        cmd = args["commandLine"]
        ok = await _confirm(
            "Run a DENIED terminal command?",
            f"Terminal: {args['terminalId']}\n\n{cmd}",
            proceed_label="Run anyway",
        )
        if not ok:
            raise RuntimeError("user declined unsafe terminal command")
        return await vscode.call("terminal.execute", {
            "terminalId": args["terminalId"],
            "commandLine": cmd,
            "timeoutMs": args.get("timeoutMs", 60000),
            "maxBytes": args.get("maxBytes", 1_000_000),
        })

    async def _unsafe_send_keys(args: dict[str, Any]) -> Any:
        manager.require_target()
        spec = str(args["keys"])
        ok = await _confirm(
            "Send a DANGEROUS key chord?",
            f"Chord: {spec}\n\nThis bypasses the dangerous-chord deny list (e.g. alt+f4, ctrl+q).",
            proceed_label="Send anyway",
        )
        if not ok:
            raise RuntimeError("user declined unsafe key chord")
        await asyncio.to_thread(inp.send_chord, spec)
        hwnd = manager.require_target()
        cap = await asyncio.to_thread(
            vision.capture_window, hwnd, audit=manager.audit, region=None, include_base64=True,
        )
        return {"keys": spec, "after": serialize_capture(cap, manager=manager)}

    reg.add(ToolSpec(
        name="unsafe_terminal_run",
        description=(
            "Run a terminal command that would normally be denied (rm -rf, git push --force, etc.). "
            "The user must confirm in a VSCode modal before the command runs."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "terminalId": {"type": "string", "minLength": 1},
                "commandLine": {"type": "string", "minLength": 1},
                "timeoutMs": {"type": "integer", "minimum": 1000, "default": 60000},
                "maxBytes": {"type": "integer", "minimum": 1024, "default": 1_000_000},
            },
            "required": ["terminalId", "commandLine"],
            "additionalProperties": False,
        },
        handler=_unsafe_terminal_run, gated=True,
    ))
    reg.add(ToolSpec(
        name="unsafe_send_keys",
        description=(
            "Send a key chord on the dangerous-chord list (alt+f4, ctrl+q, win+q, ...). "
            "User must confirm in a VSCode modal."
        ),
        input_schema={
            "type": "object",
            "properties": {"keys": {"type": "string", "minLength": 1}},
            "required": ["keys"],
            "additionalProperties": False,
        },
        handler=_unsafe_send_keys, gated=True,
    ))
