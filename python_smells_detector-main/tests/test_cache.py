"""Tests for the content-addressed analysis cache (``cache.py``)."""

from pathlib import Path

from code_quality_analyzer import delta
from code_quality_analyzer.cache import AnalysisCache, config_digest, tree_manifest
from code_quality_analyzer.code_smell_detector import CodeSmellDetector
from code_quality_analyzer.config_handler import ConfigHandler
from code_quality_analyzer.finding import Finding
from code_quality_analyzer.main import resolve_config_path

SAMPLE_PROJECT = Path(__file__).resolve().parent / "fixtures" / "sample_project"


class _FakeConfig:
    """Minimal stand-in for ConfigHandler: only get_thresholds is needed."""

    def __init__(self, thresholds):
        self.thresholds = thresholds

    def get_thresholds(self, section):
        return self.thresholds.get(section, {})


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_manifest_is_stable_across_roots(tmp_path):
    """The same sources materialised in different directories share one digest."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    _write(a / "pkg" / "mod.py", "def f():\n    return 1\n")
    _write(b / "pkg" / "mod.py", "def f():\n    return 1\n")

    _, digest_a = tree_manifest(str(a), ignore=set())
    _, digest_b = tree_manifest(str(b), ignore=set())
    assert digest_a == digest_b


def test_manifest_changes_when_content_changes(tmp_path):
    root = tmp_path / "tree"
    _write(root / "mod.py", "def f():\n    return 1\n")
    _, before = tree_manifest(str(root), ignore=set())

    _write(root / "mod.py", "def f():\n    return 2\n")
    _, after = tree_manifest(str(root), ignore=set())
    assert before != after


def test_manifest_respects_ignore(tmp_path):
    root = tmp_path / "tree"
    _write(root / "kept.py", "x = 1\n")
    _write(root / "venv" / "skipped.py", "y = 2\n")

    entries, _ = tree_manifest(str(root), ignore={"venv"})
    rel_paths = [rel for rel, _ in entries]
    assert "kept.py" in rel_paths
    assert all(not rel.startswith("venv") for rel in rel_paths)


def test_roundtrip_reroots_findings(tmp_path):
    """Findings are stored relative to the tree and re-rooted on load."""
    cache = AnalysisCache(str(tmp_path / "cache"))
    tree_a = tmp_path / "tree_a"
    tree_b = tmp_path / "tree_b"
    for tree in (tree_a, tree_b):
        (tree / "pkg").mkdir(parents=True, exist_ok=True)

    finding = Finding(
        category="code",
        smell_type="Long Method",
        file_path=str(tree_a / "pkg" / "mod.py"),
        symbol="pkg.mod.long_func",
        line=12,
        severity="high",
        description="'long_func' has 80 lines",
        metric_value=80.0,
    )
    cache.store("some-key", [finding], {"pkg.mod": 3}, str(tree_a))

    restored, fan_in = cache.load("some-key", str(tree_b))
    assert fan_in == {"pkg.mod": 3}
    assert len(restored) == 1
    assert restored[0].file_path == str(tree_b / "pkg" / "mod.py")
    assert restored[0].smell_type == "Long Method"
    assert restored[0].metric_value == 80.0
    assert restored[0].line == 12


def test_missing_entry_is_a_miss(tmp_path):
    cache = AnalysisCache(str(tmp_path / "cache"))
    assert cache.load("no-such-key", str(tmp_path)) is None


def test_key_depends_on_config():
    config_a = _FakeConfig({"code_smells": {"LONG_METHOD_LINES": 45}})
    config_b = _FakeConfig({"code_smells": {"LONG_METHOD_LINES": 80}})
    assert config_digest(config_a) != config_digest(config_b)


def test_analyze_tree_hit_reuses_cache(tmp_path, monkeypatch):
    """A warm cache returns the same findings without re-running the detector."""
    config_handler = ConfigHandler(resolve_config_path("code_quality_config.yaml"))
    cache = AnalysisCache(str(tmp_path / "cache"))
    tree = str(SAMPLE_PROJECT)

    calls = []
    original = CodeSmellDetector.detect_smells

    def counting(self, file_path):
        calls.append(file_path)
        return original(self, file_path)

    monkeypatch.setattr(CodeSmellDetector, "detect_smells", counting)

    context_first = {}
    first = delta.analyze_tree(tree, config_handler, context=context_first, cache=cache)
    assert calls, "a cold cache must still run the detector"

    calls_after_first = len(calls)
    context_second = {}
    second = delta.analyze_tree(tree, config_handler, context=context_second, cache=cache)

    assert len(calls) == calls_after_first, "a warm cache must not re-run the detector"
    assert second == first
    assert context_second.get("fan_in") == context_first.get("fan_in")


def test_tree_level_finding_round_trips_to_the_root(tmp_path):
    """A module-level smell records the analysed directory as its file_path.

    Re-rooting must map that back onto the new root verbatim: storing it as
    ``root/.`` changes the SARIF fingerprint and would turn one finding into
    NEW + RESOLVED on the next run (regression found while auditing flask).
    """
    root = str(tmp_path / "tree")
    other = str(tmp_path / "other")
    Path(root, "pkg").mkdir(parents=True, exist_ok=True)
    Path(other).mkdir(parents=True, exist_ok=True)
    cache = AnalysisCache(str(tmp_path / "cache"))

    tree_level = Finding(
        category="structural",
        smell_type="High Number of Classes (NOC)",
        file_path=root,
        symbol="Project",
        line=None,
        severity="high",
        description="Project has 9.0 weighted classes",
        metric_value=9.0,
    )
    cache.store("k", [tree_level], {}, root)

    loaded, fan_in = cache.load("k", other)
    assert loaded[0].file_path == other
    assert loaded[0].metric_value == 9.0
    assert fan_in == {}
