"""Tests for the baseline store and the new-findings gate.

The baseline is the only file the tool writes into a repository, so its
round-trip behaviour (write -> commit -> compare next PR) is worth pinning
down: a mistake here either hides real regressions or re-reports the whole
backlog on every pull request.
"""

import json
import os
import shutil

import pytest

from code_quality_analyzer.baseline import (
    BASELINE_FILENAME,
    BASELINE_SCHEMA_VERSION,
    baseline_payload,
    diff_against_baseline,
    load_baseline,
    write_baseline,
)
from code_quality_analyzer.delta import gate_violations
from code_quality_analyzer.finding import (
    CATEGORY_CODE,
    Finding,
)
from code_quality_analyzer.fingerprint import NEW, RESOLVED, UNCHANGED
from code_quality_analyzer.sarif_builder import fingerprint

ROOT = "D:/work/proj"
_TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_baseline")


def _finding(name="Long Method", path="D:/work/proj/pkg/mod.py", symbol="pkg.mod.f",
             line=12, severity="high", category=CATEGORY_CODE):
    return Finding(category, name, path, symbol, line, severity, "why")


@pytest.fixture()
def store_dir():
    if os.path.isdir(_TMP):
        shutil.rmtree(_TMP, ignore_errors=True)
    os.makedirs(_TMP, exist_ok=True)
    yield _TMP
    shutil.rmtree(_TMP, ignore_errors=True)


class TestPayload:
    def test_shape_and_counts(self):
        payload = baseline_payload(
            [_finding(), _finding(name="Large Class", symbol="pkg.mod.C")],
            ROOT,
            tool_version="0.3.0",
            ref="HEAD",
        )
        assert payload["schema_version"] == BASELINE_SCHEMA_VERSION
        assert payload["tool"] == {"name": "pyexamine-delta", "version": "0.3.0"}
        assert payload["counts"] == {"total": 2, "by_category": {CATEGORY_CODE: 2}}
        assert payload["ref"] == "HEAD"
        assert len(payload["findings"]) == 2

    def test_paths_are_relative_and_line_is_recorded(self):
        record = baseline_payload([_finding()], ROOT, tool_version="0.3.0")["findings"][0]
        assert record["path"] == "pkg/mod.py"
        assert record["line"] == 12
        assert record["rule_id"] == "pyex-code-long-method"
        assert record["fp"] == fingerprint(_finding(), ROOT)

    def test_records_are_sorted(self):
        payload = baseline_payload(
            [
                _finding(path="D:/work/proj/b.py", line=9, symbol="b.f"),
                _finding(path="D:/work/proj/a.py", line=40, symbol="a.g"),
                _finding(path="D:/work/proj/a.py", line=3, symbol="a.f"),
            ],
            ROOT,
            tool_version="0.3.0",
        )
        assert [(r["path"], r["line"]) for r in payload["findings"]] == [
            ("a.py", 3),
            ("a.py", 40),
            ("b.py", 9),
        ]


