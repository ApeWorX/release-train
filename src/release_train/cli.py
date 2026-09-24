"""Cyclopts CLI application."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from cyclopts import App, Parameter

from release_train.cut import format_cut_report, plan_cut
from release_train.manifest import ManifestError, load_manifest
from release_train.pins import MinorVersion
from release_train.prepare import format_prepare_report, plan_prepare
from release_train.status import format_status_report, gather_status

app = App(
    name="release-train",
    help="Orchestrate coordinated minor releases of ape (eth-ape) + ApeWorX plugins.",
)


def _resolve_minor(minor: str) -> MinorVersion:
    return MinorVersion.parse(minor)


@app.command
def prepare(
    minor: Annotated[str, Parameter(name="--minor", help="Train minor, e.g. 0.9")],
    apply: Annotated[
        bool,
        Parameter(name="--apply", help="Print/execute apply path (partial PR automation in v1)"),
    ] = False,
    manifest: Annotated[
        Path | None,
        Parameter(name="--manifest", help="Path to train.yaml"),
    ] = None,
) -> None:
    """Plan eth-ape pin bumps for all plugins (dry-run by default)."""
    try:
        mf = load_manifest(manifest)
    except ManifestError as exc:
        raise SystemExit(f"error: {exc}") from exc
    mv = _resolve_minor(minor)
    result = plan_prepare(mf, mv, apply=apply)
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
    """Show latest release tags and open prepare PRs for train members."""
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
        Parameter(name="--target", help="What to release: ape | plugins | all"),
    ],
    minor: Annotated[str, Parameter(name="--minor", help="Train minor, e.g. 0.9")],
    apply: Annotated[
        bool,
        Parameter(name="--apply", help="Execute gh release create (default: dry-run)"),
    ] = False,
    manifest: Annotated[
        Path | None,
        Parameter(name="--manifest", help="Path to train.yaml"),
    ] = None,
) -> None:
    """Create GitHub Releases with --generate-notes (ape first, then plugins)."""
    try:
        mf = load_manifest(manifest)
    except ManifestError as exc:
        raise SystemExit(f"error: {exc}") from exc
    mv = _resolve_minor(minor)
    result = plan_cut(mf, mv, target, apply=apply)
    print(format_cut_report(result))
