# Product Backlog — PyExamine-Delta

- **Team:** Group 9 (6 students: M1–M6, placeholders — replace with real names/IDs)
- **Product:** `pyexamine-delta`, a change-aware code smell detector for Python pull requests,
  built as a fork of PyExamine 0.3.0 (`code-quality-analyzer`)
- **Baseline snapshot:** 2026-11-26 (Week 12)
- **Scope:** 5 epics, 19 user stories, **72 story points**; 1 SP ≈ 3–4 person-hours
- **Estimation:** planning poker, Fibonacci scale (1, 2, 3, 5, 8)
- **Priority:** MoSCoW (`M` must, `S` should, `C` could, `W` won't this release)

## 1. Personas

| Persona | Who | What they care about |
| --- | --- | --- |
| **Priya** — reviewer / maintainer | Reviews 10–30 Python PRs a week in a mid-size repo | Seeing only the debt *this PR* introduces; actionable, explainable warnings |
| **Devon** — feature developer | Opens PRs, runs checks locally before pushing | Fast feedback in pre-commit / CI, no false alarms from legacy code |
| **Sam** — CI owner | Owns GitHub Actions and merge policy | Machine-readable output (SARIF/JSON), deterministic exit codes, a budget that does not block every PR |

## 2. Epics

| Epic | Outcome | Stories | SP |
| --- | --- | --- | --- |
| **E1 — Version-aware analysis core** | Analyse base and head revisions and diff their findings | US-01, US-03, US-04, US-05 | 13 |
| **E2 — Smell identity & matching** | One stable identity per smell across line shifts, renames and moves | US-02, US-08, US-09 | 15 |
| **E3 — Context adaptation & prioritisation** | Project-specific thresholds and explainable risk ranking | US-10, US-11, US-13 | 13 |
| **E4 — Reporting & PR gate** | Text/Markdown/SARIF reports and configurable CI gate | US-14, US-15, US-16, US-17 | 12 |
| **E5 — Quality attributes & evidence** | Performance cache, upstream compatibility, frozen evaluation, process evidence | US-06, US-07, US-12, US-18, US-19 | 19 |

## 3. Backlog overview

| ID | Story (short) | Epic | Pri | SP | Sprint | Status |
| --- | --- | --- | --- | --- | --- | --- |
| US-01 | Two-version (base/head) analysis | E1 | M | 5 | 1 | Done |
| US-02 | Stable exact fingerprint, line-shift invariant | E2 | M | 5 | 1 | Done |
| US-03 | Four-state lifecycle classification | E1 | M | 3 | 1 | Done |
| US-04 | Safe git worktree version provider | E1 | M | 2 | 1 | Done |
| US-05 | Committable baseline snapshot and diff mode | E1 | M | 3 | 1 | Done |
| US-06 | Byte-identical upstream output compatibility | E5 | S | 2 | 1 | Done |
| US-07 | Repository, board and process scaffolding | E5 | M | 1 | 1 | Done |
| US-08 | Normalised AST structure signature | E2 | M | 5 | 2 | Done |
| US-09 | Rename / move matching (fuzzy) | E2 | M | 5 | 2 | Done |
| US-10 | WORSENED state from metric deltas | E3 | M | 3 | 2 | Done |
| US-11 | Project-adaptive threshold calibration | E3 | S | 5 | 2 | Done |
| US-12 | Controlled mutation corpus (evaluation input) | E5 | M | 3 | 2 | Done |
| US-13 | Explainable 0–100 risk score | E3 | S | 5 | 3 | Done |
| US-14 | SARIF 2.1.0 output with 47 stable rule ids | E4 | M | 5 | 3 | Done |
| US-15 | Text and Markdown PR summary | E4 | M | 2 | 3 | Done |
| US-16 | Configurable quality gate (severity, budget, risk) | E4 | M | 3 | 3 | Done |
| US-17 | GitHub Actions integration | E4 | M | 2 | 3 | Done |
| US-18 | Content-addressed incremental analysis cache | E5 | M | 5 | 3 | Done |
| US-19 | Frozen evaluation against baselines A/B | E5 | M | 8 | 3 | In progress (Week 13) |
|  | **Total** |  |  | **72** |  | 64 SP accepted |

## 4. Definition of Ready

A story can enter a sprint only when:

1. It has a persona, a goal and a stated benefit.
2. Acceptance criteria are written as concrete scenarios (Given/When/Then) with observable output.
3. The impacted modules and the test file to extend are named.
4. It fits in one sprint (≤ 8 SP) and does not depend on an unfinished story.
5. Non-goals are clear enough that a reviewer can reject scope creep.
6. For NFR stories, the architectural option and the measurement protocol are named.

## 5. User stories with acceptance criteria

### US-01 — Two-version analysis (5 SP, Sprint 1, E1)

> **As** Priya, **I want** the tool to analyse the base and head revision of a pull request
> **so that** the report describes the change, not the repository's whole backlog.

- **FR:** FR1 · **Modules:** `version_provider.py`, `delta.py`, `finding.py`
- **AC-1:** Given a repo whose `main` contains a Long Method, when I run
  `pyexamine-delta . --base main --head HEAD` on a PR that touches another file, then that smell
  is reported as `UNCHANGED`, never `NEW`.
- **AC-2:** Both revisions are materialised with `git worktree add --detach`; `git status
  --porcelain` before and after the run is identical.
- **AC-3:** An unknown base ref exits `2` with a message naming the ref and leaves no partial
  output.
- **AC-4:** The text report prints one count line per state and each finding exactly once.
- **Evidence:** PR #28, `tests/test_delta.py`, `tests/test_delta_cli.py`

### US-02 — Stable exact fingerprint (5 SP, Sprint 1, E2)

> **As** Devon, **I want** a smell to keep the same identity when unrelated lines move
> **so that** I am not asked to fix a smell that I did not touch.

- **FR:** FR2, FR4 · **Modules:** `fingerprint.py`, `finding.py`
- **AC-1:** Given a function with a Long Method smell, when I insert 20 blank lines above it,
  then the finding is `UNCHANGED` and its fingerprint is byte-identical.
- **AC-2:** The fingerprint is composed of rule id + normalised relative path + qualified symbol
  + normalised AST signature; it never contains a line number.
- **AC-3:** Two runs on identical sources produce byte-identical fingerprints (determinism).
- **AC-4:** Renaming the *file* alone does not produce one `NEW` plus one `RESOLVED`.
- **Evidence:** PR #29, `tests/test_fingerprint.py`

### US-03 — Four-state lifecycle classification (3 SP, Sprint 1, E1)

> **As** Priya, **I want** every finding labelled `NEW`, `WORSENED`, `UNCHANGED` or `RESOLVED`
> **so that** I can tell new debt from pre-existing debt at a glance.

- **FR:** FR3 · **Modules:** `fingerprint.py`, `delta.py`
- **AC-1:** A fingerprint absent in base and present in head is `NEW`.
- **AC-2:** A fingerprint present in base and absent in head is `RESOLVED`.
- **AC-3:** A matched fingerprint whose measured value crosses the threshold in the PR is
  `WORSENED`; otherwise `UNCHANGED`.
- **AC-4:** The four counts sum to the number of head findings plus resolved findings; no
  finding carries two states.
- **AC-5:** `--format json` exposes the state field for every finding.
- **Evidence:** PR #30, `tests/test_delta.py::test_states`

### US-04 — Safe worktree version provider (2 SP, Sprint 1, E1)

> **As** Sam, **I want** revision extraction to be side-effect free
> **so that** running the gate can never disturb a developer's working copy.

- **NFR:** Reliability · **Modules:** `version_provider.py`
- **AC-1:** Base and head are checked out under a temporary directory; no branch is created in
  the user's repository.
- **AC-2:** Temporary worktrees are removed on success, on failure and on interrupt.
- **AC-3:** A dirty working tree and staged changes are ignored, not modified.
- **AC-4:** Errors (missing ref, not a git repo) exit `2` with an actionable message.
- **Evidence:** PR #27, `tests/test_delta.py::test_worktree_cleanup`

### US-05 — Committable baseline snapshot (3 SP, Sprint 1, E1)

> **As** Sam, **I want** to snapshot the main branch's findings into a committed file
> **so that** CI can diff a PR against a baseline without fetching full history.

- **FR:** FR1, supports FR8 · **Modules:** `baseline.py`, `delta.py`
- **AC-1:** `--baseline-mode write` writes `.pyexamine-baseline.json` with relative paths and
  rule ids, sorted deterministically.
- **AC-2:** `--baseline-mode diff` reproduces the same states as a two-worktree comparison on
  the same content.
- **AC-3:** The file is small enough to commit and diff (one line per finding, no AST bodies).
- **AC-4:** Documentation states the two operational traps: `write` snapshots `--head`, and a
  threshold change invalidates the baseline (see `docs/delta.md`).
- **Evidence:** PR #31, `tests/test_baseline.py`, `docs/ci/README.md`

### US-06 — Upstream output compatibility (2 SP, Sprint 1, E5)

> **As** an upstream maintainer, **I want** the fork to keep PyExamine's outputs unchanged
> **so that** existing users can adopt the fork without retraining or rewriting scripts.

- **NFR:** Compatibility / reliability · **Modules:** `main.py`, `delta.py`
- **AC-1:** On `tests/fixtures/sample_project`, default text output is 967 bytes and JSON is
  5366 bytes, byte-identical to upstream v0.3.0.
- **AC-2:** All 216 upstream tests pass unchanged.
- **AC-3:** The `analyze_code_quality` entry point and its exit codes are untouched.
- **AC-4:** A regression test fails if either output drifts.
- **Evidence:** PR #32, `tests/test_e2e.py`, `tests/test_main.py`

### US-07 — Process scaffolding (1 SP, Sprint 1, E5)

> **As** the team, **I want** a repository with milestones, labels, templates and a board
> **so that** every week's activity is visible as evidence in GitHub.

- **Mechanism:** milestone per sprint, labels per epic/type, issue template with AC, PR
  template with traceability, `docs/meetings/` weekly note, ADR folder, risk register.
- **AC-1:** Every story maps to exactly one issue and one closing PR.
- **AC-2:** Each PR body contains `Closes #<issue>` and the test command used.
- **AC-3:** A weekly note is committed within 48 h of the standing meeting.
- **Evidence:** PR #26, `GITHUB_WORKFLOW.md`, `meetings/`

### US-08 — Normalised AST signature (5 SP, Sprint 2, E2)

> **As** Devon, **I want** cosmetic edits (rename a variable, rewrite a docstring) to keep a
> smell's identity **so that** review noise does not come from formatting work.

- **FR:** FR2, FR4 · **Modules:** `fingerprint.py`
- **AC-1:** The signature ignores identifier names, docstrings, literal values, comments and
  formatting; it keeps node types and structural shape.
- **AC-2:** Renaming a local variable or editing a docstring produces no `NEW`/`RESOLVED` pair.
- **AC-3:** The signature is deterministic across Python 3.10–3.14 (`ast.dump(...,
  include_attributes=False)` normalised and hashed).
- **AC-4:** Golden signatures are pinned in tests for the three focal code smells.
- **Evidence:** PR #33, `tests/test_fingerprint.py::test_ast_signature`

### US-09 — Rename / move matching (5 SP, Sprint 2, E2)

> **As** Priya, **I want** a renamed or moved function to be recognised as the same smell
> **so that** refactoring PRs do not look like they introduced and fixed the same problem.

- **FR:** FR4 · **Modules:** `fuzzy.py`, `fingerprint.py`
- **AC-1:** A function renamed in place is matched when the combined score ≥ 0.62 (default),
  using symbol similarity, path similarity, AST similarity, line proximity and metric range.
- **AC-2:** A `git mv` to another file in the same repo yields zero `NEW` and zero `RESOLVED`.
- **AC-3:** `--no-fuzzy` disables the second pass; `--fuzzy-threshold` changes the acceptance
  score.
- **AC-4:** A different function that merely sits near the old line is not matched (precision
  guard in tests).
- **Evidence:** PR #34, `tests/test_fuzzy.py`

### US-10 — WORSENED from metric deltas (3 SP, Sprint 2, E3)

> **As** Priya, **I want** a smell that already existed but got worse to be called `WORSENED`
> **so that** a PR that doubles a method's length is not hidden among unchanged debt.

- **FR:** FR3 · **Modules:** `metrics.py`, `fingerprint.py`
- **AC-1:** A Long Method that grows from 50 to 82 lines with a 45-line threshold is
  `WORSENED`, with both values printed.
- **AC-2:** A matched finding whose metric does not worsen remains `UNCHANGED`.
- **AC-3:** `--no-worsen` downgrades matched findings to `UNCHANGED` (escape hatch for noisy
  metrics).
- **AC-4:** Metric extraction is a single source of truth shared by risk scoring and reporting.
- **Evidence:** PR #35, `tests/test_worsened.py`

### US-11 — Threshold calibration (5 SP, Sprint 2, E3)

> **As** Sam, **I want** thresholds derived from this project's own metric distribution
> **so that** "long" and "large" mean something in a 3k-line tool and in a 300k-line service.

- **FR:** FR5 · **Modules:** `calibration.py`, `delta.py`
- **AC-1:** `pyexamine-delta calibrate . --percentile 95 --max-multiplier 2` emits a YAML file
  covering method length, methods per class, cyclomatic complexity, module fan-out and module
  LOC.
- **AC-2:** Effective threshold = `max(research floor, project percentile)`, capped at
  `floor × max-multiplier`, so tiny projects cannot produce absurd thresholds.
- **AC-3:** Calibration never edits the active gate silently; a human commits the YAML.
- **AC-4:** With `--format text` the recommended values and their inputs are printed for review.
- **Evidence:** PR #36, `tests/test_calibration.py`

### US-12 — Controlled mutation corpus (3 SP, Sprint 2, E5)

> **As** the evaluation owner, **I want** synthetic commits with known expected states
> **so that** recall and precision are measured against truth, not against intuition.

- **Mechanism:** 24 commits in a sandbox repository — 8 introduce, 4 worsen, 6 move/rename,
  4 resolve, 2 cosmetic no-ops; each has expected states per focal smell.
- **AC-1:** `eval/corpus/manifest.csv` lists commit, mutation type, file, symbol, expected
  state.
- **AC-2:** The corpus is tagged `eval-corpus-v1` and frozen before matching work starts.
- **AC-3:** A script replays every commit and emits predicted vs expected states.
- **Evidence:** PR #37, `EVALUATION_CONTRACT.md`

### US-13 — Explainable risk score (5 SP, Sprint 3, E3)

> **As** Priya, **I want** new findings ranked 0–100 with reasons
> **so that** I review the riskiest 10% first instead of a flat "high/medium/low" list.

- **FR:** FR6 · **Modules:** `risk.py`, `delta.py`
- **AC-1:** Score = 0.35 × threshold excess + 0.25 × changed-line overlap + 0.20 × dependency
  centrality + 0.20 × detection confidence, clamped to 0–100.
- **AC-2:** Every scored finding prints 3–5 reasons (introduced by this PR, measured vs
  threshold value, overlap %, caller count).
- **AC-3:** `--min-risk 40` excludes lower-scored findings from the gate and implies `--risk`.
- **AC-4:** Ordering is deterministic for identical input.
- **Evidence:** PR #38, `tests/test_risk.py`

### US-14 — SARIF 2.1.0 output (5 SP, Sprint 3, E4)

> **As** Sam, **I want** SARIF so GitHub code scanning can annotate the diff inline
> **so that** reviewers see the warning where the code is, not in a separate log.

- **FR:** FR7 · **Modules:** `sarif_builder.py`, `rule_registry.py`
- **AC-1:** Output validates as SARIF 2.1.0 and uses `pyex-<category>-<slug>` rule ids (47
  descriptors).
- **AC-2:** `--all-rules` emits all descriptors; otherwise only triggered rules appear.
- **AC-3:** `--level-policy triage` demotes structural `high` to `warning` (justified: structural
  findings are 53–72% of volume, 46–57% of them high).
- **AC-4:** `--include-unchanged` adds historical findings demoted one level.
- **Evidence:** PR #39, `tests/test_sarif.py`, `docs/rule-mapping.md`

### US-15 — Text and Markdown PR summary (2 SP, Sprint 3, E4)

> **As** Devon, **I want** a short Markdown table I can paste into a PR
> **so that** the team sees the new findings without opening CI logs.

- **FR:** FR7 · **Modules:** `delta.py`
- **AC-1:** `--format markdown` prints a table (state, rule, symbol, location, severity, risk).
- **AC-2:** Tables truncate after `--markdown-limit` rows (default 20) with a "+N more" row.
- **AC-3:** Output is `$GITHUB_STEP_SUMMARY`-safe (no ANSI escapes) and renders on GitHub.
- **Evidence:** PR #40, `tests/test_markdown.py`

### US-16 — Configurable quality gate (3 SP, Sprint 3, E4)

> **As** Sam, **I want** to fail the build on new high-severity findings or a count budget
> **so that** the gate reflects the team's policy instead of the repo's history.

- **FR:** FR8 · **Modules:** `delta.py`, `risk.py`
- **AC-1:** `--fail-on-new medium` exits `1` when any `NEW` finding is medium or worse.
- **AC-2:** `--max-new 20` exits `1` when more than 20 `NEW` findings are reported, regardless
  of severity.
- **AC-3:** Severity is evaluated before the budget; when both fire, the severity message is
  printed.
- **AC-4:** `--fail-on-worsened` counts `WORSENED` findings; without it they never fail the
  build. Exit codes: `0` clean, `1` gate, `2` usage.
- **Evidence:** PR #41, `tests/test_delta_cli.py`

### US-17 — GitHub Actions integration (2 SP, Sprint 3, E4)

> **As** Sam, **I want** a copy-paste workflow with a documented baseline step
> **so that** the gate runs on every PR without us building a GitHub App.

- **FR:** FR8 · **Artifacts:** `docs/ci/github-actions.yml`, `docs/ci/README.md`
- **AC-1:** Workflow runs on `pull_request`, checks out with `fetch-depth: 0`, runs the gate,
  writes a Markdown summary and optionally uploads SARIF.
- **AC-2:** The three knobs (`PYEX_FAIL_ON`, `PYEX_MIN_RISK`, `PYEX_BUDGET`) are environment
  variables at the top of the file.
- **AC-3:** Limitations are documented: private repos need GHAS for code scanning; baseline must
  be rebuilt after threshold changes.
- **Evidence:** PR #42, `docs/ci/`

### US-18 — Incremental analysis cache (5 SP, Sprint 3, E5)

> **As** Sam, **I want** repeated runs on unchanged sources to skip re-parsing
> **so that** the gate fits the performance budget on a 100k-LOC service.

- **NFR:** Performance · **Modules:** `cache.py`, `delta.py` · **ADR:** ADR-008
- **AC-1:** A tree is keyed by the sorted `(relative path, sha256)` manifest plus a digest of
  effective thresholds and the tool version.
- **AC-2:** A cache hit returns exactly what a cold run would have produced (tested on the
  sample project), with paths re-rooted to the current worktree.
- **AC-3:** Cache lives in `.pyexamine-cache/` (gitignored), overridable with `--cache-dir`,
  bypassable with `--no-cache`.
- **AC-4:** The measurement protocol in ADR-008 is executed on the frozen benchmark; warm time
  is reported against ≤ 40% of full run or ≤ 30 s.
- **Evidence:** PR #43, `tests/test_cache.py`, ADR-008

### US-19 — Frozen evaluation against baselines (8 SP, Sprint 3, E5)

> **As** the team, **I want** an evaluation executed against a frozen contract
> **so that** the reported precision/recall and noise reduction are defensible.

- **Contract:** `EVALUATION_CONTRACT.md` (frozen 2026-11-06)
- **AC-1:** Forecasts are produced for three configurations: Baseline A (upstream full report),
  Baseline B (naive git-diff line filter), Proposed (fingerprints + fuzzy + calibration).
- **AC-2:** Report per-state precision/recall/F1, irrelevant-warning reduction, false-new
  reduction after pure moves, and runtime (full vs incremental).
- **AC-3:** Two annotators label a stratified sample; Cohen's κ is reported.
- **AC-4:** Negative results are reported without changing the metric definitions.
- **Evidence:** PR #44, evaluation report section, `data/` artefacts

## 6. Non-functional requirements and architecture options

The project targets **four** NFRs (6-person team requires at least two). Each is addressed by
an explicit architectural design option with a rationale; ADRs live in `adr/` and in the fork's
`docs/adr/`.

| NFR | Target | Architectural option | Rationale (why this option) | ADR |
| --- | --- | --- | --- | --- |
| **Performance** | Incremental run ≤ 40% of full analysis, or ≤ 30 s on the agreed 100k-LOC benchmark | Content-addressed whole-tree analysis memo (manifest of file hashes + threshold/version digest) | PRs touch few files but cross-file smells accumulate state, so per-file reuse would silently change results; whole-tree memo is correct by construction and makes repeated gate runs O(hashing) | ADR-008 (committed) |
| **Reliability** | New-smell F1 ≥ 0.85 on the frozen dataset; no false `NEW` after cosmetic moves | Two-stage identity: exact fingerprint (rule + path + symbol + AST) then scored fuzzy matching with an explicit acceptance threshold; frozen regression corpus | Line-based diff is provably unstable under insertions/moves; staged matching degrades gracefully and keeps precision auditable instead of hiding heuristics in the detector | ADR-009 (draft) |
| **Extensibility** | Add a detector without touching the comparison engine | Detector Adapter + unified `Finding` model + stable rule registry (`pyex-<category>-<slug>`, 47 ids) | The fork must inherit upstream detectors without forking their logic; a normalised finding boundary keeps the delta engine detector-agnostic | ADR-010 (draft) |
| **Usability** | New user installs, runs and interprets a comparison within 5 minutes | Single-command CLI, four output formats (text/JSON/Markdown/SARIF), explainable risk reasons, quick-start docs; explicitly no web UI | The tool is used inside an existing PR workflow; a CLI plus PR-native output removes setup cost, while a UI would add a second surface to secure and test | ADR-011 (draft) |

## 7. Non-goals (Won't, this release)

- Re-implementing PyExamine's detectors or changing upstream detection logic.
- A hosted web platform, IDE plugin or GitHub App.
- Automatic code modification or auto-fix.
- Training large ML models; runtime-only defect detection.
- Full dynamic call-graph resolution; cross-repository smell matching.
- Covering all 47 rules with tuned thresholds — five focal smells are tuned, the rest reuse
  upstream defaults.

## 8. Release plan

| Release | Sprint | Content | Exit criterion |
| --- | --- | --- | --- |
| `0.4.0-delta` (alpha) | S1 | Two-version diff, exact fingerprints, four states, baseline | Demo distinguishes new / unchanged / resolved on the fixture; upstream tests green |
| `0.5.0-delta` (beta) | S2 | AST signatures, fuzzy matching, calibration, WORSENED | Pure move yields no false NEW; calibrated YAML usable |
| `1.0.0` | S3 | Risk, SARIF, Markdown, gate, Actions, cache, evaluation | Gate blocks an injected Long Method at the right line; frozen evaluation reported |