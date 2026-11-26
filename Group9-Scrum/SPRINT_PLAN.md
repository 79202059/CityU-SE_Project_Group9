# Sprint Plan — PyExamine-Delta

**Team:** Group 9 · 6 members (M1–M6) · **Cadence:** 4-week sprints, three sprints
(Weeks 2–13 of the course) · **Estimation:** story points, 1 SP ≈ 3–4 person-hours

## 1. Calendar

| Sprint | Course weeks | Dates (2026) | Goal | Committed | Delivered | Status |
| --- | --- | --- | --- | --- | --- | --- |
| **Sprint 1** | W2–W5 | Sep 14 – Oct 9 | Baseline & core model | 21 SP | 21 SP | Closed |
| **Sprint 2** | W6–W9 | Oct 12 – Nov 6 | Matching & calibration | 21 SP | 21 SP | Closed |
| **Sprint 3** | W10–W13 | Nov 9 – Dec 4 | Integration & evaluation | 30 SP | 22 SP by Nov 26, 8 SP forecast | In progress |

Snapshot date of this document: **2026-11-26 (Week 12, Sprint 3 day 13 of 20).**

## 2. Team and roles

| ID | Role | Primary ownership |
| --- | --- | --- |
| M1 | Product Owner / team leader | Backlog, acceptance, docs, Markdown summary, evaluation protocol |
| M2 | Scrum Master | Board, burndown, meetings, CI wiring, mutation corpus |
| M3 | Lead developer | Delta CLI orchestration, fuzzy matching, gate logic, metrics |
| M4 | Developer | Fingerprints, calibration, cache, report evaluation section |
| M5 | Developer | Unified Finding model, WORSENED metrics, risk scoring, baseline runs |
| M6 | Developer | Tests, SARIF builder, cache/regression verification |

Roles are stable for the project; task ownership rotates inside a story when it reduces a
blocker. Everyone reviews at least one PR per sprint.

## 3. Capacity model

- Available effort: 6 members × 4 weeks × **~3 h/week** = **72 person-hours per sprint**.
  The course expects 30–40 h per student across the project; 240 h total is the planning cap.
- Throughput assumption: **1 SP ≈ 3.5 h**, so nominal capacity ≈ **20–21 SP** per sprint.
- Sprint 3 is deliberately stretched to **30 SP** (~105 h) because it absorbs the final
  evaluation, report section and video work; the team accepted ~4.4 h/week for four weeks.
- Buffer policy: no story above 8 SP; each sprint keeps ≤10% unallocated time for reviews and
  upstream breakage. When a sprint was at risk, scope was cut (see §6), not the Definition of
  Done.

Velocity: **21, 21, 30** SP (S3 forecast). Mean delivered velocity over closed sprints = 21.

## 4. Ceremonies

| Ceremony | When | Duration | Output |
| --- | --- | --- | --- |
| Sprint planning | Monday of week 1 of the sprint (W2, W6, W10), 20:00 | 60 min | Sprint goal, selected stories, task breakdown, capacity check |
| **Standing meeting** (required weekly) | **Every Monday 20:00–20:30** | 30 min | Decisions, blockers, action items → `meetings/week-XX.md` |
| Async stand-up | Tue–Fri, 21:00, written in the team channel | 5 min | Blockers only; burndown updated by the SM |
| Backlog refinement | Wednesday of week 3, 30 min | 30 min | Next-sprint stories reach Definition of Ready |
| Sprint review | Friday of week 4, 45 min | 45 min | Demo script executed, acceptance verdict per story |
| Retrospective | After the review, 30 min | 30 min | Start/Stop/Continue + 2–3 owned actions |

The weekly standing meeting is the evidence anchor: each note records attendance, remaining
story points, decisions with rationale, action items with owners, and blockers. Meeting notes
live in `meetings/` and are committed the same week.

## 5. Sprint goals and scope boundaries

### Sprint 1 — “Prove the diff is possible and safe”

**Goal:** produce a trustworthy four-state diff of two revisions without touching the user's
working tree, and prove the fork does not alter upstream behaviour.

