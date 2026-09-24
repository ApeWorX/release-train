"""Status logic: latest tags, phases, and open prepare PRs for train members."""

from __future__ import annotations

from dataclasses import dataclass, field

from release_train.github import GhError, gh_available, latest_semver_tag, list_open_prs
from release_train.manifest import Manifest, RepoRef
from release_train.pins import MinorVersion
from release_train.tags import next_train_tag

# Explicit minor-train lifecycle (breaking / coordinated release).
TRAIN_PHASES = (
    (
        "prepare-pins",
        "Open/plan PRs that only bump eth-ape pins "
        "(may be opened before ape is cut; often draft until ape ships).",
    ),
    (
        "cut-ape",
        "GitHub Release for ape (eth-ape) at the computed train tag.",
    ),
    (
        "compat",
        "GATED: land compat / breaking-API fix PRs per repo AFTER ape X.Y is on PyPI.",
    ),
    (
        "cut-plugins",
        "Release official plugins + extras only after pins merged (+ compat as needed).",
    ),
)


@dataclass
class RepoStatus:
    member: RepoRef
    latest_tag: str | None = None
    next_tag: str | None = None
    prepare_prs: list[dict] = field(default_factory=list)
    error: str | None = None

    @property
    def repo(self) -> str:
        return self.member.repo

    @property
    def repo_full(self) -> str:
        return self.member.full_name


@dataclass
class StatusReport:
    items: list[RepoStatus]
    minor: MinorVersion | None
    offline: bool = False
    phases: tuple[tuple[str, str], ...] = TRAIN_PHASES


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

    for member in manifest.all_members:
        full = member.full_name
        st = RepoStatus(member=member)
        if not online:
            st.error = "gh unavailable or network skipped"
            if minor is not None:
                st.next_tag = next_train_tag(None, minor)
            items.append(st)
            continue
        try:
            st.latest_tag = latest_semver_tag(full)
            if minor is not None:
                st.next_tag = next_train_tag(st.latest_tag, minor)
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

    lines.append("Train phases (minor lifecycle):")
    for name, desc in report.phases:
        gate = ""
        if name == "compat" and report.minor:
            gate = f" — land compat PRs per repo after ape {report.minor.display()} is on PyPI"
        lines.append(f"  {name}: {desc}{gate}")
    lines.append("")

    for st in report.items:
        tag = st.latest_tag or "—"
        lines.append(f"{st.repo_full}  [{st.member.kind_label}]")
        lines.append(f"  latest tag: {tag}")
        if st.next_tag:
            lines.append(f"  next train tag: {st.next_tag}")
        if st.error and report.offline:
            pass  # already noted globally
        elif st.error:
            lines.append(f"  error: {st.error}")
        if st.prepare_prs:
            for pr in st.prepare_prs:
                lines.append(f"  open PR #{pr.get('number')}: {pr.get('title')} ({pr.get('url')})")
        elif not report.offline and not st.error and st.member.role != "core":
            lines.append("  open prepare PRs: none detected")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
