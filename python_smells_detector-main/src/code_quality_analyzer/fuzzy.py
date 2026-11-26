"""Fuzzy identity matching for renamed or moved smells (PROJECT_OVERVIEW §4.2).

The exact fingerprint is `(smell_type, relative path, qualified symbol)`.  That
is deliberately strict: it survives line shifts but *not* renaming a method or
moving a file, and in a pull request those two things are common.  Without a
second stage, a pure rename reads as `RESOLVED` + `NEW`, which is exactly the
false positive the gate is supposed to suppress.

This module pairs the leftovers of the exact stage:

    base leftovers (would be RESOLVED)  x  head leftovers (would be NEW)

and accepts a pair only when one-to-one, above a score threshold, and with a
minimum symbol similarity.  Being conservative is the point - a wrong pairing
hides a real regression, a missed pairing only leaves a cosmetic NEW/RESOLVED
pair that a reviewer can see through.

Score (0..1), symbol-dominant because a rename changes the name first:

    score = 0.40 * symbol + 0.25 * path + 0.15 * line + 0.20 * ast

``ast`` is the normalised structural similarity of the two symbols
(``structure.py``).  It is the evidence that lets a rename with a *dissimilar*
name still pair: 0.90 shape similarity is accepted even when the names share
little.  When no signature is available (module-level smells, missing files)
the AST weight is dropped and the previous 0.55 / 0.30 / 0.15 blend is used
unchanged, so behaviour without evidence does not move.

The weights, the 0.62 acceptance threshold, the 0.45 symbol gate and the
"strong shape may excuse a weak name" rule are recorded in ADR-009.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Sequence, Tuple

from .finding import Finding
from .fingerprint import relative_path
from .structure import ast_ratio

DEFAULT_THRESHOLD = 0.62
MIN_SYMBOL_RATIO = 0.45

# A strong shape match may stand in for a weak name, but never for no name at
# all: 0.15 still requires a shared fragment.
AST_GATE = 0.90
MIN_WEAK_SYMBOL = 0.15

W_SYMBOL = 0.40
W_PATH = 0.25
W_LINE = 0.15
W_AST = 0.20
LINE_SCALE = 200.0

# Blend used when no AST signature exists; kept at the ADR-007 values so
# behaviour is identical when the only change is the absence of evidence.
NO_AST_WEIGHTS = {"symbol": 0.55, "path": 0.30, "line": 0.15}

# Transformations recorded in the evidence, so a report can say what happened.
RENAMED = "renamed"
MOVED = "moved"
RENAMED_AND_MOVED = "renamed+moved"


@dataclass(frozen=True)
class FuzzyMatch:
    """One accepted base -> head pairing."""

    base: Finding
    head: Finding
    score: float
    transformation: str
    parts: Dict[str, float]
    base_path: str
    head_path: str

    def as_dict(self) -> dict:
        return {
            "reason": "fuzzy",
            "transformation": self.transformation,
            "score": round(self.score, 4),
            "parts": {k: round(v, 4) for k, v in sorted(self.parts.items())},
            "base": {"path": self.base_path, "symbol": self.base.symbol or ""},
            "head": {"path": self.head_path, "symbol": self.head.symbol or ""},
        }


def _name_of(finding: Finding, path: str) -> str:
    """What a rename actually changes: the symbol, or the file stem."""
    if finding.symbol:
        return finding.symbol
    return os.path.splitext(os.path.basename(path))[0]


def symbol_ratio(base: Finding, head: Finding, base_path: str, head_path: str) -> float:
    """Similarity of the qualified names, with a bonus for a shared tail.

    ``pkg.old_service.fetch`` -> ``pkg.new_service.fetch`` scores high through
    the shared tail even though SequenceMatcher alone would be lukewarm; a
    method body that moved to a differently named class should not match.
    """
    left = _name_of(base, base_path)
    right = _name_of(head, head_path)
    if not left and not right:
        return 1.0
    if left == right:
        return 1.0
    plain = SequenceMatcher(None, left, right).ratio()
    tail = SequenceMatcher(None, left.split(".")[-1], right.split(".")[-1]).ratio()
    return max(plain, 0.5 * plain + 0.5 * tail)


def path_ratio(base_path: str, head_path: str) -> float:
    """Similarity of the containing files, weighting the directory structure."""
    if base_path == head_path:
        return 1.0
    base_name = os.path.basename(base_path)
    head_name = os.path.basename(head_path)
    if base_name == head_name:
        # Same file name in a different package: a move, not a rewrite.
        return 0.85
    base_dir = os.path.dirname(base_path)
    head_dir = os.path.dirname(head_path)
    if base_dir == head_dir:
        # Same directory, different file: a split, only weakly related.
        return 0.6
    return 0.7 * SequenceMatcher(None, base_path, head_path).ratio()


def line_ratio(base: Finding, head: Finding) -> float:
    """Proximity of the two line numbers, saturating at ``LINE_SCALE``."""
    if not base.line or not head.line:
        # No line information is not evidence of distance, but it is not
        # evidence of proximity either: stay neutral.
        return 0.5
    distance = abs(int(head.line) - int(base.line))
    return max(0.0, 1.0 - distance / LINE_SCALE)


def pair_score(
    base: Finding, head: Finding, base_root: str, head_root: str
) -> Tuple[float, Dict[str, float]]:
    """Blend the signals into one 0..1 score plus its parts."""
    base_path = relative_path(base.file_path, base_root)
    head_path = relative_path(head.file_path, head_root)
    parts = {
        "symbol": symbol_ratio(base, head, base_path, head_path),
        "path": path_ratio(base_path, head_path),
        "line": line_ratio(base, head),
    }
    shape = ast_ratio(base, head)
    if shape is None:
        score = sum(NO_AST_WEIGHTS[key] * parts[key] for key in NO_AST_WEIGHTS)
        return score, parts
    parts["ast"] = shape
    score = (
        W_SYMBOL * parts["symbol"]
        + W_PATH * parts["path"]
        + W_LINE * parts["line"]
        + W_AST * shape
    )
    return score, parts


def _passes_name_gate(
    parts: Dict[str, float], min_symbol_ratio: float, min_ast_ratio: float
) -> bool:
    """A similar name is enough; otherwise the shape has to carry the pair."""
    if parts["symbol"] >= min_symbol_ratio:
        return True
    shape: Optional[float] = parts.get("ast")
    return (
        shape is not None
        and shape >= min_ast_ratio
        and parts["symbol"] >= MIN_WEAK_SYMBOL
    )


def _transformation(base_path: str, head_path: str, base: Finding, head: Finding) -> str:
    moved = base_path != head_path
    renamed = (base.symbol or "") != (head.symbol or "")
    if moved and renamed:
        return RENAMED_AND_MOVED
    if moved:
        return MOVED
    return RENAMED


def match(
    base_leftovers: Sequence[Finding],
    head_leftovers: Sequence[Finding],
    base_root: str,
    head_root: str,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    min_symbol_ratio: float = MIN_SYMBOL_RATIO,
    min_ast_ratio: float = AST_GATE,
) -> List[FuzzyMatch]:
    """Pair leftovers one-to-one, best score first.

    Only findings of the same smell type are considered: a renamed method is
    still a Long Method, and pairing a Long Method with a Data Class because
    both moved would be worse than reporting them separately.
    """
    scored: List[FuzzyMatch] = []
    for base in base_leftovers:
        for head in head_leftovers:
            if base.smell_type != head.smell_type:
                continue
            score, parts = pair_score(base, head, base_root, head_root)
            if score < threshold or not _passes_name_gate(
                parts, min_symbol_ratio, min_ast_ratio
            ):
                continue
            base_path = relative_path(base.file_path, base_root)
            head_path = relative_path(head.file_path, head_root)
            scored.append(
                FuzzyMatch(
                    base=base,
                    head=head,
                    score=score,
                    transformation=_transformation(base_path, head_path, base, head),
                    parts=parts,
                    base_path=base_path,
                    head_path=head_path,
                )
            )

    # Deterministic order, and the tie-breakers are on stable fields only so
    # two runs on the same input accept the same pairs (ADR-002).
    scored.sort(
        key=lambda m: (
            -m.score,
            m.head_path,
            m.head.line or 0,
            m.head.symbol or "",
            m.base_path,
        )
    )

    used_base = set()
    used_head = set()
    accepted: List[FuzzyMatch] = []
    for candidate in scored:
        base_id = id(candidate.base)
        head_id = id(candidate.head)
        if base_id in used_base or head_id in used_head:
            continue
        used_base.add(base_id)
        used_head.add(head_id)
        accepted.append(candidate)
    return accepted
