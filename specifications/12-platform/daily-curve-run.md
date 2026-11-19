# Daily curve run

Spec version 0.1.0 (stage K round 1, lane k-curve-daily, 2026-11-19). Status: implemented in `tools/curve_daily/` on the Python CLI; scheduled by `.github/workflows/curve-daily.yml` from the first run after the round merges; never triggered yet. Rulings KR-90 to KR-107 (`stage-k-rulings-curve.md`, proposed; not normative until the stage K coordinator confirms them). Plan items: 14.8 K-11 (owner decisions 2026-11-18: kept in stage K, runs on GitHub Actions, US public sources only), 14.10 rule 1 (a gate counts as built only when a run shows it failing on a planted fault) and rule 6 (dates checked against the prereg holdout windows). Builds on `04-pricing/bonds.md` (`bond.price.from_yield`, `bond.yield.from_price`, `bond.fit.nelson_siegel`) and `01-core` calendars (`core.calendar.is_business_day`), all unchanged. Reviewer: none: self-assessment; no second review (owner decision 2026-11-18).

**Label on every row:** "fitted to public US Treasury par yields with a library Nelson-Siegel fit; not an official curve". The comparison with the Federal Reserve's curve is labelled **"consistency check, not proof"**.

**Plain idea.** Each US business day, after the Treasury posts its par yield curve, a small job on a free GitHub runner downloads that file, fits a three-factor Nelson-Siegel curve to it with the library's own bond fit, and writes one row: the fitted parameters, how far the fitted curve is from each published yield, the SHA-256 of what it downloaded, and the code commit. Each row carries the hash of the row before it, and the head is stamped outside the repository, so an old row cannot be changed quietly. Days that go wrong are written down as going wrong (a gap, a failed fit, a file that had not been updated yet), never left out. When the Fed later posts its own fitted curve for the same day, a second row compares the two at 1 to 30 years.

**Worked example (measured, local laptop, not the acceptance machine; dry run, nothing pushed).** The very first live dry run (13:36:05 UTC on 2026-11-19) used an unweighted price fit and gave RMSE 31.58 bp, largest error 70.58 bp at 1 month: with equal weights the bills' tiny price errors let their yields drift. The weights `1/MD^2` of KR-98 were added after that one real day was seen. That is a method change made after seeing data, and it is recorded here; the thresholds did not change. Run again at 13:36:47 UTC with `--now` unset, the job found 2026-11-18 due, fetched the Treasury file for the year and the Fed file, and wrote (in dry-run output only) a GENESIS row and one DAY row: `ok`, `on_time`, tau 2.25 years, RMSE 10.58 bp, largest error 17.91 bp at 1 month, so `within_fit_flag` "false" (the flag is 10 bp RMSE). The Fed file then ended at 2026-11-13, so the comparison stayed pending. A second dry run with `--now 2026-11-13T23:45:00Z` fitted 2026-11-13 (tau 1.5, RMSE 10.25 bp, largest 15.91 bp at 20 years) and compared it with the Fed's zero yields: RMSE 17.36 bp, largest 25.71 bp at 22 years, status `outside` the 15 bp RMSE tolerance. Both results stand as measured; the thresholds were committed (commit 7440c936, `tools/curve_daily/config.json`) before either run and are not moved. The wave in the differences (about +18 bp at 7 years, about -26 bp at 22 years) is the shape a three-factor curve cannot follow on a curve with two bends; see Limits.

## Sources and data terms (KR-90)

