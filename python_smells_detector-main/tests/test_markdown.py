"""Markdown PR-summary and quality-budget behaviour (PROJECT_OVERVIEW 4.5)."""

import unittest

from code_quality_analyzer.delta import DEFAULT_MARKDOWN_LIMIT, gate_violations, render_markdown
from code_quality_analyzer.finding import (
    CATEGORY_ARCHITECTURAL,
    CATEGORY_CODE,
    CATEGORY_STRUCTURAL,
    Finding,
)
from code_quality_analyzer.fingerprint import NEW, RESOLVED, UNCHANGED
from code_quality_analyzer.sarif_builder import fingerprint

HEAD_ROOT = "/tree"
BASE_ROOT = "/base"


def _finding(
    smell_type="Long Method",
    category=CATEGORY_CODE,
    file_path="/tree/shop/checkout.py",
    symbol="checkout",
    line=8,
    severity="medium",
):
    return Finding(
        category=category,
        smell_type=smell_type,
        file_path=file_path,
        symbol=symbol,
        line=line,
        severity=severity,
        description="",
        metric_value=None,
    )


def _risks(items, scores, root=HEAD_ROOT):
    from code_quality_analyzer.risk import RiskScore

    result = {}
    for finding, score in zip(items, scores):
        result[fingerprint(finding, root)] = RiskScore(
            score=score,
            exceeds=0.5,
            change=0.5,
            centrality=0.0,
            confidence=0.9,
            measured=True,
            metric_value=50.0,
            threshold=45.0,
            metric_key="LONG_METHOD_LINES",
        )
    return result


class TestMarkdownLayout(unittest.TestCase):
    def _render(self, classified, risks=None, limit=DEFAULT_MARKDOWN_LIMIT):
        return render_markdown(
            classified,
            "main",
            "HEAD",
            BASE_ROOT,
            HEAD_ROOT,
            risks=risks,
            limit=limit,
        )

    def _classified(self, new=None, resolved=None, unchanged=None):
        return {NEW: list(new or []), RESOLVED: list(resolved or []), UNCHANGED: list(unchanged or [])}

    def test_header_and_counts(self):
        text = self._render(self._classified(new=[_finding()], unchanged=[_finding(), _finding()]))
        self.assertIn("**PyExamine Delta** (`main` -> `HEAD`)", text)
        self.assertIn("| NEW | 1 |", text)
        self.assertIn("| RESOLVED | 0 |", text)
        self.assertIn("| UNCHANGED | 2 |", text)

    def test_no_risk_column_without_risk(self):
        text = self._render(self._classified(new=[_finding()]))
        self.assertIn("| category | rule | location | severity |", text)
        self.assertNotIn("| risk |", text)

    def test_risk_column_is_first_and_sorted_desc(self):
        low = _finding(smell_type="Lazy Class", symbol="Cart", line=4)
        high = _finding(smell_type="Long Method", symbol="checkout", line=8)
        risks = _risks([low, high], [12.5, 42.1])
        text = self._render(self._classified(new=[low, high]), risks=risks)
        self.assertIn("| risk | category | rule | location | severity |", text)
        self.assertLess(text.index("42.1"), text.index("12.5"))

    def test_location_renders_line_when_present(self):
        text = self._render(self._classified(new=[_finding(line=8)]))
        self.assertIn("`shop/checkout.py:8`", text)

    def test_location_omits_line_when_absent(self):
        architectural = _finding(
            smell_type="Orphan Module",
            category=CATEGORY_ARCHITECTURAL,
            symbol="shop.checkout",
            line=None,
        )
        text = self._render(self._classified(new=[architectural]))
        self.assertIn("| `shop/checkout.py` |", text)
        self.assertNotIn("shop/checkout.py:None", text)

    def test_truncates_with_a_count(self):
        items = [_finding(symbol="f%d" % i, line=i + 1) for i in range(5)]
        text = self._render(self._classified(new=items), limit=2)
        self.assertIn("_3 more new finding(s) not listed._", text)
        self.assertEqual(text.count("| `shop/checkout.py:"), 2)

    def test_resolved_collapses_into_details(self):
        resolved = _finding(file_path="/base/shop/cart.py", symbol="Cart")
        text = self._render(self._classified(resolved=[resolved]))
        self.assertIn("<details><summary>Resolved (1)</summary>", text)
        self.assertIn("</details>", text)
        self.assertIn("`shop/cart.py:8`", text)

    def test_empty_diff_says_so(self):
        text = self._render(self._classified())
        self.assertIn("_No change in smell findings._", text)

    def test_no_absolute_paths_leak(self):
        text = self._render(
            self._classified(new=[_finding()], resolved=[_finding(file_path="/base/shop/cart.py")])
        )
        self.assertNotIn("/tree", text)
        self.assertNotIn("/base", text)

    def test_deterministic(self):
        first = _finding(line=8)
        second = _finding(smell_type="Lazy Class", symbol="Cart", line=4)
        risks = _risks([first, second], [30.0, 30.0])
        left = self._render(self._classified(new=[first, second]), risks=risks)
        right = self._render(self._classified(new=[second, first]), risks=risks)
        self.assertEqual(left, right)

    def test_pipe_in_cell_is_escaped(self):
        hostile = _finding(smell_type="Odd | Rule")
        text = self._render(self._classified(new=[hostile]))
        self.assertIn("Odd \\| Rule", text)

    def test_risk_cell_carries_the_reasons(self):
        from code_quality_analyzer.risk import RiskScore

        finding = _finding()
        risks = {
            fingerprint(finding, HEAD_ROOT): RiskScore(
                score=55.0,
                exceeds=0.5,
                change=1.0,
                centrality=0.0,
                confidence=0.9,
                measured=True,
                metric_value=77.0,
                threshold=45.0,
                metric_key="LONG_METHOD_LINES",
                reasons=("method length is 77 lines against a threshold of 45 (1.7x)",),
            )
        }
        text = self._render(self._classified(new=[finding]), risks=risks)
        self.assertIn("55.0<br>method length is 77 lines", text)

    def test_structural_category_survives(self):
        structural = _finding(
            smell_type="Deep Nesting", category=CATEGORY_STRUCTURAL, symbol="f", line=3
        )
        text = self._render(self._classified(new=[structural]))
        self.assertIn("| structural | Deep Nesting |", text)


class TestQualityBudget(unittest.TestCase):
    def test_gate_ignores_resolved_and_unchanged(self):
        # gate_violations feeds --fail-on-new; the budget path uses len(NEW).
        classified = {
            NEW: [_finding(severity="low")],
            RESOLVED: [_finding(severity="high")],
            UNCHANGED: [_finding(severity="high")],
        }
        self.assertEqual(gate_violations(classified, "high"), [])
        self.assertEqual(len(gate_violations(classified, "low")), 1)


if __name__ == "__main__":
    unittest.main()
