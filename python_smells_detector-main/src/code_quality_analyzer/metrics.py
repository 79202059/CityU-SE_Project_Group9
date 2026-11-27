"""Metric extraction shared by risk scoring and lifecycle comparison.

Every rule whose detector reports a measured value puts that number in the
``description`` string rather than in a field.  *This* module is the single
place that knows how to read it back.

Keeping one table matters for correctness, not just tidiness: ``risk.py``
scores a finding from ``metric / threshold``, and the delta engine decides
WORSENED from ``head_metric > base_metric``.  If the two used different
extractors, a finding could be reported as "much worse than its threshold"
while simultaneously being judged "not worse than before".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from .finding import Finding
from .fingerprint import fingerprint_string, relative_path
from .rule_registry import rule_for

# The frozen evaluation contract calls a matched finding WORSENED when its
# measured metric grows by more than 20% from a positive base value.
WORSEN_RELATIVE = 0.20
WORSEN_MIN_DELTA = 1.0  # Retained for callers that explicitly request the former absolute floor.
SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}

@dataclass(frozen=True)
class MetricSpec:
    """How to recover the measured value and its threshold for one rule."""

    pattern: re.Pattern
    threshold_key: str
    section: str  # code_smells | structural_smells | architectural_smells


METRIC_SPECS: Dict[str, MetricSpec] = {
    "pyex-code-long-method": MetricSpec(
        re.compile(r"has\s+(\d+)\s+lines"), "LONG_METHOD_LINES", "code_smells"
    ),
    "pyex-code-large-class": MetricSpec(
        re.compile(r"has\s+(\d+)\s+non-trivial methods"), "LARGE_CLASS_METHODS", "code_smells"
    ),
    "pyex-code-long-parameter-list": MetricSpec(
        re.compile(r"has\s+(\d+)\s+parameters"), "LONG_PARAMETER_LIST", "code_smells"
    ),
    "pyex-code-primitive-obsession": MetricSpec(
        re.compile(r"has\s+(\d+)\s+primitive parameters"),
        "PRIMITIVE_OBSESSION_COUNT",
        "code_smells",
    ),
    "pyex-code-switch-statements": MetricSpec(
        re.compile(r"with\s+(\d+)\s+branches"), "COMPLEX_CONDITIONAL", "code_smells"
    ),
    "pyex-code-feature-envy": MetricSpec(
        re.compile(r"makes\s+(\d+)\s+calls"), "FEATURE_ENVY_CALLS", "code_smells"
    ),
    "pyex-code-message-chains": MetricSpec(
        re.compile(r"chain\s+\((\d+)\s+calls"), "MESSAGE_CHAIN_LENGTH", "code_smells"
    ),
    "pyex-code-speculative-generality": MetricSpec(
        re.compile(r"has\s+(\d+)\s+unused parameters"),
        "UNUSED_PARAMETERS_THRESHOLD",
        "code_smells",
    ),
    "pyex-struct-nom": MetricSpec(
        re.compile(r"has\s+(\d+)\s+methods"), "NOM_THRESHOLD", "structural_smells"
    ),
    "pyex-struct-loc": MetricSpec(
        re.compile(r"has\s+(\d+)\s+effective code lines"), "LOC_THRESHOLD", "structural_smells"
    ),
    "pyex-struct-long-file": MetricSpec(
        re.compile(r"has\s+(\d+)\s+meaningful lines"), "MAX_FILE_LENGTH", "structural_smells"
    ),
    "pyex-struct-high-cyclomatic-complexity": MetricSpec(
        re.compile(r"complexity of\s+(\d+)"),
        "CYCLOMATIC_COMPLEXITY_THRESHOLD",
        "structural_smells",
    ),
    "pyex-struct-deep-nesting": MetricSpec(
        re.compile(r"nests blocks\s+(\d+)\s+levels"), "MAX_NESTING_DEPTH", "structural_smells"
    ),
    "pyex-struct-too-many-branches": MetricSpec(
        re.compile(r"has\s+(\d+)\s+branches"), "MAX_BRANCHES", "structural_smells"
    ),
    "pyex-struct-cbo": MetricSpec(
        re.compile(r"coupled to\s+(\d+)\s+classes"), "CBO_THRESHOLD", "structural_smells"
    ),
    "pyex-struct-dit": MetricSpec(
        re.compile(r"DIT of\s+(\d+)"), "DIT_THRESHOLD", "structural_smells"
    ),
    "pyex-struct-nocc": MetricSpec(
        re.compile(r"has\s+(\d+)\s+significant classes"), "NOCC_THRESHOLD", "structural_smells"
    ),
    "pyex-struct-rfc": MetricSpec(
        re.compile(r"RFC of\s+(\d+)"), "RFC_THRESHOLD", "structural_smells"
    ),
    "pyex-struct-lcom": MetricSpec(
        re.compile(r"LCOM of\s+(\d+)"), "LCOM_THRESHOLD", "structural_smells"
    ),
    "pyex-struct-mpc": MetricSpec(
        re.compile(r"weighted MPC of\s+(\d+(?:\.\d+)?)"), "MPC_THRESHOLD", "structural_smells"
    ),
    "pyex-struct-wac": MetricSpec(
        re.compile(r"has\s+(\d+)\s+significant attributes"), "WAC_THRESHOLD", "structural_smells"
    ),
    "pyex-struct-wmpc": MetricSpec(
        re.compile(r"WMPC1:\s*(\d+)"), "WMPC1_THRESHOLD", "structural_smells"
    ),
    "pyex-struct-size2": MetricSpec(
        re.compile(r"has\s+(\d+)\s+significant members"), "SIZE2_THRESHOLD", "structural_smells"
    ),
    "pyex-struct-high-fan-in": MetricSpec(
        re.compile(r"has\s+(\d+)\s+incoming"), "MAX_FANIN", "structural_smells"
    ),
    "pyex-struct-high-fan-out": MetricSpec(
        re.compile(r"fan-out of\s+(\d+)"), "MAX_FANOUT", "structural_smells"
    ),
    "pyex-arch-god-object": MetricSpec(
        re.compile(r"public functions\s+\((\d+)\)"),
        "GOD_OBJECT_FUNCTIONS",
        "architectural_smells",
    ),
    # NOC's threshold is scaled inside the detector by project size, so the
    # configured default understates the excess on a large codebase; it is still
    # better evidence than the severity band alone.
    "pyex-struct-noc": MetricSpec(
        re.compile(r"Project has\s+(\d+(?:\.\d+)?)\s+weighted classes"),
        "NOC_THRESHOLD",
        "structural_smells",
    ),
    "pyex-arch-hub-like-dependency": MetricSpec(
        re.compile(r"(\d+)\s+project connections"),
        "MAX_FANIN",
        "architectural_smells",
    ),
}


def extract_metric(finding: Finding) -> Tuple[Optional[float], Optional[MetricSpec]]:
    """Recover the measured value from the detector's description, if possible.

    Returns ``(value, spec)``.  ``spec`` is ``None`` when the rule carries no
    metric at all; ``value`` is ``None`` when the rule has a spec but this
    particular description did not match it (a detector wording change, or a
    variant message such as a cross-file finding).
    """
    rule = rule_for(finding.smell_type, finding.category)
    spec = METRIC_SPECS.get(rule.rule_id)
    if spec is None or not finding.description:
        return None, None
    match = spec.pattern.search(finding.description)
    if match is None:
        return None, spec
    try:
        return float(match.group(1)), spec
    except (TypeError, ValueError):
        return None, spec


def metric_key_for(finding: Finding) -> Optional[str]:
    """The threshold key this rule measures, derived from the rule alone.

    ``extract_metric`` needs the description to recover the *number*; the key
    only needs the rule identity, so a finding restored from a baseline (which
    keeps ``metric_value`` but not the detector wording) still knows which
    threshold it belongs to.
    """
    rule = rule_for(finding.smell_type, finding.category)
    spec = METRIC_SPECS.get(rule.rule_id)
    return spec.threshold_key if spec is not None else None


def enrich_metrics(findings: Iterable[Finding]) -> List[Finding]:
    """Return the same findings with ``metric_value`` filled where recoverable.

    Comparisons downstream (baseline round-trips, ``WORSENED`` detection) need
    the number on the finding itself: a baseline file only stores serialised
    fields, and re-reading ``description`` after a round-trip would couple the
    engine to the detector's wording twice.
    """
    enriched: List[Finding] = []
    for finding in findings:
        if finding.metric_value is not None:
            enriched.append(finding)
            continue
        value, _spec = extract_metric(finding)
        enriched.append(replace(finding, metric_value=value) if value is not None else finding)
    return enriched


def _severity_rank(severity: Optional[str]) -> int:
    return SEVERITY_RANK.get((severity or "").lower(), 1)


def worsen_detail(
    base: Finding,
    head: Finding,
    *,
    min_delta: float = 0.0,
    relative: float = WORSEN_RELATIVE,
) -> Optional[dict]:
    """Decide whether ``head`` is worse than ``base`` for the same fingerprint.

    The metric is the primary evidence. A matched finding is WORSENED only
    when ``(head - base) / base > relative``. The strict comparison follows
    the frozen evaluation contract's ``> 20%`` boundary. A zero or negative
    base metric has no meaningful percentage-growth denominator and is not
    classified as WORSENED by metric evidence.

    Severity is only a fallback for findings whose detector reports no number
    (``Dead Code``, ``Orphan Module``...).  It is weaker evidence because
    severity follows the configured thresholds, so this branch is recorded with
    ``reason="severity"`` and can be disabled from the CLI.
    """
    base_value = base.metric_value
    head_value = head.metric_value
    if base_value is not None and head_value is not None:
        delta = head_value - base_value
        # Detector metrics are decimal measurements. Binary rounding can turn
        # an exact 20% increase (e.g. 9.5 -> 11.4) into a false regression.
        if (base_value > 0 and delta >= min_delta
                and Decimal(str(head_value)) > Decimal(str(base_value)) * (1 + Decimal(str(relative)))):
            return {
                "reason": "metric",
                "metric": metric_key_for(head),
                "base": base_value,
                "head": head_value,
                "delta": delta,
            }
        return None
    if _severity_rank(head.severity) > _severity_rank(base.severity):
        return {
            "reason": "severity",
            "metric": None,
            "base": None,
            "head": None,
            "severity_base": base.severity,
            "severity_head": head.severity,
        }
    return None


def long_method_crossings(base: dict, head: dict, findings: Iterable[Finding], root: str) -> dict:
    """Evidence for previously measured methods whose effective length now exceeds the limit."""
    return _threshold_crossings(base, head, findings, root, "Long Method", "LONG_METHOD_LINES", 1)


def measured_crossings(base: dict, head: dict, findings: List[Finding], root: str) -> dict:
    evidence = long_method_crossings(base.get("long_methods"), head.get("long_methods"), findings, root)
    evidence.update(_threshold_crossings(base.get("large_classes"), head.get("large_classes"),
                                        findings, root, "Large Class", "LARGE_CLASS_METHODS", 0))
    return evidence


def _threshold_crossings(base, head, findings, root, rule, metric, minimum):
    if not isinstance(head, dict):
        return {}
    threshold = head.get("threshold")
    if (not isinstance(base, dict) or type(threshold) not in (int, float)
            or base.get("threshold") != threshold):
        return {}
    before = base.get("files")
    if not isinstance(before, dict):
        return {}
    after = head.get("files")
    if not isinstance(after, dict):
        return {}
    evidence = {}
    for finding in findings:
        if finding.category != "code" or finding.smell_type != rule:
            continue
        path = relative_path(finding.file_path, root)
        old_file = before.get(path)
        new_file = after.get(path)
        if not isinstance(old_file, dict) or not isinstance(new_file, dict):
            continue
        old = old_file.get(finding.symbol)
        new = new_file.get(finding.symbol)
        if (type(old) is int and type(new) is int and new == finding.metric_value
                and minimum <= old <= threshold < new):
            evidence[fingerprint_string(finding, root)] = {
                "reason": "metric", "metric": metric, "base": old,
                "head": new, "delta": new - old, "threshold": threshold,
            }
    return evidence


def threshold_for(
    spec: MetricSpec, thresholds: Dict[str, Dict[str, float]]
) -> Optional[float]:
    """Configured threshold for a spec, or ``None`` when unusable.

    A missing or non-positive threshold is treated as unusable rather than as
    zero: dividing by it would either explode the score or silently mark every
    finding as infinitely bad.
    """
    section = thresholds.get(spec.section) or {}
    value = section.get(spec.threshold_key)
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    return numeric
