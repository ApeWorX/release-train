"""Thin wrappers around the ``gh`` CLI for GitHub operations."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from release_train.milestones import (
    LABEL_COMPAT,
    LABEL_COMPAT_COLOR,
    LABEL_COMPAT_DESCRIPTION,
    LABEL_PINS,
    LABEL_PINS_COLOR,
    LABEL_PINS_DESCRIPTION,
    find_milestone_in_list,
    train_labels,
)
from release_train.tags import pick_latest_semver


class GhError(RuntimeError):
    """``gh`` invocation failed or is unavailable."""


def gh_available() -> bool:
    return shutil.which("gh") is not None


def run_gh(
    *args: str,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    if not gh_available():
        raise GhError("`gh` CLI not found on PATH. Install: https://cli.github.com/")
    cmd = ["gh", *args]
    result = subprocess.run(
        cmd,
        check=False,
        capture_output=capture,
        text=True,
    )
    if check and result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise GhError(f"gh {' '.join(args)} failed ({result.returncode}): {err}")
    return result


def gh_api(
    endpoint: str,
    method: str = "GET",
    *,
    fields: dict[str, str] | None = None,
    raw_fields: dict[str, str] | None = None,
) -> Any:
    """Call ``gh api`` and parse JSON.

    *fields* are passed as ``-f key=value`` (strings). *raw_fields* as ``-F``.
    """
    args = ["api", "-X", method, endpoint]
    if fields:
        for key, value in fields.items():
            args.extend(["-f", f"{key}={value}"])
    if raw_fields:
        for key, value in raw_fields.items():
            args.extend(["-F", f"{key}={value}"])
    result = run_gh(*args)
    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)


def latest_release_tag(repo_full: str) -> str | None:
    """Return the latest GitHub *release* tag name, or None if none / error."""
    try:
        result = run_gh(
            "release",
            "view",
            "--repo",
            repo_full,
            "--json",
            "tagName",
            check=False,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return data.get("tagName")
    except (GhError, json.JSONDecodeError):
        return None


def list_tag_names(repo_full: str, *, limit: int = 100) -> list[str]:
    """List tag names via ``gh api`` (newest-first from GitHub, not sorted)."""
    try:
        result = run_gh(
            "api",
            f"repos/{repo_full}/tags",
            "--paginate",
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        data = json.loads(result.stdout)
        if not isinstance(data, list):
            return []
        names = [t.get("name") for t in data if isinstance(t, dict) and t.get("name")]
        return names[:limit] if limit else names
    except (GhError, json.JSONDecodeError):
        return []


def latest_semver_tag(repo_full: str) -> str | None:
    """Highest semver-ish tag on the repo (includes pre-releases), via gh."""
    tags = list_tag_names(repo_full)
    return pick_latest_semver(tags)


def list_open_prs(repo_full: str, search: str | None = None) -> list[dict[str, Any]]:
    """List open PRs; optional ``search`` filters title via ``--search``."""
    args = [
        "pr",
        "list",
        "--repo",
        repo_full,
        "--state",
        "open",
        "--json",
        "number,title,url,headRefName,labels,milestone",
        "--limit",
        "50",
    ]
    if search:
        args.extend(["--search", search])
    try:
        result = run_gh(*args, check=False)
        if result.returncode != 0:
            return []
        return json.loads(result.stdout)
    except (GhError, json.JSONDecodeError):
        return []


def list_milestones(repo_full: str, *, state: str = "all") -> list[dict[str, Any]]:
    """List milestones via REST API (``state``: open|closed|all)."""
    try:
        result = run_gh(
            "api",
            f"repos/{repo_full}/milestones?state={state}&per_page=100",
            "--paginate",
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        data = json.loads(result.stdout)
        if not isinstance(data, list):
            return []
        return [m for m in data if isinstance(m, dict)]
    except (GhError, json.JSONDecodeError):
        return []


def find_milestone(repo_full: str, title: str) -> dict[str, Any] | None:
    """Find a milestone by exact title (open or closed)."""
    return find_milestone_in_list(list_milestones(repo_full, state="all"), title)


def create_milestone(
    repo_full: str,
    title: str,
    *,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a milestone; returns the API JSON object."""
    fields: dict[str, str] = {"title": title, "state": "open"}
    if description:
        fields["description"] = description
    data = gh_api(f"repos/{repo_full}/milestones", method="POST", fields=fields)
    if not isinstance(data, dict):
        raise GhError(f"unexpected response creating milestone on {repo_full}")
    return data


