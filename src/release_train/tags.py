"""Semver-ish tag parsing and next-train tag / pin-channel logic."""

from __future__ import annotations

import re
from dataclasses import dataclass

from release_train.pins import MinorVersion

# v?MAJOR.MINOR.PATCH with optional PEP440-ish pre: aN / bN / rcN (and alpha/beta/c)
_SEMVER_TAG_RE = re.compile(
    r"""
    ^v?
    (?P<major>\d+)\.
    (?P<minor>\d+)\.
    (?P<patch>\d+)
    (?:
        (?P<pre_label>a|b|rc|alpha|beta|c)
        (?P<pre_num>\d+)
    )?
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Normalize long pre-release names to short letters used in tags
_PRE_NORMALIZE = {
    "a": "a",
    "alpha": "a",
    "b": "b",
    "beta": "b",
    "rc": "rc",
    "c": "rc",
}


@dataclass(frozen=True)
class ParsedTag:
    """A parsed semver-ish tag (stable or pre-release)."""

    major: int
    minor: int
    patch: int
    pre_label: str | None  # normalized: a | b | rc | None
    pre_num: int | None
    raw: str

    @property
    def is_prerelease(self) -> bool:
        return self.pre_label is not None

    def sort_key(self) -> tuple[int, int, int, int, int]:
        """Sort key: version ascending; stable after all pre-releases of same X.Y.Z.

        Pre sort: a < b < rc < stable. Within a label, by pre_num.
        """
        label_rank = {"a": 0, "b": 1, "rc": 2}.get(self.pre_label or "", 3)
        pre_n = self.pre_num if self.pre_num is not None else -1
        # stable: treat as rank 3 with pre_n=0 so it sorts after rc
        if self.pre_label is None:
            label_rank = 3
            pre_n = 0
        return (self.major, self.minor, self.patch, label_rank, pre_n)


@dataclass(frozen=True)
class ReleaseChannel:
    """Train minor plus optional pre-release label from the core ape cut."""

    train: MinorVersion
    pre_label: str | None = None  # a | b | rc | None (stable)

    def default_tag(self) -> str:
        base = f"v{self.train.major}.{self.train.minor}.0"
        if self.pre_label:
            return f"{base}{self.pre_label}0"
        return base

    def pin_spec(self) -> str:
        """Plugin eth-ape pin for this channel.

        Stable: ``>=X.Y.0,<X.(Y+1)``.
        Pre: ``>=X.Y.0a0,<X.(Y+1)`` (same letter, counter 0).
        """
        t = self.train
        if self.pre_label:
            lower = f"{t.major}.{t.minor}.0{self.pre_label}0"
            return f">={lower},<{t.major}.{t.next_minor}"
        return t.pin_spec()

    def display(self) -> str:
        if self.pre_label:
            return f"{self.train.display()} ({self.pre_label}0 channel)"
        return self.train.display()


def parse_semver_tag(tag: str) -> ParsedTag | None:
    """Parse a tag like ``v0.8.3a2``, ``0.8.1b1``, ``v0.8.0rc1``, ``v0.8.12``."""
    if not tag or not isinstance(tag, str):
        return None
    m = _SEMVER_TAG_RE.match(tag.strip())
    if not m:
        return None
    raw_label = m.group("pre_label")
    pre_label = _PRE_NORMALIZE[raw_label.lower()] if raw_label else None
    pre_num = int(m.group("pre_num")) if m.group("pre_num") is not None else None
    return ParsedTag(
        major=int(m.group("major")),
        minor=int(m.group("minor")),
        patch=int(m.group("patch")),
        pre_label=pre_label,
        pre_num=pre_num,
        raw=tag.strip(),
    )


def pick_latest_semver(tags: list[str]) -> str | None:
    """Return the highest semver-ish tag from *tags*, or None if none parse."""
    parsed = [p for t in tags if (p := parse_semver_tag(t)) is not None]
    if not parsed:
        return None
    best = max(parsed, key=lambda p: p.sort_key())
    return best.raw


def next_train_tag(latest: str | None, train: MinorVersion) -> str:
    """Compute the release tag for train minor ``X.Y`` given the latest tag.

    - Latest ``v0.8.3a2`` / ``0.8.1b1`` / ``v0.8.0rc1`` → ``v0.9.0a0`` / ``b0`` / ``rc0``
      (same pre-release label letter/name; version counter resets to 0).
    - Latest stable ``v0.8.12`` → ``v0.9.0``.
    - No tag / unknown → ``vX.Y.0``.
    """
    if latest is None:
        return f"v{train.major}.{train.minor}.0"
    parsed = parse_semver_tag(latest)
    if parsed is None:
        return f"v{train.major}.{train.minor}.0"
    if parsed.pre_label:
        return f"v{train.major}.{train.minor}.0{parsed.pre_label}0"
    return f"v{train.major}.{train.minor}.0"


def channel_from_tag(tag: str, train: MinorVersion) -> ReleaseChannel:
    """Derive the plugin pin channel from a (computed) core ape tag."""
    parsed = parse_semver_tag(tag)
    if parsed and parsed.pre_label:
        return ReleaseChannel(train=train, pre_label=parsed.pre_label)
    return ReleaseChannel(train=train, pre_label=None)


def channel_from_latest(latest: str | None, train: MinorVersion) -> ReleaseChannel:
    """Channel implied by computing the next core tag from *latest*."""
    return channel_from_tag(next_train_tag(latest, train), train)
