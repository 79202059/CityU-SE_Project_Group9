"""Persistent baseline of accepted findings, used to gate only *new* smells.

A baseline file is the durable form of "this repository already looked like
this".  CI compares the head checkout against it and reports only what the pull
request introduced, which is the whole point of a delta gate: a repository with
4 000 pre-existing findings must still be able to adopt the tool.

Fingerprints are produced by :func:`code_quality_analyzer.sarif_builder.fingerprint`
so the baseline, the SARIF output and the PR comments always agree on identity.

Baseline files intentionally store relative paths and no absolute root: a
baseline committed to a repository has to be identical on every machine.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from .finding import Finding
from .fingerprint import (
    NEW,
    RESOLVED,
    UNCHANGED,
    WORSENED,
    WorsenJudge,
    fingerprint_string,
    relative_path,
)
from .sarif_builder import fingerprint, rule_id_for_finding

BASELINE_SCHEMA_VERSION = 1
BASELINE_FILENAME = ".pyexamine-baseline.json"


def baseline_payload(
    findings: List[Finding],
    root: str,
    *,
    tool_version: str,
    ref: Optional[str] = None,
) -> dict:
    """Build the JSON-serialisable baseline document for ``findings``."""
    records = []
    for finding in findings:
        records.append(
            {
                "fp": fingerprint(finding, root),
                "rule_id": rule_id_for_finding(finding),
                "name": finding.smell_type,
                "category": finding.category,
                "path": relative_path(finding.file_path, root),
                "symbol": finding.symbol or "",
                "line": finding.line,
                "severity": (finding.severity or "medium").lower(),
                # The metric is what lets a later run say "this got worse"
                # instead of only "this is still here".  Baselines written
                # by older versions lack the key and skip the comparison.
                "metric": finding.metric_value,
            }
        )
    records.sort(key=lambda r: (r["path"], r["line"] or 0, r["rule_id"], r["symbol"]))
    by_category: Dict[str, int] = {}
    for record in records:
        by_category[record["category"]] = by_category.get(record["category"], 0) + 1
    payload = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "tool": {"name": "pyexamine-delta", "version": tool_version},
        "counts": {"total": len(records), "by_category": by_category},
        "findings": records,
    }
    if ref:
        payload["ref"] = ref
    return payload


def write_baseline(path: str, payload: dict) -> None:
    """Write a baseline document atomically (LF endings, UTF-8, stable order)."""
    text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(tmp_path, path)


def load_baseline(path: str) -> Optional[dict]:
    """Load a baseline document, or ``None`` when it is absent.

    A missing baseline is not an error: the first run of the gate in a
    repository writes one instead of failing.
    """
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or "findings" not in payload:
        raise ValueError(
            "%s is not a PyExamine baseline (missing 'findings')" % path
        )
    return payload


def finding_from_record(record: dict, root: str) -> Finding:
    """Rehydrate a baseline record into a Finding located under ``root``."""
    path = record.get("path") or ""
    # A module-level smell records the analysed directory as its file_path,
    # which ``relative_path`` stores as ".".  Joining it would rebuild
    # "<root>/.", a different SARIF fingerprint than the one the baseline
    # recorded, so the same finding would read as NEW + RESOLVED
    # (regression found while auditing the cache round-trip).
    if not path or path == ".":
        file_path = root
    else:
        file_path = os.path.join(root, path.replace("/", os.sep))
    return Finding(
        category=record.get("category") or "code",
        smell_type=record.get("name") or "",
        file_path=file_path,
        symbol=record.get("symbol") or "",
        line=record.get("line"),
        severity=record.get("severity") or "medium",
        description="",
        metric_value=record.get("metric"),
    )


def diff_against_baseline(
    baseline: dict,
    head_findings: List[Finding],
    head_root: str,
    *,
    worsen: Optional[WorsenJudge] = None,
    worsen_details: Optional[Dict[str, dict]] = None,
    fuzzy: Optional[object] = None,
    fuzzy_details: Optional[Dict[str, dict]] = None,
) -> Dict[str, List[Finding]]:
    """Classify ``head_findings`` against a stored baseline.

    Returns ``{NEW, WORSENED, UNCHANGED, RESOLVED}``.  RESOLVED findings are
    rehydrated from the baseline with paths rooted at the head checkout so
    SARIF can still emit a location for them.

    A stored record carries its metric, so a run can tell "still there and
    unchanged" from "still there and worse" without checking out the base
    revision - that is what keeps the incremental mode down to one tree.
    """
    baseline_records = baseline.get("findings", []) if baseline else []
    baseline_index = {
        record.get("fp"): record for record in baseline_records if record.get("fp")
    }

    new: List[Finding] = []
    worsened: List[Finding] = []
    unchanged: List[Finding] = []
    seen = set()
    for finding in head_findings:
        key = fingerprint(finding, head_root)
        seen.add(key)
        record = baseline_index.get(key)
        if record is None:
            new.append(finding)
            continue
        evidence = None
        if worsen is not None:
            evidence = worsen(finding_from_record(record, head_root), finding)
        if evidence is None:
            unchanged.append(finding)
        else:
            worsened.append(finding)
            if worsen_details is not None:
                worsen_details[key] = evidence

    resolved = [
        finding_from_record(record, head_root)
        for key, record in baseline_index.items()
        if key not in seen
    ]

    # A rename or a move changes the fingerprint, so the exact stage files it
    # as RESOLVED + NEW.  The optional fuzzy stage pairs those leftovers, using
    # the same rule as the checkout comparison (they run through one matcher).
    if fuzzy is not None and resolved and new:
        paired_new_ids = set()
        paired_resolved_ids = set()
        for pair in fuzzy(resolved, new, head_root, head_root):
            paired_resolved_ids.add(id(pair.base))
            paired_new_ids.add(id(pair.head))
            evidence = None
            if worsen is not None:
                evidence = worsen(pair.base, pair.head)
            if evidence is None:
                unchanged.append(pair.head)
            else:
                worsened.append(pair.head)
                if worsen_details is not None:
                    worsen_details[fingerprint(pair.head, head_root)] = evidence
            if fuzzy_details is not None:
                detail = pair.as_dict() if hasattr(pair, "as_dict") else {}
                fuzzy_details[fingerprint_string(pair.head, head_root)] = detail
        if paired_new_ids:
            new = [f for f in new if id(f) not in paired_new_ids]
        if paired_resolved_ids:
            resolved = [f for f in resolved if id(f) not in paired_resolved_ids]

    order = lambda f: (  # noqa: E731
        f.file_path or "",
        f.line or 0,
        f.smell_type or "",
        f.symbol or "",
    )
    return {
        NEW: sorted(new, key=order),
        WORSENED: sorted(worsened, key=order),
        UNCHANGED: sorted(unchanged, key=order),
        RESOLVED: sorted(resolved, key=order),
    }
