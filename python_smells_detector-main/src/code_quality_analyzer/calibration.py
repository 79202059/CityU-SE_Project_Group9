"""Project-adaptive thresholds (PROJECT_OVERVIEW §4.3).

The bundled ``code_quality_config.yaml`` ships one set of thresholds for every
project: 45 lines is a long method, 10 is a complex one, 15 dependencies is a
fan-out problem. Those numbers are opinions, and a project whose median method
is already 40 lines gets a report where almost every method is a "long method".

``calibrate`` measures the project's own distribution for a handful of metrics
and proposes ``effective = max(bundled_default, project_percentile)``. The
default acts as a floor on purpose: calibration may tighten a threshold, never
loosen it below what the tool ships with, so a project cannot calibrate itself
into ignoring the smells it was written with.

Every metric is measured with the same code the detectors use, so a threshold
proposed here means the same thing a threshold in the config file means:

* method length -- non-blank, non-comment lines outside the method's own
  docstring, skipping ``@property`` (``CodeSmellDetector.detect_long_methods``)
* class method count -- ``len(class_info[...]["methods"])`` (``detect_nom``)
* cyclomatic complexity -- ``StructuralSmellDetector.calculate_cyclomatic_complexity``
* module fan-out -- non-stdlib successors of the module in the dependency graph
  (``detect_fanout``)
* file length -- code + import lines (``detect_file_length``)
* module LOC -- code lines (``detect_loc``)
"""

import ast
import json
import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from .config_handler import ConfigHandler
from .project import STDLIB_MODULES, project_root
from .structural_smell_detector import StructuralSmellDetector

logger = logging.getLogger(__name__)

CALIBRATION_SCHEMA_VERSION = 1
THRESHOLDS_FILENAME = "pyexamine-thresholds.yaml"
DEFAULT_PERCENTILE = 95
MIN_SAMPLES = 20
DEFAULT_MAX_MULTIPLIER = 2.0


@dataclass(frozen=True)
class Metric:
    """One calibratable threshold."""

    section: str
    key: str
    label: str
    unit: str
    definition: str


METRICS: Sequence[Metric] = (
    Metric(
        "code_smells",
        "LONG_METHOD_LINES",
        "Method length",
        "lines",
        "non-blank, non-comment, non-docstring lines per function",
    ),
    Metric(
        "code_smells",
        "LARGE_CLASS_METHODS",
        "Class method count (non-trivial)",
        "methods",
        "non-dunder methods with more than a single return/assign, as detect_large_classes counts them",
    ),
    Metric(
        "structural_smells",
        "NOM_THRESHOLD",
        "Class method count (all)",
        "methods",
        "methods declared directly in a class body",
    ),
    Metric(
        "structural_smells",
        "CYCLOMATIC_COMPLEXITY_THRESHOLD",
        "Cyclomatic complexity",
        "points",
        "McCabe complexity of non-dunder functions",
    ),
    Metric(
        "structural_smells",
        "MAX_FANOUT",
        "Module fan-out",
        "modules",
        "non-stdlib modules a module imports",
    ),
    Metric(
        "structural_smells",
        "MAX_FILE_LENGTH",
        "File length",
        "lines",
        "code + import lines per file",
    ),
    Metric(
        "structural_smells",
        "LOC_THRESHOLD",
        "Module LOC",
        "lines",
        "code lines (comments, docstrings, imports and blanks excluded)",
    ),
)

_METRICS_BY_KEY = {metric.key: metric for metric in METRICS}


# --------------------------------------------------------------------------- #
# measurement
# --------------------------------------------------------------------------- #

def _is_property(node) -> bool:
    """True for ``@property`` / ``@x.setter`` style decorators."""
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id == "property":
            return True
        if isinstance(target, ast.Attribute) and target.attr in ("setter", "getter", "deleter"):
            return True
    return False


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _docstring_lines(node) -> range:
    """Line numbers of the function's own docstring, empty when it has none."""
    if not node.body:
        return range(0)
    first = node.body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return range(first.lineno, (first.end_lineno or first.lineno) + 1)
    return range(0)