| Ref | What | Evidence class |
|---|---|---|
| [UST-CSV] | Treasury daily par yield curve file, `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv`, the same URL the recorder uses (`tools/recorder/sources.json`, `us-treasury-par-yields`). | read (repository) |
| [UST-XML] | Treasury "Daily Treasury Rate XML Feed" page, `https://home.treasury.gov/treasury-daily-interest-rate-xml-feed`, read 2026-11-19 through the web-fetch agent: the feed accepts GET requests and documents paging for bulk pulls; it says nothing on automated use limits, copyright or reuse. | read |
| [UST-POL] | Treasury "Site Policies and Notices", `https://home.treasury.gov/subfooter/site-policies-and-notices`, read 2026-11-19: no copyright, reuse or automated-access statement. The URLs `home.treasury.gov/subject/terms-of-use` and `home.treasury.gov/footer/site-policies-and-notices` returned 404 that day. | read |
| [UST-IRS] | Treasury "Interest Rate Statistics", `https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics`, read 2026-11-19: the inputs are indicative quotations obtained by the New York Fed at about 3:30 PM each business day. | read |
| [TY-M] | Treasury yield curve methodology page, as quoted by the sister spec `paper-ledger-daily.md` (read 2026-11-19 by that lane): the par curve is usually available by 6:00 PM Eastern Time each trading day; the method is a monotone convex par curve. | read (repository) |
| [17USC105] | US federal government works have no US copyright (17 USC 105), as the recorder's licence line states; the recorder also notes that usa.gov warns not everything on a federal site is a government work. | read (repository), recalled |
| [FRB-NYC] | Fed Board "The U.S. Treasury Yield Curve: 1961 to the Present", `https://www.federalreserve.gov/data/nominal-yield-curve.htm`, read 2026-11-19: a staff research product, not an official statistical release, subject to delay, revision or method changes without notice; series are generally posted once a week, typically on Tuesday for the period up to the previous Friday. Data file `https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv`. | read |
| [FRB-DIS] | Fed Board disclaimer, `https://www.federalreserve.gov/disclaimer.htm`, read 2026-11-19: unless otherwise indicated, information on the Board's site is in the public domain and may be copied and distributed without permission; the Board asks to be cited as the source; non-Board material may be copyrighted. | read |
| [FRB-ABS] | FEDS 2006-28 abstract page, `https://www.federalreserve.gov/pubs/feds/2006/200628/200628abs.html`, read 2026-11-19: the data files are updated weekly. | read |
| [GSW07] | Gurkaynak, R. S., Sack, B. and Wright, J. H., "The U.S. Treasury yield curve: 1961 to the present", *Journal of Monetary Economics* 54(8), 2007, 2291-2304. The fitted curve uses off-the-run notes and bonds and leaves out bills and the most recent issues. | recalled (not opened) |
| [H20] | `docs/validation/central-bank-consistency.md` (stage H item H-20): the library three-factor Nelson-Siegel fit to the Fed's published zeros on 323 month-ends had median RMSE 3.81 bp, 95th percentile 9.21 bp, maximum 19.99 bp. | measured (repository) |
| [SHA] | NIST FIPS 180-4, SHA-256. | standard, recalled |

**What may be fetched and republished.** No page read permits or forbids automated fetching for either source; both offer machine-readable downloads ([UST-XML], [FRB-NYC]). The Fed's data are public domain with a citation asked for [FRB-DIS]. Treasury's own terms were not found [UST-POL]; the recorder treats the par curve as a federal government work with `redistribute_raw` "believed yes, unconfirmed" [17USC105]. Because Treasury's republication is not confirmed on a Treasury page, this job follows the brief's fallback for both sources: **rows hold only fitted parameters, fit diagnostics, derived fitted zero rates, and input hashes; no source row and no source file is committed, uploaded or printed by the scheduled job.** Downloads stay in the runner's memory. Every row names both sources' attribution (as amended by ruling KR-109: each record carries the attribution of the source whose data it uses, the GENESIS row holds both, and a record that used no source data carries none). This is a reading of published terms, not legal advice. It is consistent with the recorder, which keeps the raw bytes off the repository and publishes parsed Treasury values only because it treats them as public domain; this job publishes less than that.

## Inputs (KR-91, KR-92)

