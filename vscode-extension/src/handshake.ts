import { promises as fs } from "fs";
import * as os from "os";
import * as path from "path";

export interface Handshake {
  host: string;
  port: number;
  token: string;
  pid: number;
  writtenAt: string;
}

function handshakeDir(): string {
  return path.join(os.homedir(), ".modelscopic");
}

export function handshakePath(): string {
  return path.join(handshakeDir(), "handshake.json");
}

export async function writeHandshake(h: Handshake): Promise<void> {
  const dir = handshakeDir();
  await fs.mkdir(dir, { recursive: true });
  const file = handshakePath();
  const tmp = `${file}.tmp`;
  await fs.writeFile(tmp, JSON.stringify(h, null, 2), { encoding: "utf8", mode: 0o600 });
  await fs.rename(tmp, file);
  // Best-effort permission tighten on POSIX; no-op on Windows.
  try {
    await fs.chmod(file, 0o600);
  } catch {
    // ignore
  }
}

export async function deleteHandshake(): Promise<void> {
  try {
    await fs.unlink(handshakePath());
  } catch {
    // ignore
  }
}
