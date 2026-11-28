# ADR-009: Reliability through staged fingerprint matching

- **Status:** Accepted (draft to be committed to the fork's `docs/adr/`)
- **Date:** 2026-11-06
- **NFR:** Reliability — new-smell F1 ≥ 0.85 on the frozen dataset; no false `NEW` after cosmetic
  edits, renames or moves.
- **Related:** `fingerprint.py`, `fuzzy.py`, `structure.py`, `metrics.py`, `tests/test_fuzzy.py`,
  `tests/test_structure.py`, `EVALUATION_CONTRACT.md`

## Context

The core question of the product is “is this smell new *because of this PR*?”. A line-number diff
answers a different question (“does the warning sit on a changed line?”) and fails on three common
edits: inserting lines, renaming a symbol, moving code to another module. All three change line
numbers without changing the smell.

Reliability here is not “the process does not crash”; it is “the lifecycle label is trustworthy”.
A false `NEW` wastes reviewer time and erodes trust; a false match hides real new debt, which is
worse. We therefore need an identity that is (a) deterministic, (b) insensitive to layout, and
(c) auditable when it matches two things that are not exactly equal.

## Decision

Use a **two-stage identity**:

1. **Exact stage** — fingerprint = `rule_id | normalised relative POSIX path | qualified symbol`.
   Line numbers are forbidden. A match on all three components is `UNCHANGED` (or `WORSENED`
   if the metric worsened).
2. **Fuzzy stage** — for leftovers, generate candidates and score them on symbol similarity
   (normalised edit distance), path similarity, AST shape similarity and line proximity.
   Accept at ≥ 0.62 by default. The threshold is configurable (`--fuzzy-threshold`) and the stage
   can be disabled (`--no-fuzzy`) as an escape hatch.
3. **Worsening is a separate question** — a matched finding is `WORSENED` only when its measured
   value crosses the effective threshold in head, or worsens by > 20% while already above it.
   `--no-worsen` collapses matched findings to `UNCHANGED`.

### Why the AST signature is *not* in the exact fingerprint

The first draft put the normalised AST signature in the exact key (as §4.2 of the project overview
originally described). That is self-contradictory: the edit that makes a smell `WORSENED` — adding
statements to the method — also changes its AST signature, so a worsened finding would never match
exactly and would be reported as `NEW`. `WORSENED` is defined as “same identity, larger metric”, so
identity must survive the body edit. The signature therefore enters as **similarity evidence in the
fuzzy stage**, where a partial match is allowed by design. `fingerprint.py` keeps the exact key at
`(smell_type, path, symbol)` and `structure.py` owns the signature.

Weights in the fuzzy stage (sum 1.0):

```text
score = 0.40 * symbol + 0.25 * path + 0.15 * line + 0.20 * ast
```

Gates: the symbol must reach 0.45, **unless** the AST shape reaches 0.90 and the name still shares
a fragment (≥ 0.15). That exception is what pairs a rename whose name changed completely
(`compute_total` → `tally`) while refusing two same-shaped but unrelated functions. When no
signature is available (module-level smells such as Cyclic Dependency, missing files, unparsable
files) the AST weight is dropped and the previous `0.55 / 0.30 / 0.15` blend is used unchanged, so
absence of evidence never changes the verdict.

Every match carries the score components in the explanation, so a reviewer can see *why* two
findings were paired.

## Alternatives considered

- **Line-number diff only.** Rejected: inserting a blank line turns one smell into `NEW` +
  `RESOLVED`. This is exactly Baseline B in the evaluation; it is expected to lose on the
  move/rename commits.
- **Fuzzy-only matching.** Rejected: no cheap, exact path, and it hides precision regressions;
  the exact stage is O(1) per finding and handles the majority case.
- **Match by metric value.** Rejected: two unrelated 60-line methods would match; identity and
  severity are different questions.
- **git blame / history-based identity.** Rejected: baseline mode works on a snapshot without
  history; shallow CI clones would break.
- **Lower the threshold until the fixtures pass.** Rejected as a practice; precision was measured
  on negative fixtures and on real packages before accepting 0.62.

## Consequences

- **Positive:** deterministic, testable identity; all state transitions are explainable in one
  sentence; cosmetic edits produce no noise (verified on 40 move/rename fixtures); a rename whose
  name changed completely still pairs when the body shape is intact (added 2026-11-26).
- **Neutral:** the AST signature is version-sensitive by nature; normalisation rules are pinned by
  golden tests, not by the interpreter's `ast.dump` formatting luck. Shape similarity is an
  evidence signal, never an exact key, for the `WORSENED` reason above.
- **Negative / accepted limitations:** cross-repository moves are unsupported; a function split
  into two is reported as one `RESOLVED` plus one `NEW` (documented as risk R3-adjacent); deeply
  dynamic code may not produce a stable signature.

## Verification

The [evaluation workflow](../../python_smells_detector-main/docs/evaluation-baselines.md) exports revision-specific findings for independent scoring. Long Method and Large Class also record below-threshold measurements to distinguish first crossings of existing symbols from newly introduced symbols. The saved baseline and cache carry these measurements. A unique comparable symbol and the same effective threshold are required. Older baselines can be refreshed on their accepted revision.

1. `tests/test_delta.py` — line shifts and exact-key stability (the key never carries a number).
2. `tests/test_fuzzy.py` — 40 move/rename fixtures, including negative cases (unrelated function
   next to the old line must not match).
3. `tests/test_structure.py` — normalised shape: rename keeps 1.0, docstring ≥ 0.85, module-level
   symbols have no signature, dissimilar rename pairs, different shape does not, exact key ignores
   the body (so `WORSENED` survives).
4. Mutation corpus replay (`eval-corpus-v1`) — lifecycle accuracy per focal smell.
5. Real-world sample — new-smell precision/recall against two annotators; Cohen's κ reported.
