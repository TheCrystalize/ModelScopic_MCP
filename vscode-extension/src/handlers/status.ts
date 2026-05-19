import { Dispatcher } from "../rpc";
import { SessionLevel, StatusBar } from "../status";
import { ensureObject } from "./util";

interface SetParams {
  level: SessionLevel;
  detail?: string;
}

const VALID: SessionLevel[] = ["idle", "active", "paused", "killed"];

export function registerStatusHandlers(d: Dispatcher, statusBar: StatusBar): void {
  d.register("status.set", async (params) => {
    const p = ensureObject<SetParams>(params, ["level"]);
    if (!VALID.includes(p.level)) {
      throw new Error(`invalid session level: ${p.level}`);
    }
    statusBar.setSession(p.level, p.detail);
    return { ok: true };
  });
}
