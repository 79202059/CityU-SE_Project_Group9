"""Guard the preload sheet that supports the eight-pair pilot review."""

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRELOAD = ROOT / "eval/pilot-review-preload.csv"
BLANK = ROOT / "eval/pilot-review-sheet.csv"
STATES = {"head", "base"}


def _rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, strict=True))


def test_preload_covers_every_pilot_pair():
    pairs = {
        (row["base_sha"], row["head_sha"])
        for row in _rows(BLANK)
    }
    rows = _rows(PRELOAD)
    assert rows
    assert {(row["base_sha"], row["head_sha"]) for row in rows} == pairs


def test_every_preload_row_is_a_usable_location():
    for row in _rows(PRELOAD):
        assert row["rule"].startswith("pyex-")
        assert row["side"] in STATES
        assert row["path"] and not row["path"].startswith("/")
        assert re.fullmatch(r"[0-9a-f]{40}", row["base_sha"])
        assert re.fullmatch(r"[0-9a-f]{40}", row["head_sha"])
        if row["line"]:
            assert row["line"].isdigit() and int(row["line"]) >= 1
        assert row["occurrence"].isdigit() and int(row["occurrence"]) >= 1


def test_labels_stay_blank_for_the_reviewers():
    for row in _rows(PRELOAD):
        assert row["label"] == ""


def test_occurrence_is_unique_per_location():
    seen = set()
    for row in _rows(PRELOAD):
        key = (row["base_sha"], row["head_sha"], row["rule"], row["side"], row["path"],
               row["symbol"], row["line"], row["occurrence"])
        assert key not in seen
        seen.add(key)


def test_preload_is_plain_lf_without_bom():
    blob = PRELOAD.read_bytes()
    assert not blob.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in blob
    assert blob.endswith(b"\n")
