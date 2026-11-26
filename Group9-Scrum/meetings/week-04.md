# Week 4 standing meeting

- **Date:** Monday 2026-09-28 · **Time:** 20:00–20:30 · **Location:** online
- **Facilitator:** M1 (M2 traveling) · **Minutes:** M1
- **Sprint:** Sprint 1, day 11 · **Burndown:** 10 SP remaining

**Attendees:** M1, M2 (remote), M3, M4, M5, M6 (all present)

## Agenda

1. First demo of the four-state report (US-01).
2. Fingerprint composition — what goes in, what must stay out.
3. Upstream compatibility harness.

## Decisions

- **D9:** Fingerprint = `rule_id | normalised relative path | qualified symbol | AST signature`.
  **Line numbers are forbidden** in the identity. Reason: the only property we must guarantee in
  Sprint 1 is invariance under line shifts; anything else can be added in Sprint 2.
- **D10:** Normalisation v1 strips identifier names and literal values only in the *signature*
  hash, never in the Finding payload — the report must still show the real name.
- **D11:** Upstream compatibility becomes a **merge gate**: text and JSON outputs on
  `tests/fixtures/sample_project` are pinned byte-for-byte (967 / 5366 bytes). Any PR that changes
  them must say so in its description and update the fixture deliberately.
- **D12:** The demo will use a real commit pair, not a mock: one smell fixed, one introduced.

## Action items

| # | Action | Owner | Due |
| --- | --- | --- | --- |
| W4-A1 | Add equivalence test: two runs, identical sources → identical fingerprints | M6 | Sep 30 |
| W4-A2 | Pin upstream output sizes in `test_e2e.py` | M2 | Oct 1 |
| W4-A3 | Prepare the demo commit pair in the sample fixture | M3 | Oct 6 |
| W4-A4 | Write the Sprint 1 review script (5 steps, ≤10 min) | M1 | Oct 7 |

## Blockers / risks

- The four-state classification currently reports a renamed function as NEW + RESOLVED. Accepted
  as a Sprint 1 limitation; US-09 (fuzzy) is scheduled in Sprint 2. Risk R2 opened.
- Risk R6 (structural findings dominate volume) observed on the first full run; not yet a
  Sprint 1 problem but noted for the gate design.

## Notes

The team agreed that **a state must be defensible in one sentence**: “this fingerprint was absent
in base and present in head”. Any state that cannot be explained that way is a bug, not a
heuristic.