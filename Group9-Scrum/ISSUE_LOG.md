# Issue Log (board snapshot)

Snapshot: **2026-11-26**. One issue per story, plus support issues. Issues use #1–#25 and pull
requests #26–#49 in one shared sequence (as GitHub does); the numbers are the planned numbering
used throughout this package — **replace with the real repository numbers** if they
differ (the mapping in `TRACEABILITY.md` is one-to-one).

## Sprint 1 — milestone closed 2026-10-09

| Issue | Title | Type | SP | PR | State |
| --- | --- | --- | --- | --- | --- |
| #1 | Process scaffolding: board, templates, ADR folder, weekly cadence | task | 1 | #26 | Closed |
| #2 | Safe git worktree version provider (cleanup, dirty tree, errors) | story | 2 | #27 | Closed |
| #3 | Analyse base and head revisions and diff findings | story | 5 | #28 | Closed |
| #4 | Exact stable fingerprint invariant to line shifts | story | 5 | #29 | Closed |
| #5 | Four-state lifecycle classification | story | 3 | #30 | Closed |
| #6 | Committable baseline snapshot and `--baseline-mode` | story | 3 | #31 | Closed |
| #7 | Upstream output byte-compatibility harness | story | 2 | #32 | Closed |
| #21 | Bug: baseline keys differ on Windows paths | bug | — | #45 | Closed |

## Sprint 2 — milestone closed 2026-11-06

| Issue | Title | Type | SP | PR | State |
| --- | --- | --- | --- | --- | --- |
| #8 | Normalised AST structure signature | story | 5 | #33 | Closed |
| #9 | Rename / move matching with explicit threshold | story | 5 | #34 | Closed |
| #10 | WORSENED state from metric deltas | story | 3 | #35 | Closed |
| #11 | Project-adaptive threshold calibration | story | 5 | #36 | Closed |
| #12 | Controlled mutation corpus (`eval-corpus-v1`) | task | 3 | #37 | Closed |
| #20 | Bug: flaky marker assertion on Windows CI | bug | — | #46 | Closed |
| #22 | Task: fold threshold digest into cache key | task | — | #49 | Closed |
| #23 | Docs: quick-start verified on clean clone | docs | — | #47 | Closed |

## Sprint 3 — milestone due 2026-12-04

| Issue | Title | Type | SP | PR | State |
| --- | --- | --- | --- | --- | --- |
| #13 | Explainable 0–100 risk score | story | 5 | #38 | Closed |
| #14 | SARIF 2.1.0 with 47 stable rule ids | story | 5 | #39 | Closed |
| #15 | Text and Markdown PR summary | story | 2 | #40 | Closed |
| #16 | Configurable gate: severity, budget, risk, worsened | story | 3 | #41 | Closed |
| #17 | GitHub Actions workflow and integration guide | story | 2 | #42 | Closed |
| #18 | Content-addressed incremental cache (ADR-008) | story | 5 | #43 | Closed |
| #19 | Frozen evaluation against baselines A/B | story | 8 | #44 | **Open** (in review) |
| #24 | ADR-008 accepted: incremental cache | adr | — | #48 | Closed (status only) |
| #25 | Release 1.0 checklist: tag, changelog, video, slides | task | — | — | Open |

## Board summary

| Column | Cards |
| --- | --- |
| Backlog | #25 |
| Ready | — |
| In progress | #19 (evaluation runs) |
| In review | #44 (open PR) |
| Done | #1–#18, #20–#24 |

Accepted story points: **64 / 72**. Remaining: **8 SP** (#19).

## Conventions used in every issue

- Title starts with the US id when the issue is a story (`US-09: Rename / move matching`).
- The body contains the persona sentence, the AC checklist and the evidence plan (§4 of
  `GITHUB_WORKFLOW.md`).
- Blocked issues carry `state/blocked` and a comment naming the blocking issue or external cause.
- Closed issues have the closing PR linked and a one-line “accepted at review” comment with the
  date and the reviewer.