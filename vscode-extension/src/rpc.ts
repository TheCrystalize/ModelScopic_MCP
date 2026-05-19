import { registerAdminHandlers } from "./handlers/admin";
import { registerConfirmHandlers } from "./handlers/confirm";
import { registerDiagnosticsHandlers } from "./handlers/diagnostics";
import { registerEditorHandlers } from "./handlers/editor";
import { registerStatusHandlers } from "./handlers/status";
import { registerTerminalHandlers } from "./handlers/terminal";
import { registerWorkspaceHandlers } from "./handlers/workspace";
import type { StatusBar } from "./status";

export type Handler = (params: unknown) => Promise<unknown>;

export interface RpcRequest {
  id: string | number;
  method: string;
  params?: unknown;
}

export interface RpcReply {
  id: string | number | null;
  ok: boolean;
  result?: unknown;
  error?: { code: string; message: string };
}

export class Dispatcher {
  private handlers = new Map<string, Handler>();

  constructor(statusBar: StatusBar) {
    registerEditorHandlers(this);
    registerTerminalHandlers(this);
    registerWorkspaceHandlers(this);
    registerDiagnosticsHandlers(this);
    registerAdminHandlers(this);
    registerConfirmHandlers(this);
    registerStatusHandlers(this, statusBar);
    this.register("ping", async () => ({ pong: true }));
  }

  register(method: string, handler: Handler): void {
    this.handlers.set(method, handler);
  }

  async dispatch(raw: unknown): Promise<RpcReply> {
    if (!isRequest(raw)) {
      return { id: null, ok: false, error: { code: "invalid_request", message: "malformed request" } };
    }
    const handler = this.handlers.get(raw.method);
    if (!handler) {
      return {
        id: raw.id,
        ok: false,
        error: { code: "unknown_method", message: `no handler for ${raw.method}` },
      };
    }
    try {
      const result = await handler(raw.params);
      return { id: raw.id, ok: true, result };
    } catch (err) {
      return {
        id: raw.id,
        ok: false,
        error: {
          code: "handler_error",
          message: err instanceof Error ? err.message : String(err),
        },
      };
    }
  }
}

function isRequest(raw: unknown): raw is RpcRequest {
  if (typeof raw !== "object" || raw === null) return false;
  const r = raw as Record<string, unknown>;
  const idOk = typeof r.id === "string" || typeof r.id === "number";
  const methodOk = typeof r.method === "string";
  return idOk && methodOk;
}
