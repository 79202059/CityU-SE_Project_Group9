"""Threshold evidence through real checkouts, cached analysis and stored baselines."""

import json
import subprocess
from pathlib import Path

from code_quality_analyzer.cache import AnalysisCache
from code_quality_analyzer.config_handler import ConfigHandler
from code_quality_analyzer.delta import analyze_tree, main
from code_quality_analyzer.finding import Finding
from code_quality_analyzer.main import resolve_config_path
from code_quality_analyzer.metrics import long_method_crossings, measured_crossings


def test_class_measurements_filter_exempt_and_ambiguous_symbols(tmp_path):
    src = tmp_path / "m.py"
    src.write_text("from dataclasses import dataclass\n@dataclass\nclass Data:\n    pass\n"
                   "class Broken(Exception):\n    pass\nclass Twice:\n    pass\nclass Twice:\n    pass\n"
                   "class Simple:\n    def __init__(self):\n        pass\n    def get(self):\n        return 1\n"
                   "    class Inner:\n        pass\n", encoding="utf-8")
    context = {}
    handler = ConfigHandler(resolve_config_path("code_quality_config.yaml"))
    analyze_tree(str(tmp_path), handler, context=context)
    counts = context["large_classes"]["files"]["m.py"]
    assert counts == {"Data": None, "Broken": None, "Twice": None, "Simple": 0, "Inner": None}
    f = Finding("code", "Large Class", str(src), "Simple", metric_value=2)
    head = {"large_classes": {"threshold": 1, "files": {"m.py": {"Simple": 2}}}}
    for count, limit in [(None, 1), (1, 2), (2, 1)]:
        base = {"large_classes": {"threshold": limit, "files": {"m.py": {"Simple": count}}}}
        assert measured_crossings(base, head, [f], str(tmp_path)) == {}


def test_large_class_threshold_in_repository_and_legacy_baseline(tmp_path, monkeypatch, capsys):
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY", "GIT_INDEX_FILE"):
        monkeypatch.delenv(key, raising=False)
    repo = tmp_path / "project"
    repo.mkdir()

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), "-c", "user.name=Test", "-c",
                                        "user.email=test@example.invalid", *args], text=True).strip()

    git("init")
    assert Path(git("rev-parse", "--show-toplevel")).samefile(repo)
    cfg = tmp_path / "config.yaml"
    cfg.write_text("code_smells:\n  LARGE_CLASS_METHODS: 1\n", encoding="utf-8")
    baseline = tmp_path / "accepted.json"
    cache = tmp_path / "cache"
    methods = "    def a(self):\n        pass\n    def b(self):\n        pass\n"
    source = repo / "calc.py"
    source.write_text("class Cart:\n    def trivial(self):\n        return 1\n", encoding="utf-8")
    git("add", "calc.py")
    git("commit", "--no-gpg-sign", "-m", "base")
    base = git("rev-parse", "HEAD")
    source.write_text("class Cart:\n" + methods + "class New:\n" + methods, encoding="utf-8")
    git("commit", "--no-gpg-sign", "-am", "head")

    def run(mode, head="HEAD"):
        capsys.readouterr()
        assert main([str(repo), "--base", base, "--head", head, "--config", str(cfg), "--format", "json",
                     "--baseline-mode", mode, "--baseline", str(baseline), "--cache-dir", str(cache)]) == 0
        return json.loads(capsys.readouterr().out)["findings"]

    run("write", base)
    for mode in ("off", "diff"):
        rows = run(mode)
        worse, = [f for f in rows["WORSENED"] if f["type"] == "Large Class"]
        assert worse["worsened"] == {"reason": "metric", "metric": "LARGE_CLASS_METHODS", "base": 0,
                                    "head": 2, "delta": 2, "threshold": 1}
        assert [f["symbol"] for f in rows["NEW"] if f["type"] == "Large Class"] == ["New"]
    doc = json.loads(baseline.read_text(encoding="utf-8"))
    del doc["large_classes"]
    baseline.write_text(json.dumps(doc), encoding="utf-8")
    assert {f["symbol"] for f in run("diff")["NEW"] if f["type"] == "Large Class"} == {"Cart", "New"}


