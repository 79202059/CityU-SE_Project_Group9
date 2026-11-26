# Repository & Board Workflow

This document is the operating manual for keeping the Scrum evidence inside GitHub. It is written
so that a reader can reconstruct the board and audit a story end-to-end.

## 1. Repository layout

```text
CityU-SE_Project_Group9/
├─ README.md                 # team log + ideas
├─ PROJECT_OVERVIEW.md       # problem statement, FR/NFR, evaluation plan
├─ docs/
│  ├─ delta.md               # user-facing tool documentation
│  ├─ ci/                    # workflow + integration guide
│  ├─ adr/                   # architecture decision records
│  └─ meetings/              # weekly standing-meeting notes (copy of meetings/)
├─ src/code_quality_analyzer/  # upstream detectors + delta modules
├─ tests/                    # 431 tests (216 upstream + 215 new)
└─ eval/                     # frozen corpus, dataset list, labels, scripts
```

The Scrum package (`PRODUCT_BACKLOG.md`, `SPRINT_PLAN.md`, `sprints/`, `meetings/`,
`RISK_REGISTER.md`, …) is committed to `docs/scrum/` so that the report can cite repository paths.

## 2. Labels

| Group | Labels |
| --- | --- |
| Type | `type/story`, `type/task`, `type/bug`, `type/adr`, `type/docs`, `type/eval` |
| Epic | `epic/E1-core`, `epic/E2-identity`, `epic/E3-context`, `epic/E4-gate`, `epic/E5-quality` |
| Priority | `prio/must`, `prio/should`, `prio/could` |
| Size | `sp/1`, `sp/2`, `sp/3`, `sp/5`, `sp/8` |
| State | `state/blocked`, `state/needs-review`, `state/carry-over` |
| Risk | `risk/R2`, `risk/R6`, … (only when an issue is the mitigation owner) |

## 3. Milestones and board

| Milestone | Due | Content |
| --- | --- | --- |
| `Sprint 1` | 2026-10-09 | US-01…US-07 |
| `Sprint 2` | 2026-11-06 | US-08…US-12 |
| `Sprint 3` | 2026-12-04 | US-13…US-19 + wrap-up |
| `1.0.0` | 2026-12-04 | release checklist |

Board columns: **Backlog → Ready → In progress → In review → Done**. WIP limit: 3 cards in
`In progress` per member, 2 in `In review` overall (review latency was the Sprint 1 bottleneck).

## 4. Issue template (story)

```markdown
### Story
As a <persona>, I want <capability> so that <benefit>.

### Acceptance criteria
- [ ] Given …, when …, then …
- [ ] Given …, when …, then …

### Scope
- Modules:
- Tests to extend:
- Out of scope:

### Estimate
SP: <1|2|3|5|8>   Epic: <E1…E5>   Priority: <M|S|C>

### Evidence plan
- Demo step:
- NFR/ADR (if any):
```

## 5. Pull request template

```markdown
## What & why
Closes #<issue>

## Acceptance criteria
- [ ] AC-1 … (test: `tests/test_x.py::test_y`)
- [ ] AC-2 …

## How verified
```
$ python -m pytest tests -q
431 passed
$ ruff check src tests
All checks passed
```

## Risk / behaviour change
- [ ] No default/threshold/format change
- [ ] Docs updated (`docs/delta.md`, `docs/ci/README.md`, `CHANGELOG.md`)

## Review
- [ ] Reviewed by someone who did not author this PR
```

## 6. Branch and commit conventions

- Branches: `story/us-09-fuzzy-matching`, `fix/cache-invalidation`, `docs/adr-009`.
- Commits: imperative subject, ≤ 72 characters, body explains the *why*; reference the issue
  (`Refs #9`).
- One story per PR. A PR touching more than three modules is split unless it is a mechanical
  rename.
- No force-push to `main`; no direct commits to `main` after Sprint 1 starts (the scaffolding PR
  is the only exception).

## 7. Weekly evidence routine (the graded part)

Every week, before Monday 23:59:

| Step | Owner | Artefact |
| --- | --- | --- |
| 1. Hold the standing meeting (Mon 20:00, 30 min) | M2 | `meetings/week-XX.md` |
| 2. Update remaining story points in `data/burndown-sprint-N.csv` | M2 | CSV row for the meeting date |
| 3. Regenerate the chart and dashboard | M2 | `charts/*.svg`, `burndown.html` |
| 4. Move cards on the board; comment on blocked issues | all | board state |
| 5. Merge at least one reviewed PR per active story | owners | PR with `Closes #N` |
| 6. Review the risk register; apply a stop rule if a trigger fired | M2 | `RISK_REGISTER.md` |
| 7. Commit the week's evidence in one `chore: week-XX evidence` commit | M2 | repo history |

Weekly commit messages: `chore: week-05 evidence (S1 review, 2 SP left)`.

## 8. Traceability rules

1. Every story has exactly one issue (US-id in the title).
2. Every issue is closed by a PR with `Closes #N` — no manual closes.
3. Every AC has a test name in the PR body; a reviewer can run it.
4. Sprint review notes list, per story: accepted / returned / carried over, with the reason.
5. The contribution table is derived from task ownership + hours, not from commit counts.

## 9. Evidence audit (at each sprint review)

- [ ] Milestone closed; no open issue without a comment explaining where it went.
- [ ] Every merged PR since the last review links an issue and a test command.
- [ ] Burndown and velocity data updated; chart matches the data.
- [ ] Weekly notes exist for all weeks in the sprint and contain attendance.
- [ ] Risk register reviewed; at least one decision date updated.
- [ ] `python -m pytest tests -q` and `ruff check src tests` green at the reviewed commit.
- [ ] ADR status reflects reality (accepted / draft / superseded).

## 10. Release checklist (1.0.0)

- [ ] Tag `1.0.0`; `CHANGELOG.md` entry; version bumped in `pyproject.toml`.
- [ ] `pip install -e .` in a clean venv; run the quick start.
- [ ] Attach the demo video and slides to the release notes.
- [ ] Archive the frozen corpus tag and evaluation outputs.
- [ ] Confirm the report cites the tag and the commit hash.