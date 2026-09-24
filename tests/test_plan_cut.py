"""Unit tests for plan / cut / prepare reporting (offline, no gh)."""

from __future__ import annotations

from pathlib import Path

import yaml

from release_train.cut import format_cut_report, plan_cut
from release_train.manifest import load_manifest
from release_train.pins import MinorVersion
from release_train.plan import build_train_plan, format_train_plan
from release_train.prepare import format_prepare_report, plan_prepare
from release_train.status import TRAIN_PHASES, format_status_report, gather_status
from release_train.tags import ReleaseChannel


def _mini_manifest(tmp_path: Path):
    data = {
        "org": "ApeWorX",
        "core": {"repo": "ape", "package": "eth-ape"},
        "plugins": ["ape-vyper"],
        "extra": ["someone/ape-fake"],
    }
    path = tmp_path / "train.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return load_manifest(path)


def test_prepare_includes_extras_and_plan_header(tmp_path: Path) -> None:
    mf = _mini_manifest(tmp_path)
    mv = MinorVersion(0, 9)
    result = plan_prepare(mf, mv, apply=False, skip_network=True)
    assert len(result.items) == 2
    assert result.items[0].member.role == "plugin"
    assert result.items[1].member.role == "extra"
    report = format_prepare_report(result)
    assert "PLAN (no changes)" in report
    assert "extra/personal" in report
    assert "ApeWorX/ape-vyper" in report
    assert "someone/ape-fake" in report
    assert "APPLY" not in report or "partial" in report.lower()  # plan mode


def test_prepare_apply_header(tmp_path: Path) -> None:
    mf = _mini_manifest(tmp_path)
    result = plan_prepare(mf, MinorVersion(0, 9), apply=True, skip_network=True)
    report = format_prepare_report(result)
    assert report.startswith("== prepare 0.9 [APPLY] ==")


def test_prepare_prerelease_channel(tmp_path: Path) -> None:
    mf = _mini_manifest(tmp_path)
    mv = MinorVersion(0, 9)
    ch = ReleaseChannel(train=mv, pre_label="a")
    result = plan_prepare(mf, mv, channel=ch, skip_network=True)
    assert result.items[0].new_pin == "eth-ape>=0.9.0a0,<0.10"


def test_cut_per_repo_tags(tmp_path: Path) -> None:
    mf = _mini_manifest(tmp_path)
    mv = MinorVersion(0, 9)
    latest = {
        "ApeWorX/ape": "v0.8.3a2",
        "ApeWorX/ape-vyper": "v0.8.12",
        "someone/ape-fake": "v0.8.1b1",
    }
    result = plan_cut(mf, mv, "all", apply=False, latest_tags=latest, skip_network=True)
    tags = {i.repo_full: i.tag for i in result.items}
    assert tags["ApeWorX/ape"] == "v0.9.0a0"
    assert tags["ApeWorX/ape-vyper"] == "v0.9.0"
    assert tags["someone/ape-fake"] == "v0.9.0b0"
    report = format_cut_report(result)
    assert "PLAN (no changes)" in report
    assert "WARNING" in report  # plugins target warning on all
    assert "v0.9.0a0" in report
    assert "extra/personal" in report


def test_cut_plugins_warns_compat(tmp_path: Path) -> None:
    mf = _mini_manifest(tmp_path)
    result = plan_cut(mf, MinorVersion(0, 9), "plugins", skip_network=True, latest_tags={})
    assert any("compat" in w.lower() for w in result.warnings)


def test_train_plan_phases(tmp_path: Path) -> None:
    mf = _mini_manifest(tmp_path)
    mv = MinorVersion(0, 9)
    latest = {"ApeWorX/ape": "v0.8.3a2"}
    plan = build_train_plan(mf, mv, latest_tags=latest, skip_network=True)
    assert plan.ape_tag == "v0.9.0a0"
    assert plan.channel.pre_label == "a"
    text = format_train_plan(plan)
    assert "PLAN (no changes)" in text
    assert "Phase 1: prepare-pins" in text
    assert "Phase 2: cut-ape" in text
    assert "Phase 3: compat" in text
    assert "Phase 4: cut-plugins" in text
    assert "GATED" in text
    assert "eth-ape>=0.9.0a0,<0.10" in text
    for name, _ in TRAIN_PHASES:
        assert name in text


def test_status_offline_shows_phases(tmp_path: Path) -> None:
    mf = _mini_manifest(tmp_path)
    report = gather_status(mf, MinorVersion(0, 9), skip_network=True)
    text = format_status_report(report)
    assert "prepare-pins" in text
    assert "compat" in text
    assert "cut-plugins" in text
    assert "extra/personal" in text
    assert "ApeWorX/ape" in text
