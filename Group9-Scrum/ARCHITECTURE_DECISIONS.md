# Architecture Decisions for the Non-Functional Requirements

The course requires each selected NFR to be addressed by **a software architectural design option
with a rationale**. This project selects four NFRs (a 6-person team needs at least two). The
decisive ADR for performance (`ADR-008`) lives in the fork at
`docs/adr/ADR-008-performance-incremental-cache.md`; the other three are drafted here and should
be committed to the fork's `docs/adr/` folder.

## Summary

| NFR | Design option | Rejected alternatives | Why this option | Consequence accepted | ADR |
| --- | --- | --- | --- | --- | --- |
| **Performance**: warm run ≤ 40% of full, or ≤ 30 s on 100k LOC | Content-addressed **whole-tree analysis memo**: key = sorted `(path, sha256)` manifest + threshold digest + tool version; results cached with relative paths | (a) per-file partial reuse; (b) cache keyed by git commit OID; (c) baseline mode only | Cross-file smells (cycles, data clumps, fan-in/out) accumulate state, so skipping files silently changes results; whole-tree memo is correct by construction and turns repeated gate runs into hashing | A changed head still triggers a full analysis; per-file incrementality is future work gated on a detector refactor | [ADR-008](../CityU-SE_Project_Group9-main/CityU-SE_Project_Group9-main/python_smells_detector-main/docs/adr/ADR-008-performance-incremental-cache.md) (in fork) |
| **Reliability**: F1 ≥ 0.85; no false NEW after cosmetic moves | **Two-stage identity**: exact fingerprint (rule + normalised path + qualified symbol + AST signature), then scored fuzzy matching with an explicit threshold and escape hatches | (a) line-number diff; (b) fuzzy-only; (c) metric-value matching | Line numbers are provably unstable under insertions; fuzzy-only has no cheap exact path and hides precision problems; metric values conflate identity with severity | Cross-repository moves are unsupported; a function split in two remains a known false-NEW case | `adr/ADR-009-reliability-staged-matching.md` |
| **Extensibility**: new detector without touching the comparison engine | **Detector Adapter + unified `Finding` + stable rule registry** (`pyex-<category>-<slug>`, 47 ids) | (a) fork each detector's diff logic; (b) let each detector emit its own diff format; (c) dynamic plugin discovery | The fork must inherit upstream detectors untouched; a normalised finding boundary keeps the delta engine detector-agnostic and testable | Detector-specific nuances (e.g. dead code across files) must be expressed as metrics or metadata on `Finding` | `adr/ADR-010-extensibility-detector-adapter.md` |
| **Usability**: install → run → interpret in 5 minutes | **Single-command CLI with PR-native outputs**: text/JSON/Markdown/SARIF, explainable risk, quick-start docs; no web UI | (a) web dashboard; (b) IDE plugin; (c) GitHub App | The tool is used inside an existing PR workflow; a CLI plus native outputs removes a second surface to secure, test and host; a UI was also a stated non-goal | Interpretation quality depends on the explanation text, which must be maintained like code | `adr/ADR-011-usability-cli.md` |

## How the options interact

The four decisions are deliberately layered so that they do not fight each other:

1. **Finding** (extensibility) is the data boundary. Everything downstream — fingerprints, cache,
   risk, SARIF — consumes `Finding`, never detector internals.
2. **Identity** (reliability) is a pure function of a `Finding`, so it is unit-testable without a
   repository and independent of detector upgrades.
3. **Cache** (performance) memoises the *detector output for a tree*, not the identity result.
   That keeps cache correctness independent of matching heuristics; invalidating on threshold or
   version digest is enough.
4. **CLI/report** (usability) is a thin presentation layer. It never contains matching logic, so a
   new output format cannot change a state.

## Trade-offs we consciously did not take

- **Per-file incremental analysis** would be faster but is incorrect for cross-file smells without
  splitting detector state into “local” and “cross-file contributions”. Deferred, documented.
- **A learned risk model** would fit rankings better but needs labels we do not have at this scale;
  fixed weights are auditable and explainable.
- **A web UI** would look impressive in a demo but is not used by a reviewer inside a PR and would
  consume the evaluation budget.
- **Deriving identity from git blame** would be accurate for moves but ties the tool to repository
  history and breaks baseline mode (no history in shallow clones).

## Verification map

| Decision | How we verify it |
| --- | --- |
| Cache correctness | `tests/test_cache.py`: hit equals cold run; invalidation on threshold/version change |
| Identity stability | `tests/test_fingerprint.py`: line shifts, renames, docstring edits |
| Matching precision | `tests/test_fuzzy.py` negative fixtures + precision sample on `site-packages` |
| Adapter boundary | `tests/test_rule_coverage.py`: all 47 rule ids; a detector can be added without editing `delta.py` |
| Usability | quick-start executed on a clean clone; demo script ≤ 10 minutes |