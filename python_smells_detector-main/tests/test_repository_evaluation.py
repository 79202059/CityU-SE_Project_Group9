"""Exercise the case runner and verify the blank review input from the source manifest."""

import csv
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_replay_checks_the_actual_classification(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "python_smells_detector-main/scripts"))
    import replay_local_cases as runner

    cases = list(runner.cases())
    mix = {"introduce": 8, "worsen": 4, "rename": 3, "move": 3, "resolve": 4, "cosmetic": 2}
    assert Counter(kind for kind, *_ in cases) == mix
    assert len({(after or before).rule for _, before, after, _ in cases}) == 5
    # Exercise the Git and detector path for one case. The CLI replays the full matrix.
    moved = next(case for case in cases if case[0] == "move")
    monkeypatch.setattr(runner, "cases", lambda: [moved])
    report = runner.replay(tmp_path)
    row, = report["results"]
    assert row["observed"] == [row["expected"]]
    assert row["expected"]["state"] == "UNCHANGED"
    assert report["exact"] == report["cases"] == 1


def test_blank_review_sheet_covers_the_sample():
    with (ROOT / "eval/sample-dataset.csv").open(encoding="utf-8", newline="") as handle:
        pairs = list(csv.DictReader(line for line in handle if not line.startswith("#")))
    with (ROOT / "eval/pilot-review-sheet.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, strict=True))
    assert len(rows) == len(pairs) == 8
    for row, pair in zip(rows, pairs):
        assert row["repo_id"] == pair["repo"] and row["head_sha"].startswith(pair["head"])
        assert all(re.fullmatch(r"[0-9a-f]{40}", row[k]) for k in ("base_sha", "head_sha"))
        assert all(v == "" for k, v in row.items() if k not in ("repo_id", "base_sha", "head_sha"))
