"""GitHub milestone + label conventions for release-train state.

Train/compat progress is tracked on GitHub (per-repo milestones + labels),
not in local state files or committed JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from release_train.pins import MinorVersion

# Labels that distinguish prepare-pins vs compat PRs on the same milestone.
LABEL_PINS = "release-train/pins"
LABEL_COMPAT = "release-train/compat"

LABEL_PINS_COLOR = "0E8A16"
LABEL_COMPAT_COLOR = "D93F0B"
LABEL_PINS_DESCRIPTION = "Release-train eth-ape pin-bump PR"
LABEL_COMPAT_DESCRIPTION = "Release-train compat / breaking-API fix PR"

MILESTONE_PREFIX = "release-train/"


def milestone_title(minor: MinorVersion | str) -> str:
    """Return the canonical milestone title for a train minor.

    The minor string is used as the user passes it (e.g. ``0.9``).

    Examples::

        milestone_title("0.9") -> "release-train/0.9"
        milestone_title(MinorVersion(0, 9)) -> "release-train/0.9"
    """
    display = minor.display() if isinstance(minor, MinorVersion) else str(minor).strip().lstrip("v")
    return f"{MILESTONE_PREFIX}{display}"


def train_labels() -> tuple[tuple[str, str, str], ...]:
    """(name, color, description) for both train labels."""
    return (
        (LABEL_PINS, LABEL_PINS_COLOR, LABEL_PINS_DESCRIPTION),
        (LABEL_COMPAT, LABEL_COMPAT_COLOR, LABEL_COMPAT_DESCRIPTION),
    )


@dataclass
class MilestonePRCounts:
    """Open-PR breakdown for a train milestone on one repo."""

    pins_open: int = 0
    compat_open: int = 0
    other_open: int = 0
    milestone_number: int | None = None
    milestone_title: str | None = None
    due_on: str | None = None
    found: bool = False

    @property
    def total_open(self) -> int:
        return self.pins_open + self.compat_open + self.other_open


def _label_names(pr: dict[str, Any]) -> set[str]:
    labels = pr.get("labels") or []
    names: set[str] = set()
    for lab in labels:
        if isinstance(lab, str):
            names.add(lab)
        elif isinstance(lab, dict) and lab.get("name"):
            names.add(str(lab["name"]))
    return names


def count_prs_by_train_label(prs: list[dict[str, Any]]) -> tuple[int, int, int]:
    """Count open PRs by ``release-train/pins`` / ``release-train/compat``.

    Returns ``(pins_open, compat_open, other_open)``. A PR with both labels
    counts in both pin and compat buckets (and not in other).
    """
    pins = 0
    compat = 0
    other = 0
    for pr in prs:
        names = _label_names(pr)
        in_pins = LABEL_PINS in names
        in_compat = LABEL_COMPAT in names
        if in_pins:
            pins += 1
        if in_compat:
            compat += 1
        if not in_pins and not in_compat:
            other += 1
    return pins, compat, other


def milestone_counts_from_payload(
    *,
    milestone: dict[str, Any] | None,
    open_prs: list[dict[str, Any]],
    title: str | None = None,
) -> MilestonePRCounts:
    """Build counts from a milestone API object + open PR JSON list."""
    pins, compat, other = count_prs_by_train_label(open_prs)
    if milestone is None:
        return MilestonePRCounts(
            pins_open=pins,
            compat_open=compat,
            other_open=other,
            milestone_title=title,
            found=False,
        )
    due = milestone.get("due_on") or milestone.get("dueOn")
    return MilestonePRCounts(
        pins_open=pins,
        compat_open=compat,
        other_open=other,
        milestone_number=milestone.get("number"),
        milestone_title=milestone.get("title") or title,
        due_on=due if isinstance(due, str) else None,
        found=True,
    )


def find_milestone_in_list(
    milestones: list[dict[str, Any]],
    title: str,
) -> dict[str, Any] | None:
    """Return the first milestone whose title matches exactly."""
    for ms in milestones:
        if isinstance(ms, dict) and ms.get("title") == title:
            return ms
    return None


def should_block_plugin_cut(*, compat_open: int) -> bool:
    """Refuse plugin cut --apply when any compat-labeled PR is still open."""
    return compat_open > 0


@dataclass
class CutGateResult:
    """Pure gating decision for ``cut --target plugins`` (or ``all``)."""

    blocked: bool = False
    warnings: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    members_with_compat: list[str] = field(default_factory=list)
    members_with_pins: list[str] = field(default_factory=list)

    def merge_member(
        self,
        repo_full: str,
        counts: MilestonePRCounts,
        *,
        title: str,
    ) -> None:
        self.checks.append(
            f"{repo_full}: milestone {title!r} "
            f"{'found' if counts.found else 'absent'} — "
            f"pins open {counts.pins_open} / compat open {counts.compat_open}"
            + (f" / due {counts.due_on}" if counts.due_on else "")
        )
        if counts.compat_open > 0:
            self.members_with_compat.append(repo_full)
            self.blocked = True
        if counts.pins_open > 0:
            self.members_with_pins.append(repo_full)


def finalize_cut_gate(gate: CutGateResult, *, apply: bool) -> CutGateResult:
    """Attach human-readable warnings / block messages after member merges."""
    if gate.members_with_compat:
        repos = ", ".join(gate.members_with_compat)
        msg = (
            f"BLOCK: open release-train/compat PRs on milestone for: {repos}. "
            "Land or close compat PRs before cut --target plugins --apply."
        )
        gate.warnings.append(msg)
        if not apply:
            gate.warnings.append("(Plan mode: would refuse --apply while compat PRs remain open.)")
    if gate.members_with_pins:
        repos = ", ".join(gate.members_with_pins)
        gate.warnings.append(
            f"WARNING: open release-train/pins PRs still on milestone for: {repos}. "
            "Prefer merging pin bumps before cutting plugins."
        )
    if not gate.checks:
        gate.checks.append(
            "Would query each plugin/extra milestone for open PRs labeled "
            f"{LABEL_PINS!r} / {LABEL_COMPAT!r}."
        )
    return gate
