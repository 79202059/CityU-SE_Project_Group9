# Week 8 standing meeting

- **Date:** Monday 2026-10-26 · **Time:** 20:00–20:30 · **Location:** online
- **Facilitator:** M2 · **Minutes:** M2
- **Sprint:** Sprint 2, day 10 · **Burndown:** 10 SP remaining

**Attendees:** M1, M2, M3, M4, M5, M6 (all present)

## Agenda

1. AST signature merged — review of normalisation edge cases.
2. Calibration study design (six repositories).
3. Precision sample on real code.

## Decisions

- **D25:** The normalised signature strips docstrings **only when the docstring is a string
  expression statement**; attribute names used as data (e.g. `config["mode"]`) stay. Reason:
  stripping all constants erased real structural differences in dict-heavy code.
- **D26:** Calibration sample = 6 Python repositories of different sizes; percentiles 90/95/99
  with `--max-multiplier 2`; effective threshold = `max(research floor, percentile)`. Rejected:
  mean + k·σ (unstable with long tails in LOC metrics).
- **D27:** Precision is measured on real packages under `site-packages` (astroid, networkx,
  PyYAML) before any heuristic change is merged. Counts alone are not evidence.
- **D28:** US-09 must ship with `--no-fuzzy` as an escape hatch and `--fuzzy-threshold` for
  teams whose codebase behaves differently.

## Action items

| # | Action | Owner | Due |
| --- | --- | --- | --- |
| W8-A1 | Publish the precision sample table (per rule, 30 sampled findings) | M5 | Oct 30 |
| W8-A2 | Finish the percentile study and pick default percentiles | M4 | Nov 4 |
| W8-A3 | Add normalisation edge-case tests (dict-heavy module) | M6 | Oct 30 |
| W8-A4 | Draft ADR-009 (reliability via staged matching) | M1 | Nov 6 |

## Blockers / risks

- Calibration on tiny projects produced thresholds below the research floor; fixed by the
  `max(floor, percentile)` rule and a test. Risk R3 partially mitigated; final comparison in
  Sprint 3.
- Risk R6 (structural dominance) quantified: structural findings are 53–72% of volume in four
  real projects, 46–57% of them `high`. This number later justified the `triage` level policy.

## Notes

The sprint buffer is nearly consumed by the threshold sweep. US-11 (calibration) is at risk of
slipping to Sprint 3; the team agreed to keep it in Sprint 2 but to freeze the evaluation contract
on Nov 6 regardless of the calibration outcome.