# Week 10 standing meeting

- **Date:** Monday 2026-11-09 · **Time:** 20:00–20:30 · **Location:** online
- **Facilitator:** M2 · **Minutes:** M1
- **Sprint:** Sprint 3, day 0 · **Burndown:** 30 SP remaining (start)

**Attendees:** M1, M2, M3, M4, M5, M6 (all present)

## Agenda

1. Sprint 3 planning (30 SP).
2. Risk score component weights.
3. SARIF scope and rule-id handling.

## Decisions

- **D33:** Sprint 3 backlog confirmed: US-15 (2), US-13 (5), US-14 (5), US-16 (3), US-17 (2),
   US-18 (5), US-19 (8) = 30 SP.
- **D34:** Risk weights accepted as 0.35 excess + 0.25 changed-line overlap + 0.20 dependency
  centrality + 0.20 confidence. Weights are a stated design choice, not a learned parameter; the
  evaluation reports ranking quality, not “optimal” weights.
- **D35:** SARIF rule ids are stable `pyex-<category>-<slug>` strings mapped from the legacy
  `PX-*` numbers; `docs/rule_ids.json` is the source, the registry is generated from it.
- **D36:** `--min-risk 40` is the recommended default: p90 across the three calibration corpora is
  34–40, so 40 approximates “top 10% riskiest new findings”.

## Action items

| # | Action | Owner | Due |
| --- | --- | --- | --- |
| W10-A1 | Finish risk explanation text and test the 82-line example | M5 | Nov 16 |
| W10-A2 | Validate SARIF against the 2.1.0 schema; add `--all-rules` | M6 | Nov 19 |
| W10-A3 | Implement Markdown truncation and step-summary output | M1 | Nov 12 |
| W10-A4 | Start the cache manifest design and measure cold-run time | M4 | Nov 23 |

## Blockers / risks

- Risk R6 (structural high findings) needs a policy before the gate is usable. Discussion moved
  to Week 11 with data; no silent bypass will be added.
- Risk R8 (annotation disagreement) opened: two annotators will label the frozen sample; κ target
  ≥ 0.60, adjudication rule fixed in the contract.

## Notes

The team agreed that the risk score must never be the only reason a finding is shown — severity
and state remain visible, because a reviewer needs to understand the finding even if they
disagree with the weights.