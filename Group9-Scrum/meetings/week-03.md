# Week 3 standing meeting

- **Date:** Monday 2026-09-21 · **Time:** 20:00–20:30 · **Location:** online
- **Facilitator:** M2 · **Minutes:** M2
- **Sprint:** Sprint 1, day 6 · **Burndown:** 18 SP remaining

**Attendees:** M1, M2, M3, M5, M6 · **Apologies:** M4 (lab session; written update sent)

## Agenda

1. Worktree provider review outcome.
2. Baseline file: schema and placement in the sprint.
3. Review latency on PR #27.

## Decisions

- **D5:** Baseline snapshot (`--baseline-mode`) moves into Sprint 1 instead of Sprint 3. Reason:
  CI needs a cheap diff before the gate exists, and it removes a second full analysis in demos.
  Scope swap: US-05 in, nothing removed (capacity check: 75 h planned vs 72 h capacity, buffer
  from US-07).
- **D6:** Baseline format = JSON list of findings with **relative** paths, rule id, symbol and
  metadata; no AST bodies. It must be commit-friendly and deterministic.
- **D7:** The worktree provider must clean up on `KeyboardInterrupt` and on exceptions, not only
  on success. This is an acceptance criterion, not a nice-to-have.
- **D8:** Review SLA: first review within 24 h on weekdays; if the author is blocked, the SM
  reassigns the reviewer at the next stand-up.

## Action items

| # | Action | Owner | Due |
| --- | --- | --- | --- |
| W3-A1 | Add interrupt/failure cleanup test to `test_delta.py` | M6 | Sep 23 |
| W3-A2 | Fix Windows path normalisation in baseline keys | M4 | Sep 23 |
| W3-A3 | Document the two baseline traps (`write` snapshots `--head`; thresholds invalidate) | M4 | Sep 25 |
| W3-A4 | Start the Finding model PR (no behaviour change) | M5 | Sep 24 |

## Blockers / risks

- PR #27 sat 3 days without review because the reviewer was on another task. Mitigated by D8.
- Risk R7 (path handling differs on Windows) triggered and closed the same week by W3-A2; added
  to the Definition of Done as a cross-platform check.

## Notes

The baseline decision was the first scope change of the project; it was recorded in the change
log rather than silently absorbed, because the burndown and the sprint review both reference it.