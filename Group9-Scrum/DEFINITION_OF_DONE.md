# Definition of Ready & Definition of Done

## 1. Definition of Ready (DoR)

A story enters a sprint only if all boxes are ticked. The Product Owner checks at planning; the
Scrum Master can send a story back.

- [ ] Persona, goal and benefit are written (“As …, I want …, so that …”).
- [ ] At least two acceptance scenarios in Given/When/Then form, each with an observable output
      (report line, exit code, file, test id).
- [ ] Impacted modules and the test file to extend are named.
- [ ] Estimated ≤ 8 SP, with the estimate agreed by at least two members.
- [ ] Dependencies are merged or scheduled earlier in the same sprint.
- [ ] Non-goals for the story are explicit enough to reject scope creep in review.
- [ ] For NFR stories: the architectural option, the metric and the measurement protocol are
      named (link to ADR).
- [ ] A demo step is defined: how the story will be shown at the sprint review.

## 2. Definition of Done (story level)

A story is **Done** only when every item holds:

1. **Acceptance scenarios are automated.** Each AC maps to at least one test in `tests/`; manual
   checks are allowed only for CLI ergonomics and are recorded in the PR body.
2. **Full suite green.** `python -m pytest tests -q` passes on the CI matrix (Linux 3.10–3.14,
   Windows/macOS 3.13). Final count at submission: 431 tests.
3. **Lint clean.** `ruff check src tests` reports no issues.
4. **Upstream behaviour unchanged.** For default invocations, text (967 bytes) and JSON
   (5366 bytes) on `tests/fixtures/sample_project` remain byte-identical to v0.3.0; the
   compatibility test is part of the suite.
5. **Documentation touched.** If a flag, default or output format changed, `docs/delta.md` (and
   `docs/ci/README.md` when the gate is affected) is updated **in the same PR**.
6. **Reviewed by someone else.** One approving review from a member who did not author the
   change; review comments resolved; no self-merge except for a documented hotfix.
7. **Traceability.** PR body contains `Closes #<issue>`, the AC checklist, and the commands run
   with their results. The issue is closed automatically.
8. **Deterministic evidence.** No flaky test: a rerun of the failing test three times must pass
   before the PR is merged; flaky tests are fixed or quarantined with an issue.
9. **No silent behaviour change.** Any change to a threshold, weight or default is stated in the
   PR body and in `CHANGELOG.md`, and is reflected in the risk register or ADR if it affects an
   NFR.
10. **Cross-platform sanity.** Paths are relative POSIX; temp worktrees are cleaned up; no test
    depends on the developer's absolute path.

## 3. Definition of Done (sprint level)

- [ ] Every committed story meets the story-level DoD, or is explicitly returned to the backlog
      with a written reason (no “90% done” stories).
- [ ] Burndown CSV updated through the last working day; chart regenerated.
- [ ] Sprint review executed with the demo script; verdict per story recorded in
      `sprints/sprint-N.md`.
- [ ] Retrospective held; 2–4 actions with owners and due dates; previous actions reviewed.
- [ ] Weekly notes committed for every week of the sprint; attendance and decisions recorded.
- [ ] Risk register reviewed; triggers evaluated; decisions logged.
- [ ] Milestone closed; open issues moved to the next milestone with a comment explaining why.
- [ ] Velocity recorded in `data/velocity.csv`.

## 4. Definition of Done (release level, 1.0.0)

- [ ] `pyexamine-delta` installs from a clean environment (`pip install -e .`) and runs the
      quick-start commands in `docs/delta.md`.
- [ ] The five focal smells are covered by the delta engine; the remaining rules reuse upstream
      defaults without modification.
- [ ] Gate, SARIF, Markdown, JSON and text outputs demonstrated end-to-end on a real PR.
- [ ] Evaluation contract executed; results reproducible from the committed scripts and the
      `eval-corpus-v1` tag.
- [ ] Performance NFR measured against ADR-008's protocol and reported honestly (including a
      negative result if applicable).
- [ ] Final report, slides, demo video and contribution table complete; repository evidence
      index links every sprint.

## 5. Review checklist (what a reviewer must verify)

| Area | Check |
| --- | --- |
| Semantics | Does the change do exactly what the story says, no more? |
| Identity | Does any change to fingerprinting keep line numbers out of the identity? |
| Determinism | Is ordering deterministic (no set iteration in output)? |
| Cache | Does a cache hit return the cold-run result after a threshold change? (invalidate) |
| Gate | Are exit codes still 0/1/2 and is severity evaluated before budget? |
| Output | Do default text/JSON outputs stay byte-identical to upstream? |
| Docs | Are the two baseline traps still documented and true? |
| Tests | Does each new AC have a test that fails if the behaviour regresses? |

## 6. Evidence required per story (for the final report)

1. Issue with AC and estimate.
2. Merged PR with review discussion.
3. Test names (and the command) proving each AC.
4. A line in the weekly note mentioning the merge.
5. ADR/risk update if the story touched an NFR, a default or a known limitation.