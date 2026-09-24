"""GitHub milestone conventions for release-train state.

Train progress is tracked on GitHub via per-repo milestones only
(no release-scoped labels). Pin bumps and compat fixes are both
ordinary train PRs assigned to ``release-train/{minor}``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from release_train.pins import MinorVersion

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


@dataclass
class MilestonePRCounts:
    """Open vs closed PR counts for a train milestone on one repo."""

    open_count: int = 0
    closed_count: int = 0
    milestone_number: int | None = None
    milestone_title: str | None = None
    due_on: str | None = None
    found: bool = False

    @property
    def total(self) -> int:
        return self.open_count + self.closed_count


def milestone_counts_from_payload(
    *,
    milestone: dict[str, Any] | None,
    open_prs: list[dict[str, Any]],
    title: str | None = None,
) -> MilestonePRCounts:
    """Build counts from a milestone API object + open PR JSON list.

    Open count comes from the listed open PRs. Closed count uses the
    milestone's ``closed_issues`` field when the milestone is found
    (GitHub counts both issues and PRs on the milestone).
    """
    open_count = len(open_prs)
    if milestone is None:
        return MilestonePRCounts(
            open_count=open_count,
            closed_count=0,
            milestone_title=title,
            found=False,
        )
    closed_raw = milestone.get("closed_issues")
    if closed_raw is None:
        closed_raw = milestone.get("closedIssues")
    try:
        closed_count = int(closed_raw) if closed_raw is not None else 0
    except (TypeError, ValueError):
        closed_count = 0
    due = milestone.get("due_on") or milestone.get("dueOn")
    return MilestonePRCounts(
        open_count=open_count,
        closed_count=closed_count,
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


def should_block_plugin_cut(*, open_count: int) -> bool:
    """Refuse plugin cut --apply when any PR is still open on the milestone."""
    return open_count > 0


@dataclass
class CutGateResult:
    """Pure gating decision for ``cut --target plugins`` (or ``all``)."""

    blocked: bool = False
    warnings: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    members_with_open: list[str] = field(default_factory=list)

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
            f"open {counts.open_count} / closed {counts.closed_count}"
            f" (total {counts.total})" + (f" / due {counts.due_on}" if counts.due_on else "")
        )
        if counts.open_count > 0:
            self.members_with_open.append(repo_full)
            self.blocked = True


def finalize_cut_gate(gate: CutGateResult, *, apply: bool) -> CutGateResult:
    """Attach human-readable warnings / block messages after member merges."""
    if gate.members_with_open:
        repos = ", ".join(gate.members_with_open)
        msg = (
            f"BLOCK: open PRs still on milestone for: {repos}. "
            "Land or close all milestone PRs before cut --target plugins --apply."
        )
        gate.warnings.append(msg)
        if not apply:
            gate.warnings.append(
                "(Plan mode: would refuse --apply while any milestone PRs remain open.)"
            )
    if not gate.checks:
        gate.checks.append(
            "Would query each plugin/extra milestone for any open PRs (gate if open > 0)."
        )
    return gate
