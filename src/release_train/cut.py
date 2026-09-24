"""Cut release logic: create GitHub Releases for ape and/or plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from release_train.github import (
    create_release,
    find_milestone,
    gh_available,
    latest_semver_tag,
    list_open_prs_on_milestone,
)
from release_train.manifest import Manifest, RepoRef
from release_train.milestones import (
    CutGateResult,
    finalize_cut_gate,
    milestone_counts_from_payload,
    milestone_title,
)
from release_train.pins import MinorVersion
from release_train.tags import next_train_tag

Target = Literal["ape", "plugins", "all"]


@dataclass
class CutPlanItem:
    member: RepoRef
    tag: str
    command: str
    latest_tag: str | None = None

    @property
    def repo(self) -> str:
        return self.member.repo

    @property
    def repo_full(self) -> str:
        return self.member.full_name


@dataclass
class CutResult:
    minor: MinorVersion
    target: Target
    items: list[CutPlanItem]
    apply: bool
    warnings: list[str] = field(default_factory=list)
    blocked: bool = False
    gate_checks: list[str] = field(default_factory=list)
    milestone: str | None = None


def _evaluate_plugin_gate(
    manifest: Manifest,
    minor: MinorVersion,
    *,
    apply: bool,
    skip_network: bool,
) -> CutGateResult:
    """Check for any open PRs on the train milestone for each plugin/extra."""
    gate = CutGateResult()
    ms = milestone_title(minor)
    online = gh_available() and not skip_network

    gate.checks.append(
        f"Gate: for each plugin/extra, query milestone `{ms}` for any open PRs "
        "(block --apply if open > 0)."
    )

    if not online:
        gate.checks.append("Network skipped or gh unavailable — gate not evaluated against GitHub.")
        gate.warnings.append(
            "WARNING: milestone open-PR gate not checked (offline / no gh). "
            "Re-run without --offline before --apply when possible."
        )
        return finalize_cut_gate(gate, apply=apply)

    for member in manifest.plugin_members:
        full = member.full_name
        try:
            ms_obj = find_milestone(full, ms)
            prs = list_open_prs_on_milestone(full, ms)
            counts = milestone_counts_from_payload(milestone=ms_obj, open_prs=prs, title=ms)
            gate.merge_member(full, counts, title=ms)
        except Exception as exc:  # noqa: BLE001
            gate.checks.append(f"{full}: gate query failed: {exc}")
            gate.warnings.append(f"WARNING: could not query milestone on {full}: {exc}")
            if apply:
                # Refuse apply when we cannot verify the gate
                gate.blocked = True
                gate.warnings.append(
                    f"BLOCK: refusing --apply because gate could not be verified for {full}."
                )

    return finalize_cut_gate(gate, apply=apply)


def plan_cut(
    manifest: Manifest,
    minor: MinorVersion,
    target: Target,
    *,
    apply: bool = False,
    latest_tags: dict[str, str | None] | None = None,
    skip_network: bool = False,
) -> CutResult:
    """Plan GitHub Releases. Each repo gets its own computed tag from latest semver.

    *latest_tags* maps ``owner/repo`` → latest tag (for tests / offline). When
    omitted and network is available, tags are fetched via ``gh``.

    For ``plugins`` / ``all``, evaluates the milestone open-PR gate. ``--apply``
    is refused (``blocked=True``) when any member has open PRs on the train
    milestone.
    """
    members: list[RepoRef] = []
    if target in ("ape", "all"):
        members.append(manifest.core_ref)
    if target in ("plugins", "all"):
        members.extend(manifest.plugin_members)

    tag_cache = dict(latest_tags or {})
    online = gh_available() and not skip_network
    ms = milestone_title(minor) if target in ("plugins", "all") else None

    warnings: list[str] = []
    gate_checks: list[str] = []
    blocked = False

    if target in ("plugins", "all"):
        warnings.append(
            "WARNING: cut --target plugins assumes prepare-pins are merged and any "
            "compat PRs that must land AFTER ape is on PyPI are already merged. "
            "Check `release-train status --minor …` before applying."
        )
        gate = _evaluate_plugin_gate(manifest, minor, apply=apply, skip_network=skip_network)
        warnings.extend(gate.warnings)
        gate_checks.extend(gate.checks)
        blocked = gate.blocked

    # Do not mutate when blocked
    do_apply = apply and not blocked

    items: list[CutPlanItem] = []
    for member in members:
        full = member.full_name
        if full not in tag_cache:
            if online:
                tag_cache[full] = latest_semver_tag(full)
            else:
                tag_cache[full] = None
        latest = tag_cache[full]
        tag = next_train_tag(latest, minor)
        cmd = create_release(full, tag, apply=False)
        if do_apply:
            cmd = create_release(full, tag, apply=True)
        items.append(CutPlanItem(member=member, tag=tag, command=cmd, latest_tag=latest))

    return CutResult(
        minor=minor,
        target=target,
        items=items,
        apply=apply,
        warnings=warnings,
        blocked=blocked,
        gate_checks=gate_checks,
        milestone=ms,
    )


def format_cut_report(result: CutResult) -> str:
    mode = "APPLY" if result.apply else "PLAN (no changes)"
    if result.blocked:
        mode = "APPLY BLOCKED"
    phase = {
        "ape": "cut-ape",
        "plugins": "cut-plugins",
        "all": "cut-ape then cut-plugins",
    }.get(result.target, result.target)
    lines = [
        f"== cut target={result.target} minor={result.minor.display()} [{mode}] ==",
        f"Phase: {phase}",
        "Each repo uses its own computed tag (pre-release label preserved, counter→0).",
        "Order: ape first, then official plugins, then extras (when target=all).",
        "PyPI publish: handled by each repo's publish.yaml on release: released.",
        "",
    ]
    if result.milestone:
        lines.append(
            f"Milestone gate: `{result.milestone}` "
            "(block --apply if any open PRs remain on the milestone)."
        )
        lines.append("")
    if result.gate_checks:
        lines.append("Gate checks:")
        for c in result.gate_checks:
            lines.append(f"  • {c}")
        lines.append("")
    for w in result.warnings:
        lines.append(w)
        lines.append("")
    if result.blocked:
        lines.append(
            "No releases were created. Land or close all open milestone PRs, "
            "then re-run cut --apply."
        )
        lines.append("")
    for i, item in enumerate(result.items, 1):
        latest = item.latest_tag or "(none/unknown)"
        lines.append(
            f"{i}. {item.repo_full}  [{item.member.kind_label}]  latest={latest} → {item.tag}"
        )
        lines.append(f"   $ {item.command}")
    if not result.apply:
        lines.append("")
        lines.append("Re-run with --apply to execute these gh release create commands.")
    elif result.blocked:
        lines.append("")
        lines.append("(--apply was refused due to the milestone open-PR gate.)")
    return "\n".join(lines)
