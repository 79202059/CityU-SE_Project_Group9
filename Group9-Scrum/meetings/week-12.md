# Week 12 standing meeting

- **Date:** Monday 2026-11-23 · **Time:** 20:00–20:30 · **Location:** online
- **Facilitator:** M2 · **Minutes:** M1
- **Sprint:** Sprint 3, day 10 · **Burndown:** 13 SP remaining (8 by Nov 25, after US-18)

**Attendees:** M1, M2, M3, M4, M5, M6 (all present)

## Agenda

1. Cache merge and NFR measurement plan.
2. Evaluation status: annotation, baselines, schedule.
3. Report, slides and demo video assignments.

## Decisions

- **D41:** US-18 accepted after the cache-hit equivalence test: a hit returns exactly the cold-run
  result, paths re-rooted, and a threshold or version change invalidates the entry. ADR-008
  accepted.
- **D42:** Feature freeze confirmed for 2026-11-26. Remaining work is US-19 only.
- **D43:** Report ownership: introduction/related work/preliminaries → M1; solution → M3 + M4;
  software process → M2; evaluation → M5; conclusion and bios → each member, assembled by M1.
- **D44:** Demo video: one continuous end-to-end flow (baseline → PR gate fails → fix → gate
  passes → SARIF annotation), plus a 60-second process segment (board, burndown, retros). No
  future features in the demo.
- **D45:** Contribution table uses productive hours per sprint, cross-checked against story
  ownership; ratios are capped to [0.8, 1.2] for extreme cases, with a written explanation.

## Action items

| # | Action | Owner | Due |
| --- | --- | --- | --- |
| W12-A1 | Complete annotation round 2 (26 remaining items) | M1 | Nov 27 |
| W12-A2 | Run Baseline A and B on the frozen corpus | M5 | Nov 30 |
| W12-A3 | Produce metrics table and two charts | M3 | Dec 1 |
| W12-A4 | Draft evaluation section (2–5 pages) | M4 | Dec 2 |
| W12-A5 | Collect weekly evidence links into one index | M2 | Dec 2 |

## Blockers / risks

- Week 13 collides with two other course deadlines; mitigation: evaluation accepted Dec 3, slides
  frozen Dec 4, no new code.
- Warm-cache timing must be measured on the agreed environment; if the laptop disagrees with CI,
  both numbers are reported (ADR-008 measurement protocol).

## Notes

The 8 SP left is the evaluation story, not development. The team explicitly rejected adding a
“nice extra” (approximate duplicate detection) in Week 13; the risk register's stop rule says the
evaluation and test evidence are never weakened for extra features.