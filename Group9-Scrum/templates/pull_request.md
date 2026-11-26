## What & why

Closes #<issue>

<One paragraph: the user-visible change and why it is needed. Link the story id.>

## Acceptance criteria

- [ ] AC-1: <criterion> — test: `tests/test_x.py::test_y`
- [ ] AC-2: <criterion> — test: `tests/test_x.py::test_z`

## How verified

```text
$ python -m pytest tests -q
431 passed

$ ruff check src tests
All checks passed
```

<Manual checks, e.g. CLI output excerpt.>

## Behaviour / risk

- [ ] No default, threshold or output-format change
- [ ] If changed: `docs/delta.md` + `CHANGELOG.md` updated in this PR
- [ ] Risk register / ADR updated if an NFR is touched

## Review

- [ ] Reviewed by a member who did not author this PR
- [ ] Scope matches the story (no drive-by refactors)
- [ ] Tests fail if the acceptance behaviour regresses

## Screenshots / output (optional)

<PR summary, SARIF snippet, gate message.>