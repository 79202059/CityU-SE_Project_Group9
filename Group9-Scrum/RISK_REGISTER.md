# Risk Register and Stop Rules

Owner of the register: **M2 (Scrum Master)**, reviewed at every Monday standing meeting and at
every sprint review. Likelihood and impact are scored 1–5; score = L × I.
Anything scoring ≥ 12 requires a written mitigation and a decision date.

**Stop rule:** when the trigger fires, the team applies the stop/re-scope action in the table
**before** starting new work. A stop rule is not advisory; it is a pre-agreed decision so that a
bad week does not turn into a changed evaluation standard.

## Register

| ID | Risk | Trigger (observable) | L | I | Score | Owner | Mitigation | Stop / re-scope rule | Decision date | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | Upstream PyExamine 0.3.0 does not run deterministically across interpreters | Findings differ between Python 3.10 and 3.14 on the fixture | 3 | 4 | 12 | M6 | Pin fixture outputs; run the CI matrix before any detector work | If unresolved by end of Sprint 1, freeze on Python 3.13 only and document the deviation | 2026-09-25 | **Closed** — identical on 3.10–3.14 |
| R2 | Fuzzy matching precision < 0.70 on rename/move fixtures | False pairs appear on negative fixtures; match rate < 70% | 3 | 4 | 12 | M3 | Two-stage matching; precision-over-recall bias; threshold sweep; negative fixtures | If precision stays < 0.70 after the sweep, restrict matching to same-file symbols and list cross-file moves as unsupported | 2026-10-21 | **Closed** — 37/40 fixtures, 0 false pairs at 0.62 |
| R3 | Adaptive thresholds do not beat fixed defaults | Calibrated config yields lower F1 than defaults on the frozen set | 3 | 3 | 9 | M5 | Compare on 6 repositories; keep research floors; report per-size effects | Report as a negative result; do not weaken the metric or hide the config behind a default | 2026-12-03 | Open (evaluation) |
| R4 | GitHub integration consumes the sprint | More than 2 days spent on workflow/GHAS issues | 3 | 3 | 9 | M2 | Emit SARIF locally; use the existing upload action; no GitHub App | Drop the upload step; keep exit-code gate and step summary | 2026-11-16 | **Closed** — no App built |
| R5 | Scope too large for 12 weeks | Any sprint > 20% over capacity at planning | 4 | 4 | 16 | M1 | Five focal smells; defer optional integrations; freeze features on Nov 26 | Keep the five smells; delete optional integrations first; never weaken tests or evaluation | 2026-11-09 | Monitoring |
| R6 | Structural findings dominate volume and make the gate always red | > 50% of findings structural, > 40% of them `high` | 4 | 3 | 12 | M2 | Measure share on real repos; `triage` level policy; `--min-risk` default 40; budget knob | If `triage` still blocks every PR, ship the gate disabled-by-default with documented settings | 2026-11-16 | **Mitigated** — measured 53–72% / 46–57%; triage shipped |
| R7 | Path normalisation differs across OS | Baseline keys mismatch between Windows and Linux | 3 | 3 | 9 | M4 | Relative POSIX paths in fingerprints and baseline; Windows test in CI | If unresolved, forbid baseline mode on non-POSIX and document | 2026-09-23 | **Closed** |
| R8 | Annotators disagree on ground truth | Cohen's κ < 0.60 after round 2 | 3 | 4 | 12 | M1 | Written adjudication rule; two independent rounds; disagreement log | Report per-annotator results and analyse disagreements; never re-label to force agreement | 2026-11-27 | Open |
| R9 | Team availability (midterms, other deadlines) | Two members unavailable in the same week | 4 | 3 | 12 | M2 | Pair ownership; buffer in Sprint 1–2; async stand-ups | Reduce sprint scope at the boundary, not mid-sprint; protect the evaluation | Ongoing | Monitoring |
| R10 | Repository / access and free-rider problems | A member misses two consecutive meetings and has no merged PR | 2 | 5 | 10 | M1 | Written contribution log; small reviewable tasks; weekly evidence | Contribution ratio < 0.8 requires a documented case; report to the instructor if unresolved | Ongoing | Monitoring |
| R11 | AI coding agent output merged without human understanding | A PR contains unexplained algorithms or tests that assert nothing | 3 | 4 | 12 | M1 | Agent contract: bounded task, repo context, tests + rationale, human review and veto; never auto-merge | Revert the PR; re-implement with the owner; record the incident in the retro | 2026-11-09 | Monitoring |
| R12 | Baseline invalidation causes a silent green gate | After a threshold change, many findings appear as RESOLVED | 4 | 4 | 16 | M5 | Threshold digest in cache key; docs state the two traps; sprint checklist | Rebuild baseline (`--base X --head X`) and re-run the gate before trusting a green result | 2026-11-25 | **Mitigated** (documented + digest) |
| R13 | Benchmark environment differs from the agreed one | Warm-run timing varies > 2× between laptop and CI | 3 | 2 | 6 | M4 | Record environment in ADR-008 protocol; report both numbers | Judge the NFR on the agreed environment only; report the deviation explicitly | 2026-12-02 | Open |

## Decision log

| Date | Risk | Decision | Consequence |
| --- | --- | --- | --- |
| 2026-09-21 | R5 | Move baseline snapshot into Sprint 1 | Removed a second analysis from demos; no scope removed |
| 2026-10-19 | R2 | Precision over recall; same-repo moves only | Accepted 1 NEW + 1 RESOLVED for cross-repo moves |
| 2026-11-09 | R5 | Risk score moved to Sprint 3 | Protected fuzzy work; Sprint 3 stretched |
| 2026-11-16 | R6 | `triage` becomes the CI default | Structural `high` demoted to `warning`; documented with numbers |
| 2026-11-16 | R4 | No GitHub App; local SARIF + upload action | One integration surface removed |
| 2026-11-26 | R5 | Feature freeze | Only evaluation/report/video after this date |

## Closed risks — what we learned

- **R1/R7** were “boring” infrastructure risks that cost a week each if discovered late. Running
  the CI matrix and a Windows test early was cheaper than fixing identity bugs later.
- **R2** could have been “solved” by lowering the threshold until the fixtures passed. The stop
  rule prevented that: precision was measured on negative fixtures and on real code, not only on
  the happy path.
- **R6** was a product risk disguised as a technical one: the detector was right, but the gate
  policy was wrong for real repositories. The fix was a documented policy, not a code change.

## Review checklist (every Monday)

1. Did any trigger fire since the last meeting? If yes, apply the stop rule today.
2. Is every open risk ≤ 14 days from its decision date?
3. Did a closed risk reappear (e.g. after a refactor)?
4. Does the sprint plan still fit the remaining capacity?
5. Is the risk register linked from the weekly note?