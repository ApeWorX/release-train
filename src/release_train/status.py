"""Status logic: latest tags and open prepare PRs for train members."""

from __future__ import annotations

from dataclasses import dataclass, field

from release_train.github import GhError, gh_available, latest_release_tag, list_open_prs
from release_train.manifest import Manifest
from release_train.pins import MinorVersion


@dataclass
class RepoStatus:
    repo: str
    repo_full: str
    latest_tag: str | None = None
    prepare_prs: list[dict] = field(default_factory=list)
    error: str | None = None


@dataclass
class StatusReport:
    items: list[RepoStatus]
    minor: MinorVersion | None
    offline: bool = False


def gather_status(
    manifest: Manifest,
    minor: MinorVersion | None = None,
    *,
    skip_network: bool = False,
) -> StatusReport:
    online = gh_available() and not skip_network
    items: list[RepoStatus] = []

    search = None
    if minor is not None:
        search = f"eth-ape {minor.display()} in:title"

    for repo in manifest.all_repos:
        full = manifest.full_name(repo)
        st = RepoStatus(repo=repo, repo_full=full)
        if not online:
            st.error = "gh unavailable or network skipped"
            items.append(st)
            continue
        try:
            st.latest_tag = latest_release_tag(full)
            # Prefer title search related to prepare; fall back to broader "eth-ape"
            if search:
                prs = list_open_prs(full, search=search)
            else:
                prs = list_open_prs(full, search="eth-ape")
            # Also catch our default PR title pattern without network search quirks
            if not prs and minor is not None:
                prs = [
                    p
                    for p in list_open_prs(full)
                    if "eth-ape" in (p.get("title") or "").lower()
                    or "release-train" in (p.get("headRefName") or "")
                ]
            st.prepare_prs = prs
        except GhError as exc:
            st.error = str(exc)
        items.append(st)

    return StatusReport(items=items, minor=minor, offline=not online)


def format_status_report(report: StatusReport) -> str:
    lines: list[str] = []
    header = "=== release-train status"
    if report.minor:
        header += f" (minor {report.minor.display()})"
    header += " ==="
    lines.append(header)
    if report.offline:
        lines.append("(offline / no gh — listing train members only)")
    lines.append("")

    for st in report.items:
        tag = st.latest_tag or "—"
        lines.append(f"{st.repo_full}")
        lines.append(f"  latest release: {tag}")
        if st.error and report.offline:
            pass  # already noted globally
        elif st.error:
            lines.append(f"  error: {st.error}")
        if st.prepare_prs:
            for pr in st.prepare_prs:
                lines.append(f"  open PR #{pr.get('number')}: {pr.get('title')} ({pr.get('url')})")
        elif not report.offline and not st.error:
            lines.append("  open prepare PRs: none detected")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
