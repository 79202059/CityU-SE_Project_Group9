# Week 6 standing meeting

- **Date:** Monday 2026-10-12 · **Time:** 20:00–20:30 · **Location:** online
- **Facilitator:** M2 · **Minutes:** M2
- **Sprint:** Sprint 2, day 0 · **Burndown:** 21 SP remaining (start)

**Attendees:** M1, M2, M3, M4, M5, M6 (all present)

## Agenda

1. Sprint 2 planning (21 SP).
2. AST signature scope and normalisation rules.
3. Evaluation corpus design.

## Decisions

- **D17:** Sprint 2 goal: “identity survives refactoring”. Committed: US-08 (5), US-09 (5),
  US-10 (3), US-11 (5), US-12 (3) = 21 SP.
- **D18:** AST signature ignores identifier names, docstrings, literal values, comments and
  formatting; keeps node types and structural shape. `ast.dump(..., include_attributes=False)`
  normalised, then hashed. Rejected alternative: full `ast.dump` with attributes (line numbers
  reappear, defeating the purpose).
- **D19:** Corpus = 24 controlled commits (8 introduce, 4 worsen, 6 move/rename, 4 resolve,
  2 cosmetic no-ops) in a sandbox repository, tagged `eval-corpus-v1` when frozen.
- **D20:** Risk scoring is **not** committed to Sprint 2. It depends on the metric table from
  US-10 and would put US-08/US-09 at risk. Moved to Sprint 3 change log.

## Action items

| # | Action | Owner | Due |
| --- | --- | --- | --- |
| W6-A1 | Build the 24-commit corpus and `manifest.csv` | M2 | Oct 20 |
| W6-A2 | Write normalisation unit tests with golden AST dumps | M6 | Oct 19 |
| W6-A3 | Draft fuzzy scoring formula and candidate generation | M3 | Oct 19 |
| W6-A4 | Define the metric table (rule → value, threshold) | M5 | Oct 16 |

## Blockers / risks

- Calendar risk: two members have midterms in Weeks 7–8. Mitigation: pair US-08 with US-09 so
  neither story is single-owner; recorded as R10.
- Risk R2 trigger still “precision < 0.70 on rename/move fixtures”; measurement scheduled for
  Oct 21 after the sweep.

## Notes

The team explicitly wrote down what “identity” means, because “same smell” had three different
usages in early discussions: same rule + same symbol, same AST shape, and same metric value.
The fingerprint answers only the first two; metric change is the WORSENED question (US-10).