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
| A | every finding of the head revision | upstream `analyze_tree`, no filtering |
| B | findings whose line falls inside a changed hunk | `filter_by_changed_lines` over the same findings |
| Proposed | findings that are new or worse than the base revision | `classify_lifecycle` with the `worsen_detail` judge and fuzzy matching |

B is the obvious cheap fix a reviewer could apply by hand: run the existing tool, then
throw away everything that does not sit on a changed line. It is the baseline the
proposal has to beat, and it is implemented in this repository so the comparison can be
re-run rather than argued about.

## Metric

`irrelevant warning reduction = 1 - median(config) / median(A)`

The median is taken over the pull requests in the dataset, not over findings, so one
huge pull request cannot dominate the result. `scripts/baseline_b.py` prints the three
medians and the two ratios; the JSON form carries every pair.

## How to run

```bash
python scripts/baseline_b.py --dataset ../eval/sample-dataset.csv --format text
python scripts/baseline_b.py --dataset ../eval/sample-dataset.csv --format json --output baseline-comparison.json
```

`eval/sample-dataset.csv` has the columns `repo,base,head`. A `repo` of `.` means the
repository that contains the script, and a trailing `^` on a revision means "its parent",
so a pair can be written as `9580afb^,9580afb`.

## Results on this repository

Eight consecutive commits that touch Python files, measured on 2026-11-27. `touched`
counts the Python files whose lines the diff actually changes; `of` is the number of
Python files in the head revision.

| base | head | A | B | Proposed | touched |
| --- | --- | ---: | ---: | ---: | --- |
| 0de1c1db | 0de1c1db | 302 | 7 | 8 | 4 of 46 |
| 53de1583 | 53de1583 | 308 | 19 | 15 | 6 of 46 |
| e878487e | e878487e | 312 | 4 | 4 | 3 of 48 |
| 9580afb^ | 9580afb | 313 | 1 | 1 | 6 of 48 |
| ba6b5bda | ba6b5bda | 314 | 2 | 1 | 1 of 48 |
| b95e694^ | b95e694 | 315 | 2 | 3 | 1 of 48 |
| b6bd5b3^ | b6bd5b3 | 318 | 4 | 3 | 1 of 48 |
| 747d4b6^ | 747d4b6 | 319 | 1 | 1 | 1 of 49 |

| configuration | median findings | reduction against A |
| --- | ---: | ---: |
| A | 313.5 | - |
| B | 3.0 | 99.0 % |
| Proposed | 3.0 | 99.0 % |

## What the numbers say, and what they do not

1. **The cheap fix already wins on this sample.** B and Proposed have the same median,
   so on small, focused pull requests "filter by changed lines" removes as much noise as
   the full delta engine. The contract's threshold (60 % reduction) is met by both, which
   is exactly why B is the baseline: the proposal has to be justified by the cases where
   the two configurations disagree, not by the aggregate.
2. **They disagree in both directions.** In `0de1c1db` the proposal reports 8 findings
   where B reports 7: a method became worse without its line being edited, so B cannot
   see it (the change is in the metric, not in the text). In `53de1583` B reports 19 and
   the proposal 15: B keeps every finding that happens to sit inside an edited hunk, even
   when that finding existed before the pull request, while the proposal knows the
   fingerprint was already in the baseline.
3. **Only two of eight pull requests move the difference.** Six of the eight pairs are
   within one finding of each other. The aggregate 99.0 % therefore says little about
   quality; the useful evidence is per-pair, which is why the script prints every row.

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
  The numbers measure how much noise is removed, not whether what remains is correct.
- **A single machine and a single run per pair.** Analysis is deterministic, so repeating
  a pair reproduces the same counts; that makes the counts stable but says nothing about
  variance across environments.
- **A is re-computed, not read from a report.** A runs the same detectors as B and the
  proposal, so the three columns share a detector version. Comparing against a report
  produced by a different version would not be meaningful.

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
