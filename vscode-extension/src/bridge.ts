import * as crypto from "crypto";
import * as vscode from "vscode";
import { WebSocket, WebSocketServer } from "ws";
import { deleteHandshake, writeHandshake } from "./handshake";
import { Dispatcher } from "./rpc";
import { StatusBar } from "./status";

export interface BridgeSnapshot {
  state: "stopped" | "starting" | "listening" | "error";
  host: string;
  port: number | null;
  clients: number;
}

export class Bridge implements vscode.Disposable {
  private wss: WebSocketServer | undefined;
  private token: string | undefined;
  private port: number | null = null;
  private clients = new Set<WebSocket>();
  private state: BridgeSnapshot["state"] = "stopped";
  private dispatcher: Dispatcher;

  constructor(private readonly statusBar: StatusBar) {
    this.dispatcher = new Dispatcher(statusBar);
  }

  snapshot(): BridgeSnapshot {
    return {
      state: this.state,
      host: this.host(),
      port: this.port,
      clients: this.clients.size,
    };
  }

  async start(): Promise<void> {
    if (this.wss) {
      return;
    }
    this.state = "starting";
    this.statusBar.set("starting");

    this.token = crypto.randomBytes(32).toString("hex");

    await new Promise<void>((resolve, reject) => {
      const server = new WebSocketServer({ host: this.host(), port: 0 });
      server.on("listening", () => {
        const addr = server.address();
        if (addr && typeof addr === "object") {
          this.port = addr.port;
        }
        this.wss = server;
        this.state = "listening";
        this.statusBar.set("listening", `${this.host()}:${this.port}`);
        resolve();
      });
      server.on("error", (err) => {
        this.state = "error";
        this.statusBar.set("error", String(err));
        reject(err);
      });
      server.on("connection", (ws, req) => this.onConnection(ws, req.headers.authorization));
    });

    await writeHandshake({
      host: this.host(),
      port: this.port!,
      token: this.token,
      pid: process.pid,
      writtenAt: new Date().toISOString(),
    });
  }

  async stop(): Promise<void> {
    for (const ws of this.clients) {
      try {
        ws.close(1001, "bridge stopping");
      } catch {
        // ignore
      }
    }
    this.clients.clear();
    if (this.wss) {
      await new Promise<void>((resolve) => this.wss!.close(() => resolve()));
      this.wss = undefined;
    }
    this.port = null;
    this.token = undefined;
    this.state = "stopped";
    this.statusBar.set("stopped");
    await deleteHandshake();
  }

  dispose(): void {
    void this.stop();
  }

  private host(): string {
    return (
      vscode.workspace.getConfiguration("modelscopic").get<string>("bridge.host") ??
      "127.0.0.1"
    );
  }

  private onConnection(ws: WebSocket, authHeader: string | undefined): void {
    if (!this.authorized(authHeader)) {
      ws.close(4401, "unauthorized");
      return;
    }
    this.clients.add(ws);

    ws.on("message", async (data) => {
      let req: unknown;
      try {
        req = JSON.parse(data.toString("utf8"));
      } catch {
        ws.send(JSON.stringify({ ok: false, error: "invalid_json" }));
        return;
      }
      const reply = await this.dispatcher.dispatch(req);
      ws.send(JSON.stringify(reply));
    });

    ws.on("close", () => {
      this.clients.delete(ws);
    });
  }

  private authorized(authHeader: string | undefined): boolean {
    if (!this.token || !authHeader) {
      return false;
    }
    const expected = `Bearer ${this.token}`;
    if (authHeader.length !== expected.length) {
      return false;
    }
    return crypto.timingSafeEqual(Buffer.from(authHeader), Buffer.from(expected));
  }
}
