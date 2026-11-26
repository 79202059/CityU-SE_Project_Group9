# Performance measurement: 100k-line analysis against the NFR

Evidence for the performance NFR in `PROJECT_OVERVIEW.md` section 8:

> Incremental analysis must not exceed 40 % of the full-analysis time, or must
> stay under 30 s in the agreed environment.

The requirement has two clauses joined by **or**, and a pull-request
(incremental) analysis is the case the `changed` phase measures. The `warm`
phase measures something else: a repeated gate run on sources that did not
change. Earlier revisions of this file and of `run_benchmark.py` scored the
requirement on `warm`; both now use `changed` and report `warm` as information.

## Result

Same protocol, same generated corpus shape, two machines:

| phase | machine A (s) | machine B (s) | note |
| --- | ---: | ---: | --- |
| full (no cache) | 25.06 | 12.56 | detector cost, the denominator |
| cold (cache write) | 22.55 | 13.49 | first run of a new tree |
| warm (cache hit) | 0.36 | 0.07 | repeated run on unchanged sources |
| changed (memo miss) | 28.99 | 14.16 | one changed line, the NFR case |

| clause | machine A | machine B |
| --- | --- | --- |
| relative: changed / full <= 40 % | 115.7 % -> FAIL | 112.7 % -> FAIL |
| absolute: changed <= 30 s | 28.99 s -> PASS | 14.16 s -> PASS |

**Verdict: the relative clause is not met on either machine; the absolute
clause is met on both.** Machine A clears the absolute clause by 3.4 %, which a
single measurement on another machine can flip, so read it as "met in this
environment" rather than as a portable guarantee.

`warm` is 1.4 % (A) and 0.6 % (B) of `full`. That is a real property of the
content-addressed memo, but it is **not** the requirement: any edit changes the
whole-tree manifest and pays the full price (ADR-008).

## Machines

- Machine A: Windows 10 (10.0.26300), CPython 3.11.4, 16 logical CPUs,
  AMD64 Family 23 Model 104.
- Machine B: Windows 11 (10.0.26200), CPython 3.14.7, 32 logical CPUs,
  AMD64 Family 26 Model 68.

## Corpus

Generated, not a real repository (`benchmarks/generate_100k.py`, deterministic):

- 522 modules and about 100,000 lines under `bench/` (10 sub-packages, roughly
  40 modules each). The raw JSON records the exact line count of the run.
- Each module: a docstring, two or three chained
  `from bench.subX import modYYY` imports, three module-level functions
  (40/30/60 lines with 6/3/8 branches) and one class with 8 methods of 12 lines.
- The shape targets the detectors that dominate cost: long methods, large
  classes, branch counts, and an import graph for cycles and fan-in/fan-out.
- A full analysis of this corpus produces 1,537 findings.

## Protocol

`benchmarks/run_benchmark.py` runs four phases against the same tree:

| phase | what it does | what it represents |
| --- | --- | --- |
| full | `analyze_tree` with no cache | detector cost, the denominator |
| cold | new empty cache directory, one run | first run of a new tree |
| warm | same tree, same cache, second run | repeated gate run on an unchanged tree |
| changed | append one line to one module, rerun | a PR that touches a single file |

The script asserts that `warm` reports the same number of findings as `full`, so
a fast warm run cannot be fast by skipping work it was supposed to do.

## Limits

- **Synthetic corpus.** No real 100k-line repository was measured; absolute
  seconds on real code (larger modules, deeper import graphs, annotations) may
  differ. The ratio is more trustworthy than the absolute number.
- **Single run per phase, no variance estimate, no OS-cache control.** On
  machine A the `full` phase ran first and was still faster than `changed`,
  which suggests the file-system cache flatters the later phase.
- **No per-file incrementality.** The memo key is the whole-tree manifest, so
  `changed` is a full re-analysis by design: ADR-008 rejected partial reuse.
- Reproduction: `uv run python -m benchmarks.run_benchmark --root <dir>
  --target-lines 100000 --json docs/benchmarks/performance-100k.json`.
  Raw numbers: `docs/benchmarks/performance-100k.json`.
