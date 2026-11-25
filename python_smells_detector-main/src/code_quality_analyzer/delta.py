"""``pyexamine-delta`` - change-aware code smell analysis and PR quality gate.

The command answers three questions in one run:

1. *What does this pull request introduce?*  Every detector result from the
   head revision is turned into a unified :class:`Finding` and compared with
   either the base revision or a stored baseline.  Findings that already
   existed but got measurably worse are reported as WORSENED, not as
   unchanged - see ``metrics.worsen_detail`` for the tolerance.
2. *Which of those should block the merge?*  ``--fail-on-new`` maps the new
   findings onto an exit code, so the gate lives in CI rather than in a
   reviewer's head.
3. *What does GitHub need to show them inline?*  ``--format sarif`` emits a
   SARIF 2.1.0 log with stable ``partialFingerprints``, which is what code
   scanning and ``gh api`` consume.

Modes (``--baseline-mode``):

``off``    compare base and head checkouts directly (two analyses).
``diff``   compare the head checkout against a stored baseline (one analysis;
           this is the CI path and the reason NFR1 is reachable).
``write``  refresh the baseline from the head checkout (one analysis).
"""

import argparse
import json
import logging
import os
import sys
from typing import Dict, List, Optional

from .architectural_smell_detector import ArchitecturalSmellDetector
from .baseline import (
    BASELINE_FILENAME,
    baseline_payload,
    diff_against_baseline,
    load_baseline,
    write_baseline,
)
from .cache import DEFAULT_CACHE_DIRNAME, AnalysisCache, tree_manifest
from .code_smell_detector import CodeSmellDetector
from .config_handler import ConfigHandler
from .exceptions import CodeAnalysisError
from .finding import (
    CATEGORY_ARCHITECTURAL,
    CATEGORY_CODE,
    CATEGORY_STRUCTURAL,
    Finding,
)
from .fingerprint import (
    NEW,
    RESOLVED,
    UNCHANGED,
    WORSENED,
    classify_lifecycle,
    fingerprint_string,
    relative_path,
)
from .fuzzy import match as fuzzy_match
from .main import _version, resolve_config_path
from .metrics import enrich_metrics, worsen_detail
from .risk import (
    RiskScore,
    changed_lines,
    gate_by_risk,
    rank_findings,
    score_findings,
)
from .sarif_builder import LEVEL_POLICIES, build_sarif, fingerprint
from .structural_smell_detector import StructuralSmellDetector
from .version_provider import VersionProvider, VersionProviderError, resolve_repo_root

logger = logging.getLogger(__name__)

# Directories that never contain project source and are skipped by default.
DEFAULT_IGNORE_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules"}

# How many rows a markdown table shows before it truncates with a count.
DEFAULT_MARKDOWN_LIMIT = 20