def test_long_method_crossing_at_cli(tmp_path, capsys, monkeypatch):
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                 "GIT_OBJECT_DIRECTORY"):
        monkeypatch.delenv(name, raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=t@example.com",
             *args], text=True,
        ).strip()

    def revision(name, length):
        (repo / "calc.py").write_text(
            f"def {name}():\n" + "".join(f"    n = {i}\n" for i in range(length - 2))
            + "    return n\n", encoding="utf-8",
        )
        git("add", "calc.py")
        git("commit", "--no-gpg-sign", "-m", name + str(length))
        return git("rev-parse", "HEAD")

    git("init")
    assert Path(git("rev-parse", "--show-toplevel")).samefile(repo)
    base = revision("price", 5)
    head = revision("price", 6)
    renamed = revision("replacement", 6)
    config = tmp_path / "thresholds.yaml"
    config.write_text("code_smells:\n  LONG_METHOD_LINES: 5\n", encoding="utf-8")
    baseline = tmp_path / "accepted.json"

    def report(ref, *args, expected=0):
        capsys.readouterr()
        result = main([str(repo), "--base", base, "--head", ref, "--config", str(config),
                       "--baseline", str(baseline), "--format", "json", *args])
        out, err = capsys.readouterr()
        assert result == expected, err
        return json.loads(out)["findings"]

    clean = report(base, "--baseline-mode", "write")
    assert all(f["type"] != "Long Method" for rows in clean.values() for f in rows)
    for mode in ("off", "diff"):
        report(head, "--baseline-mode", mode, "--max-new", "0")
        findings = report(head, "--baseline-mode", mode, "--max-new", "0",
                          "--fail-on-worsened", expected=1)
        item, = (f for f in findings["WORSENED"] if f["type"] == "Long Method")
        assert item["worsened"] == {
            "reason": "metric", "metric": "LONG_METHOD_LINES", "base": 5,
            "head": 6, "delta": 1, "threshold": 5,
        }
    for ref, options in ((head, ["--no-worsen"]), (renamed, [])):
        findings = report(ref, "--baseline-mode", "off", *options)
        assert [f["type"] for f in findings["NEW"]].count("Long Method") == 1

    doc = json.loads(baseline.read_text(encoding="utf-8"))
    del doc["long_methods"]
    baseline.write_text(json.dumps(doc), encoding="utf-8")
    legacy = report(head, "--baseline-mode", "diff")
    assert any(f["type"] == "Long Method" for f in legacy["NEW"])


def test_crossing_requires_comparable_unambiguous_evidence(tmp_path):
    finding = Finding("code", "Long Method", str(tmp_path / "mod.py"), "f", metric_value=46)

    def observations(length, threshold=45):
        return {"files": {"mod.py": {"f": length}}, "threshold": threshold}

    for base in ({}, None, observations(None), observations(46), observations(44, 60)):
        assert not long_method_crossings(base, observations(46), [finding], str(tmp_path))
    assert not long_method_crossings(observations(44), observations(45), [finding], str(tmp_path))
    assert not long_method_crossings(observations(44), observations(None), [finding], str(tmp_path))


def test_cache_hit_restores_the_cold_measurements_without_absolute_paths(tmp_path):
    cache = AnalysisCache(str(tmp_path / "cache"))
    config = ConfigHandler(resolve_config_path("code_quality_config.yaml"))
    source = ("class Cart:\n    def subtotal(self):\n        # ignored\n        return 1\n"
              "def outer():\n    def helper():\n        return 1\n    return helper()\n"
              "def twice():\n    pass\ndef twice():\n    pass\n")
    tree_a, tree_b = tmp_path / "a", tmp_path / "b"
    for tree in (tree_a, tree_b):
        tree.mkdir()
        (tree / "shop.py").write_text(source, encoding="utf-8")
    analyze_tree(str(tree_a), config, cache=cache)
    warm, cold = {}, {}
    analyze_tree(str(tree_b), config, context=warm, cache=cache)
    analyze_tree(str(tree_b), config, context=cold)
    assert warm == cold
    methods = warm["long_methods"]["files"]["shop.py"]
    assert methods["Cart.subtotal"] == 2
    assert methods["twice"] is None and methods["helper"] is None
