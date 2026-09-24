"""Unit tests for semver tag parsing and next-train tag / channel logic."""

from __future__ import annotations

import pytest

from release_train.pins import MinorVersion, format_eth_ape_pin, rewrite_eth_ape_pin
from release_train.tags import (
    ReleaseChannel,
    channel_from_latest,
    channel_from_tag,
    next_train_tag,
    parse_semver_tag,
    pick_latest_semver,
)


@pytest.mark.parametrize(
    "raw,major,minor,patch,pre_label,pre_num",
    [
        ("v0.8.12", 0, 8, 12, None, None),
        ("0.8.12", 0, 8, 12, None, None),
        ("v0.8.3a2", 0, 8, 3, "a", 2),
        ("0.8.1b1", 0, 8, 1, "b", 1),
        ("v0.8.0rc1", 0, 8, 0, "rc", 1),
        ("v1.0.0alpha0", 1, 0, 0, "a", 0),
        ("v1.0.0beta3", 1, 0, 0, "b", 3),
        ("v0.9.0c1", 0, 9, 0, "rc", 1),
        ("v0.9.0a0", 0, 9, 0, "a", 0),
    ],
)
def test_parse_semver_tag(
    raw: str,
    major: int,
    minor: int,
    patch: int,
    pre_label: str | None,
    pre_num: int | None,
) -> None:
    p = parse_semver_tag(raw)
    assert p is not None
    assert p.major == major
    assert p.minor == minor
    assert p.patch == patch
    assert p.pre_label == pre_label
    assert p.pre_num == pre_num


@pytest.mark.parametrize("raw", ["", "latest", "v1", "0.8", "v0.8.3-dev", "foo"])
def test_parse_semver_tag_invalid(raw: str) -> None:
    assert parse_semver_tag(raw) is None


@pytest.mark.parametrize(
    "latest,train,expected",
    [
        (None, "0.9", "v0.9.0"),
        ("not-a-tag", "0.9", "v0.9.0"),
        ("v0.8.12", "0.9", "v0.9.0"),
        ("0.8.12", "0.9", "v0.9.0"),
        ("v0.8.3a2", "0.9", "v0.9.0a0"),
        ("0.8.1b1", "0.9", "v0.9.0b0"),
        ("v0.8.0rc1", "0.9", "v0.9.0rc0"),
        ("v0.8.0alpha5", "0.9", "v0.9.0a0"),
        ("v0.8.0beta2", "1.0", "v1.0.0b0"),
        ("v0.9.0a3", "0.9", "v0.9.0a0"),  # same minor train: still reset counter
        ("v1.2.5", "2.0", "v2.0.0"),
    ],
)
def test_next_train_tag(latest: str | None, train: str, expected: str) -> None:
    assert next_train_tag(latest, MinorVersion.parse(train)) == expected


def test_pick_latest_semver() -> None:
    tags = ["v0.8.1", "v0.8.3a2", "v0.8.2", "junk", "v0.8.3a1", "v0.7.99"]
    # stable 0.8.2 > 0.8.3a2? No — 0.8.3a2 has higher patch than 0.8.2
    # sort: (0,8,3,a,2) vs (0,8,2,stable) → 0.8.3a2 wins on patch
    assert pick_latest_semver(tags) == "v0.8.3a2"

    # stable beats pre of same X.Y.Z
    assert pick_latest_semver(["v0.8.3a2", "v0.8.3", "v0.8.3b1"]) == "v0.8.3"

    # a < b < rc < stable within same X.Y.Z
    assert pick_latest_semver(["v1.0.0a9", "v1.0.0rc1", "v1.0.0b2"]) == "v1.0.0rc1"

    assert pick_latest_semver([]) is None
    assert pick_latest_semver(["nope"]) is None


def test_channel_from_tag_stable() -> None:
    train = MinorVersion(0, 9)
    ch = channel_from_tag("v0.9.0", train)
    assert ch.pre_label is None
    assert ch.pin_spec() == ">=0.9.0,<0.10"
    assert ch.default_tag() == "v0.9.0"


def test_channel_from_tag_prerelease() -> None:
    train = MinorVersion(0, 9)
    ch = channel_from_tag("v0.9.0a0", train)
    assert ch.pre_label == "a"
    assert ch.pin_spec() == ">=0.9.0a0,<0.10"
    assert ch.default_tag() == "v0.9.0a0"

    ch_b = channel_from_tag("v0.9.0b0", train)
    assert ch_b.pin_spec() == ">=0.9.0b0,<0.10"

    ch_rc = channel_from_tag("v0.9.0rc0", train)
    assert ch_rc.pin_spec() == ">=0.9.0rc0,<0.10"


def test_channel_from_latest() -> None:
    train = MinorVersion(0, 9)
    assert channel_from_latest("v0.8.3a2", train).pre_label == "a"
    assert channel_from_latest("v0.8.12", train).pre_label is None
    assert channel_from_latest(None, train).pre_label is None


def test_format_pin_with_channel() -> None:
    train = MinorVersion(0, 9)
    ch = ReleaseChannel(train=train, pre_label="a")
    assert format_eth_ape_pin(train, channel=ch) == "eth-ape>=0.9.0a0,<0.10"
    assert format_eth_ape_pin(train, extras="[dev]", channel=ch) == ("eth-ape[dev]>=0.9.0a0,<0.10")


def test_rewrite_with_prerelease_channel() -> None:
    train = MinorVersion(0, 9)
    ch = ReleaseChannel(train=train, pre_label="a")
    new, n = rewrite_eth_ape_pin("eth-ape>=0.8.25,<0.9", train, channel=ch)
    assert n == 1
    assert new == "eth-ape>=0.9.0a0,<0.10"


def test_rewrite_matches_existing_prerelease_pin() -> None:
    train = MinorVersion(0, 9)
    text = "eth-ape>=0.9.0a0,<0.10"
    new, n = rewrite_eth_ape_pin(text, train)
    assert n == 1
    assert new == "eth-ape>=0.9.0,<0.10"
