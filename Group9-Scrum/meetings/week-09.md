# Week 9 standing meeting

- **Date:** Monday 2026-11-02 · **Time:** 20:00–20:30 · **Location:** online
- **Facilitator:** M1 · **Minutes:** M2
- **Sprint:** Sprint 2, day 15 · **Burndown:** 5 SP remaining

**Attendees:** M1, M2, M3, M4, M5, M6 (all present)

## Agenda

1. US-09 acceptance and merge.
2. Calibration results and guard rails.
3. Freeze the evaluation contract; plan Sprint 3.

## Decisions

- **D29:** US-09 accepted at threshold 0.62: on the 40-fixture set it matched 37 moves/renames with
  no false pair on the negative fixtures. `--no-fuzzy` documented.
- **D30:** Calibration guard: effective threshold = `max(research floor, percentile)`, capped at
  `floor × max-multiplier`. Calibration only **writes a file**; it never edits the gate. The
  operator commits the YAML consciously.
- **D31:** Evaluation contract frozen on 2026-11-06: tasks, repositories, commits, metrics,
  thresholds, environment, baselines A/B, and the rule that negative results are reported without
  changing definitions. Risk score (US-13) moves to Sprint 3.
- **D32:** Sprint 3 is a deliberate stretch: 30 SP including the 8-SP evaluation and wrap-up.
  Capacity accepted at ~4.4 h/week per member for four weeks.

## Action items

| # | Action | Owner | Due |
| --- | --- | --- | --- |
| W9-A1 | Write `EVALUATION_CONTRACT.md` and freeze it with the team's signatures | M1 | Nov 6 |
| W9-A2 | Publish the calibration YAML example for three repos | M4 | Nov 5 |
| W9-A3 | Prepare Sprint 3 backlog and task breakdown | M2 | Nov 9 |
| W9-A4 | Record ADR-009 status as “draft, accepted at review” | M1 | Nov 6 |

## Blockers / risks

- US-11 merged on Nov 5, one day before review; no carry-over.
- Remaining schedule risk is concentrated in Week 12–13 (evaluation + report + video). Mitigation:
  no new features after Nov 26; evaluation accepted Dec 3.

## Notes

Freezing the contract before seeing results was the most important process decision of the
project. The team wrote down the thresholds and the sampling rule, and agreed that a disappointing
number is a finding, not a reason to move the goalposts.