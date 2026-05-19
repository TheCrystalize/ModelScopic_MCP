import * as vscode from "vscode";
import { Dispatcher } from "../rpc";
import { asString, ensureObject } from "./util";

interface OpenParams {
  path: string;
  preview?: boolean;
}

interface ReadParams {
  path: string;
}

interface ApplyEditParams {
  path: string;
  text: string;
}

interface SaveParams {
  path: string;
}

export function registerEditorHandlers(d: Dispatcher): void {
  d.register("editor.open", async (params) => {
    const p = ensureObject<OpenParams>(params, ["path"]);
    const uri = vscode.Uri.file(p.path);
    const doc = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(doc, { preview: p.preview ?? false });
    return { path: uri.fsPath };
  });

  d.register("editor.read", async (params) => {
    const p = ensureObject<ReadParams>(params, ["path"]);
    const uri = vscode.Uri.file(p.path);
    const doc = await vscode.workspace.openTextDocument(uri);
    return { path: uri.fsPath, text: doc.getText(), version: doc.version };
  });

  d.register("editor.applyEdit", async (params) => {
    const p = ensureObject<ApplyEditParams>(params, ["path", "text"]);
    asString(p.text, "text");
    const uri = vscode.Uri.file(p.path);
    const doc = await vscode.workspace.openTextDocument(uri);
    const edit = new vscode.WorkspaceEdit();
    const full = new vscode.Range(
      new vscode.Position(0, 0),
      doc.lineAt(doc.lineCount - 1).range.end,
    );
    edit.replace(uri, full, p.text);
    const ok = await vscode.workspace.applyEdit(edit);
    return { ok, path: uri.fsPath };
  });

  d.register("editor.save", async (params) => {
    const p = ensureObject<SaveParams>(params, ["path"]);
    const uri = vscode.Uri.file(p.path);
    const doc = vscode.workspace.textDocuments.find((d) => d.uri.fsPath === uri.fsPath);
    if (!doc) {
      throw new Error(`document not open: ${uri.fsPath}`);
    }
    const ok = await doc.save();
    return { ok, path: uri.fsPath };
  });
}
