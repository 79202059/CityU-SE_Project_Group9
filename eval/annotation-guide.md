# Pilot annotation guide (24 findings over 8 commit pairs)

This is the reviewer pack for the eight-pair pilot in `docs/evaluation-baselines.md:122`.
Reviewer M1 works in `eval/pilot-review-preload-m1.csv`; reviewer M5 works from
`eval/labels-m5.csv`. The two are filled independently - do not compare notes until
both are complete, otherwise the agreement (kappa) in the report is meaningless.

## What you are looking at

`eval/pilot-review-preload.csv` lists the 24 findings the delta engine calls *proposed* on
the eight adjacent commit pairs of this repository (NEW plus WORSENED, before review).
Each row is one claim that needs a second opinion: is this finding really new or worse
than the base revision, or is it a false alarm?

Columns: `repo_id,base_sha,head_sha,rule,side,path,symbol,line,occurrence`. `side` says which
revision carries the location (always `head` in this batch); `occurrence` separates two
findings of the same rule at the same location. Rows are in a fixed order - do not sort or
reorder them.

## What to write

Fill the `label` column, one row at a time, with exactly one of:

| label | meaning |
| --- | --- |
| `NEW` | No finding of this rule at this location exists on the base revision. |
| `WORSENED` | It exists on base and the metric now crosses the threshold, or it was already above and grew by more than 20%. |
| `UNCHANGED` | It exists on base and the metric is still inside the same band. |
| `RESOLVED` | It exists on base and is gone on head (cite the base location). |
| `UNCLEAR` | You cannot decide from the diff and the thresholds. Say so; do not guess. |

The band is `docs/EVALUATION_CONTRACT.md:149`: a state change needs a threshold crossing,
or a move of more than 20% while already above the threshold.

Thresholds come from `code_quality_config.yaml` at the package root: Long Method 45 lines,
Primitive Obsession more than 4 primitive parameters (and above 70% of parameters), Long
Parameter List 5, Shotgun Surgery 5 calls over 3 contexts, Improper API Usage 70% ratio
(at least 10 calls, one repeated 3 times), WAC more than 10 significant members, CBO more
than 8, LOC 150 effective code lines, file length 250 meaningful lines, cyclomatic
complexity and branches 10.

## How to check one row

```bash
# the pair, then the file on each side
git diff <base_sha> <head_sha>
git show <base_sha>:<path>
git show <head_sha>:<path>
```

- `symbol` names the function or class when the rule reports one; `line` is the reported
  line, blank when the finding is file-scoped.
- For size-type rules (LOC, file length, Long Method, WAC) count the metric on both sides;
  the definitions are the ones the detector uses, not raw `wc -l`.
- If the same rule fires twice at one location, `occurrence` 1 and 2 are separate claims.

## Ground rules

- Edit only `label` in your own copy. Leave every other column byte-identical.
- Save as UTF-8 with LF line endings and no BOM. `tests/test_pilot_preload.py` guards the
  reviewed copy; keep yours in the same shape and the merge will not surprise you.
- **Do not fill `eval/pilot-review-sheet.csv`.** That file is a blank template with its own
  contract test (`tests/test_repository_evaluation.py::test_blank_review_sheet_covers_the_sample`).
  Add rows only to your working copy.
- Reviewers must not see each other's labels before both are done.

## How the labels are merged

1. M3 (or the designated adjudicator) compares M5's `label_1` with M1's `label_2` per row.
2. Matching definite votes become `final`. Disagreements get an adjudicated `final` state,
   or `EXCLUDED` when the item cannot be settled.
3. The merged file is a UTF-8 CSV with the twelve columns in
   `docs/evaluation-baselines.md:139` -
   `repo_id,base_sha,head_sha,rule,side,path,symbol,line,occurrence,label_1,label_2,final` -
   saved as `eval/labels.csv`.
4. Score it from the package directory:

```bash
python scripts/score_evaluation.py .local-reports/pilot.json --labels ../eval/labels.csv
```

A single annotator cannot be scored: `scripts/score_evaluation.py` raises
`two independent annotations are required` when only one of the two label columns is filled.
