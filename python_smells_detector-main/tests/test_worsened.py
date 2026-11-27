"""Tests for the fourth lifecycle state: WORSENED.

A smell that already existed and got measurably worse is neither NEW nor
UNCHANGED, and reviewers treat it differently from both: it is the only state
that proves a pull request actively degraded something.  These tests pin the
two halves of that decision - the metric judge and the plumbing that carries
the verdict into the baseline, the gate and SARIF.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from code_quality_analyzer.baseline import (
    baseline_payload,
    diff_against_baseline,
    finding_from_record,
    load_baseline,
    write_baseline,
)
from code_quality_analyzer.delta import build_parser, gate_violations
from code_quality_analyzer.finding import CATEGORY_CODE, Finding
from code_quality_analyzer.fingerprint import (
    NEW,
    RESOLVED,
    UNCHANGED,
    WORSENED,
    classify_lifecycle,
    fingerprint_string,
)
from code_quality_analyzer.metrics import WORSEN_RELATIVE, worsen_detail
from code_quality_analyzer.sarif_builder import build_sarif, fingerprint

BASE_ROOT = "/base"
HEAD_ROOT = "/tree"
TMP = Path(__file__).resolve().parent / "_tmp_worsened"


def _finding(
    *,
    smell_type: str = "Long Method",
    symbol: str = "checkout",
    line: int = 8,
    severity: str = "high",
    metric_value=None,
    file_path: str = "/tree/shop/checkout.py",
    description: str = "",
    category: str = CATEGORY_CODE,
) -> Finding:
    return Finding(
        category=category,
        smell_type=smell_type,
        file_path=file_path,
        symbol=symbol,
        line=line,
        severity=severity,
        description=description,
        metric_value=metric_value,
    )


def _base_of(finding: Finding) -> Finding:
    """The same smell as it looked on the base tree (different root)."""
    return Finding(
        category=finding.category,
        smell_type=finding.smell_type,
        file_path=finding.file_path.replace(HEAD_ROOT, BASE_ROOT, 1),
        symbol=finding.symbol,
        line=finding.line,
        severity=finding.severity,
        description=finding.description,
        metric_value=finding.metric_value,
    )


class TestMetricTableOwnership(unittest.TestCase):
    def test_risk_and_delta_share_one_table(self):
        # Risk scoring and WORSENED detection must never drift apart: one
        # table, one owner.  A copy in either module would let the same smell
        # be "very serious" for risk and "unchanged" for delta.
        from code_quality_analyzer import metrics, risk

        self.assertIs(risk.METRIC_SPECS, metrics.METRIC_SPECS)
        self.assertEqual(len(metrics.METRIC_SPECS), 28)


class TestWorsenDetail(unittest.TestCase):
    def test_metric_growth_above_twenty_percent_is_worse(self):
        detail = worsen_detail(_base_of(_finding(metric_value=45)), _finding(metric_value=60))
        self.assertIsNotNone(detail)
        self.assertEqual(detail["reason"], "metric")
        self.assertEqual(detail["base"], 45)
        self.assertEqual(detail["head"], 60)
        self.assertEqual(detail["delta"], 15)
        self.assertEqual(detail["metric"], "LONG_METHOD_LINES")

    def test_one_line_growth_is_not_news(self):
        # The increase is well below the frozen contract's 20% threshold.
        self.assertIsNone(
            worsen_detail(_base_of(_finding(metric_value=46)), _finding(metric_value=47))
        )

    def test_exactly_twenty_percent_growth_is_not_worse(self):
        self.assertIsNone(
            worsen_detail(_base_of(_finding(metric_value=50)), _finding(metric_value=60))
        )
        self.assertIsNone(
            worsen_detail(_base_of(_finding(metric_value=9.5)), _finding(metric_value=11.4))
        )

    def test_growth_just_above_twenty_percent_is_worse(self):
        detail = worsen_detail(
            _base_of(_finding(metric_value=50)), _finding(metric_value=61)
        )
        self.assertIsNotNone(detail)
        self.assertEqual(detail["delta"], 11)

    def test_zero_base_metric_has_no_percentage_growth(self):
        self.assertIsNone(
            worsen_detail(_base_of(_finding(metric_value=0)), _finding(metric_value=1))
        )

    def test_negative_base_metric_has_no_percentage_growth(self):
        self.assertIsNone(
            worsen_detail(_base_of(_finding(metric_value=-10)), _finding(metric_value=5))
        )

    def test_flat_metric_is_not_worse(self):
        self.assertIsNone(
            worsen_detail(_base_of(_finding(metric_value=60)), _finding(metric_value=60))
        )

    def test_shrinking_metric_is_not_worse(self):
        self.assertIsNone(
            worsen_detail(_base_of(_finding(metric_value=80)), _finding(metric_value=50))
        )

    def test_relative_threshold_scales_for_large_values(self):
        # 194 -> 232 is just below 20%; 194 -> 233 is above it.
        self.assertIsNone(
            worsen_detail(
                _base_of(_finding(smell_type="LCOM", metric_value=194)),
                _finding(smell_type="LCOM", metric_value=232),
            )
        )
        detail = worsen_detail(
            _base_of(_finding(smell_type="LCOM", metric_value=194)),
            _finding(smell_type="LCOM", metric_value=233),
        )
        self.assertIsNotNone(detail)
        self.assertEqual(detail["delta"], 39)

    def test_severity_fallback_when_no_metric_exists(self):
        detail = worsen_detail(
            _base_of(_finding(smell_type="Dead Code", metric_value=None, severity="low")),
            _finding(smell_type="Dead Code", metric_value=None, severity="high"),
        )
        self.assertIsNotNone(detail)
        self.assertEqual(detail["reason"], "severity")
        self.assertEqual(detail["severity_base"], "low")
        self.assertEqual(detail["severity_head"], "high")

    def test_equal_severity_without_metric_is_not_worse(self):
        self.assertIsNone(
            worsen_detail(
                _base_of(_finding(smell_type="Dead Code", metric_value=None)),
                _finding(smell_type="Dead Code", metric_value=None),
            )
        )

    def test_thresholds_are_overridable(self):
        base = _base_of(_finding(metric_value=10))
        self.assertIsNone(worsen_detail(base, _finding(metric_value=14), relative=0.50))
        self.assertIsNotNone(worsen_detail(base, _finding(metric_value=14), relative=0.30))

    def test_defaults_are_pinned(self):
        self.assertEqual(WORSEN_RELATIVE, 0.20)


class TestClassifyWorsened(unittest.TestCase):
    def test_grown_metric_lands_in_worsened_not_unchanged(self):
        base = [_base_of(_finding(metric_value=45))]
        head = [_finding(metric_value=75)]
        details: dict = {}
        state = classify_lifecycle(
            base, head, BASE_ROOT, HEAD_ROOT, worsen=worsen_detail, worsen_details=details
        )
        self.assertEqual(len(state[WORSENED]), 1)
        self.assertEqual(state[UNCHANGED], [])
        self.assertEqual(state[NEW], [])
        key = fingerprint_string(head[0], HEAD_ROOT)
        self.assertEqual(details[key]["reason"], "metric")

    def test_without_judge_the_old_three_state_behaviour_holds(self):
        base = [_base_of(_finding(metric_value=45))]
        head = [_finding(metric_value=75)]
        state = classify_lifecycle(base, head, BASE_ROOT, HEAD_ROOT)
        self.assertEqual(state.get(WORSENED, []), [])
        self.assertEqual(len(state[UNCHANGED]), 1)

    def test_line_drift_alone_is_still_unchanged(self):
        base = [_base_of(_finding(line=8, metric_value=60))]
        head = [_finding(line=120, metric_value=60)]
        state = classify_lifecycle(
            base, head, BASE_ROOT, HEAD_ROOT, worsen=worsen_detail, worsen_details={}
        )
        self.assertEqual(len(state[UNCHANGED]), 1)
        self.assertEqual(state.get(WORSENED, []), [])

    def test_new_and_resolved_are_unaffected(self):
        state = classify_lifecycle(
            [],
            [_finding()],
            BASE_ROOT,
            HEAD_ROOT,
            worsen=worsen_detail,
            worsen_details={},
        )
        self.assertEqual(len(state[NEW]), 1)
        self.assertEqual(state[RESOLVED], [])


class TestBaselineWorsened(unittest.TestCase):
    def setUp(self):
        if TMP.exists():
            for item in TMP.iterdir():
                item.unlink()
        else:
            TMP.mkdir(parents=True)

    def tearDown(self):
        # Keep the working tree clean: the baseline file is an artefact, not a
        # fixture, and a stale one would show up in `git status` after upload.
        if TMP.exists():
            for item in TMP.iterdir():
                item.unlink()
            TMP.rmdir()

    def test_metric_survives_the_baseline_round_trip(self):
        findings = [_finding(metric_value=45)]
        doc = baseline_payload(findings, HEAD_ROOT, tool_version="test")
        path = str(TMP / "baseline.json")
        write_baseline(path, doc)
        loaded = load_baseline(path)
        self.assertIsNotNone(loaded)
        restored = finding_from_record(loaded["findings"][0], HEAD_ROOT)
        self.assertEqual(restored.metric_value, 45)

    def test_diff_marks_the_grown_smell_as_worsened(self):
        base_doc = baseline_payload([_finding(metric_value=45)], HEAD_ROOT, tool_version="t")
        details: dict = {}
        state = diff_against_baseline(
            base_doc,
            [_finding(metric_value=75)],
            HEAD_ROOT,
            worsen=worsen_detail,
            worsen_details=details,
        )
        self.assertEqual(len(state[WORSENED]), 1)
        self.assertEqual(state[UNCHANGED], [])
        self.assertTrue(details)

    def test_diff_without_judge_stays_three_state(self):
        base_doc = baseline_payload([_finding(metric_value=45)], HEAD_ROOT, tool_version="t")
        state = diff_against_baseline(base_doc, [_finding(metric_value=75)], HEAD_ROOT)
        self.assertEqual(state.get(WORSENED, []), [])
        self.assertEqual(len(state[UNCHANGED]), 1)


class TestSarifBaselineState(unittest.TestCase):
    def test_worsened_maps_to_updated(self):
        finding = _finding(metric_value=75)
        key = fingerprint(finding, HEAD_ROOT)
        doc = build_sarif(
            [finding],
            tool_version="t",
            root=HEAD_ROOT,
            baseline_states={key: "updated"},
        )
        result = doc["runs"][0]["results"][0]
        self.assertEqual(result["baselineState"], "updated")

    def test_no_states_means_no_field(self):
        doc = build_sarif([_finding()], tool_version="t", root=HEAD_ROOT)
        self.assertNotIn("baselineState", doc["runs"][0]["results"][0])


class TestGateAndParser(unittest.TestCase):
    def _classified(self):
        return {
            NEW: [_finding(symbol="fresh")],
            WORSENED: [_finding(severity="high", metric_value=90, symbol="grown")],
            UNCHANGED: [],
            RESOLVED: [],
        }

    def test_gate_ignores_worsened_by_default(self):
        blocking = gate_violations(self._classified(), "high")
        self.assertEqual([f.symbol for f in blocking], ["fresh"])

    def test_gate_counts_worsened_when_asked(self):
        blocking = gate_violations(self._classified(), "high", include_worsened=True)
        self.assertEqual(sorted(f.symbol for f in blocking), ["fresh", "grown"])

    def test_parser_defaults_keep_the_old_contract(self):
        args = build_parser().parse_args([".", "--base", "main"])
        self.assertFalse(args.no_worsen)
        self.assertFalse(args.fail_on_worsened)

    def test_parser_accepts_both_switches(self):
        args = build_parser().parse_args(
            [".", "--base", "main", "--no-worsen", "--fail-on-worsened"]
        )
        self.assertTrue(args.no_worsen)
        self.assertTrue(args.fail_on_worsened)


if __name__ == "__main__":
    unittest.main()
