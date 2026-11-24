"""Tests for the SARIF export layer.

These tests deliberately avoid ``tmp_path``: the whole point of
:mod:`code_quality_analyzer.sarif_builder` is that it is a pure function of
``Finding`` objects plus a root string, so it can be verified without touching
the filesystem.
"""

import json

import pytest

from code_quality_analyzer.finding import (
    CATEGORY_ARCHITECTURAL,
    CATEGORY_CODE,
    CATEGORY_STRUCTURAL,
    Finding,
)
from code_quality_analyzer.rule_registry import (
    RULES,
    RULES_BY_NAME,
    rule_for,
    rule_id_for,
)
from code_quality_analyzer.sarif_builder import (
    FINGERPRINT_KEY,
    LEVEL_POLICIES,
    SRCROOT,
    build_sarif,
    build_sarif_from_report,
    fingerprint,
    relative_uri,
    sarif_level,
)

ROOT = "D:/work/proj"


def _finding(name="Long Method", category=CATEGORY_CODE, path="D:/work/proj/pkg/mod.py",
             symbol="pkg.mod.f", line=12, severity="high", description="method too long"):
    return Finding(
        category=category,
        smell_type=name,
        file_path=path,
        symbol=symbol,
        line=line,
        severity=severity,
        description=description,
    )


class TestRuleRegistry:
    def test_registry_covers_every_detector(self):
        assert len(RULES) == 47
        assert len(RULES_BY_NAME) == 47
        assert len({r.rule_id for r in RULES}) == 47

    def test_categories_are_the_shared_labels(self):
        allowed = {CATEGORY_CODE, CATEGORY_STRUCTURAL, CATEGORY_ARCHITECTURAL}
        assert {r.category for r in RULES} <= allowed

    def test_rule_ids_are_stable_and_prefixed(self):
        assert rule_id_for("Long Method", CATEGORY_CODE) == "pyex-code-long-method"
        assert rule_id_for("Cyclic Dependency", CATEGORY_ARCHITECTURAL).startswith("pyex-arch-")
        # parenthesised abbreviations are used verbatim so NOC and NOCC differ
        assert rule_id_for("High Number of Methods (NOM)", CATEGORY_STRUCTURAL) == "pyex-struct-nom"

    def test_unknown_smell_gets_deterministic_fallback(self):
        first = rule_id_for("Brand New Smell", CATEGORY_CODE)
        second = rule_id_for("Brand New Smell", CATEGORY_CODE)
        assert first == second == "pyex-code-brand-new-smell"
        assert rule_for("Brand New Smell", CATEGORY_CODE).rule_id == first


class TestRelativeUri:
    def test_relativises_inside_root(self):
        assert relative_uri("D:\\work\\proj\\pkg\\mod.py", ROOT) == "pkg/mod.py"

    def test_root_relative_path_is_idempotent(self):
        assert relative_uri("pkg/mod.py", ROOT) == "pkg/mod.py"

    def test_outside_root_keeps_absolute_path(self):
        uri = relative_uri("C:/other/x.py", ROOT)
        assert "other/x.py" in uri
        assert "\\" not in uri

    def test_sibling_prefix_is_not_mistaken_for_a_child(self):
        # D:/work/proj2 must not be relativised against D:/work/proj
        uri = relative_uri("D:/work/proj2/mod.py", ROOT)
        assert uri.endswith("proj2/mod.py")


class TestFingerprint:
    def test_line_drift_keeps_the_same_fingerprint(self):
        a = fingerprint(_finding(line=12), ROOT)
        b = fingerprint(_finding(line=240), ROOT)
        assert a == b

    def test_severity_change_keeps_the_same_fingerprint(self):
        assert fingerprint(_finding(severity="low"), ROOT) == fingerprint(_finding(severity="high"), ROOT)

    def test_symbol_is_part_of_the_identity(self):
        assert fingerprint(_finding(symbol="pkg.mod.f"), ROOT) != fingerprint(_finding(symbol="pkg.mod.g"), ROOT)

    def test_root_prefix_does_not_leak_into_the_identity(self):
        a = _finding(path="D:/work/proj/pkg/mod.py")
        b = _finding(path="/home/ci/proj/pkg/mod.py")
        assert fingerprint(a, ROOT) == fingerprint(b, "/home/ci/proj")

    def test_two_smells_in_one_file_are_distinct(self):
        assert fingerprint(_finding(name="Long Method"), ROOT) != fingerprint(
            _finding(name="Large Class"), ROOT
        )


