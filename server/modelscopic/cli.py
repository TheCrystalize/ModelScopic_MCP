"""Interactive REPL for poking at ModelScopic tools without an MCP client.

Run: ``python -m modelscopic.cli``

Each line is `<tool_name> [<json args>]`. Args default to `{}`. Lines starting
with `.` are meta-commands (`.help`, `.list`, `.quit`, `.status`, `.resume`).

A session auto-starts on the first gated tool call and auto-wipes on exit.
Use `.keep <reason>` if you want to retain the session folder.

Example:
    > .list
    > list_windows
    > session_pick_window {"timeout_s": 10}
    > screenshot
    > ocr
    > click {"x": 100, "y": 200}
    > .quit
"""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
import sys
from typing import Any

from .handshake import HandshakeMissing, read_handshake
from .session import (
    NoActiveSession,
    SessionManager,
    SessionPaused,
)
from .tools import build_tool_registry
from .vscode_client import VSCodeClient
from .windows import set_dpi_awareness

log = logging.getLogger("modelscopic.cli")


HELP = """\
ModelScopic interactive REPL.
  <tool> [json args]    run a tool. Args default to {}. Use single quotes
                        if your shell mangles double quotes.
  .list                 list all tools
  .help <tool>          show tool description + schema
  .status               session status
  .resume               resume a paused session
  .keep <reason>        mark active session to be kept on exit
  .quit / Ctrl+D        exit (auto-wipes session unless .keep was used)
"""


async def run() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    set_dpi_awareness()

    manager = SessionManager()
    vscode = await _try_connect_vscode()
    registry = build_tool_registry(manager=manager, vscode=vscode)

    print("ModelScopic REPL. Type .help for commands, .quit to exit.")
    print(f"  Bridge: {'connected' if vscode else 'NOT connected (vscode_* tools will error)'}")
    print(f"  Tools:  {len(registry.specs())} available -- `.list` to see them.")

    auto_started = False
    keep_marked = False
    keep_reason = ""

    try:
        loop = asyncio.get_running_loop()
        while True:
            try:
                line = await loop.run_in_executor(None, _read_line)
            except (EOFError, KeyboardInterrupt):
                print()
                break
            line = line.strip()
            if not line:
                continue

            if line.startswith("."):
                cmd, _, rest = line[1:].partition(" ")
                cmd = cmd.lower()
                if cmd in {"quit", "exit", "q"}:
                    break
                if cmd == "list":
                    _print_tool_list(registry)
                    continue
                if cmd == "help":
                    _print_tool_help(registry, rest.strip())
                    continue
                if cmd == "status":
                    _pp(manager.status())
                    continue
                if cmd == "resume":
                    try:
                        _pp(manager.resume())
                    except NoActiveSession as exc:
                        print(f"error: {exc}")
                    continue
                if cmd == "keep":
                    if not rest.strip():
                        print("error: .keep requires a reason")
                        continue
                    keep_marked = True
                    keep_reason = rest.strip()
                    print(f"  will keep session on exit. reason: {keep_reason!r}")
                    continue
                print(f"unknown command: .{cmd}. Try .help")
                continue

            # Parse `tool [args]`
            tool_name, _, raw_args = line.partition(" ")
            args = _parse_args(raw_args)
            if args is _PARSE_ERROR:
                continue
            spec = registry.get(tool_name)
            if spec is None:
                print(f"unknown tool: {tool_name!r}. `.list` to see them.")
                continue

            if spec.gated and not manager.active:
                info = manager.start()
                auto_started = True
                print(f"  [auto-started session {info['session_id']}]")

            if spec.gated:
                try:
                    manager.before_tool()
                except (NoActiveSession, SessionPaused) as exc:
                    print(f"error: {exc}")
                    continue

            err: str | None = None
            try:
                result = await spec.handler(args)
                _pp(result)
            except Exception as exc:  # noqa: BLE001
                err = f"{type(exc).__name__}: {exc}"
                print(f"error: {err}")
            finally:
                if spec.gated:
                    manager.after_tool(error=err is not None)

        # Exit: end auto-started session
        if auto_started and manager.active:
            if keep_marked:
                end_info = manager.end(keep=True, reason=keep_reason)
            else:
                end_info = manager.end(keep=False, reason="")
            print(f"  session ended -- {'kept at ' + end_info['dir'] if end_info['kept'] else 'wiped'}")
        return 0
    finally:
        if vscode is not None:
            await vscode.close()


def _read_line() -> str:
    try:
        return input("modelscopic> ")
    except EOFError:
        raise


async def _try_connect_vscode() -> VSCodeClient | None:
    try:
        handshake = read_handshake()
    except HandshakeMissing:
        return None
    client = VSCodeClient(handshake)
    try:
        await client.connect()
    except Exception as exc:  # noqa: BLE001
        log.warning("VSCode bridge connect failed: %s", exc)
        return None
    return client


_PARSE_ERROR = object()


def _parse_args(raw: str) -> Any:
    raw = raw.strip()
    if not raw:
        return {}
    # Allow either JSON or `key=value key=value` style for convenience
    if raw.startswith("{"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"error: invalid JSON: {exc}")
            return _PARSE_ERROR
    out: dict[str, Any] = {}
    try:
        tokens = shlex.split(raw)
    except ValueError as exc:
        print(f"error: shell-parse: {exc}")
        return _PARSE_ERROR
    for tok in tokens:
        if "=" not in tok:
            print(f"error: token {tok!r} is not key=value (and input doesn't start with {{)")
            return _PARSE_ERROR
        k, _, v = tok.partition("=")
        out[k] = _coerce(v)
    return out


def _coerce(v: str) -> Any:
    """Try JSON first (handles numbers, bools, null, strings, arrays, objects);
    fall back to the raw string."""
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        return v


def _pp(value: Any) -> None:
    if isinstance(value, str):
        print(value)
    else:
        try:
            print(json.dumps(value, indent=2, default=str))
        except Exception:  # noqa: BLE001
            print(repr(value))


def _print_tool_list(registry) -> None:
    rows = [(s.name, "G" if s.gated else " ", s.description.split("\n")[0]) for s in registry.specs()]
    rows.sort()
    name_w = max(len(r[0]) for r in rows) + 2
    print(f"  {'GATED'}  {'NAME'.ljust(name_w)}DESCRIPTION")
    for name, gated, desc in rows:
        print(f"   [{gated}]   {name.ljust(name_w)}{desc[:80]}")


def _print_tool_help(registry, name: str) -> None:
    if not name:
        print("usage: .help <tool>")
        return
    spec = registry.get(name)
    if spec is None:
        print(f"unknown tool: {name}")
        return
    print(f"  {spec.name}  ({'gated' if spec.gated else 'ungated'})")
    print(f"  {spec.description}")
    print("  schema:")
    print("    " + json.dumps(spec.input_schema, indent=2).replace("\n", "\n    "))


def main() -> None:
    try:
        sys.exit(asyncio.run(run()))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
