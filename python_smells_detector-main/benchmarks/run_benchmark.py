"""Performance measurement for the NFR in ADR-008 (100k-line project).

Protocol (fixed, so numbers are comparable across machines):

1. **full** - a cold detector run with no cache at all. This is the cost the
   NFR compares against.
2. **cold** - a detector run with an empty content-addressed cache: it pays the
   analysis *and* writes the cache entry. Reported separately, because CI pays
   this on the first run of a new tree.
3. **warm** - the same tree again with the populated cache: this must skip the
   detectors entirely.
4. **changed** - one file gains a line, so the tree manifest changes and the
   whole-tree memo misses. This is the honest cost of an actual pull-request
   diff under the current design (per-file incrementality is future work).

The NFR: an incremental (pull-request) analysis <= 40 % of a full run, or
<= 30 s in absolute terms. The `changed` phase models that case. The `warm`
phase answers a different question (a repeated gate run on unchanged
sources) and is reported for information only.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import time

from benchmarks.generate_100k import generate
from code_quality_analyzer.cache import AnalysisCache
from code_quality_analyzer.config_handler import ConfigHandler
from code_quality_analyzer.delta import analyze_tree

RATIO_TARGET = 0.40
SECONDS_TARGET = 30.0


def _timed(call):
    start = time.perf_counter()
    result = call()
    return time.perf_counter() - start, result


def _count_lines(root: str) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if not name.endswith(".py"):
                continue
            with open(os.path.join(dirpath, name), "r", encoding="utf-8", errors="replace") as handle:
                total += sum(1 for _ in handle)
    return total


def run(root: str, config_path: str) -> dict:
    handler = ConfigHandler(config_path)
    files = sum(
        1
        for dirpath, _dirnames, filenames in os.walk(root)
        for name in filenames
        if name.endswith(".py")
    )
    lines = _count_lines(root)

    full_seconds, full_findings = _timed(lambda: analyze_tree(root, handler))

    cache_dir = os.path.join(root, "..", "_bench_cache")
    cache_dir = os.path.abspath(cache_dir)
    shutil.rmtree(cache_dir, ignore_errors=True)
    cold_seconds, cold_findings = _timed(
        lambda: analyze_tree(root, handler, cache=AnalysisCache(cache_dir))
    )
    warm_seconds, warm_findings = _timed(
        lambda: analyze_tree(root, handler, cache=AnalysisCache(cache_dir))
    )

    target = None
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if name.startswith("mod") and name.endswith(".py"):
                target = os.path.join(dirpath, name)
                break
        if target:
            break
    with open(target, "a", encoding="utf-8", newline="\n") as handle:
        handle.write("# one line changed in this pull request\n")
    changed_seconds, changed_findings = _timed(
        lambda: analyze_tree(root, handler, cache=AnalysisCache(cache_dir))
    )

    if len(warm_findings) != len(full_findings):
        raise RuntimeError(
            "cache changed the result: full=%d warm=%d"
            % (len(full_findings), len(warm_findings))
        )

    changed_ratio = changed_seconds / full_seconds if full_seconds else 0.0
    warm_ratio = warm_seconds / full_seconds if full_seconds else 0.0
    relative_ok = changed_ratio <= RATIO_TARGET
    absolute_ok = changed_seconds <= SECONDS_TARGET
    return {
        "project": os.path.basename(os.path.abspath(root)),
        "files": files,
        "lines": lines,
        "findings": len(full_findings),
        "seconds": {
            "full": round(full_seconds, 2),
            "cold_with_cache_write": round(cold_seconds, 2),
            "warm": round(warm_seconds, 2),
            "changed": round(changed_seconds, 2),
        },
        "ratios": {
            "changed_over_full": round(changed_ratio, 4),
            "warm_over_full": round(warm_ratio, 4),
        },
        "nfr": {
            "requirement": "incremental analysis <= 40 % of a full run, or <= 30 s",
            "relative": {
                "observed": round(changed_ratio, 4),
                "target": RATIO_TARGET,
                "passes": relative_ok,
            },
            "absolute": {
                "observed_seconds": round(changed_seconds, 2),
                "target": SECONDS_TARGET,
                "passes": absolute_ok,
            },
            "warm_repeat_run": {
                "observed_seconds": round(warm_seconds, 2),
                "observed_over_full": round(warm_ratio, 4),
                "note": "a repeated run on unchanged sources, not the requirement",
            },
            "passes": relative_ok or absolute_ok,
        },
        "machine": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpus": os.cpu_count(),
            "processor": platform.processor() or "unknown",
        },
    }


def render(result: dict) -> str:
    seconds = result["seconds"]
    nfr = result["nfr"]
    relative = nfr["relative"]
    absolute = nfr["absolute"]
    if relative["passes"]:
        verdict = "PASS via the relative clause"
    elif absolute["passes"]:
        verdict = "PASS via the absolute clause"
    else:
        verdict = "FAIL under both clauses"
    return "\n".join(
        [
            "## 100k-line performance measurement",
            "",
            "| phase | seconds | note |",
            "| --- | ---: | --- |",
            "| full (no cache) | %(full).2f | detector cost, the NFR denominator |" % seconds,
            "| cold (cache write) | %(cold_with_cache_write).2f | first run of a new tree |" % seconds,
            "| warm (cache hit) | %(warm).2f | repeated run on unchanged sources, not the NFR |" % seconds,
            "| changed (memo miss) | %(changed).2f | one PR line: whole-tree re-analysis, the NFR case |" % seconds,
            "",
            "- project: %d files, %d lines, %d findings"
            % (result["files"], result["lines"], result["findings"]),
            "- NFR relative clause: changed / full = %.1f %% (target <= %.0f %%) -> %s"
            % (
                relative["observed"] * 100,
                relative["target"] * 100,
                "PASS" if relative["passes"] else "FAIL",
            ),
            "- NFR absolute clause: changed = %.2f s (target <= %.0f s) -> %s"
            % (
                absolute["observed_seconds"],
                absolute["target"],
                "PASS" if absolute["passes"] else "FAIL",
            ),
            "- warm / full = %.1f %% (informational: a repeated run, not an incremental one)"
            % (nfr["warm_repeat_run"]["observed_over_full"] * 100),
            "- NFR verdict: **%s**" % verdict,
            "",
        ]
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Measure full vs warm analysis on a 100k-line project.")
    parser.add_argument("--root", default=os.path.join(os.environ.get("TEMP", "/tmp"), "pe-bench-100k"))
    parser.add_argument("--config", default="code_quality_config.yaml")
    parser.add_argument("--target-lines", type=int, default=100_000)
    parser.add_argument("--json", default=None, help="write the raw numbers here")
    parser.add_argument("--no-generate", action="store_true", help="reuse an existing project")
    args = parser.parse_args(argv)

    if not args.no_generate:
        if os.path.isdir(args.root):
            shutil.rmtree(args.root)
        counts = generate(args.root, args.target_lines)
        print("generated %d files / %d lines" % (counts["files"], counts["lines"]))

    result = run(args.root, args.config)
    print(render(result))
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(result, handle, indent=2)
            handle.write("\n")
        print("json written to %s" % args.json)
    return 0 if result["nfr"]["passes"] else 1


if __name__ == "__main__":
    sys.exit(main())
