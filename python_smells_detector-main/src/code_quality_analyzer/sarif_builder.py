"""SARIF 2.1.0 export for PyExamine findings.

This module is the contract between the detectors and every CI surface we
support (GitHub code scanning, ``gh api`` PR review comments, third-party
SARIF viewers).  It is deliberately free of detector knowledge: it consumes
:class:`~code_quality_analyzer.finding.Finding` objects and the static
:mod:`rule_registry`.

Design rules that the rest of the code base relies on:

* **Stable identity.**  ``partialFingerprints["pyex-v1"]`` is derived from
  (ruleId, path relative to the analysed root, qualified symbol) and never
  from the line number, so moving code inside a file does not mint a "new"
  finding.
* **Deterministic output.**  ``results`` and ``rules`` are sorted by stable
  keys and every mapping is built in a fixed order, so two runs over the same
  tree serialise to identical bytes (except ``invocations[0].startTimeUtc``,
  which callers may strip).
* **Relative URIs only.**  Paths are emitted relative to ``%SRCROOT%`` so a
  SARIF file produced on Windows stays valid on a Linux runner and never
  leaks a drive letter or a user name.
"""

from __future__ import annotations

import hashlib
import os
from typing import Iterable, List, Optional, Sequence
from urllib.parse import quote

from .finding import (
    CATEGORY_ARCHITECTURAL,
    CATEGORY_CODE,
    CATEGORY_STRUCTURAL,
    Finding,
)
from .rule_registry import RULES, Rule, rule_for

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SRCROOT = "%SRCROOT%"
FINGERPRINT_KEY = "pyex-v1"

# A ``uriBaseId`` referenced by an ``artifactLocation`` must resolve, otherwise
# strict SARIF consumers (and the GitHub upload step) report an unknown base.
# ``file:///`` keeps the base machine-independent: ``%SRCROOT%`` + relative uri
# is still a valid absolute file URI without leaking a drive letter or user name.
_SRCROOT_URI = "file:///"

LEVEL_POLICIES = ("strict", "triage", "advisory")

# Map our lifecycle names onto SARIF 2.1.0 result.baselineState values.
_BASELINE_STATES = {
    "NEW": "new",
    "WORSENED": "updated",
    "UNCHANGED": "unchanged",
    "RESOLVED": "absent",
}

_INFORMATION_URI = "https://python-smell.readthedocs.io/en/latest/"

_CATEGORY_LABEL = {
    CATEGORY_CODE: "Code smell",
    CATEGORY_STRUCTURAL: "Structural smell",
    CATEGORY_ARCHITECTURAL: "Architectural smell",
}


def _posix(path: str) -> str:
    return path.replace("\\", "/")


def _normalised_absolute(path: str) -> Optional[str]:
    """POSIX form of an absolute path, without mangling foreign-style roots."""
    if not path:
        return None
    if os.name == "nt" and path.startswith("/"):
        # A POSIX-absolute root (a CI checkout path stored in a baseline) must
        # not be run through os.path.abspath, which would prepend a drive.
        return path.replace("\\", "/")
    if not os.path.isabs(path):
        return None
    return os.path.abspath(path).replace("\\", "/")


def relative_uri(file_path: str, root: Optional[str]) -> str:
    """Return the ``uri`` for a finding location.

    ``root`` is the analysed tree root.  When the finding lives inside it the
    URI is relative and ``%SRCROOT%`` applies; otherwise the path is left as
    given (POSIX-normalised) and the caller resolves it without a base id.

    ``analyze()`` reports paths exactly as the caller passed them, which is
    usually relative to the CWD while ``root`` is absolute.  The second
    comparison below stitches that pair; it only fires when the resolved path
    really is inside the root, so an unrelated relative path is untouched.
    """
    if not file_path:
        return ""
    p = file_path.replace("\\", "/")
    base = _normalised_absolute(root) if root else None
    if base:
        base = base.rstrip("/")
        if p == base or p.startswith(base + "/"):
            return quote(p[len(base):].lstrip("/"), safe="/")
        if not os.path.isabs(file_path):
            candidate = _normalised_absolute(os.path.abspath(file_path)) or ""
            if candidate == base or candidate.startswith(base + "/"):
                return quote(candidate[len(base):].lstrip("/"), safe="/")
    return quote(p, safe="/:")


