"""Tool registry and per-domain tool modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ..session import SessionManager
from ..vscode_client import VSCodeClient
from . import input as input_tools
from . import session as session_tools
from . import unsafe as unsafe_tools
from . import vision as vision_tools
from . import vscode as vscode_tools


Handler = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Handler
    gated: bool  # if True, participates in session breaker and is audit-logged


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def add(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"duplicate tool: {spec.name}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def specs(self) -> list[ToolSpec]:
        return list(self._specs.values())


def build_tool_registry(*, manager: SessionManager, vscode: VSCodeClient | None) -> ToolRegistry:
    reg = ToolRegistry()
    session_tools.register(reg, manager=manager)
    vscode_tools.register(reg, manager=manager, vscode=vscode)
    vision_tools.register(reg, manager=manager)
    input_tools.register(reg, manager=manager)
    unsafe_tools.register(reg, manager=manager, vscode=vscode)
    return reg
