# Baseline comparison for the reviewer-facing task

`EVALUATION_CONTRACT.md` section 4 names two baselines and one proposed configuration,
but only the definitions existed: there was no script that produced the numbers. This
document records the missing implementation (`scripts/baseline_b.py`), the sample
dataset it runs on (`eval/sample-dataset.csv`), and the measurements it produced.

The task under test is the one in contract section 2: *find the smells that this pull
request introduces or worsens, and stay quiet about the debt that was already there*.
Nothing here measures precision or recall; those need the labelled corpus, which is a
separate deliverable (see *What is still missing*).

## The three configurations

| id | what it shows a reviewer | how it is produced |
| --- | --- | --- |
| A | every finding of the head revision | `--upstream-archive` runs the published v0.3.0 source in a separate Python process |
| B | findings whose line falls inside a changed hunk | `filter_by_changed_lines` over the same findings |
| Proposed | findings that are new or worse than the base revision | `classify_lifecycle` with the `worsen_detail` judge and fuzzy matching |

B is the obvious cheap fix a reviewer could apply by hand: run the existing tool, then
throw away everything that does not sit on a changed line. It is the baseline the
proposal has to beat, and it is implemented in this repository so the comparison can be
re-run rather than argued about.

## Metric

`display-volume reduction = 1 - median(config) / median(A)`

The median is taken over the pull requests in the dataset, not over findings, so one
huge pull request cannot dominate the result. `scripts/baseline_b.py` prints the three
medians and the two ratios. The JSON form carries every pair and reports recall
as `null` until labels are evaluated. The frozen contract permits a claim about
irrelevant warnings only at recall ≥ 0.85. A zero median A makes the ratio
undefined (`null`). An unreadable diff aborts the run with exit code 2 and the
affected revisions. A successful empty diff contributes zero findings to B.

## How to run

Run these commands from `python_smells_detector-main`. Create `.local-reports/` once to save local output. Git ignores that directory.

```bash
mkdir .local-reports
python scripts/baseline_b.py --check-dataset ../eval/sample-dataset.csv --format json
python scripts/baseline_b.py --dataset ../eval/sample-dataset.csv --format text
python scripts/baseline_b.py --dataset ../eval/sample-dataset.csv --format json --details --output .local-reports/sample.json
python scripts/score_evaluation.py .local-reports/sample.json --audit
```

`eval/sample-dataset.csv` has the columns `repo,base,head`. A `repo` of `.` means the
repository containing the current working directory, and a trailing `^` means "its parent",
so a pair can be written as `9580afb^,9580afb`.

For a spreadsheet export, use a UTF-8 CSV (a BOM is supported). With a header,
the reader selects `repo` (or `repository`), `base` and `head` by name in any
order and allows other columns such as `pr` and `selection_date`. Without a
header it reads the first three fields as `repo,base,head`. Empty lines and
comment lines beginning with `#` between records are skipped.

Both commands validate the whole CSV before analysis. A missing value, a
malformed row or a repeated `(repo, base, head)` triple stops the batch with
exit code 2 and identifies the offending record. `--check-dataset` counts the
distinct repository path strings and writes its summary to stdout. Resolving
Git refs and checking out the snapshots happens during `--dataset`. The team
checks the sample membership and annotations against the frozen contract.

## Results on this repository

The following historical counts were published in `c4a97cd` on 2026-11-27.
`touched` counts Python paths with head-side changed lines. `of` counts distinct
paths appearing in the head findings.

| base | head | A | B | Proposed | touched |
| --- | --- | ---: | ---: | ---: | --- |
| 0de1c1db^ | 0de1c1db | 302 | 7 | 8 | 4 of 46 |
| 53de1583^ | 53de1583 | 308 | 19 | 15 | 6 of 46 |
| e878487e^ | e878487e | 312 | 4 | 4 | 3 of 48 |
| 9580afb^ | 9580afb | 313 | 1 | 1 | 6 of 48 |
| ba6b5bda^ | ba6b5bda | 314 | 2 | 1 | 1 of 48 |
| b95e694^ | b95e694 | 315 | 2 | 3 | 1 of 48 |
| b6bd5b3^ | b6bd5b3 | 318 | 4 | 3 | 1 of 48 |
| 747d4b6^ | 747d4b6 | 319 | 1 | 1 | 1 of 49 |

| configuration | median findings | reduction against A |
| --- | ---: | ---: |
| A | 313.5 | - |
| B | 3.0 | 99.0 % |
| Proposed | 3.0 | 99.0 % |

## What the numbers say, and what they do not

B and Proposed each displayed a median of 3 findings against A's 313.5. Counts
differ in five of the eight pairs, in both directions. For `53de1583`, B displayed
19 findings and Proposed displayed 15. Determining which findings were relevant
requires reviewing individual results against independent labels.

For results with the current worsening boundary, see the [NFR evidence index](nfr-evidence.md).

## Limitations

- **One repository, eight commits.** These are the commits of this project, chosen for
  convenience, not a random sample of Python pull requests. Contract section 3.2 asks for
  68 pull requests across six repositories; that dataset is not in the repository yet.
- **No rename or move in the sample.** The two configurations mainly differ on three
  cases: a metric crossing a threshold without a text edit, a moved or renamed symbol,
  and a finding that sits inside an edited hunk but predates the pull request. Only the
  first and third appear in these eight commits, so the fuzzy matching path is not
  exercised by this measurement.
- **No ground truth.** Nothing here says whether a reported finding is a true positive.
  The numbers measure the change in report volume. Recall and F1 are unmeasured.
- **A single machine and a single run per pair.** Analysis is deterministic, so repeating
  a pair reproduces the same counts; that makes the counts stable but says nothing about
  variance across environments.
