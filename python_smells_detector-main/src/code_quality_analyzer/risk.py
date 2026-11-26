"""Explainable risk ranking for findings (PROJECT_OVERVIEW §4.4).

The detector answers *what* smells exist.  A reviewer needs a second answer:
*which of these is worth my next ten minutes?*  This module turns one finding
into a 0-100 score built from four components whose weights are fixed and
auditable:

    risk = 100 * (0.35 * exceeds
                + 0.25 * change
                + 0.20 * centrality
                + 0.20 * confidence)

Each component is normalised to ``[0, 1]`` and documented below.  Every
component is derived from data the tool already has, so a score can be
recomputed by hand from the report — no hidden model, no learned weights.

``exceeds``
    How far past its configured threshold the measured value sits, on a log
    scale: ``clamp(log(value / threshold) / log(10), 0, 1)``.  A finding at
    threshold scores 0, one at 10x saturates at 1.  The first version used a
    linear ``(ratio - 1) / 1`` capped at 2x, and measurement killed it: across
    four corpora 73-80% of findings already exceeded 2x, so the whole middle of
    the distribution collapsed onto one value (p90 52.5 vs max 52.9 on flask)
    and the ranking had no resolution left.  Log scale keeps 2x at 0.30,
    5x at 0.70 and 10x at 1.0, so the component still separates findings that
    are all "bad" in absolute terms.
    Findings whose detector reports no numeric metric fall back to the
    severity band (high 1.0 / medium 0.5 / low 0.25) and are marked
    ``measured=False``.

``change``
    Whether the finding sits on lines this pull request actually touched:
    inside a changed hunk (with a small context gutter) 1.0, elsewhere in a
    modified file 0.3, untouched file 0.0.  Module-level findings have no line
    and also score 0.3 for a modified file: a module-wide verdict cannot be
    attributed to the diff, and at 0.6 they outranked the line-anchored finding
    the same PR actually introduced (see the note in ``CHANGE_MODULE_LEVEL``).

``centrality``
    Normalised fan-in of the finding's module inside the project graph.  A
    smell in a module that 40 others import is more consequential than the
    same smell in a leaf.  Modules with no graph node score 0.

``confidence``
    How much the *detection mechanism* deserves trust, penalised by how
    ubiquitous the rule is in this run:
    ``mechanism * (1 - 0.5 * share)``.  A rule that fires on half the codebase
    is statistically indistinguishable from that codebase's normal shape, so
    its individual instances are weaker evidence.  This is a proxy for
    precision — the project has no labelled corpus — and the ADR says so.

The score is a *ranking*, not a probability.  It never suppresses a finding:
``--min-risk`` filters the gate, not the report.
"""

from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .finding import (
    CATEGORY_ARCHITECTURAL,
    CATEGORY_STRUCTURAL,
    Finding,
)
from .fingerprint import relative_path
from .metrics import (
    METRIC_SPECS as METRIC_SPECS,  # explicit re-export: one owner for the table
)
from .metrics import (
    extract_metric,
)
from .metrics import (
    threshold_for as _threshold_for,
)
from .rule_registry import rule_for

RISK_SCHEMA_VERSION = 1

# Component weights.  Sum is 1.0 by construction; ``risk_weights`` asserts it.
W_EXCEEDS = 0.35
W_CHANGE = 0.25
W_CENTRALITY = 0.20
W_CONFIDENCE = 0.20

# Ratio past the threshold at which ``exceeds`` saturates (log scale).
EXCEED_FULL_SCALE = 10.0

# Lines of slack around a changed hunk that still count as "touched".
CHANGE_GUTTER = 3

# Partial credit when a finding has no line but its file changed.
CHANGE_FILE_ONLY = 0.3
# A module-level verdict is not attributable to the diff, so it can never beat
# a line-anchored finding that the diff actually touched.  Measured on the demo
# repo: at 0.6 an "Orphan Module" on a merely-modified file outranked the
# Long Method introduced by the same PR, which is the wrong answer for review.
CHANGE_MODULE_LEVEL = 0.3

# Severity fallback when the detector exposes no numeric metric.  A three-way
# severity band is weaker evidence than a measured ratio, so it tops out at 0.6
# instead of taking full credit: at 1.0 an unmeasured "High Number of Classes"
# outranked a class whose LCOM was measured at 19x its threshold, which inverted
# the ranking the numbers were supposed to provide.
SEVERITY_FALLBACK = {"high": 0.6, "medium": 0.4, "low": 0.2}

