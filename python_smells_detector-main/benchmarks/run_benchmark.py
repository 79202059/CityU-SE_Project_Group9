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

The NFR (EVALUATION_CONTRACT.md section 8): an incremental (pull-request)
analysis <= 40 % of a full run, or <= 30 s in absolute terms. The `changed`
phase models that case. The `warm` phase answers a different question (a
repeated gate run on unchanged sources) and is reported for information only.

The contract also asks for 3 runs and a median with a range, so `--repeat N`
repeats the whole protocol N times and reports the per-phase median and the
min-max spread. `run()` restores the file it touches, so repetitions measure
the same tree every time.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path

from benchmarks.generate_100k import generate
from code_quality_analyzer.cache import AnalysisCache
from code_quality_analyzer.config_handler import ConfigHandler
from code_quality_analyzer.delta import analyze_tree

RATIO_TARGET = 0.40
SECONDS_TARGET = 30.0
PHASES = ("full", "cold_with_cache_write", "warm", "changed")
CHANGE_MARKER = "# one line changed in this pull request"


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


def _median(values):
    ordered = sorted(values)
    size = len(ordered)
    if size == 0:
        return 0.0
    middle = size // 2
    if size % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _nfr_block(seconds: dict) -> dict:
    full_seconds = seconds["full"]
    changed_seconds = seconds["changed"]
    warm_seconds = seconds["warm"]
    changed_ratio = changed_seconds / full_seconds if full_seconds else 0.0
    warm_ratio = warm_seconds / full_seconds if full_seconds else 0.0
    relative_ok = changed_ratio <= RATIO_TARGET
    absolute_ok = changed_seconds <= SECONDS_TARGET
    return {
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
    }


def run(root: str, config_path: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="pyexamine-bench-cache-", dir=Path(root).resolve().parent) as cache_dir:
        return _run(root, config_path, cache_dir)


def _run(root: str, config_path: str, cache_dir: str) -> dict:
    handler = ConfigHandler(config_path)
    files = sum(
        1
        for dirpath, _dirnames, filenames in os.walk(root)
        for name in filenames
        if name.endswith(".py")
    )
    lines = _count_lines(root)

    full_seconds, full_findings = _timed(lambda: analyze_tree(root, handler))

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

    if target is None:
        raise ValueError("the benchmark corpus needs a mod*.py file for the changed phase")
    target = Path(target)
    original = target.read_bytes()
    newline = b"\r\n" if b"\r\n" in original else b"\n"
    marker = (b"" if not original or original.endswith(b"\n") else newline) + CHANGE_MARKER.encode() + newline
    try:
        target.write_bytes(original + marker)
        changed_seconds, changed_findings = _timed(
            lambda: analyze_tree(root, handler, cache=AnalysisCache(cache_dir))
        )
    finally:
        target.write_bytes(original)

    if len(warm_findings) != len(full_findings):
        raise RuntimeError(
            "cache changed the result: full=%d warm=%d"
            % (len(full_findings), len(warm_findings))
        )
    if len(changed_findings) != len(full_findings):
        raise RuntimeError(
            "the diff changed the result: full=%d changed=%d"
            % (len(full_findings), len(changed_findings))
        )

    seconds = {
        "full": round(full_seconds, 2),
        "cold_with_cache_write": round(cold_seconds, 2),
        "warm": round(warm_seconds, 2),
        "changed": round(changed_seconds, 2),
    }
    result = {
        "project": os.path.basename(os.path.abspath(root)),
        "files": files,
        "lines": lines,
        "findings": len(full_findings),
        "seconds": seconds,
    }
    result.update(_nfr_block(seconds))
    result["machine"] = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpus": os.cpu_count(),
        "processor": platform.processor() or "unknown",
    }
    return result


def run_repeated(root: str, config_path: str, repeat: int = 1) -> dict:
    repeat = max(1, int(repeat))
    runs = [run(root, config_path) for _ in range(repeat)]
    if repeat == 1:
        return runs[0]

    first = runs[0]
    for other in runs[1:]:
        if other["findings"] != first["findings"] or other["lines"] != first["lines"]:
            raise RuntimeError(
                "the runs disagreed on the tree: findings %d vs %d, lines %d vs %d"
                % (first["findings"], other["findings"], first["lines"], other["lines"])
            )

    seconds = {phase: round(_median([item["seconds"][phase] for item in runs]), 2) for phase in PHASES}
    spread = {
        phase: {
            "min": round(min(item["seconds"][phase] for item in runs), 2),
            "max": round(max(item["seconds"][phase] for item in runs), 2),
        }
        for phase in PHASES
    }

    result = {
        "project": first["project"],
        "files": first["files"],
        "lines": first["lines"],
        "findings": first["findings"],
        "seconds": seconds,
    }
    result.update(_nfr_block(seconds))
    result["machine"] = first["machine"]
    result["repetitions"] = {
        "count": repeat,
        "protocol": "each run repeats the full / cold / warm / changed sequence on an unchanged tree",
        "runs": [{"seconds": item["seconds"]} for item in runs],
        "median": seconds,
        "range": spread,
    }
    return result


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
    lines = [
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

    repetitions = result.get("repetitions")
    if repetitions:
        spread = repetitions["range"]
        lines.extend(
            [
                "### Repetitions",
                "",
                "- %d runs of the whole protocol on an unchanged tree; the table above reports medians"
                % repetitions["count"],
                "",
                "| phase | median s | min s | max s |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for phase in PHASES:
            lines.append(
                "| %s | %.2f | %.2f | %.2f |"
                % (phase, seconds[phase], spread[phase]["min"], spread[phase]["max"])
            )
        lines.append("")
        lines.extend(
            [
                "| run | full s | cold s | warm s | changed s |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for index, item in enumerate(repetitions["runs"], 1):
            per_run = item["seconds"]
            lines.append(
                "| %d | %.2f | %.2f | %.2f | %.2f |"
                % (
                    index,
                    per_run["full"],
                    per_run["cold_with_cache_write"],
                    per_run["warm"],
                    per_run["changed"],
                )
            )
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Measure full vs warm analysis on a 100k-line project.")
    parser.add_argument("--root", help="new or empty generation directory, or existing corpus with --no-generate")
    parser.add_argument("--config", default="code_quality_config.yaml")
    parser.add_argument("--target-lines", type=int, default=100_000)
    parser.add_argument("--json", default=None, help="write the raw numbers here")
    parser.add_argument("--no-generate", action="store_true", help="reuse an existing project")
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="repeat the whole protocol N times and report per-phase median and range",
    )
    args = parser.parse_args(argv)

    if args.no_generate and not args.root:
        parser.error("--no-generate requires --root")
    with tempfile.TemporaryDirectory(prefix="pyexamine-benchmark-") as temporary:
        root = Path(args.root or temporary)
        if args.no_generate:
            if not root.is_dir():
                parser.error("the corpus directory does not exist")
        else:
            if root.exists() and (not root.is_dir() or any(root.iterdir())):
                parser.error("choose a new or empty directory for generation")
            counts = generate(str(root), args.target_lines)
            print("generated %d files / %d lines" % (counts["files"], counts["lines"]))
        result = run_repeated(str(root), args.config, args.repeat)
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
