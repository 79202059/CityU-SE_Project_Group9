# Performance measurement: 100k-line warm analysis (NFR)

Measured on 2026-11-26 as the evidence for the performance NFR in
`PROJECT_OVERVIEW.md` §8: **a warm analysis of a 100k-line project must finish
in ≤ 40% of the full-analysis time, or in ≤ 30 s.**

Machine: Windows 10 (10.0.26300), CPython 3.11.4, 16 logical CPUs
(AMD64 Family 23 Model 104), SSD. One run per phase, single process, no
parallelism.

## Corpus

The corpus is **generated, not a real repository**
(`benchmarks/generate_100k.py`, deterministic):

- 522 modules, 100,077 lines under `bench/` (10 sub-packages, ~40 modules each).
- Each module: module docstring, 2–4 chained `from bench.subX import modYYY`
  imports, three module-level functions (40/30/60 lines, containing 6/3/8
  branches) and one class with 8 methods × 12 lines.
- The shape targets the detectors that dominate cost: long methods, large
  classes, high branch counts, import graphs for cycles and fan-in/out.
- Total findings produced by the full analysis: 1,537.

## Protocol

`benchmarks/run_benchmark.py` runs four phases against the same tree:

| phase | what it does | what it represents |
| --- | --- | --- |
| full | `analyze_tree` with no cache | detector cost, the NFR denominator |
| cold | new empty cache directory, one run | first run of a new tree (hashing + write) |
| warm | same tree, same cache, second run | repeated CI gate run on an unchanged tree |
| changed | append one line to one module, then rerun | a PR that touches a single file |

The warm phase asserts that it reports the same number of findings as `full`,
so a fast warm run cannot be fast by skipping work it should have done.

## Result

| phase | seconds | vs full |
| --- | ---: | ---: |
| full (no cache) | 25.06 | 100% |
| cold (cache write) | 22.55 | 90% |
| **warm (cache hit)** | **0.36** | **1.4%** |
| changed (memo miss) | 28.99 | 116% |

Verdict: **PASS** — warm is 1.4% of full (target ≤ 40%) and 0.36 s in absolute
terms (target ≤ 30 s). A 20k-line run of the same protocol gave 4.40 s full /
0.10 s warm (2.2%), so the ratio holds at both sizes.

## What this does and does not show

- **Warm means unchanged.** The memo key is the whole-tree manifest
  (sorted `(path, sha256)` pairs + threshold digest + version), so any edits
  invalidate it. `changed` (28.99 s) equals the cost of a first-time analysis:
  a PR that modifies one file pays full price today. This is the documented
  trade-off in ADR-008, not a bug, but it means the NFR is met for repeated
  gate runs, **not** for incremental analysis of a change.
- **Synthetic corpus.** No real 100k-line repository was measured; absolute
  seconds on a real project (larger modules, deeper import graphs, type
  annotations) may differ. The ratio is more trustworthy than the absolute
  number.
- **Single run, single machine.** No variance estimate; no cold-OS-cache
  control. `full` ran first and still was faster than `changed`, which suggests
  file-system caching flatters the last run's denominator comparison.
- Reproduction: `uv run python -m benchmarks.run_benchmark --root <dir>
  --target-lines 100000 --json docs/benchmarks/performance-100k.json`.
  Raw numbers: `docs/benchmarks/performance-100k.json`.