# Detection-mechanism confidence, by category and rule shape.
CONFIDENCE_MEASURED = 0.90
CONFIDENCE_ARCHITECTURAL = 0.75
CONFIDENCE_HEURISTIC = 0.60

# Code smells whose detectors decide by a hard structural rule rather than a
# heuristic pattern; everything else in the code category is heuristic.
_CODE_MEASURED = frozenset(
    {
        "Dead Code",
        "Duplicate Code",
        "Large Class",
        "Long Method",
        "Long Parameter List",
        "Message Chains",
        "Primitive Obsession",
        "Switch Statements",
    }
)

# Frequency penalty: share of this run's findings carrying the same rule.
FREQUENCY_PENALTY = 0.5


@dataclass(frozen=True)
class RiskScore:
    """One finding's 0-100 risk score with its four components and the reasons."""

    score: float
    exceeds: float
    change: float
    centrality: float
    confidence: float
    measured: bool
    metric_value: Optional[float]
    threshold: Optional[float]
    metric_key: Optional[str]
    fan_in_count: int = 0
    reasons: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "score": round(self.score, 2),
            "components": {
                "exceeds": round(self.exceeds, 4),
                "change": round(self.change, 4),
                "centrality": round(self.centrality, 4),
                "confidence": round(self.confidence, 4),
            },
            "measured": self.measured,
            "metric": (
                None
                if self.metric_key is None
                else {
                    "key": self.metric_key,
                    "value": self.metric_value,
                    "threshold": self.threshold,
                }
            ),
            "fan_in": self.fan_in_count,
            "reasons": list(self.reasons),
        }


def risk_weights() -> Dict[str, float]:
    """The weights, for reports and assertions."""
    weights = {
        "exceeds": W_EXCEEDS,
        "change": W_CHANGE,
        "centrality": W_CENTRALITY,
        "confidence": W_CONFIDENCE,
    }
    assert math.isclose(sum(weights.values()), 1.0), "risk weights must sum to 1"
    return weights


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def exceeds_component(
    finding: Finding, thresholds: Dict[str, Dict[str, float]]
) -> Tuple[float, bool, Optional[float], Optional[float], Optional[str]]:
    """How far past threshold, plus the evidence behind it."""
    value, spec = extract_metric(finding)
    if value is None or spec is None:
        severity = (finding.severity or "medium").lower()
        return SEVERITY_FALLBACK.get(severity, 0.5), False, None, None, None
    threshold = _threshold_for(spec, thresholds)
    if threshold is None:
        severity = (finding.severity or "medium").lower()
        return SEVERITY_FALLBACK.get(severity, 0.5), False, value, None, spec.threshold_key
    ratio = value / threshold
    if ratio <= 1.0:
        component = 0.0
    else:
        # Log scale: 2x -> 0.30, 5x -> 0.70, 10x -> 1.0.  A linear ramp
        # saturates too early and flattens the distribution (see module docs).
        component = _clamp(math.log(ratio) / math.log(EXCEED_FULL_SCALE))
    return component, True, value, threshold, spec.threshold_key


def confidence_component(
    finding: Finding, share: float, measured: bool
) -> float:
    """Detection-mechanism trust, discounted by how ubiquitous the rule is."""
    if finding.category == CATEGORY_ARCHITECTURAL:
        base = CONFIDENCE_ARCHITECTURAL
    elif finding.category == CATEGORY_STRUCTURAL:
        base = CONFIDENCE_MEASURED
    elif measured or finding.smell_type in _CODE_MEASURED:
        base = CONFIDENCE_MEASURED
    else:
        base = CONFIDENCE_HEURISTIC
    penalty = 1.0 - FREQUENCY_PENALTY * _clamp(share)
    return _clamp(base * penalty)


def _module_fan_in(
    finding: Finding, tree_root: Optional[str], fan_in: Dict[str, int]
) -> int:
    """How many modules depend on the finding's module (0 when unknown)."""
    if not fan_in:
        return 0
    module = finding.symbol.split(".")[0] if finding.symbol else ""
    candidates = []
    if module:
        candidates.append(module)
    if finding.file_path and tree_root:
        relative = relative_path(finding.file_path, tree_root)
        stem = relative[:-3].replace("/", ".") if relative.endswith(".py") else relative
        if stem.endswith(".__init__"):
            stem = stem[: -len(".__init__")]
        candidates.append(stem)
    value = 0
    for candidate in candidates:
        if candidate in fan_in:
            value = max(value, int(fan_in[candidate]))
    return max(0, value)


