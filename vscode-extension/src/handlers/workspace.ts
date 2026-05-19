import * as vscode from "vscode";
import { Dispatcher } from "../rpc";
import { ensureObject } from "./util";

interface ListParams {
  glob?: string;
  maxResults?: number;
}

interface CreateParams {
  path: string;
  content?: string;
  overwrite?: boolean;
}

interface DeleteParams {
  path: string;
  recursive?: boolean;
}

export function registerWorkspaceHandlers(d: Dispatcher): void {
  d.register("workspace.list", async (params) => {
    const p = (params ?? {}) as ListParams;
    const glob = p.glob ?? "**/*";
    const files = await vscode.workspace.findFiles(
      glob,
      "**/node_modules/**",
      p.maxResults ?? 1000,
    );
    return { files: files.map((u) => u.fsPath) };
  });

  d.register("workspace.create", async (params) => {
    const p = ensureObject<CreateParams>(params, ["path"]);
    const uri = vscode.Uri.file(p.path);
    if (!p.overwrite) {
      try {
        await vscode.workspace.fs.stat(uri);
        throw new Error(`file exists: ${uri.fsPath}`);
      } catch (err) {
        if (err instanceof Error && err.message.startsWith("file exists")) {
          throw err;
        }
        // not found → proceed
      }
    }
    const data = Buffer.from(p.content ?? "", "utf8");
    await vscode.workspace.fs.writeFile(uri, data);
    return { path: uri.fsPath };
  });

  d.register("workspace.delete", async (params) => {
    const p = ensureObject<DeleteParams>(params, ["path"]);
    const uri = vscode.Uri.file(p.path);
    const confirm = await vscode.window.showWarningMessage(
      `ModelScopic wants to delete: ${uri.fsPath}`,
      { modal: true },
      "Delete",
      "Cancel",
    );
    if (confirm !== "Delete") {
      throw new Error("user declined delete");
    }
    await vscode.workspace.fs.delete(uri, { recursive: p.recursive ?? false, useTrash: true });
    return { path: uri.fsPath };
  });
}