- **Treasury par yields** for business day `D`: the CSV for `D`'s year [UST-CSV]. Thirteen tenors are used, fixed in `tools/curve_daily/config.json`: 1, 2, 3, 4 and 6 months; 1, 2, 3, 5, 7, 10, 20 and 30 years. Any other column (for example a 1.5 month column) is ignored. Values are percent, two decimals, as published. A missing or unreadable cell for one of the thirteen is a failed fit (`E_MISSING_TENOR`, `E_PARSE`), not a smaller fit.
- **Fed GSW file** [FRB-NYC]: columns `SVENY01` to `SVENY30` (continuously compounded zero yields, percent). Read only for the consistency rows.
- **Prereg holdout windows**: `research/holdout_scan.py` `windows()`, the same reader that `research/test_preregs.py` uses.
- **Calendar**: library calendar `USGS` through `core.calendar.is_business_day` (KR-93), as the paper ledger. Early closes are business days.

## The fit (KR-97 to KR-100)

Plain idea: treat each published par yield as a bond that trades at par, and let the library fit a Nelson-Siegel curve to those bond prices.

Formal statement, for business day `D` (settlement `D`; T+1 settlement is not modelled):

1. For each tenor `k`, a par bond `{maturity: D + k months (day clamped to month end), coupon: y_k / 100, frequency: 2}`. `bond.price.from_yield` at yield `y_k / 100` gives `dirty_k`, `accrued_k` and modified duration `MD_k`. For tenors of 6 months and more `dirty_k` is 100; below 6 months the bond has one cash flow and the operation's ACT/ACT ICMA accrual makes `dirty_k` slightly different from 100.
2. Weights `w_k = 1 / MD_k^2`, so the operation's price objective `sum w_k (model_k - dirty_k)^2` is close to the sum of squared yield errors.
3. `bond.fit.nelson_siegel` with these bonds and weights, once for each `tau` in the grid 0.25, 0.5, ..., 10 years (40 values, the H-20 A3 grid [H20]). The chosen `tau` has the lowest objective; ties go to the smaller `tau`. A `tau` whose call fails is listed with its error code; if every `tau` fails, the day is `fit_failed` with the first code.
4. Zero rates: the same operation at the chosen `tau`, with 30 zero-coupon probe bonds (maturity `D + n` years, `n = 1..30`, coupon 0, dirty price 100) added at weight 0. A weight-0 bond does not move the fit (`bonds.md`: "a bond with weight 0 shows its richness"), and its residual is model price minus 100. The job checks that the betas and the 13 residuals are bit-identical to step 3 (else `E_PROBE_MISMATCH`). `z_n = -ln((100 + r_n) / 100) / t_n`, `t_n = days / 365` as in `bonds.md`, in percent: a unit change, not a model.
5. Fit errors: each par bond's model clean price (`dirty_k + residual_k - accrued_k`) goes back through `bond.yield.from_price`; `error_k = (yield_k - y_k / 100) x 10^4` bp. `rmse_bp = sqrt(mean(error_k^2))`, `max_abs_bp` the largest `|error_k|` and `max_at` its tenor (first one on a tie).
6. **Fit flag** (informational, not a gate): `within_fit_flag` is "true" when `rmse_bp <= 10` and `max_abs_bp <= 25`. Reason, fixed before any real-day run: the same three-factor model fitted to the Fed's own smooth curve had a 95th-percentile RMSE of 9.21 bp and a maximum of 19.99 bp [H20], so a daily RMSE above 10 bp is in the tail of what model shape alone gave there; 25 bp is about 2.5 times that RMSE for a single point. Evidence class: inferred from measured.

The job adds no numerical method of its own. Its own arithmetic is: the weights in step 2, the price-to-rate change in step 4, the clean price in step 5, the bp change, the RMSE and the maximum.

**Worked example (synthetic, from the tests).** A day with par yields from a smooth curve (two decimals) fits with 40 of 40 `tau` values succeeding and an RMSE of a few bp; `python/tests/test_curve_daily.py` asserts RMSE below 10 bp for 30 such days.

## Consistency with the Fed's curve (KR-101)

