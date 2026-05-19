# ModelScopic Quickstart

End-to-end setup for using ModelScopic as a personal MCP server: edit code in VSCode, run the resulting app, watch it via screenshots + OCR, click and type back into it.

## Prerequisites

- **Windows 10/11** (Win32 APIs)
- **Python 3.11+**
- **Node.js 18+** (only for compiling the VSCode extension)
- **VSCode** (any recent version)
- **Tesseract OCR** binary -- [installer from UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki). Add to PATH or set `TESSERACT_CMD` to its full path.

## One-time setup

### 1. Install Python deps

```cmd
cd c:\dev\ModelScopic_MCP\server
pip install -e .[dev]
```

### 2. Build the VSCode extension

```cmd
cd c:\dev\ModelScopic_MCP\vscode-extension
npm install
npm run compile
```

### 3. Verify everything

```cmd
cd c:\dev\ModelScopic_MCP\server
python -m modelscopic.doctor
```

You should see 11/12 pass. The `vscode bridge handshake` failure is expected until you launch the extension below.

## Running

### Launch the VSCode bridge

1. Open [vscode-extension/](../vscode-extension/) in VSCode (File -> Open Folder).
2. Press **F5**. A second VSCode window opens with `[Extension Development Host]` in the title bar.
3. In that second window, look bottom-right -- you should see `[plug] ModelScopic`. Hover for `Bridge: listening -- 127.0.0.1:<port>`.

Re-run the doctor: should be 12/12.

### Run the unified entry

`python -m modelscopic` auto-detects how it was launched:

- **Pipe / MCP client** -> runs the MCP stdio server (JSON-RPC over stdin/stdout)
- **Terminal (TTY)** -> drops you into the interactive REPL

So the same command works for both an MCP client config and a human at a prompt.

**As a human:**

```cmd
python -m modelscopic
```

You get the REPL:

```
modelscopic> .list
modelscopic> list_windows
modelscopic> screenshot
modelscopic> click x=400 y=300
modelscopic> .help screenshot
modelscopic> .quit
```

A session auto-starts on the first gated call and auto-wipes on exit (use
`.keep <reason>` to retain it instead). Type `.list` to see all tools or
`.help <tool>` for one's schema.

