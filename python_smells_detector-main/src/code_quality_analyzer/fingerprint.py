"""Stable fingerprints and lifecycle classification for findings.

A finding is identified by ``(smell_type, normalized relative path, qualified
symbol)``.  Line numbers are deliberately excluded so that a pure line shift
(inserting blank lines, reordering code) does not turn an unchanged smell into
a spurious ``NEW``.

Lifecycle has four states: ``NEW`` (no counterpart in base), ``WORSENED``
(matched, but the measured metric grew past a tolerance), ``UNCHANGED``
(matched and no worse) and ``RESOLVED`` (present in base only).  The WORSENED
decision is injected as a callback so this module does not need to know about
thresholds or detector wording; see ``metrics.worsen_detail``.

A fifth step exists for renames and moves: when an exact key disappears and
a new one appears, an injected ``fuzzy`` matcher may pair the two leftovers.
That verdict is recorded as ``matched`` evidence and the pair is classified as
UNCHANGED (or WORSENED), because the smell did not appear - its identity moved.
"""

import os
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .finding import Finding

# The key is a tuple so it can be used directly as a dict key; the string
# form is only for humans and stable serialisation.
FingerprintKey = Tuple[str, str, str]

# Lifecycle states.
NEW = "NEW"
WORSENED = "WORSENED"
UNCHANGED = "UNCHANGED"
RESOLVED = "RESOLVED"

# A callback decides whether a matched pair got worse.  It returns the evidence
# dict (recorded in the report) or ``None``.  Keeping it a callback means this
# module stays free of metric/threshold knowledge and the engine can be run
# without the comparison at all.
WorsenJudge = Callable[[Finding, Finding], Optional[dict]]

# A fuzzy matcher pairs the leftovers of the exact stage: base findings that
# would be RESOLVED against head findings that would be NEW.  It returns the
# accepted pairs; the caller decides how to report them.
FuzzyMatcher = Callable[
    [Sequence[Finding], Sequence[Finding], str, str], Sequence[object]
]


def relative_path(file_path: str, tree_root: str) -> str:
    """Return a cross-platform relative path for a file inside a tree.

    Normalisation to ``/`` separators keeps the same file stable across
    base and head checkouts even though they live in different temporary
    directories (and possibly on different drive casings).
    """
    try:
        rel = os.path.relpath(file_path, tree_root)
    except ValueError:
        # Different drive letters on Windows: fall back to the raw path.
        rel = file_path
    return rel.replace(os.sep, "/")


def fingerprint_key(finding: Finding, tree_root: str) -> FingerprintKey:
    """Return the exact-match identity of a finding within its tree."""
    return (
        finding.smell_type,
        relative_path(finding.file_path, tree_root),
        finding.symbol or "",
    )


def fingerprint_string(finding: Finding, tree_root: str) -> str:
    """Human-readable, stable fingerprint string."""
    smell_type, path, symbol = fingerprint_key(finding, tree_root)
    return f"{smell_type}@{path}::{symbol}"


def classify_lifecycle(
    base: Iterable[Finding],
    head: Iterable[Finding],
    base_root: str,
    head_root: str,
    *,
    worsen: Optional[WorsenJudge] = None,
    worsen_details: Optional[Dict[str, dict]] = None,
    fuzzy: Optional[FuzzyMatcher] = None,
    fuzzy_details: Optional[Dict[str, dict]] = None,
) -> Dict[str, List[Finding]]:
    """Split head findings into NEW / WORSENED / UNCHANGED / RESOLVED.

    Args:
        base: Findings from the base version.
        head: Findings from the head version.
        base_root: Root of the base checkout (for relative-path normalisation).
        head_root: Root of the head checkout.
        worsen: Optional judge; a pair that matches the fingerprint is moved
            from ``UNCHANGED`` to ``WORSENED`` when it returns evidence.
        worsen_details: Optional sink filled with ``fingerprint_string ->
            evidence`` for every WORSENED finding, so reports can say *why*.
        fuzzy: Optional matcher for renamed/moved smells (``fuzzy.match``).
        fuzzy_details: Optional sink filled with ``fingerprint_string ->
            evidence`` for every fuzzy-matched pair.

    Returns:
        dict mapping ``NEW`` / ``WORSENED`` / ``UNCHANGED`` / ``RESOLVED`` to
        finding lists.
    """
    base_by_key: Dict[FingerprintKey, Finding] = {}
    for finding in base:
        base_by_key.setdefault(fingerprint_key(finding, base_root), finding)

    head_by_key: Dict[FingerprintKey, Finding] = {}
    for finding in head:
        head_by_key.setdefault(fingerprint_key(finding, head_root), finding)

    result = {NEW: [], WORSENED: [], UNCHANGED: [], RESOLVED: []}
    for key, finding in head_by_key.items():
        previous = base_by_key.get(key)
        if previous is None:
            result[NEW].append(finding)
            continue
        evidence = worsen(previous, finding) if worsen is not None else None
        if evidence is None:
            result[UNCHANGED].append(finding)
            continue
        result[WORSENED].append(finding)
        if worsen_details is not None:
            worsen_details[fingerprint_string(finding, head_root)] = evidence
    base_leftovers = [f for k, f in base_by_key.items() if k not in head_by_key]
    if fuzzy is not None and base_leftovers and result[NEW]:
        paired_head_ids = set()
        paired_base_ids = set()
        for pair in fuzzy(base_leftovers, result[NEW], base_root, head_root):
            paired_base_ids.add(id(pair.base))
            paired_head_ids.add(id(pair.head))
            evidence = worsen(pair.base, pair.head) if worsen is not None else None
            if evidence is None:
                result[UNCHANGED].append(pair.head)
            else:
                result[WORSENED].append(pair.head)
                if worsen_details is not None:
                    worsen_details[fingerprint_string(pair.head, head_root)] = evidence
            if fuzzy_details is not None:
                detail = pair.as_dict() if hasattr(pair, "as_dict") else {}
                fuzzy_details[fingerprint_string(pair.head, head_root)] = detail
        if paired_head_ids:
            result[NEW] = [f for f in result[NEW] if id(f) not in paired_head_ids]
        base_leftovers = [f for f in base_leftovers if id(f) not in paired_base_ids]

    for finding in base_leftovers:
        result[RESOLVED].append(finding)

    for state in (NEW, WORSENED, UNCHANGED, RESOLVED):
        result[state].sort(key=lambda f: (f.file_path, f.line or 0, f.smell_type))
    return result