EXIT_OK = 0
EXIT_GATE_REACHED = 1
EXIT_USAGE = 2

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyexamine-delta",
        description="Compare code smells between two git revisions (or against a "
                    "stored baseline) and classify each finding as NEW, UNCHANGED, "
                    "or RESOLVED.",
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
        choices=["text", "json", "sarif", "markdown"],
        default="text",
        help="Output format (default: text); 'markdown' is a PR-comment summary",
    )
    parser.add_argument(
        "--ignore",
        nargs="*",
        default=[],
        metavar="DIR",
        help="Additional directory names to ignore",
    )
    parser.add_argument(
        "--baseline",
        default=None,
        help="Baseline file path (default: %s inside the project)" % BASELINE_FILENAME,
    )
    parser.add_argument(
        "--baseline-mode",
        choices=["off", "diff", "write"],
        default="off",
        help="off: compare base and head checkouts; diff: compare head against the "
             "stored baseline; write: refresh the baseline from head (default: off)",
    )
    parser.add_argument(
        "--level-policy",
        choices=list(LEVEL_POLICIES),
        default="triage",
        help="SARIF level mapping (default: triage, which demotes structural 'high' "
             "findings to warnings so the gate stays actionable)",
    )
    parser.add_argument(
        "--fail-on-new",
        nargs="?",
        const="medium",
        default=None,
        choices=["low", "medium", "high"],
        metavar="LEVEL",
        help="Exit 1 when a NEW finding reaches LEVEL severity (default level: medium)",
    )
    parser.add_argument(
        "--include-unchanged",
        action="store_true",
        help="Also emit unchanged findings in the SARIF log (demoted one level)",
    )
    parser.add_argument(
        "--all-rules",
        action="store_true",
        help="Emit all 47 rule descriptors in SARIF, not only the triggered ones",
    )
    parser.add_argument(
        "--risk",
        action="store_true",
        help="Attach an explainable 0-100 risk score to every finding and rank "
             "the report by it (see risk.py for the four components)",
    )
    parser.add_argument(
        "--min-risk",
        type=float,
        default=None,
        metavar="SCORE",
        help="Only NEW findings at or above SCORE (0-100) can satisfy --fail-on-new "
             "or trigger the gate; implies --risk",
    )
    parser.add_argument(
        "--max-new",
        type=int,
        default=None,
        metavar="N",
        help="Quality budget: exit 1 when more than N NEW findings are reported",
    )
    parser.add_argument(
        "--no-fuzzy",
        action="store_true",
        help="pair renamed/moved smells by exact fingerprint only (no fuzzy pass)",
    )
    parser.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=None,
        metavar="SCORE",
        help="accept a rename/move pairing at or above SCORE (default 0.62)",
    )
    parser.add_argument(
        "--no-worsen",
        action="store_true",
        help="Do not compare metrics: a matched finding can only be UNCHANGED",
    )
    parser.add_argument(
        "--fail-on-worsened",
        action="store_true",
        help="Count WORSENED findings toward --fail-on-new and --max-new too",
    )
    parser.add_argument(
        "--markdown-limit",
        type=int,
        default=DEFAULT_MARKDOWN_LIMIT,
        metavar="N",
        help="Rows per table in --format markdown (default: %d)" % DEFAULT_MARKDOWN_LIMIT,
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable the content-addressed analysis cache (always re-analyze the tree)",
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        metavar="DIR",
        help="Cache directory (default: %s under the repository root)"
        % DEFAULT_CACHE_DIRNAME,
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s " + _version(),
    )
    return parser


def analyze_tree(
    tree_path: str,
    config_handler: ConfigHandler,
    ignore_dirs: Optional[List[str]] = None,
    *,
    context: Optional[dict] = None,
    cache: Optional[AnalysisCache] = None,
) -> List[Finding]:
    """Run all three detectors against one checkout and return Findings.

    Each detector is intentionally independent: a failure in one does not
    abort the others, matching the behaviour of the original CLI.

    When ``context`` is a dict, project-level signals used by risk ranking are
    recorded into it (``fan_in`` from the structural dependency graph).  The
    parameter is optional so existing callers keep their exact behaviour.

    When ``cache`` is provided, the tree is first looked up by its content
    manifest (see :mod:`code_quality_analyzer.cache`).  A hit returns the
    stored findings re-rooted onto ``tree_path`` without running any detector;
    a miss runs the detectors and stores the result.  Results are identical
    either way - the cache is a memo of a pure function of tree content.
    """
    ignore = DEFAULT_IGNORE_DIRS | set(ignore_dirs or [])
    if cache is None:
        return _analyze_tree_uncached(tree_path, config_handler, ignore, context)

    _manifest, manifest_digest = tree_manifest(tree_path, ignore)
    key = cache.key_for(config_handler, manifest_digest, _version())
    hit = cache.load(key, tree_path)
    if hit is not None:
        findings, fan_in = hit
        if context is not None:
            context["fan_in"] = fan_in
        return findings

    findings = _analyze_tree_uncached(tree_path, config_handler, ignore, context)
    cache.store(key, findings, (context or {}).get("fan_in") or {}, tree_path)
    return findings


