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
    assert "ape-template" not in mf.plugins
    assert len(mf.plugins) == 34
    assert "ape-solidity" in mf.plugins
    assert "ape-vyper" in mf.plugins
    assert mf.full_name("ape") == "ApeWorX/ape"


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
    assert mf.plugins == ["ape-vyper", "ape-solidity"]