In scope: version provider, unified Finding, exact fingerprint, states, baseline file,
byte-compatibility harness, process scaffolding. Out of scope: fuzzy matching, calibration,
risk, SARIF, CI gate.

**Demo:** on `tests/fixtures/sample_project`, a commit that fixes one smell and introduces
another produces exactly one `RESOLVED` and one `NEW`; every other finding is `UNCHANGED`.

### Sprint 2 — “Make identity survive refactoring”

**Goal:** a moved or renamed smell keeps its identity, and thresholds can be learned from the
project instead of a library average.

In scope: normalised AST signature, fuzzy matching with an explicit threshold, WORSENED metric
deltas, `calibrate`, frozen mutation corpus. Out of scope: reporting formats and CI gate; those
belong to Sprint 3.

**Demo:** moving a function to another module and inserting blank lines yields **zero** `NEW`
findings; `calibrate` produces a YAML whose thresholds differ from defaults on a 6-repo sample.

### Sprint 3 — “Ship the gate and defend the numbers”

**Goal:** make the tool usable in a real PR workflow (Markdown/SARIF, exit-code gate, Actions),
meet the performance budget with a cache, and execute the frozen evaluation.

In scope: risk score, SARIF, Markdown, gate flags, Actions workflow, cache, evaluation, report,
video. Out of scope (frozen by the contract): new detectors, new metrics definitions, UI.

**Demo:** a PR that introduces an 82-line method fails the gate with a risk-ranked,
explained finding at the right line; after refactoring, the gate passes. Evaluation table
compares Baseline A, Baseline B and Proposed on the frozen corpus.

## 6. Scope changes and decisions (change log)

| Date | Change | Reason | Decision owner |
| --- | --- | --- | --- |
| 2026-09-22 | Baseline snapshot moved into Sprint 1 instead of Sprint 3 | CI needs it earlier than expected; it also removes a second analysis in demos | M1 |
| 2026-10-21 | Cross-file move matching kept; cross-repository moves rejected | Time-boxed spike showed cross-repo identity is out of scope | M3 |
| 2026-11-09 | Risk score moved from Sprint 2 to Sprint 3 | Fuzzy matching consumed the Sprint 2 buffer; risk depends on metrics that landed late | M1 |
| 2026-11-16 | Web UI / IDE plugin formally dropped | Non-goal; CLI + PR-native output is the usability argument | M1 |
| 2026-11-16 | `--level-policy triage` made the CI default | Measured structural-finding share makes raw `high` block every PR | M2 |
| 2026-11-25 | Evaluation kept as an 8-SP Sprint 3 story, not split | Splitting would break the frozen contract; report section folded in | M1 |

No change altered the evaluation metrics or the NFR targets after the contract freeze
(2026-11-06). See `EVALUATION_CONTRACT.md` §7.

## 7. Dependencies

- US-08/US-09 depend on US-02 (exact identity) and US-05 (baseline).
- US-10 depends on US-02/US-09 (matching) and on `metrics.py`.
- US-13 depends on US-10's metric table and on `git diff` line ranges from US-01.
- US-14/US-15 depend on US-13 for the risk column.
- US-16/US-17 depend on US-13 and US-14.
- US-18 is independent of US-13–17 but shares the CLI; it was scheduled last to avoid blocking
  the gate work.
- US-19 depends on US-01, US-09, US-11, US-18; it is the only story allowed to extend into the
  wrap-up week.

## 8. Sprint detail

- [Sprint 1 — Baseline & core model](sprints/sprint-1.md)
- [Sprint 2 — Matching & calibration](sprints/sprint-2.md)
- [Sprint 3 — Integration & evaluation](sprints/sprint-3.md)

Burndown data and charts: [BURNDOWN.md](BURNDOWN.md) · live dashboard:
[`burndown.html`](burndown.html).

## 9. Definition of Done (summary)

A story is done when its acceptance scenarios pass as automated tests, `python -m pytest tests`
is green (431 tests), `ruff check src tests` is clean, the PR is reviewed by a second member,
the acceptance evidence is linked in the issue, and the weekly note mentions the merged PR.
Full checklist: [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md).