def _analyze_tree_uncached(
    tree_path: str,
    config_handler: ConfigHandler,
    ignore: set,
    context: Optional[dict],
) -> List[Finding]:
    """Detector pass without cache lookup; returns enriched findings."""
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
    if context is not None:
        graph = getattr(structural_detector, "dependency_graph", None)
        if graph is not None:
            context["fan_in"] = {node: int(degree) for node, degree in graph.in_degree()}

    architectural_detector = ArchitecturalSmellDetector(
        config_handler.get_thresholds("architectural_smells"))
    architectural_detector.detect_smells(tree_path, ignore_dirs=ignore)
    findings.extend(
        Finding.from_smell(s, CATEGORY_ARCHITECTURAL)
        for s in architectural_detector.architectural_smells
    )

    return enrich_metrics(findings)


def _as_dict(
    finding: Finding,
    tree_root: str,
    risk: Optional[RiskScore] = None,
    evidence: Optional[dict] = None,
    matched: Optional[dict] = None,
) -> dict:
    payload = {
        "category": finding.category,
        "type": finding.smell_type,
        "file": relative_path(finding.file_path, tree_root),
        "symbol": finding.symbol,
        "line": finding.line,
        "severity": finding.severity,
        "description": finding.description,
    }
    if finding.metric_value is not None:
        payload["metric"] = finding.metric_value
    if risk is not None:
        payload["risk"] = risk.as_dict()
    if evidence is not None:
        payload["worsened"] = evidence
    if matched is not None:
        payload["matched"] = matched
    return payload


def _format_evidence(evidence: dict) -> str:
    """One-line, ASCII-only rendering of a WORSENED evidence dict."""
    if evidence.get("reason") == "metric" and evidence.get("base") is not None:
        return " %s %s->%s" % (
            evidence.get("metric") or "metric",
            _num(evidence["base"]),
            _num(evidence["head"]),
        )
    return " severity %s->%s" % (
        evidence.get("severity_base"),
        evidence.get("severity_head"),
    )


