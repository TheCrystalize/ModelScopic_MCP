import * as vscode from "vscode";
import { Dispatcher } from "../rpc";
import { ensureObject } from "./util";

interface InstallParams {
  extensionId: string;
}

interface SettingParams {
  key: string;
  value: unknown;
  target?: "user" | "workspace";
}

export function registerAdminHandlers(d: Dispatcher): void {
  d.register("extensions.install", async (params) => {
    const p = ensureObject<InstallParams>(params, ["extensionId"]);
    const choice = await vscode.window.showWarningMessage(
      `ModelScopic wants to install extension: ${p.extensionId}`,
      { modal: true },
      "Install",
      "Cancel",
    );
    if (choice !== "Install") {
      throw new Error("user declined extension install");
    }
    await vscode.commands.executeCommand("workbench.extensions.installExtension", p.extensionId);
    return { installed: p.extensionId };
  });

  d.register("settings.update", async (params) => {
    const p = ensureObject<SettingParams>(params, ["key", "value"]);
    const target =
      p.target === "workspace"
        ? vscode.ConfigurationTarget.Workspace
        : vscode.ConfigurationTarget.Global;
    const choice = await vscode.window.showWarningMessage(
      `ModelScopic wants to update setting "${p.key}" (${p.target ?? "user"}) to:\n` +
        JSON.stringify(p.value),
      { modal: true },
      "Update",
      "Cancel",
    );
    if (choice !== "Update") {
      throw new Error("user declined setting update");
    }
    // Use the root namespace section so dotted keys are supported.
    const [section, ...rest] = p.key.split(".");
    const cfg = vscode.workspace.getConfiguration(section);
    await cfg.update(rest.join("."), p.value, target);
    return { updated: p.key };
  });
}
