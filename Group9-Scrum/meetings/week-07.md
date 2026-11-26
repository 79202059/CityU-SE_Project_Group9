# Week 7 standing meeting

- **Date:** Monday 2026-10-19 · **Time:** 20:00–20:30 · **Location:** online
- **Facilitator:** M2 · **Minutes:** M1
- **Sprint:** Sprint 2, day 5 · **Burndown:** 18 SP remaining

**Attendees:** M1, M2, M3, M4, M6 · **Apologies:** M5 (midterm; async update)

## Agenda

1. WORSENED semantics and metric table.
2. Fuzzy matching spike: first numbers from the threshold sweep.
3. Corpus status.

## Decisions

- **D21:** A matched finding is `WORSENED` only when its measured value **crosses the effective
  threshold** in head and did not in base, or worsens by more than 20% while already over the
  threshold. Reason: “any increase” produced noise on every refactor. The 20% band is recorded
  in `metrics.py` and in the evaluation contract.
- **D22:** Fuzzy scoring uses symbol similarity, path similarity, AST similarity and line
  proximity; candidate generation at a low threshold, acceptance at 0.62 by default. Rejected:
  pure token similarity (matched unrelated short functions), pure path-first (failed on `git mv`).
- **D23:** Cross-file moves inside the repository are supported; **cross-repository** moves are
  out of scope and will be stated as a limitation.
- **D24:** The 20% worsening band is a hypothesis; it will be evaluated, not assumed. If it hurts
  recall, it is reported as a negative result.

## Action items

| # | Action | Owner | Due |
| --- | --- | --- | --- |
| W7-A1 | Run the threshold sweep on 40 rename/move fixtures; record precision per threshold | M5 | Oct 23 |
| W7-A2 | Add the 20% band to the WORSENED tests | M6 | Oct 23 |
| W7-A3 | Fix cross-file move failures in `fuzzy.py` | M3 | Oct 26 |
| W7-A4 | Tag the corpus `eval-corpus-v1` after review | M2 | Oct 20 |

## Blockers / risks

- Cross-file move cases were failing on Oct 22 (recorded in the burndown note). Fixed by adding
  path similarity as a component rather than a hard filter.
- Risk R3 (calibration not better than defaults) remains open; the percentile study starts Oct 26.

## Notes

The team accepted an explicit bias: **precision over recall** for matching. A missed move produces
one NEW + one RESOLVED (noisy but honest); a wrong match hides a real new smell, which is worse
for a review gate.