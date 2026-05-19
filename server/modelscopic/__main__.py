"""Dual-mode entry point for ModelScopic.

`python -m modelscopic` (or the installed `modelscopic` script) auto-detects
whether stdin is a TTY:

  TTY  -> drop into the interactive REPL (human user).
  pipe -> run the MCP stdio server (MCP client/parent process).

Explicit override flags:
  --mcp     force MCP stdio mode
  --repl    force interactive REPL mode
  --doctor  run env self-check and exit
  --replay  launch the replay-log viewer (HTTP server)
  --help    show this banner and exit
"""

from __future__ import annotations

import asyncio
import sys

USAGE = """\
usage: modelscopic [--mcp | --repl | --doctor | --replay] [args...]

Auto-detects mode from stdin:
  - TTY  -> REPL
  - pipe -> MCP stdio server

Flags:
  --mcp      Force MCP stdio mode (for MCP-client invocations)
  --repl     Force interactive REPL
  --doctor   Run environment self-check and exit
  --replay   Start the session replay viewer (web UI)
  --help     This message
"""


def _is_interactive() -> bool:
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def main() -> None:
    args = sys.argv[1:]

    if args and args[0] in {"-h", "--help"}:
        print(USAGE)
        return

    if args and args[0] == "--doctor":
        from modelscopic.doctor import main as doctor_main  # noqa: PLC0415
        sys.exit(doctor_main())

    if args and args[0] == "--replay":
        from modelscopic.replay import main as replay_main  # noqa: PLC0415
        sys.argv = ["modelscopic-replay"] + args[1:]
        sys.exit(replay_main())

    force_mcp = "--mcp" in args
    force_repl = "--repl" in args

    if force_mcp and force_repl:
        print("error: --mcp and --repl are mutually exclusive", file=sys.stderr)
        sys.exit(2)

    if force_repl or (not force_mcp and _is_interactive()):
        from modelscopic.cli import run as cli_run  # noqa: PLC0415
        sys.exit(asyncio.run(cli_run()))

    # default to MCP stdio
    from modelscopic.server import run_stdio  # noqa: PLC0415
    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
