"""Load and validate ``train.yaml``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

DEFAULT_MANIFEST_NAMES = ("train.yaml", "train.yml")

MemberRole = Literal["core", "plugin", "extra"]


@dataclass(frozen=True)
class RepoRef:
    """A train member: owner + repo name + role (core / plugin / extra)."""

    owner: str
    repo: str
    role: MemberRole = "plugin"

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def kind_label(self) -> str:
        if self.role == "extra":
            return "extra/personal"
        if self.role == "core":
            return "core"
        return "plugin"


@dataclass
class CoreRepo:
    repo: str
    package: str


@dataclass
class Manifest:
    org: str
    core: CoreRepo
    plugins: list[RepoRef] = field(default_factory=list)
    extras: list[RepoRef] = field(default_factory=list)
    policy: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None

    @property
    def core_ref(self) -> RepoRef:
        return RepoRef(owner=self.org, repo=self.core.repo, role="core")

    @property
    def plugin_members(self) -> list[RepoRef]:
        """Official plugins + extras (prepare / cut-plugins / status members)."""
        return [*self.plugins, *self.extras]

    @property
    def all_members(self) -> list[RepoRef]:
        return [self.core_ref, *self.plugin_members]

    @property
    def all_repos(self) -> list[str]:
        """Bare repo names for core + plugins + extras (legacy helper)."""
        return [m.repo for m in self.all_members]

    def full_name(self, repo: str) -> str:
        """Resolve a bare repo name or ``owner/repo`` to ``owner/repo``."""
        if "/" in repo:
            return repo
        # Prefer an explicit member match
        for m in self.all_members:
            if m.repo == repo:
                return m.full_name
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


def _parse_member(
    entry: Any,
    *,
    default_org: str,
    role: MemberRole,
    path: Path,
    key: str,
) -> RepoRef:
    """Parse a bare name, ``owner/repo`` string, or ``{owner, repo}`` mapping."""
    if isinstance(entry, str):
        name = entry.strip()
        if not name:
            raise ManifestError(f"{path}: '{key}' entries must be non-empty")
        if "/" in name:
            owner, _, repo = name.partition("/")
            owner, repo = owner.strip(), repo.strip()
            if not owner or not repo or "/" in repo:
                raise ManifestError(
                    f"{path}: '{key}' entry {entry!r} must be 'owner/repo' or bare repo"
                )
            return RepoRef(owner=owner, repo=repo, role=role)
        return RepoRef(owner=default_org, repo=name, role=role)

    if isinstance(entry, dict):
        owner = entry.get("owner") or default_org
        repo = entry.get("repo")
        if not repo or not isinstance(repo, str):
            raise ManifestError(f"{path}: '{key}' mapping requires 'repo' (string)")
        if not isinstance(owner, str) or not owner:
            raise ManifestError(f"{path}: '{key}' mapping 'owner' must be a non-empty string")
        return RepoRef(owner=owner, repo=repo.strip(), role=role)

    kind = type(entry).__name__
    raise ManifestError(
        f"{path}: '{key}' entries must be strings or {{owner, repo}} mappings, got {kind}"
    )


def _dedupe_refs(refs: list[RepoRef]) -> list[RepoRef]:
    seen: set[str] = set()
    out: list[RepoRef] = []
    for r in refs:
        key = r.full_name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


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

    plugins_raw = raw.get("plugins") or []
    if not isinstance(plugins_raw, list):
        raise ManifestError(f"{path}: 'plugins' must be a list")
    plugins = _dedupe_refs(
        [
            _parse_member(p, default_org=org, role="plugin", path=path, key="plugins")
            for p in plugins_raw
        ]
    )

    extras_raw = raw.get("extra") or []
    if not isinstance(extras_raw, list):
        raise ManifestError(f"{path}: 'extra' must be a list if present")
    extras = _dedupe_refs(
        [
            _parse_member(e, default_org=org, role="extra", path=path, key="extra")
            for e in extras_raw
        ]
    )

    # Drop extras that duplicate an official plugin full_name
    plugin_names = {p.full_name.lower() for p in plugins}
    extras = [e for e in extras if e.full_name.lower() not in plugin_names]

    policy = raw.get("policy") or {}
    if not isinstance(policy, dict):
        raise ManifestError(f"{path}: 'policy' must be a mapping if present")

    return Manifest(
        org=org,
        core=CoreRepo(repo=str(repo), package=str(package)),
        plugins=plugins,
        extras=extras,
        policy=policy,
        path=path,
    )
