"""Tests for the explainable risk ranking (PROJECT_OVERVIEW §4.4)."""

import math
import os
import unittest

from code_quality_analyzer.finding import (
    CATEGORY_ARCHITECTURAL,
    CATEGORY_CODE,
    CATEGORY_STRUCTURAL,
    Finding,
)
from code_quality_analyzer.metrics import METRIC_SPECS, extract_metric
from code_quality_analyzer.risk import (
    CHANGE_FILE_ONLY,
    CHANGE_MODULE_LEVEL,
    FREQUENCY_PENALTY,
    SEVERITY_FALLBACK,
    W_CENTRALITY,
    W_CHANGE,
    W_CONFIDENCE,
    W_EXCEEDS,
    RiskScore,
    centrality_component,
    change_component,
    changed_lines,
    confidence_component,
    exceeds_component,
    gate_by_risk,
    parse_diff_hunks,
    rank_findings,
    risk_weights,
    score_findings,
)

THRESHOLDS = {
    "code_smells": {"LONG_METHOD_LINES": 45, "LARGE_CLASS_METHODS": 15},
    "structural_smells": {"NOM_THRESHOLD": 10, "LOC_THRESHOLD": 150},
    "architectural_smells": {"GOD_OBJECT_FUNCTIONS": 20},
}


def _finding(**overrides):
    base = dict(
        category=CATEGORY_STRUCTURAL,
        smell_type="High Number of Methods (NOM)",
        file_path="/tree/pkg/a.py",
        symbol="pkg.a.A",
        line=10,
        severity="high",
        description=(
            "Class 'pkg.a.A' has 20 methods (excluding special methods and properties)"
        ),
    )
    base.update(overrides)
    return Finding(**base)


class TestWeights(unittest.TestCase):
    def test_weights_sum_to_one(self):
        weights = risk_weights()
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertAlmostEqual(W_EXCEEDS, 0.35)
        self.assertAlmostEqual(W_CHANGE, 0.25)
        self.assertAlmostEqual(W_CENTRALITY, 0.20)
        self.assertAlmostEqual(W_CONFIDENCE, 0.20)


class TestMetricExtraction(unittest.TestCase):
    def test_long_method_value(self):
        finding = _finding(
            category=CATEGORY_CODE,
            smell_type="Long Method",
            description="'Flask.run' has 50 lines in /tree/pkg/a.py at line 641",
        )
        value, spec = extract_metric(finding)
        self.assertEqual(value, 50.0)
        self.assertEqual(spec.threshold_key, "LONG_METHOD_LINES")

    def test_nom_value(self):
        value, spec = extract_metric(_finding())
        self.assertEqual(value, 20.0)
        self.assertEqual(spec.threshold_key, "NOM_THRESHOLD")

    def test_unknown_rule_has_no_spec(self):
        finding = _finding(smell_type="Middle Man", category="code")
        self.assertIsNone(METRIC_SPECS.get("pyex-code-middle-man"))
        value, spec = extract_metric(finding)
        self.assertIsNone(value)
        self.assertIsNone(spec)

    def test_missing_description_returns_none(self):
        finding = _finding(description="")
        value, _spec = extract_metric(finding)
        self.assertIsNone(value)

    def test_all_specs_target_a_known_rule(self):
        from code_quality_analyzer.rule_registry import RULES_BY_ID

        for rule_id in METRIC_SPECS:
            self.assertIn(rule_id, RULES_BY_ID)


