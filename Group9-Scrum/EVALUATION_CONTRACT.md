# Evaluation Contract (frozen)

**Version:** 1.0 · **Frozen:** 2026-11-06 (Sprint 2 review) · **Owner:** M1 ·
**Approvals:** M1, M2, M3, M4, M5, M6 (unanimous at the review)

**Rule:** after this date, the task, data, baselines, metrics, thresholds and environment may not
change. Clarifications that do not alter a metric are allowed and must be logged in §8. Negative
results are reported as findings, not reasons to move the goalposts.

## 1. Research questions

| RQ | Question | Primary metric |
| --- | --- | --- |
| RQ1 | Does change-aware analysis reduce warnings unrelated to the PR? | Irrelevant-warning reduction at fixed recall |
| RQ2 | Does the fingerprint survive line shifts, renames and moves? | Lifecycle-classification accuracy on the mutation corpus; false-NEW rate after pure moves |
| RQ3 | Do project-adaptive thresholds beat fixed defaults? | New-smell precision / F1 with calibrated vs default thresholds |
| RQ4 | Does the tool reduce review effort? | Time on a scripted review task (small user study, n ≥ 6), plus perceived usefulness |

## 2. Task definition

Given a Python repository and a pair `(base, head)`:

1. Run the three detectors on both revisions (or on head + stored baseline).
2. Produce findings with stable identities.
3. Classify each as `NEW`, `WORSENED`, `UNCHANGED`, `RESOLVED`.
4. Emit a risk-ranked report and a gate verdict.

The **reviewer-facing task** is: “identify code smells introduced or worsened by this PR, ignoring
pre-existing debt”. Ground truth is the set of labels for that question, not “all smells in the
repository”.

## 3. Data

### 3.1 Controlled mutation corpus (RQ2)

- 24 commits in one sandbox repository, tagged **`eval-corpus-v1`** (frozen 2026-10-20).
- Composition: 8 introduce, 4 worsen, 6 move/rename (3 same-file, 3 cross-file), 4 resolve,
  2 cosmetic no-ops (blank lines, docstring edits).
- Each commit has expected states in `eval/corpus/manifest.csv` (commit, mutation, file, symbol,
  expected state per focal smell).
- Only the five focal smells are scored: Long Method, Large Class, High Cyclomatic Complexity,
  Duplicate Code, Cyclic Dependency.

### 3.2 Real-world sample (RQ1, RQ3, RQ4)

- **6 Python repositories**, chosen before any measurement, with these criteria: ≥ 5k LOC, ≥ 20
  merged PRs in 2025–2026, permissive licence, tests present, no vendored mega-directories.
- **68 merged pull requests**, stratified by size: 1–5 files (30), 6–20 files (24), > 20 files (14).
- Exclusions: PRs that only bump dependencies or touch generated code.
- Repositories and PR numbers are listed in `eval/dataset.csv` with the selection date.
- **Separation:** the 6 calibration repositories and the 6 evaluation repositories are disjoint at
  the *repository* level; calibration never sees evaluation PR labels.

## 4. Baselines

| ID | Configuration | What it represents |
| --- | --- | --- |
| **A** | Upstream PyExamine 0.3.0 full-project report, unchanged | “The tool as it exists” — reviewer must filter manually |
| **B** | Upstream findings filtered by **changed line numbers** from `git diff` | The obvious cheap fix: “only show warnings on touched lines” |
| **Proposed** | `pyexamine-delta`: exact + fuzzy identity, four states, calibrated thresholds, risk ranking | The project's claim |

All three run on the same commit pair, same interpreter, same thresholds unless the row says
“calibrated”. Baseline B is implemented as a small script committed with the evaluation code so
the comparison is reproducible.

## 5. Metrics (definitions fixed)

- **New-smell precision** = TP / (TP + FP) over findings predicted `NEW` or `WORSENED`.
- **New-smell recall** = TP / (TP + FN) over ground-truth new/worsened smells.
- **F1** = harmonic mean of the two.
- **Lifecycle accuracy** = correctly classified findings / all matched findings on the mutation
  corpus.
- **Irrelevant-warning reduction** = 1 − (median findings shown per PR by the configuration) /
  (median findings in Baseline A for the same PR), computed **at recall ≥ 0.85** for the
  configuration. A configuration that reduces noise by dropping true positives does not count.
- **Move false-NEW reduction** = 1 − (false `NEW` after pure move/rename in Proposed) /
  (false `NEW` after pure move/rename in Baseline B). Only the 6 move/rename commits.
