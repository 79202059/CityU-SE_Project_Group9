"""Baseline A/B/Proposed counts, manifest preflight and CLI error handling."""

import importlib.util
import json
import os
import subprocess
import unittest

import pytest

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
        self.assertIsNone(summary["reduction_b_vs_a"])
        self.assertIsNone(summary["reduction_proposed_vs_a"])

    def test_empty_rows_are_reported_as_zero(self):
        summary = baseline_b.summarise([])
        self.assertEqual(summary["pairs"], 0)
        self.assertEqual(summary["median"]["A"], 0.0)


def test_named_manifest_maps_reordered_columns_and_preserves_pairs(tmp_path, monkeypatch, capsys):
    path = tmp_path / "dataset.csv"
    path.write_bytes((
        '# comment, "unbalanced\r\n\r\npr,HEAD,Repository,notes,base\r\n'
        '7,b,"项目,one","first line\r\n# still inside notes",a\r\n'
        '8,c,two,,b\r\n'
    ).encode("utf-8-sig"))
    seen = []

    def count(repo, base, head, config_handler, **kwargs):
        seen.append((repo, base, head))
        return {"repo": repo, "counts": {"A": 1, "B": 1, "proposed": 1}}

    monkeypatch.setattr(baseline_b, "counts_for_pair", count)
    assert baseline_b.main(["--dataset", str(path), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["pairs"] == 2
    assert seen == [("项目,one", "a", "b"), ("two", "b", "c")]


def test_headerless_preflight_needs_no_repository_or_analysis(tmp_path, monkeypatch, capsys):
    path = tmp_path / "dataset.csv"
    path.write_text("# headerless legacy input\nrepo,abc,HEAD\nrepo,a,b\n", encoding="utf-8")
    monkeypatch.setattr(baseline_b, "ConfigHandler", lambda *_: pytest.fail("loaded detectors' config"))
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("started a subprocess"))
    assert baseline_b.main(["--check-dataset", str(path), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"pairs": 2, "repo_paths": 1}


@pytest.mark.parametrize(("content", "location", "detail"), [
    ("# only comments\nrepo,base,head\n", "", "no commit pairs"),
    ("repo,base,notes\n.,a,n\n", ":1:", "'head'"),
    ("pr,base,head\n7,a,b\n", ":1:", "'repo'"),
    ("base,repo,repository,head\n", ":1:", "'repo'"),
    ("repo,base,head\n.,a\n", ":2:", "expected 3 columns"),
    (".,a\n", ":1:", "rows need repo,base,head"),
    ("repo,base,head\n.,a,b\n,aaa,bbb\n", ":3:", "empty 'repo'"),
    ("repo,base,head\n.,  ,b\n", ":2:", "empty 'base'"),
    ("repo,base,head\n.,a,\n", ":2:", "empty 'head'"),
    ("repo,base,head\n.,a,b\nrepo,base,head\n", ":3:", "repeated header"),
    ('repo,base,head,pr\n.,a,b,"two\nlines"\n.,a,b,2\n', ":4:", "first on line 2"),
    ('repo,base,head\n.,a,"unterminated\n', ":2:", "invalid CSV"),
    ("repo,base,head\n.,a,--stat\n", ":2:", "invalid 'head'"),
    # Python 3.10 rejects NUL in csv.reader; newer versions pass it to field validation.
    ("repo,base,head\n.,a,b\x00c\n", ":2:", "invalid"),
])
def test_manifest_errors_precede_analysis_and_preserve_report(
    tmp_path, monkeypatch, capsys, content, location, detail,
):
    path = tmp_path / "dataset.csv"
    path.write_text(content, encoding="utf-8")
    report = tmp_path / "report.json"
    report.write_bytes(b"previous result")
    monkeypatch.setattr(baseline_b, "counts_for_pair", lambda *a, **kw: pytest.fail("started analysis"))
    for args in (["--check-dataset", str(path)], ["--dataset", str(path), "--output", str(report)]):
        assert baseline_b.main(args) == 2
        out, err = capsys.readouterr()
        assert out == "" and str(path) + location in err and detail in err
    assert report.read_bytes() == b"previous result"


@pytest.mark.parametrize("mode", ["--dataset", "--check-dataset"])
def test_output_cannot_clobber_input_manifest(tmp_path, monkeypatch, capsys, mode):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "data.csv"
    original = b"repo,base,head\n.,a,b\n"
    path.write_bytes(original)
    monkeypatch.setattr(baseline_b, "counts_for_pair", lambda *a, **kw: pytest.fail("started analysis"))
    assert baseline_b.main([mode, str(path), "--output", "./data.csv"]) == 2
    assert "--output" in capsys.readouterr().err
    assert path.read_bytes() == original


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
        self.assertIn("Reduction in findings shown vs A (recall unmeasured)", text)
        self.assertNotIn("Only one pair", text)

    def test_single_pair_is_flagged(self):
        rows = self._rows()[:1]
        text = baseline_b.render_text(rows, baseline_b.summarise(rows))
        self.assertIn("Only one pair", text)

    def test_json_round_trips(self):
        rows = self._rows()
        payload = json.loads(baseline_b.render_json(rows, baseline_b.summarise(rows)))
        self.assertEqual(payload["summary"]["pairs"], 2)
        self.assertEqual(len(payload["pairs"]), 2)


@pytest.mark.parametrize("failure", [
    FileNotFoundError("git executable unavailable"),
    subprocess.TimeoutExpired(["git", "diff"], timeout=1),
    subprocess.CalledProcessError(128, ["git", "diff"], stderr="invalid revision"),
])
def test_failed_diff_aborts_evaluation_and_preserves_output(tmp_path, monkeypatch, capsys, failure):
    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(baseline_b, "resolve_repo_root", lambda _: str(tmp_path))
    monkeypatch.setattr(subprocess, "run", fail)
    report = tmp_path / "report.json"
    report.write_bytes(b"previous run")
    assert baseline_b.main([".", "--base", "base", "--head", "head",
                            "--format", "json", "--output", str(report)]) == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert "base..head" in err and "Could not read git diff" in err
    assert report.read_bytes() == b"previous run"
    assert baseline_b.changed_lines("repo", "base", "head") == {}


def test_missing_dataset_returns_usage_error(tmp_path, capsys):
    assert baseline_b.main(["--dataset", str(tmp_path / "missing.csv")]) == 2
    out, err = capsys.readouterr()
    assert out == "" and "missing.csv" in err


def test_invalid_upstream_archive_preserves_output(tmp_path, capsys):
    archive = tmp_path / "release.zip"
    archive.write_bytes(b"unverified")
    report = tmp_path / "report.json"
    report.write_bytes(b"previous report")
    assert baseline_b.main(["--base", "HEAD", "--upstream-archive", str(archive), "--output", str(report)]) == 2
    assert "SHA-256" in capsys.readouterr().err
    assert report.read_bytes() == b"previous report"


def test_verified_source_runs_in_isolation_with_effective_thresholds(tmp_path, monkeypatch):
    import hashlib
    import zipfile

    archive = tmp_path / "test.zip"
    prefix = f"python_smells_detector-{baseline_b.UPSTREAM_COMMIT}/src/code_quality_analyzer/"
    with zipfile.ZipFile(archive, "w") as snapshot:
        snapshot.writestr(prefix + "__init__.py", "")
        snapshot.writestr(prefix + "main.py", '''
import json
from pathlib import Path

def analyze(directory, config, ignore):
    assert json.loads(Path(config).read_text())["code_smells"]["LIMIT"] == 3
    assert ignore == ["ignored"]
    target = str(Path(directory) / "cart.py")
    finding = {"type": "Code", "name": "Large Class", "file_path": target, "module_class": "Cart",
               "line_number": 4, "severity": "medium", "description": "example"}
    return {"findings": [finding], "errors": [{"file": target, "detector": "test"}]}
''')
    monkeypatch.setattr(baseline_b, "UPSTREAM_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest())
    root = tmp_path / "isolated"
    baseline_b.prepare_upstream(archive, root, {"code_smells": {"LIMIT": 3}})
    findings, errors = baseline_b.upstream_findings(root, str(tmp_path), ["ignored"])
    assert [(f.category, f.smell_type, f.symbol, f.line) for f in findings] == [("code", "Large Class", "Cart", 4)]
    assert errors == [{"file": "cart.py", "detector": "test"}]


def test_detail_export_uses_relative_paths_for_each_member(tmp_path):
    f = Finding(CATEGORY_CODE, "Duplicate Code", f"{tmp_path / 'a, b.py'}, {tmp_path / 'c.py'}",
                "group", line=None)
    assert baseline_b._record(f, str(tmp_path), "RESOLVED") == {
        "rule": "pyex-code-duplicate-code", "path": "a, b.py, c.py", "symbol": "group",
        "line": None, "side": "base", "state": "RESOLVED",
    }


if __name__ == "__main__":
    unittest.main()
