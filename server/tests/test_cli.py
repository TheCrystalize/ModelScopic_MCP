from __future__ import annotations

import pytest

from modelscopic.cli import _PARSE_ERROR, _coerce, _parse_args


def test_empty_args_is_empty_dict() -> None:
    assert _parse_args("") == {}
    assert _parse_args("   ") == {}


def test_json_object() -> None:
    assert _parse_args('{"x": 1, "y": 2}') == {"x": 1, "y": 2}
    assert _parse_args('{"text": "hello world"}') == {"text": "hello world"}


def test_json_object_invalid() -> None:
    assert _parse_args("{nope}") is _PARSE_ERROR


def test_key_value_basic() -> None:
    assert _parse_args("x=1 y=2") == {"x": 1, "y": 2}


def test_key_value_strings_quoted() -> None:
    assert _parse_args('name="Hello World"') == {"name": "Hello World"}


def test_key_value_bools_nulls() -> None:
    assert _parse_args("enabled=true muted=false ttl=null") == {
        "enabled": True,
        "muted": False,
        "ttl": None,
    }


def test_key_value_nested_json() -> None:
    assert _parse_args('rect=[1,2,3,4]') == {"rect": [1, 2, 3, 4]}


def test_key_value_unquoted_string_falls_through() -> None:
    assert _parse_args("name=alice") == {"name": "alice"}


def test_key_value_missing_equals_errors() -> None:
    assert _parse_args("just_text") is _PARSE_ERROR


def test_coerce_types() -> None:
    assert _coerce("1") == 1
    assert _coerce("1.5") == 1.5
    assert _coerce("true") is True
    assert _coerce("null") is None
    assert _coerce('"quoted"') == "quoted"
    assert _coerce("plain") == "plain"
    assert _coerce("[1,2]") == [1, 2]