class TestExceeds(unittest.TestCase):
    def test_at_threshold_is_zero(self):
        finding = _finding(
            description="Class 'A' has 10 methods (excluding special methods and properties)"
        )
        component, measured, value, threshold, key = exceeds_component(finding, THRESHOLDS)
        self.assertAlmostEqual(component, 0.0)
        self.assertTrue(measured)
        self.assertEqual((value, threshold, key), (10.0, 10.0, "NOM_THRESHOLD"))

    def test_double_threshold_is_log_scaled(self):
        component, _m, _v, _t, _k = exceeds_component(_finding(), THRESHOLDS)
        self.assertAlmostEqual(component, math.log(2) / math.log(10), places=6)

    def test_ten_times_threshold_saturates(self):
        finding = _finding(
            description="Class 'A' has 100 methods (excluding special methods and properties)"
        )
        component, _m, _v, _t, _k = exceeds_component(finding, THRESHOLDS)
        self.assertAlmostEqual(component, 1.0)

    def test_halfway(self):
        finding = _finding(
            description="Class 'A' has 15 methods (excluding special methods and properties)"
        )
        component, _m, _v, _t, _k = exceeds_component(finding, THRESHOLDS)
        self.assertAlmostEqual(component, math.log(1.5) / math.log(10), places=6)

    def test_below_threshold_clamps_to_zero(self):
        finding = _finding(
            description="Class 'A' has 4 methods (excluding special methods and properties)"
        )
        component, _m, _v, _t, _k = exceeds_component(finding, THRESHOLDS)
        self.assertEqual(component, 0.0)

    def test_missing_threshold_falls_back_to_severity(self):
        finding = _finding(severity="high")
        component, measured, value, threshold, key = exceeds_component(finding, {})
        self.assertFalse(measured)
        self.assertEqual(component, SEVERITY_FALLBACK["high"])
        self.assertEqual(value, 20.0)
        self.assertIsNone(threshold)
        self.assertEqual(key, "NOM_THRESHOLD")

    def test_no_metric_uses_severity_band(self):
        finding = _finding(smell_type="Middle Man", category="code", severity="medium")
        component, measured, _v, _t, _k = exceeds_component(finding, THRESHOLDS)
        self.assertFalse(measured)
        self.assertEqual(component, SEVERITY_FALLBACK["medium"])

    def test_severity_band_never_takes_full_credit(self):
        # A measured ratio must be able to outrank an unmeasured severity band.
        self.assertLess(max(SEVERITY_FALLBACK.values()), 1.0)


class TestConfidence(unittest.TestCase):
    def test_structural_measured_base(self):
        value = confidence_component(_finding(), share=0.0, measured=True)
        self.assertAlmostEqual(value, 0.90)

    def test_ubiquity_penalty(self):
        value = confidence_component(_finding(), share=1.0, measured=True)
        self.assertAlmostEqual(value, 0.90 * (1 - FREQUENCY_PENALTY))

    def test_half_share(self):
        value = confidence_component(_finding(), share=0.5, measured=True)
        self.assertAlmostEqual(value, 0.90 * 0.75)

    def test_heuristic_code_rule_is_lower(self):
        finding = _finding(smell_type="Middle Man", category=CATEGORY_CODE)
        value = confidence_component(finding, share=0.0, measured=False)
        self.assertAlmostEqual(value, 0.60)

    def test_architectural_band(self):
        finding = _finding(category=CATEGORY_ARCHITECTURAL, smell_type="God Object")
        value = confidence_component(finding, share=0.0, measured=False)
        self.assertAlmostEqual(value, 0.75)

    def test_stays_within_bounds(self):
        for share in (0.0, 0.25, 0.5, 1.0, 2.0):
            value = confidence_component(_finding(), share=share, measured=True)
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)


class TestCentrality(unittest.TestCase):
    def test_unknown_module_scores_zero(self):
        self.assertEqual(centrality_component(_finding(), "/tree", {}), 0.0)

    def test_hub_scores_one(self):
        fan_in = {"pkg.a": 40, "pkg.b": 5}
        self.assertAlmostEqual(centrality_component(_finding(), "/tree", fan_in), 1.0)

    def test_log_scaled_middle_value(self):
        fan_in = {"pkg.a": 5, "pkg.b": 40}
        expected = math.log1p(5) / math.log1p(40)
        self.assertAlmostEqual(
            centrality_component(_finding(), "/tree", fan_in), expected
        )

    def test_falls_back_to_file_stem(self):
        finding = _finding(symbol="")
        fan_in = {"pkg.a": 40}
        self.assertAlmostEqual(centrality_component(finding, "/tree", fan_in), 1.0)


