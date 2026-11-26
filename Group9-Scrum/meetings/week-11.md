# Week 11 standing meeting

- **Date:** Monday 2026-11-16 · **Time:** 20:00–20:30 · **Location:** online
- **Facilitator:** M2 · **Minutes:** M2
- **Sprint:** Sprint 3, day 5 · **Burndown:** 23 SP remaining

**Attendees:** M1, M2, M3, M4, M5, M6 (all present)

## Agenda

1. Risk score demo and feedback.
2. Gate policy: severity mapping and defaults.
3. Scope freeze for Week 13.

## Decisions

- **D37:** Default SARIF/level policy is `triage`: structural `high` is demoted to `warning`.
  Evidence: structural findings are 53–72% of volume and 46–57% of them are `high`; raw mapping
  makes every PR red and the gate gets ignored. `strict` and `advisory` remain available.
- **D38:** Gate defaults for the example workflow: `PYEX_FAIL_ON=medium`, `PYEX_MIN_RISK=40`,
  `PYEX_BUDGET=20`. Teams are told to tighten the budget by 20% per sprint after measuring their
  own history.
- **D39:** Severity is checked before the budget; when both fail, only the severity message is
  printed (the more actionable one).
- **D40:** **Feature freeze on 2026-11-26.** After that date only evaluation, report, slides and
  demo video work. The web-UI idea is formally dropped (non-goal); it stays in the report as a
  rejected alternative.

## Action items

| # | Action | Owner | Due |
| --- | --- | --- | --- |
| W11-A1 | Wire the workflow with the four knobs and document local reproduction | M2 | Nov 20 |
| W11-A2 | Add gate tests for severity-before-budget ordering | M3 | Nov 20 |
| W11-A3 | Prepare the 82-line demo PR (fail → fix → pass) | M5 | Dec 2 |
| W11-A4 | Draft the demo video storyboard (7-minute cut) | M1 | Nov 27 |

## Blockers / risks

- SARIF upload needs GHAS on private repositories; documented limitation, workflow step is
  optional. No GitHub App will be built (risk R4 closed by this decision).
- Evaluation annotation is behind by one round; recovery plan in `EVALUATION_CONTRACT.md` §6
  (26 items by Nov 27, then baseline runs).

## Notes

The policy discussion produced the only “product” debate of the sprint: a gate that is always red
is worse than no gate. The team chose to demote a noisy category explicitly, with numbers, rather
than silently raising the severity threshold.