- **Warm-run ratio** = warm incremental time / full analysis time on the frozen 100k-LOC
  benchmark; **warm-run time** in seconds on the agreed environment (ADR-008).
- **Review time** = minutes to complete the scripted review task (find the introduced smell,
  decide gate verdict); median of 3 tasks per participant.

## 6. Success thresholds (decided before running)

| Criterion | Threshold | Consequence if missed |
| --- | --- | --- |
| New-smell recall | ≥ 0.85 | Report actual value; no threshold tuning after seeing results |
| New-smell precision | ≥ 0.80 | Same |
| Irrelevant-warning reduction | ≥ 60% at recall ≥ 0.85 | Report as partial success; discuss cause |
| Move/rename false-NEW reduction vs B | ≥ 80% | Report; the matching limitation goes in the threats section |
| Warm run | ≤ 40% of full, or ≤ 30 s on 100k LOC | Report both numbers; NFR judged on the agreed environment |
| Annotation agreement | Cohen's κ reported; κ ≥ 0.60 expected | If lower, report per-annotator results and analyse disagreements |

## 7. Annotation protocol

1. Two members label independently (M1, M5), blind to each other and to tool output where
   possible (they see the diff, not the predicted state).
2. Labels: `new`, `worsened`, `unchanged`, `resolved`, plus `unclear` (counted as a disagreement).
3. **Adjudication rule (fixed):** a smell is `worsened` if its measured metric crosses the
   effective threshold in head and not in base, or worsens by > 20% while already above threshold.
   A smell inside a moved block is `unchanged` if the AST signature matches after normalisation.
4. Disagreements are adjudicated by M3 only when both labels are defensible under §7.3;
   otherwise the item is excluded and the exclusion is counted.
5. Cohen's κ is computed on the pre-adjudication labels for the 5 focal smells.
6. Labels are stored in `eval/labels.csv`; the labelling sheet is committed (no names, only
   issue/PR ids).

## 8. Environment

| Item | Value |
| --- | --- |
| OS | Windows 11 (development), Ubuntu 24.04 (CI) |
| Python | 3.13 (measurement), 3.10–3.14 (test matrix) |
| CPU / RAM | 8 logical cores / 16 GB (record exact model in the report appendix) |
| Upstream version | `code-quality-analyzer` 0.3.0, commit pinned in `pyproject.toml` |
| Benchmark | frozen 100k-LOC Python corpus, tag `bench-100k-v1` |
| Repetitions | 3 runs; report median and range |
| Cache state | cold vs warm explicitly labelled; cache cleared before cold runs |

## 9. Analysis and reporting rules

1. Report per-state precision/recall/F1 for A, B and Proposed; aggregate per repository and
   overall (macro-average, each PR weighted equally).
2. Report the confidence interval (bootstrap, 1,000 resamples) for the headline F1.
3. Report the number of PRs and findings behind every number.
4. Any deviation from this contract (e.g. a repository dropped) must be listed with the reason
   and the date, before the results are computed.
5. A negative result (calibration not better, warm run above target, κ below 0.60) is reported in
   the evaluation section and the conclusion, not removed.

## 10. Status (2026-11-26)

The table records the team's status at the time. Verifying its completion counts requires the original PR manifest, independent labels and tagged corpus. The eight bundled pairs and the supplementary controlled cases can be replayed using the [evaluation guide](../python_smells_detector-main/docs/evaluation-baselines.md).

| Item | Status |
| --- | --- |
| Contract | Frozen since 2026-11-06; no metric changed |
| Mutation corpus | Frozen, `eval-corpus-v1`; replay passes |
| Evaluation repositories/PRs | 6 repos, 68 PRs listed and frozen |
| Annotation | 42/68 labelled by Nov 16; round 2 (26) due Nov 27 |
| Baseline A/B runs | Scheduled Nov 30 (time-boxed to 3 repos/day) |
| Metrics + report | Scheduled Dec 1–2 |
| Acceptance | Sprint review Dec 4 |

## 11. Change log

| Date | Change | Metric impact |
| --- | --- | --- |
| 2026-10-19 | WORSENED band set to “crosses threshold, or > 20% while above” | Definition chosen **before** labelling; not changed later |
| 2026-11-06 | Contract frozen; thresholds in §6 locked | — |
| 2026-11-06 | Risk score weights documented as design choice, not tuned on labels | None (ranking only) |

No change after 2026-11-06 has altered a metric, threshold, baseline or dataset membership.
