"""Tests for milestone title/label helpers and cut gating pure logic."""

from __future__ import annotations

from pathlib import Path

import yaml

from release_train.cut import format_cut_report, plan_cut
from release_train.manifest import load_manifest
from release_train.milestones import (
    LABEL_COMPAT,
    LABEL_PINS,
    CutGateResult,
    count_prs_by_train_label,
    finalize_cut_gate,
    find_milestone_in_list,
    milestone_counts_from_payload,
    milestone_title,
    should_block_plugin_cut,
)
from release_train.pins import MinorVersion
from release_train.plan import build_train_plan, format_train_plan
from release_train.prepare import format_prepare_report, plan_prepare
from release_train.status import format_status_report, gather_status


def test_milestone_title_from_str_and_minor() -> None:
    assert milestone_title("0.9") == "release-train/0.9"
    assert milestone_title(MinorVersion(0, 9)) == "release-train/0.9"
    assert milestone_title("v0.10") == "release-train/0.10"


def test_label_constants() -> None:
    assert LABEL_PINS == "release-train/pins"
    assert LABEL_COMPAT == "release-train/compat"


def test_find_milestone_in_list_fixture() -> None:
    fixtures = [
        {"number": 1, "title": "other", "due_on": None},
        {"number": 7, "title": "release-train/0.9", "due_on": "2026-10-01T00:00:00Z"},
    ]
    found = find_milestone_in_list(fixtures, "release-train/0.9")
    assert found is not None
    assert found["number"] == 7
    assert find_milestone_in_list(fixtures, "missing") is None


def test_count_prs_by_train_label_fixture() -> None:
    prs = [
        {"number": 1, "labels": [{"name": "release-train/pins"}]},
        {"number": 2, "labels": [{"name": "release-train/compat"}]},
        {"number": 3, "labels": [{"name": "release-train/pins"}, {"name": "release-train/compat"}]},
        {"number": 4, "labels": [{"name": "bug"}]},
        {"number": 5, "labels": []},
    ]
    pins, compat, other = count_prs_by_train_label(prs)
    assert pins == 2
    assert compat == 2
    assert other == 2


def test_milestone_counts_from_payload() -> None:
    ms = {"number": 3, "title": "release-train/0.9", "due_on": "2026-12-01T00:00:00Z"}
    prs = [
        {"labels": [{"name": LABEL_PINS}]},
        {"labels": [{"name": LABEL_COMPAT}]},
    ]
    counts = milestone_counts_from_payload(milestone=ms, open_prs=prs, title="release-train/0.9")
    assert counts.found is True
    assert counts.pins_open == 1
    assert counts.compat_open == 1
    assert counts.due_on == "2026-12-01T00:00:00Z"
    assert counts.milestone_number == 3

    absent = milestone_counts_from_payload(milestone=None, open_prs=[], title="release-train/0.9")
    assert absent.found is False
    assert absent.total_open == 0


def test_should_block_plugin_cut() -> None:
    assert should_block_plugin_cut(compat_open=1) is True
    assert should_block_plugin_cut(compat_open=0) is False


def test_cut_gate_result_merge_and_finalize() -> None:
    gate = CutGateResult()
    counts_ok = milestone_counts_from_payload(
        milestone={"number": 1, "title": "release-train/0.9"},
        open_prs=[{"labels": [{"name": LABEL_PINS}]}],
        title="release-train/0.9",
    )
    counts_bad = milestone_counts_from_payload(
        milestone={"number": 1, "title": "release-train/0.9"},
        open_prs=[{"labels": [{"name": LABEL_COMPAT}]}],
        title="release-train/0.9",
    )
    gate.merge_member("ApeWorX/ape-vyper", counts_ok, title="release-train/0.9")
    gate.merge_member("someone/ape-fake", counts_bad, title="release-train/0.9")
    assert gate.blocked is True
    assert "someone/ape-fake" in gate.members_with_compat
    assert "ApeWorX/ape-vyper" in gate.members_with_pins
    finalize_cut_gate(gate, apply=True)
    assert any("BLOCK" in w for w in gate.warnings)
    assert any("WARNING" in w and "pins" in w for w in gate.warnings)


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


