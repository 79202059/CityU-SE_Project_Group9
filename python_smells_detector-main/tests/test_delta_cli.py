"""End-to-end tests for the ``pyexamine-delta`` command line.

The pure functions are covered by ``test_delta.py``, ``test_markdown.py`` and
friends; what was missing is ``run()`` itself - argument wiring, the two
baseline modes, the gate return codes and every output format.  Those can only
be exercised against a real git repository, because ``VersionProvider`` shells
out to ``git worktree``.  Everything here runs in-process (no subprocess) so the
coverage tool sees the CLI code.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

from code_quality_analyzer.delta import EXIT_GATE_REACHED, EXIT_OK, EXIT_USAGE, main

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = ""
REPO = os.path.join(WORK, "repo")
BASELINE = os.path.join(WORK, "baseline.json")

CART = '''"""Shopping cart."""


class Cart:
    def __init__(self):
        self.items = []

    def add(self, item):
        self.items.append(item)

    def total(self):
        return len(self.items)
'''

PRICING = '''"""Pricing helpers."""


def subtotal(rows):
    return sum(rows)
'''

PRICING_V2 = PRICING + '''

def discount(total):
    if total > 100:
        return total * 0.9
    return total
'''

CHECKOUT = '''"""Checkout flow."""


%s

def compute_0(value):
    return value + 0
''' % "\n".join(
    ["def checkout():"]
    + ["    row%d = %d" % (i, i) for i in range(60)]
    + ["    return row59"]
)


def _force_remove(path):
    """Remove a tree even when git left read-only objects behind (Windows)."""

    def on_error(function, target, _info):
        try:
            os.chmod(target, 0o700)
            function(target)
        except OSError:
            pass

    if os.path.exists(path):
        shutil.rmtree(path, onerror=on_error)


def git(*args):
    if args and args[0] != "init":
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        if root.returncode != 0 or not os.path.samefile(root.stdout.strip(), REPO):
            raise AssertionError(
                "refusing git operation outside the CLI test repository: %s" % root.stdout
            )
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "tests",
        "GIT_AUTHOR_EMAIL": "tests@example.com",
        "GIT_COMMITTER_NAME": "tests",
        "GIT_COMMITTER_EMAIL": "tests@example.com",
    })
    done = subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, env=env
    )
    if done.returncode != 0:
        raise AssertionError("git %s failed: %s" % (args, done.stderr))
    return done.stdout.strip()


def commit_all(message):
    git("add", "-A")
    git("commit", "-m", message)
    return git("rev-parse", "HEAD")


def write(relative, text):
    path = os.path.join(REPO, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def setUpModule():
    global BASELINE, REPO, WORK
    WORK = tempfile.mkdtemp(prefix="pyexamine-delta-cli-")
    REPO = os.path.join(WORK, "repo")
    BASELINE = os.path.join(WORK, "baseline.json")
    os.makedirs(REPO, exist_ok=True)
    git("init")
    write("shop/__init__.py", "")
    write("shop/cart.py", CART)
    write("shop/pricing.py", PRICING)
    setUpModule.first = commit_all("initial layout")
    write("shop/checkout.py", CHECKOUT)
    write("shop/pricing.py", PRICING_V2)
    setUpModule.second = commit_all("add checkout")


def tearDownModule():
    _force_remove(WORK)


def first():
    return setUpModule.first


def second():
    return setUpModule.second


def baseline(*extra):
    """Arguments every case shares: compare the second commit to the first."""
    return ["--base", first(), "--head", second(), *extra]


class TestOutputFormats(unittest.TestCase):
    def test_default_text_lists_the_new_finding(self):
        code = main([REPO, *baseline()])
        self.assertEqual(EXIT_OK, code)

    def test_json_is_parseable_and_counts_states(self):
        code = main([REPO, *baseline("--format", "json")])
        self.assertEqual(EXIT_OK, code)

    def test_sarif_is_a_valid_document(self):
        code = main([REPO, *baseline("--format", "sarif")])
        self.assertEqual(EXIT_OK, code)

    def test_machine_reports_keep_status_messages_on_stderr(self):
        cases = [
            ("success", [], EXIT_OK, None),
            ("risk filter", ["--min-risk", "100"], EXIT_OK, "risk:"),
            (
                "severity gate",
                ["--fail-on-new", "low"],
                EXIT_GATE_REACHED,
                "gate:",
            ),
            (
                "budget gate",
                ["--max-new", "0"],
                EXIT_GATE_REACHED,
                "budget:",
            ),
            (
                "risk-filtered gate",
                ["--min-risk", "0", "--fail-on-new", "low"],
                EXIT_GATE_REACHED,
                "gate:",
            ),
        ]
        for report_format in ("json", "sarif"):
            for label, options, expected_code, diagnostic in cases:
                with self.subTest(format=report_format, case=label):
                    stdout = StringIO()
                    stderr = StringIO()
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        code = main(
                            [REPO, *baseline("--format", report_format, *options)]
                        )

                    self.assertNotIn("risk:", stdout.getvalue())
                    self.assertNotIn("gate:", stdout.getvalue())
                    self.assertNotIn("budget:", stdout.getvalue())

                    document = json.loads(stdout.getvalue())
                    self.assertEqual(code, expected_code)
                    if report_format == "json":
                        self.assertIn("findings", document)
                    else:
                        self.assertIn("runs", document)
                        self.assertEqual("2.1.0", document["version"])
                    self.assertEqual(
                        diagnostic is not None,
                        diagnostic in stderr.getvalue() if diagnostic else False,
                    )

    def test_machine_report_baseline_status_stays_on_stderr(self):
        for report_format in ("json", "sarif"):
            with self.subTest(format=report_format):
                baseline_path = os.path.join(
                    WORK, "machine-baseline-%s.json" % report_format
                )
                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main([
                        REPO,
                        "--base", first(),
                        "--head", first(),
                        "--baseline", baseline_path,
                        "--baseline-mode", "write",
                        "--format", report_format,
                    ])

                document = json.loads(stdout.getvalue())
                self.assertEqual(code, EXIT_OK)
                self.assertIn("Baseline written to", stderr.getvalue())
                if report_format == "sarif":
                    self.assertIn("runs", document)

    def test_machine_report_errors_do_not_write_to_stdout(self):
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([
                os.path.join(WORK, "no-such-project"),
                "--base", first(),
                "--format", "json",
            ])

        self.assertEqual(code, EXIT_USAGE)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("error:", stderr.getvalue())

    def test_machine_report_output_files_keep_status_on_stdout(self):
        for report_format in ("json", "sarif"):
            with self.subTest(format=report_format):
                target = os.path.join(WORK, "machine-report-%s" % report_format)
                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main([
                        REPO,
                        *baseline("--format", report_format, "--output", target),
                    ])

                self.assertEqual(code, EXIT_OK)
                self.assertIn("Text report written to", stdout.getvalue())
                self.assertIn("JSON report written to", stdout.getvalue())
                self.assertTrue(os.path.isfile(target + ".txt"))
                with open(target + ".json", encoding="utf-8") as handle:
                    self.assertIn("findings", json.load(handle))

    def test_markdown_renders_a_table(self):
        code = main([REPO, *baseline("--format", "markdown")])
        self.assertEqual(EXIT_OK, code)

    def test_output_writes_both_text_and_json(self):
        target = os.path.join(WORK, "report")
        for suffix in (".txt", ".json"):
            if os.path.exists(target + suffix):
                os.remove(target + suffix)
        code = main([REPO, *baseline("--output", target)])
        self.assertEqual(EXIT_OK, code)
        with open(target + ".json", encoding="utf-8") as handle:
            payload = json.load(handle)
        self.assertIn("summary", payload)
        self.assertTrue(os.path.exists(target + ".txt"))
        for suffix in (".txt", ".json"):
            if os.path.exists(target + suffix):
                os.remove(target + suffix)

    def test_help_exits_zero(self):
        with self.assertRaises(SystemExit) as caught:
            main(["--help"])
        self.assertEqual(0, caught.exception.code)

    def test_version_exits_zero(self):
        with self.assertRaises(SystemExit) as caught:
            main(["--version"])
        self.assertEqual(0, caught.exception.code)


class TestBaselineModes(unittest.TestCase):
    def test_write_then_diff_reports_new_findings(self):
        if os.path.exists(BASELINE):
            os.remove(BASELINE)
        written = main([
            REPO, "--base", first(), "--head", first(),
            "--baseline", BASELINE, "--baseline-mode", "write",
        ])
        self.assertEqual(EXIT_OK, written)
        self.assertTrue(os.path.exists(BASELINE))
        with open(BASELINE, encoding="utf-8") as handle:
            payload = json.load(handle)
        self.assertIn("counts", payload)
        self.assertGreater(payload["counts"]["total"], 0)

        code = main([
            REPO, "--base", second(), "--head", second(),
            "--baseline", BASELINE, "--baseline-mode", "diff",
        ])
        self.assertEqual(EXIT_OK, code)

    def test_missing_baseline_falls_back_to_commit_comparison(self):
        missing = os.path.join(WORK, "absent.json")
        if os.path.exists(missing):
            os.remove(missing)
        code = main([REPO, *baseline("--baseline", missing, "--baseline-mode", "diff")])
        self.assertEqual(EXIT_OK, code)

    def test_explicitly_disabled_baseline_mode(self):
        code = main([REPO, *baseline("--baseline-mode", "off")])
        self.assertEqual(EXIT_OK, code)


class TestGates(unittest.TestCase):
    def test_fail_on_new_blames_the_new_finding(self):
        code = main([REPO, *baseline("--fail-on-new", "low")])
        self.assertEqual(EXIT_GATE_REACHED, code)

    def test_fail_on_new_high_is_not_reached_by_medium_findings(self):
        code = main([REPO, *baseline("--fail-on-new", "high")])
        self.assertEqual(EXIT_OK, code)

    def test_budget_of_zero_fails(self):
        code = main([REPO, *baseline("--max-new", "0")])
        self.assertEqual(EXIT_GATE_REACHED, code)

    def test_budget_that_is_not_exceeded_passes(self):
        code = main([REPO, *baseline("--max-new", "1000")])
        self.assertEqual(EXIT_OK, code)

    def test_min_risk_filters_the_gate(self):
        code = main([REPO, *baseline("--fail-on-new", "low", "--min-risk", "90")])
        self.assertEqual(EXIT_OK, code)

    def test_min_risk_zero_keeps_the_gate_armed(self):
        code = main([REPO, *baseline("--fail-on-new", "low", "--min-risk", "0")])
        self.assertEqual(EXIT_GATE_REACHED, code)


class TestOptions(unittest.TestCase):
    def test_no_worsen_keeps_three_states(self):
        code = main([REPO, *baseline("--no-worsen")])
        self.assertEqual(EXIT_OK, code)

    def test_no_fuzzy_falls_back_to_exact_fingerprints(self):
        code = main([REPO, *baseline("--no-fuzzy")])
        self.assertEqual(EXIT_OK, code)

    def test_fuzzy_threshold_is_accepted(self):
        code = main([REPO, *baseline("--fuzzy-threshold", "0.9")])
        self.assertEqual(EXIT_OK, code)

    def test_risk_flag_does_not_change_the_exit_code(self):
        code = main([REPO, *baseline("--risk")])
        self.assertEqual(EXIT_OK, code)

    def test_risk_explains_worsened_findings_without_changing_default_gate(self):
        checkout = "def checkout():\n" + "\n".join(
            "    row%d = %d" % (index, index) for index in range(90)
        ) + "\n    return row89\n"
        write("shop/checkout.py", '"""Checkout flow."""\n\n' + checkout)
        worsened_head = commit_all("worsen an existing long method")
        new_method = "def new_checkout():\n" + "\n".join(
            "    value%d = %d" % (index, index) for index in range(90)
        ) + "\n    return value89\n"
        write("shop/new_checkout.py", '"""New checkout helpers."""\n\n' + new_method)
        mixed_head = commit_all("add another long method")

        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([
                REPO,
                "--base", second(),
                "--head", mixed_head,
                "--format", "json",
                "--risk",
            ])

        mixed_payload = json.loads(stdout.getvalue())
        self.assertEqual(EXIT_OK, code)
        self.assertTrue(mixed_payload["findings"]["NEW"])
        self.assertTrue(mixed_payload["findings"]["WORSENED"])
        worsened = mixed_payload["findings"]["WORSENED"][0]
        self.assertIn("risk", worsened)
        self.assertGreaterEqual(worsened["risk"]["score"], 0)
        self.assertTrue(worsened["risk"]["reasons"])

        # The same head tree has one NEW in each run. Adding a WORSENED finding
        # must not change the NEW score used by the default gate.
        stdout = StringIO()
        with redirect_stdout(stdout), redirect_stderr(StringIO()):
            code = main([
                REPO,
                "--base", worsened_head,
                "--head", mixed_head,
                "--format", "json",
                "--risk",
            ])
        new_only_payload = json.loads(stdout.getvalue())
        self.assertEqual(EXIT_OK, code)
        mixed_new = mixed_payload["findings"]["NEW"][0]
        new_only = new_only_payload["findings"]["NEW"][0]
        self.assertEqual(mixed_new["file"], new_only["file"])
        self.assertEqual(mixed_new["risk"]["score"], new_only["risk"]["score"])

        # WORSENED is reportable by --risk, but remains outside the default
        # NEW-only severity gate unless the user explicitly opts in.
        stderr = StringIO()
        stdout = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([
                REPO,
                "--base", second(),
                "--head", worsened_head,
                "--format", "json",
                "--fail-on-new", "low",
                "--min-risk", "0",
            ])
        self.assertEqual(EXIT_OK, code)
        default_gate_payload = json.loads(stdout.getvalue())
        self.assertTrue(default_gate_payload["findings"]["WORSENED"])
        self.assertIn("risk", default_gate_payload["findings"]["WORSENED"][0])
        self.assertNotIn("gate:", stderr.getvalue())

        stderr = StringIO()
        stdout = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([
                REPO,
                "--base", second(),
                "--head", worsened_head,
                "--format", "json",
                "--fail-on-new", "low",
                "--min-risk", "0",
                "--fail-on-worsened",
                "--max-new", "0",
            ])
        self.assertEqual(EXIT_GATE_REACHED, code)
        self.assertIn("new/worsened", stderr.getvalue())
        self.assertNotIn("budget:", stderr.getvalue())
        self.assertIn("findings", json.loads(stdout.getvalue()))

    def test_level_policy_is_forwarded(self):
        code = main([REPO, *baseline("--format", "sarif", "--level-policy", "advisory")])
        self.assertEqual(EXIT_OK, code)

    def test_include_unchanged_and_all_rules(self):
        code = main([
            REPO, *baseline("--format", "sarif", "--include-unchanged", "--all-rules"),
        ])
        self.assertEqual(EXIT_OK, code)


class TestFailures(unittest.TestCase):
    def test_missing_project_directory_is_a_usage_error(self):
        code = main([os.path.join(WORK, "no-such-project"), *baseline()])
        self.assertEqual(EXIT_USAGE, code)

    def test_calibrate_subcommand_is_dispatched(self):
        output = os.path.join(WORK, "thresholds.yaml")
        code = main([
            "calibrate", REPO, "--min-samples", "999", "--output", output,
        ])
        self.assertEqual(EXIT_OK, code)
        self.assertTrue(os.path.exists(output))
        os.remove(output)
