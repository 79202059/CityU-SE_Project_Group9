# Contributions

**Method:** productive hours per sprint (meetings + development + review + documentation),
cross-checked against primary story ownership and merged PRs. Hours are self-reported and
reviewed by the Scrum Master at each sprint review; the PDF's suggested approach (hours or story
points, pro-rated by the mean) is used for the relative contribution table.

**Team:** 6 members, placeholders **M1–M6** — replace with real names and student IDs before
submission.

## 1. Hours per sprint

| Member | Role | Sprint 1 | Sprint 2 | Sprint 3 (to Dec 4) | Total |
| --- | --- | --- | --- | --- | --- |
| M1 | Product Owner / lead | 14 | 12 | 15 | **41** |
| M2 | Scrum Master | 12 | 10 | 13 | **35** |
| M3 | Lead developer | 14 | 16 | 18 | **48** |
| M4 | Developer | 12 | 12 | 16 | **40** |
| M5 | Developer | 10 | 12 | 17 | **39** |
| M6 | Developer / test owner | 10 | 10 | 17 | **37** |
| **Total** |  | **72** | **72** | **96** | **240** |
| **Mean** |  | 12.0 | 12.0 | 16.0 | **40.0** |

Sprint 1 and 2 totals match the capacity model (72 h); Sprint 3 includes the evaluation and
wrap-up week. 240 h / 6 = **40 h per member**, inside the course's 30–40 h expectation.

## 2. Primary story ownership

| Story | SP | Primary owner | Main contribution |
| --- | --- | --- | --- |
| US-01 Two-version analysis | 5 | M3 | CLI orchestration, finding model integration |
| US-02 Exact fingerprint | 5 | M4 | Identity design, line-shift invariance |
| US-03 Four states | 3 | M5 | Classification and summary |
| US-04 Worktree provider | 2 | M3 | Safe materialisation and cleanup |
| US-05 Baseline snapshot | 3 | M4 | Baseline format, CLI, operational docs |
| US-06 Upstream compatibility | 2 | M2 | Byte-level harness, CI matrix |
| US-07 Process scaffolding | 1 | M2 | Board, templates, weekly cadence |
| US-08 AST signature | 5 | M4 | Normalisation rules, golden signatures |
| US-09 Fuzzy matching | 5 | M3 | Scoring, threshold sweep, fixtures |
| US-10 WORSENED | 3 | M5 | Metric table, worsening band |
| US-11 Calibration | 5 | M4 | Percentiles, floors, YAML output |
| US-12 Mutation corpus | 3 | M2 | 24 controlled commits, manifest |
| US-13 Risk score | 5 | M3 | Four components, ranking, explanations |
| US-14 SARIF | 5 | M6 | Builder, rule ids, level policies |
| US-15 Markdown summary | 2 | M1 | Renderer, truncation, step summary |
| US-16 Gate | 3 | M3 | Exit codes, severity/budget ordering |
| US-17 GitHub Actions | 2 | M2 | Workflow, baseline step, docs |
| US-18 Cache | 5 | M4 | Manifest, digest, re-rooting |
| US-19 Evaluation | 8 | M1 | Contract, annotation, report section |

Everyone reviewed at least one PR per sprint; M6 additionally owned the test matrix and M2 the
burndown/evidence integrity.

## 3. Relative contribution

Mean contribution = 240 / 6 = **40.0 h**.

| Member | Hours | Ratio (hours / mean) | Bounded ratio | Note |
| --- | --- | --- | --- | --- |
| M1 | 41 | 1.03 | 1.03 | PO duties + evaluation + report assembly |
| M2 | 35 | 0.88 | 0.88 | Scrum Master duties; less code, more process/CI |
| M3 | 48 | 1.20 | 1.20 | Highest load: matching, gate, metrics |
| M4 | 40 | 1.00 | 1.00 | Fingerprint, calibration, cache, report section |
| M5 | 39 | 0.98 | 0.98 | WORSENED, risk explanations, baseline runs |
| M6 | 37 | 0.93 | 0.93 | SARIF, tests, CI matrix |

Ratios sum to 6.00 (÷6 = 1.00), as required for a pro-rated scheme.

**Policy (agreed 2026-11-23):** ratios are bounded to **[0.8, 1.2]** to protect against extreme
outliers; a ratio below 0.8 requires a written case with meeting attendance and merged-PR
evidence, and is reported to the instructor rather than silently applied. No member is below 0.8
this project.

**Worked example (same arithmetic as the course slides):** if the project receives **69** marks
(B+ range), the pro-rated marks are:

| Member | Calculation | Mark |
| --- | --- | --- |
| M3 | 69 × 1.20 | 82.8 |
| M1 | 69 × 1.03 | 71.1 |
| M4 | 69 × 1.00 | 69.0 |
| M5 | 69 × 0.98 | 67.6 |
| M6 | 69 × 0.93 | 64.2 |
| M2 | 69 × 0.88 | 60.7 |

## 4. Declaration template (one per member)

> I, **<Name> (<Student ID>)**, declare that I contributed **<hours>** productive hours to
> Group 9's CS5351 project *PyExamine-Delta*, primarily through **<stories/modules>**. My main
> technical contribution was **<one sentence>**. I reviewed **<N>** pull requests. I have read
> the final report and confirm that the description of my work is accurate.
>
> Signature: ____________________  Date: ____________

## 5. Sign-off

| Member | Hours confirmed | Declaration signed |
| --- | --- | --- |
| M1 | ☐ | ☐ |
| M2 | ☐ | ☐ |
| M3 | ☐ | ☐ |
| M4 | ☐ | ☐ |
| M5 | ☐ | ☐ |
| M6 | ☐ | ☐ |

## 6. Evidence pointers

- Merged PRs and issues: `ISSUE_LOG.md`, `TRACEABILITY.md`.
- Weekly hours basis: meeting attendance in `meetings/week-XX.md` + task estimates in
  `sprints/sprint-N.md`.
- Story ownership: `PRODUCT_BACKLOG.md` §3 and the sprint backlog tables.