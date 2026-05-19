import * as vscode from "vscode";
import { Bridge } from "./bridge";
import { StatusBar } from "./status";

let bridge: Bridge | undefined;
let statusBar: StatusBar | undefined;

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  statusBar = new StatusBar();
  context.subscriptions.push(statusBar);

  bridge = new Bridge(statusBar);
  context.subscriptions.push(bridge);

  context.subscriptions.push(
    vscode.commands.registerCommand("modelscopic.showStatus", () => {
      const s = bridge?.snapshot();
      vscode.window.showInformationMessage(
        s
          ? `ModelScopic: ${s.state} on ${s.host}:${s.port ?? "?"} (clients: ${s.clients})`
          : "ModelScopic: not initialized",
      );
    }),
    vscode.commands.registerCommand("modelscopic.stopBridge", async () => {
      await bridge?.stop();
    }),
    vscode.commands.registerCommand("modelscopic.startBridge", async () => {
      await bridge?.start();
    }),
  );

  await bridge.start();
}

export async function deactivate(): Promise<void> {
  await bridge?.stop();
  bridge = undefined;
  statusBar?.dispose();
  statusBar = undefined;
}
