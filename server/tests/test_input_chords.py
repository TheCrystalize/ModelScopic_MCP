"""Tests for the chord parser (pure logic, runs on any platform)."""

from __future__ import annotations

import pytest

from modelscopic.input import parse_chord


def test_simple_letter() -> None:
    assert parse_chord("a") == [0x41]


def test_ctrl_s() -> None:
    assert parse_chord("ctrl+s") == [0x11, 0x53]


def test_chord_with_function_key() -> None:
    assert parse_chord("alt+f4") == [0x12, 0x73]


def test_chord_with_digit() -> None:
    assert parse_chord("ctrl+1") == [0x11, 0x31]


def test_aliases_resolve_to_same_vk() -> None:
    assert parse_chord("ctrl+s") == parse_chord("control+s")
    assert parse_chord("alt+f4") == parse_chord("menu+f4")
    assert parse_chord("esc") == parse_chord("escape")


def test_whitespace_tolerated() -> None:
    assert parse_chord(" ctrl + shift + p ") == [0x11, 0x10, 0x50]


def test_unknown_key_raises() -> None:
    with pytest.raises(ValueError):
        parse_chord("ctrl+zz9plural")


def test_empty_chord_raises() -> None:
    with pytest.raises(ValueError):
        parse_chord("")
    with pytest.raises(ValueError):
        parse_chord("+")
