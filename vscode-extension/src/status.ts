import * as vscode from "vscode";

export type BridgeState = "stopped" | "starting" | "listening" | "error";
export type SessionLevel = "idle" | "active" | "paused" | "killed";

export class StatusBar implements vscode.Disposable {
  private readonly item: vscode.StatusBarItem;
  private bridge: BridgeState = "stopped";
  private bridgeDetail: string | undefined;
  private session: SessionLevel = "idle";
  private sessionDetail: string | undefined;

  constructor() {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    this.item.command = "modelscopic.showStatus";
    this.render();
    this.item.show();
  }

  set(state: BridgeState, detail?: string): void {
    this.bridge = state;
    this.bridgeDetail = detail;
    this.render();
  }

  setSession(level: SessionLevel, detail?: string): void {
    this.session = level;
    this.sessionDetail = detail;
    this.render();
  }

  private render(): void {
    const icon =
      this.session === "killed"
        ? "$(stop-circle)"
        : this.session === "paused"
        ? "$(debug-pause)"
        : this.session === "active"
        ? "$(record)"
        : "$(plug)";
    this.item.text = `${icon} ModelScopic`;
    const lines = [
      `Bridge: ${this.bridge}${this.bridgeDetail ? ` -- ${this.bridgeDetail}` : ""}`,
      `Session: ${this.session}${this.sessionDetail ? ` -- ${this.sessionDetail}` : ""}`,
    ];
    this.item.tooltip = lines.join("\n");
    const error =
      this.bridge === "error" || this.session === "killed" || this.session === "paused";
    this.item.backgroundColor = error
      ? new vscode.ThemeColor("statusBarItem.warningBackground")
      : undefined;
  }

  dispose(): void {
    this.item.dispose();
  }
}
