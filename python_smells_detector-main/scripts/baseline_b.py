"""Baseline A / B / Proposed counts for the evaluation contract.

``Group9-Scrum/EVALUATION_CONTRACT.md`` section 4 compares three configurations
on the same commit pair:

``A``          the upstream report for the head revision, unfiltered;
``B``          the same report restricted to the lines the change touched;
``Proposed``   ``pyexamine-delta`` findings classified ``NEW`` or ``WORSENED``.

Section 5 turns those numbers into the reviewer-facing metric

    display-volume reduction = 1 - median(shown per PR) / median(A per PR)

The contract also requires labelled recall >= 0.85 for a success claim. This script produces
those counts and the per-pair detail, so the comparison table can be rebuilt
from committed code instead of from a spreadsheet.

Usage::

    python scripts/baseline_b.py <repo> --base origin/main --head HEAD
    python scripts/baseline_b.py --check-dataset eval/dataset.csv
    python scripts/baseline_b.py --dataset eval/dataset.csv --format json

The dataset file is a CSV with the columns ``repo,base,head`` - the shape
section 3.2 describes for the sampled pull requests.  Nothing is fetched from
the network and nothing is written unless ``--output`` is given.  ``--gutter``
widens each changed-line range; the contract filters on changed lines only, so
the default is 0 and the value is recorded in the output.
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import statistics
import subprocess
import sys
import tempfile
import zipfile
from contextlib import nullcontext
from itertools import chain
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from code_quality_analyzer.cache import config_digest
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
from code_quality_analyzer.metrics import measured_crossings, worsen_detail
from code_quality_analyzer.risk import changed_lines
from code_quality_analyzer.rule_registry import rule_id_for
from code_quality_analyzer.version_provider import (
    VersionProvider,
    VersionProviderError,
    resolve_repo_root,
)

Span = Tuple[int, int]
Hunks = Dict[str, List[Span]]

UPSTREAM_COMMIT = "838b212fafe9b1ff1e06c3364892e53177dab16f"
UPSTREAM_SHA256 = "e5b0431ac2129e22dfc774de15e91eca415214954b1654b93753516e55cbbe4c"


def prepare_upstream(archive, destination, thresholds):
    """Unpack the verified release package into a private import directory."""
    root = Path(destination)
    prefix = f"python_smells_detector-{UPSTREAM_COMMIT}/src/"
    with open(archive, "rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
        if digest.hexdigest() != UPSTREAM_SHA256:
            raise ValueError("upstream archive SHA-256 does not match the verified v0.3.0 snapshot")
        stream.seek(0)
        with zipfile.ZipFile(stream) as snapshot:
            for name in snapshot.namelist():
                if name.startswith(prefix + "code_quality_analyzer/") and not name.endswith("/"):
                    target = root / name[len(prefix):]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(snapshot.read(name))
    (root / "thresholds.json").write_text(json.dumps(thresholds), encoding="utf-8")


def upstream_findings(source, tree, ignore):
    # -I avoids user PYTHONPATH and the target checkout. The verified package
    # takes precedence over the editable fork in the active virtual environment.
    command = [sys.executable, "-I", "-B", "-X", "utf8", "-c", (
        "import json, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from code_quality_analyzer.main import analyze\n"
        "print(json.dumps(analyze(sys.argv[2], config=sys.argv[3], ignore=sys.argv[4:])))"
    ), str(source), tree, str(Path(source) / "thresholds.json"), *ignore]
    try:
        result = subprocess.run(command, capture_output=True, encoding="utf-8", timeout=1800, check=True)
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"upstream analysis failed: {(exc.stderr or str(exc))[-1500:]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("upstream analysis timed out") from exc
    report = json.loads(result.stdout)
    findings = [Finding(category=f["type"].lower(), smell_type=f["name"], file_path=f["file_path"],
                        symbol=f["module_class"] or "", line=f["line_number"], severity=f["severity"],
                        description=f["description"]) for f in report["findings"]]
    errors = [{"file": relative_path(item["file"], tree), "detector": item["detector"]}
              for item in report["errors"]]
    return findings, errors


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
    details: bool = False,
    upstream_source=None,
) -> dict:
    """Run the three configurations for one commit pair."""
    repo_root = resolve_repo_root(repo_arg)
    base_ref, head_ref = base, head
    if details or upstream_source is not None:
        base_ref, head_ref = (_commit_id(repo_root, ref) for ref in (base, head))
    hunks = changed_lines(repo_root, base_ref, head_ref, strict=True)
    with VersionProvider(repo_root) as provider:
        head_tree = provider.materialize(head_ref)
        base_tree = provider.materialize(base_ref)
        head_context, base_context = {}, {}
        head_findings = analyze_tree(head_tree, config_handler, ignore_dirs, context=head_context)
        base_findings = analyze_tree(base_tree, config_handler, ignore_dirs, context=base_context)
        baseline_a, scan_errors = head_findings, []
        if upstream_source is not None:
            baseline_a, scan_errors = upstream_findings(upstream_source, head_tree, ignore_dirs)
        baseline_b = filter_by_changed_lines(baseline_a, hunks, head_tree, gutter)
        classified = classify_lifecycle(
            base_findings,
            head_findings,
            base_tree,
            head_tree,
            worsen=worsen_detail,
            crossings=measured_crossings(base_context, head_context, head_findings, head_tree),
            fuzzy=fuzzy_match,
        )
    proposed = list(classified[NEW]) + list(classified.get(WORSENED, []))
    row = {
        "repo": os.path.basename(os.path.normpath(repo_root)),
        "base": base,
        "head": head,
        "gutter": gutter,
        "counts": {
            "A": len(baseline_a),
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
            for f in baseline_a
        }),
    }
    if upstream_source is not None:
        row.update(upstream_commit=UPSTREAM_COMMIT, upstream_errors=scan_errors,
                   base_sha=base_ref, head_sha=head_ref, config_digest=config_digest(config_handler))
    if details:
        row.update(repo_id=repo_arg, base_sha=base_ref, head_sha=head_ref,
                   config_digest=config_digest(config_handler))
        row["details"] = {
            "A": [_record(f, head_tree) for f in baseline_a],
            "B": [_record(f, head_tree) for f in baseline_b],
            "proposed": [_record(f, base_tree if state == RESOLVED else head_tree, state)
                         for state, findings in classified.items() for f in findings],
        }
    return row


def _commit_id(repo, ref):
    try:
        result = subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "--end-of-options",
                                 ref + "^{commit}"], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"timed out resolving {ref!r}") from exc
    if result.returncode:
        raise ValueError(f"could not resolve {ref!r}: {result.stderr.strip()}")
    return result.stdout.strip()


def _record(finding, tree, state=None):
    # Cross-file detectors join absolute paths with ', '. Strip the exact
    # checkout prefix after each separator, preserving commas in file names.
    path = relative_path(finding.file_path, tree)
    prefix = os.path.abspath(tree).replace(os.sep, "/").rstrip("/") + "/"
    path = path.replace(", " + prefix, ", ")
    return {"rule": rule_id_for(finding.smell_type, finding.category),
            "path": path, "symbol": finding.symbol or "",
            "line": finding.line, "side": "base" if state == RESOLVED else "head", "state": state}


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
        "recall": None,
        "reduction_b_vs_a": None if baseline_a == 0 else 1.0 - baseline_b / baseline_a,
        "reduction_proposed_vs_a": (
            None if baseline_a == 0 else 1.0 - proposed / baseline_a
        ),
    }


def render_text(rows: Sequence[dict], summary: dict) -> str:
    """Human-readable table plus the medians the metric is built on."""
    lines: List[str] = []
    if rows and "upstream_commit" in rows[0]:
        errors = sum(len(row["upstream_errors"]) for row in rows)
        lines.append(f"Baseline A/B upstream commit {rows[0]['upstream_commit']} ({errors} scan errors across all pairs)")
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
    lines.append("Reduction in findings shown vs A (recall unmeasured)")
    for label, key in (("B", "reduction_b_vs_a"), ("Proposed", "reduction_proposed_vs_a")):
        ratio = summary[key]
        value = "undefined (zero median A)" if ratio is None else f"{100 * ratio:.1f} %"
        lines.append(f"  {label:<10}{value}")
    if summary["pairs"] < 2:
        lines.append("")
        lines.append("Only one pair was measured.")
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


def _dataset_records(path: str) -> Iterator[Tuple[int, List[str]]]:
    """Yield the starting physical line and fields of each CSV record."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        line_no = 0
        for line in handle:
            line_no += 1
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            # csv.reader consumes continuation lines of a quoted field, including
            # any that start with '#'. Only comments between records are skipped.
            reader = csv.reader(chain((line,), handle), strict=True)
            try:
                cells = next(reader)
            except csv.Error as exc:
                raise ValueError(f"{path}:{line_no}: invalid CSV ({exc})") from exc
            yield line_no, [cell.strip() for cell in cells]
            line_no += reader.line_num - 1


