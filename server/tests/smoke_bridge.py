"""Live smoke test for the VSCode bridge. Requires the extension to be running.

Run: ``python tests/smoke_bridge.py``

Exercises ping, editor.read, terminal.create + terminal.execute, diagnostics.get.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# allow running this file directly without an editable install
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modelscopic.handshake import HandshakeMissing, read_handshake  # noqa: E402
from modelscopic.vscode_client import VSCodeClient, VSCodeRpcError  # noqa: E402


async def main() -> int:
    try:
        handshake = read_handshake()
    except HandshakeMissing as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"OK   handshake: {handshake.host}:{handshake.port}")

    client = VSCodeClient(handshake)
    await client.connect()
    print("OK   connected")

    failures = 0

    async def step(name: str, coro) -> object | None:
        nonlocal failures
        try:
            result = await coro
        except VSCodeRpcError as exc:
            print(f"FAIL {name}: {exc}")
            failures += 1
            return None
        print(f"OK   {name}")
        return result

    # ping
    await step("ping", client.call("ping"))

    # workspace listing -- doesn't matter if empty, just a roundtrip
    files = await step("workspace.list", client.call("workspace.list", {"glob": "**/*.json", "maxResults": 5}))
    if isinstance(files, dict) and files.get("files"):
        print(f"     found {len(files['files'])} json file(s); first: {files['files'][0]}")

    # diagnostics for everything
    await step("diagnostics.get", client.call("diagnostics.get"))

    # create terminal + execute. shellIntegration may not be ready instantly --
    # we retry the execute a couple of times.
    term = await step("terminal.create", client.call("terminal.create", {"name": "smoke"}))
    if isinstance(term, dict) and term.get("terminalId"):
        tid = term["terminalId"]
        print(f"     terminalId={tid}")
        last_err: BaseException | None = None
        for attempt in range(3):
            await asyncio.sleep(1.5)
            try:
                out = await client.call("terminal.execute", {
                    "terminalId": tid,
                    "commandLine": "echo modelscopic-smoke-OK",
                    "timeoutMs": 8000,
                })
                last_err = None
                print(f"OK   terminal.execute (attempt {attempt + 1}): exit={out.get('exitCode')} bytes={out.get('bytes')}")
                print(f"     output (truncated): {out.get('output', '')[:200]!r}")
                break
            except VSCodeRpcError as exc:
                last_err = exc
                print(f"     terminal.execute attempt {attempt + 1} failed: {exc}")
        if last_err is not None:
            print("FAIL terminal.execute: shellIntegration likely not active for this shell yet")
            failures += 1

    await client.close()
    print()
    print(f"{'PASS' if failures == 0 else 'FAIL'}: {failures} failure(s)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