def _num(value: object) -> str:
    """Render an int-valued float without a trailing ``.0``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else ("%.2f" % number)


def render_text(
    classified: Dict[str, List[Finding]],
    base_ref: str,
    head_ref: str,
    base_root: str,
    head_root: str,
    risks: Optional[Dict[str, RiskScore]] = None,
    worsen_details: Optional[Dict[str, dict]] = None,
    fuzzy_details: Optional[Dict[str, dict]] = None,
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
        WORSENED: head_root,
        UNCHANGED: head_root,
        RESOLVED: base_root,
    }
    for state in (NEW, WORSENED, RESOLVED, UNCHANGED):
        items = classified[state]
        lines.append(f"{state} ({len(items)})")
        lines.append("-" * (len(state) + len(str(len(items))) + 3))
        if not items:
            lines.append("  (none)")
        for finding in items:
            root = state_roots[state]
            location = relative_path(finding.file_path, root)
            symbol = f"{finding.symbol}" if finding.symbol else location
            suffix = ""
            if risks is not None and state in (NEW, WORSENED):
                score = risks.get(fingerprint(finding, root))
                if score is not None:
                    suffix = " risk=%.1f" % score.score
            if state == WORSENED and worsen_details:
                evidence = worsen_details.get(fingerprint_string(finding, root))
                if evidence:
                    suffix += _format_evidence(evidence)
            if state in (UNCHANGED, WORSENED) and fuzzy_details:
                matched = fuzzy_details.get(fingerprint_string(finding, root))
                if matched:
                    suffix += " matched=%s(%.2f)" % (
                        matched.get("transformation", "fuzzy"),
                        float(matched.get("score", 0.0)),
                    )
            lines.append(
                f"  - [{finding.category}] {finding.smell_type} "
                f"({symbol}) severity={finding.severity}{suffix}"
            )
        lines.append("")

    lines.append("Summary")
    lines.append("-------")
    lines.append(f"NEW: {len(classified[NEW])}")
    lines.append(f"WORSENED: {len(classified.get(WORSENED, []))}")
    lines.append(f"UNCHANGED: {len(classified[UNCHANGED])}")
    lines.append(f"RESOLVED: {len(classified[RESOLVED])}")
    return "\n".join(lines)


def render_json(
    classified: Dict[str, List[Finding]],
    base_ref: str,
    head_ref: str,
    base_root: str,
    head_root: str,
    risks: Optional[Dict[str, RiskScore]] = None,
    worsen_details: Optional[Dict[str, dict]] = None,
    fuzzy_details: Optional[Dict[str, dict]] = None,
) -> str:
    roots = {
        NEW: head_root,
        WORSENED: head_root,
        UNCHANGED: head_root,
        RESOLVED: base_root,
    }
    payload = {
        "base": base_ref,
        "head": head_ref,
        "summary": {
            "new": len(classified[NEW]),
            "worsened": len(classified.get(WORSENED, [])),
            "unchanged": len(classified[UNCHANGED]),
            "resolved": len(classified[RESOLVED]),
        },
        "findings": {
            state: [
                _as_dict(
                    f,
                    roots[state],
                    None
                    if risks is None or state not in (NEW, WORSENED)
                    else risks.get(fingerprint(f, roots[state])),
                    (
                        worsen_details.get(fingerprint_string(f, roots[state]))
                        if worsen_details
                        else None
                    ),
                    (
                        fuzzy_details.get(fingerprint_string(f, roots[state]))
                        if fuzzy_details
                        else None
                    ),
                )
                for f in classified[state]
            ]
            for state in (NEW, WORSENED, RESOLVED, UNCHANGED)
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def render_sarif(
    classified: Dict[str, List[Finding]],
    head_root: str,
    *,
    level_policy: str,
    include_unchanged: bool = False,
    all_rules: bool = False,
    risks: Optional[Dict[str, RiskScore]] = None,
) -> str:
    """SARIF 2.1.0 log containing the findings a reviewer must see.

    NEW and WORSENED findings are emitted: both are things the pull request
    is responsible for.  WORSENED results carry ``baselineState: updated`` so a
    code-scanning consumer groups them with the earlier alert instead of
    opening a duplicate.  An unchanged finding is, by definition, one the
    repository already accepted.  RESOLVED findings become invocation
    notifications so the summary can show progress without turning them into
    annotations on lines that may no longer exist.
    """
    results = list(classified[NEW]) + list(classified.get(WORSENED, []))
    if include_unchanged:
        results.extend(classified[UNCHANGED])
    states = {fingerprint(f, head_root): state for state in (NEW,) for f in classified[NEW]}
    for finding in classified.get(WORSENED, []):
        states[fingerprint(finding, head_root)] = WORSENED
    notifications = []
    resolved = classified[RESOLVED]
    if resolved:
        notifications.append(
            {
                "level": "note",
                "message": {
                    "text": "%d finding(s) present in the baseline are no longer "
                            "reported by the head revision." % len(resolved)
                },
            }
        )
    document = build_sarif(
        results,
        tool_version=_version(),
        level_policy=level_policy,
        root=head_root,
        include_all_rules=all_rules,
        notifications=notifications,
        risks=risks,
        baseline_states=states,
    )
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=False)


def _md_cell(text: object) -> str:
    """Escape one markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def render_markdown(
    classified: Dict[str, List[Finding]],
    base_ref: str,
    head_ref: str,
    base_root: str,
    head_root: str,
    *,
    risks: Optional[Dict[str, RiskScore]] = None,
    limit: int = DEFAULT_MARKDOWN_LIMIT,
    worsen_details: Optional[Dict[str, dict]] = None,
    fuzzy_details: Optional[Dict[str, dict]] = None,
) -> str:
    """A PR-comment summary: counts plus the tables a reviewer reads first.

    Deliberately free of timestamps and absolute paths so the same diff posted
    twice produces the same comment (ADR-002).  Only NEW findings can flatten a
    review, so they come first and keep their risk score; RESOLVED is collapsed
    into a details block; UNCHANGED is a single count.
    """
    new_items = list(classified[NEW]) + list(classified.get(WORSENED, []))
    resolved_items = list(classified[RESOLVED])
    unchanged_count = len(classified[UNCHANGED])

    if risks is not None:
        def weight_of(finding: Finding) -> float:
            score = risks.get(fingerprint(finding, head_root))
            return score.score if score is not None else -1.0

        new_items.sort(key=lambda f: (-weight_of(f), relative_path(f.file_path, head_root),
                                      f.line or 0, f.smell_type))

    lines = [
        "**PyExamine Delta** (`%s` -> `%s`)" % (base_ref, head_ref),
        "",
        "| state | findings |",
        "| --- | ---: |",
        f"| NEW | {len(classified[NEW])} |",
        f"| WORSENED | {len(classified.get(WORSENED, []))} |",
        f"| RESOLVED | {len(resolved_items)} |",
        f"| UNCHANGED | {unchanged_count} |",
        "",
    ]

    if new_items:
        header = "| risk | category | rule | location | severity |"
        divider = "| ---: | --- | --- | --- | --- |"
        if risks is None:
            header = "| category | rule | location | severity |"
            divider = "| --- | --- | --- | --- |"
        heading = "### New findings"
        if classified.get(WORSENED, []):
            heading = "### New and worsened findings"
        lines += [heading, "", header, divider]
        for finding in new_items[:limit]:
            location = relative_path(finding.file_path, head_root)
            if finding.line:
                location = f"`{location}:{finding.line}`"
            else:
                location = f"`{location}`"
            rule_cell = _md_cell(finding.smell_type)
            state = (
                WORSENED
                if any(f is finding for f in classified.get(WORSENED, []))
                else NEW
            )
            if state == WORSENED and worsen_details:
                evidence = worsen_details.get(fingerprint_string(finding, head_root))
                if evidence:
                    rule_cell = "%s (worsened: %s)" % (
                        rule_cell,
                        _format_evidence(evidence).strip(),
                    )
            if fuzzy_details:
                matched = fuzzy_details.get(fingerprint_string(finding, head_root))
                if matched:
                    rule_cell = "%s (%s %.2f)" % (
                        rule_cell,
                        matched.get("transformation", "fuzzy"),
                        float(matched.get("score", 0.0)),
                    )
            row = [
                _md_cell(finding.category),
                rule_cell,
                location,
                _md_cell(finding.severity),
            ]
            if risks is not None:
                score = risks.get(fingerprint(finding, head_root))
                row.insert(0, "%.1f" % score.score if score is not None else "n/a")
            lines.append("| " + " | ".join(row) + " |")
        hidden = len(new_items) - limit
        if hidden > 0:
            lines += ["", f"_{hidden} more new finding(s) not listed._"]
        lines.append("")

    if resolved_items:
        lines += [
            "<details><summary>Resolved (%d)</summary>" % len(resolved_items),
            "",
            "| category | rule | location |",
            "| --- | --- | --- |",
        ]
        for finding in resolved_items[:limit]:
            location = relative_path(finding.file_path, base_root)
            if finding.line:
                location = f"`{location}:{finding.line}`"
            else:
                location = f"`{location}`"
            lines.append(
                "| " + " | ".join(
                    [_md_cell(finding.category), _md_cell(finding.smell_type), location]
                ) + " |"
            )
        hidden = len(resolved_items) - limit
        if hidden > 0:
            lines += ["", f"_{hidden} more resolved finding(s) not listed._"]
        lines += ["", "</details>", ""]

    if not new_items and not resolved_items:
        lines += ["_No change in smell findings._", ""]

    return "\n".join(lines).rstrip() + "\n"


