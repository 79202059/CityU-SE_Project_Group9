"""``pyexamine-delta`` — change-aware code smell analysis.

This module is the Sprint 1 entry point: it analyses the base and head
revisions of a repository, converts every detector result into a unified
:class:`~code_quality_analyzer.finding.Finding`, and classifies each finding
as NEW / UNCHANGED / RESOLVED using exact fingerprints.
"""

import argparse
import json
import logging
import os
from typing import Dict, List, Optional

from .architectural_smell_detector import ArchitecturalSmellDetector
from .code_smell_detector import CodeSmellDetector
from .config_handler import ConfigHandler
from .exceptions import CodeAnalysisError
from .finding import (
    CATEGORY_ARCHITECTURAL,
    CATEGORY_CODE,
    CATEGORY_STRUCTURAL,
    Finding,
)
from .fingerprint import NEW, RESOLVED, UNCHANGED, classify_lifecycle, relative_path
from .main import resolve_config_path
from .structural_smell_detector import StructuralSmellDetector
from .version_provider import VersionProvider, VersionProviderError, resolve_repo_root

logger = logging.getLogger(__name__)

# Directories that never contain project source and are skipped by default.
DEFAULT_IGNORE_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyexamine-delta",
        description="Compare code smells between two git revisions and classify "
                    "each finding as NEW, UNCHANGED, or RESOLVED.",
    )
    parser.add_argument(
        "project",
        help="Path to the Python project to analyze (must be inside a git repository)",
    )
    parser.add_argument("--base", required=True, help="Base git ref, e.g. origin/main")
    parser.add_argument("--head", default="HEAD", help="Head git ref (default: HEAD)")
    parser.add_argument(
        "--config",
        default="code_quality_config.yaml",
        help="Path to the configuration file (falls back to the bundled config)",
    )
    parser.add_argument(
        "--output",
        help="Base path for reports; writes <output>.txt and <output>.json",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format when no --output is given (default: text)",
    )
    parser.add_argument(
        "--ignore",
        nargs="*",
        default=[],
        metavar="DIR",
        help="Additional directory names to ignore",
    )
    return parser


def analyze_tree(
    tree_path: str,
    config_handler: ConfigHandler,
    ignore_dirs: Optional[List[str]] = None,
) -> List[Finding]:
    """Run all three detectors against one checkout and return Findings.

    Each detector is intentionally independent: a failure in one does not
    abort the others, matching the behaviour of the original CLI.
    """
    ignore = DEFAULT_IGNORE_DIRS | set(ignore_dirs or [])
    findings: List[Finding] = []

    code_detector = CodeSmellDetector(config_handler.get_thresholds("code_smells"))
    for root, dirs, files in os.walk(tree_path):
        dirs[:] = [d for d in dirs if d not in ignore]
        for file in files:
            if not file.endswith(".py"):
                continue
            file_path = os.path.join(root, file)
            try:
                code_detector.detect_smells(file_path)
            except (CodeAnalysisError, Exception):  # noqa: BLE001 - keep isolation
                logger.debug("Skipping %s after a code analysis error", file_path)
    try:
        code_detector.detect_cross_file_smells()
    except Exception:  # noqa: BLE001 - cross-file is best-effort
        logger.debug("Cross-file code smell detection failed", exc_info=True)
    findings.extend(Finding.from_smell(s, CATEGORY_CODE) for s in code_detector.code_smells)

    structural_detector = StructuralSmellDetector(
        config_handler.get_thresholds("structural_smells"))
    structural_detector.detect_smells(tree_path, ignore_dirs=ignore)
    findings.extend(
        Finding.from_smell(s, CATEGORY_STRUCTURAL)
        for s in structural_detector.structural_smells
    )

    architectural_detector = ArchitecturalSmellDetector(
        config_handler.get_thresholds("architectural_smells"))
    architectural_detector.detect_smells(tree_path, ignore_dirs=ignore)
    findings.extend(
        Finding.from_smell(s, CATEGORY_ARCHITECTURAL)
        for s in architectural_detector.architectural_smells
    )

    return findings


