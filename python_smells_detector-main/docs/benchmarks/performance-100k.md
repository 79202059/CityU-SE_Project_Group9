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

Same protocol, same generated corpus shape, two machines. Machine B reports the
median of three runs, because `EVALUATION_CONTRACT.md` section 8 asks for three
repetitions with a median and a range.

| phase | machine A (s) | machine B median (s) | machine B range (s) | note |
| --- | ---: | ---: | --- | --- |
| full (no cache) | 25.06 | 13.74 | 13.06 - 14.03 | detector cost, the denominator |
| cold (cache write) | 22.55 | 13.80 | 13.11 - 15.36 | first run of a new tree |
| warm (cache hit) | 0.36 | 0.07 | 0.07 - 0.08 | repeated run on unchanged sources |
| changed (memo miss) | 28.99 | 14.06 | 12.87 - 14.20 | one changed line, the NFR case |

| clause | machine A | machine B (median) |
| --- | --- | --- |
| relative: changed / full <= 40 % | 115.7 % -> FAIL | 102.3 % -> FAIL |
| absolute: changed <= 30 s | 28.99 s -> PASS | 14.06 s -> PASS |

**Verdict: the relative clause is not met on either machine; the absolute
clause is met on both.** Machine A clears the absolute clause by 3.4 % and was
measured once, which a single slower run can flip; read it as "met in this
environment" rather than as a portable guarantee. Machine B's three runs put
`changed` between 12.87 s and 14.20 s, i.e. a 1.33 s spread on a 30 s target.

`warm` is 1.4 % (A) and 0.5 % (B) of `full`. That is a real property of the
content-addressed memo, but it is **not** the requirement: any edit changes the
whole-tree manifest and pays the full price (ADR-008).

## Repetitions (machine B)

| run | full s | cold s | warm s | changed s |
| --- | ---: | ---: | ---: | ---: |
| 1 | 14.03 | 15.36 | 0.08 | 14.06 |
| 2 | 13.74 | 13.80 | 0.07 | 14.20 |
| 3 | 13.06 | 13.11 | 0.07 | 12.87 |
| median | 13.74 | 13.80 | 0.07 | 14.06 |

The per-run ratio `changed / full` is 100.2 %, 103.3 % and 98.5 %, so the
relative clause fails in every repetition, not only in the median. The last run
being the fastest while `full` is also fastest points at machine warm-up rather
than at a change in the analysed tree.

## Machines

- Machine A: Windows 10 (10.0.26300), CPython 3.11.4, 16 logical CPUs,
  AMD64 Family 23 Model 104. One run per phase.
- Machine B: Windows 11 (10.0.26200), CPython 3.14.7, 32 logical CPUs,
  AMD64 Family 26 Model 68. Three runs per phase, medians reported.

## Corpus

Generated, not a real repository (`benchmarks/generate_100k.py`, deterministic):

- 522 modules and 100,077 lines under `bench/` (10 sub-packages, roughly
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

`--repeat N` repeats the whole four-phase sequence and reports the per-phase
median and the min-max range. The `changed` phase restores the file it edits, so
every repetition measures the same tree; the script also asserts that `warm` and
`changed` report the same number of findings as `full`, so a fast phase cannot be
fast by skipping work it was supposed to do.

## Limits

- **Synthetic corpus.** No real 100k-line repository was measured; absolute
  seconds on real code (larger modules, deeper import graphs, annotations) may
  differ. The ratio is more trustworthy than the absolute number.
- **Environment differs from the contract.** `EVALUATION_CONTRACT.md` section 8
  fixes Python 3.13 and 8 logical cores for measurement; machine B is CPython
  3.14.7 on 32 cores. The CI matrix proves the package runs on 3.10-3.14, but it
  does not measure this corpus on 3.13.
- **Variance is measured on one machine only.** Machine B has three runs; machine
  A has a single run, so its 3.4 % margin is not a variance-backed claim.
- **No per-file incrementality.** The memo key is the whole-tree manifest, so
  `changed` is a full re-analysis by design: ADR-008 rejected partial reuse.
- Reproduction: `python -m benchmarks.run_benchmark --root <dir>
  --target-lines 100000 --repeat 3 --json docs/benchmarks/performance-100k.json`.
  Raw numbers: `docs/benchmarks/performance-100k.json`.