def centrality_component(
    finding: Finding, tree_root: Optional[str], fan_in: Dict[str, int]
) -> float:
    """Normalised fan-in of the finding's module."""
    value = _module_fan_in(finding, tree_root, fan_in)
    if value <= 0 or not fan_in:
        return 0.0
    peak = max(int(v) for v in fan_in.values()) or 1
    return _clamp(math.log1p(value) / math.log1p(peak))


# --------------------------------------------------------------------------- #
# Changed-line extraction
# --------------------------------------------------------------------------- #

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_diff_hunks(diff_text: str) -> Dict[str, List[Tuple[int, int]]]:
    """Map repository-relative path -> inclusive line ranges added in head."""
    ranges: Dict[str, List[Tuple[int, int]]] = {}
    current: Optional[str] = None
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            if target == "/dev/null":
                current = None
                continue
            if target.startswith("b/"):
                target = target[2:]
            current = target
            ranges.setdefault(current, [])
            continue
        if raw.startswith("@@"):
            match = _HUNK.match(raw)
            if match is None or current is None:
                continue
            start = int(match.group(1))
            count = 1 if match.group(2) is None else int(match.group(2))
            if count <= 0:
                continue
            ranges[current].append((start, start + count - 1))
    return {path: hunks for path, hunks in ranges.items() if hunks}


