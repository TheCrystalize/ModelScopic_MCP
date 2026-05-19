"""WebSocket client that talks to the VSCode companion extension."""

from __future__ import annotations

import asyncio
import itertools
import json
from typing import Any

import websockets
from websockets.client import WebSocketClientProtocol

from .handshake import Handshake


class VSCodeRpcError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class VSCodeClient:
    """Thin JSON-RPC-like client over a single WebSocket.

    Requests are correlated by an integer id. The extension's `Dispatcher` echoes
    the id back in its reply, so we resolve futures by id.
    """

    def __init__(self, handshake: Handshake) -> None:
        self._handshake = handshake
        self._ws: WebSocketClientProtocol | None = None
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._ws is not None:
            return
        url = f"ws://{self._handshake.host}:{self._handshake.port}"
        self._ws = await websockets.connect(
            url,
            additional_headers={"Authorization": f"Bearer {self._handshake.token}"},
            max_size=64 * 1024 * 1024,  # generous for future image payloads
        )
        self._reader_task = asyncio.create_task(self._reader())

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
            self._reader_task = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("client closed"))
        self._pending.clear()

    async def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if self._ws is None:
            raise ConnectionError("not connected")
        req_id = next(self._ids)
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending[req_id] = fut
        payload = json.dumps({"id": req_id, "method": method, "params": params or {}})
        async with self._send_lock:
            await self._ws.send(payload)
        try:
            return await fut
        finally:
            self._pending.pop(req_id, None)

    async def _reader(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                req_id = msg.get("id")
                fut = self._pending.get(req_id) if isinstance(req_id, int) else None
                if fut is None or fut.done():
                    continue
                if msg.get("ok"):
                    fut.set_result(msg.get("result"))
                else:
                    err = msg.get("error") or {"code": "unknown", "message": "no error info"}
                    fut.set_exception(VSCodeRpcError(err.get("code", "unknown"), err.get("message", "")))
        except Exception as exc:  # noqa: BLE001
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(exc)
