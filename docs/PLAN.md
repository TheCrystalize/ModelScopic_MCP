# ModelScopic MCP — Design Plan

## Goal

A local MCP server that lets a model develop apps inside VSCode and visually iterate on the resulting app via screenshots, OCR, and synthesized input.

## Architecture

```
┌──────────────────────┐  WebSocket   ┌─────────────────────────┐
│  MCP Server (Python) │◄────────────►│ VSCode Companion Ext.   │
│                      │   localhost  │ (TypeScript)            │
│  - MCP stdio         │              │  - Editor R/W           │
│  - Session manager   │              │  - Terminal I/O         │
│  - Safety gates      │              │  - Workspace ops        │
│  - Audit logger      │              │  - Diagnostics          │
│  - OCR pipeline      │              │  - Confirmation modals  │
│  - Input injector    │              │                         │
│  - Kill-switch hook  │              │                         │
└──────────┬───────────┘              └─────────────────────────┘
           │  Win32 (screenshots, input, window handles)
           ▼
   ┌───────────────┐
   │  Target App   │
   └───────────────┘
```

## Decisions locked

- **Use case:** personal automation assistant.
- **Scope:** VSCode only for editor/terminal control; OCR for any target app being developed.
- **Stack:** Python (MCP server) + TypeScript (VSCode extension).
- **Vision:** companion extension for VSCode introspection + screenshots/OCR for the target app.
- **Control:** both VSCode commands and raw mouse/keyboard, exposed as separate tools.
- **Confirmation:** destructive actions only, surfaced via VSCode modal.
- **Feedback:** tools return structured result + post-action screenshot for input tools.
- **Window targeting:** start session → user clicks target window → server captures handle.
- **Single session at a time.**
- **Circuit breaker:** 3 consecutive tool errors → pause; user resumes or ends.
- **Max actions per session** (default 500).
- **Kill switch:** global OS hotkey `Ctrl+Alt+Esc`.
- **Audit log:** JSONL + post-action-only screenshots, one folder per session under `~/.modelscopic/sessions/<id>/`.

## Retention policy

- `session_end(keep: bool = false, reason: str = "")` — default wipe.
- `keep=true` retains the session folder; requires `reason`.
- Wipe scope: server-written artifacts only (log, screenshots, manifest). User's workspace files are never touched.
- Crash recovery: orphan folders surface on next `session_start`; `cleanup_sessions()` reviews/removes them.
- Config overrides via `modelscopic.retention.*` in extension settings.

## Tool surface (planned)

**Session:** `session_start`, `session_end`, `session_status`, `session_resume`, `session_mark_keep`, `cleanup_sessions`.

**VSCode:** `vscode_open_file`, `vscode_read_file`, `vscode_apply_edit`, `vscode_save`, `vscode_list_files`, `vscode_create_file`, `vscode_delete_file`*, `vscode_terminal_run`, `vscode_terminal_read`, `vscode_get_diagnostics`, `vscode_run_command`, `vscode_install_extension`*, `vscode_update_setting`*.

**Vision:** `list_windows`, `screenshot`, `screenshot_region`, `ocr`, `wait_for_text`, `session_pick_window`, `session_retarget`.

**Control:** `click`, `move`, `type_text`, `send_keys`, `scroll`, `drag`.

**Window mgmt:** `window_resize`, `window_move`, `window_set_bounds`, `window_restore`.

`*` = destructive, requires confirmation.

## Build order

- **M1** — VSCode plumbing: extension scaffold + WebSocket + handshake + Python MCP scaffold + session lifecycle + audit log. **DONE**
- **M2** — Vision: window enumeration + foreground-click picker + `session_retarget`, `mss` capture (full + region), Tesseract OCR with file-hash cache, `wait_for_text`, DPI awareness on startup. **DONE**
- **M3** — Control: SendInput-based mouse + keyboard (window-relative coords), post-action screenshots, global Ctrl+Alt+Esc kill switch, deny patterns for terminal commands + dangerous key chords, `doctor` self-check. **DONE**
- **M4** — Polish: terminal output capture via shellIntegration (`vscode_terminal_execute`), `cleanup_sessions` for orphaned folders, extension install + setting update tools (with VSCode modal confirmation), generic `confirm.request` RPC + `unsafe_terminal_run` / `unsafe_send_keys` escape hatches, stdlib replay viewer (`python -m modelscopic.replay`), live status bar pushed from Python lifecycle. **DONE**