class TestDiffParsing(unittest.TestCase):
    def test_hunks_are_parsed(self):
        diff = (
            "diff --git a/pkg/a.py b/pkg/a.py\n"
            "--- a/pkg/a.py\n"
            "+++ b/pkg/a.py\n"
            "@@ -1,0 +3,4 @@\n"
            "+x = 1\n"
            "diff --git a/pkg/b.py b/pkg/b.py\n"
            "--- a/pkg/b.py\n"
            "+++ b/pkg/b.py\n"
            "@@ -10 +12,2 @@\n"
            "+y = 2\n"
        )
        ranges = parse_diff_hunks(diff)
        self.assertEqual(ranges["pkg/a.py"], [(3, 6)])
        self.assertEqual(ranges["pkg/b.py"], [(12, 13)])

    def test_deleted_file_yields_nothing(self):
        diff = "--- a/gone.py\n+++ /dev/null\n@@ -1,0 +0,0 @@\n"
        self.assertEqual(parse_diff_hunks(diff), {})

    def test_missing_git_returns_empty(self):
        # A path that cannot be a git repository on any platform.
        self.assertEqual(changed_lines(os.path.join("no", "such", "repo"), "a", "b"), {})


class TestChange(unittest.TestCase):
    def test_line_inside_hunk(self):
        finding = _finding(line=10)
        self.assertEqual(change_component(finding, "/tree", {"pkg/a.py": [(9, 12)]}), 1.0)

    def test_line_within_gutter(self):
        finding = _finding(line=10)
        self.assertEqual(change_component(finding, "/tree", {"pkg/a.py": [(12, 20)]}), 1.0)

    def test_line_far_from_hunk_scores_file_only(self):
        finding = _finding(line=200)
        self.assertEqual(
            change_component(finding, "/tree", {"pkg/a.py": [(9, 12)]}), CHANGE_FILE_ONLY
        )

    def test_untouched_file_scores_zero(self):
        finding = _finding(line=10)
        self.assertEqual(change_component(finding, "/tree", {"pkg/z.py": [(1, 2)]}), 0.0)

    def test_module_level_finding_on_changed_file(self):
        finding = _finding(line=None, smell_type="Cyclic Dependency", category="architectural")
        self.assertEqual(
            change_component(finding, "/tree", {"pkg/a.py": [(1, 2)]}), CHANGE_MODULE_LEVEL
        )

    def test_module_level_never_beats_line_anchored(self):
        module_level = _finding(
            line=None, smell_type="Orphan Module", category=CATEGORY_ARCHITECTURAL
        )
        line_level = _finding(line=10)
        hunks = {"pkg/a.py": [(9, 12)]}
        self.assertLess(
            change_component(module_level, "/tree", hunks),
            change_component(line_level, "/tree", hunks),
        )


