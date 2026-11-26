# Week 13 standing meeting (planned)

- **Date:** Monday 2026-11-30 · **Time:** 20:00–20:30 · **Location:** online
- **Facilitator:** M2 · **Minutes:** M2
- **Sprint:** Sprint 3, day 15 · **Burndown:** 8 SP remaining (forecast)

**Attendees (expected):** M1, M2, M3, M4, M5, M6

## Agenda

1. Evaluation results walkthrough; freeze the numbers.
2. Final report assembly and IEEE TSE format check.
3. Submission checklist: repo, slides, video, contribution table.

## Planned decisions

- Accept US-19 only when the evaluation table is reproducible from the committed scripts and the
  frozen corpus tag.
- Freeze the report PDF and the slide deck on 2026-12-03; only typo fixes afterwards.
- Confirm that all 431 tests pass on the CI matrix and that `ruff` is clean at the submitted commit.
- Confirm relative-contribution numbers and each member's declaration.

## Action items (to be confirmed at the meeting)

| # | Action | Owner | Due |
| --- | --- | --- | --- |
| W13-A1 | Run the full evaluation script from a clean clone | M5 | Dec 1 |
| W13-A2 | Complete the report's software-process section (2 pages/sprint) | M2 | Dec 2 |
| W13-A3 | Record the demo video in one take | M1 | Dec 2 |
| W13-A4 | Verify every story has an issue, a merged PR and a test | M6 | Dec 3 |
| W13-A5 | Submit code, report and slides; archive the release tag | M1 | Dec 4 |

## Blockers / risks

- If annotation κ falls below 0.60, report per-annotator results and the disagreement analysis;
  do not re-label to force agreement.
- If the 100k-LOC benchmark cannot be reproduced, report the largest available repository and the
  deviation; do not change the NFR target.

## Notes

This note is a placeholder until the meeting happens: replace the planned decisions with the
actual ones, update the burndown (`forecast` 1 → 0), and commit within 48 hours.