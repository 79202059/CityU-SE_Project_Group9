"""Validate a SARIF document against the official 2.1.0 schema.

The repository ships the schema as a test fixture
(``tests/fixtures/sarif/sarif-schema-2.1.0.json``, copied from
``https://json.schemastore.org/sarif-2.1.0.json``), so validation works
offline.  ``fastjsonschema`` is used because it is a pure-Python wheel that
installs on every platform the project supports; it is deliberately *not* a
runtime dependency, because shipped code never validates its own output.

Usage::

    python scripts/validate_sarif_schema.py report.sarif
    python scripts/validate_sarif_schema.py --format sarif out/*.sarif
    python scripts/validate_sarif_schema.py --schema other-schema.json a.sarif

Exit code 0 means every document is valid; 1 means at least one failed or a
document could not be read.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_SCHEMA = os.path.join(ROOT, "tests", "fixtures", "sarif", "sarif-schema-2.1.0.json")


def _validator():
    try:
        import fastjsonschema
    except ImportError:
        print("fastjsonschema is missing: pip install fastjsonschema", file=sys.stderr)
        return None
    return fastjsonschema.compile


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate SARIF documents against SARIF 2.1.0.")
    parser.add_argument("documents", nargs="+", help="SARIF JSON files")
    parser.add_argument("--schema", default=DEFAULT_SCHEMA, help="schema file (defaults to the bundled copy)")
    args = parser.parse_args(argv)

    compile_schema = _validator()
    if compile_schema is None:
        return 1
    if not os.path.exists(args.schema):
        print("schema not found: %s" % args.schema, file=sys.stderr)
        return 1
    with io.open(args.schema, encoding="utf-8") as handle:
        schema = json.load(handle)
    validate = compile_schema(schema)

    failures = 0
    for path in args.documents:
        if not os.path.exists(path):
            print("%-40s MISSING" % path)
            failures += 1
            continue
        with io.open(path, encoding="utf-8") as handle:
            document = json.load(handle)
        results = 0
        runs = document.get("runs") or []
        if runs:
            results = len(runs[0].get("results") or [])
        try:
            validate(document)
        except Exception as error:  # fastjsonschema raises a subclass of Exception
            message = getattr(error, "message", str(error))
            where = getattr(error, "path", [])
            print("%-40s INVALID results=%d: %s at %s" % (path, results, message, where))
            failures += 1
            continue
        print("%-40s VALID   results=%d" % (path, results))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
