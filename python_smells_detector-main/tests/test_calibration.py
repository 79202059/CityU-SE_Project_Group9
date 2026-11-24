"""Tests for project-adaptive threshold calibration (PROJECT_OVERVIEW §4.3).

Two properties matter more than the numbers:

1. A calibrated threshold must mean the same thing as a bundled threshold, so
   every metric is measured with the detector's own definition. If the two
   drift apart, calibration silently proposes numbers the detector does not
   interpret the same way.
2. Calibration may tighten a threshold but never loosen the bundled default,
   and never by more than ``max_multiplier`` -- otherwise one 900-line file
   raises the file-length threshold above every file in the project and the
   check stops reporting anything at all.
"""

import ast
import os
import shutil

import pytest

from code_quality_analyzer.calibration import (
    DEFAULT_MAX_MULTIPLIER,
    DEFAULT_PERCENTILE,
    MIN_SAMPLES,
    THRESHOLDS_FILENAME,
    build_parser,
    calibrate,
    collect_metric_values,
    method_length,
    percentile,
    render_calibration_text,
    thresholds_yaml,
    write_thresholds,
)
from code_quality_analyzer.code_smell_detector import CodeSmellDetector
from code_quality_analyzer.config_handler import ConfigHandler
from code_quality_analyzer.main import DEFAULT_CONFIG_NAME, resolve_config_path
from code_quality_analyzer.structural_smell_detector import StructuralSmellDetector

_TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_calibration")


def _handler():
    return ConfigHandler(resolve_config_path(DEFAULT_CONFIG_NAME))


@pytest.fixture()
def workdir():
    if os.path.isdir(_TMP):
        shutil.rmtree(_TMP, ignore_errors=True)
    os.makedirs(_TMP, exist_ok=True)
    yield _TMP
    shutil.rmtree(_TMP, ignore_errors=True)