class TestLevelPolicy:
    def test_policies_are_declared(self):
        assert LEVEL_POLICIES == ("strict", "triage", "advisory")

    @pytest.mark.parametrize(
        "severity,expected",
        [("high", "error"), ("medium", "warning"), ("low", "note")],
    )
    def test_strict_maps_severity_directly(self, severity, expected):
        assert sarif_level(_finding(severity=severity), "strict") == expected

    def test_triage_demotes_structural_high_but_keeps_code_authoritative(self):
        struct = _finding("High Cyclomatic Complexity", CATEGORY_STRUCTURAL, severity="high")
        code = _finding("Duplicate Code", CATEGORY_CODE, severity="high")
        assert sarif_level(struct, "triage") == "warning"
        assert sarif_level(code, "triage") == "error"

    def test_advisory_never_errors(self):
        for category in (CATEGORY_CODE, CATEGORY_STRUCTURAL, CATEGORY_ARCHITECTURAL):
            assert sarif_level(_finding(category=category, severity="high"), "advisory") == "warning"

    def test_unknown_policy_is_rejected(self):
        with pytest.raises(ValueError):
            sarif_level(_finding(), "sloppy")


class TestBuildSarif:
    def test_minimal_document_shape(self):
        doc = build_sarif([_finding()], tool_version="0.3.0", root=ROOT)
        assert doc["version"] == "2.1.0"
        assert doc["$schema"].endswith("sarif-2.1.0.json")
        run = doc["runs"][0]
        assert run["tool"]["driver"]["name"] == "PyExamine"
        assert run["tool"]["driver"]["version"] == "0.3.0"
        assert run["invocations"][0]["executionSuccessful"] is True
        assert len(run["results"]) == 1

    def test_result_carries_fingerprint_location_and_level(self):
        result = build_sarif([_finding()], tool_version="0.3.0", root=ROOT)["runs"][0]["results"][0]
        assert result["ruleId"] == "pyex-code-long-method"
        assert result["level"] == "error"
        loc = result["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"]["uri"] == "pkg/mod.py"
        assert loc["artifactLocation"]["uriBaseId"] == SRCROOT
        assert loc["region"]["startLine"] == 12
        assert result["partialFingerprints"][FINGERPRINT_KEY]

    def test_missing_line_omits_the_region(self):
        result = build_sarif([_finding(line=None)], tool_version="0.3.0", root=ROOT)["runs"][0]["results"][0]
        assert "region" not in result["locations"][0]["physicalLocation"]

    def test_only_used_rules_are_emitted_by_default(self):
        run = build_sarif([_finding()], tool_version="0.3.0", root=ROOT)["runs"][0]
        assert [r["id"] for r in run["tool"]["driver"]["rules"]] == ["pyex-code-long-method"]
        assert run["results"][0]["ruleIndex"] == 0

    def test_all_rules_can_be_emitted(self):
        run = build_sarif(
            [_finding()], tool_version="0.3.0", root=ROOT, include_all_rules=True
        )["runs"][0]
        assert len(run["tool"]["driver"]["rules"]) == 47

    def test_results_are_sorted_deterministically(self):
        findings = [
            _finding(name="Large Class", path="D:/work/proj/b.py", line=5, symbol="b.B"),
            _finding(name="Long Method", path="D:/work/proj/a.py", line=9, symbol="a.f"),
            _finding(name="Long Method", path="D:/work/proj/a.py", line=2, symbol="a.g"),
        ]
        first = build_sarif(findings, tool_version="0.3.0", root=ROOT)
        second = build_sarif(list(reversed(findings)), tool_version="0.3.0", root=ROOT)
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
        uris = [r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] for r in first["runs"][0]["results"]]
        assert uris == sorted(uris)

    def test_no_windows_paths_or_drive_letters_leak(self):
        blob = json.dumps(build_sarif([_finding()], tool_version="0.3.0", root=ROOT), sort_keys=True)
        assert "D:/work" not in blob
        assert "D:\\\\work" not in blob

    def test_metric_value_is_exported_when_present(self):
        f = Finding(CATEGORY_STRUCTURAL, "High Cyclomatic Complexity", "D:/work/proj/a.py",
                    "a.f", 3, "high", "cc 24", metric_value=24.0)
        result = build_sarif([f], tool_version="0.3.0", root=ROOT)["runs"][0]["results"][0]
        assert result["properties"]["metricValue"] == 24.0

    def test_notifications_are_attached_to_the_invocation(self):
        note = {"level": "note", "message": {"text": "3 findings resolved"}}
        run = build_sarif([], tool_version="0.3.0", root=ROOT, notifications=[note])["runs"][0]
        assert run["invocations"][0]["toolExecutionNotifications"] == [note]
        assert run["results"] == []


class TestReportAdapter:
    def test_analyze_report_round_trips_into_sarif(self):
        report = {
            "target": "D:/work/proj",
            "findings": [
                {
                    "type": "code",
                    "name": "Duplicate Code",
                    "description": "duplicate block",
                    "file_path": "D:/work/proj/pkg/mod.py",
                    "module_class": "pkg.mod.f",
                    "line_number": 30,
                    "severity": "high",
                }
            ],
        }
        doc = build_sarif_from_report(report, tool_version="0.3.0")
        result = doc["runs"][0]["results"][0]
        assert result["ruleId"] == "pyex-code-duplicate-code"
        assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "pkg/mod.py"