def changed_lines(
    repo_root: str,
    base_ref: str,
    head_ref: str,
    timeout: int = 120,
) -> Dict[str, List[Tuple[int, int]]]:
    """Added/modified line ranges between two refs; empty dict when git fails.

    A failure is not fatal: risk ranking then simply has no change signal, and
    the report marks every ``change`` component as unmeasured by scoring 0.
    """
    command = [
        "git",
        "-C",
        repo_root,
        "diff",
        "-U0",
        "--no-color",
        "--no-ext-diff",
        base_ref,
        head_ref,
        "--",
        "*.py",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if completed.returncode != 0:
        return {}
    return parse_diff_hunks(completed.stdout)


def change_component(
    finding: Finding,
    tree_root: Optional[str],
    hunks: Dict[str, List[Tuple[int, int]]],
) -> float:
    """How much of this finding sits on lines the change touched."""
    if not hunks or not finding.file_path or not tree_root:
        return 0.0
    relative = relative_path(finding.file_path, tree_root)
    touched = hunks.get(relative)
    if not touched:
        return 0.0
    if finding.line is None:
        return CHANGE_MODULE_LEVEL
    line = int(finding.line)
    for start, end in touched:
        if start - CHANGE_GUTTER <= line <= end + CHANGE_GUTTER:
            return 1.0
    return CHANGE_FILE_ONLY


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #

# Human wording for the metric behind the "exceeds" component (PROJECT_OVERVIEW
# 4.4 asks every score to explain itself, not just publish four numbers).
_METRIC_LABELS: Dict[str, Tuple[str, str]] = {
    "LONG_METHOD_LINES": ("method length", "lines"),
    "LARGE_CLASS_METHODS": ("class method count", "methods"),
    "NOM_THRESHOLD": ("class method count", "methods"),
    "CYCLOMATIC_COMPLEXITY_THRESHOLD": ("cyclomatic complexity", "branch points"),
    "LOC_THRESHOLD": ("module size", "code lines"),
    "MAX_FILE_LENGTH": ("file length", "lines"),
    "MAX_FANOUT": ("module fan-out", "modules"),
    "GOD_OBJECT_FUNCTIONS": ("module function count", "functions"),
}


def metric_label(metric_key: Optional[str]) -> Tuple[str, str]:
    """Readable name and unit for a threshold key."""
    if not metric_key:
        return ("metric", "units")
    return _METRIC_LABELS.get(metric_key, (metric_key.lower().replace("_", " "), "units"))


def risk_reasons(
    *,
    measured: bool,
    value: Optional[float],
    threshold: Optional[float],
    metric_key: Optional[str],
    change: float,
    fan_in_count: int,
    confidence: float,
) -> Tuple[str, ...]:
    """The sentences behind one score, in the order a reviewer reads them.

    Wording is deliberately evidence-first: the number, the threshold it is
    measured against, whether the diff touched it, how central the module is,
    and how much the detector itself is trusted.  Lifecycle wording ("added by
    this change") belongs to the caller, which knows the state.
    """
    reasons: List[str] = []
    label, unit = metric_label(metric_key)
    if measured and threshold and value is not None:
        ratio = value / threshold if threshold else 0.0
        if ratio >= 1.0:
            reasons.append(
                "%s is %g %s against a threshold of %g (%.1fx)"
                % (label, value, unit, threshold, ratio)
            )
        else:
            reasons.append(
                "%s is %g %s, inside the %g threshold"
                % (label, value, unit, threshold)
            )
    elif value is not None and threshold is None:
        reasons.append(
            "%s is %g %s but no threshold is configured; severity band used instead"
            % (label, value, unit)
        )
    else:
        reasons.append("no numeric metric for this rule; severity band used instead")

    if change >= 1.0:
        reasons.append("the reported line is inside a changed hunk")
    elif change > 0.0:
        reasons.append("the containing file changed, but the reported line did not")

    if fan_in_count > 0:
        reasons.append("the enclosing module is imported by %d other module(s)" % fan_in_count)

    reasons.append("detection confidence %.2f" % confidence)
    return tuple(reasons)


def score_findings(
    findings: Sequence[Finding],
    *,
    thresholds: Optional[Dict[str, Dict[str, float]]] = None,
    tree_root: Optional[str] = None,
    hunks: Optional[Dict[str, List[Tuple[int, int]]]] = None,
    fan_in: Optional[Dict[str, int]] = None,
    fingerprint_of=None,
) -> Dict[str, RiskScore]:
    """Score every finding; keys are fingerprints so callers can look them up."""
    thresholds = thresholds or {}
    hunks = hunks or {}
    fan_in = fan_in or {}
    fingerprint_of = fingerprint_of or (lambda finding: _fallback_key(finding, tree_root))

    counts: Dict[str, int] = {}
    for finding in findings:
        rule_id = rule_for(finding.smell_type, finding.category).rule_id
        counts[rule_id] = counts.get(rule_id, 0) + 1
    total = max(1, len(findings))

    scores: Dict[str, RiskScore] = {}
    for finding in findings:
        rule_id = rule_for(finding.smell_type, finding.category).rule_id
        exceeds, measured, value, threshold, key = exceeds_component(finding, thresholds)
        share = counts.get(rule_id, 1) / total
        confidence = confidence_component(finding, share, measured)
        centrality = centrality_component(finding, tree_root, fan_in)
        fan_in_count = _module_fan_in(finding, tree_root, fan_in)
        change = change_component(finding, tree_root, hunks)
        score = 100.0 * (
            W_EXCEEDS * exceeds
            + W_CHANGE * change
            + W_CENTRALITY * centrality
            + W_CONFIDENCE * confidence
        )
        reasons = risk_reasons(
            measured=measured,
            value=value,
            threshold=threshold,
            metric_key=key,
            change=change,
            fan_in_count=fan_in_count,
            confidence=confidence,
        )
        scores[fingerprint_of(finding)] = RiskScore(
            score=round(score, 2),
            exceeds=exceeds,
            change=change,
            centrality=centrality,
            confidence=confidence,
            measured=measured,
            metric_value=value,
            threshold=threshold,
            metric_key=key,
            fan_in_count=fan_in_count,
            reasons=reasons,
        )
    return scores


def _fallback_key(finding: Finding, tree_root: Optional[str]) -> str:
    """Stable key when the caller has no fingerprint helper: rule + path + symbol."""
    rule_id = rule_for(finding.smell_type, finding.category).rule_id
    path = relative_path(finding.file_path, tree_root) if tree_root else finding.file_path
    return "%s|%s|%s" % (rule_id, path, finding.symbol or "")


def rank_findings(
    findings: Iterable[Finding], scores: Dict[str, RiskScore], fingerprint_of
) -> List[Finding]:
    """Findings ordered by descending risk, ties broken deterministically."""
    def sort_key(finding: Finding):
        score = scores.get(fingerprint_of(finding))
        return (
            -(score.score if score else 0.0),
            finding.file_path or "",
            finding.line or 0,
            rule_for(finding.smell_type, finding.category).rule_id,
            finding.symbol or "",
        )

    return sorted(findings, key=sort_key)


def gate_by_risk(
    findings: Sequence[Finding], scores: Dict[str, RiskScore], fingerprint_of, min_risk: float
) -> List[Finding]:
    """Findings at or above ``min_risk``, in the caller's order."""
    kept = []
    for finding in findings:
        score = scores.get(fingerprint_of(finding))
        if score is not None and score.score >= min_risk:
            kept.append(finding)
    return kept