Plain idea: once the Fed posts its fitted curve for the same day, compare the two zero curves at whole years. Agreement shows the job, the conventions and the data agree with an independent fit; disagreement shows by how much they differ. It is a **consistency check, not proof**: neither curve is the truth, they are fitted to different bonds by different models.

Formal statement. For an `ok` DAY row of date `D` and the Fed row of date `D`: `diff_n = (z_n - SVENYn) x 100` bp for `n = 1..30` where the Fed value is present. `rmse_bp`, `max_abs_bp`, `max_at` as above. Status `within` when `rmse_bp <= 15` and `max_abs_bp <= 40`, else `outside`.

**Tolerance and its reason, fixed before any real-day run** (committed in `config.json` at 7440c936 before the first live dry run): three effects add up. (a) Model shape: a three-factor fit to the Fed's own four-factor curve leaves a median 3.81 bp, 95th percentile 9.21 bp and maximum 19.99 bp RMSE [H20], measured. (b) Different inputs: the Treasury par curve rests on indicative quotes for recent issues and bills [UST-IRS], the Fed curve on off-the-run notes and bonds without bills [GSW07]; a few bp, more at the long end, inferred. (c) Par to zero through the fitted model, sub-bp, inferred. 15 bp RMSE allows (a) at its 95th percentile plus (b); 40 bp for one point is twice the largest (a) seen. `outside` is a result, not a fit failure, and is never re-labelled. A day outside the tolerance is written as a `CONSISTENCY` row with status `outside` and kept in the chain like any other row; it is never dropped, skipped or retried until it passes (the verifier's `DIAG` and `VERDICT` checks recompute the status from the stored differences).

**Recorded result before the scheduled runs: a miss.** The one real day tried, 2026-11-13 (dry run of 2026-11-19, local laptop, measured), gave RMSE 17.36 bp, largest 25.71 bp at 22 years: `outside` the 15 bp RMSE tolerance that was fixed beforehand. It is recorded as a miss of the consistency check on the one day tried. It is a consistency check, not proof: it neither shows the job wrong nor would a pass have shown it right. The fit weights (KR-98) were changed once, after one real day had been seen (worked example above); the tolerance and the method have not been changed since, and will not be changed to turn this result into a pass.

Timing: the Fed posts weekly, days behind [FRB-NYC]. A day's comparison stays pending (no row) until the Fed file has that date. It becomes `unavailable` (one row, with the reason) if the Fed file has later dates but not this one, or after 30 calendar days with no Fed row. A fetch failure of the Fed file writes nothing; the next run tries again.

## Row format (KR-102)

Format string `qf-curve-daily/1`. JSON Lines, file `ledger/curves.jsonl` on branch `curve-daily`; `ledger/summary.json` beside it is rewritten by each run (latest fit, counts, head).

| Field | Meaning |
|---|---|
| `seq` | integer from 0 |
| `ts` | UTC time of the run that wrote the row, `YYYY-MM-DDTHH:MM:SSZ` |
| `kind` | `GENESIS` (row 0 only), `DAY`, `GAP`, `CONSISTENCY` |
| `format`, `label` | as above |
| `body` | below |
| `prev`, `hash` | SHA-256 of the previous row (64 zeros for row 0) and of this row's canonical bytes |

Canonical bytes: the row without `hash`, keys sorted at every level, separators `,` and `:`, ASCII; every scalar a string except `seq` (the HR-45 rule of `10-execution/paper-trading.md`, as the paper ledger uses it). A line that repeats a key does not parse. Numbers from the CLI are written as the shortest decimal string that reads back to the same binary64 value.

