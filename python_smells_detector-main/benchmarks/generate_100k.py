"""Deterministic ~100k-line Python project generator for the performance NFR.

The benchmark target is synthetic on purpose: the ADR-008 measurement protocol
asks for a fixed 100k-line project, and a generated tree can be rebuilt byte for
byte on any machine.  The shape is realistic enough for the detectors to do
their usual work - packages, module imports, module-level functions, classes
with methods, long and branchy functions.
"""

from __future__ import annotations

import argparse
import os

MODULE_TARGET_LINES = 250
MODULES_PER_SUB = 40
SUBS = 10


def _body(prefix: str, count: int, indent: str = "    ") -> list:
    """A predictable straight-line body (identifier + literal per line)."""
    return ["%sv%d = %s%d" % (indent, index, prefix, index) for index in range(count)]


def _function(name: str, size: int, branches: int = 0) -> list:
    lines = ["def %s(x):" % name, '    """Generated helper."""']
    if branches:
        for index in range(branches):
            lines += ["    if x > %d:" % index, "        x = x - %d" % index]
    lines += _body("x + ", max(4, size - len(lines) - branches * 2 - 2))
    lines.append("    return v0")
    return lines


def _klass(name: str, methods: int, method_lines: int) -> list:
    lines = ["class %s:" % name, '    """Generated service."""']
    for index in range(methods):
        lines.append("    def m%d(self, x):" % index)
        lines.append("        y%d = x + %d" % (index, index))
        for step in range(max(2, method_lines - 4)):
            lines.append("        y%d = y%d + %d" % (index, index, step))
        lines.append("        return y%d" % index)
        lines.append("")
    return lines[:-1]


def module_source(index: int, imports: list) -> str:
    lines = ['"""Benchmark module %03d."""' % index]
    for target in imports:
        lines.append("from bench.sub%d import mod%03d" % (target // MODULES_PER_SUB, target))
    lines.append("")
    lines += _function("helper_%03d_a" % index, 40, branches=6)
    lines.append("")
    lines += _function("helper_%03d_b" % index, 30, branches=3)
    lines.append("")
    lines += _function("helper_%03d_c" % index, 60, branches=8)
    lines.append("")
    lines += _klass("Service%03d" % index, methods=8, method_lines=12)
    lines.append("")
    return "\n".join(lines) + "\n"


def generate(root: str, target_lines: int = 100_000) -> dict:
    """Write the project under ``root``; return counts used in the report."""
    written_lines = 0
    files = 0
    index = 0
    os.makedirs(root, exist_ok=True)
    init = os.path.join(root, "bench", "__init__.py")
    os.makedirs(os.path.dirname(init), exist_ok=True)
    if not os.path.exists(init):
        with open(init, "w", encoding="utf-8", newline="\n") as handle:
            handle.write('"""Benchmark project."""\n')
    while written_lines < target_lines:
        sub = index // MODULES_PER_SUB
        sub_dir = os.path.join(root, "bench", "sub%d" % sub)
        os.makedirs(sub_dir, exist_ok=True)
        sub_init = os.path.join(sub_dir, "__init__.py")
        if not os.path.exists(sub_init):
            with open(sub_init, "w", encoding="utf-8", newline="\n") as handle:
                handle.write("")
        source = module_source(index, [index + 1])
        path = os.path.join(sub_dir, "mod%03d.py" % index)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(source)
        written_lines += source.count("\n")
        files += 1
        index += 1
    return {"files": files, "lines": written_lines, "modules": index}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate the 100k-line benchmark project.")
    parser.add_argument("root")
    parser.add_argument("--target-lines", type=int, default=100_000)
    args = parser.parse_args(argv)
    counts = generate(args.root, args.target_lines)
    print("generated %d files, %d lines at %s" % (counts["files"], counts["lines"], args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