def _split_cross_file_paths(file_path: str):
    """Split the comma-joined path that cross-file detectors emit.

    ``Duplicate Code`` and friends report one finding that spans several
    files as ``"a.py, b.py"``.  SARIF needs a primary location plus
    ``relatedLocations``, so the string is split here rather than downstream.
    """
    if not file_path:
        return []
    parts = [part.strip() for part in file_path.split(",")]
    return [part for part in parts if part] or [file_path]


def fingerprint(finding: Finding, root: Optional[str] = None) -> str:
    """Stable 16-hex identity for a finding.

    The tuple is (ruleId, relative path, symbol).  ``line`` is intentionally
    excluded: line drift is the single largest source of false "new" findings
    in an incremental gate.
    """
    rule_id = rule_id_for_finding(finding)
    uri = relative_uri(finding.file_path, root or getattr(finding, "tree_root", None))
    symbol = finding.symbol or ""
    digest = hashlib.sha256("\x00".join((rule_id, uri, symbol)).encode("utf-8"))
    return digest.hexdigest()[:16]


def rule_id_for_finding(finding: Finding) -> str:
    return rule_for(finding.smell_type, finding.category).rule_id


def sarif_level(finding: Finding, policy: str = "strict") -> str:
    """Map a PyExamine severity onto a SARIF result level.

    ``triage`` exists because measurements over four real projects show that
    53-72 % of findings are structural and 33-43 % of *all* findings are
    ``high`` there.  A gate that maps every ``high`` to ``error`` is red on
    every PR, which is how gates get switched off.  ``triage`` keeps the
    expensive categories authoritative for code and architectural smells but
    demotes structural ``high`` to ``warning``.
    """
    severity = (finding.severity or "medium").lower()
    if policy not in LEVEL_POLICIES:
        raise ValueError("unknown level policy %r (choose from %s)" % (policy, ", ".join(LEVEL_POLICIES)))
    if policy == "strict":
        return {"high": "error", "medium": "warning", "low": "note"}.get(severity, "warning")
    if policy == "advisory":
        return {"high": "warning", "medium": "note", "low": "note"}.get(severity, "note")
    # triage
    if severity == "high":
        if finding.category == CATEGORY_STRUCTURAL:
            return "warning"
        return "error"
    if severity == "medium":
        return "warning"
    return "note"


def _rule_descriptor(rule: Rule) -> dict:
    descriptor = {
        "id": rule.rule_id,
        "name": rule.name.replace(" ", ""),
        "shortDescription": {"text": "%s (%s)" % (rule.name, rule.legacy_id)},
        "fullDescription": {
            "text": "%s detected by PyExamine. Reported category: %s."
            % (rule.name, _CATEGORY_LABEL.get(rule.category, rule.category))
        },
        "defaultConfiguration": {"level": "warning"},
        "properties": {
            "category": rule.category,
            "legacyId": rule.legacy_id,
            "tags": [rule.category, "python", "code-smell"],
        },
        "helpUri": _INFORMATION_URI,
    }
    return descriptor


def _result(
    finding: Finding,
    root: Optional[str],
    policy: str,
    rule_index: dict,
    risks: Optional[dict] = None,
    baseline_states: Optional[dict] = None,
) -> dict:
    rule = rule_for(finding.smell_type, finding.category)
    effective_root = root or getattr(finding, "tree_root", None)
    parts = _split_cross_file_paths(finding.file_path)
    uri = relative_uri(parts[0], effective_root)
    location = {
        "physicalLocation": {
            "artifactLocation": {"uri": uri, "uriBaseId": SRCROOT},
        }
    }
    if finding.line:
        location["physicalLocation"]["region"] = {"startLine": int(finding.line)}
    text = finding.description or rule.name
    if finding.symbol:
        text = "%s [%s]" % (text, finding.symbol)
    result = {
        "ruleId": rule.rule_id,
        "ruleIndex": rule_index[rule.rule_id],
        "level": sarif_level(finding, policy),
        "message": {"text": text},
        "locations": [location],
        "partialFingerprints": {FINGERPRINT_KEY: fingerprint(finding, root)},
        "properties": {
            "category": finding.category,
            "severity": (finding.severity or "medium").lower(),
            "symbol": finding.symbol or "",
        },
    }
    if finding.metric_value is not None:
        result["properties"]["metricValue"] = finding.metric_value
    if baseline_states:
        state = baseline_states.get(fingerprint(finding, root))
        if state:
            # SARIF 2.1.0 §3.27.24: new / unchanged / updated / absent.
            # "updated" is exactly what a WORSENED finding is: same identity,
            # worse measurement.  GitHub Code Scanning uses this to group
            # alerts across runs instead of reopening them as brand new.
            result["baselineState"] = _BASELINE_STATES.get(state, state)
    if risks:
        score = risks.get(fingerprint(finding, root))
        if score is not None:
            # SARIF 2.1.0 §3.27.19: rank is 0.0-100.0, higher means more important.
            result["rank"] = round(float(score.score), 2)
            result["properties"]["riskScore"] = round(float(score.score), 2)
            result["properties"]["risk"] = score.as_dict()
    if len(parts) > 1:
        result["relatedLocations"] = [
            {
                "id": index + 1,
                "message": {"text": "Also appears in %s" % (part,)},
                "physicalLocation": {
                    "artifactLocation": {
                        "uri": relative_uri(part, effective_root),
                        "uriBaseId": SRCROOT,
                    }
                },
            }
            for index, part in enumerate(parts[1:])
        ]
    return result


