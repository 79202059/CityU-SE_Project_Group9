# Requirement → Result Traceability

This matrix is the “trace requirement to result” evidence: every story has an issue, a merged
pull request, code, tests and a sprint. Issue/PR numbers are the planned numbering used in this
package — **reconcile them with the real GitHub numbers** before submission; the mapping is
one-to-one, so a find-and-replace is enough.

## 1. Story-level matrix

| Story | Requirement | Sprint | Issue | PR | Modules | Key tests | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| US-01 | FR1 | 1 | #3 | #28 | `delta.py`, `finding.py`, `version_provider.py` | `test_delta.py`, `test_delta_cli.py`, `test_e2e.py` | Done |
| US-02 | FR2, FR4 | 1 | #4 | #29 | `fingerprint.py` | `test_fingerprint.py` | Done |
| US-03 | FR3 | 1 | #5 | #30 | `fingerprint.py`, `delta.py` | `test_delta.py` | Done |
| US-04 | NFR2 (reliability) | 1 | #2 | #27 | `version_provider.py` | `test_delta.py` | Done |
| US-05 | FR1, FR8 (support) | 1 | #6 | #31 | `baseline.py`, `delta.py` | `test_baseline.py` | Done |
| US-06 | NFR2 (compatibility) | 1 | #7 | #32 | `main.py`, `delta.py` | `test_e2e.py`, `test_main.py` | Done |
| US-07 | Process | 1 | #1 | #26 | repo artefacts | — | Done |
| US-08 | FR2, FR4 | 2 | #8 | #33 | `fingerprint.py` | `test_fingerprint.py` | Done |
| US-09 | FR4 | 2 | #9 | #34 | `fuzzy.py` | `test_fuzzy.py` | Done |
| US-10 | FR3 | 2 | #10 | #35 | `metrics.py` | `test_worsened.py` | Done |
| US-11 | FR5 | 2 | #11 | #36 | `calibration.py` | `test_calibration.py` | Done |
| US-12 | Evaluation input | 2 | #12 | #37 | `eval/corpus/` | replay script | Done |
| US-13 | FR6 | 3 | #13 | #38 | `risk.py` | `test_risk.py` | Done |
| US-14 | FR7 | 3 | #14 | #39 | `sarif_builder.py`, `rule_registry.py` | `test_sarif.py`, `test_rule_coverage.py` | Done |
| US-15 | FR7 | 3 | #15 | #40 | `delta.py` | `test_markdown.py` | Done |
| US-16 | FR8 | 3 | #16 | #41 | `delta.py`, `risk.py` | `test_delta_cli.py` | Done |
| US-17 | FR8 | 3 | #17 | #42 | `.github/workflows/` | manual + docs | Done |
| US-18 | NFR1 (performance) | 3 | #18 | #43 | `cache.py` | `test_cache.py` | Done |
| US-19 | Evaluation | 3 | #19 | #44 | `eval/`, report | [Detailed export and independent scoring](../python_smells_detector-main/docs/evaluation-baselines.md) | In progress. Frozen inputs and contract-host measurement outstanding. |

## 2. Functional requirement coverage

| FR | Requirement (from `PROJECT_OVERVIEW.md`) | Stories | Evidence |
| --- | --- | --- | --- |
| FR1 | Analyse two Git revisions and collect findings on both | US-01, US-05 | `delta.py`, `version_provider.py`, `baseline.py` |
| FR2 | Stable fingerprint per supported smell | US-02, US-08 | `fingerprint.py` |
| FR3 | Classify NEW / WORSENED / UNCHANGED / RESOLVED | US-03, US-10 | `fingerprint.py`, `metrics.py` |
| FR4 | Match after line shifts, renames and moves | US-02, US-08, US-09 | `fingerprint.py`, `fuzzy.py` |
| FR5 | Recommend thresholds from project metrics | US-11 | `calibration.py` |
| FR6 | Risk score with explanation | US-13 | `risk.py` |
| FR7 | Human- and machine-readable reports | US-14, US-15 | `sarif_builder.py`, `delta.py` |
| FR8 | CI pass/fail by configurable quality budget | US-16, US-17 | `delta.py`, `docs/ci/` |

