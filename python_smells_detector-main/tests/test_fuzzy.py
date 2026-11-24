"""Tests for the fuzzy rename/move stage (PROJECT_OVERVIEW §4.2).

The stage is deliberately conservative, so these tests spend most of their
weight on the rejections: a pairing accepted by mistake hides a real
regression, while a missed pairing only leaves a cosmetic NEW/RESOLVED pair.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.code_quality_analyzer import fuzzy  # noqa: E402
from src.code_quality_analyzer.baseline import (  # noqa: E402
    baseline_payload,
    diff_against_baseline,
)
from src.code_quality_analyzer.finding import Finding  # noqa: E402
from src.code_quality_analyzer.fingerprint import (  # noqa: E402
    NEW,
    RESOLVED,
    UNCHANGED,
    WORSENED,
    classify_lifecycle,
)
from src.code_quality_analyzer.fuzzy import (  # noqa: E402
    DEFAULT_THRESHOLD,
    MIN_SYMBOL_RATIO,
    MOVED,
    RENAMED,
    RENAMED_AND_MOVED,
    match,
    pair_score,
    path_ratio,
    symbol_ratio,
)
from src.code_quality_analyzer.metrics import worsen_detail  # noqa: E402

BASE_ROOT = os.path.join(os.sep, "repo-base")
HEAD_ROOT = os.path.join(os.sep, "repo-head")


def _base(
    smell_type="Long Method",
    path="pkg/service.py",
    symbol="pkg.service.fetch",
    line=10,
    severity="Medium",
    category="code",
    metric=None,
):
    return _finding_on(
        BASE_ROOT, smell_type, path, symbol, line, severity, category, metric
    )


def _head(
    smell_type="Long Method",
    path="pkg/service.py",
    symbol="pkg.service.fetch",
    line=10,
    severity="Medium",
    category="code",
    metric=None,
):
    return _finding_on(
        HEAD_ROOT, smell_type, path, symbol, line, severity, category, metric
    )


def _finding_on(root, smell_type, path, symbol, line, severity, category, metric):
    return Finding(
        category=category,
        smell_type=smell_type,
        file_path=os.path.join(root, path),
        symbol=symbol,
        line=line,
        severity=severity,
        description="%s at line %s" % (smell_type, line),
        metric_value=metric,
    )


class TestSymbolRatio:
    def test_identical_symbols_score_one(self):
        assert symbol_ratio(_base(), _head(), "pkg/a.py", "pkg/a.py") == 1.0

    def test_class_rename_keeps_shared_tail(self):
        ratio = symbol_ratio(
            _base(symbol="pkg.old_service.fetch"),
            _head(symbol="pkg.new_service.fetch"),
            "pkg/a.py",
            "pkg/b.py",
        )
        assert 0.6 < ratio < 1.0

    def test_method_rename_shares_the_class_tail(self):
        ratio = symbol_ratio(
            _base(symbol="pkg.service.fetch"),
            _head(symbol="pkg.service.retrieve"),
            "pkg/a.py",
            "pkg/a.py",
        )
        assert ratio > MIN_SYMBOL_RATIO

    def test_unrelated_names_fall_below_the_gate(self):
        ratio = symbol_ratio(
            _base(symbol="pkg.service.fetch"),
            _head(symbol="pkg.other.zzzzzzzz"),
            "pkg/a.py",
            "pkg/b.py",
        )
        assert ratio < MIN_SYMBOL_RATIO

    def test_missing_symbols_fall_back_to_the_file_stem(self):
        same = symbol_ratio(
            _base(symbol=""), _head(symbol=""), "pkg/orders.py", "pkg/orders.py"
        )
        other = symbol_ratio(
            _base(symbol=""), _head(symbol=""), "pkg/orders.py", "pkg/billing.py"
        )
        assert same == 1.0
        assert other < 1.0


class TestPathRatio:
    def test_same_path_is_one(self):
        assert path_ratio("pkg/a.py", "pkg/a.py") == 1.0

    def test_same_file_name_different_dir_is_a_move(self):
        assert path_ratio("pkg/a.py", "other/a.py") == 0.85

    def test_same_directory_different_file_is_weak(self):
        assert path_ratio("pkg/a.py", "pkg/b.py") == 0.6

    def test_unrelated_paths_use_the_sequence_ratio(self):
        assert 0.0 <= path_ratio("pkg/orders.py", "zzz/billing.py") <= 0.7


class TestLineRatio:
    def test_missing_line_is_neutral(self):
        assert fuzzy.line_ratio(_base(line=None), _head(line=10)) == 0.5

    def test_distance_decays(self):
        ratio = fuzzy.line_ratio(_base(line=10), _head(line=110))
        assert ratio == pytest.approx(0.5)

    def test_far_apart_saturates_at_zero(self):
        assert fuzzy.line_ratio(_base(line=1), _head(line=1000)) == 0.0


class TestPairScore:
    def test_weights_sum_to_one(self):
        assert fuzzy.W_SYMBOL + fuzzy.W_PATH + fuzzy.W_LINE == pytest.approx(1.0)

    def test_identical_findings_score_one(self):
        score, parts = pair_score(_base(), _head(), BASE_ROOT, HEAD_ROOT)
        assert score == pytest.approx(1.0)
        assert parts == {"symbol": 1.0, "path": 1.0, "line": 1.0}

    def test_score_stays_inside_zero_and_one(self):
        base = _base(symbol="pkg.a.x", path="pkg/a.py", line=1)
        head = _head(symbol="zzz.q.y", path="other/b.py", line=900)
        score, _parts = pair_score(base, head, BASE_ROOT, HEAD_ROOT)
        assert 0.0 <= score <= 1.0


class TestMatch:
    def test_accepts_a_rename(self):
        base = _base(symbol="pkg.service.fetch_old")
        head = _head(symbol="pkg.service.fetch_new")
        pairs = match([base], [head], BASE_ROOT, HEAD_ROOT)
        assert len(pairs) == 1
        assert pairs[0].transformation == RENAMED
        assert pairs[0].base is base and pairs[0].head is head

    def test_accepts_a_move(self):
        pairs = match(
            [_base(path="pkg/service.py")],
            [_head(path="other/service.py")],
            BASE_ROOT,
            HEAD_ROOT,
        )
        assert len(pairs) == 1
        assert pairs[0].transformation == MOVED

    def test_accepts_a_rename_and_a_move(self):
        pairs = match(
            [_base(path="pkg/service.py", symbol="pkg.service.fetch_old")],
            [_head(path="other/service.py", symbol="pkg.service.fetch_new")],
            BASE_ROOT,
            HEAD_ROOT,
        )
        assert len(pairs) == 1
        assert pairs[0].transformation == RENAMED_AND_MOVED

    def test_exact_pairs_never_reach_the_fuzzy_stage(self):
        # The matcher only ever sees leftovers, so the exact stage owns this
        # pair and classifies it without any fuzzy evidence.
        details = {}
        classified = classify_lifecycle(
            [_base()],
            [_head(symbol="pkg.service.fetch", path="pkg/service.py")],
            BASE_ROOT,
            HEAD_ROOT,
            fuzzy=match,
            fuzzy_details=details,
        )
        assert len(classified[UNCHANGED]) == 1
        assert classified[NEW] == []
        assert details == {}

    def test_different_smell_types_never_pair(self):
        pairs = match(
            [_base(smell_type="Long Method")],
            [_head(smell_type="Large Class")],
            BASE_ROOT,
            HEAD_ROOT,
        )
        assert pairs == []

    def test_symbol_gate_rejects_unrelated_names(self):
        pairs = match(
            [_base(symbol="pkg.service.fetch")],
            [_head(symbol="pkg.other.zzzzzzzz")],
            BASE_ROOT,
            HEAD_ROOT,
        )
        assert pairs == []

    def test_threshold_is_configurable(self):
        base = _base(symbol="pkg.old_service.fetch")
        head = _head(symbol="pkg.new_service.fetch")
        assert len(match([base], [head], BASE_ROOT, HEAD_ROOT, threshold=0.1)) == 1
        assert match([base], [head], BASE_ROOT, HEAD_ROOT, threshold=0.99) == []

    def test_pairs_are_one_to_one(self):
        base1 = _base(path="pkg/a.py", symbol="pkg.a.fetch", line=10)
        base2 = _base(path="pkg/a.py", symbol="pkg.a.fetch2", line=12)
        head = _head(path="pkg/a.py", symbol="pkg.a.fetch_new", line=10)
        pairs = match([base1, base2], [head], BASE_ROOT, HEAD_ROOT)
        assert len(pairs) == 1

    def test_ordering_is_deterministic(self):
        base1 = _base(path="pkg/a.py", symbol="pkg.a.fetch", line=5)
        base2 = _base(path="pkg/a.py", symbol="pkg.a.store", line=40)
        head1 = _head(path="pkg/a.py", symbol="pkg.a.fetch_new", line=5)
        head2 = _head(path="pkg/a.py", symbol="pkg.a.store_new", line=40)
        first = match([base1, base2], [head1, head2], BASE_ROOT, HEAD_ROOT)
        second = match([base2, base1], [head2, head1], BASE_ROOT, HEAD_ROOT)
        assert [m.head.symbol for m in first] == [m.head.symbol for m in second]

    def test_evidence_shape(self):
        pairs = match(
            [_base(symbol="pkg.service.fetch_old")],
            [_head(symbol="pkg.service.fetch_new")],
            BASE_ROOT,
            HEAD_ROOT,
        )
        evidence = pairs[0].as_dict()
        assert evidence["reason"] == "fuzzy"
        assert set(evidence) == {
            "reason",
            "transformation",
            "score",
            "parts",
            "base",
            "head",
        }
        assert evidence["base"]["symbol"] == "pkg.service.fetch_old"
        assert evidence["head"]["path"] == "pkg/service.py"


class TestClassifyIntegration:
    def test_rename_moves_from_new_to_unchanged(self):
        details = {}
        classified = classify_lifecycle(
            [_base(symbol="pkg.service.fetch_old")],
            [_head(symbol="pkg.service.fetch_new")],
            BASE_ROOT,
            HEAD_ROOT,
            fuzzy=match,
            fuzzy_details=details,
        )
        assert classified[NEW] == []
        assert len(classified[UNCHANGED]) == 1
        assert details

    def test_without_the_matcher_a_rename_reads_as_resolved_plus_new(self):
        head = _head(symbol="pkg.service.fetch_new")
        classified = classify_lifecycle(
            [_base(symbol="pkg.service.fetch_old")], [head], BASE_ROOT, HEAD_ROOT
        )
        assert classified[NEW] == [head]
        assert len(classified[RESOLVED]) == 1

    def test_a_renamed_regression_is_still_worsened(self):
        details = {}
        classified = classify_lifecycle(
            [_base(symbol="pkg.service.fetch_old", metric=45.0)],
            [_head(symbol="pkg.service.fetch_new", metric=80.0)],
            BASE_ROOT,
            HEAD_ROOT,
            worsen=worsen_detail,
            worsen_details={},
            fuzzy=match,
            fuzzy_details=details,
        )
        assert classified[NEW] == []
        assert len(classified[WORSENED]) == 1


class TestBaselineIntegration:
    def test_rename_against_a_baseline_is_unchanged(self):
        payload = baseline_payload(
            [_base(symbol="pkg.service.fetch_old")], BASE_ROOT, tool_version="test"
        )
        details = {}
        classified = diff_against_baseline(
            payload,
            [_head(symbol="pkg.service.fetch_new")],
            HEAD_ROOT,
            fuzzy=match,
            fuzzy_details=details,
        )
        assert classified[NEW] == []
        assert len(classified[UNCHANGED]) == 1

    def test_baseline_without_the_matcher_reports_a_new_finding(self):
        payload = baseline_payload(
            [_base(symbol="pkg.service.fetch_old")], BASE_ROOT, tool_version="test"
        )
        head = _head(symbol="pkg.service.fetch_new")
        classified = diff_against_baseline(payload, [head], HEAD_ROOT)
        assert classified[NEW] == [head]
        assert len(classified[RESOLVED]) == 1


class TestDefaults:
    def test_threshold_defaults(self):
        assert DEFAULT_THRESHOLD == pytest.approx(0.62)
        assert MIN_SYMBOL_RATIO == pytest.approx(0.45)
