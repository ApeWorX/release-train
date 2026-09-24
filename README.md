# release-train

CLI to orchestrate coordinated **minor** releases of [`ape`](https://github.com/ApeWorX/ape) (PyPI: `eth-ape`) and official ApeWorX plugins (plus optional personal / out-of-org **extra** members).

**Stage 1 scope:** plan and dry-run pin bumps / release cuts; live GitHub mutations behind `--apply`. This does **not** replace per-repo `publish.yaml` — PyPI publish still fires from each repo on `release: released`.

## Version policy

| Rule | Detail |
|------|--------|
| Track | Plugin `major.minor` tracks ape `major.minor` |
| Patches | Float independently |
| Pin (stable) | Plugins depend on `eth-ape>=X.Y.0,<X.(Y+1)` |
| Pin (pre) | If core ape cut is `vX.Y.0a0` / `b0` / `rc0`, pins use `>=X.Y.0a0,<X.(Y+1)` (same channel) |
| Example | Minor `0.9` → `eth-ape>=0.9.0,<0.10` |
| Tags | Per-repo: latest `v0.8.3a2` → next `v0.9.0a0` (label kept, counter→0); stable `v0.8.12` → `v0.9.0` |

Releases are cut with GitHub Releases and `--generate-notes` (conventional-commit PR titles on squash merge).

Manifest: [`train.yaml`](train.yaml) (org, core, plugins, optional `extra`, policy).

## Train phases (minor / breaking)

A coordinated minor follows this lifecycle:

1. **prepare-pins** — open/plan PRs that only bump `eth-ape` pins (may open before ape is cut; often draft until ape ships)
2. **cut-ape** — GitHub Release for ape at the computed train tag
3. **compat** — gated window: land breaking-API fix PRs **after** ape `X.Y` is on PyPI (`status` / `plan` show this; `prepare --phase compat` may come later)
4. **cut-plugins** — release official plugins **and** extras only after pins are merged (+ compat as needed)

Use `release-train plan --minor 0.9` to print the full sequence without mutating anything.

## Personal / out-of-org plugins (`extra`)

Bare plugin names use the default `org`. Members outside the org go under `extra:` and are treated like plugins for prepare / cut / status, but labeled **extra/personal** in reports.

```yaml
org: ApeWorX
plugins:
  - ape-etherscan          # → ApeWorX/ape-etherscan
extra:
  - someuser/ape-example   # owner/repo string
  # or structured:
  # - owner: anotheruser
  #   repo: ape-other
```

Do not invent real personal plugin names in the shared manifest; keep `extra: []` until you add your own.

## Install

```bash
# one-shot tool (recommended)
uv tool install -e /path/to/release-train

# or editable for development
cd /path/to/release-train
uv pip install -e ".[dev]"   # or: pip install -e ".[dev]"
# dependency-groups (uv):
uv sync --group dev
```

Requires Python 3.10+, and the [`gh`](https://cli.github.com/) CLI authenticated for live `--apply` / `status` network calls.

## Commands

All mutating commands default to a **plan** (`PLAN (no changes)`). Pass `--apply` to execute. There are no interactive y/n prompts (CI-safe).

### `plan` — full multi-phase sequence

```bash
release-train plan --minor 0.9
release-train plan --minor 0.9 --offline
```

Prints prepare-pins → cut-ape → compat → cut-plugins for the minor. Never mutates.

### `prepare` — bump eth-ape pins for a minor

```bash
release-train prepare --minor 0.9
release-train prepare --minor 0.9 --apply   # create branches/PRs via gh (partial in v1)
```

For each official plugin **and** extra: plan a PR that rewrites `eth-ape>=…` to the train pin (channel follows ape’s computed tag). Also prints an ape `fallback_version` bump reminder (setuptools_scm).

### `status` — train health + phases

```bash
release-train status
release-train status --minor 0.9
```

Shows the four phases, latest semver-ish tags, computed next tags, and open prepare-related PRs when `gh` is available; degrades gracefully offline.

### `cut` — create GitHub Releases

```bash
release-train cut --target ape --minor 0.9
release-train cut --target plugins --minor 0.9
release-train cut --target all --minor 0.9 --apply
```

Order for `all`: ape first, then official plugins, then extras. Each repo gets its **own** computed tag (not a blanket `v0.9.0`). Uses `gh release create … --generate-notes`. Per-repo `publish.yaml` handles PyPI.

**Warning:** `cut --target plugins` assumes prepare-pins are merged and any **compat** PRs that must land after ape is on PyPI are already merged.

## Layout

```
train.yaml                 # manifest (org, core, plugins, extra, policy)
src/release_train/
  cli.py                   # cyclopts app
  manifest.py              # load/validate train.yaml
  pins.py                  # eth-ape pin rewrite
  tags.py                  # semver tags + release channel
  github.py                # thin gh wrappers
  plan.py / prepare.py / status.py / cut.py
```

## Development

```bash
uv run pytest
uv run ruff check src tests
uv run ruff format src tests
python -m release_train --help
```

## TODOs (apply-mode)

- Full fork/branch/commit/PR flow for `prepare --apply` (v1 prints exact `gh` commands + rewrites pins locally when a checkout path is given)
- Detect prepare PR titles more robustly in `status`
- Optional: `prepare --phase compat` and listing known open compat PR URLs
