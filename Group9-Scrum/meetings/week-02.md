# Week 2 standing meeting

- **Date:** Monday 2026-09-14 · **Time:** 20:00–20:30 · **Location:** online (team call)
- **Facilitator:** M2 (Scrum Master) · **Minutes:** M2
- **Sprint:** Sprint 1, day 0 · **Burndown:** 21 SP remaining (start)

**Attendees:** M1, M2, M3, M4, M5, M6 (all present)

## Agenda

1. Confirm roles and decision rules.
2. Sprint 1 planning: goal, story selection, capacity.
3. Fork strategy for PyExamine 0.3.0.

## Decisions

- **D1:** M1 is Product Owner and repository owner; M2 is Scrum Master. Code ownership is by
  module, but every PR needs one reviewer who did not write it.
- **D2:** Sprint 1 goal accepted: “prove the diff is possible and safe”. 21 SP committed
  (US-01, US-02, US-03, US-04, US-05, US-06, US-07).
- **D3:** Fork strategy — add a **second console script** `pyexamine-delta` and leave the three
  upstream detectors byte-identical. Rejected alternative: rewrite the detectors to emit a
  delta-aware model (too much risk in four weeks, and it would break upstream tests).
- **D4:** Estimation: 1 SP ≈ 3.5 h; capacity 72 h per sprint; no story above 8 SP.

## Action items

| # | Action | Owner | Due |
| --- | --- | --- | --- |
| W2-A1 | Create fork, milestones, labels, issue/PR templates | M2 | Sep 15 |
| W2-A2 | Seed risk register and ADR template | M1 | Sep 16 |
| W2-A3 | Spike `git worktree add --detach` and prove the working tree stays clean | M3 | Sep 17 |
| W2-A4 | Draft the unified `Finding` fields (no line numbers in identity) | M5 | Sep 18 |

## Blockers / risks

- Repository access for two members was pending; resolved during the meeting by adding them as
  collaborators. (Risk R10: availability.)
- Risk R1 (upstream may not run deterministically) opened; owner M6; check on Python 3.10–3.14
  by Sep 25.

## Notes

The weekly cadence is fixed: Monday 20:00, 30 minutes, notes committed the same day. If a
meeting is skipped, the burndown value is still recorded by the SM so the chart has no gaps.