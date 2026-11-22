"""Stable fingerprints and lifecycle classification for findings.

Sprint 1 implements *exact* matching only.  A finding is identified by
``(smell_type, normalized relative path, qualified symbol)``.  Line numbers
are deliberately excluded so that a pure line shift (inserting blank lines,
reordering code) does not turn an unchanged smell into a spurious ``NEW``.
Fuzzy matching (renames, file moves, AST similarity) is a Sprint 2 concern.
"""

import os
from typing import Dict, Iterable, List, Tuple

from .finding import Finding

# The key is a tuple so it can be used directly as a dict key; the string
# form is only for humans and stable serialisation.
FingerprintKey = Tuple[str, str, str]

# Lifecycle states.
NEW = "NEW"
UNCHANGED = "UNCHANGED"
RESOLVED = "RESOLVED"
# Reserved for Sprint 2 (metric comparison): WORSENED = "WORSENED"


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
) -> Dict[str, List[Finding]]:
    """Split head findings into NEW / UNCHANGED / RESOLVED.

    Args:
        base: Findings from the base version.
        head: Findings from the head version.
        base_root: Root of the base checkout (for relative-path normalisation).
        head_root: Root of the head checkout.

    Returns:
        dict mapping ``NEW`` / ``UNCHANGED`` / ``RESOLVED`` to finding lists.
    """
    base_by_key: Dict[FingerprintKey, Finding] = {}
    for finding in base:
        base_by_key.setdefault(fingerprint_key(finding, base_root), finding)

    head_by_key: Dict[FingerprintKey, Finding] = {}
    for finding in head:
        head_by_key.setdefault(fingerprint_key(finding, head_root), finding)

    result = {NEW: [], UNCHANGED: [], RESOLVED: []}
    for key, finding in head_by_key.items():
        result[NEW if key not in base_by_key else UNCHANGED].append(finding)
    for key, finding in base_by_key.items():
        if key not in head_by_key:
            result[RESOLVED].append(finding)

    for state in (NEW, UNCHANGED, RESOLVED):
        result[state].sort(key=lambda f: (f.file_path, f.line or 0, f.smell_type))
    return result
