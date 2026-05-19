"""VSCode RPC tools. Gated by the session breaker."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..safety import check_terminal_command
from ..session import SessionManager
from ..vscode_client import VSCodeClient

if TYPE_CHECKING:
    from . import ToolRegistry


def register(reg: "ToolRegistry", *, manager: SessionManager, vscode: VSCodeClient | None) -> None:
    from . import ToolSpec

    async def _need_bridge() -> None:
        if vscode is None:
            raise RuntimeError(
                "VSCode bridge not connected — ensure the ModelScopic extension is running and "
                "restart the MCP server."
            )

    async def _open(args: dict[str, Any]) -> Any:
        await _need_bridge()
        return await vscode.call("editor.open", {"path": args["path"], "preview": args.get("preview", False)})  # type: ignore[union-attr]

    async def _read(args: dict[str, Any]) -> Any:
        await _need_bridge()
        return await vscode.call("editor.read", {"path": args["path"]})  # type: ignore[union-attr]

    async def _apply_edit(args: dict[str, Any]) -> Any:
        await _need_bridge()
        return await vscode.call("editor.applyEdit", {"path": args["path"], "text": args["text"]})  # type: ignore[union-attr]

    async def _save(args: dict[str, Any]) -> Any:
        await _need_bridge()
        return await vscode.call("editor.save", {"path": args["path"]})  # type: ignore[union-attr]

    async def _list_files(args: dict[str, Any]) -> Any:
        await _need_bridge()
        return await vscode.call("workspace.list", {  # type: ignore[union-attr]
            "glob": args.get("glob", "**/*"),
            "maxResults": args.get("maxResults", 1000),
        })

    async def _create_file(args: dict[str, Any]) -> Any:
        await _need_bridge()
        return await vscode.call("workspace.create", {  # type: ignore[union-attr]
            "path": args["path"],
            "content": args.get("content", ""),
            "overwrite": args.get("overwrite", False),
        })

    async def _delete_file(args: dict[str, Any]) -> Any:
        await _need_bridge()
        return await vscode.call("workspace.delete", {  # type: ignore[union-attr]
            "path": args["path"],
            "recursive": args.get("recursive", False),
        })

    async def _terminal_create(args: dict[str, Any]) -> Any:
        await _need_bridge()
        return await vscode.call("terminal.create", {  # type: ignore[union-attr]
            "name": args.get("name"),
            "cwd": args.get("cwd"),
        })

    async def _terminal_send(args: dict[str, Any]) -> Any:
        await _need_bridge()
        check_terminal_command(args["text"])
        return await vscode.call("terminal.send", {  # type: ignore[union-attr]
            "terminalId": args["terminalId"],
            "text": args["text"],
            "addNewline": args.get("addNewline", True),
        })

    async def _terminal_execute(args: dict[str, Any]) -> Any:
        await _need_bridge()
        check_terminal_command(args["commandLine"])
        return await vscode.call("terminal.execute", {  # type: ignore[union-attr]
            "terminalId": args["terminalId"],
            "commandLine": args["commandLine"],
            "timeoutMs": args.get("timeoutMs", 60000),
            "maxBytes": args.get("maxBytes", 1_000_000),
        })

    async def _diagnostics(args: dict[str, Any]) -> Any:
        await _need_bridge()
        return await vscode.call("diagnostics.get", {"path": args.get("path")})  # type: ignore[union-attr]

    async def _install_extension(args: dict[str, Any]) -> Any:
        await _need_bridge()
        return await vscode.call("extensions.install", {"extensionId": args["extensionId"]})  # type: ignore[union-attr]

    async def _update_setting(args: dict[str, Any]) -> Any:
        await _need_bridge()
        return await vscode.call("settings.update", {  # type: ignore[union-attr]
            "key": args["key"],
            "value": args["value"],
            "target": args.get("target", "user"),
        })

    def path_obj(extra: dict[str, Any] | None = None) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {"path": {"type": "string", "minLength": 1}},
            "required": ["path"],
            "additionalProperties": True,
        }
        if extra:
            schema["properties"].update(extra)
        return schema

    reg.add(ToolSpec(
        name="vscode_open_file",
        description="Open a file in the VSCode editor.",
        input_schema=path_obj({"preview": {"type": "boolean", "default": False}}),
        handler=_open, gated=True,
    ))
    reg.add(ToolSpec(
        name="vscode_read_file",
        description="Read a file's contents through VSCode (returns text + document version).",
        input_schema=path_obj(),
        handler=_read, gated=True,
    ))
    reg.add(ToolSpec(
        name="vscode_apply_edit",
        description="Replace the entire contents of a file via VSCode WorkspaceEdit.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "text": {"type": "string"},
            },
            "required": ["path", "text"],
            "additionalProperties": False,
        },
        handler=_apply_edit, gated=True,
    ))
    reg.add(ToolSpec(
        name="vscode_save",
        description="Save an open document.",
        input_schema=path_obj(),
        handler=_save, gated=True,
    ))
    reg.add(ToolSpec(
        name="vscode_list_files",
        description="List workspace files matching a glob (excludes node_modules).",
        input_schema={
            "type": "object",
            "properties": {
                "glob": {"type": "string", "default": "**/*"},
                "maxResults": {"type": "integer", "minimum": 1, "default": 1000},
            },
            "additionalProperties": False,
        },
        handler=_list_files, gated=True,
    ))
    reg.add(ToolSpec(
        name="vscode_create_file",
        description="Create a new file. Fails if it exists unless overwrite=true.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "content": {"type": "string", "default": ""},
                "overwrite": {"type": "boolean", "default": False},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        handler=_create_file, gated=True,
    ))
    reg.add(ToolSpec(
        name="vscode_delete_file",
        description="Delete a file or folder. Sends to the OS trash. User must confirm in VSCode.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "recursive": {"type": "boolean", "default": False},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        handler=_delete_file, gated=True,
    ))
    reg.add(ToolSpec(
        name="vscode_terminal_create",
        description="Create a new integrated terminal. Returns a terminalId for subsequent sends.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "cwd": {"type": "string"},
            },
            "additionalProperties": False,
        },
        handler=_terminal_create, gated=True,
    ))
    reg.add(ToolSpec(
        name="vscode_terminal_send",
        description=(
            "Send raw text to a terminal (write-only; output is not captured). Use "
            "`vscode_terminal_execute` instead when you need the output."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "terminalId": {"type": "string", "minLength": 1},
                "text": {"type": "string"},
                "addNewline": {"type": "boolean", "default": True},
            },
            "required": ["terminalId", "text"],
            "additionalProperties": False,
        },
        handler=_terminal_send, gated=True,
    ))
    reg.add(ToolSpec(
        name="vscode_terminal_execute",
        description=(
            "Run a command in a terminal and return its stdout/stderr + exit code. Requires "
            "VSCode shellIntegration to be active for that terminal (bash/zsh/pwsh/cmd on "
            "recent shells). Output is VT-stripped and capped at maxBytes."
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
        handler=_terminal_execute, gated=True,
    ))
    reg.add(ToolSpec(
        name="vscode_get_diagnostics",
        description="Get diagnostics (errors/warnings) for a file, or all files if path omitted.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "additionalProperties": False,
        },
        handler=_diagnostics, gated=True,
    ))
    reg.add(ToolSpec(
        name="vscode_install_extension",
        description="Install a VSCode extension by id (e.g. `ms-python.python`). User confirms in a modal.",
        input_schema={
            "type": "object",
            "properties": {"extensionId": {"type": "string", "minLength": 1}},
            "required": ["extensionId"],
            "additionalProperties": False,
        },
        handler=_install_extension, gated=True,
    ))
    reg.add(ToolSpec(
        name="vscode_update_setting",
        description=(
            "Update a VSCode setting. `key` is the dotted path (e.g. 'editor.formatOnSave'). "
            "`target`: 'user' (default) or 'workspace'. User confirms in a modal showing the new value."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "minLength": 1},
                "value": {},
                "target": {"type": "string", "enum": ["user", "workspace"], "default": "user"},
            },
            "required": ["key", "value"],
            "additionalProperties": False,
        },
        handler=_update_setting, gated=True,
    ))