**As an MCP client config** (Claude Desktop is `%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "modelscopic": {
      "command": "python",
      "args": ["-m", "modelscopic"],
      "cwd": "c:\\dev\\ModelScopic_MCP\\server"
    }
  }
}
```

Restart the client. The model has access to all 38 tools.

**Flag overrides** (for when you need to force a mode):

- `--mcp` -- force MCP stdio mode even when stdin is a TTY
- `--repl` -- force REPL even when stdin is piped
- `--doctor` -- run the environment self-check and exit
- `--replay` -- start the session replay viewer (web UI)
- `--help` -- show the banner

## The iteration loop

The intended workflow:

1. `session_start` -- new session folder under `~/.modelscopic/sessions/<id>/`.
2. `vscode_create_file` / `vscode_apply_edit` -- write code.
3. `vscode_terminal_create` then `vscode_terminal_execute` (e.g. `python my_app.py`).
4. `list_windows` -- find the app you just launched. Optionally `window_resize` to shrink it for cheaper OCR.
5. `session_retarget(hwnd=...)` -- lock onto it.
6. `screenshot` / `ocr` / `wait_for_text` -- see what the app shows.
7. `click` / `type_text` / `send_keys` / `scroll` -- interact. Every input tool returns a post-action screenshot.
8. If the app crashed and was relaunched, `list_windows` + `session_retarget` again.
9. `session_end(keep=true, reason="...")` if you want to inspect the run later via `python -m modelscopic.replay`, or `session_end()` to wipe.

## Tools available

**Session lifecycle (ungated):** `session_start`, `session_end`, `session_status`, `session_resume`, `session_mark_keep`, `session_pick_window`, `session_retarget`, `cleanup_sessions`, `list_windows`, `window_resize`, `window_move`, `window_set_bounds`, `window_restore`.

**VSCode (gated):** `vscode_open_file`, `vscode_read_file`, `vscode_apply_edit`, `vscode_save`, `vscode_list_files`, `vscode_create_file`, `vscode_delete_file`*, `vscode_terminal_create`, `vscode_terminal_send`, `vscode_terminal_execute`, `vscode_get_diagnostics`, `vscode_install_extension`*, `vscode_update_setting`*.

**Vision (gated):** `screenshot`, `screenshot_region`, `ocr`, `wait_for_text`.

**Input (gated):** `click`, `move`, `type_text`, `send_keys`, `scroll`, `drag`.

**Escape hatches:** `unsafe_terminal_run`, `unsafe_send_keys` -- bypass deny patterns; user must click "Proceed" in a VSCode modal.

`*` = destructive, prompts before acting.

## Safety

- **Kill switch:** press **Ctrl+Alt+Esc** any time to pause the active session. The next gated tool returns a paused error; resume with `session_resume`.
- **Circuit breaker:** 3 consecutive tool errors auto-pause the session.
- **Max actions:** default 500 per session; configurable in `Limits()`.
- **Deny patterns:** terminal commands matching `rm -rf`, `git push --force`, `format C:`, etc. are blocked. Dangerous key chords (`alt+f4`, `ctrl+q`) too. Use the `unsafe_*` variants if you really mean it.
- **Retention:** sessions wipe on `session_end` unless `keep=true` with a reason.

## Replay viewer

```cmd
python -m modelscopic.replay
```

Opens a browser tab listing kept sessions; click one to step through tool calls with screenshots.

## Known good values

- **Typing delay:** `type_text(per_char_delay_ms=60)` is the default. Faster delays (15-30ms) cause autorepeat and dropped characters on most Win11 systems. The model can override per-call when targeting modern Electron/web apps that handle faster input.
- **OCR confidence:** filter at `min_confidence=50` by default; bump to 70+ for high-stakes decisions, drop to 30 for "is there *anything* there?" probes.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Doctor: bridge handshake missing | Extension Development Host not running | Open `vscode-extension/` in VSCode, F5 |
| `tesseract is not installed` | Binary not on PATH | `setx TESSERACT_CMD "C:\Program Files\Tesseract-OCR\tesseract.exe"`, reopen terminal |
| Typed text drops chars / autorepeats | `per_char_delay_ms` too low for this app | Bump to 60+ |
| `terminal.execute`: shellIntegration error | Shell doesn't have VSCode shell integration active | Wait a moment after `terminal.create`; use bash/pwsh/cmd-on-Win11 |
| Window picker grabs a ghost HWND | Old picker bug | Fixed in current version (filters minimized/cloaked/offscreen); update if behavior recurs |
| Scroll seems not to work | Modern app dispatches wheel to deep child | Fixed in current version (`WindowFromPoint`); inspect screenshots before/after to confirm |

## Building a standalone .exe (optional)

If you'd rather not require Python on the target machine, you can bundle everything into a single ~42 MB `.exe`:

```cmd
cd c:\dev\ModelScopic_MCP\server
pip install -e .[build]
pyinstaller modelscopic.spec --clean --noconfirm
```

Output: `dist\modelscopic.exe`. It exposes the same dual-mode behavior as `python -m modelscopic` -- pipe stdin and it runs as the MCP server, run it from a terminal and you get the REPL.

The Tesseract OCR binary is still a separate system install -- bundling it would push the package past 100 MB and the user can install it once and forget it.

MCP client config for the exe:

```json
{
  "mcpServers": {
    "modelscopic": {
      "command": "C:\\path\\to\\dist\\modelscopic.exe",
      "args": []
    }
  }
}
```

## File layout

```
ModelScopic_MCP/
├── README.md
├── docs/
│   ├── PLAN.md
│   └── QUICKSTART.md     <- this file
├── vscode-extension/     <- TypeScript companion extension
│   ├── package.json
│   └── src/
└── server/               <- Python MCP server
    ├── pyproject.toml
    ├── modelscopic/      <- 11 modules, all <500 lines
    └── tests/            <- 54 unit tests + smoke + diagnostics
```
