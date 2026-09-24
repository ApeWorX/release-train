# release-train

CLI to orchestrate coordinated **minor** releases of [`ape`](https://github.com/ApeWorX/ape) (PyPI: `eth-ape`) and official ApeWorX plugins.

**Stage 1 scope:** plan and dry-run pin bumps / release cuts; live GitHub mutations behind `--apply`. This does **not** replace per-repo `publish.yaml` — PyPI publish still fires from each repo on `release: released`.

## Version policy

| Rule | Detail |
|------|--------|
| Track | Plugin `major.minor` tracks ape `major.minor` |
| Patches | Float independently |
| Pin | Plugins depend on `eth-ape>=X.Y.0,<X.(Y+1)` |
| Example | Minor `0.9` → `eth-ape>=0.9.0,<0.10` |

Releases are cut with GitHub Releases and `--generate-notes` (conventional-commit PR titles on squash merge).

Manifest: [`train.yaml`](train.yaml) (org, core, plugin list, policy).

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

All mutating commands default to **dry-run**. Pass `--apply` to execute.

### `prepare` — bump eth-ape pins for a minor

```bash
release-train prepare --minor 0.9
release-train prepare --minor 0.9 --apply   # create branches/PRs via gh (partial in v1)
```

For each plugin: plan a PR that rewrites `eth-ape>=…` to the train pin. Also prints an ape `fallback_version` bump reminder (setuptools_scm).

### `status` — train health snapshot

```bash
release-train status
release-train status --minor 0.9
```

Shows latest release tags and open prepare-related PRs when `gh` is available; degrades gracefully offline.

### `cut` — create GitHub Releases

```bash
release-train cut --target ape --minor 0.9
release-train cut --target plugins --minor 0.9
release-train cut --target all --minor 0.9 --apply
```

Order for `all`: ape first, then plugins. Tag form: `v0.9.0`. Uses `gh release create … --generate-notes`. Per-repo `publish.yaml` handles PyPI.

## Layout

```
train.yaml                 # manifest
src/release_train/
  cli.py                   # cyclopts app
  manifest.py              # load/validate train.yaml
  pins.py                  # eth-ape pin rewrite
  github.py                # thin gh wrappers
  prepare.py / status.py / cut.py
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