## 3. Non-functional requirement coverage

| NFR | Target | Architectural option | Stories | ADR | Verification |
| --- | --- | --- | --- | --- | --- |
| NFR1 Performance (primary) | Changed tree ≤ 40% of full, or ≤ 30 s on 100k LOC | Whole-tree reuse preserves cross-file detector state | US-18, US-19 | [ADR-008](../python_smells_detector-main/docs/adr/ADR-008-performance-incremental-cache.md) | [Measured timings and environment](../python_smells_detector-main/docs/nfr-evidence.md) |
| NFR2 Reliability (primary) | F1 ≥ 0.85 and cosmetic moves tracked correctly | Stable exact identity survives edits. Fuzzy evidence recovers moved symbols. | US-02, US-04, US-06, US-08, US-09, US-19 | [ADR-009](adr/ADR-009-reliability-staged-matching.md) | [Scoring and outstanding ground truth](../python_smells_detector-main/docs/evaluation-baselines.md) |
| NFR3 Extensibility | New detector without touching the comparison engine | Detector Adapter + unified Finding + rule registry | US-01, US-08, US-14 | ADR-010 | `rule_registry.py`, `test_rule_coverage.py` |
| NFR4 Usability | Install → run → interpret in 5 minutes | Single-command CLI, four formats, explanations | US-13, US-15, US-17 | ADR-011 | quick-start walkthrough, demo script |

## 4. Closing syntax used on PRs

GitHub closes the linked issue when the PR merges to the default branch. The exact keywords we
use (case-insensitive, one per line):

```text
Closes #18
Fixes #13
Resolves #19
```

Rules:

1. One story per PR; a PR closing two stories is split or the second story is re-estimated.
2. The PR body lists each acceptance criterion with the test that proves it.
3. The PR body contains the commands run, e.g.

```text
$ python -m pytest tests/test_risk.py -q
12 passed in 0.84s

$ pyexamine-delta . --base origin/main --risk --format markdown
gate: clean (0 new findings at or above 'medium')
```

4. A PR that changes a default, threshold or output format also updates `docs/delta.md` and
   `CHANGELOG.md` in the same diff.

## 5. Weekly evidence links

| Week | Meeting note | Sprint | Stories moved | CI |
| --- | --- | --- | --- | --- |
| W2 | `meetings/week-02.md` | S1 | US-07 | green |
| W3 | `meetings/week-03.md` | S1 | US-04 | green |
| W4 | `meetings/week-04.md` | S1 | US-05, US-01 | green |
| W5 | `meetings/week-05.md` | S1 | US-02, US-03, US-06 | green |
| W6 | `meetings/week-06.md` | S2 | — (planning) | green |
| W7 | `meetings/week-07.md` | S2 | US-10, US-12 | green |
| W8 | `meetings/week-08.md` | S2 | — (review week) | green |
| W9 | `meetings/week-09.md` | S2 | US-08, US-09, US-11 | green |
| W10 | `meetings/week-10.md` | S3 | — (planning) | green |
| W11 | `meetings/week-11.md` | S3 | US-15, US-13 | green |
| W12 | `meetings/week-12.md` | S3 | US-14, US-16, US-17, US-18 | green |
| W13 | `meetings/week-13.md` | S3 | US-19 (forecast) | target |

## 6. How to audit this matrix in five minutes

1. Open the project board; every issue listed above is in the right milestone.
2. For three random stories, open the PR: it must contain `Closes #N`, the AC checklist and a
   test command with output.
3. Run `python -m pytest tests -q` — 431 passed.
4. Run `ruff check src tests` — clean.
5. Open `burndown.html`; the accepted SP in the KPI cards must equal the sum of closed story
   points (64 of 72 at Week 12).
