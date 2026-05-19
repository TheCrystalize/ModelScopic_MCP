import * as vscode from "vscode";
import { Dispatcher } from "../rpc";
import { ensureObject } from "./util";

interface ConfirmParams {
  title: string;
  detail: string;
  proceedLabel?: string;
}

export function registerConfirmHandlers(d: Dispatcher): void {
  d.register("confirm.request", async (params) => {
    const p = ensureObject<ConfirmParams>(params, ["title", "detail"]);
    const proceed = p.proceedLabel ?? "Proceed";
    const choice = await vscode.window.showWarningMessage(
      `${p.title}\n\n${p.detail}`,
      { modal: true },
      proceed,
      "Cancel",
    );
    return { confirmed: choice === proceed };
  });
}
