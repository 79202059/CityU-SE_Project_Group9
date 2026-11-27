"""Score detailed baseline exports against independently reviewed PR or mutation labels."""

import argparse
import csv
import json
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

STATES = ("NEW", "WORSENED", "UNCHANGED", "RESOLVED")
ACTIONABLE = {"NEW", "WORSENED"}
CONFIGS = ("A", "B", "proposed")
FOCAL = {"pyex-code-long-method", "pyex-code-large-class", "pyex-code-duplicate-code",
         "pyex-arch-cyclic-dependency", "pyex-struct-high-cyclomatic-complexity"}
PAIR_COLUMNS = ("repo_id", "base_sha", "head_sha")
LOCATION = ("rule", "side", "path", "symbol", "line")


def pair_key(row):
    repo, base, head = (row[key] for key in PAIR_COLUMNS)
    if not repo or not all(re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", sha) for sha in (base, head)):
        raise ValueError("expected repository ID and full base/head commit IDs")
    return repo, base, head


def location(record):
    rule, side, path, symbol, line = (record[k] for k in LOCATION)
    if not rule or not path or side not in {"head", "base"}:
        raise ValueError("expected a rule, path and revision side")
    if line not in (None, "") and (not str(line).isdecimal() or int(line) < 1):
        raise ValueError("expected a positive line number or an empty field")
    return rule, side, path, symbol, int(line) if line else 0


def predictions(pair):
    """Validate the export, retaining multiplicity even at identical source locations."""
    out = {}
    for config in CONFIGS:
        records = pair["details"][config]
        indexed = {}
        occurrences = Counter()
        states = Counter()
        for record in records:
            key = location(record)
            state = record["state"]
            if config == "proposed":
                if state not in STATES or (state == "RESOLVED") != (key[1] == "base"):
                    raise ValueError("invalid Proposed state or revision side")
            elif state is not None or key[1] != "head":
                raise ValueError("baseline findings must be unclassified head findings")
            occurrences[key] += 1
            indexed[(*key, occurrences[key])] = state or "SHOWN"
            states[state] += 1
        shown = sum(states[s] for s in ACTIONABLE) if config == "proposed" else len(records)
        if shown != pair["counts"][config]:
            raise ValueError(f"{config} detail count differs from summary")
        if config == "proposed" and any(states[s] != pair["lifecycle"][s.lower()] for s in STATES):
            raise ValueError("lifecycle counts differ from details")
        out[config] = indexed
    return out


def audit_details(report):
    rows = []
    seen = set()
    for pair in report["pairs"]:
        key = pair_key(pair)
        if key in seen:
            raise ValueError(f"duplicate resolved commit pair {key}")
        seen.add(key)
        indexed = predictions(pair)
        if not indexed["B"].keys() <= indexed["A"].keys():
            raise ValueError("Baseline B contains findings absent from A")
        row = {**dict(zip(PAIR_COLUMNS, key)), "counts": pair["counts"],
               "detail_rows": {config: len(items) for config, items in indexed.items()}}
        if "upstream_commit" in pair:
            row.update(upstream_commit=pair["upstream_commit"], upstream_errors=pair["upstream_errors"],
                       config_digest=pair["config_digest"])
        rows.append(row)
    if not rows:
        raise ValueError("no commit pairs in the export")
    medians = {c: statistics.median(r["counts"][c] for r in rows) for c in CONFIGS}
    if report["summary"]["pairs"] != len(rows) or report["summary"]["median"] != medians:
        raise ValueError("export medians or sample size differ from the pair details")
    return {"pairs": rows, "medians": medians, "prs": len(rows)}


def read_labels(path, *, corpus=False):
    fields = {*PAIR_COLUMNS, *LOCATION, "occurrence"}
    fields.update(("mutation", "expected") if corpus else ("label_1", "label_2", "final"))
    by_pair = defaultdict(dict)
    empty = set()
    agreement = []
    mutations = {}
    individual = [defaultdict(dict), defaultdict(dict)]
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        header = reader.fieldnames or []
        if len(header) != len(set(header)) or not fields.issubset(header):
            raise ValueError(f"{path}: expected unique columns including {', '.join(sorted(fields))}")
        for row in reader:
            try:
                if None in row or None in row.values():
                    raise ValueError("row width differs from the header")
                row = {k: v.strip() for k, v in row.items()}
                pair = pair_key(row)
                truth = by_pair[pair]
                if corpus:
                    mutation = row["mutation"].lower()
                    if mutation not in {"introduce", "worsen", "move", "rename", "resolve", "cosmetic"}:
                        raise ValueError("unknown mutation")
                    if mutations.setdefault(pair, mutation) != mutation:
                        raise ValueError("multiple mutations for the same commit pair")
                state = row["expected" if corpus else "final"].upper()
                if state == "EMPTY":
                    if truth or pair in empty or any(row[k] for k in (*LOCATION, "occurrence")):
                        raise ValueError("EMPTY requires one row without a finding")
                    if not corpus and (row["label_1"], row["label_2"]) != ("", ""):
                        raise ValueError("EMPTY requires blank annotation fields")
                    empty.add(pair)
                    continue
                key = (*location(row), int(row["occurrence"] or "1"))
                if key[-1] < 1 or key in truth or pair in empty:
                    raise ValueError("duplicate, invalid or contradictory label")
                if corpus:
                    if state not in STATES or key[0] not in FOCAL:
                        raise ValueError("expected one of the four states for a focal rule")
                else:
                    votes = (row["label_1"].upper(), row["label_2"].upper())
                    if any(v not in (*STATES, "UNCLEAR") for v in votes):
                        raise ValueError("two independent annotations are required")
                    if votes[0] == votes[1] and votes[0] in STATES:
                        if state and state != votes[0]:
                            raise ValueError("final state contradicts annotator agreement")
                        state = votes[0]
                    if state not in (*STATES, "EXCLUDED"):
                        raise ValueError("record an adjudicated state or EXCLUDED")
                    if key[0] in FOCAL:
                        agreement.append(votes)
                    for rows, vote in zip(individual, votes):
                        rows[pair][key] = vote
                if state in STATES and (state == "RESOLVED") != (key[1] == "base"):
                    raise ValueError("use the base location for RESOLVED and head for other states")
                truth[key] = state
            except (ValueError, KeyError) as exc:
                raise ValueError(f"{path}:{reader.line_num}: {exc}") from exc
    return by_pair, agreement, mutations, individual


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def agreement_stats(votes):
    n = len(votes)
    left = Counter(a for a, _ in votes)
    right = Counter(b for _, b in votes)
    # UNCLEAR is always disagreement, including two UNCLEAR votes. Treat each
    # annotator's UNCLEAR as a distinct category in the chance calculation too.
    matches = sum(a == b and a != "UNCLEAR" for a, b in votes)
    chance = sum(left[s] * right[s] for s in STATES)
    return {"items": n, "agreements": matches, "kappa": ratio(matches*n - chance, n*n - chance)}


def pr_scores(actual, predicted):
    tp = len(actual & predicted)
    fp, fn = len(predicted) - tp, len(actual) - tp
    return {"tp": tp, "fp": fp, "fn": fn, "precision": ratio(tp, tp + fp),
            "recall": ratio(tp, tp + fn), "f1": ratio(2*tp, 2*tp + fp + fn)}


def aggregate(rows):
    result = {"prs": len(rows), **{k: sum(row[k] for row in rows) for k in ("tp", "fp", "fn")}}
    for metric in ("precision", "recall", "f1"):
        values = [row[metric] for row in rows if row[metric] is not None]
        result[metric] = statistics.mean(values) if values else None
        result[metric + "_prs"] = len(values)
    return result


def bootstrap(rows):
    """95% percentile interval from 1,000 PR-level resamples, including empty PRs."""
    rng = random.Random(0)
    values = []
    for _ in range(1000):
        sample = [r["f1"] for r in rng.choices(rows, k=len(rows)) if r["f1"] is not None]
        if sample:
            values.append(statistics.mean(sample))
    values.sort()
    return [values[round(q*(len(values)-1))] for q in (.025, .975)] if values else None


def score(report, label_path, *, corpus=False):
    labels, votes, mutations, individual = read_labels(label_path, corpus=corpus)
    pairs = {}
    for pair in report["pairs"]:
        key = pair_key(pair)
        if key in pairs:
            raise ValueError(f"duplicate resolved commit pair {key}")
        pairs[key] = pair
    if not pairs or pairs.keys() != labels.keys():
        raise ValueError(f"PR coverage mismatch: {len(pairs.keys()-labels.keys())} without labels, "
                         f"{len(labels.keys()-pairs.keys())} without predictions; at least one PR is required")
    per_pr = []
    reviewer_scores = [{config: [] for config in CONFIGS} for _ in individual]
    moved = Counter()
    matched = correct = excluded = 0
    for key, pair in pairs.items():
        truth = labels[key]
        skip = {k for k, v in truth.items() if v == "EXCLUDED"}
        excluded += len(skip)
        row = {**dict(zip(PAIR_COLUMNS, key)), "configurations": {}}
        for config, raw_guesses in predictions(pair).items():
            guesses = {k: v for k, v in raw_guesses.items() if k not in skip and (not corpus or k[0] in FOCAL)}
            relevant = {k for k, v in truth.items() if v in ACTIONABLE}
            shown = {k for k, v in guesses.items() if v in ACTIONABLE or v == "SHOWN"}
            if not corpus:
                # Restore excluded items for each annotator's independent result.
                raw_shown = {k for k,v in raw_guesses.items() if v in ACTIONABLE or v == "SHOWN"}
                for review, totals in zip(individual, reviewer_scores):
                    annotations = review[key]
                    uncertain = {k for k,v in annotations.items() if v == "UNCLEAR"}
                    accepted = {k for k,v in annotations.items() if v in ACTIONABLE}
                    totals[config].append(pr_scores(accepted, raw_shown - uncertain))
            results = {"actionable": pr_scores(relevant, shown), "states": None}
            if config == "proposed":
                results["states"] = {s: pr_scores({k for k, v in truth.items() if v == s},
                                                  {k for k, v in guesses.items() if v == s}) for s in STATES}
                common = guesses.keys() & truth.keys()
                matched += len(common)
                correct += sum(guesses[k] == truth[k] for k in common)
            if mutations.get(key) in {"move", "rename"}:
                moved[config] += sum(guesses.get(k) in {"NEW", "SHOWN"} for k,v in truth.items() if v == "UNCHANGED")
            row["configurations"][config] = results
        per_pr.append(row)

    def summary(rows):
        result = {}
        for config in CONFIGS:
            entries = [r["configurations"][config] for r in rows]
            items = [e["actionable"] for e in entries]
            result[config] = {"actionable": aggregate(items), "states": None,
                              "f1_ci95": bootstrap(items)}
            if config == "proposed":
                result[config]["states"] = {s: aggregate([e["states"][s] for e in entries]) for s in STATES}
        return result

    overall = summary(per_pr)
    for config in CONFIGS:
        recall = overall[config]["actionable"]["recall"]
        med = statistics.median(p["counts"][config] for p in pairs.values())
        base = statistics.median(p["counts"]["A"] for p in pairs.values())
        overall[config]["irrelevant_warning_reduction"] = (
            1 - med / base if not corpus and base and recall is not None and recall >= .85 else None)
    result = {"prs": len(pairs), "excluded": excluded, "overall": overall, "per_pr": per_pr,
              "by_repo": {repo: summary([r for r in per_pr if r['repo_id'] == repo])
                          for repo in sorted({p[0] for p in pairs})}}
    if corpus:
        result["mutation"] = {"matched": matched, "correct": correct, "accuracy": ratio(correct, matched),
                              "move_commits": sum(m in {"move", "rename"} for m in mutations.values()),
                              "move_false_new": dict(moved),
                              "move_false_new_reduction": ratio(moved["B"]-moved["proposed"], moved["B"])}
    else:
        result["agreement"] = agreement_stats(votes)
        result["per_annotator"] = [{config: aggregate(rows) for config, rows in totals.items()}
                                   for totals in reviewer_scores]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="baseline_b.py --format json --details output")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--labels", type=Path)
    group.add_argument("--corpus", type=Path)
    group.add_argument("--audit", action="store_true", help="reconcile detailed rows and counts for an unlabelled export")
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8-sig"))
        audit = audit_details(report)
        result = audit if args.audit else score(report, args.labels or args.corpus, corpus=args.corpus is not None)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
