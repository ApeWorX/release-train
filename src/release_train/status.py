"""Status logic: latest tags, phases, and GitHub milestone progress."""

from __future__ import annotations

from dataclasses import dataclass, field

from release_train.github import (
    GhError,
    find_milestone,
    gh_available,
    latest_semver_tag,
    list_open_prs_on_milestone,
)
from release_train.manifest import Manifest, RepoRef
from release_train.milestones import (
    LABEL_COMPAT,
    LABEL_PINS,
    MilestonePRCounts,
    milestone_counts_from_payload,
    milestone_title,
)
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
    milestone_counts: MilestonePRCounts | None = None
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
    milestone: str | None = None
    network_required_note: str | None = None


def gather_status(
    manifest: Manifest,
    minor: MinorVersion | None = None,
    *,
    skip_network: bool = False,
) -> StatusReport:
    online = gh_available() and not skip_network
    items: list[RepoStatus] = []
    ms_title = milestone_title(minor) if minor is not None else None
    network_note: str | None = None

    if not online:
        network_note = (
            "Network required for milestone status "
            f"({ms_title or 'release-train/{minor}'}). "
            "Re-run without --offline when `gh` is authenticated."
        )

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
            # Milestone progress for plugins + extras (not core ape)
            if ms_title is not None and member.role != "core":
                ms = find_milestone(full, ms_title)
                prs = list_open_prs_on_milestone(full, ms_title) if ms else []
                # If milestone absent, still allow empty counts (found=False)
                if ms is None:
                    # Also try listing in case milestone exists but find failed oddly
                    prs = list_open_prs_on_milestone(full, ms_title)
                st.milestone_counts = milestone_counts_from_payload(
                    milestone=ms, open_prs=prs, title=ms_title
                )
                st.prepare_prs = prs
            elif ms_title is None and member.role != "core":
                st.error = "pass --minor to query milestone progress"
        except GhError as exc:
            st.error = str(exc)
        items.append(st)

    return StatusReport(
        items=items,
        minor=minor,
        offline=not online,
        milestone=ms_title,
        network_required_note=network_note,
    )


def format_status_report(report: StatusReport) -> str:
    lines: list[str] = []
    header = "=== release-train status"
    if report.minor:
        header += f" (minor {report.minor.display()})"
    header += " ==="
    lines.append(header)
    if report.offline:
        lines.append("(offline / no gh — listing train members only)")
        if report.network_required_note:
            lines.append(report.network_required_note)
    elif report.milestone:
        lines.append(
            f"Milestone: `{report.milestone}`  |  labels: `{LABEL_PINS}` / `{LABEL_COMPAT}`"
        )
        lines.append("State lives on GitHub (no local train-status files).")
    else:
        lines.append("Tip: pass --minor X.Y to query per-repo milestone progress.")
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
            lines.append(f"  note: {st.error}")
        counts = st.milestone_counts
        if counts is not None:
            due = f" / due {counts.due_on}" if counts.due_on else ""
            presence = "present" if counts.found else "absent"
            lines.append(f"  milestone: {counts.milestone_title or report.milestone} ({presence})")
            lines.append(
                f"  progress: pins open {counts.pins_open} / compat open {counts.compat_open}{due}"
            )
            if counts.other_open:
                lines.append(f"  other open on milestone: {counts.other_open}")
            for pr in st.prepare_prs:
                labels = pr.get("labels") or []
                label_names = []
                for lab in labels:
                    if isinstance(lab, dict) and lab.get("name"):
                        label_names.append(str(lab["name"]))
                    elif isinstance(lab, str):
                        label_names.append(lab)
                lab_s = ",".join(label_names) if label_names else "—"
                lines.append(
                    f"  open PR #{pr.get('number')}: {pr.get('title')} [{lab_s}] ({pr.get('url')})"
                )
        elif (
            not report.offline
            and not st.error
            and st.member.role != "core"
            and report.milestone is None
        ):
            lines.append("  milestone progress: (need --minor)")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