class TestScoring(unittest.TestCase):
    def _fingerprint(self, finding):
        return "%s|%s" % (finding.smell_type, finding.file_path)

    def test_score_is_the_weighted_sum(self):
        finding = _finding()
        scores = score_findings(
            [finding],
            thresholds=THRESHOLDS,
            tree_root="/tree",
            fingerprint_of=self._fingerprint,
        )
        score = scores[self._fingerprint(finding)]
        exceeds = math.log(2) / math.log(10)
        expected = 100 * (
            W_EXCEEDS * exceeds
            + W_CHANGE * 0.0
            + W_CENTRALITY * 0.0
            + W_CONFIDENCE * 0.45
        )
        self.assertAlmostEqual(score.score, expected, places=1)
        self.assertTrue(score.measured)
        self.assertEqual(score.metric_key, "NOM_THRESHOLD")

    def test_components_are_exposed(self):
        finding = _finding()
        scores = score_findings(
            [finding],
            thresholds=THRESHOLDS,
            tree_root="/tree",
            hunks={"pkg/a.py": [(9, 12)]},
            fan_in={"pkg.a": 40},
            fingerprint_of=self._fingerprint,
        )
        payload = scores[self._fingerprint(finding)].as_dict()
        self.assertIn("components", payload)
        self.assertEqual(set(payload["components"]), {"exceeds", "change", "centrality", "confidence"})
        self.assertEqual(payload["components"]["change"], 1.0)
        self.assertEqual(payload["components"]["centrality"], 1.0)

    def test_deterministic_across_runs(self):
        findings = [_finding(), _finding(line=99, symbol="pkg.a.B")]
        first = score_findings(
            findings, thresholds=THRESHOLDS, tree_root="/tree", fingerprint_of=self._fingerprint
        )
        second = score_findings(
            findings, thresholds=THRESHOLDS, tree_root="/tree", fingerprint_of=self._fingerprint
        )
        self.assertEqual(
            {k: v.as_dict() for k, v in first.items()},
            {k: v.as_dict() for k, v in second.items()},
        )

    def test_empty_input(self):
        self.assertEqual(score_findings([], fingerprint_of=self._fingerprint), {})

    def test_rank_orders_by_descending_score(self):
        low = _finding(
            smell_type="Middle Man",
            category="code",
            severity="low",
            description="Method delegates nothing",
            line=500,
        )
        high = _finding()
        scores = score_findings(
            [low, high],
            thresholds=THRESHOLDS,
            tree_root="/tree",
            fingerprint_of=self._fingerprint,
        )
        ranked = rank_findings([low, high], scores, self._fingerprint)
        self.assertIs(ranked[0], high)

    def test_gate_filters_by_min_risk(self):
        kept = _finding(
            description="Class 'A' has 100 methods (excluding special methods and properties)"
        )
        dropped = _finding(
            smell_type="Middle Man",
            category="code",
            severity="low",
            description="Method delegates nothing",
            line=500,
        )
        scores = score_findings(
            [kept, dropped],
            thresholds=THRESHOLDS,
            tree_root="/tree",
            fingerprint_of=self._fingerprint,
        )
        gated = gate_by_risk([kept, dropped], scores, self._fingerprint, 30.0)
        self.assertEqual(gated, [kept])

    def test_score_range(self):
        finding = _finding(
            description="Class 'A' has 400 methods (excluding special methods and properties)"
        )
        scores = score_findings(
            [finding],
            thresholds=THRESHOLDS,
            tree_root="/tree",
            hunks={"pkg/a.py": [(10, 10)]},
            fan_in={"pkg.a": 40},
            fingerprint_of=self._fingerprint,
        )
        score = scores[self._fingerprint(finding)].score
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)


class TestRiskReasons(unittest.TestCase):
    def test_measured_reason_states_value_and_threshold(self):
        finding = _finding()
        scores = score_findings(
            [finding],
            thresholds=THRESHOLDS,
            tree_root="/tree",
            hunks={"pkg/a.py": [(9, 12)]},
            fan_in={"pkg.a": 7},
            fingerprint_of=lambda f: "k",
        )
        score = scores["k"]
        self.assertEqual(score.fan_in_count, 7)
        self.assertIn(
            "class method count is 20 methods against a threshold of 10 (2.0x)",
            score.reasons,
        )
        self.assertIn("the reported line is inside a changed hunk", score.reasons)
        self.assertIn("the enclosing module is imported by 7 other module(s)", score.reasons)
        self.assertTrue(any("detection confidence" in r for r in score.reasons))

    def test_unmeasured_reason_says_so(self):
        finding = _finding(smell_type="Middle Man", category="code", description="")
        scores = score_findings([finding], thresholds=THRESHOLDS, fingerprint_of=lambda f: "k")
        self.assertTrue(
            any("no numeric metric" in reason for reason in scores["k"].reasons)
        )

    def test_reasons_survive_serialisation(self):
        finding = _finding()
        scores = score_findings(
            [finding], thresholds=THRESHOLDS, tree_root="/tree", fingerprint_of=lambda f: "k"
        )
        payload = scores["k"].as_dict()
        self.assertEqual(payload["reasons"], list(scores["k"].reasons))
        self.assertEqual(payload["fan_in"], 0)


class TestRiskScore(unittest.TestCase):
    def test_as_dict_shape(self):
        score = RiskScore(
            score=42.0,
            exceeds=0.5,
            change=1.0,
            centrality=0.25,
            confidence=0.675,
            measured=True,
            metric_value=67.5,
            threshold=45.0,
            metric_key="LONG_METHOD_LINES",
        )
        payload = score.as_dict()
        self.assertEqual(payload["score"], 42.0)
        self.assertEqual(payload["metric"]["key"], "LONG_METHOD_LINES")
        self.assertFalse(payload["measured"] is False)


if __name__ == "__main__":
    unittest.main()
