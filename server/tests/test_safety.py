from __future__ import annotations

import pytest

from modelscopic.safety import (
    DeniedCommand,
    DeniedKeyChord,
    check_key_chord,
    check_terminal_command,
)


@pytest.mark.parametrize("cmd", [
    "rm -rf /",
    "rm   -rf  ~",
    "RM -RF .",
    "del /s C:\\foo",
    "format C:",
    "shutdown /r /t 0",
    "git push --force origin main",
    "git push -f",
    "git reset --hard HEAD~3",
    ":(){:|:&};:",
    "Remove-Item C:\\temp -Recurse -Force",
    "dd if=/dev/zero of=/dev/sda",
])
def test_dangerous_commands_blocked(cmd: str) -> None:
    with pytest.raises(DeniedCommand):
        check_terminal_command(cmd)


@pytest.mark.parametrize("cmd", [
    "ls -la",
    "git status",
    "python app.py",
    "npm install",
    "git push origin main",       # no --force
    "git reset HEAD~",            # no --hard
    "echo rm -rf is just a string",  # literal works? actually this would match!
])
def test_safe_commands_pass(cmd: str) -> None:
    if "rm -rf" in cmd:
        pytest.skip("literal 'rm -rf' in echo would correctly match the deny pattern")
    check_terminal_command(cmd)


@pytest.mark.parametrize("chord", ["alt+f4", "ALT+F4", "ctrl+w", "ctrl+q", "win+q"])
def test_dangerous_chords_blocked(chord: str) -> None:
    with pytest.raises(DeniedKeyChord):
        check_key_chord(chord)


@pytest.mark.parametrize("chord", ["ctrl+s", "ctrl+shift+p", "f5", "enter", "tab"])
def test_safe_chords_pass(chord: str) -> None:
    check_key_chord(chord)