def test_prepare_plan_mentions_milestone(tmp_path: Path) -> None:
    mf = _mini_manifest(tmp_path)
    result = plan_prepare(mf, MinorVersion(0, 9), apply=False, skip_network=True)
    assert result.milestone == "release-train/0.9"
    assert all(i.milestone == "release-train/0.9" for i in result.items)
    assert all(i.label == LABEL_PINS for i in result.items)
    report = format_prepare_report(result)
    assert "release-train/0.9" in report
    assert LABEL_PINS in report


def test_prepare_apply_recipes_include_milestone_and_labels(tmp_path: Path) -> None:
    mf = _mini_manifest(tmp_path)
    result = plan_prepare(mf, MinorVersion(0, 9), apply=True, skip_network=True)
    report = format_prepare_report(result)
    assert "--milestone" in report
    assert f'--label "{LABEL_PINS}"' in report or f"--label {LABEL_PINS}" in report
    assert "gh api -X POST" in report
    assert "gh label create" in report
    cmds = result.items[0].gh_commands()
    joined = "\n".join(cmds)
    assert 'milestone "release-train/0.9"' in joined
    assert LABEL_PINS in joined


def test_train_plan_mentions_github_state(tmp_path: Path) -> None:
    mf = _mini_manifest(tmp_path)
    plan = build_train_plan(mf, MinorVersion(0, 9), latest_tags={}, skip_network=True)
    text = format_train_plan(plan)
    assert "release-train/0.9" in text
    assert "GitHub as source of truth" in text or "source of truth" in text
    assert "ensure" in text.lower()
    assert LABEL_PINS in text
    assert LABEL_COMPAT in text
    assert "no local state" in text.lower() or "No local state" in text


def test_status_offline_mentions_network_for_milestones(tmp_path: Path) -> None:
    mf = _mini_manifest(tmp_path)
    report = gather_status(mf, MinorVersion(0, 9), skip_network=True)
    text = format_status_report(report)
    assert "Network required" in text or "network" in text.lower()
    assert "release-train/0.9" in text or "milestone" in text.lower()


def test_cut_plugins_offline_prints_gate_checks(tmp_path: Path) -> None:
    mf = _mini_manifest(tmp_path)
    result = plan_cut(
        mf, MinorVersion(0, 9), "plugins", apply=False, skip_network=True, latest_tags={}
    )
    assert result.milestone == "release-train/0.9"
    assert result.gate_checks
    assert result.blocked is False  # offline plan does not block
    report = format_cut_report(result)
    assert "Gate checks" in report
    assert LABEL_COMPAT in report


def test_cut_plugins_apply_blocked_when_compat_injected(tmp_path: Path, monkeypatch) -> None:
    """Simulate online gate with open compat PRs → blocked apply."""
    mf = _mini_manifest(tmp_path)

    def fake_available() -> bool:
        return True

    def fake_find(repo: str, title: str):
        return {"number": 1, "title": title, "due_on": None}

    def fake_prs(repo: str, title: str):
        return [
            {
                "number": 9,
                "title": "compat: fix API",
                "url": "https://example/pr/9",
                "labels": [{"name": LABEL_COMPAT}],
                "milestone": {"title": title},
            }
        ]

    monkeypatch.setattr("release_train.cut.gh_available", fake_available)
    monkeypatch.setattr("release_train.cut.find_milestone", fake_find)
    monkeypatch.setattr("release_train.cut.list_open_prs_on_milestone", fake_prs)
    # Avoid real tag / release network
    monkeypatch.setattr("release_train.cut.latest_semver_tag", lambda _r: "v0.8.1")
    monkeypatch.setattr(
        "release_train.cut.create_release",
        lambda repo, tag, apply=False: f"gh release create {tag} --repo {repo}",
    )

    result = plan_cut(
        mf, MinorVersion(0, 9), "plugins", apply=True, skip_network=False, latest_tags={}
    )
    assert result.blocked is True
    assert any("BLOCK" in w for w in result.warnings)
    report = format_cut_report(result)
    assert "APPLY BLOCKED" in report