def ensure_milestone(
    repo_full: str,
    title: str,
    *,
    apply: bool = False,
    description: str | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Ensure milestone exists. On apply, create via API if absent.

    Returns ``(milestone_or_None, log_lines)``. In plan mode (apply=False),
    returns recipe commands and does not mutate.
    """
    lines: list[str] = []
    existing = find_milestone(repo_full, title)
    if existing is not None:
        lines.append(f"# milestone already present on {repo_full}: {title!r}")
        return existing, lines

    desc = description or f"Release-train tracking for {title}"
    recipe = (
        f"gh api -X POST repos/{repo_full}/milestones "
        f'-f title="{title}" -f state=open '
        f'-f description="{desc}"'
    )
    if not apply:
        lines.append(f"# create milestone if absent on {repo_full}")
        lines.append(recipe)
        return None, lines

    created = create_milestone(repo_full, title, description=desc)
    lines.append(f"# created milestone on {repo_full}: {title!r} (#{created.get('number')})")
    return created, lines


def list_label_names(repo_full: str) -> set[str]:
    """Return label names on the repo."""
    try:
        result = run_gh(
            "label",
            "list",
            "--repo",
            repo_full,
            "--json",
            "name",
            "--limit",
            "100",
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return set()
        data = json.loads(result.stdout)
        if not isinstance(data, list):
            return set()
        return {str(x["name"]) for x in data if isinstance(x, dict) and x.get("name")}
    except (GhError, json.JSONDecodeError):
        return set()


def ensure_label(
    repo_full: str,
    name: str,
    *,
    color: str,
    description: str,
    apply: bool = False,
) -> list[str]:
    """Ensure a label exists. On apply, create via ``gh label create`` if absent."""
    lines: list[str] = []
    existing = list_label_names(repo_full)
    if name in existing:
        lines.append(f"# label already present on {repo_full}: {name!r}")
        return lines

    recipe = (
        f'gh label create "{name}" --repo {repo_full} --color {color} --description "{description}"'
    )
    if not apply:
        lines.append(f"# create label if absent on {repo_full}")
        lines.append(recipe)
        return lines

    run_gh(
        "label",
        "create",
        name,
        "--repo",
        repo_full,
        "--color",
        color,
        "--description",
        description,
    )
    lines.append(f"# created label on {repo_full}: {name!r}")
    return lines


def ensure_train_labels(repo_full: str, *, apply: bool = False) -> list[str]:
    """Ensure both ``release-train/pins`` and ``release-train/compat`` labels."""
    lines: list[str] = []
    for name, color, desc in train_labels():
        lines.extend(ensure_label(repo_full, name, color=color, description=desc, apply=apply))
    return lines


def ensure_milestone_and_labels(
    repo_full: str,
    title: str,
    *,
    apply: bool = False,
) -> list[str]:
    """Ensure train milestone + both labels; return log / recipe lines."""
    _, ms_lines = ensure_milestone(repo_full, title, apply=apply)
    label_lines = ensure_train_labels(repo_full, apply=apply)
    return [*ms_lines, *label_lines]


def list_open_prs_on_milestone(
    repo_full: str,
    milestone_title: str,
) -> list[dict[str, Any]]:
    """List open PRs assigned to a milestone (by title), with labels."""
    # GitHub search: milestone:"title"
    search = f'milestone:"{milestone_title}"'
    prs = list_open_prs(repo_full, search=search)
    # Fallback: list open and filter client-side if search returned empty
    # (search can be eventual-consistent / permission quirks).
    if prs:
        return prs
    try:
        result = run_gh(
            "pr",
            "list",
            "--repo",
            repo_full,
            "--state",
            "open",
            "--json",
            "number,title,url,headRefName,labels,milestone",
            "--limit",
            "50",
            check=False,
        )
        if result.returncode != 0:
            return []
        all_prs = json.loads(result.stdout)
        out: list[dict[str, Any]] = []
        for pr in all_prs:
            if not isinstance(pr, dict):
                continue
            ms = pr.get("milestone")
            ms_title = ms.get("title") if isinstance(ms, dict) else ms
            if ms_title == milestone_title:
                out.append(pr)
        return out
    except (GhError, json.JSONDecodeError):
        return []


def recipe_ensure_milestone(repo_full: str, title: str) -> str:
    """Shell recipe to create a milestone if the operator runs it manually."""
    return (
        f"gh api -X POST repos/{repo_full}/milestones "
        f'-f title="{title}" -f state=open '
        f'-f description="Release-train tracking for {title}"'
    )


def recipe_ensure_label(repo_full: str, name: str, color: str, description: str) -> str:
    return (
        f'gh label create "{name}" --repo {repo_full} --color {color} --description "{description}"'
    )


def recipe_pr_create_with_milestone(
    *,
    repo_full: str,
    head: str,
    title: str,
    milestone: str,
    label: str,
    body: str,
) -> str:
    """Exact ``gh pr create`` including milestone + label."""
    # Body via heredoc keeps multiline safe in printed recipes.
    return (
        f"gh pr create --repo {repo_full} --head {head} "
        f'--title "{title}" '
        f'--milestone "{milestone}" '
        f'--label "{label}" '
        f"--body-file - <<'EOF'\n{body}\nEOF"
    )


# Re-export label constants for callers that import from github
__all_labels__ = (
    LABEL_PINS,
    LABEL_COMPAT,
    LABEL_PINS_COLOR,
    LABEL_COMPAT_COLOR,
    LABEL_PINS_DESCRIPTION,
    LABEL_COMPAT_DESCRIPTION,
)


@dataclass
class ReleasePlan:
    repo_full: str
    tag: str
    title: str | None = None

    def gh_command(self) -> str:
        parts = [
            "gh",
            "release",
            "create",
            self.tag,
            "--repo",
            self.repo_full,
            "--generate-notes",
        ]
        if self.title:
            parts.extend(["--title", self.title])
        return " ".join(parts)


def create_release(
    repo_full: str,
    tag: str,
    *,
    title: str | None = None,
    apply: bool = False,
) -> str:
    """Create a GitHub Release or return the dry-run command string."""
    plan = ReleasePlan(repo_full=repo_full, tag=tag, title=title)
    cmd = plan.gh_command()
    if not apply:
        return cmd
    args = [
        "release",
        "create",
        tag,
        "--repo",
        repo_full,
        "--generate-notes",
    ]
    if title:
        args.extend(["--title", title])
    run_gh(*args)
    return cmd