def method_length(node, lines: List[str]) -> int:
    """Line count of ``node`` using ``detect_long_methods``' definition."""
    doc_lines = _docstring_lines(node)
    total = 0
    last = min(node.end_lineno or node.lineno, len(lines))
    for number in range(node.lineno, last + 1):
        line = lines[number - 1].strip()
        if line and not line.startswith("#") and number not in doc_lines:
            total += 1
    return total


# The Large Class detector skips exception hierarchies outright (its own
# ``_is_exception_class`` rule).  Mirroring that here keeps the measured
# population equal to the population the threshold is applied to.
_EXCEPTION_SUFFIXES = ("Exception", "Error")


def _is_exception_hierarchy(bases) -> bool:
    for base in bases:
        name = str(base).rsplit(".", 1)[-1]
        if name.endswith(_EXCEPTION_SUFFIXES):
            return True
    return False


def non_trivial_method_count(methods) -> int:
    """How ``detect_large_classes`` counts methods for one class."""
    count = 0
    for method in methods:
        if _is_dunder(method.name):
            continue
        if len(method.body) == 1 and isinstance(method.body[0], (ast.Return, ast.Assign)):
            continue
        count += 1
    return count


def collect_metric_values(detector: StructuralSmellDetector) -> Dict[str, List[float]]:
    """Raw metric values for every object the detectors would inspect.

    ``detector.analyze_directory()`` must have run first: this reads the same
    parsed state the detection methods read.
    """
    values: Dict[str, List[float]] = {metric.key: [] for metric in METRICS}

    def visit_function(node, lines, doc_aware):
        if _is_dunder(node.name):
            return
        if doc_aware and _is_property(node):
            return
        values["LONG_METHOD_LINES"].append(method_length(node, lines))
        values["CYCLOMATIC_COMPLEXITY_THRESHOLD"].append(
            detector.calculate_cyclomatic_complexity(node)
        )

    for module_name, info in detector.module_info.items():
        lines = info["lines"]
        code_lines, _, import_lines, _ = detector._line_counts(info)
        values["LOC_THRESHOLD"].append(code_lines)
        values["MAX_FILE_LENGTH"].append(code_lines + import_lines)
        for node in info["functions"]:
            visit_function(node, lines, doc_aware=True)

    for class_name, info in detector.class_info.items():
        methods = info["methods"]
        if methods:
            values["NOM_THRESHOLD"].append(len(methods))
            if not _is_exception_hierarchy(info.get("base_classes", ())):
                values["LARGE_CLASS_METHODS"].append(non_trivial_method_count(methods))
        module = class_name.rsplit(".", 1)[0]
        lines = detector.module_info.get(module, {}).get("lines", [])
        for node in methods:
            visit_function(node, lines, doc_aware=True)

    for module in detector.module_info:
        if module.rsplit(".", 1)[-1].startswith("test"):
            continue
        significant = sum(
            1
            for successor in detector.dependency_graph.successors(module)
            if successor.split(".")[0] not in STDLIB_MODULES
        )
        values["MAX_FANOUT"].append(significant)

    return values


# --------------------------------------------------------------------------- #
# statistics
# --------------------------------------------------------------------------- #

def percentile(values: Sequence[float], percent: float) -> float:
    """Linear-interpolated percentile (the numpy default)."""
    if not values:
        raise ValueError("cannot take a percentile of no values")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100.0
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(ordered[int(position)])
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _summary(values: List[float], percent: float) -> dict:
    return {
        "n": len(values),
        "min": min(values),
        "median": percentile(values, 50),
        "p75": percentile(values, 75),
        "p90": percentile(values, 90),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "max": max(values),
        "project": percentile(values, percent),
    }


