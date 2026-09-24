"""Cut release logic: create GitHub Releases for ape and/or plugins."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from release_train.github import create_release
from release_train.manifest import Manifest
from release_train.pins import MinorVersion

Target = Literal["ape", "plugins", "all"]


@dataclass
class CutPlanItem:
    repo: str
    repo_full: str
    tag: str
    command: str


@dataclass
class CutResult:
    minor: MinorVersion
    target: Target
    items: list[CutPlanItem]
    apply: bool


def plan_cut(
    manifest: Manifest,
    minor: MinorVersion,
    target: Target,
    *,
    apply: bool = False,
    patch: int = 0,
) -> CutResult:
    tag = minor.tag(patch)
    repos: list[str] = []
    if target in ("ape", "all"):
        repos.append(manifest.core.repo)
    if target in ("plugins", "all"):
        repos.extend(manifest.plugins)

    items: list[CutPlanItem] = []
    for repo in repos:
        full = manifest.full_name(repo)
        # Dry-run always builds the command string; apply executes in order.
        cmd = create_release(full, tag, apply=False)
        if apply:
            cmd = create_release(full, tag, apply=True)
        items.append(CutPlanItem(repo=repo, repo_full=full, tag=tag, command=cmd))

    return CutResult(minor=minor, target=target, items=items, apply=apply)


def format_cut_report(result: CutResult) -> str:
    mode = "APPLY" if result.apply else "DRY-RUN"
    lines = [
        f"== cut target={result.target} minor={result.minor.display()} [{mode}] ==",
        f"Tag: {result.minor.tag()}",
        "Order: ape first, then plugins (when target=all).",
        "PyPI publish: handled by each repo's publish.yaml on release: released.",
        "",
    ]
    for i, item in enumerate(result.items, 1):
        lines.append(f"{i}. {item.repo_full} → {item.tag}")
        lines.append(f"   $ {item.command}")
    if not result.apply:
        lines.append("")
        lines.append("Re-run with --apply to execute these gh release create commands.")
    return "\n".join(lines)