def _write_project(root, files):
    for name, body in files.items():
        path = os.path.join(root, name)
        os.makedirs(os.path.dirname(path) or root, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
    return root


def _small_project(root):
    files = {}
    for index in range(6):
        files["mod%d.py" % index] = (
            "def f%d(x):\n"
            "    \"\"\"doc.\"\"\"\n"
            "    # a comment\n"
            "    y = x + 1\n"
            "\n"
            "    return y\n" % index
        )
    return _write_project(root, files)


def _long_function(lines=60):
    body = ["def big(x):"] + ["    v%d = x + %d" % (i, i) for i in range(lines - 2)]
    body.append("    return v0")
    return "\n".join(body) + "\n"


def _huge_project(root, count=3, lines=600):
    files = {}
    for index in range(count):
        files["big%d.py" % index] = "\n".join(
            "x%d_%d = %d" % (index, i, i) for i in range(lines)
        ) + "\n"
    return _write_project(root, files)


class TestPercentile:
    def test_linear_interpolation(self):
        values = list(range(1, 11))
        assert percentile(values, 50) == pytest.approx(5.5)
        assert percentile(values, 95) == pytest.approx(9.55)
        assert percentile(values, 0) == pytest.approx(1.0)
        assert percentile(values, 100) == pytest.approx(10.0)

    def test_single_value(self):
        assert percentile([7], 95) == pytest.approx(7.0)

    def test_empty_is_an_error(self):
        with pytest.raises(ValueError):
            percentile([], 95)


class TestMethodLength:
    def test_matches_detect_long_methods(self):
        source = (
            "def f(x):\n"
            "    \"\"\"Docstring.\"\"\"\n"
            "    # comment\n"
            "    y = x + 1\n"
            "\n"
            "    return y\n"
        )
        node = ast.parse(source).body[0]
        assert method_length(node, source.splitlines()) == 3

    def test_docstring_lines_excluded(self):
        source = (
            "def f():\n"
            "    \"\"\"one\n"
            "    two\n"
            "    three\"\"\"\n"
            "    return 1\n"
        )
        node = ast.parse(source).body[0]
        assert method_length(node, source.splitlines()) == 2

    def test_agrees_with_the_detector_on_a_long_function(self, workdir):
        root = _write_project(os.path.join(workdir, "agree"), {"mod.py": _long_function(60)})

        thresholds = _handler().get_thresholds("code_smells")
        thresholds["LONG_METHOD_LINES"] = 10
        code_detector = CodeSmellDetector(thresholds)
        code_detector.detect_smells(os.path.join(root, "mod.py"))
        reported = [smell for smell in code_detector.code_smells
                    if smell.name == "Long Method"]
        assert len(reported) == 1
        detector_lines = int(reported[0].description.split(" has ")[1].split(" lines")[0])

        structural = StructuralSmellDetector(_handler().get_thresholds("structural_smells"))
        structural.analyze_directory(root)
        measured = max(collect_metric_values(structural)["LONG_METHOD_LINES"])

        # Both numbers describe the same function; if they ever disagree,
        # calibration would propose a threshold the detector reads differently.
        assert measured == detector_lines
        assert measured > 45


class TestCalibration:
    def test_small_project_keeps_defaults(self, workdir):
        root = _small_project(os.path.join(workdir, "small"))
        report = calibrate(root, _handler(), min_samples=1)
        for metric in report["metrics"].values():
            assert metric["proposed"] >= metric["default"]
        assert all(not metric["applied"] for metric in report["metrics"].values())

    def test_min_samples_blocks_calibration(self, workdir):
        root = _small_project(os.path.join(workdir, "small2"))
        report = calibrate(root, _handler(), min_samples=MIN_SAMPLES)
        assert all(not metric["applied"] for metric in report["metrics"].values())
        assert "fewer than" in report["metrics"]["MAX_FILE_LENGTH"]["reason"]

    def test_cap_limits_a_single_huge_file(self, workdir):
        root = _huge_project(os.path.join(workdir, "huge"))
        report = calibrate(root, _handler(), min_samples=1)
        entry = report["metrics"]["MAX_FILE_LENGTH"]
        assert entry["applied"] is True
        assert entry["capped"] is True
        assert entry["proposed"] == int(entry["default"] * DEFAULT_MAX_MULTIPLIER)
        assert entry["proposed"] < entry["max"]

    def test_population_counts(self, workdir):
        root = _small_project(os.path.join(workdir, "pop"))
        report = calibrate(root, _handler(), min_samples=1)
        assert report["population"]["files"] == 6
        assert report["population"]["functions"] == 6
        assert report["schema_version"] == 1
        assert report["percentile"] == DEFAULT_PERCENTILE
        assert report["root"] == os.path.abspath(root)

    def test_rejects_bad_arguments(self, workdir):
        root = _small_project(os.path.join(workdir, "bad"))
        with pytest.raises(ValueError):
            calibrate(root, _handler(), percent=0)
        with pytest.raises(ValueError):
            calibrate(root, _handler(), percent=100)
        with pytest.raises(ValueError):
            calibrate(root, _handler(), max_multiplier=0.5)


class TestThresholdFile:
    def test_round_trip_through_config_handler(self, workdir):
        root = _huge_project(os.path.join(workdir, "round"))
        report = calibrate(root, _handler(), min_samples=1)

        target = os.path.join(workdir, "round", THRESHOLDS_FILENAME)
        written = write_thresholds(target, report)
        assert written == sum(1 for m in report["metrics"].values() if m["applied"])

        loaded = ConfigHandler(target).get_thresholds("structural_smells")
        assert loaded["MAX_FILE_LENGTH"] == report["metrics"]["MAX_FILE_LENGTH"]["proposed"]

    def test_file_is_plain_utf8_lf(self, workdir):
        root = _small_project(os.path.join(workdir, "bytes"))
        report = calibrate(root, _handler(), min_samples=1)
        target = os.path.join(workdir, "plain.yaml")
        write_thresholds(target, report)
        raw = open(target, "rb").read()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert b"\r\n" not in raw

    def test_only_applied_keys_are_written(self, workdir):
        root = _small_project(os.path.join(workdir, "only"))
        report = calibrate(root, _handler(), min_samples=1)
        payload = thresholds_yaml(report)
        assert "nothing calibrated" in payload
        assert "LONG_METHOD_LINES" not in payload


class TestRender:
    def test_text_report_mentions_target_and_percentile(self, workdir):
        root = _small_project(os.path.join(workdir, "render"))
        report = calibrate(root, _handler(), min_samples=1)
        text = render_calibration_text(report)
        assert os.path.abspath(root) in text
        assert "p95" in text
        assert "Method length" in text

    def test_parser_defaults(self):
        args = build_parser().parse_args(["proj"])
        assert args.percentile == DEFAULT_PERCENTILE
        assert args.min_samples == MIN_SAMPLES
        assert args.max_multiplier == DEFAULT_MAX_MULTIPLIER
        assert args.format == "text"
