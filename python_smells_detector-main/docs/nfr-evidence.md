# NFR evidence index

This file is the single place a report author should read before claiming an
NFR. It records what is **met**, what is **by design but not measured**, and
what must **not** be claimed. Requirements are quoted in English; the binding
wording is in `PROJECT_OVERVIEW.md` section 8.

Rule of thumb: cite ADR-008 to ADR-011 only (they are the only ADRs in this
repository), and quote numbers together with the commit that produced them.

## NFR1 - performance (ADR-008)

Requirement (translated): incremental analysis must not exceed 40 % of the
full-analysis time, **or** must stay under 30 s in the agreed environment.

Implementation: a content-addressed, whole-tree memo (`cache.py`). The key is
the sorted `(relative path, sha256)` manifest folded with the effective
threshold digest and the tool version, so findings are reused only for a tree
that is byte-identical under that configuration. ADR-008 explicitly rejects
per-file reuse, because dead code, data clumps, architectural cycles and fan-in
accumulate state across files.

| clause | earlier benchmark verdict | evidence |
| --- | --- | --- |
| relative: changed / full <= 40 % | **not met** | 102.3 % (median of 3 runs, this machine); 100.2 %, 103.3 %, 98.5 % per run / 115.7 % (earlier machine) |
| absolute: changed <= 30 s | **met** | 14.06 s median, range 12.87-14.20 s (3 runs, this machine) / 28.99 s (earlier machine); `docs/benchmarks/performance-100k.json` |
| warm / full | informational only | 0.5 % / 1.4 %; a repeated run, not an incremental one |

Do not write "incremental analysis" for the warm number. A repeated gate run on
an unchanged tree is nearly free; a one-line change pays the full cost.

Limits to state in the report: generated corpus (about 100k lines, 522 modules,
1537 findings), three runs per phase with the median reported (per-run `changed` 12.87-14.20 s), a single process, and an environment that differs from `EVALUATION_CONTRACT.md` section 8 (CPython 3.14.7 on 32 cores instead of Python 3.13 on 8 cores).

With Long Method and Large Class measurements enabled, three changed runs on a generated corpus of 100,077 lines and 522 files took 31.81, 37.12 and 28.20 s (Windows 10, Python 3.13.15, eight logical CPUs). The median was **31.81 s**, or **93.3%** of the 34.10 s full-run median. Both targets were missed on this host. An identical-tree cache hit took 0.14 s. Formal acceptance requires the tagged corpus and contract environment.

## NFR2 - reliability (ADR-009)

Requirement (translated): on the frozen evaluation dataset, F1 of the
new-smell classification must be at least 0.85.

Status: **design met, metric not evaluated.** There is no double-annotated
frozen dataset in the repository, so no F1 number exists. Do not claim 0.85 as
achieved; claim it as the target and put the gap in threats to validity.

All 24 supplementary controlled cases produced their expected focal findings, including six pure moves or renames classified `UNCHANGED`. Over the eight unlabelled repository pairs, upstream v0.3.0 reproduced all 2,501 A findings and all 40 B findings. Median displayed counts for A, B and Proposed were 313.5, 3 and 2.5. [Reproduction and scoring](evaluation-baselines.md)

What is implemented: a two-stage identity (ADR-009). Stage one is an exact
fingerprint of `rule id | normalised relative POSIX path | qualified symbol`
with line numbers forbidden. Stage two scores the leftovers on symbol
similarity, path similarity, AST shape (`structure.py`) and line proximity, with
two gates (total 0.62, symbol 0.45, AST 0.90).

Evidence that the design does what it claims (all reproducible offline):

- Rename with an unchanged body: new 1 -> 0, score 0.869.
- Move across modules: new 2 -> 0, scores 0.955 and 0.8356.
- Rename plus a rewritten body: still reported as new, i.e. the matcher does not
  force a pair.
- AST signature availability on a real corpus (flask `src/flask`, 96 findings):
  19.8 % before the qualified-symbol fix, 71.9 % after.
- All 47 rule ids are reachable from fixtures (`tests/test_rule_coverage.py`,
  `tests/fixtures/rule_coverage/`).

## SARIF conformance (NFR2, machine-readable output)

The SARIF writer is checked against the official 2.1.0 schema, not only against
its own tests. The schema is committed at
`tests/fixtures/sarif/sarif-schema-2.1.0.json` (copied from
`https://json.schemastore.org/sarif-2.1.0.json`), so validation runs offline.

| document | results | verdict |
| --- | ---: | --- |
| `tests/fixtures/sample_project`, `--format sarif --level-policy triage` | 10 | valid |
| `click` source tree, `--format sarif --all-rules` | 216 | valid |
| `pyexamine-delta`, `--format sarif --risk --include-unchanged` | 5 | valid |

The third document is the one that carries the additions this fork makes:
`baselineState` (SARIF 2.1.0 section 3.27.24), `rank` (3.27.19) and
`properties.risk`. All three are part of the schema, which is why they pass.

## Other NFRs

- Extensibility (ADR-010): a detector adapter returns the shared `Finding`
  type, so the comparison engine does not change when a detector is added.
- Usability (ADR-011): install and first run fit in the five-minute budget
  described in `docs/delta.md`.

## Verification evidence (commit level)

- Head at the time of writing: the commit that added this index (`b95e694` was the previous one).
- CI run `45838055833`: 13 of 13 jobs green in 76 s, including
  ubuntu 3.10/3.11/3.12/3.13/3.14, windows 3.13, macos 3.13, minimum
  dependencies, docs (`sphinx-build -W`), self-analysis, dependency audit and
  the wheel smoke test.
- Tests: 457 passed (`tests/`), coverage 90.53 % against a 85 % gate
  (`ci.yml`, 3.13 leg).
- Determinism: two consecutive runs of the same tree are byte-identical apart
  from the run timestamp; the SARIF baseline path uses `partialFingerprints`
  without line numbers.
- The CI workflows live at the repository **root** (`.github/workflows/ci.yml`);
  the copy inside `python_smells_detector-main/` is kept for history but GitHub
  never schedules it.

## Commands

```bash
# tests and coverage
python -m pytest tests -q
python -m pytest tests -q --cov=code_quality_analyzer --cov-fail-under=85

# performance evidence (about 30 s per phase on a 32-core machine)
python -m benchmarks.run_benchmark --root <dir> --target-lines 100000 \
  --repeat 3 --json .local-reports/performance-100k.json

# formal measurement on a disposable checkout of bench-100k-v1 on the contract host
python -m benchmarks.run_benchmark --no-generate --root <frozen-corpus-directory> \
  --repeat 3 --json .local-reports/performance-contract.json

# lifecycle evidence on a real repository
pyexamine-delta <repo> --base origin/main --head HEAD --format markdown --risk
```
