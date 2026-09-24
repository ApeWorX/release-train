"""Unit tests for train.yaml loading."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from release_train.manifest import ManifestError, load_manifest


def test_load_bundled_manifest() -> None:
    root = Path(__file__).resolve().parents[1]
    mf = load_manifest(root / "train.yaml")
    assert mf.org == "ApeWorX"
    assert mf.core.repo == "ape"
    assert mf.core.package == "eth-ape"
    assert "ape-template" not in [p.repo for p in mf.plugins]
    assert len(mf.plugins) == 34
    assert any(p.repo == "ape-solidity" for p in mf.plugins)
    assert any(p.repo == "ape-vyper" for p in mf.plugins)
    assert mf.full_name("ape") == "ApeWorX/ape"
    assert mf.extras == []
    assert mf.core_ref.full_name == "ApeWorX/ape"
    assert all(p.role == "plugin" for p in mf.plugins)
    assert all(p.owner == "ApeWorX" for p in mf.plugins)


def test_load_missing(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="not found"):
        load_manifest(tmp_path / "nope.yaml")


def test_load_invalid(tmp_path: Path) -> None:
    bad = tmp_path / "train.yaml"
    bad.write_text("plugins: not-a-list\n", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(bad)


def test_dedupe_plugins(tmp_path: Path) -> None:
    data = {
        "org": "ApeWorX",
        "core": {"repo": "ape", "package": "eth-ape"},
        "plugins": ["ape-vyper", "ape-vyper", "ape-solidity"],
    }
    path = tmp_path / "train.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    mf = load_manifest(path)
    assert [p.repo for p in mf.plugins] == ["ape-vyper", "ape-solidity"]


def test_extra_owner_repo_string(tmp_path: Path) -> None:
    data = {
        "org": "ApeWorX",
        "core": {"repo": "ape", "package": "eth-ape"},
        "plugins": ["ape-vyper"],
        "extra": ["someone/ape-fake-example", "ape-local-extra"],
    }
    path = tmp_path / "train.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    mf = load_manifest(path)
    assert len(mf.extras) == 2
    assert mf.extras[0].owner == "someone"
    assert mf.extras[0].repo == "ape-fake-example"
    assert mf.extras[0].role == "extra"
    assert mf.extras[0].kind_label == "extra/personal"
    # bare name under extra still uses default org
    assert mf.extras[1].owner == "ApeWorX"
    assert mf.extras[1].repo == "ape-local-extra"
    members = mf.plugin_members
    assert [m.full_name for m in members] == [
        "ApeWorX/ape-vyper",
        "someone/ape-fake-example",
        "ApeWorX/ape-local-extra",
    ]


def test_extra_structured_mapping(tmp_path: Path) -> None:
    data = {
        "org": "ApeWorX",
        "core": {"repo": "ape", "package": "eth-ape"},
        "plugins": ["ape-solidity"],
        "extra": [{"owner": "alice", "repo": "ape-toy"}],
    }
    path = tmp_path / "train.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    mf = load_manifest(path)
    assert len(mf.extras) == 1
    assert mf.extras[0].full_name == "alice/ape-toy"
    assert mf.extras[0].role == "extra"


def test_extra_dedupe_against_plugins(tmp_path: Path) -> None:
    data = {
        "org": "ApeWorX",
        "core": {"repo": "ape", "package": "eth-ape"},
        "plugins": ["ape-vyper"],
        "extra": ["ApeWorX/ape-vyper", "bob/ape-other"],
    }
    path = tmp_path / "train.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    mf = load_manifest(path)
    assert [e.full_name for e in mf.extras] == ["bob/ape-other"]


def test_invalid_extra_entry(tmp_path: Path) -> None:
    data = {
        "org": "ApeWorX",
        "core": {"repo": "ape", "package": "eth-ape"},
        "plugins": [],
        "extra": [123],
    }
    path = tmp_path / "train.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    with pytest.raises(ManifestError, match="extra"):
        load_manifest(path)
