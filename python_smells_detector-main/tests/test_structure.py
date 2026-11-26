"""Tests for normalised AST signatures and their use in fuzzy matching (§4.2)."""

from __future__ import annotations

import os

import pytest

from code_quality_analyzer.finding import CATEGORY_CODE, Finding
from code_quality_analyzer.fingerprint import UNCHANGED, classify_lifecycle, fingerprint_key
from code_quality_analyzer.fuzzy import match, pair_score, symbol_ratio
from code_quality_analyzer.structure import ast_ratio, clear_cache, symbol_signature

BASE_ROOT = "/base"
HEAD_ROOT = "/head"

LONG_BODY = "\n".join(
    ["    v%d = x + %d" % (i, i) for i in range(55)] + ["    return v0"]
) + "\n"


def _finding(path, symbol, line=1):
    return Finding(
        category=CATEGORY_CODE,
        smell_type="Long Method",
        file_path=str(path),
        symbol=symbol,
        line=line,
        severity="high",
        description="",
    )


def _write(root, name, source):
    path = os.path.join(root, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(source)
    return path


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_cache()
    yield
    clear_cache()


def test_rename_keeps_the_shape(tmp_path):
    base_path = _write(tmp_path / "base", "pkg/core.py", "def compute_total(x):\n" + LONG_BODY)
    head_path = _write(tmp_path / "head", "pkg/core.py", "def tally(x):\n" + LONG_BODY)
    base = _finding(base_path, "compute_total")
    head = _finding(head_path, "tally")

    assert ast_ratio(base, head) == pytest.approx(1.0)
    assert symbol_ratio(base, head, "pkg/core.py", "pkg/core.py") < 0.45


def test_docstring_is_a_small_shape_change(tmp_path):
    base_path = _write(tmp_path / "base", "m.py", "def f(x):\n" + LONG_BODY)
    head_path = _write(
        tmp_path / "head", "m.py", "def f(x):\n    \"\"\"Doc.\"\"\"\n" + LONG_BODY
    )
    ratio = ast_ratio(_finding(base_path, "f"), _finding(head_path, "f"))
    assert ratio is not None
    assert 0.85 <= ratio < 1.0


def test_module_level_symbol_has_no_signature(tmp_path):
    path = _write(tmp_path, "m.py", "def f():\n    return 1\n")
    assert symbol_signature(_finding(path, "pkg.m")) is None


def test_missing_file_has_no_signature(tmp_path):
    assert symbol_signature(_finding(tmp_path / "nope.py", "f")) is None


def test_dissimilar_rename_pairs_on_shape(tmp_path):
    base_path = _write(tmp_path / "base", "pkg/core.py", "def compute_total(x):\n" + LONG_BODY)
    head_path = _write(tmp_path / "head", "pkg/core.py", "def tally(x):\n" + LONG_BODY)
    accepted = match(
        [_finding(base_path, "compute_total")],
        [_finding(head_path, "tally")],
        str(tmp_path / "base"),
        str(tmp_path / "head"),
    )
    assert len(accepted) == 1
    assert accepted[0].transformation == "renamed"
    assert accepted[0].parts["ast"] == pytest.approx(1.0)


def test_different_shape_is_not_paired(tmp_path):
    base_path = _write(tmp_path / "base", "pkg/core.py", "def compute_total(x):\n" + LONG_BODY)
    head_source = "def zz(q):\n" + "".join(
        "    if q == %d:\n        return %d\n" % (i, i) for i in range(5)
    ) + "    return q\n"
    head_path = _write(tmp_path / "head", "pkg/core.py", head_source)
    accepted = match(
        [_finding(base_path, "compute_total")],
        [_finding(head_path, "zz", line=500)],
        str(tmp_path / "base"),
        str(tmp_path / "head"),
    )
    assert accepted == []


def test_no_signature_falls_back_to_the_old_blend(tmp_path):
    base = _finding(tmp_path / "gone.py", "compute_total")
    head = _finding(tmp_path / "gone.py", "compute_total")
    score, parts = pair_score(base, head, str(tmp_path), str(tmp_path))
    assert "ast" not in parts
    assert score == pytest.approx(0.55 * 1.0 + 0.30 * 1.0 + 0.15 * 1.0)


def test_exact_key_ignores_the_body_so_worsened_still_works(tmp_path):
    base_path = _write(tmp_path / "base", "pkg/core.py", "def f(x):\n    return x\n")
    head_path = _write(tmp_path / "head", "pkg/core.py", "def f(x):\n" + LONG_BODY)
    base = _finding(base_path, "f")
    head = _finding(head_path, "f", line=40)
    assert fingerprint_key(base, str(tmp_path / "base")) == fingerprint_key(
        head, str(tmp_path / "head")
    )


def test_lifecycle_says_unchanged_after_a_dissimilar_rename(tmp_path):
    base_path = _write(tmp_path / "base", "pkg/core.py", "def compute_total(x):\n" + LONG_BODY)
    head_path = _write(tmp_path / "head", "pkg/core.py", "def tally(x):\n" + LONG_BODY)
    base = _finding(base_path, "compute_total")
    head = _finding(head_path, "tally")
    classified = classify_lifecycle(
        [base],
        [head],
        str(tmp_path / "base"),
        str(tmp_path / "head"),
        worsen=lambda _a, _b: None,
        fuzzy=match,
    )
    assert classified[UNCHANGED] == [head]


def test_qualified_symbol_resolves_after_stripping_the_module_prefix(tmp_path):
    """``Finding.symbol`` is ``module.Class`` / ``module.func``, not a bare name.

    Resolving only the full dotted path fails for every prefixed finding
    (measured: 80% of them on flask), which silently disabled the shape
    component.  Leading segments naming the module/package must be skipped.
    """
    path = _write(tmp_path, "pkg/core.py", "def compute_total(x):\n" + LONG_BODY)
    assert symbol_signature(_finding(path, "pkg.core.compute_total")) is not None


def test_two_segment_module_symbol_still_has_no_signature(tmp_path):
    path = _write(tmp_path, "m.py", "def f():\n    return 1\n")
    assert symbol_signature(_finding(path, "pkg.m")) is None
