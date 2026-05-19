# ModelScopic MCP

A local MCP server that lets a model develop apps inside VSCode and visually iterate on the resulting app via screenshots, OCR, and synthesized input on Windows.

## What it does

The model can:
- Read/write files in VSCode, run commands in the integrated terminal and capture output, query diagnostics.
- Launch the app it just built, locate its window, take screenshots, run OCR.
- Click, type, scroll, drag, send key chords -- with every input action returning a fresh screenshot.
- Resize/move the target window to make capture cheaper.
- Survive the target app restarting (`session_retarget`).

All of it gated by a session lifecycle with a circuit breaker, a global Ctrl+Alt+Esc kill switch, deny patterns for destructive commands, and audit logs that wipe by default.

## Quick start

See [docs/QUICKSTART.md](docs/QUICKSTART.md) for the full setup walkthrough.

```cmd
cd server && pip install -e .[dev]
cd ..\vscode-extension && npm install && npm run compile
cd ..\server && python -m modelscopic.doctor
```

Then open [vscode-extension/](vscode-extension/) in VSCode and press F5.

## Layout

- [server/](server/) -- Python MCP server (11 modules, 54 unit tests)
- [vscode-extension/](vscode-extension/) -- TypeScript companion extension (WebSocket bridge)
- [docs/](docs/) -- design plan + quickstart

## Status

38 MCP tools across session lifecycle, VSCode control, vision, input injection, window management, and escape-hatch variants. Also includes an interactive REPL (`python -m modelscopic.cli`) for manually poking tools without an MCP client. Verified end-to-end against Notepad on Windows 11. See [docs/PLAN.md](docs/PLAN.md) for the full design + milestone history.
