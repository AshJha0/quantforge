# Deviation note: R3 holdout-period data downloaded and published

Status: **signed**. Signed by Claude (signing delegated by the owner, 2026-11-07; owner decision D2 of the 2026-11-12 review keeps the holdout dates and discloses) on 2026-11-12.
- SHA-256 of the body below the marker line: recorded in amendment 2 of each R3 study (a file cannot carry its own hash in its body; the header is outside the hashed part).
- This file is not edited after signing; a later correction is a new note.

<!-- body -->
Date: 2026-11-12. Source: finding 1 of `QUANTFORGE_REVIEW_2026-11-12.md` (outside this repository). Reproduced on 2026-11-12 by `python research/holdout_scan.py` on branch `r6-research`, forward log at `origin/forward-log` commit `b33f784`.

## What the preregs said

All six signed R3 files (three preregs, three amendments 1) say: "Holdout data has not been read, downloaded or summarised. No study data of any period has been downloaded at signing." That was true when the three preregs were signed on 2026-11-07 for parsed values, but not for raw files, and it was false for amendment 1, signed 2026-11-09.

Holdout windows (from the preregs): R3-01 2013-01-02 to 2026-10-30; R3-02 2023-01-03 to 2026-10-30; R3-03 2016-01-04 to 2026-10-30.

## What happened, with dates

1. 2026-11-07 18:24 UTC, forward-log row 1: the recorder fetched the whole 2026 year-to-date Treasury par-yield file (hash and size only in the log; raw bytes kept on the Actions runner and in the owner's local recorder folder, never committed). Year-to-date files of every source were fetched the same way from then on. **Reproduced** ([lane] claim in the review).
2. 2026-11-09 23:29 UTC, forward-log rows 16, 32, 33, 34: the recorder's new parser published parsed values in the log itself, dated inside the holdout windows (table below). **Reproduced**; row 34 (BLS CPI) was not named in the review.
3. 2026-11-09 23:44 UTC: `reports/2025-12-31/p&l-explain.*` on `forward-log` published daily Treasury curve moves for 2025. **Reproduced** (41 dated rows in the window of R3-01 counted by the scan).
4. Daily SOFR checks on `forward-log` (`reports/2026-11-0*/sofr-check.*`) publish NY Fed 30, 90 and 180-day SOFR averages whose windows start inside the R3-02 holdout. **Reproduced.**
5. Tracked pages on main carry real SOFR fixings and Treasury values from September and October 2026: `examples/real_sofr_compound_2026_10.json`, `docs/curves/data/ois-full.json`, `docs/curves/ois-full.md`, `docs/curves/pnl-explain.md` (2026-10-23 to 2026-11-06). **Reproduced.**

Nobody has computed any study statistic, signal or position on holdout data. The study rows on the forward log all read `position: null`. The values that were seen are general market levels, the kind already disclosed under "Holdout knowledge" in amendment 1.

## Full list (machine-checked)

`research/test_preregs.py` fails if `research/holdout_scan.py` reports a location that is not listed here. Class: **H** = real holdout-period observation of a study input; **S** = synthetic test data or a date that is not an observation (a citation date, a calendar example, a spec version date) caught by the marker rule.

- `forward-log:actions/log.jsonl#row16:us-treasury-par-yields` | R3-01, R3-03 | H | 2026-01-02 to 2026-10-30, 1,045 values
- `forward-log:actions/log.jsonl#row32:us-treasury-bill-rates` | R3-02 | H | 2026-01-02 to 2026-10-30, 627 values
- `forward-log:actions/log.jsonl#row33:us-treasury-real-yields` | R3-03 | H | 2026-01-02 to 2026-10-30, 418 values
- `forward-log:actions/log.jsonl#row34:bls-cpi-u-nsa` | R3-03 | H | 2024-01 to 2026-09, 32 monthly values
- `forward-log:actions/log.jsonl#row78:bls-cpi-u-nsa` | R3-03 | H | 2026-10 (the month overlaps the window end)
- `forward-log:reports/2025-12-31/p&l-explain.json` | R3-01, R3-02 | H | 2025-01-09 to 2025-12-31
- `forward-log:reports/2025-12-31/p&l-explain.md` | R3-01, R3-02 | H | same values as the json
- `forward-log:reports/2026-11-06/sofr-check.json` | R3-02 | H | 180-day average window from 2026-08-06
- `forward-log:reports/2026-11-06/sofr-check.md` | R3-02 | H | same
- `forward-log:reports/2026-11-09/sofr-check.json` | R3-02 | H | window from 2026-08-07
- `forward-log:reports/2026-11-09/sofr-check.md` | R3-02 | H | same
- `forward-log:reports/2026-11-10/sofr-check.json` | R3-02 | H | window from 2026-08-10
- `forward-log:reports/2026-11-10/sofr-check.md` | R3-02 | H | same
- `examples/real_sofr_compound_2026_10.json` | R3-02 | H | SOFR fixings 2026-09-21 to 2026-10-30
- `docs/curves/data/ois-full.json` | R3-02 | H | SOFR fixings 2026-09-21 to 2026-10-30
- `docs/curves/ois-full.md` | R3-02 | H | page built from the json above
- `docs/curves/pnl-explain.md` | R3-01, R3-02 | H | Treasury and SOFR values 2026-10-23 to 2026-10-30
- `datasets/golden/stage_d/compound_d.json` | R3-02 | S | synthetic fixings (for example 4.33% on 2026-10-21, not the published rate)
- `datasets/golden/stage_d/edge_d.json` | R3-02 | S | synthetic or zero fixings; Good Friday calendar dates
- `datasets/golden/stage_d/rulings2_d.json` | R3-02 | S | synthetic fixings
- `datasets/golden/stage_d/rulings_d.json` | R3-02 | S | synthetic case date
- `LEARN.md` | R3-01, R3-02 | S | day-count and calendar examples
- `README.md` | R3-02 | S | a date in prose
- `datasets/data-availability.md` | R3-01, R3-02 | S | month a dataset ends, no values
- `docs/getting-started/tutorial-2-bonds-repo.md` | R3-02 | S | example trade date
- `docs/model-inventory.md` | R3-02 | S | source page date
- `docs/references.md` | R3-02 | S | a vendor site shutdown date
- `specifications/02-curves/overnight-compounding.md` | R3-02 | S | Good Friday dates
- `specifications/edge-case-register.md` | R3-02 | S | calendar and cessation dates
- `specifications/r1-rulings.md` | R3-02 | S | Good Friday date
- `specifications/stage-f-rulings.md` | R3-02 | S | BIS page date
- `tools/recorder/sources.json` | R3-01, R3-02, R3-03 | S | terms-check prose dates

Not in the scan, stated here: raw year-to-date files of every recorder source on the Actions runners (discarded with each run) and in the owner's local folder `qf-recorder/data/recorder` (never committed).

## What changes

- The recorder keeps only observations dated on or after the forward start, 2026-11-10 (`tools/recorder/record.py`, R6-19). The log rows above are append-only and stay; they are disclosed, not deleted.
- Amendment 2 of each study corrects the "not downloaded" sentence and points here.
- New workflow reports and gallery pages use in-sample or forward dates only; `research/test_preregs.py` stops any new holdout-dated observation that is not on this list.
