"""Rewrite ``eth-ape`` dependency pins in pyproject.toml text."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Matches eth-ape pins with optional extras and various bound styles, e.g.:
#   eth-ape>=0.8.25,<0.9
#   eth-ape>=0.8.34,<0.9
#   eth-ape>=0.8.38,<1
#   eth-ape[dev]>=0.8.0,<0.9
#   "eth-ape>=0.8.25,<0.9"
_ETH_APE_PIN_RE = re.compile(
    r"""
    (?P<prefix>eth-ape(?:\[[^\]]*\])?)   # package + optional extras
    (?P<spec>
        \s*
        (?:
            >=?\s*[\d.]+                 # lower bound (>= or >)
            (?:\s*,\s*<?\s*[\d.]+)?      # optional upper bound
          | ==\s*[\d.]+                  # exact pin
          | ~=\s*[\d.]+                  # compatible release
        )
    )
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class MinorVersion:
    """A major.minor train target (patch is always .0 for the lower pin)."""

    major: int
    minor: int

    @classmethod
    def parse(cls, value: str) -> MinorVersion:
        parts = value.strip().lstrip("v").split(".")
        if len(parts) < 2:
            raise ValueError(f"Expected major.minor, got {value!r}")
        major, minor = int(parts[0]), int(parts[1])
        if major < 0 or minor < 0:
            raise ValueError(f"Invalid version: {value!r}")
        return cls(major=major, minor=minor)

    @property
    def next_minor(self) -> int:
        return self.minor + 1

    def tag(self, patch: int = 0) -> str:
        return f"v{self.major}.{self.minor}.{patch}"

    def pin_spec(self) -> str:
        """Train policy pin: ``>=X.Y.0,<X.(Y+1)``."""
        return f">={self.major}.{self.minor}.0,<{self.major}.{self.next_minor}"

    def display(self) -> str:
        return f"{self.major}.{self.minor}"


def format_eth_ape_pin(minor: MinorVersion, extras: str = "") -> str:
    """Return the full requirement string for the train pin."""
    pkg = f"eth-ape{extras}" if extras else "eth-ape"
    return f"{pkg}{minor.pin_spec()}"


def rewrite_eth_ape_pin(text: str, minor: MinorVersion) -> tuple[str, int]:
    """Replace all ``eth-ape…`` pin specs in *text* with the train policy pin.

    Preserves extras (e.g. ``eth-ape[dev]``). Returns ``(new_text, n_replacements)``.
    When rewriting for a train, upper bounds like ``<1`` are tightened to the
    next-minor bound per policy.
    """

    def _sub(match: re.Match[str]) -> str:
        prefix = match.group("prefix")
        # prefix is eth-ape or eth-ape[...]
        if prefix.startswith("eth-ape["):
            extras = prefix[len("eth-ape") :]  # includes brackets
            return format_eth_ape_pin(minor, extras=extras)
        return format_eth_ape_pin(minor)

    new_text, n = _ETH_APE_PIN_RE.subn(_sub, text)
    return new_text, n


def find_eth_ape_pins(text: str) -> list[str]:
    """Return the full matched pin strings found in *text*."""
    return [m.group(0) for m in _ETH_APE_PIN_RE.finditer(text)]