- `GENESIS`: `config` (all of `config.json`), `config_sha256`. The verifier fails if `config.json` on `main` later differs. Any change of tenors, fit, grid, weights, thresholds, schedule rule or row fields needs a new format string, a ruling and a new ledger; rows of version 1 are never rewritten.
- `DAY`: `date`, `timing` (`on_time` or `late`), `status`, `run` (`commit` of `main`, `contract_version` from the CLI's `version` verb, `impl`). By status:
  - `ok`: `input` (`url`, `sha256` and `bytes` of the downloaded file, `latest_date` in it, `row_date`, `row_sha256` of the day's thirteen values as one text line, `attribution`) and `fit` (`operation`, `weighting`, `tau`, `betas`, `objective`, `taus_ok`, `taus_failed`, `errors_bp` per tenor, `rmse_bp`, `max_abs_bp`, `max_at`, `within_fit_flag`, `zeros_pct` for 1 to 30 years);
  - `fit_failed`: `error` (`code`, `detail`) and `input` as far as it was read; never a `fit`;
  - `stale_input`: `input` with `latest_date` before `date` (the file had not been updated);
  - `fetch_failed`: `input.url`;
  - `holdout_blocked`: `studies` (the prereg ids whose window holds `date`); no input is read.
- `GAP`: `date`, `reason`, `run`.
- `CONSISTENCY`: `date`, `day_row` (hash of the DAY row), `label`, `gsw` (`url`, `sha256`, `bytes`, `last_date`, `fetched_at`, `attribution`), `tolerance_bp`, `status` (`within`, `outside`, `unavailable`), and for the first two `diffs_bp`, `rmse_bp`, `max_abs_bp`, `max_at`; for `unavailable` a `reason`.

## When a day is due, on time, late or a gap (KR-94 to KR-96)

- **Due**: business day `D` is due from 23:00:00 UTC on `D` (6:00 PM Eastern in winter, 7:00 PM in summer; Treasury usually posts by 6:00 PM ET [TY-M]).
- **On time**: a DAY row written no later than 19:30:00 UTC on the next business day, before the next day's 3:30 PM ET input quotes in either daylight regime [UST-IRS]. Otherwise `late`. The verifier recomputes the label from `ts`.
- **Settled**: a date is settled by one DAY row with status `ok`, `fit_failed` or `holdout_blocked`, or by a GAP row. `stale_input` and `fetch_failed` rows do not settle a date; later runs try again. A second settling row for a date fails verification.
- **Late window**: a run may still fit an unsettled date, labelled `late`, until 19:30 UTC on the fifth business day after the date's next business day. After that the run writes a GAP row. **A gap is recorded as a gap and never filled later.**
- **Start**: the first run writes GENESIS and the latest due day only. Nothing is back-filled.
- **Holdout** (plan 14.10 rule 6): before any input is read, each due date is checked against every prereg holdout window; a date inside one gets a `holdout_blocked` row and nothing else. Today every window ends before the first possible run date, so this rule is expected never to fire; it is there for future preregs.
- A run that finds nothing due writes nothing.

## Failures (KR-99, KR-100)

A failed fit is a row with its error code (the CLI's code, for example `E_DOMAIN` or `E_SINGULAR`, or the job's own `E_MISSING_TENOR`, `E_PARSE`, `E_NONFINITE`, `E_PROBE_MISMATCH`), never a dropped day. `run_day.py` exits 2 when it wrote any row with a problem (GAP, `fit_failed`, `stale_input`, `fetch_failed`, `holdout_blocked`); the workflow still pushes the rows and then turns the run red, so GitHub notifies the owner. Exit 1 is a refusal: the existing ledger does not verify, or the new one would not; nothing is written.

## Chain, anchor and verification (KR-103 to KR-105)

The chain is the `prev`/`hash` link. After each push the workflow writes `anchors/<UTC time>.json` (`count`, `head`, `format`, `config_sha256`) on branch `curve-daily-anchors` and stamps it with OpenTimestamps, as `recorder.yml` anchors the forward log (plan 13.2 R4). Before each push every anchor held must still match line `count` of the ledger.

`tools/curve_daily/verify_chain.py verify` stops at the first failure and never repairs:

| Reason | Check | Planted-fault test |
|---|---|---|
| `PARSE`, `SEQ`, `HASH`, `LINK`, `FORMAT`, `LABEL`, `KIND` | chain, row by row | `test_tampered_row_fails` |
| `CONFIG` | genesis configuration equals `config.json` | `test_config_change_fails` |
| `ORDER`, `DUP` | dates never go back; one settling row per date; one consistency row per DAY row | `test_second_settled_row_for_a_day_fails` |
| `HOLDOUT` | no row other than `holdout_blocked` dated inside a window; a `holdout_blocked` row names the windows and read nothing | `test_holdout_date_is_blocked_and_checked` |
| `DATE`, `EARLY`, `TIMING` | business day; not written before due; timing label; no DAY row after the late window | `test_wrong_timing_label_fails`, `test_row_written_before_due_fails` |
| `FAILCODE` | a `fit_failed` row has an error code and no fit | `test_failed_fit_is_recorded_with_its_code` |
| `STALE` | an `ok` row used a file row dated `date` | `test_stale_input_is_recorded_then_retried` |
| `DIAG`, `VERDICT` | RMSE, maximum, fit flag and consistency status recomputed from the stored differences | `test_doctored_diagnostics_fail` |
| `REF` | a consistency row names an earlier `ok` DAY row of its date | (covered by the rechain helper in the tests) |
| `MISSING` | every business day from the first to the last date has a row, and each is settled unless still inside its late window at the last row's time | `test_missing_day_fails` |
| `ANCHOR` | each anchor matches the ledger | `test_anchor_catches_a_rewritten_chain` |

`verify_chain.py rebuild --date D --treasury-file F` refits one day from a saved copy of the Treasury file whose SHA-256 matches the row and requires the whole `fit` object to be equal (`test_fit_is_deterministic_and_rebuilds`). The calendar checks need the CLI; `--no-calendar` skips them and says so in its output.

## Acceptance (plan K-11)

| # | Criterion | Evidence |
|---|---|---|
| C1 | Scheduled run on free public data | `.github/workflows/curve-daily.yml`: two crons, US business days, free public runner, no secret needed; local dry run against the live files (worked example above). Not yet run on a runner. |
| C2 | Hash-chained output | KR-102, KR-103; tamper, rewrite and anchor tests |
| C3 | Dates checked against prereg holdouts | KR-96 holdout rule in the run and the verifier; planted-fault test with an injected window; `research/test_preregs.py` passes on this branch |
| C4 | Each gate shown failing on a planted fault (plan 14.10 rule 1) | the table above; 23 tests in `python/tests/test_curve_daily.py`, including an offline 30-business-day run |

## Limits

- Three-factor Nelson-Siegel only. On both real days tried the fit RMSE was just above 10 bp and the residuals wave with the curve's two bends; a Svensson (four-factor) fit would follow them better, but the library has no Svensson fit operation (it has the Svensson formula only in `tools/validation/cb_consistency.py`, outside the library). No par bootstrap of the Treasury curve exists in the library either (`rates.ois.bootstrap` is for swap quotes). Both are listed for another lane in the handover; this job does not add them.
- Par bonds are a convention: settlement on `D`, no T+1, no day-count difference between bills and coupon securities beyond what `bond.price.from_yield` does, and Treasury's own curve method (monotone convex [TY-M]) is not reproduced.
- Zero rates are compared at `D + n` years on the ACT/365 axis of `bonds.md` against the Fed's values at `n` years; the difference in time is under one day per year of maturity, well under 0.1 bp on these curves (inferred).
- The Fed curve is a staff research product that may be revised or delayed [FRB-NYC]; a comparison uses the file as fetched that day, identified by its SHA-256.
- No raw file is kept anywhere by the scheduled job, so a third party can check the chain and the arithmetic of every row but can refit a day only with their own copy of the Treasury file whose hash matches (Treasury may later revise a value, which then shows as a hash mismatch).
- Python CLI only; the other three builds are not run by this job.
- GitHub may delay scheduled runs and disables schedules after 60 days without repository activity; the late window and the GAP rule record what that costs.
