"""Cut release logic: create GitHub Releases for ape and/or plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from release_train.github import create_release, gh_available, latest_semver_tag
from release_train.manifest import Manifest, RepoRef
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
    """
    members: list[RepoRef] = []
    if target in ("ape", "all"):
        members.append(manifest.core_ref)
    if target in ("plugins", "all"):
        members.extend(manifest.plugin_members)

    tag_cache = dict(latest_tags or {})
    online = gh_available() and not skip_network

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
        if apply:
            cmd = create_release(full, tag, apply=True)
        items.append(CutPlanItem(member=member, tag=tag, command=cmd, latest_tag=latest))

    warnings: list[str] = []
    if target in ("plugins", "all"):
        warnings.append(
            "WARNING: cut --target plugins assumes prepare-pins are merged and any "
            "compat PRs that must land AFTER ape is on PyPI are already merged. "
            "Check `release-train status --minor …` / the compat phase before applying."
        )

    return CutResult(minor=minor, target=target, items=items, apply=apply, warnings=warnings)


def format_cut_report(result: CutResult) -> str:
    mode = "APPLY" if result.apply else "PLAN (no changes)"
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
    for w in result.warnings:
        lines.append(w)
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
    return "\n".join(lines)