def _dataset_rows(path: str) -> List[Tuple[str, str, str]]:
    """Validate the entire manifest before any commit pair is analysed."""
    required = ("repo", "base", "head")
    indices = (0, 1, 2)
    header = None
    first_seen: Dict[Tuple[str, str, str], int] = {}
    for record_no, (line_no, cells) in enumerate(_dataset_records(path)):
        source = f"{path}:{line_no}"
        names = ["repo" if cell.lower() == "repository" else cell.lower() for cell in cells]
        # In the legacy three-column format 'repo' may be a directory and
        # 'base' and 'HEAD' may be refs. Look for corroborating column names.
        if record_no == 0:
            # A complete header is case-insensitive. In a partial header,
            # ignore the conventional positional head ref when spelled HEAD.
            signals = {name for i, name in enumerate(names) if not (i == 2 and cells[i] == "HEAD")}
            has_header = set(required).issubset(names) or (
                ("repo" in signals or bool(signals & {"pr", "selection_date"}))
                and bool(signals & {"base", "head"})
            )
            if has_header:
                for field in required:
                    if names.count(field) != 1:
                        raise ValueError(f"{source}: header needs exactly one '{field}' column")
                indices = tuple(names.index(field) for field in required)
                header = names
                continue
        if header is not None:
            if names == header:
                raise ValueError(f"{source}: repeated header")
            if len(cells) != len(header):
                raise ValueError(f"{source}: expected {len(header)} columns, found {len(cells)}")
        if len(cells) < 3:
            raise ValueError(f"{source}: rows need repo,base,head")
        repo, base, head = (cells[index] for index in indices)
        pair = (repo, base, head)
        for field, value in zip(required, pair):
            if not value:
                raise ValueError(f"{source}: empty '{field}'")
            if any(char in value for char in "\r\n\x00"):
                raise ValueError(f"{source}: invalid character in '{field}'")
            if field != "repo" and value.startswith("-"):
                raise ValueError(f"{source}: invalid '{field}' revision {value!r}")
        if pair in first_seen:
            raise ValueError(f"{source}: duplicate commit pair (first on line {first_seen[pair]})")
        first_seen[pair] = line_no
    if not first_seen:
        raise ValueError(f"{path}: no commit pairs to analyse")
    return list(first_seen)


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
    dataset_group = parser.add_mutually_exclusive_group()
    dataset_group.add_argument(
        "--dataset",
        default=None,
        help="CSV with repo,base,head rows; replaces the positional argument",
    )
    dataset_group.add_argument(
        "--check-dataset", metavar="CSV",
        help="validate the CSV structure and report its size on stdout, before running Git or the detectors",
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
    parser.add_argument("--details", action="store_true", help="include finding-level records in JSON")
    parser.add_argument("--upstream-archive", metavar="ZIP", help="run A and B with the verified upstream v0.3.0 source ZIP")
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
    if args.gutter < 0:
        print("error: --gutter must be zero or positive", file=sys.stderr)
        return 2
    if args.details and (args.format != "json" or args.check_dataset is not None):
        raise ValueError("--details requires an analysis with --format json")
    if args.upstream_archive and args.check_dataset is not None:
        raise ValueError("--upstream-archive requires an analysis")
    if args.upstream_archive and args.output and os.path.exists(args.output) and os.path.samefile(args.upstream_archive, args.output):
        raise ValueError("choose an output separate from the upstream archive")
    if args.check_dataset is not None:
        if args.repo is not None or args.base is not None:
            raise ValueError("choose either --check-dataset or a single repository and --base")
        if args.output:
            raise ValueError("--check-dataset writes to stdout (omit --output)")
        triples = _dataset_rows(args.check_dataset)
        summary = {"pairs": len(triples), "repo_paths": len({repo for repo, _, _ in triples})}
        if args.format == "json":
            print(json.dumps(summary))
        else:
            print(f"Validated {summary['pairs']} commit pair(s) "
                  f"across {summary['repo_paths']} repository path(s).")
        return 0
    if args.dataset:
        triples = _dataset_rows(args.dataset)
        if args.output and os.path.exists(args.output) and os.path.samefile(args.dataset, args.output):
            raise ValueError("--output refers to the input dataset; choose a separate report file")
    elif args.base:
        triples = [(args.repo or ".", args.base, args.head)]
    else:
        print("error: pass --base REV or --dataset FILE", file=sys.stderr)
        return 2
    config_handler = ConfigHandler(resolve_config_path(args.config))
    context = tempfile.TemporaryDirectory(prefix="pyexamine-upstream-") if args.upstream_archive else nullcontext()
    with context as source:
        if source is not None:
            prepare_upstream(args.upstream_archive, source, config_handler.thresholds)
        return _run_pairs(triples, args, config_handler, source)


def _run_pairs(triples, args, config_handler, source):
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
                details=args.details,
                upstream_source=source,
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
    logger = logging.getLogger("code_quality_analyzer")
    level = logger.level
    try:
        if not args.debug:
            logger.setLevel(logging.CRITICAL)
        return run(args)
    except (OSError, ValueError, csv.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        logger.setLevel(level)


if __name__ == "__main__":
    sys.exit(main())
