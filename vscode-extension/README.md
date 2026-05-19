# ModelScopic VSCode Companion Extension

The bridge between the ModelScopic MCP server and VSCode. Exposes editor, terminal, workspace, diagnostics, and admin operations over a local WebSocket on `127.0.0.1`.

The MCP server talks to this extension via a handshake file written to `~/.modelscopic/handshake.json` (containing host, port, and a per-session bearer token). Without this extension running, ModelScopic's `vscode_*` tools error; vision/input/window tools still work.

See [the main repo](https://github.com/TheCrystalize/ModelScopic_MCP) for the full project.

## Install

```cmd
code --install-extension modelscopic-vscode-0.0.1.vsix
```

After install, look bottom-right for `[plug] ModelScopic`. Hover for bridge status.

## Build from source

```cmd
npm install
npm run compile
npm run package
```

Output: `modelscopic-vscode-<version>.vsix`.
