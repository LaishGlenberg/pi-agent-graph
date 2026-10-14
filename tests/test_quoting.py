"""Tests for shell / OS quoting helpers."""

from __future__ import annotations

import shlex

import pytest

from pi_agent_graph.quoting import (
    join_posix,
    quote_applescript,
    quote_posix,
    quote_windows,
)

TRICKY = [
    "simple",
    "with space",
    "it's",
    'double"quote',
    "dollar$sign",
    "back\\slash",
    "new\nline",
    "",
    "--flag",
    "a'b\"c$d\\e\nf",
    "~$HOME`cmd`",
]


@pytest.mark.parametrize("value", TRICKY)
def test_quote_posix_round_trips(value):
    assert shlex.split(quote_posix(value), posix=True) == [value]


def test_quote_posix_simple():
    assert quote_posix("abc") == "'abc'"


def test_quote_posix_escapes_single_quote():
    assert quote_posix("it's") == "'it'\\''s'"


def test_join_posix_round_trips():
    argv = ["pi", "--system-prompt", "multi\nline 'quoted' $x", "--", "go"]
    assert shlex.split(join_posix(argv), posix=True) == argv


def test_join_posix_empty():
    assert join_posix([]) == ""


def test_quote_applescript_escapes_backslash_and_quote():
    assert quote_applescript('a"b\\c') == 'a\\"b\\\\c'


def test_quote_applescript_plain():
    assert quote_applescript("plain") == "plain"


def test_quote_windows_keeps_tokens():
    rendered = quote_windows(["pi", "--name", "a b"])
    assert "pi" in rendered
    assert "a b" in rendered
