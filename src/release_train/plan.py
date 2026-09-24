"""Top-level multi-phase train plan (always non-mutating)."""

from __future__ import annotations

from dataclasses import dataclass

from release_train.cut import CutResult, format_cut_report, plan_cut
from release_train.manifest import Manifest
from release_train.pins import MinorVersion
from release_train.prepare import PrepareResult, format_prepare_report, plan_prepare
from release_train.status import TRAIN_PHASES
from release_train.tags import ReleaseChannel, channel_from_latest, next_train_tag


@dataclass
class TrainPlan:
    minor: MinorVersion
    prepare: PrepareResult
    cut_ape: CutResult
    cut_plugins: CutResult
    channel: ReleaseChannel
    ape_tag: str


def build_train_plan(
    manifest: Manifest,
    minor: MinorVersion,
    *,
    latest_tags: dict[str, str | None] | None = None,
    skip_network: bool = True,
) -> TrainPlan:
    """Assemble the full four-phase plan for a minor (never mutates)."""
    tag_cache = dict(latest_tags or {})
    core_full = manifest.core_ref.full_name
    core_latest = tag_cache.get(core_full)
    channel = channel_from_latest(core_latest, minor)
    ape_tag = next_train_tag(core_latest, minor)

    prepare = plan_prepare(
        manifest,
        minor,
        apply=False,
        channel=channel,
        core_latest_tag=core_latest,
        skip_network=True,
    )
    cut_ape = plan_cut(
        manifest,
        minor,
        "ape",
        apply=False,
        latest_tags=tag_cache,
        skip_network=skip_network,
    )
    cut_plugins = plan_cut(
        manifest,
        minor,
        "plugins",
        apply=False,
        latest_tags=tag_cache,
        skip_network=skip_network,
    )
    return TrainPlan(
        minor=minor,
        prepare=prepare,
        cut_ape=cut_ape,
        cut_plugins=cut_plugins,
        channel=channel,
        ape_tag=ape_tag,
    )


def format_train_plan(plan: TrainPlan) -> str:
    lines: list[str] = []
    lines.append(f"== PLAN (no changes) — minor {plan.minor.display()} train ==")
    lines.append(f"Core ape computed tag: {plan.ape_tag}")
    lines.append(f"Plugin pin channel: {plan.channel.display()} → eth-ape{plan.channel.pin_spec()}")
    lines.append("")
    lines.append("Phases (in order):")
    for i, (name, desc) in enumerate(TRAIN_PHASES, 1):
        lines.append(f"  {i}. {name} — {desc}")
    lines.append("")

    # Phase 1
    lines.append("--- Phase 1: prepare-pins ---")
    lines.append(format_prepare_report(plan.prepare))
    lines.append("")

    # Phase 2
    lines.append("--- Phase 2: cut-ape ---")
    lines.append(format_cut_report(plan.cut_ape))
    lines.append("")

    # Phase 3
    lines.append("--- Phase 3: compat ---")
    lines.append("[PLAN (no changes)]")
    lines.append(
        f"GATED step: land compat PRs per repo after ape {plan.minor.display()} "
        f"({plan.ape_tag}) is on PyPI."
    )
    lines.append(
        "Breaking API fixes that must follow the ape cut belong here. "
        "`prepare --phase compat` may be added later; v1 is phase awareness only."
    )
    lines.append("Optional later: list known open compat PR URLs in status.")
    lines.append("")

    # Phase 4
    lines.append("--- Phase 4: cut-plugins ---")
    lines.append("Prerequisite: prepare-pins merged; compat PRs landed as needed.")
    lines.append(format_cut_report(plan.cut_plugins))
    lines.append("")
    lines.append(
        "This command never mutates. Use `prepare --apply` / `cut … --apply` "
        "for individual phases when ready."
    )
    return "\n".join(lines)
