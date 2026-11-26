# Week 5 standing meeting

- **Date:** Monday 2026-10-05 · **Time:** 20:00–20:30 · **Location:** online
- **Facilitator:** M2 · **Minutes:** M2
- **Sprint:** Sprint 1, day 16 · **Burndown:** 2 SP remaining

**Attendees:** M1, M2, M3, M4, M5, M6 (all present)

## Agenda

1. Sprint 1 review rehearsal (demo script dry run).
2. Sprint 2 readiness: AST signature and fuzzy matching.
3. Retrospective preparation.

## Decisions

- **D13:** Sprint 1 is accepted at 21 SP only if all four demo steps pass twice in a row on a
  clean clone. Flaky demos count as failures.
- **D14:** Sprint 2 will start with US-08 (AST signature), not US-09 (fuzzy). Reason: fuzzy
  scoring without a normalised signature reproduces the Sprint 1 limitation in a more expensive
  way.
- **D15:** The evaluation corpus (US-12) is pulled into Sprint 2 as a **frozen artefact**; tuning
  must not happen on the same commits used to report results. Contract to be frozen at the end
  of Sprint 2.
- **D16:** No new detector work. The five focal smells are the scope; everything else keeps
  upstream defaults.

## Action items

| # | Action | Owner | Due |
| --- | --- | --- | --- |
| W5-A1 | Execute the demo script on a clean clone and record the output | M6 | Oct 8 |
| W5-A2 | Write the retrospective board (Start/Stop/Continue) | M2 | Oct 9 |
| W5-A3 | Draft US-08 normalisation rules for review | M4 | Oct 14 |
| W5-A4 | Collect 6 candidate repositories for calibration study | M5 | Oct 16 |

## Blockers / risks

- Sprint 1 has no carry-over; the only open question is whether the fuzzy pass can hit the
  precision target in four weeks. Risk R2 stays open with trigger “precision < 0.70 on fixtures”.
- Risk R3 (calibration may not beat defaults) opened; decision date set to the Sprint 2 review.

## Notes

Rehearsal exposed one usability issue: the report did not show the metric value that made a
finding “new”. That observation later became the WORSENED work (US-10) and the explanation lines
in risk scoring (US-13).