def _sorted_findings(findings: Iterable[Finding], root: Optional[str]) -> List[Finding]:
    return sorted(
        findings,
        key=lambda f: (
            relative_uri(f.file_path, root or getattr(f, "tree_root", None)),
            f.line or 0,
            rule_id_for_finding(f),
            f.symbol or "",
        ),
    )


def build_sarif(
    findings: Sequence[Finding],
    *,
    tool_version: str,
    level_policy: str = "strict",
    root: Optional[str] = None,
    include_all_rules: bool = False,
    notifications: Optional[Sequence[dict]] = None,
    risks: Optional[dict] = None,
    baseline_states: Optional[dict] = None,
) -> dict:
    """Serialise findings into a SARIF 2.1.0 log.

    ``root`` is the tree the paths should be relative to; when omitted each
    finding's own ``tree_root`` is used (base and head findings therefore stay
    individually correct).

    ``risks`` maps a finding's SARIF fingerprint to an object exposing
    ``score`` (0-100) and ``as_dict()``; passing it adds ``result.rank`` and
    ``properties.riskScore`` without changing anything else.
    """
    if level_policy not in LEVEL_POLICIES:
        raise ValueError("unknown level policy %r" % (level_policy,))
    ordered = _sorted_findings(findings, root)
    used_ids = {rule_id_for_finding(f) for f in ordered}
    if include_all_rules:
        rules = list(RULES)
    else:
        rules = [rule for rule in RULES if rule.rule_id in used_ids]

    rule_index = {rule.rule_id: i for i, rule in enumerate(rules)}
    results = [
        _result(f, root, level_policy, rule_index, risks, baseline_states)
        for f in ordered
    ]

    invocation = {"executionSuccessful": True}
    if notifications:
        invocation["toolExecutionNotifications"] = list(notifications)

    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "PyExamine",
                        "fullName": "PyExamine - Python smell detection",
                        "version": tool_version,
                        "informationUri": _INFORMATION_URI,
                        "rules": [_rule_descriptor(rule) for rule in rules],
                    }
                },
                "invocations": [invocation],
                "results": results,
                "columnKind": "utf16CodeUnits",
                "originalUriBaseIds": {SRCROOT: {"uri": _SRCROOT_URI}},
                "properties": {
                    "levelPolicy": level_policy,
                    "resultCount": len(results),
                },
            }
        ],
    }


def build_sarif_from_report(
    report: dict,
    *,
    tool_version: str,
    level_policy: str = "strict",
    root: Optional[str] = None,
    include_all_rules: bool = False,
) -> dict:
    """Adapter for the ``analyze()`` dict produced by :mod:`code_quality_analyzer.main`.

    The JSON report groups findings under ``findings`` with a ``type`` field of
    ``code``/``structural``/``architectural``; every other key matches what
    :class:`Finding` needs.
    """
    findings: List[Finding] = []
    for item in report.get("findings", []):
        findings.append(
            Finding(
                category=item.get("type", CATEGORY_CODE),
                smell_type=item.get("name", ""),
                file_path=item.get("file_path", ""),
                symbol=item.get("module_class") or "",
                line=item.get("line_number") or 0,
                severity=item.get("severity") or "medium",
                description=item.get("description") or "",
                metric_value=item.get("metric_value"),
            )
        )
    return build_sarif(
        findings,
        tool_version=tool_version,
        level_policy=level_policy,
        root=root or report.get("target"),
        include_all_rules=include_all_rules,
    )
