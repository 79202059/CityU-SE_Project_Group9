"""Baseline A / B / Proposed counts for the evaluation contract.

``Group9-Scrum/EVALUATION_CONTRACT.md`` section 4 compares three configurations
on the same commit pair:

``A``          the upstream report for the head revision, unfiltered;
``B``          the same report restricted to the lines the change touched;
``Proposed``   ``pyexamine-delta`` findings classified ``NEW`` or ``WORSENED``.

Section 5 turns those numbers into the reviewer-facing metric

    irrelevant-warning reduction = 1 - median(shown per PR) / median(A per PR)

which only needs counts per pull request, not annotations.  This script produces
those counts and the per-pair detail, so the comparison table can be rebuilt
from committed code instead of from a spreadsheet.

Usage::

    python scripts/baseline_b.py <repo> --base origin/main --head HEAD
    python scripts/baseline_b.py --dataset eval/dataset.csv --format json

The dataset file is a CSV with the columns ``repo,base,head`` - the shape
section 3.2 describes for the sampled pull requests.  Nothing is fetched from
the network and nothing is written unless ``--output`` is given.  ``--gutter``
widens each changed-line range; the contract filters on changed lines only, so
the default is 0 and the value is recorded in the output.
"""

import argparse
import csv
import json
import logging
import os
import statistics
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from code_quality_analyzer.config_handler import ConfigHandler
from code_quality_analyzer.delta import analyze_tree
from code_quality_analyzer.finding import Finding
from code_quality_analyzer.fingerprint import (
    NEW,
    RESOLVED,
    UNCHANGED,
    WORSENED,
    classify_lifecycle,
    relative_path,
)
from code_quality_analyzer.fuzzy import match as fuzzy_match
from code_quality_analyzer.main import DEFAULT_CONFIG_NAME, _version, resolve_config_path
from code_quality_analyzer.metrics import worsen_detail
from code_quality_analyzer.risk import changed_lines
from code_quality_analyzer.version_provider import (
    VersionProvider,
    VersionProviderError,
    resolve_repo_root,
)

Span = Tuple[int, int]
Hunks = Dict[str, List[Span]]


def line_is_touched(
    finding: Finding,
    hunks: Hunks,
    root: str,
    gutter: int = 0,
) -> bool:
    """True when the finding sits on a line range the change added or edited.

    A finding without ``line`` is a module- or class-level smell; it is kept
    whenever its file was touched at all, because there is no narrower position
    to compare against.
    """
    if not hunks or not finding.file_path:
        return False
    try:
        relative = relative_path(finding.file_path, root)
    except ValueError:
        return False
    spans = hunks.get(relative)
    if not spans:
        return False
    if finding.line is None:
        return True
    for start, end in spans:
        if start - gutter <= finding.line <= end + gutter:
            return True
    return False


def filter_by_changed_lines(
    findings: Sequence[Finding],
    hunks: Hunks,
    root: str,
    gutter: int = 0,
) -> List[Finding]:
    """Baseline B: the upstream findings a reviewer would see on touched lines."""
    return [f for f in findings if line_is_touched(f, hunks, root, gutter)]


def counts_for_pair(
    repo_arg: str,
    base: str,
    head: str,
    config_handler: ConfigHandler,
    gutter: int = 0,
    ignore_dirs: Sequence[str] = (),
) -> dict:
    """Run the three configurations for one commit pair."""
    repo_root = resolve_repo_root(repo_arg)
    hunks = changed_lines(repo_root, base, head)
    with VersionProvider(repo_root) as provider:
        head_tree = provider.materialize(head)
        base_tree = provider.materialize(base)
        head_findings = analyze_tree(head_tree, config_handler, ignore_dirs)
        base_findings = analyze_tree(base_tree, config_handler, ignore_dirs)
        baseline_b = filter_by_changed_lines(head_findings, hunks, head_tree, gutter)
        classified = classify_lifecycle(
            base_findings,
            head_findings,
            base_tree,
            head_tree,
            worsen=worsen_detail,
            fuzzy=fuzzy_match,
        )
    proposed = list(classified[NEW]) + list(classified.get(WORSENED, []))
    return {
        "repo": os.path.basename(os.path.normpath(repo_root)),
        "base": base,
        "head": head,
        "gutter": gutter,
        "counts": {
            "A": len(head_findings),
            "B": len(baseline_b),
            "proposed": len(proposed),
        },
        "lifecycle": {
            "new": len(classified[NEW]),
            "worsened": len(classified.get(WORSENED, [])),
            "unchanged": len(classified[UNCHANGED]),
            "resolved": len(classified[RESOLVED]),
        },
        "files_touched": len(hunks),
        "files_head": len({
            relative_path(f.file_path, head_tree)
            for f in head_findings
        }),
    }


def summarise(rows: Sequence[dict]) -> dict:
    """Medians across pull requests, which is what section 5 measures."""

    def median(key: str) -> float:
        values = [float(row["counts"][key]) for row in rows]
        return float(statistics.median(values)) if values else 0.0

    baseline_a = median("A")
    baseline_b = median("B")
    proposed = median("proposed")
    return {
        "pairs": len(rows),
        "median": {"A": baseline_a, "B": baseline_b, "proposed": proposed},
        "reduction_b_vs_a": 0.0 if baseline_a == 0 else 1.0 - baseline_b / baseline_a,
        "reduction_proposed_vs_a": (
            0.0 if baseline_a == 0 else 1.0 - proposed / baseline_a
        ),
    }


