"""MCP server entry point. Registers tools and runs over stdio."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .handshake import HandshakeMissing, read_handshake
from .killswitch import KillSwitch
from .session import (
    NoActiveSession,
    SessionError,
    SessionManager,
    SessionPaused,
)
from .tools import build_tool_registry
from .vscode_client import VSCodeClient
from .windows import set_dpi_awareness

log = logging.getLogger("modelscopic")


async def run_stdio() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    set_dpi_awareness()

    manager = SessionManager()
    vscode = await _connect_vscode()

    killswitch = KillSwitch()
    killswitch.start(asyncio.get_running_loop())

    server: Server = Server("modelscopic")
    registry = build_tool_registry(manager=manager, vscode=vscode)

    last_status_payload: dict[str, str] = {}

    async def _push_status() -> None:
        if vscode is None:
            return
        s = manager.status()
        if not s.get("active"):
            level, detail = "idle", ""
        elif s.get("paused"):
            level, detail = "paused", str(s.get("paused_reason", ""))
        else:
            tgt = s.get("target") or {}
            tcalls = s.get("tool_calls", 0)
            detail = f"{tgt.get('title') or 'no target'} | {tcalls} calls"
            level = "active"
        payload = {"level": level, "detail": detail}
        if payload == last_status_payload:
            return
        last_status_payload.update(payload)
        try:
            await vscode.call("status.set", payload)
        except Exception:  # noqa: BLE001 -- non-critical
            pass

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(name=spec.name, description=spec.description, inputSchema=spec.input_schema)
            for spec in registry.specs()
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
        args = arguments or {}
        spec = registry.get(name)
        if spec is None:
            return [TextContent(type="text", text=f"unknown tool: {name}")]

        gated = spec.gated  # whether this tool participates in the session breaker
        if gated:
            if killswitch.consume() and manager.active:
                manager.trip("kill switch (Ctrl+Alt+Esc)")
            try:
                manager.before_tool()
            except (NoActiveSession, SessionPaused) as exc:
                return [TextContent(type="text", text=str(exc))]

        error: str | None = None
        try:
            result = await spec.handler(args)
            text = result if isinstance(result, str) else _format(result)
            if gated and manager.active:
                shot = manager.audit.last_screenshot
                manager.audit.last_screenshot = None
                manager.audit.record(name, args, _summarize(result), screenshot=shot)
            return [TextContent(type="text", text=text)]
        except (SessionError, Exception) as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
            if gated and manager.active:
                shot = manager.audit.last_screenshot
                manager.audit.last_screenshot = None
                manager.audit.record(name, args, None, screenshot=shot, error=error)
            return [TextContent(type="text", text=error)]
        finally:
            if gated:
                manager.after_tool(error=error is not None)
            await _push_status()

    try:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        killswitch.stop()
        if vscode is not None:
            await vscode.close()


def _sync_entry() -> None:
    """Sync wrapper for the `modelscopic-mcp` script alias."""
    asyncio.run(run_stdio())


async def _connect_vscode() -> VSCodeClient | None:
    try:
        handshake = read_handshake()
    except HandshakeMissing as exc:
        log.warning("VSCode bridge unavailable: %s", exc)
        return None
    client = VSCodeClient(handshake)
    try:
        await client.connect()
    except Exception as exc:  # noqa: BLE001
        log.warning("VSCode bridge connect failed: %s", exc)
        return None
    log.info("Connected to VSCode bridge at %s:%s", handshake.host, handshake.port)
    return client


def _format(value: Any) -> str:
    import json
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:  # noqa: BLE001
        return repr(value)


def _summarize(value: Any) -> Any:
    """Trim large fields out of audit summaries (e.g. file contents)."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(v, str) and len(v) > 200:
                out[k] = f"<{len(v)} chars>"
            else:
                out[k] = v
        return out
    return value