def _as_dict(finding: Finding, tree_root: str) -> dict:
    return {
        "category": finding.category,
        "type": finding.smell_type,
        "file": relative_path(finding.file_path, tree_root),
        "symbol": finding.symbol,
        "line": finding.line,
        "severity": finding.severity,
        "description": finding.description,
    }


def render_text(
    classified: Dict[str, List[Finding]],
    base_ref: str,
    head_ref: str,
    base_root: str,
    head_root: str,
) -> str:
    lines = [
        "pyexamine-delta report",
        "======================",
        f"base: {base_ref}",
        f"head: {head_ref}",
        "",
    ]
    state_roots = {
        NEW: head_root,
        UNCHANGED: head_root,
        RESOLVED: base_root,
    }
    for state in (NEW, RESOLVED, UNCHANGED):
        items = classified[state]
        lines.append(f"{state} ({len(items)})")
        lines.append("-" * (len(state) + len(str(len(items))) + 3))
        if not items:
            lines.append("  (none)")
        for finding in items:
            root = state_roots[state]
            location = relative_path(finding.file_path, root)
            symbol = f"{finding.symbol}" if finding.symbol else location
            lines.append(
                f"  - [{finding.category}] {finding.smell_type} "
                f"({symbol}) severity={finding.severity}"
            )
        lines.append("")

    lines.append("Summary")
    lines.append("-------")
    lines.append(f"NEW: {len(classified[NEW])}")
    lines.append(f"UNCHANGED: {len(classified[UNCHANGED])}")
    lines.append(f"RESOLVED: {len(classified[RESOLVED])}")
    return "\n".join(lines)


def render_json(
    classified: Dict[str, List[Finding]],
    base_ref: str,
    head_ref: str,
    base_root: str,
    head_root: str,
) -> str:
    roots = {NEW: head_root, UNCHANGED: head_root, RESOLVED: base_root}
    payload = {
        "base": base_ref,
        "head": head_ref,
        "summary": {
            "new": len(classified[NEW]),
            "unchanged": len(classified[UNCHANGED]),
            "resolved": len(classified[RESOLVED]),
        },
        "findings": {
            state: [_as_dict(f, roots[state]) for f in classified[state]]
            for state in (NEW, RESOLVED, UNCHANGED)
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def run(args: argparse.Namespace) -> int:
    project = os.path.abspath(args.project)
    if not os.path.isdir(project):
        raise FileNotFoundError(
            f"Project directory does not exist: {project}. "
            "Run from the directory you want to analyze and pass '.'."
        )
    repo_root = resolve_repo_root(project)
    config_path = resolve_config_path(args.config)
    logger.info("Loading configuration from: %s", config_path)
    config_handler = ConfigHandler(config_path)

    with VersionProvider(repo_root) as provider:
        base_tree = provider.materialize(args.base)
        head_tree = provider.materialize(args.head)
        logger.info("Analyzing base revision %s ...", args.base)
        base_findings = analyze_tree(base_tree, config_handler, args.ignore)
        logger.info("Analyzing head revision %s ...", args.head)
        head_findings = analyze_tree(head_tree, config_handler, args.ignore)
        classified = classify_lifecycle(base_findings, head_findings, base_tree, head_tree)

    if args.output:
        base_path = os.path.splitext(args.output)[0]
        txt_path = f"{base_path}.txt"
        json_path = f"{base_path}.json"
        with open(txt_path, "w", encoding="utf-8") as handle:
            handle.write(
                render_text(classified, args.base, args.head, base_tree, head_tree)
            )
        with open(json_path, "w", encoding="utf-8") as handle:
            handle.write(
                render_json(classified, args.base, args.head, base_tree, head_tree)
            )
        print(f"Text report written to {txt_path}")
        print(f"JSON report written to {json_path}")
    elif args.format == "json":
        print(render_json(classified, args.base, args.head, base_tree, head_tree))
    else:
        print(render_text(classified, args.base, args.head, base_tree, head_tree))

    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except (VersionProviderError, FileNotFoundError, CodeAnalysisError) as exc:
        logger.error("pyexamine-delta failed: %s", exc)
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