def render_text(rows: Sequence[dict], summary: dict) -> str:
    """Human-readable table plus the medians the metric is built on."""
    lines: List[str] = []
    header = "%-28s %-12s %-12s %6s %6s %10s %8s" % (
        "repo", "base", "head", "A", "B", "Proposed", "touched",
    )
    lines.append(header)
    lines.append("-" * len(header))
    for row in rows:
        counts = row["counts"]
        lines.append(
            "%-28s %-12s %-12s %6d %6d %10d %8d" % (
                row["repo"][:28],
                row["base"][:12],
                row["head"][:12],
                counts["A"],
                counts["B"],
                counts["proposed"],
                row["files_touched"],
            )
        )
    lines.append("")
    lines.append("Median findings shown per pull request")
    lines.append("  A (upstream, unfiltered)      %8.1f" % summary["median"]["A"])
    lines.append("  B (upstream, changed lines)   %8.1f" % summary["median"]["B"])
    lines.append("  Proposed (new + worsened)     %8.1f" % summary["median"]["proposed"])
    lines.append("")
    lines.append("Irrelevant-warning reduction vs A")
    lines.append("  B         %6.1f %%" % (100.0 * summary["reduction_b_vs_a"]))
    lines.append("  Proposed  %6.1f %%" % (100.0 * summary["reduction_proposed_vs_a"]))
    if summary["pairs"] < 2:
        lines.append("")
        lines.append("Note: a single pair is not a median; add rows with --dataset.")
    return "\n".join(lines)


def render_json(rows: Sequence[dict], summary: dict) -> str:
    return json.dumps(
        {
            "tool": "pyexamine-delta baseline comparison",
            "tool_version": _version(),
            "pairs": list(rows),
            "summary": summary,
        },
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )


def _dataset_rows(path: str) -> List[Tuple[str, str, str]]:
    """Read ``repo,base,head`` rows from a CSV, ignoring blank and comment lines."""
    triples: List[Tuple[str, str, str]] = []
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        for raw in reader:
            if not raw or not raw[0].strip() or raw[0].lstrip().startswith("#"):
                continue
            cells = [cell.strip() for cell in raw]
            if cells[0].lower() in ("repo", "repository"):
                # The header row may be preceded by comments, so do not key on
                # the row index.
                continue
            if len(cells) < 3:
                raise ValueError("%s: rows need repo,base,head" % path)
            triples.append((cells[0], cells[1], cells[2]))
    return triples


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="baseline_b",
        description=(
            "Count the findings shown by Baseline A, Baseline B and "
            "pyexamine-delta on the same commit pairs."
        ),
    )
    parser.add_argument("repo", nargs="?", help="repository path (default: .)")
    parser.add_argument("--base", default=None, help="base revision (e.g. origin/main)")
    parser.add_argument("--head", default="HEAD", help="head revision (default: HEAD)")
    parser.add_argument(
        "--dataset",
        default=None,
        help="CSV with repo,base,head rows; replaces the positional argument",
    )
    parser.add_argument(
        "--gutter",
        type=int,
        default=0,
        help="extra lines around each changed range (default: 0)",
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG_NAME, help="threshold YAML")
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        help="directory name to skip (repeatable)",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--output", default=None, help="write the report to this path")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="let detector warnings through to stderr",
    )
    parser.add_argument("--version", action="store_true", help="print the version")
    return parser


def run(args: argparse.Namespace) -> int:
    if args.version:
        print("pyexamine-delta baseline comparison %s" % _version())
        return 0
    if not args.debug:
        # Detector warnings about unparsable fixtures would drown the table.
        logging.getLogger("code_quality_analyzer").setLevel(logging.CRITICAL)
    if args.gutter < 0:
        print("error: --gutter must be zero or positive", file=sys.stderr)
        return 2
    config_handler = ConfigHandler(resolve_config_path(args.config))
    if args.dataset:
        triples = _dataset_rows(args.dataset)
    elif args.base:
        triples = [(args.repo or ".", args.base, args.head)]
    else:
        print("error: pass --base REV or --dataset FILE", file=sys.stderr)
        return 2
    if not triples:
        print("error: no commit pairs to analyse", file=sys.stderr)
        return 2

    rows: List[dict] = []
    for repo_arg, base, head in triples:
        try:
            row = counts_for_pair(
                repo_arg,
                base,
                head,
                config_handler,
                gutter=args.gutter,
                ignore_dirs=args.ignore,
            )
        except (OSError, ValueError, VersionProviderError) as exc:
            print("error: %s (%s..%s): %s" % (repo_arg, base, head, exc), file=sys.stderr)
            return 2
        rows.append(row)
        print(
            "%s %s..%s: A=%d B=%d Proposed=%d"
            % (row["repo"], base, head, row["counts"]["A"], row["counts"]["B"],
               row["counts"]["proposed"]),
            file=sys.stderr,
        )

    summary = summarise(rows)
    text = render_json(rows, summary) if args.format == "json" else render_text(rows, summary)
    if args.output:
        with open(args.output, "w", newline="\n", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(text)
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
