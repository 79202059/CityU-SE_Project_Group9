# ADR-009: Reliability through staged fingerprint matching

- **Status:** Accepted (draft to be committed to the fork's `docs/adr/`)
- **Date:** 2026-11-06
- **NFR:** Reliability — new-smell F1 ≥ 0.85 on the frozen dataset; no false `NEW` after cosmetic
  edits, renames or moves.
- **Related:** `fingerprint.py`, `fuzzy.py`, `metrics.py`, `tests/test_fingerprint.py`,
  `tests/test_fuzzy.py`, `EVALUATION_CONTRACT.md`

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

1. **Exact stage** — fingerprint = `rule_id | normalised relative POSIX path | qualified symbol |
   normalised AST signature`. Line numbers are forbidden. A match on all four components is
   `UNCHANGED` (or `WORSENED` if the metric worsened).
2. **Fuzzy stage** — for leftovers, generate candidates and score them on symbol similarity
   (normalised edit distance), path similarity, AST similarity, line proximity and metric range.
   Accept at ≥ 0.62 by default. The threshold is configurable (`--fuzzy-threshold`) and the stage
   can be disabled (`--no-fuzzy`) as an escape hatch.
3. **Worsening is a separate question** — a matched finding is `WORSENED` only when its measured
   value crosses the effective threshold in head, or worsens by > 20% while already above it.
   `--no-worsen` collapses matched findings to `UNCHANGED`.

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
  sentence; cosmetic edits produce no noise (verified on 40 move/rename fixtures).
- **Neutral:** the AST signature is version-sensitive by nature; normalisation rules are pinned by
  golden tests, not by the interpreter's `ast.dump` formatting luck.
- **Negative / accepted limitations:** cross-repository moves are unsupported; a function split
  into two is reported as one `RESOLVED` plus one `NEW` (documented as risk R3-adjacent); deeply
  dynamic code may not produce a stable signature.

## Verification

1. `tests/test_fingerprint.py` — line shifts, renames, docstring-only edits, file moves.
2. `tests/test_fuzzy.py` — 40 move/rename fixtures, including negative cases (unrelated function
   next to the old line must not match).
3. Mutation corpus replay (`eval-corpus-v1`) — lifecycle accuracy per focal smell.
4. Real-world sample — new-smell precision/recall against two annotators; Cohen's κ reported.