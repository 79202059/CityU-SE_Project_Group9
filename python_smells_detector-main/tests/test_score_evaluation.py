import csv
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/score_evaluation.py"
spec = importlib.util.spec_from_file_location("score_evaluation", SCRIPT)
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)


def finding(symbol, state=None):
    return {"rule": "pyex-code-large-class", "side": "base" if state == "RESOLVED" else "head",
            "path": "m.py", "line": 1, "symbol": symbol, "state": state}


def pair(head, upstream, proposed):
    return {"repo_id": ".", "base_sha": "0"*40, "head_sha": head*40,
            "counts": {"A": len(upstream), "B": len(upstream),
                       "proposed": sum(f["state"] in scorer.ACTIONABLE for f in proposed)},
            "lifecycle": {s.lower(): sum(f["state"] == s for f in proposed) for s in scorer.STATES},
            "details": {"A": upstream, "B": list(upstream), "proposed": proposed}}


def write_rows(path, rows, corpus=False):
    header = [*scorer.PAIR_COLUMNS, *scorer.LOCATION, "occurrence"]
    header.extend(["expected", "mutation"] if corpus else ["label_1", "label_2", "final"])
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def test_scores_duplicate_predictions_false_negative_and_empty_pr(tmp_path):
    pre = [".", "0"*40, "1"*40]
    rule = "pyex-code-large-class"
    path = tmp_path / "labels.csv"
    write_rows(path, [pre + [rule, "head", "m.py", "C", 1, 1, "new", "new", ""],
                      pre + [rule, "head", "m.py", "D", 1, 1, "worsened", "new", "worsened"],
                      pre + [rule, "head", "m.py", "E", 1, 1, "unclear", "unclear", "excluded"],
                      [".", "0"*40, "2"*40] + [""]*8 + ["EMPTY"]])
    report = {"pairs": [pair("1", [finding("C"), finding("C"), finding("E")], [finding("C", "NEW")]),
                        pair("2", [], [])]}
    result = scorer.score(report, path)
    proposed = result["overall"]["proposed"]
    assert proposed["actionable"]["recall"] == .5
    assert proposed["actionable"]["f1"] == pytest.approx(2/3)
    assert proposed["actionable"]["f1_prs"] == 1
    assert proposed["states"]["WORSENED"]["fn"] == 1
    assert proposed["irrelevant_warning_reduction"] is None
    assert proposed["f1_ci95"] == pytest.approx([2/3, 2/3])
    assert result["overall"]["B"]["actionable"]["fp"] == 1
    assert result["agreement"] == {"items": 3, "agreements": 1, "kappa": 1/7}
    assert result["excluded"] == 1 and len(result["per_annotator"]) == 2
    assert len(result["per_pr"]) == 2 and result["by_repo"]["."]["A"]["states"] is None
    with pytest.raises(ValueError, match="coverage mismatch"):
        scorer.score({"pairs": report["pairs"][:1]}, path)


def test_corpus_move_uses_head_location_and_counts_false_new(tmp_path):
    path = tmp_path / "manifest.csv"
    item = finding("Renamed", "UNCHANGED")
    location = [item[k] for k in scorer.LOCATION]
    write_rows(path, [[".", "0"*40, "1"*40, *location, 1, "unchanged", "rename"]], corpus=True)
    report = {"pairs": [pair("1", [finding("Renamed")], [item])]}
    result = scorer.score(report, path, corpus=True)["mutation"]
    assert result["accuracy"] == 1 and result["move_false_new_reduction"] == 1
    assert result["move_false_new"] == {"A": 1, "B": 1, "proposed": 0}


def test_cli_rejects_missing_details_and_unadjudicated_disagreement(tmp_path, capsys):
    labels = tmp_path / "labels.csv"
    report = tmp_path / "report.json"
    row = [".", "0"*40, "1"*40, "pyex-code-large-class", "head", "m.py", "C", 1, 1, "new", "unclear", ""]
    payload = pair("1", [], [])
    for decision, why in [("", "adjudicated"), ("new", "details")]:
        if decision:
            del payload["details"]
        report.write_text(json.dumps({"pairs": [payload], "summary": {"pairs": 1, "median": payload["counts"]}}),
                          encoding="utf-8")
        row[-1] = decision
        write_rows(labels, [row])
        assert scorer.main([str(report), "--labels", str(labels)]) == 2
        out, err = capsys.readouterr()
        assert not out and why in err


def test_zero_denominators_and_inconsistent_counts():
    assert scorer.agreement_stats([])["kappa"] is None
    assert scorer.agreement_stats([("NEW", "NEW")])["kappa"] is None
    run = pair("1", [], [])
    run["counts"]["A"] = 1
    with pytest.raises(ValueError, match="detail count"):
        scorer.predictions(run)


def test_audit_rejects_equal_counts_with_different_baseline_findings():
    run = pair("a", [finding("One")], [])
    report = {"pairs": [run], "summary": {"pairs": 1, "median": run["counts"]}}
    assert scorer.audit_details(report)["prs"] == 1
    run["details"]["B"] = [finding("Two")]
    with pytest.raises(ValueError, match="absent from A"):
        scorer.audit_details(report)
