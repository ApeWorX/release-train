"""Unit tests for eth-ape pin rewriting."""

from __future__ import annotations

import pytest

from release_train.pins import (
    MinorVersion,
    find_eth_ape_pins,
    format_eth_ape_pin,
    rewrite_eth_ape_pin,
)


@pytest.mark.parametrize(
    "raw,major,minor",
    [
        ("0.9", 0, 9),
        ("v0.9", 0, 9),
        ("0.9.0", 0, 9),
        ("1.2", 1, 2),
    ],
)
def test_parse_minor(raw: str, major: int, minor: int) -> None:
    mv = MinorVersion.parse(raw)
    assert mv.major == major
    assert mv.minor == minor
    assert mv.next_minor == minor + 1


def test_parse_minor_invalid() -> None:
    with pytest.raises(ValueError):
        MinorVersion.parse("9")
    with pytest.raises(ValueError):
        MinorVersion.parse("nope")


def test_pin_spec() -> None:
    mv = MinorVersion(0, 9)
    assert mv.pin_spec() == ">=0.9.0,<0.10"
    assert format_eth_ape_pin(mv) == "eth-ape>=0.9.0,<0.10"
    assert format_eth_ape_pin(mv, extras="[dev]") == "eth-ape[dev]>=0.9.0,<0.10"
    assert mv.tag() == "v0.9.0"


@pytest.mark.parametrize(
    "original,expected",
    [
        ("eth-ape>=0.8.25,<0.9", "eth-ape>=0.9.0,<0.10"),
        ("eth-ape>=0.8.34,<0.9", "eth-ape>=0.9.0,<0.10"),
        ("eth-ape>=0.8.38,<1", "eth-ape>=0.9.0,<0.10"),
        ('"eth-ape>=0.8.25,<0.9"', '"eth-ape>=0.9.0,<0.10"'),
        ("eth-ape[dev]>=0.8.0,<0.9", "eth-ape[dev]>=0.9.0,<0.10"),
        ("  eth-ape>=0.8.1,<0.9  ", "  eth-ape>=0.9.0,<0.10  "),
    ],
)
def test_rewrite_common_forms(original: str, expected: str) -> None:
    mv = MinorVersion(0, 9)
    new, n = rewrite_eth_ape_pin(original, mv)
    assert n == 1
    assert new == expected


def test_rewrite_in_pyproject_snippet() -> None:
    text = """\
[project]
dependencies = [
    "eth-ape>=0.8.25,<0.9",
    "click>=8",
]
"""
    mv = MinorVersion(0, 9)
    new, n = rewrite_eth_ape_pin(text, mv)
    assert n == 1
    assert "eth-ape>=0.9.0,<0.10" in new
    assert "click>=8" in new
    assert "0.8.25" not in new


def test_rewrite_multiple() -> None:
    text = "eth-ape>=0.8.25,<0.9\neth-ape>=0.8.38,<1\n"
    mv = MinorVersion(0, 9)
    new, n = rewrite_eth_ape_pin(text, mv)
    assert n == 2
    assert find_eth_ape_pins(new) == ["eth-ape>=0.9.0,<0.10", "eth-ape>=0.9.0,<0.10"]


def test_rewrite_no_match() -> None:
    text = "requests>=2.0\n"
    new, n = rewrite_eth_ape_pin(text, MinorVersion(0, 9))
    assert n == 0
    assert new == text


def test_rewrite_major_bump_train() -> None:
    """1.0 train tightens pins accordingly."""
    text = "eth-ape>=0.8.38,<1"
    new, n = rewrite_eth_ape_pin(text, MinorVersion(1, 0))
    assert n == 1
    assert new == "eth-ape>=1.0.0,<1.1"


def test_find_pins() -> None:
    text = 'deps = ["eth-ape>=0.8.25,<0.9", "other"]'
    found = find_eth_ape_pins(text)
    assert found == ["eth-ape>=0.8.25,<0.9"]
