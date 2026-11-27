# Group 9 — Scrum Evidence Package

**Project:** PyExamine-Delta — change-aware, context-adaptive code-smell detection for Python
pull requests (fork of PyExamine 0.3.0) · **Course:** CS5351 Software Engineering, CityU (DG) ·
**Team:** 6 students (M1–M6 placeholders) .

| Code | Name         | Role |
| --- |--------------| --- |
| M1 | ChenShikai   | Product Owner |
| M2 | XieQin       | Scrum Master |
| M3 | HuangYiguo   | Lead developer |
| M4 | LiuYuxuan    | Developer |
| M5 | ChenZirui    | Developer |
| M6 | HuangMinghui | Developer / test owner |

This folder contains the Scrum artefacts required by the course project: product backlog with user
stories and acceptance criteria, sprint plans and backlogs, three sprint burndowns plus a project
burndown, velocity, weekly standing-meeting notes, a risk register with stop rules, a definition of
done, a frozen evaluation contract, a requirement-to-result traceability matrix and the relative
contribution table.

## Start here

| If you want to … | Open |
| --- | --- |
| See the burndown dashboard | [`burndown.html`](burndown.html) |
| Read the stories and acceptance criteria | [`PRODUCT_BACKLOG.md`](PRODUCT_BACKLOG.md) |
| Check the sprint goals, capacity and change log | [`SPRINT_PLAN.md`](SPRINT_PLAN.md) |
| Audit a sprint | [`sprints/sprint-1.md`](sprints/sprint-1.md) · [2](sprints/sprint-2.md) · [3](sprints/sprint-3.md) |
| Read the weekly evidence | [`meetings/week-02.md`](meetings/week-02.md) … [`week-13.md`](meetings/week-13.md) |
| See risks and stop rules | [`RISK_REGISTER.md`](RISK_REGISTER.md) |
| Check the quality bar | [`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md) |
| Trace a requirement to code/tests | [`TRACEABILITY.md`](TRACEABILITY.md) · [`ISSUE_LOG.md`](ISSUE_LOG.md) |
| Check the frozen evaluation | [`EVALUATION_CONTRACT.md`](EVALUATION_CONTRACT.md) |
| Check NFR architecture decisions | [`ARCHITECTURE_DECISIONS.md`](ARCHITECTURE_DECISIONS.md) · [`adr/`](adr/) |
| See the contribution split | [`CONTRIBUTIONS.md`](CONTRIBUTIONS.md) |
| Set up the GitHub board the same way | [`GITHUB_WORKFLOW.md`](GITHUB_WORKFLOW.md) · [`templates/`](templates/) |

## Project at a glance

| Item | Value |
| --- | --- |
| Product | `pyexamine-delta`: base/head analysis, stable fingerprints, fuzzy rename/move matching, calibrated thresholds, explainable risk, SARIF/Markdown, CI gate, cache |
| Baseline | PyExamine 0.3.0 (`code-quality-analyzer`), three detectors, 47 stable rule ids |
| Story scope | 5 epics · 19 user stories · **72 SP** · 64 SP accepted by 2026-11-26 |
| Sprints | S1 W2–W5 (Sep 14–Oct 9), S2 W6–W9 (Oct 12–Nov 6), S3 W10–W13 (Nov 9–Dec 4) |
| Velocity | 21 / 21 / 30 SP (S3 forecast) |
| Quality (repo, 2026-11-25) | 431 tests passed (216 upstream + 215 new), `ruff` clean, 18 test files |
| Compatibility | default text 967 bytes / JSON 5366 bytes identical to upstream v0.3.0 |
| NFRs | performance (cache), reliability (staged identity), extensibility (adapter + registry), usability (CLI + PR-native output) |
| Evaluation | frozen 2026-11-06: 6 repos, 68 PRs, 24-commit mutation corpus, baselines A/B, κ reported |

## Calendar (course weeks)

| Week | Date (Mon) | Sprint | Event | Evidence |
| --- | --- | --- | --- | --- |
| W2 | Sep 14 | S1 | Kickoff, planning | `week-02.md` |
| W3 | Sep 21 | S1 | Baseline decision | `week-03.md` |
| W4 | Sep 28 | S1 | Fingerprint decision | `week-04.md` |
| W5 | Oct 5 | S1 | Review + retro | `week-05.md`, `sprint-1.md` |
| W6 | Oct 12 | S2 | Planning | `week-06.md` |
| W7 | Oct 19 | S2 | WORSENED / fuzzy decisions | `week-07.md` |
| W8 | Oct 26 | S2 | Calibration study | `week-08.md` |
| W9 | Nov 2 | S2 | Review; contract frozen | `week-09.md`, `sprint-2.md` |
| W10 | Nov 9 | S3 | Planning | `week-10.md` |
| W11 | Nov 16 | S3 | Gate policy | `week-11.md` |
| W12 | Nov 23 | S3 | Cache accepted; evaluation starts | `week-12.md` |


## Folder layout

```text
Group9-Scrum/
├─ README.md                        # this index
├─ PRODUCT_BACKLOG.md               # 5 epics, 19 stories, ACs, NFR table, non-goals
├─ SPRINT_PLAN.md                   # capacity, ceremonies, goals, change log, dependencies
├─ sprints/
│  ├─ sprint-1.md                   # backlog, burndown checkpoints, review, retro
│  ├─ sprint-2.md
│  └─ sprint-3.md
├─ meetings/
│  └─ week-02.md … week-13.md       # weekly standing-meeting notes
├─ BURNDOWN.md                      # method, data dictionary, interpretation
├─ data/
│  ├─ burndown-sprint-1.csv         # day,date,remaining_sp,forecast,today,note
│  ├─ burndown-sprint-2.csv
│  ├─ burndown-sprint-3.csv
│  ├─ burndown-project.csv          # weekly checkpoints
│  └─ velocity.csv
├─ charts/
│  ├─ burndown-sprint-1.svg … burndown-sprint-3.svg
│  ├─ burndown-project.svg
│  └─ velocity.svg
├─ burndown.html                    # self-contained dashboard (inline SVG + tables)
├─ tools/make_burndown.py           # regenerates charts + dashboard from CSV
├─ RISK_REGISTER.md                 # 13 risks, triggers, stop rules, decision log
├─ DEFINITION_OF_DONE.md            # DoR, story/sprint/release DoD, review checklist
├─ TRACEABILITY.md                  # story → FR/NFR → module → test → issue/PR
├─ ISSUE_LOG.md                     # board snapshot, 19 stories + support issues
├─ EVALUATION_CONTRACT.md           # frozen task/data/baselines/metrics/thresholds
├─ ARCHITECTURE_DECISIONS.md         # NFR → option → alternatives → rationale
├─ adr/
│  ├─ ADR-009-reliability-staged-matching.md
│  ├─ ADR-010-extensibility-detector-adapter.md
│  └─ ADR-011-usability-cli.md
├─ CONTRIBUTIONS.md                 # hours, ratios, worked example, declarations
├─ GITHUB_WORKFLOW.md               # labels, templates, weekly routine, audit checklist
└─ templates/
   ├─ issue-story.md
   └─ pull_request.md
```

## How the deliverables map to the course requirements

| Requirement (project PDF) | Where |
| --- | --- |
| Develop user stories (Sprint 1 activity) | `PRODUCT_BACKLOG.md` §5 (19 stories, Gherkin ACs) |
| Agile with ≥ 3 sprint cycles | `SPRINT_PLAN.md`, `sprints/` (S1 W2–5, S2 W6–9, S3 W10–13) |
| ≥ 1 standing meeting per week | `meetings/week-02.md` … `week-12.md` (+ W13) |
| Burndown chart | `BURNDOWN.md`, `charts/*.svg`, `burndown.html`, `data/*.csv` |
| 2+ NFRs each with an architectural option + rationale | `PRODUCT_BACKLOG.md` §6, `ARCHITECTURE_DECISIONS.md`, `adr/`, fork `docs/adr/ADR-008` |
| Code, test, review, technical debt tracking | `sprints/*.md` task tables, `DEFINITION_OF_DONE.md`, `RISK_REGISTER.md` R3/R5 |
| Risk register and stop rules | `RISK_REGISTER.md` |
| Baseline → change → measure | `EVALUATION_CONTRACT.md` (baselines A/B, metrics, thresholds) |
| Trace requirement to result | `TRACEABILITY.md`, `ISSUE_LOG.md`, `GITHUB_WORKFLOW.md` §8 |
| Freeze the evaluation contract | `EVALUATION_CONTRACT.md` §1, §11 |
| Weekly repository evidence | `GITHUB_WORKFLOW.md` §7 (routine), `meetings/` |
| Relative contribution (pro-rated) | `CONTRIBUTIONS.md` §3 |
| Self-reflection / process improvement | sprint retro sections + `SPRINT_PLAN.md` §6 |

## Keeping it current

```bash
# 1) edit the daily row(s) in data/burndown-sprint-N.csv (remaining_sp, forecast, today, note)
# 2) regenerate every chart and the dashboard
python tools/make_burndown.py
```

Rules: burn a point only when the story is accepted (tests + review + DoD); flip `forecast` to `0`
when a day becomes history; move the `today` flag to the current working day; commit CSV + charts
together.

## Data provenance — read before submitting


| Source | Items |
| --- | --- |
| **Verified in the repository (2026-11-25/26)** | 431 tests, 18 test files, 47 rule ids, 3 detectors, 12 delta modules (~3.6k LOC), text 967 B / JSON 5366 B compatibility, ADR-008 date and content, delta CLI flags, `docs/ci` knobs, p90 risk 34–40, structural share 53–72% |
| **Planning records in this package (review before submitting)** | Story points, hours, meeting dates/attendance/decisions, issue and PR numbers, annotation progress (42/68), κ target, benchmark tag names |
| **To fill in by the team** | Real member names and student IDs, real GitHub issue/PR numbers, final evaluation values, final κ, release tag, signatures in `CONTRIBUTIONS.md` |



