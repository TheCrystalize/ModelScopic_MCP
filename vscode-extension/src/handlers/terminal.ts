import * as vscode from "vscode";
import { Dispatcher } from "../rpc";
import { ensureObject } from "./util";

interface CreateParams {
  name?: string;
  cwd?: string;
}

interface SendParams {
  terminalId: string;
  text: string;
  addNewline?: boolean;
}

interface ExecParams {
  terminalId: string;
  commandLine: string;
  timeoutMs?: number;
  maxBytes?: number;
}

// Terminal output capture in VSCode is limited — `Terminal.shellIntegration` is the
// supported path on recent versions but is opt-in per shell. For M1 we expose
// create/send only and surface a note that read is best-effort (added in a later
// milestone). We track terminals by a stable id so the model can reference them.
const terminals = new Map<string, vscode.Terminal>();
let counter = 0;

function nextId(): string {
  counter += 1;
  return `t${counter}`;
}

export function registerTerminalHandlers(d: Dispatcher): void {
  d.register("terminal.create", async (params) => {
    const p = (params ?? {}) as CreateParams;
    const id = nextId();
    const term = vscode.window.createTerminal({ name: p.name ?? `ModelScopic ${id}`, cwd: p.cwd });
    terminals.set(id, term);
    term.show(true);
    return { terminalId: id };
  });

  d.register("terminal.send", async (params) => {
    const p = ensureObject<SendParams>(params, ["terminalId", "text"]);
    const term = terminals.get(p.terminalId);
    if (!term) {
      throw new Error(`unknown terminalId: ${p.terminalId}`);
    }
    term.sendText(p.text, p.addNewline ?? true);
    return { ok: true };
  });

  d.register("terminal.list", async () => {
    return {
      terminals: [...terminals.entries()].map(([id, t]) => ({ id, name: t.name })),
    };
  });

  d.register("terminal.execute", async (params) => {
    const p = ensureObject<ExecParams>(params, ["terminalId", "commandLine"]);
    const term = terminals.get(p.terminalId);
    if (!term) {
      throw new Error(`unknown terminalId: ${p.terminalId}`);
    }
    const si = term.shellIntegration;
    if (!si) {
      throw new Error(
        "shellIntegration not active for this terminal yet. Ensure your shell " +
          "(bash, zsh, pwsh, cmd ≥ Win11) has VSCode shell integration enabled, " +
          "wait a moment after creating the terminal, and retry.",
      );
    }
    term.show(true);
    const exec = si.executeCommand(p.commandLine);
    const maxBytes = p.maxBytes ?? 1_000_000;
    const timeoutMs = p.timeoutMs ?? 60_000;

    const chunks: string[] = [];
    let bytes = 0;
    let truncated = false;
    let exitCode: number | undefined;

    const endPromise = new Promise<void>((resolve) => {
      const sub = vscode.window.onDidEndTerminalShellExecution((evt) => {
        if (evt.execution === exec) {
          exitCode = evt.exitCode ?? undefined;
          sub.dispose();
          resolve();
        }
      });
    });

    const reader = (async () => {
      const stream = exec.read();
      for await (const chunk of stream) {
        const s = stripVtControl(chunk);
        bytes += Buffer.byteLength(s, "utf8");
        if (bytes > maxBytes) {
          truncated = true;
          break;
        }
        chunks.push(s);
      }
    })();

    const timer = new Promise<"timeout">((resolve) =>
      setTimeout(() => resolve("timeout"), timeoutMs),
    );
    const winner = await Promise.race([
      Promise.all([reader, endPromise]).then(() => "done" as const),
      timer,
    ]);

    return {
      output: chunks.join(""),
      bytes,
      truncated,
      timedOut: winner === "timeout",
      exitCode,
    };
  });

  vscode.window.onDidCloseTerminal((closed) => {
    for (const [id, t] of terminals) {
      if (t === closed) {
        terminals.delete(id);
      }
    }
  });
}

// Strip ANSI/VT control sequences so OCR-style text consumers don't choke.
function stripVtControl(s: string): string {
  // eslint-disable-next-line no-control-regex
  return s.replace(/\x1B\[[0-?]*[ -/]*[@-~]/g, "").replace(/\x1B\][^\x07]*\x07/g, "");
}
