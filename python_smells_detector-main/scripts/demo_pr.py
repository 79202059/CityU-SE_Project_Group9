"""Reproduce the demo pull request: one commit adds a smell, the next removes it.

The script builds a throw-away git repository from ``tests/fixtures/demo_pr`` and
runs the delta gate three times:

1. write the baseline for the clean tree;
2. rewrite ``shop/orders.py`` into one 52-line function, so the gate must fail;
3. split that function into helpers, so the gate must pass.

It prints the exit code of every run and the measured size of the pull request, so
a demo or a report can quote a real number instead of an estimate.
"""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PACKAGE_ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(PACKAGE_ROOT, "tests", "fixtures", "demo_pr")

CLEAN_CART = "shop/cart.py"
ORDERS = "shop/orders.py"
INIT_FILE = "shop/__init__.py"
INIT_TEXT = '"""Demo package for the pull-request walkthrough."""\n'

GIT_IDENTITY = ("-c", "user.name=Demo Author", "-c", "user.email=demo@example.com")

EXIT_OK = 0
EXIT_GATE_REACHED = 1


def git(root: str, *args: str) -> subprocess.CompletedProcess:
    """Run one git command inside *root* and capture its output."""
    command = ["git", "-C", root, *GIT_IDENTITY, *args]
    return subprocess.run(command, capture_output=True, text=True, errors="replace", check=False)


def read_fixture(name: str) -> str:
    """Return the text of one file from the demo fixture directory."""
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as handle:
        return handle.read()


def write_file(root: str, relative: str, text: str) -> str:
    """Write *text* below *root* and return the absolute path."""
    path = os.path.join(root, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n", encoding="utf-8") as handle:
        handle.write(text)
    return path


def commit(root: str, message: str) -> str:
    """Stage everything and create one commit; return its short hash."""
    git(root, "add", "-A")
    result = git(root, "commit", "-m", message, "--no-gpg-sign")
    if result.returncode != 0:
        raise RuntimeError("git commit failed: %s" % (result.stderr or result.stdout).strip())
    rev = git(root, "rev-parse", "--short", "HEAD")
    return rev.stdout.strip()


def added_lines(root: str, base: str, head: str) -> tuple:
    """Return ``(added, removed, files)`` between *base* and *head*."""
    result = git(root, "diff", "--numstat", base, head)
    added = 0
    removed = 0
    files = 0
    for raw in result.stdout.splitlines():
        cells = raw.split("\t")
        if len(cells) >= 3 and cells[0].isdigit():
            added += int(cells[0])
            removed += int(cells[1])
            files += 1
    return added, removed, files


def build_repository(root: str) -> None:
    """Initialize the demo in a new or empty directory."""
    # Git hooks can export repository paths that take precedence over git -C.
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
                 "GIT_OBJECT_DIRECTORY"):
        if os.environ.get(name):
            raise RuntimeError(f"Run the demo with {name} unset so Git uses the demo directory.")
    os.makedirs(root, exist_ok=True)
    info = os.lstat(root)
    if stat.S_ISLNK(info.st_mode) or (
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    ):
        raise ValueError(f"Choose a demo directory that is not a link or junction: {root}")
    with os.scandir(root) as entries:
        if next(entries, None) is not None:
            raise ValueError(f"Demo directory is not empty: {root}. Choose a new or empty directory.")

    # Reserve the repository before writing fixtures. Concurrent demos targeting
    # the same empty directory cannot both initialize it.
    os.mkdir(os.path.join(root, ".git"))
    result = git(root, "init", "-b", "main")
    if result.returncode != 0:
        raise RuntimeError("git init failed: %s" % (result.stderr or result.stdout).strip())
    write_file(root, INIT_FILE, INIT_TEXT)
    write_file(root, CLEAN_CART, read_fixture("cart.py"))
    write_file(root, ORDERS, read_fixture("orders_fixed.py"))
    commit(root, "initial layout")


def delta_main(argv: list) -> int:
    """Call the delta CLI in process and return its exit code."""
    from code_quality_analyzer.delta import main as cli

    return cli(argv)


def run_step(root: str, label: str, argv: list, expected: int) -> bool:
    """Run one gate invocation, print the outcome and report whether it matched."""
    code = delta_main(argv)
    mark = "ok" if code == expected else "UNEXPECTED"
    print("%-26s exit=%d (expected %d)  %s" % (label, code, expected, mark))
    return code == expected


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Build the demo pull request and run the delta gate on it.",
    )
    parser.add_argument(
        "--root",
        help="keep the demo in a new or empty directory; by default a temporary directory "
             "is created for this run and cleaned up afterwards",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    """Execute the three-step walkthrough and return 0 when every step matched."""
    if args.root is not None:
        return run_walkthrough(os.path.abspath(args.root))
    with tempfile.TemporaryDirectory(prefix="pyexamine-demo-") as root:
        return run_walkthrough(root)


def run_walkthrough(root: str) -> int:
    build_repository(root)
    print("built a clean repository at %s" % root)

    base = git(root, "rev-parse", "HEAD").stdout.strip()

    print("")
    print("step 1: record the baseline of the clean tree")
    ok = run_step(
        root,
        "  write baseline",
        [root, "--base", base, "--head", base, "--baseline-mode", "write"],
        EXIT_OK,
    )

    print("")
    print("step 2: open a pull request that adds one long function")
    write_file(root, ORDERS, read_fixture("orders_long.py"))
    head = commit(root, "add order pricing")
    added, removed, files = added_lines(root, base, head)
    ok = run_step(
        root,
        "  gate on the pull request",
        [
            root,
            "--base", base,
            "--head", head,
            "--baseline-mode", "diff",
            "--fail-on-new", "medium",
            "--fail-on-worsened",
            "--level-policy", "triage",
            "--format", "markdown",
        ],
        EXIT_GATE_REACHED,
    ) and ok

    print("")
    print("step 3: split the long function in a follow-up commit")
    write_file(root, ORDERS, read_fixture("orders_fixed.py"))
    fixed = commit(root, "split the pricing loop into helpers")
    ok = run_step(
        root,
        "  gate after the fix",
        [
            root,
            "--base", base,
            "--head", fixed,
            "--baseline-mode", "diff",
            "--fail-on-new", "medium",
            "--fail-on-worsened",
            "--level-policy", "triage",
            "--format", "markdown",
        ],
        EXIT_OK,
    ) and ok

    print("")
    print("the pull request changes %d line(s): +%d -%d across %d file(s)"
          % (added + removed, added, removed, files))
    print("reproduced: %s" % ("yes" if ok else "no"))
    return EXIT_OK if ok else EXIT_GATE_REACHED


def main(argv: list = None) -> int:
    """Command-line entry point."""
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except (OSError, RuntimeError, ValueError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