class TestRoundTrip:
    def test_write_then_load(self, store_dir):
        path = os.path.join(store_dir, BASELINE_FILENAME)
        payload = baseline_payload([_finding()], ROOT, tool_version="0.3.0")
        write_baseline(path, payload)
        assert os.path.exists(path)
        loaded = load_baseline(path)
        assert loaded["counts"]["total"] == 1
        # LF endings, no BOM: the file has to diff cleanly in git
        raw = open(path, "rb").read()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert b"\r\n" not in raw
        assert json.loads(raw.decode("utf-8"))["findings"][0]["path"] == "pkg/mod.py"

    def test_missing_baseline_is_not_an_error(self, store_dir):
        assert load_baseline(os.path.join(store_dir, "nope.json")) is None

    def test_garbage_baseline_is_rejected(self, store_dir):
        path = os.path.join(store_dir, "bad.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('{"unrelated": true}')
        with pytest.raises(ValueError):
            load_baseline(path)


class TestDiff:
    def _baseline(self, findings):
        return baseline_payload(findings, ROOT, tool_version="0.3.0")

    def test_new_and_resolved_are_separated(self):
        baseline = self._baseline([_finding(symbol="pkg.mod.gone")])
        head = [_finding(symbol="pkg.mod.added")]
        result = diff_against_baseline(baseline, head, ROOT)
        assert [f.symbol for f in result[NEW]] == ["pkg.mod.added"]
        assert [f.symbol for f in result[RESOLVED]] == ["pkg.mod.gone"]
        assert result[UNCHANGED] == []

    def test_same_finding_is_unchanged(self):
        baseline = self._baseline([_finding()])
        result = diff_against_baseline(baseline, [_finding()], ROOT)
        assert len(result[UNCHANGED]) == 1
        assert result[NEW] == []
        assert result[RESOLVED] == []

    def test_line_drift_does_not_manufacture_new_findings(self):
        baseline = self._baseline([_finding(line=12)])
        result = diff_against_baseline(baseline, [_finding(line=180)], ROOT)
        assert result[NEW] == []
        assert len(result[UNCHANGED]) == 1

    def test_severity_change_alone_is_not_a_new_finding(self):
        baseline = self._baseline([_finding(severity="high")])
        result = diff_against_baseline(baseline, [_finding(severity="low")], ROOT)
        assert result[NEW] == []
        assert len(result[UNCHANGED]) == 1

    def test_renamed_file_is_new_and_resolved(self):
        baseline = self._baseline([_finding(path="D:/work/proj/old.py", symbol="old.f")])
        head = [_finding(path="D:/work/proj/new.py", symbol="new.f")]
        result = diff_against_baseline(baseline, head, ROOT)
        assert len(result[NEW]) == 1
        assert len(result[RESOLVED]) == 1

    def test_resolved_findings_are_rehydrated_under_head_root(self):
        baseline = self._baseline([_finding(path="D:/work/proj/pkg/mod.py")])
        result = diff_against_baseline(baseline, [], "/tmp/head")
        resolved = result[RESOLVED][0]
        assert resolved.file_path == os.path.join("/tmp/head", "pkg", "mod.py")
        assert resolved.smell_type == "Long Method"

    def test_empty_baseline_marks_everything_new(self):
        result = diff_against_baseline({"findings": []}, [_finding()], ROOT)
        assert len(result[NEW]) == 1

    def test_diff_is_deterministic(self):
        baseline = self._baseline([_finding(symbol="pkg.mod.a")])
        head = [_finding(symbol="pkg.mod.b"), _finding(symbol="pkg.mod.c")]
        first = diff_against_baseline(baseline, head, ROOT)
        second = diff_against_baseline(baseline, list(reversed(head)), ROOT)
        assert [f.symbol for f in first[NEW]] == [f.symbol for f in second[NEW]]


class TestGate:
    def test_threshold_filters_by_severity(self):
        classified = {
            NEW: [_finding(severity="low", symbol="a"), _finding(severity="high", symbol="b")],
            UNCHANGED: [],
            RESOLVED: [],
        }
        assert len(gate_violations(classified, "low")) == 2
        assert len(gate_violations(classified, "medium")) == 1
        assert [f.symbol for f in gate_violations(classified, "high")] == ["b"]

    def test_unchanged_and_resolved_never_fail_the_gate(self):
        classified = {
            NEW: [],
            UNCHANGED: [_finding(severity="high")],
            RESOLVED: [_finding(severity="high")],
        }
        assert gate_violations(classified, "low") == []

    def test_empty_severity_is_treated_as_medium(self):
        classified = {NEW: [_finding(severity="")], UNCHANGED: [], RESOLVED: []}
        assert len(gate_violations(classified, "medium")) == 1
        assert gate_violations(classified, "high") == []
