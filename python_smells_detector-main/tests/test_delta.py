"""Tests for the change-aware (pyexamine-delta) core.

The version-provider itself shells out to ``git``, so it is exercised by the
integration path on a developer machine; these tests cover everything that is
pure Python and deterministic.
"""

import os
from importlib import resources

from code_quality_analyzer.config_handler import ConfigHandler
from code_quality_analyzer.delta import analyze_tree
from code_quality_analyzer.finding import CATEGORY_CODE, Finding
from code_quality_analyzer.fingerprint import (
    NEW,
    RESOLVED,
    UNCHANGED,
    classify_lifecycle,
    fingerprint_key,
    relative_path,
)


def _bundled_config() -> ConfigHandler:
    config_path = str(
        resources.files("code_quality_analyzer").joinpath("code_quality_config.yaml")
    )
    return ConfigHandler(config_path)


def _finding(root, smell_type="Long Method", rel="pkg/mod.py", symbol="pkg.mod.f"):
    return Finding(
        category=CATEGORY_CODE,
        smell_type=smell_type,
        file_path=os.path.join(root, rel.replace("/", os.sep)),
        symbol=symbol,
        line=10,
        severity="medium",
        description=f"{smell_type} here",
    )


class TestFinding:
    def test_from_smell_adapts_detector_object(self):
        from code_quality_analyzer.code_smell_detector import CodeSmell

        smell = CodeSmell(
            name="Long Method",
            description="method 'f' is too long",
            file_path="/repo/a.py",
            module_class="a.C",
            line_number=7,
            severity="High",
        )
        finding = Finding.from_smell(smell, CATEGORY_CODE)
        assert finding.smell_type == "Long Method"
        assert finding.symbol == "a.C"
        assert finding.line == 7
        assert finding.severity == "high"
        assert finding.category == "code"

    def test_missing_severity_defaults_to_medium(self):
        from code_quality_analyzer.structural_smell_detector import StructuralSmell

        smell = StructuralSmell(
            name="Large Module",
            description="module is large",
            file_path="/repo/a.py",
            module_class="a",
            line_number=None,
            severity="",
        )
        finding = Finding.from_smell(smell, "structural")
        assert finding.severity == "medium"


class TestFingerprint:
    def test_relative_path_normalizes_separators(self):
        root = os.path.join("C:", "base")
        path = os.path.join(root, "pkg", "mod.py")
        assert relative_path(path, root) == "pkg/mod.py"

    def test_key_is_identical_across_different_roots(self):
        base = _finding("C:/base", rel="pkg/mod.py")
        head = _finding("C:/head", rel="pkg/mod.py")
        assert fingerprint_key(base, "C:/base") == fingerprint_key(head, "C:/head")

    def test_key_ignores_line_number(self):
        first = _finding("C:/base")
        second = Finding(
            category=CATEGORY_CODE,
            smell_type="Long Method",
            file_path=os.path.join("C:/base", "pkg", "mod.py"),
            symbol="pkg.mod.f",
            line=999,
        )
        assert fingerprint_key(first, "C:/base") == fingerprint_key(second, "C:/base")


class TestClassifyLifecycle:
    def test_new_unchanged_resolved(self):
        base = [
            _finding("B", rel="pkg/a.py", symbol="pkg.a.f"),
            _finding("B", rel="pkg/b.py", symbol="pkg.b.g"),
        ]
        head = [
            _finding("H", rel="pkg/a.py", symbol="pkg.a.f"),
            _finding("H", rel="pkg/c.py", symbol="pkg.c.h"),
        ]
        result = classify_lifecycle(base, head, "B", "H")
        assert len(result[NEW]) == 1 and result[NEW][0].symbol == "pkg.c.h"
        assert len(result[UNCHANGED]) == 1 and result[UNCHANGED][0].symbol == "pkg.a.f"
        assert len(result[RESOLVED]) == 1 and result[RESOLVED][0].symbol == "pkg.b.g"

    def test_pure_line_shift_is_unchanged(self):
        base = [_finding("B", rel="pkg/a.py", symbol="pkg.a.f")]
        shifted = [
            Finding(
                category=CATEGORY_CODE,
                smell_type="Long Method",
                file_path=os.path.join("H", "pkg", "a.py"),
                symbol="pkg.a.f",
                line=50,  # line moved but identity is unchanged
            )
        ]
        result = classify_lifecycle(base, shifted, "B", "H")
        assert not result[NEW]
        assert len(result[UNCHANGED]) == 1


class TestAnalyzeTree:
    def test_returns_unified_findings_for_a_small_project(self, tmp_path):
        (tmp_path / "bad.py").write_text(
            "def calc(a, b, c, d, e, f, g):\n"
            "    return a + b + c + d + e + f + g\n"
        )
        handler = _bundled_config()
        findings = analyze_tree(str(tmp_path), handler)
        code_findings = [f for f in findings if f.category == "code"]
        assert code_findings, "expected at least one code smell from bad.py"
        assert all(isinstance(f, Finding) for f in findings)
        # Every finding must carry a symbol and an absolute file path.
        assert all(f.file_path for f in code_findings)
        assert all(f.symbol for f in code_findings)

    def test_ignores_directories(self, tmp_path):
        (tmp_path / "keep.py").write_text(
            "def calc(a, b, c, d, e, f, g):\n"
            "    return a + b + c + d + e + f + g\n"
        )
        ignored = tmp_path / ".venv"
        ignored.mkdir()
        (ignored / "hidden.py").write_text(
            "def calc(a, b, c, d, e, f, g):\n"
            "    return a + b + c + d + e + f + g\n"
        )
        handler = _bundled_config()
        findings = analyze_tree(str(tmp_path), handler, ignore_dirs=[".venv"])
        bad_paths = [f.file_path for f in findings if f.file_path.endswith("hidden.py")]
        assert not bad_paths, ".venv must be ignored"


class TestEndToEndClassification:
    """Classify the real detector output of two separate checkouts."""

    def _smelly(self, name):
        return (
            f"def {name}(a, b, c, d, e, f, g):\n"
            "    return a + b + c + d + e + f + g\n"
        )

    def test_pipeline_marks_new_and_resolved(self, tmp_path):
        base = tmp_path / "base"
        head = tmp_path / "head"
        base.mkdir()
        head.mkdir()

        # Unchanged smell + a smell that is removed in head.
        (base / "kept.py").write_text(self._smelly("kept"))
        (base / "removed.py").write_text(self._smelly("removed"))
        # Unchanged smell + a new smell introduced in head.
        (head / "kept.py").write_text(self._smelly("kept"))
        (head / "added.py").write_text(self._smelly("added"))

        handler = _bundled_config()
        base_findings = analyze_tree(str(base), handler)
        head_findings = analyze_tree(str(head), handler)

        result = classify_lifecycle(
            base_findings, head_findings, str(base), str(head)
        )

        symbols_by_state = {
            state: {f.symbol for f in findings}
            for state, findings in result.items()
        }

        # Code-smell findings carry the bare function name as their symbol
        # (the file path is part of the fingerprint, so this is unambiguous).
        assert "kept" in symbols_by_state[UNCHANGED]
        assert "added" in symbols_by_state[NEW]
        assert "removed" in symbols_by_state[RESOLVED]
        # No finding may be assigned to more than one state.
        assert symbols_by_state[NEW].isdisjoint(symbols_by_state[UNCHANGED])
        assert symbols_by_state[NEW].isdisjoint(symbols_by_state[RESOLVED])

