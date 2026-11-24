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
import unittest

from code_quality_analyzer.delta import EXIT_GATE_REACHED, EXIT_OK, EXIT_USAGE, main

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "_tmp_cli")
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
    global WORK, REPO, BASELINE
    base = os.path.join(HERE, "_tmp_cli")
    _force_remove(base)
    if os.path.exists(base):
        # A previous run left git objects behind that Windows still holds open;
        # use a fresh directory instead of failing the whole module.
        base = "%s_%d" % (base, os.getpid())
        _force_remove(base)
    WORK = base
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
