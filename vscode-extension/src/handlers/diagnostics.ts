import * as vscode from "vscode";
import { Dispatcher } from "../rpc";

interface GetParams {
  path?: string;
}

export function registerDiagnosticsHandlers(d: Dispatcher): void {
  d.register("diagnostics.get", async (params) => {
    const p = (params ?? {}) as GetParams;
    const all = p.path
      ? [[vscode.Uri.file(p.path), vscode.languages.getDiagnostics(vscode.Uri.file(p.path))] as const]
      : vscode.languages.getDiagnostics();
    return {
      diagnostics: all.map(([uri, diags]) => ({
        path: uri.fsPath,
        items: diags.map((dx) => ({
          severity: vscode.DiagnosticSeverity[dx.severity],
          message: dx.message,
          source: dx.source,
          code: typeof dx.code === "object" ? dx.code.value : dx.code,
          range: {
            startLine: dx.range.start.line,
            startCol: dx.range.start.character,
            endLine: dx.range.end.line,
            endCol: dx.range.end.character,
          },
        })),
      })),
    };
  });
}
