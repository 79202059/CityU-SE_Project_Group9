"""Tests for ``scripts/baseline_b.py`` - the Baseline A/B/Proposed counter.

The script is not part of the installed package, so it is loaded by path.  Only
the pure functions are covered here: the git-dependent part is exercised by
running the script over real commit pairs (see ``docs/evaluation-baselines.md``).
"""

import importlib.util
import os
import unittest

from code_quality_analyzer.finding import CATEGORY_CODE, Finding

_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "baseline_b.py",
)


def _load_module():
    spec = importlib.util.spec_from_file_location("baseline_b_under_test", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


baseline_b = _load_module()

ROOT = os.path.join(os.sep, "repo")
OTHER_ROOT = os.path.join(os.sep, "other")


def _finding(path, line, name="Long Method"):
    return Finding(
        category=CATEGORY_CODE,
        smell_type=name,
        file_path=os.path.join(ROOT, *path.split("/")),
        symbol="pkg.mod.target",
        line=line,
        severity="medium",
        description="synthetic",
        metric_value=50.0,
    )


HUNKS = {"pkg/mod.py": [(10, 20)], "pkg/other.py": [(1, 3), (40, 41)]}


class TestLineIsTouched(unittest.TestCase):
    def test_line_inside_the_range_is_touched(self):
        self.assertTrue(baseline_b.line_is_touched(_finding("pkg/mod.py", 15), HUNKS, ROOT))

    def test_line_on_the_range_edges_is_touched(self):
        self.assertTrue(baseline_b.line_is_touched(_finding("pkg/mod.py", 10), HUNKS, ROOT))
        self.assertTrue(baseline_b.line_is_touched(_finding("pkg/mod.py", 20), HUNKS, ROOT))

    def test_line_outside_every_range_is_not_touched(self):
        self.assertFalse(baseline_b.line_is_touched(_finding("pkg/mod.py", 21), HUNKS, ROOT))
        self.assertFalse(baseline_b.line_is_touched(_finding("pkg/mod.py", 9), HUNKS, ROOT))

    def test_gutter_widens_the_range(self):
        finding = _finding("pkg/mod.py", 23)
        self.assertFalse(baseline_b.line_is_touched(finding, HUNKS, ROOT, gutter=0))
        self.assertTrue(baseline_b.line_is_touched(finding, HUNKS, ROOT, gutter=3))

    def test_second_range_of_the_same_file_counts(self):
        self.assertTrue(baseline_b.line_is_touched(_finding("pkg/other.py", 41), HUNKS, ROOT))

    def test_untouched_file_is_never_touched(self):
        self.assertFalse(baseline_b.line_is_touched(_finding("pkg/gone.py", 15), HUNKS, ROOT))

    def test_module_level_finding_follows_its_file(self):
        self.assertTrue(baseline_b.line_is_touched(_finding("pkg/mod.py", None), HUNKS, ROOT))

    def test_empty_hunks_mean_nothing_is_touched(self):
        self.assertFalse(baseline_b.line_is_touched(_finding("pkg/mod.py", 15), {}, ROOT))

    def test_path_outside_the_root_is_not_touched(self):
        finding = Finding(
            category=CATEGORY_CODE,
            smell_type="Long Method",
            file_path=os.path.join(OTHER_ROOT, "pkg", "mod.py"),
            symbol="pkg.mod.target",
            line=15,
            severity="medium",
            description="synthetic",
            metric_value=50.0,
        )
        self.assertFalse(baseline_b.line_is_touched(finding, HUNKS, ROOT))


class TestFilterByChangedLines(unittest.TestCase):
    def test_keeps_only_changed_line_findings_in_order(self):
        findings = [
            _finding("pkg/mod.py", 12),
            _finding("pkg/mod.py", 99),
            _finding("pkg/other.py", 2),
            _finding("pkg/gone.py", 2),
        ]
        kept = baseline_b.filter_by_changed_lines(findings, HUNKS, ROOT)
        self.assertEqual([f.line for f in kept], [12, 2])

    def test_empty_input_stays_empty(self):
        self.assertEqual(baseline_b.filter_by_changed_lines([], HUNKS, ROOT), [])


class TestSummarise(unittest.TestCase):
    def _row(self, a, b, proposed):
        return {"counts": {"A": a, "B": b, "proposed": proposed}}

    def test_medians_and_reductions(self):
        rows = [self._row(100, 10, 5), self._row(200, 30, 15), self._row(300, 50, 25)]
        summary = baseline_b.summarise(rows)
        self.assertEqual(summary["pairs"], 3)
        self.assertAlmostEqual(summary["median"]["A"], 200.0)
        self.assertAlmostEqual(summary["median"]["B"], 30.0)
        self.assertAlmostEqual(summary["median"]["proposed"], 15.0)
        self.assertAlmostEqual(summary["reduction_b_vs_a"], 0.85)
        self.assertAlmostEqual(summary["reduction_proposed_vs_a"], 0.925)

    def test_zero_baseline_does_not_divide_by_zero(self):
        summary = baseline_b.summarise([self._row(0, 0, 0)])
        self.assertEqual(summary["reduction_b_vs_a"], 0.0)
        self.assertEqual(summary["reduction_proposed_vs_a"], 0.0)

    def test_empty_rows_are_reported_as_zero(self):
        summary = baseline_b.summarise([])
        self.assertEqual(summary["pairs"], 0)
        self.assertEqual(summary["median"]["A"], 0.0)


class TestDataset(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_baseline_b", "dataset.csv"
        )
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def tearDown(self):
        directory = os.path.dirname(self.path)
        if os.path.isfile(self.path):
            os.remove(self.path)
        if os.path.isdir(directory):
            os.rmdir(directory)

    def _write(self, text):
        with open(self.path, "w", newline="\n", encoding="utf-8") as handle:
            handle.write(text)

    def test_comments_and_header_are_skipped(self):
        self._write(
            "# comment line\n"
            "#\n"
            "repo,base,head\n"
            ".,main~1,main\n"
            "other,abc,def\n"
        )
        self.assertEqual(
            baseline_b._dataset_rows(self.path),
            [(".", "main~1", "main"), ("other", "abc", "def")],
        )

    def test_header_after_comments_is_skipped(self):
        self._write("# a\n# b\n# c\nrepo,base,head\n.,aaa,bbb\n")
        self.assertEqual(baseline_b._dataset_rows(self.path), [(".", "aaa", "bbb")])

    def test_short_row_is_rejected(self):
        self._write("repo,base,head\n.,onlytwo\n")
        with self.assertRaises(ValueError):
            baseline_b._dataset_rows(self.path)


class TestRender(unittest.TestCase):
    def _rows(self):
        return [
            {"repo": "a", "base": "b1", "head": "h1", "counts": {"A": 100, "B": 10, "proposed": 8},
             "files_touched": 3, "lifecycle": {}, "gutter": 0, "files_head": 2},
            {"repo": "b", "base": "b2", "head": "h2", "counts": {"A": 300, "B": 30, "proposed": 24},
             "files_touched": 5, "lifecycle": {}, "gutter": 0, "files_head": 4},
        ]

    def test_text_contains_the_three_rows_of_the_metric(self):
        rows = self._rows()
        text = baseline_b.render_text(rows, baseline_b.summarise(rows))
        self.assertIn("A (upstream, unfiltered)", text)
        self.assertIn("B (upstream, changed lines)", text)
        self.assertIn("Proposed (new + worsened)", text)
        self.assertIn("Irrelevant-warning reduction vs A", text)
        self.assertNotIn("a single pair is not a median", text)

    def test_single_pair_is_flagged(self):
        rows = self._rows()[:1]
        text = baseline_b.render_text(rows, baseline_b.summarise(rows))
        self.assertIn("a single pair is not a median", text)

    def test_json_round_trips(self):
        import json

        rows = self._rows()
        payload = json.loads(baseline_b.render_json(rows, baseline_b.summarise(rows)))
        self.assertEqual(payload["summary"]["pairs"], 2)
        self.assertEqual(len(payload["pairs"]), 2)


if __name__ == "__main__":
    unittest.main()
