# ADR-008: Content-addressed incremental analysis cache

- **Status:** Accepted
- **Date:** 2026-11-25
- **NFR:** Performance — incremental analysis of a 100k-LOC project must stay
  under 40% of a full analysis, or under 30 seconds in the agreed environment.
- **Related:** `cache.py`, `delta.py` (`--no-cache`, `--cache-dir`)

## Context

`pyexamine-delta` runs three detectors (code, structural, architectural) over a
materialised git worktree. Parsing every `.py` file with astroid and walking
the structural/architectural graphs is the dominant cost. A pull request
usually changes a handful of files, and the base snapshot is identical across
every pull request of a repository, so re-running the detectors from scratch on
unchanged sources is wasted work that directly threatens the Performance NFR.

The NFR's suggested mechanism is "cache AST and detection results, and only
re-analyse modified files and their dependency impact scope."

## Decision

Add a persistent, **content-addressed memo of the per-tree analysis result**:

1. A tree is identified by a *manifest*: the sorted list of
   `(relative path, sha256)` pairs of every Python file the detectors observe.
   Byte-identical snapshots therefore share one entry regardless of the
   temporary worktree directory they were materialised into.
2. The cache key also folds in a digest of the effective thresholds
   (`code_smells` / `structural_smells` / `architectural_smells`) and the tool
   version, so a config change or detector upgrade invalidates the entry.
3. Findings are stored with **relative paths** and re-rooted onto the tree
   being served on load, so a hit never returns paths into a deleted worktree.
4. The project-level `fan_in` context used by risk scoring is cached alongside
   the findings.
5. The cache is a pure memo: a hit returns exactly the result a cold run would
   have produced. It is safe to delete and rebuild at any time.

The cache lives at `.pyexamine-cache/` under the repository root by default
(gitignored), overridable with `--cache-dir`, and can be disabled with
`--no-cache`.

## Alternatives considered

- **Per-file partial reuse** (re-analyse only changed files and their
  dependency impact scope). Rejected for this iteration: smells such as Dead
  Code, Data Clumps, architectural cycles and fan-in/out accumulate state
  across files, so skipping unchanged files would silently change results
  without a detector-level refactor that separates "local findings" from
  "cross-file contributions". The whole-tree memo keeps correctness by
  construction.
- **Git object-keyed cache** (key by commit/tree OID). Rejected in favour of
  content addressing: two different commits with identical content should share
  work, and content addressing needs no repository state, which makes the cache
  portable and simpler to invalidate.
- **No cache, rely on one-tree baseline mode only.** Insufficient: baseline
  mode removes the second analysis but still re-parses the whole head tree on
  every run.

## Consequences

- **Positive:** repeated gate runs on unchanged sources become O(manifest
  hashing) instead of O(parse + walk); the base snapshot is analysed once per
  repository state and reused across every pull request.
- **Neutral:** a cold run is unchanged (manifest hashing is negligible), and
  the cache file grows with the number of distinct tree contents.
- **Negative:** a *changed* head still triggers a full analysis; per-file
  partial reuse remains future work gated on a detector refactor.

## Measurement protocol (for the evaluation report)

1. Freeze a 100k-LOC benchmark and record the full-analysis time `T_full`.
2. Run `pyexamine-delta --baseline-mode diff` twice on the same head; the
   second run must be dominated by hashing and the diff, not by the detectors.
3. Report the warm incremental time against both NFR targets
   (≤ 40% of `T_full`, or ≤ 30 s).