def calibrate(
    directory: str,
    config_handler: ConfigHandler,
    *,
    percent: float = DEFAULT_PERCENTILE,
    ignore_dirs: Optional[Sequence[str]] = None,
    min_samples: int = MIN_SAMPLES,
    max_multiplier: float = DEFAULT_MAX_MULTIPLIER,
    tool_version: str = "unknown",
) -> dict:
    """Measure the project and propose one threshold per metric."""
    if not 0 < percent < 100:
        raise ValueError("percentile must be between 0 and 100 (exclusive), got %r" % (percent,))
    if max_multiplier < 1:
        raise ValueError("max-multiplier must be at least 1, got %r" % (max_multiplier,))

    target = os.path.abspath(directory)
    detector = StructuralSmellDetector(config_handler.get_thresholds("structural_smells"))
    detector.analyze_directory(target, ignore_dirs=ignore_dirs)

    values = collect_metric_values(detector)
    defaults = {
        **config_handler.get_thresholds("code_smells"),
        **config_handler.get_thresholds("structural_smells"),
    }

    metrics: Dict[str, dict] = {}
    for metric in METRICS:
        observed = values.get(metric.key, [])
        if not observed:
            metrics[metric.key] = {
                "section": metric.section,
                "label": metric.label,
                "unit": metric.unit,
                "definition": metric.definition,
                "n": 0,
                "default": defaults.get(metric.key),
                "proposed": defaults.get(metric.key),
                "applied": False,
                "reason": "no objects to measure",
            }
            continue

        stats = _summary(observed, percent)
        default = defaults.get(metric.key)
        rounded = int(math.ceil(stats["project"]))
        floor = None if default is None else int(default)
        cap = None if floor is None else int(math.ceil(floor * max_multiplier))
        raw = rounded if floor is None else max(floor, rounded)
        proposed = raw if cap is None else min(raw, cap)
        capped = proposed < raw

        if len(observed) < min_samples:
            reason = "fewer than %d samples (%d)" % (min_samples, len(observed))
            applied = False
        elif floor is not None and proposed <= floor:
            reason = "project p%g = %d does not exceed the bundled default %d" % (
                percent,
                rounded,
                floor,
            )
            applied = False
        else:
            reason = "project p%g = %d exceeds the bundled default %d" % (
                percent,
                rounded,
                floor,
            )
            if capped:
                reason += "; capped at %d (%gx the default)" % (proposed, max_multiplier)
            applied = True

        metrics[metric.key] = {
            "section": metric.section,
            "label": metric.label,
            "unit": metric.unit,
            "definition": metric.definition,
            "default": default,
            "cap": cap,
            "proposed": proposed,
            "capped": capped,
            "applied": applied,
            "reason": reason,
            **stats,
        }

    return {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "tool": {"name": "PyExamine", "version": tool_version},
        "target": target,
        "root": project_root(target),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "percentile": percent,
        "min_samples": min_samples,
        "max_multiplier": max_multiplier,
        "population": {
            "files": len(detector.module_info),
            "modules": len(detector.module_info),
            "classes": len(detector.class_info),
            "functions": len(values["LONG_METHOD_LINES"]),
            "analysis_errors": len(detector.errors),
        },
        "metrics": metrics,
    }


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #

def render_calibration_text(report: dict) -> str:
    """Human-readable table of the measured distributions."""
    population = report["population"]
    lines = [
        "PyExamine threshold calibration",
        "  target          %s" % report["target"],
        "  percentile      p%g" % report["percentile"],
        "  files           %d" % population["files"],
        "  functions       %d" % population["functions"],
        "  classes         %d" % population["classes"],
        "",
        "%-30s %6s %8s %8s %8s %8s %9s %9s" % (
            "metric", "n", "median", "p75", "p90", "max", "default", "proposed",
        ),
    ]
    for metric in METRICS:
        entry = report["metrics"][metric.key]
        if not entry.get("n"):
            lines.append("%-30s %6s %8s %8s %8s %8s %9s %9s  (no data)" % (
                metric.label[:30], "-", "-", "-", "-", "-",
                entry.get("default", "-"), "-",
            ))
            continue
        marker = "*" if entry["applied"] else " "
        if entry.get("capped"):
            marker = "^"
        lines.append("%-30s %6d %8.1f %8.1f %8.1f %8.1f %9s %9s %s" % (
            metric.label[:30],
            entry["n"],
            entry["median"],
            entry["p75"],
            entry["p90"],
            entry["max"],
            entry["default"],
            entry["proposed"],
            marker,
        ))
    lines.append("")
    lines.append("* = written to the threshold file (the others stay at the bundled default)")
    lines.append("^ = written, but capped at %gx the default" % report["max_multiplier"])
    changed = [m for m in METRICS if report["metrics"][m.key]["applied"]]
    if not changed:
        lines.append("")
        lines.append(
            "No threshold was raised: this project is already inside the bundled defaults."
        )
    return "\n".join(lines)


