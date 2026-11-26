# ADR-011: Usability through a single-command CLI and PR-native outputs

- **Status:** Accepted (draft to be committed to the fork's `docs/adr/`)
- **Date:** 2026-11-16
- **NFR:** Usability — a new user can install, run a comparison and interpret the result within
  5 minutes.
- **Related:** `delta.py`, `docs/delta.md`, `docs/ci/README.md`, `sarif_builder.py`

## Context

The target user is a reviewer inside a pull-request workflow, not a person looking for a dashboard.
The measurable usability target is time-to-first-result: clone, install, run, understand. Every
extra surface (server, UI, login, plugin) adds setup and testing cost that a 12-week project cannot
afford, and none of it is used at the moment the reviewer makes a decision.

## Decision

1. **One command for the core job:**
   `pyexamine-delta <repo> --base <ref> [--head <ref>]` — no config required, sensible defaults,
   two optional sub-flows (`calibrate`, baseline mode).
2. **Four outputs, one engine:** text (terminal), JSON (machines), Markdown (PR comment /
   `$GITHUB_STEP_SUMMARY`), SARIF 2.1.0 (code scanning annotations). Output format never changes
   the classification.
3. **Explainability as a feature:** risk-ranked findings print 3–5 concrete reasons (introduced by
   this PR, measured vs threshold, overlap %, caller count). A number without a reason is not
   shippable.
4. **Gate is explicit and copy-pasteable:** three documented knobs (`--fail-on-new`,
   `--min-risk`, `--max-new`) with recommended defaults and a working GitHub Actions file.
5. **No web UI / IDE plugin / GitHub App** in this release. Rejected as non-goals; the CLI is the
   product surface.

Defaults were chosen from measurements, not taste: `--min-risk 40` corresponds to roughly the top
10% of the risk distribution (p90 34–40 across three corpora); the `triage` level policy demotes
structural `high`, which would otherwise block every PR (structural findings 53–72% of volume,
46–57% of them `high`).

## Alternatives considered

- **Local web dashboard.** Rejected: adds server, auth, state and screenshot-driven tests; the
  reviewer still has to copy the result into the PR.
- **IDE plugin.** Rejected: one plugin per IDE, none of them used by the CI gate; out of scope.
- **GitHub App.** Rejected: App installation/permissions would consume a sprint for the same
  annotations SARIF already provides.
- **YAML-first configuration.** Rejected for the quick start: defaults must work; calibration
  produces an *optional* file a human commits deliberately.

## Consequences

- **Positive:** time-to-first-result is a single `pip install -e .` plus one command; outputs meet
  users where they already are (terminal, PR comment, code scanning); the same engine is tested by
  every format.
- **Neutral:** explanation text must be maintained; a misleading reason is a bug.
- **Negative:** no graphical exploration of trends; users who expect a GUI are out of scope. The
  Markdown/SARIF outputs mitigate this inside the PR.

## Verification

- Quick-start walkthrough executed on a clean clone by a member who did not write the docs; target
  ≤ 5 minutes to a first diff.
- Demo script ≤ 10 minutes: baseline → PR gate fail → fix → pass → SARIF annotation.
- Gate defaults documented and reproduced locally with the exact CI command
  (`docs/ci/README.md` §5).