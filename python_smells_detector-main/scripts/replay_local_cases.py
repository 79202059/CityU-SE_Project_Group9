"""Replay supplementary, source-defined lifecycle cases using the normal evaluation runner."""

import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from baseline_b import counts_for_pair
from score_evaluation import FOCAL

from code_quality_analyzer.config_handler import ConfigHandler

CONFIG = Path(__file__).resolve().parents[1] / "code_quality_config.yaml"


@dataclass(frozen=True)
class Fixture:
    files: dict
    rule: str
    path: str
    symbol: str
    line: int | None


def method(length=50, name="price", path="prices.py"):
    body = "".join(f"    value += {n}\n" for n in range(length - 2))
    return Fixture({path: f"def {name}(value):\n{body}    return value\n"},
                   "pyex-code-long-method", path, name, 1)


def large(size=16, name="Ledger", path="ledger.py"):
    body = "".join(f"    def entry_{n}(self):\n        pass\n" for n in range(size))
    return Fixture({path: f"class {name}:\n{body}"}, "pyex-code-large-class", path, name, 1)


def complex_function(branches=12, name="dispatch", path="routes.py", doc=False):
    body = "".join(f"    if x == {n}:\n        return {n}\n" for n in range(branches))
    docstring = '    """Pick a route."""\n' if doc else ""
    return Fixture({path: f"def {name}(x):\n{docstring}{body}    return -1\n"},
                   "pyex-struct-high-cyclomatic-complexity", path, Path(path).stem, 1)


def duplicate():
    body = "    a = x + 1\n    b = a * 2\n    c = b - 3\n    d = c ** 2\n    return d\n"
    source = "".join(f"def {name}(x):\n{body}" for name in ("first", "second"))
    return Fixture({"copies.py": source}, "pyex-code-duplicate-code", "copies.py", "first, second", None)


def cycle():
    return Fixture({"a.py": "import b\ndef start():\n    return b.stop()\n",
                    "b.py": "import a\ndef stop():\n    return a.start()\n"},
                   "pyex-arch-cyclic-dependency", "a.py", "a", None)


def cases():
    # Each pair starts from its own base. Expected records are specified before analysis.
    long, big, branching, clones, mutual = method(), large(), complex_function(), duplicate(), cycle()
    for added in (long, method(46, "total"), big, large(18, "Report"), branching,
                  complex_function(10, "lookup"), clones, mutual):
        yield "introduce", None, added, "NEW"
    for before, after in ((method(45), method(46)), (method(50), method(61)),
                          (large(15), large(16)), (large(16), large(20))):
        yield "worsen", before, after, "WORSENED"
    for before, after in ((long, method(name="charge")), (big, large(name="Journal")),
                          (branching, complex_function(name="route"))):
        yield "rename", before, after, "UNCHANGED"
    for before, after in ((long, method(path="billing.py")), (big, large(path="accounts.py")),
                          (branching, complex_function(path="routing.py"))):
        yield "move", before, after, "UNCHANGED"
    for removed in (long, big, clones, mutual):
        yield "resolve", removed, None, "RESOLVED"
    yield "cosmetic", long, replace(long, files={long.path: "\n" + long.files[long.path]}, line=2), "UNCHANGED"
    yield "cosmetic", branching, complex_function(doc=True), "UNCHANGED"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c",
                           "user.email=fixture@example.invalid", "-c", "core.hooksPath=" + str(repo / ".git/no-hooks"),
                           *args], check=True, capture_output=True, text=True).stdout.strip()


def revision(repo, fixture, message):
    if fixture:
        for filename, source in fixture.files.items():
            (repo / filename).write_text(source, encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    git(repo, "commit", "--allow-empty", "--no-gpg-sign", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def replay(root):
    overrides = {name for name in os.environ if name in {
        "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE"}}
    if overrides:
        raise ValueError("unset Git repository overrides before replay: " + ", ".join(sorted(overrides)))
    handler = ConfigHandler(str(CONFIG))
    rows = []
    for index, (mutation, before, after, state) in enumerate(cases(), 1):
        repo = root / f"case-{index:02d}"
        repo.mkdir()
        git(repo, "init")
        if not Path(git(repo, "rev-parse", "--show-toplevel")).samefile(repo):
            raise RuntimeError("fixture repository was not isolated")
        base = revision(repo, before, "fixture base")
        if before:
            for filename in before.files:
                (repo / filename).unlink()
        head = revision(repo, after, "fixture " + mutation)
        report = counts_for_pair(str(repo), base, head, handler, details=True)
        focal = after or before
        expected = {"rule": focal.rule, "path": focal.path, "symbol": focal.symbol,
                    "line": focal.line, "side": "base" if state == "RESOLVED" else "head", "state": state}
        observed = [item for item in report["details"]["proposed"] if item["rule"] in FOCAL]
        rows.append({"case": index, "mutation": mutation, "expected": expected, "observed": observed,
                     "exact": observed == [expected]})
    return {"experiment": "supplementary repository fixtures (2026-11-27)",
            "cases": len(rows), "exact": sum(r["exact"] for r in rows),
            "mix": dict(Counter(r["mutation"] for r in rows)), "results": rows}


def main():
    with tempfile.TemporaryDirectory(prefix="pyexamine-local-cases-") as directory:
        report = replay(Path(directory))
    print(json.dumps(report, indent=2))
    return int(report["exact"] != report["cases"])


if __name__ == "__main__":
    sys.exit(main())
