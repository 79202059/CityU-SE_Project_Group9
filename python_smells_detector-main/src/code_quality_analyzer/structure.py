"""Normalised AST signatures used by the fuzzy matching stage (§4.2).

The overview lists "normalised AST signature" as part of the smell identity.
It is *not* part of the exact fingerprint, and that is deliberate: exact
equality on the body would make every WORSENED smell a NEW one, because the
edit that grows a method also changes its body.  ``WORSENED`` is defined as
"same identity, larger metric", so the signature has to enter as *similarity
evidence* in the fuzzy stage, where a partial match is allowed.

The signature is shape, not content:

* node types only - identifiers, constants and operators are erased, so renaming
  a variable or changing a literal keeps the signature identical;
* depth is recorded per node, so moving a block between nesting levels shows up;
* document order is kept, so a reordered body is a *different* shape.

``None`` means "no signature available" (no file on disk, symbol is a module
rather than a function/class, or the file does not parse).  Callers must treat
that as neutral evidence, never as a mismatch.
"""

from __future__ import annotations

import ast
import os
from typing import Dict, Optional, Tuple

from .finding import Finding

# Signature vocabulary: node type plus depth.  Kept as strings so a signature
# can be compared with difflib and printed in evidence.
Token = str

_CACHE: Dict[Tuple[str, int, int], ast.AST] = {}
_CACHE_LIMIT = 256


def _parse(path: str) -> Optional[ast.AST]:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    key = (os.path.abspath(path), stat.st_mtime_ns, stat.st_size)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            source = handle.read()
        tree = ast.parse(source)
    except (OSError, SyntaxError, ValueError):
        return None
    if len(_CACHE) >= _CACHE_LIMIT:
        _CACHE.clear()
    _CACHE[key] = tree
    return tree


_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _descend(tree: ast.AST, parts) -> Optional[ast.AST]:
    current: Optional[ast.AST] = tree
    for part in parts:
        if not isinstance(current, ast.AST):
            return None
        found = None
        for child in ast.iter_child_nodes(current):
            if isinstance(child, _DEFINITIONS) and child.name == part:
                found = child
                break
        if found is None:
            return None
        current = found
    return current if isinstance(current, _DEFINITIONS) else None


def _find_node(tree: ast.AST, symbol: str) -> Optional[ast.AST]:
    """Resolve a finding symbol against a parsed module.

    ``Finding.symbol`` is a *qualified owner name* (``module.Class`` /
    ``module.func``), so the leftmost segments usually name the module or a
    package rather than a definition.  Trying only the full dotted path would
    therefore fail for almost every real finding (measured: 80% of the
    findings on ``flask``), silently disabling the shape component.  Try the
    full path first, then drop leading segments one at a time and take the
    first suffix that resolves.
    """
    parts = [part for part in symbol.replace(",", ".").split(".") if part]
    if not parts:
        return None
    node = _descend(tree, parts)
    if node is not None:
        return node
    for start in range(1, len(parts)):
        node = _descend(tree, parts[start:])
        if node is not None:
            return node
    return None


def _tokens(node: ast.AST) -> Tuple[Token, ...]:
    out: list = []

    def visit(current: ast.AST, depth: int) -> None:
        out.append("%s|%d" % (type(current).__name__, depth))
        for child in ast.iter_child_nodes(current):
            visit(child, depth + 1)

    visit(node, 0)
    return tuple(out)


def symbol_signature(finding: Finding) -> Optional[Tuple[Token, ...]]:
    """Shape signature of the symbol a finding points at."""
    symbol = (finding.symbol or "").strip()
    if not symbol:
        return None
    tree = _parse(finding.file_path)
    if tree is None:
        return None
    node = _find_node(tree, symbol)
    if node is None:
        return None
    return _tokens(node)


def ast_ratio(base: Finding, head: Finding) -> Optional[float]:
    """Similarity of the two symbols' shapes, or ``None`` when unavailable."""
    left = symbol_signature(base)
    right = symbol_signature(head)
    if left is None or right is None:
        return None
    from difflib import SequenceMatcher

    if not left or not right:
        return 1.0 if left == right else 0.0
    return SequenceMatcher(None, left, right).ratio()


def clear_cache() -> None:
    """Drop parsed trees (tests and long-running processes)."""
    _CACHE.clear()