def thresholds_yaml(report: dict) -> str:
    """A config overlay containing only the applied thresholds."""
    sections: Dict[str, List[Metric]] = {}
    for metric in METRICS:
        if report["metrics"][metric.key]["applied"]:
            sections.setdefault(metric.section, []).append(metric)

    lines = [
        "# Generated by `pyexamine-delta calibrate` -- pass it with --config.",
        "# Only thresholds raised above the bundled defaults appear here.",
        "# target: %s" % report["target"],
        "# percentile: p%g   generated_at: %s" % (
            report["percentile"], report["generated_at"],
        ),
    ]
    if not sections:
        lines.append("# (nothing calibrated)")
        return "\n".join(lines) + "\n"

    for section in ("code_smells", "structural_smells", "architectural_smells"):
        if section not in sections:
            continue
        lines.append("%s:" % section)
        for metric in sections[section]:
            entry = report["metrics"][metric.key]
            lines.append("  %s:" % metric.key)
            lines.append("    value: %d" % entry["proposed"])
            lines.append(
                '    explanation: "calibrated: project p%g = %d over %d samples '
                '(bundled default %d)"'
                % (
                    report["percentile"],
                    int(math.ceil(entry["project"])),
                    entry["n"],
                    int(entry["default"]),
                )
            )
    return "\n".join(lines) + "\n"


def write_thresholds(path: str, report: dict) -> int:
    """Write the overlay and return the number of thresholds it contains."""
    payload = thresholds_yaml(report)
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    return sum(1 for metric in METRICS if report["metrics"][metric.key]["applied"])


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="pyexamine-delta calibrate",
        description=(
            "Measure a project's own metric distribution and propose thresholds "
            "of the form max(bundled default, project percentile)."
        ),
    )
    parser.add_argument("project", help="Directory to calibrate")
    parser.add_argument(
        "--percentile",
        type=float,
        default=DEFAULT_PERCENTILE,
        help="Project percentile to compare against (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Threshold overlay to write (default: <project>/%s)" % THRESHOLDS_FILENAME,
    )
    parser.add_argument("--config", default=None, help="Configuration file to read defaults from")
    parser.add_argument(
        "--ignore",
        nargs="+",
        default=None,
        help="Directory names to skip",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=MIN_SAMPLES,
        help="Do not calibrate a metric with fewer observations (default: %(default)s)",
    )
    parser.add_argument(
        "--max-multiplier",
        type=float,
        default=DEFAULT_MAX_MULTIPLIER,
        help=(
            "Cap a proposed threshold at this multiple of the bundled default "
            "(default: %(default)s); without a cap one huge file can raise the "
            "file-length threshold past every file in the project"
        ),
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Report format (default: %(default)s)",
    )
    parser.add_argument("--version", action="store_true", help="Print the tool version and exit")
    return parser


def run(args) -> int:
    from .delta import EXIT_OK, _version
    from .main import DEFAULT_CONFIG_NAME, resolve_config_path

    project = os.path.abspath(args.project)
    if not os.path.isdir(project):
        raise FileNotFoundError(
            "Project directory does not exist: %s. Pass '.' to calibrate the "
            "current directory." % project
        )
    config_path = resolve_config_path(args.config or DEFAULT_CONFIG_NAME)
    config_handler = ConfigHandler(config_path)
    report = calibrate(
        project,
        config_handler,
        percent=args.percentile,
        ignore_dirs=args.ignore,
        min_samples=args.min_samples,
        max_multiplier=args.max_multiplier,
        tool_version=_version(),
    )

    output = args.output or os.path.join(project, THRESHOLDS_FILENAME)
    written = write_thresholds(output, report)

    if args.format == "json":
        report["output"] = os.path.abspath(output)
        report["written"] = written
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=False))
    else:
        print(render_calibration_text(report))
        print("")
        print("thresholds written to %s (%d raised)" % (os.path.abspath(output), written))
        if written:
            print("use them with: pyexamine-delta . --base origin/main --config %s" % output)
    return EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    from .delta import EXIT_USAGE

    args = build_parser().parse_args(argv)
    if args.version:
        from .delta import _version

        print(_version())
        return 0
    try:
        return run(args)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("calibrate failed: %s", exc)
        print("error: %s" % exc)
        return EXIT_USAGE
