"""Cyclopts CLI application."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from cyclopts import App, Parameter

from release_train.cut import format_cut_report, plan_cut
from release_train.manifest import ManifestError, load_manifest
from release_train.pins import MinorVersion
from release_train.plan import build_train_plan, format_train_plan
from release_train.prepare import format_prepare_report, plan_prepare
from release_train.status import format_status_report, gather_status

app = App(
    name="release-train",
    help="Orchestrate coordinated minor releases of ape (eth-ape) + ApeWorX plugins.",
)


def _resolve_minor(minor: str) -> MinorVersion:
    return MinorVersion.parse(minor)


@app.command
def plan(
    minor: Annotated[str, Parameter(name="--minor", help="Train minor, e.g. 0.9")],
    manifest: Annotated[
        Path | None,
        Parameter(name="--manifest", help="Path to train.yaml"),
    ] = None,
    offline: Annotated[
        bool,
        Parameter(name="--offline", help="Skip gh tag lookups (default tags vX.Y.0)"),
    ] = False,
) -> None:
    """Print the full multi-phase train sequence (always a plan; never mutates).

    Phases: prepare-pins → cut-ape → compat → cut-plugins.
    """
    try:
        mf = load_manifest(manifest)
    except ManifestError as exc:
        raise SystemExit(f"error: {exc}") from exc
    mv = _resolve_minor(minor)
    train_plan = build_train_plan(mf, mv, skip_network=offline)
    print(format_train_plan(train_plan))


@app.command
def prepare(
    minor: Annotated[str, Parameter(name="--minor", help="Train minor, e.g. 0.9")],
    apply: Annotated[
        bool,
        Parameter(
            name="--apply",
            help="Print/execute apply path (partial PR automation in v1). Default: plan only.",
        ),
    ] = False,
    manifest: Annotated[
        Path | None,
        Parameter(name="--manifest", help="Path to train.yaml"),
    ] = None,
    offline: Annotated[
        bool,
        Parameter(name="--offline", help="Skip gh lookup of ape latest tag for channel"),
    ] = False,
) -> None:
    """Plan eth-ape pin bumps for all plugins + extras (plan by default; --apply to act)."""
    try:
        mf = load_manifest(manifest)
    except ManifestError as exc:
        raise SystemExit(f"error: {exc}") from exc
    mv = _resolve_minor(minor)
    result = plan_prepare(mf, mv, apply=apply, skip_network=offline)
    print(format_prepare_report(result))


@app.command
def status(
    minor: Annotated[
        str | None,
        Parameter(name="--minor", help="Optional minor to filter prepare PR search"),
    ] = None,
    manifest: Annotated[
        Path | None,
        Parameter(name="--manifest", help="Path to train.yaml"),
    ] = None,
    offline: Annotated[
        bool,
        Parameter(name="--offline", help="Skip gh network calls"),
    ] = False,
) -> None:
    """Show phases, latest tags, and open prepare PRs for train members."""
    try:
        mf = load_manifest(manifest)
    except ManifestError as exc:
        raise SystemExit(f"error: {exc}") from exc
    mv = _resolve_minor(minor) if minor else None
    report = gather_status(mf, mv, skip_network=offline)
    print(format_status_report(report))


@app.command
def cut(
    target: Annotated[
        Literal["ape", "plugins", "all"],
        Parameter(
            name="--target",
            help=(
                "What to release: ape | plugins | all. "
                "For plugins: ensure prepare-pins are merged and compat PRs "
                "(breaking fixes after ape is on PyPI) have landed before --apply."
            ),
        ),
    ],
    minor: Annotated[str, Parameter(name="--minor", help="Train minor, e.g. 0.9")],
    apply: Annotated[
        bool,
        Parameter(
            name="--apply",
            help="Execute gh release create (default: plan only, no changes)",
        ),
    ] = False,
    manifest: Annotated[
        Path | None,
        Parameter(name="--manifest", help="Path to train.yaml"),
    ] = None,
    offline: Annotated[
        bool,
        Parameter(name="--offline", help="Skip gh tag lookups; tags default to vX.Y.0"),
    ] = False,
) -> None:
    """Create GitHub Releases with --generate-notes (ape first, then plugins).

    Default is a plan. Pass --apply to execute. Plugin cuts should wait for the
    compat phase when breaking API fixes are required after ape lands on PyPI.
    """
    try:
        mf = load_manifest(manifest)
    except ManifestError as exc:
        raise SystemExit(f"error: {exc}") from exc
    mv = _resolve_minor(minor)
    result = plan_cut(mf, mv, target, apply=apply, skip_network=offline)
    print(format_cut_report(result))
