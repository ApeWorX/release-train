"""Thin wrappers around the ``gh`` CLI for GitHub operations."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any


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


def gh_api(endpoint: str, method: str = "GET") -> Any:
    """Call ``gh api`` and parse JSON."""
    result = run_gh("api", "-X", method, endpoint)
    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)


def latest_release_tag(repo_full: str) -> str | None:
    """Return the latest release tag name, or None if none / error."""
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
        "number,title,url,headRefName",
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
