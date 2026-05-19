"""Reader for the handshake file written by the VSCode companion extension."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


HANDSHAKE_PATH = Path.home() / ".modelscopic" / "handshake.json"


@dataclass(frozen=True)
class Handshake:
    host: str
    port: int
    token: str
    pid: int
    written_at: str


class HandshakeMissing(RuntimeError):
    """The handshake file is absent — the VSCode extension is not running."""


def read_handshake(path: Path = HANDSHAKE_PATH) -> Handshake:
    if not path.exists():
        raise HandshakeMissing(
            f"handshake file not found at {path} — is the ModelScopic VSCode extension running?"
        )
    raw = json.loads(path.read_text(encoding="utf8"))
    return Handshake(
        host=raw["host"],
        port=int(raw["port"]),
        token=raw["token"],
        pid=int(raw["pid"]),
        written_at=raw["writtenAt"],
    )