- The earlier sample runs used the detectors in the working tree for A and B. `--upstream-archive` records the released detector revision and its scan diagnostics.

## Reproduce the controlled cases

`python scripts/replay_local_cases.py > .local-reports/local-cases.json` checks 24 source-defined cases across five rules using the default configuration. Each case runs in a disposable Git repository. Exit code 1 identifies a mismatch in the expected state, rule, revision side, location or number of focal findings. The JSON output contains the expected and observed records. This supplementary suite is separate from the historical frozen corpus.

## Score independently reviewed findings

For the eight-pair pilot, give each reviewer their own copy of the [blank review sheet](../../eval/pilot-review-sheet.csv). Review `git diff <base_sha> <head_sha>` for each pair. Keep both original sheets, reconcile unmatched observations and enter the adjudicated results in the CSV format below.

From the package directory, use the following commands with the team's independent annotations. Keep the real PRs and the controlled mutation corpus in separate runs. Use a second detailed export with `--config` for the calibrated-threshold comparison. Download the source ZIP for commit `838b212fafe9b1ff1e06c3364892e53177dab16f` to `upstream.zip` outside the measured repositories and pass its path. The exporter verifies SHA-256 `e5b0431ac2129e22dfc774de15e91eca415214954b1654b93753516e55cbbe4c`, then runs A and B with the same interpreter, dependencies, effective thresholds and ignored directories as Proposed. [Upstream release tag](https://github.com/KarthikShivasankar/python_smells_detector/releases/tag/v0.3.0) · [Exact source ZIP](https://codeload.github.com/KarthikShivasankar/python_smells_detector/zip/838b212fafe9b1ff1e06c3364892e53177dab16f)

```bash
python scripts/baseline_b.py --dataset ../eval/dataset.csv --upstream-archive /path/to/upstream.zip --format json --details --output .local-reports/real.json
python scripts/score_evaluation.py .local-reports/real.json --audit
python scripts/score_evaluation.py .local-reports/real.json --labels ../eval/labels.csv
python scripts/baseline_b.py --dataset corpus-pairs.csv --upstream-archive /path/to/upstream.zip --format json --details --output .local-reports/corpus.json
python scripts/score_evaluation.py .local-reports/corpus.json --corpus corpus-labels.csv
```

The exporter resolves the requested revisions to commit IDs before reading the diff or checking out the trees. It records the configuration digest, every head finding shown by A and B, and all four Proposed states. The Proposed display count includes NEW and WORSENED. The three counts and four lifecycle totals are checked on scoring. A and B have no state classifier, so their per-state output is `null`. Both still receive actionable precision, recall and F1 based on the findings they show reviewers.

Use a UTF-8 CSV copy of the team sheet with these columns. Preserve the independent labels, original selection and exclusions when adapting column names. Review the diff independently before joining labels to predictions. Include manually identified findings that all three tools missed.

```csv
repo_id,base_sha,head_sha,rule,side,path,symbol,line,occurrence,label_1,label_2,final
```

- `repo_id` is the exact repository token in the pair manifest. Use full commit IDs. Use the registry's `rule` ID and a `/`-separated path relative to the identified revision. Use `base` for a resolved finding and `head` for all other states. For a moved finding use its head location. Cross-file findings use the detector's ordered paths joined by `, `. Leave `line` blank for findings with no line.
- `occurrence` starts at 1 among identical rule, side, path, symbol and line combinations. This preserves multiplicity at a location. Explicitly annotate additional real occurrences. Extra unmatched predictions count as false positives.
- Both independent labels use the four lifecycle states or `unclear`. Matching definite votes supply the final label. For disagreements, record the adjudicated `final` state or `EXCLUDED`. An excluded item is omitted from adjudicated metrics and remains in the pre-adjudication agreement calculation for the five focal smells. The report includes separate actionable scores for each annotator, omitting that annotator's `unclear` items.
- For a fully reviewed pair with zero ground-truth findings, use one row with its three identifiers, `EMPTY` in `final` and blank remaining fields. A missing PR aborts scoring. Verify the manifest's membership against the frozen 68 PRs separately.
- For the controlled corpus, replace the three annotation columns with `expected,mutation`. Map the frozen commit to its parent and head and retain its expected focal records. Mutation values are `introduce`, `worsen`, `move`, `rename`, `resolve`, `cosmetic`. Check the 24 commits and the six pure moves/renames against the original manifest. The move baseline treats a displayed B finding on a labelled moved item as a false new alert. The numerator counts Proposed `NEW` on those same items.

Each PR has equal weight in the macro averages. A zero denominator produces `null` and the output reports the number of PRs contributing to each metric. The 95% interval uses 1,000 reproducible PR-level bootstrap resamples. Cohen's κ uses the five focal rules before adjudication and counts even paired `unclear` votes as disagreement. Volume reduction qualifies as irrelevant-warning reduction only when that configuration's labelled recall reaches 0.85 and the baseline median is positive. Lifecycle accuracy is calculated on matched focal records in the controlled corpus.

## What is still missing

- **The labelled corpus** (`eval/corpus/manifest.csv`, 24 commits with expected states)
  and **the pull request dataset** (`eval/dataset.csv`, 68 pull requests). Both are
  deliverables of the evaluation owner (M1) in `Group9-Scrum/EVALUATION_CONTRACT.md`
  section 3, and both are needed for recall, precision and F1.
- **Two independent annotations plus an arbiter** (contract section 7). Anything measured
  by one person on this repository is a smoke test, not evidence.
- **The contract measurement environment** (Python 3.13, 8 logical cores, 16 GB, three
  runs). This measurement ran on CPython 3.14.7 with 32 cores, so the timings in
  `docs/nfr-evidence.md` are not contract timings either.
