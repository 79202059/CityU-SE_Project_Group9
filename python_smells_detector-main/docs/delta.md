# pyexamine-delta - change-aware analysis for pull requests

This fork adds a second console script on top of PyExamine 0.3.0.  The
detection logic of the three upstream detectors is **byte-identical** to
upstream: `text` and `json` output are unchanged unless you pass a new
argument (verified on `tests/fixtures/sample_project`: 967 bytes of text and
5366 bytes of JSON, identical to upstream v0.3.0).

```
pyexamine-delta <project> --base <ref> [--head <ref>] [...]
pyexamine-delta calibrate <project> [...]
```

Run it from inside the repository you want to check; both refs are resolved
with `git worktree`, so the working tree is never touched.

## What it adds

| capability | flag | what it answers |
| --- | --- | --- |
| Two-version comparison, four states | `--base` / `--head` | which smells are new, worsened, resolved, unchanged between two commits |
| Stable fingerprints | always on | the same smell keeps one identity even when its line number moves |
| Rename / move matching | `--no-fuzzy`, `--fuzzy-threshold` | a renamed or moved function is not reported as one new smell plus one fixed smell; a completely different name still pairs when the body shape is intact (AST shape is a scoring signal, not part of the exact key) |
| Adaptive thresholds | `pyexamine-delta calibrate` | what "long" and "large" mean *in this project*, not in a library average; moves `LARGE_CLASS_METHODS` as well as the structural `NOM_THRESHOLD` |
| Explainable risk score | `--risk`, `--min-risk` | which of the new findings deserve review first, with the reasons spelled out (metric vs threshold, diff overlap, fan-in, confidence) |
| CI gate | `--fail-on-new`, `--fail-on-worsened`, `--max-new` | fail the build on new findings, not on the whole project's backlog |
| SARIF 2.1.0 | `--format sarif` | GitHub code scanning annotations, inline on the diff |
| PR summary | `--format markdown` | a table for `$GITHUB_STEP_SUMMARY` |

## Quick start

```bash
pip install -e .

# snapshot the baseline on main
pyexamine-delta . --base origin/main --head origin/main --baseline-mode write

# in a pull request: only what the PR introduced, ranked by risk
pyexamine-delta . --base origin/main --format markdown --risk
pyexamine-delta . --base origin/main --format sarif --risk > delta.sarif
pyexamine-delta . --base origin/main --risk --min-risk 40 --fail-on-new medium --max-new 20

# once: learn the project's own thresholds
pyexamine-delta calibrate . --percentile 95 --max-multiplier 2
pyexamine-delta . --base origin/main --config pyexamine-thresholds.yaml
```

Exit codes: `0` clean, `1` gate reached (or the run failed), `2` usage error.

## Two things that bite

1. **`--baseline-mode write` snapshots `--head`, not `--base`.**  To create a
   baseline from `main` you must pass `--base main --head main`, otherwise the
   pull request's own findings end up in the baseline and the gate goes green
   forever.
2. **Changing thresholds invalidates the baseline.**  Severity is a function of
   the thresholds, so after `calibrate` you must rebuild it, or every finding
   that no longer triggers shows up as `RESOLVED`.

## Layout of the added code

| module | role |
| --- | --- |
| `finding.py` | one `Finding` type for the three detectors |
| `fingerprint.py` | four-state classification, exact + fuzzy matching |
| `fuzzy.py` | rename/move matching (symbol + path + line, two thresholds) |
| `baseline.py` | committable baseline file and diffing |
| `metrics.py` | rule id -> measured value + threshold (single source of truth) |
| `risk.py` | 0-100 score from four weighted components |
| `sarif_builder.py` | SARIF 2.1.0 document |
| `calibration.py` | project-adaptive thresholds |
| `rule_registry.py` | 47 stable rule ids (`pyex-<category>-<slug>`) |
| `version_provider.py` | `git worktree` materialisation of base/head |
| `delta.py` | the second CLI |

`docs/rule-mapping.md` lists all 47 rule ids with their legacy `PX-*` numbers;
`docs/rule_ids.json` is the machine-readable version the registry was generated
from.

Tests: `python -m pytest tests -q` -> 457 passed (216 upstream + 241 for the delta engine).
`ruff check src tests` -> clean.

See `docs/ci/` for a GitHub Actions workflow and the four knobs it exposes.
