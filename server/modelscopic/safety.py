"""Safety rules: deny patterns for terminal commands and key chords."""

from __future__ import annotations

import re

# Substring/regex patterns blocked unconditionally for terminal commands.
# These run *before* anything else; the model has to ask the user via VSCode
# (and a future `unsafe_terminal_run` tool, M4) to bypass.
TERMINAL_DENY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
    re.compile(r"\bdel\s+/[sqf]\b", re.IGNORECASE),
    re.compile(r"\bformat\s+[a-z]:", re.IGNORECASE),
    re.compile(r"\bshutdown\b", re.IGNORECASE),
    re.compile(r"\breboot\b", re.IGNORECASE),
    re.compile(r"git\s+push\s+(--force|-f)\b", re.IGNORECASE),
    re.compile(r"git\s+reset\s+--hard\b", re.IGNORECASE),
    re.compile(r":\(\)\{.*\};:"),  # fork bomb
    # Remove-Item with both -Recurse and -Force, in either order:
    re.compile(r"\bRemove-Item\b(?=.*-Recurse\b)(?=.*-Force\b)", re.IGNORECASE),
    re.compile(r"\bdd\s+if=.*of=/dev/", re.IGNORECASE),
]

# Key chords that close/quit the active window. The model can still issue them
# but must call `unsafe_send_keys` (M4) — for now they're rejected outright.
DANGEROUS_CHORDS: set[str] = {
    "alt+f4",
    "ctrl+w",
    "ctrl+shift+w",
    "ctrl+q",
    "cmd+q",
    "meta+q",
    "win+q",
}


class DeniedCommand(RuntimeError):
    """Raised when a terminal command matches a deny pattern."""


class DeniedKeyChord(RuntimeError):
    """Raised when a key chord matches the dangerous list."""


def check_terminal_command(cmd: str) -> None:
    for pat in TERMINAL_DENY_PATTERNS:
        if pat.search(cmd):
            raise DeniedCommand(
                f"terminal command matches deny pattern {pat.pattern!r}; refusing to run"
            )


def check_key_chord(spec: str) -> None:
    normalized = "+".join(p.strip().lower() for p in spec.split("+"))
    if normalized in DANGEROUS_CHORDS:
        raise DeniedKeyChord(f"key chord {normalized!r} is on the dangerous list; refusing")
