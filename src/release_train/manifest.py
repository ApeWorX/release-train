"""Load and validate ``train.yaml``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_MANIFEST_NAMES = ("train.yaml", "train.yml")


@dataclass
class CoreRepo:
    repo: str
    package: str


@dataclass
class Manifest:
    org: str
    core: CoreRepo
    plugins: list[str] = field(default_factory=list)
    policy: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None

    @property
    def all_repos(self) -> list[str]:
        return [self.core.repo, *self.plugins]

    def full_name(self, repo: str) -> str:
        return f"{self.org}/{repo}"


class ManifestError(ValueError):
    """Invalid or missing manifest."""


def _default_search_paths(explicit: Path | None = None) -> list[Path]:
    if explicit is not None:
        return [explicit]
    cwd = Path.cwd()
    candidates: list[Path] = []
    for name in DEFAULT_MANIFEST_NAMES:
        candidates.append(cwd / name)
    # Package-adjacent: repo root when installed editable from src layout
    here = Path(__file__).resolve()
    # src/release_train/manifest.py -> repo root
    repo_root = here.parents[2]
    for name in DEFAULT_MANIFEST_NAMES:
        candidates.append(repo_root / name)
    return candidates


def load_manifest(path: Path | str | None = None) -> Manifest:
    """Load ``train.yaml`` from *path* or search CWD / project root."""
    explicit = Path(path) if path else None
    tried: list[Path] = []
    for candidate in _default_search_paths(explicit):
        tried.append(candidate)
        if candidate.is_file():
            return _parse(candidate)
    locs = ", ".join(str(p) for p in tried)
    raise ManifestError(f"train.yaml not found. Looked in: {locs}")


def _parse(path: Path) -> Manifest:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ManifestError(f"{path}: expected a mapping at top level")

    org = raw.get("org")
    if not org or not isinstance(org, str):
        raise ManifestError(f"{path}: 'org' is required (string)")

    core_raw = raw.get("core")
    if not isinstance(core_raw, dict):
        raise ManifestError(f"{path}: 'core' is required (mapping with repo/package)")
    repo = core_raw.get("repo")
    package = core_raw.get("package")
    if not repo or not package:
        raise ManifestError(f"{path}: core.repo and core.package are required")

    plugins = raw.get("plugins") or []
    if not isinstance(plugins, list) or not all(isinstance(p, str) for p in plugins):
        raise ManifestError(f"{path}: 'plugins' must be a list of strings")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_plugins: list[str] = []
    for p in plugins:
        if p in seen:
            continue
        seen.add(p)
        unique_plugins.append(p)

    policy = raw.get("policy") or {}
    if not isinstance(policy, dict):
        raise ManifestError(f"{path}: 'policy' must be a mapping if present")

    return Manifest(
        org=org,
        core=CoreRepo(repo=str(repo), package=str(package)),
        plugins=unique_plugins,
        policy=policy,
        path=path,
    )