def gate_violations(
    classified: Dict[str, List[Finding]],
    fail_on_new: str,
    *,
    include_worsened: bool = False,
) -> List[Finding]:
    """Findings at or above ``fail_on_new`` severity, in report order.

    By default only NEW findings can block a merge: that is the contract the
    baseline feature shipped with, and a team adopting the gate must not be
    surprised by pre-existing smells turning a worse severity.  ``--fail-on-
worsened`` opts into the stricter reading of the overview's
    "gate on NEW + WORSENED".
    """
    threshold = _SEVERITY_RANK[fail_on_new]
    candidates = list(classified[NEW])
    if include_worsened:
        candidates.extend(classified.get(WORSENED, []))
    return [
        finding
        for finding in candidates
        if _SEVERITY_RANK.get((finding.severity or "medium").lower(), 1) >= threshold
    ]


def _resolve_baseline_path(args: argparse.Namespace, project: str) -> str:
    if args.baseline:
        return os.path.abspath(args.baseline)
    return os.path.join(project, BASELINE_FILENAME)


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
    tool_version = _version()

    cache: Optional[AnalysisCache] = None
    if not args.no_cache:
        cache_dir = args.cache_dir or os.path.join(repo_root, DEFAULT_CACHE_DIRNAME)
        cache = AnalysisCache(cache_dir)

    baseline_path = _resolve_baseline_path(args, project)
    baseline_doc = None
    if args.baseline_mode == "diff":
        baseline_doc = load_baseline(baseline_path)
        if baseline_doc is None:
            logger.warning(
                "Baseline %s not found; falling back to base/head comparison.",
                baseline_path,
            )

    classified: Dict[str, List[Finding]]
    base_tree: Optional[str] = None
    head_tree: str
    context: dict = {}
    # A matched finding is WORSENED only if the judge says its metric grew past
    # the tolerance; --no-worsen keeps the old three-state behaviour.
    worsen = None if args.no_worsen else worsen_detail
    worsen_details: Dict[str, dict] = {}
    fuzzy_details: Dict[str, dict] = {}
    if args.no_fuzzy:
        fuzzy = None
    elif args.fuzzy_threshold is None:
        fuzzy = fuzzy_match
    else:
        threshold = float(args.fuzzy_threshold)
        fuzzy = lambda left, right, base_root, head_root: fuzzy_match(  # noqa: E731
            left, right, base_root, head_root, threshold=threshold
        )

    with VersionProvider(repo_root) as provider:
        if args.baseline_mode in ("diff", "write"):
            head_tree = provider.materialize(args.head)
            logger.info("Analyzing head revision %s ...", args.head)
            head_findings = analyze_tree(
                head_tree, config_handler, args.ignore, context=context, cache=cache
            )
            if args.baseline_mode == "write":
                payload = baseline_payload(
                    head_findings, head_tree, tool_version=tool_version, ref=args.head
                )
                write_baseline(baseline_path, payload)
                print(
                    "Baseline written to %s (%d findings)"
                    % (baseline_path, payload["counts"]["total"])
                )
                classified = {
                    NEW: [],
                    WORSENED: [],
                    UNCHANGED: head_findings,
                    RESOLVED: [],
                }
            elif baseline_doc is not None:
                classified = diff_against_baseline(
                    baseline_doc,
                    head_findings,
                    head_tree,
                    worsen=worsen,
                    worsen_details=worsen_details,
                    fuzzy=fuzzy,
                    fuzzy_details=fuzzy_details,
                )
            else:
                base_tree = provider.materialize(args.base)
                base_findings = analyze_tree(base_tree, config_handler, args.ignore, cache=cache)
                classified = classify_lifecycle(
                    base_findings,
                    head_findings,
                    base_tree,
                    head_tree,
                    worsen=worsen,
                    worsen_details=worsen_details,
                    fuzzy=fuzzy,
                    fuzzy_details=fuzzy_details,
                )
        else:
            base_tree = provider.materialize(args.base)
            head_tree = provider.materialize(args.head)
            logger.info("Analyzing base revision %s ...", args.base)
            base_findings = analyze_tree(base_tree, config_handler, args.ignore, cache=cache)
            logger.info("Analyzing head revision %s ...", args.head)
            head_findings = analyze_tree(
                head_tree, config_handler, args.ignore, context=context, cache=cache
            )
            classified = classify_lifecycle(
                base_findings,
                head_findings,
                base_tree,
                head_tree,
                worsen=worsen,
                worsen_details=worsen_details,
                fuzzy=fuzzy,
                fuzzy_details=fuzzy_details,
            )

    gate_candidates = list(classified[NEW])
    if args.fail_on_worsened:
        gate_candidates.extend(classified.get(WORSENED, []))

    risks: Optional[Dict[str, RiskScore]] = None
    if (args.risk or args.min_risk is not None) and gate_candidates:
        thresholds = {
            section: config_handler.get_thresholds(section)
            for section in ("code_smells", "structural_smells", "architectural_smells")
        }
        hunks = changed_lines(repo_root, args.base, args.head)
        risks = score_findings(
            gate_candidates,
            thresholds=thresholds,
            tree_root=head_tree,
            hunks=hunks,
            fan_in=context.get("fan_in") or {},
            fingerprint_of=lambda finding: fingerprint(finding, head_tree),
        )
        if args.min_risk is not None:
            def key_of(finding):
                return fingerprint(finding, head_tree)

            ranked = rank_findings(gate_candidates, risks, key_of)
            highest = risks[key_of(ranked[0])].score if ranked else 0.0
            eligible = gate_by_risk(
                gate_candidates, risks, key_of, float(args.min_risk)
            )
            print(
                "risk: scored %d candidate finding(s); highest %.1f; "
                "%d at or above %.1f"
                % (len(risks), highest, len(eligible), float(args.min_risk))
            )

    base_for_render = base_tree or head_tree
    if args.output:
        base_path = os.path.splitext(args.output)[0]
        txt_path = f"{base_path}.txt"
        json_path = f"{base_path}.json"
        with open(txt_path, "w", encoding="utf-8") as handle:
            handle.write(
                render_text(
                    classified,
                    args.base,
                    args.head,
                    base_for_render,
                    head_tree,
                    risks,
                    worsen_details,
                    fuzzy_details,
                )
            )
        with open(json_path, "w", encoding="utf-8") as handle:
            handle.write(
                render_json(
                    classified,
                    args.base,
                    args.head,
                    base_for_render,
                    head_tree,
                    risks,
                    worsen_details,
                    fuzzy_details,
                )
            )
        print(f"Text report written to {txt_path}")
        print(f"JSON report written to {json_path}")
    elif args.format == "json":
        print(
            render_json(
                classified,
                args.base,
                args.head,
                base_for_render,
                head_tree,
                risks,
                worsen_details,
                fuzzy_details,
            )
        )
    elif args.format == "sarif":
        print(
            render_sarif(
                classified,
                head_tree,
                level_policy=args.level_policy,
                include_unchanged=args.include_unchanged,
                all_rules=args.all_rules,
                risks=risks,
            )
        )
    elif args.format == "markdown":
        print(
            render_markdown(
                classified,
                args.base,
                args.head,
                base_for_render,
                head_tree,
                risks=risks,
                limit=max(0, int(args.markdown_limit)),
                worsen_details=worsen_details,
                fuzzy_details=fuzzy_details,
            )
        )
    else:
        print(
            render_text(
                classified,
                args.base,
                args.head,
                base_for_render,
                head_tree,
                risks,
                worsen_details,
                fuzzy_details,
            )
        )

    if args.fail_on_new:
        violations = gate_violations(
            classified,
            args.fail_on_new,
            include_worsened=args.fail_on_worsened,
        )
        if risks is not None and args.min_risk is not None:
            violations = gate_by_risk(
                violations,
                risks,
                lambda finding: fingerprint(finding, head_tree),
                float(args.min_risk),
            )
        if violations:
            print(
                "gate: %d new/worsened finding(s) at or above '%s' - failing the run"
                % (len(violations), args.fail_on_new)
            )
            return EXIT_GATE_REACHED

    budget_count = len(classified[NEW])
    if args.fail_on_worsened:
        budget_count += len(classified.get(WORSENED, []))
    if args.max_new is not None and budget_count > args.max_new:
        print(
            "budget: %d new/worsened finding(s) exceed the budget of %d - failing the run"
            % (budget_count, args.max_new)
        )
        return EXIT_GATE_REACHED

    return EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "calibrate":
        from .calibration import main as calibrate_main

        return calibrate_main(argv[1:])
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("pyexamine-delta failed: %s", exc)
        print(f"error: {exc}")
        return EXIT_USAGE
    except (VersionProviderError, CodeAnalysisError) as exc:
        logger.error("pyexamine-delta failed: %s", exc)
        print(f"error: {exc}")
        return EXIT_GATE_REACHED


if __name__ == "__main__":
    raise SystemExit(main())
