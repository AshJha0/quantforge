# R3 amendment 6 (shared text for R3-01/02/03): DRAFT, unsigned

Draft for the second read (program/R3_A6_REVIEW.md). On signing, this body goes into research/preregs/R3-0{1,2,3}-amendment-6.md and this file is removed.

<!-- body -->
Amends each of `R3-01-treasury-fly.md`, `R3-02-bill-repo-spread.md` and `R3-03-breakeven-seasonality.md` (one shared text; the file header names the study it amends) and that study's earlier amendments (R3-01: 1 to 5; R3-02 and R3-03: 1 to 4). They stand; where this amendment differs, this amendment governs. Common rules: `README.md`. Source: the stop recorded in `program/R3_NOTES.md` (holdout run, 2026-11-14) and the second read `program/R3_A6_REVIEW.md`.

**Why.** Amendment 3 rules 3 and 4 say the forward-log signal rows are computed, and the back-fill made, "by the script named in the run line". That script is `research/r3_runner.py`. It has no forward-log writer, and its SHA-256 is pinned by the three lines of `research/holdout_runs.csv`, so it cannot gain one without breaking the record of the holdout run. Rule 5 names a check in `research/holdout_scan.py` that does not exist. Both are fixed here by naming a separate writer and the check. This amendment is about where and how the forward-log signal fields are written. It changes no verdict, no holdout number and no frozen output.

**State at signing.** All three holdout runs are done and logged: run lines in `research/holdout_runs.csv` (committed in 22d0c92, `utc_date` 2026-11-14, runner SHA-256 `f45ce97f...`, freeze commit faadaa4), results in `research/r3/holdout.json` and `research/r3/RESULTS.md`. All three fail; Holm rejects none. The signer knows these results. Nothing about them changes, and no rule here can change them: the writer reads only forward-log rows and frozen in-sample quantities, and writes only to the two new files named below. No forward signal or position has been computed on any date. To see whether any value would be computed at all, the signer counted the dates present in the replayed recorded inputs (counts only, no value read): at the last study row in the log (2026-11-14T03:27:20Z) the 2Y/5Y/10Y par yields have 218 dates, fewer than R3-01's window of 500; SOFR has 2 fixings, fewer than the 20 R3-02 needs for one spread value. So every R3-01 and R3-02 row of this back-fill will be null under the rules below. R3-03's forecast needs no recorded input (Change 3); its value for any month was not computed at signing.

**How the choices were made.** Each choice below follows amendment 3's own words ("from recorded forward-log inputs only", "once", "no P&L claim"), the timing rule C1 of amendment 4 (no look-ahead), or the recorder's own published definition of a source's state (`tools/recorder/record.py`, `replay`). None depends on a holdout or forward outcome.

## Change 1: the writer

Replaces "the script named in the run line" in amendment 3 rules 3 and 4.

- The forward-log signal fields are computed and written by `research/r3_forward.py` (the writer). It imports `research/r3_runner.py` unchanged and uses its functions for every study formula (`zscore`, `hysteresis`, `par_dv01_closed`, `bill_basis`, `month_starts`), so the formulas are the ones the holdout run used. It refuses to run if the SHA-256 of `research/r3_runner.py` differs from the `script_sha256` of the study's line in `research/holdout_runs.csv`.
- The forward log itself (`actions/log.jsonl` on branch `forward-log`) is append-only and written by the scheduled recorder job; its `study/<id>` rows are not edited and keep `"signal": null`. The writer puts the fields of rules 3 and 4 in companion rows in `research/r3/forward_signals.jsonl`, a log in the same chained format (`tools/forward-log/forward_log.py`). Each companion row has `series_id` `study/<id>`, the `event_time` of the forward-log row it belongs to, and names that row by `fills` (its `hash`) and `fills_sequence`. One companion row per forward-log study row, never two.
- Each companion row carries: `signal`, `position`, `signal_status`, `as_of` (the date of the last input value used, or null), `params_sha256` (SHA-256 of `research/r3/params/<id>.json`), `inputs` (the replayed state hash of each input), `forward_log_head` (hash of the last forward-log line read), `writer_sha256`, `runner_sha256`, `backfilled`, `label` (`signal on a fitted curve; tradability not established`) and, when back-filled, `backfill_commit`. No P&L, return or Sharpe field.
- Every writer run appends one line to `research/r3/forward_runs.csv`: UTC time, mode, writer path and SHA-256, commit, forward-log ref and the commit it resolves to, forward-log head hash, rows written per study.

## Change 2: recorded inputs and dates

Makes "from recorded forward-log inputs only" exact.

- A row's date is the UTC date of its `event_time`. The J-2 run date is the `utc_date` of the study's run line (2026-11-14 for all three).
- The recorded inputs of a forward-log study row are the observations of the `recorder/<source>` rows with a lower `sequence`, replayed as `record.py` `replay` does (later values replace earlier ones; revisions included). This is what the recorder held when it wrote the row (C1). It includes the January to October 2026 values that entered the log before the forward-start filter (`DEVIATION-2026-11-12.md`); the holdout runs are done, so these values are no longer unread. Where the recorder row of a source carries `state_sha256`, the replayed state must hash to it, else the writer stops. No other data (study files, other worktrees, FRED) is read for a signal.
- Field names map to the study files' columns: par yields `2 Yr`, `5 Yr`, `10 Yr` to `2 YR`, `5 YR`, `10 YR`; bill `13 WEEKS COUPON EQUIVALENT` unchanged; NY Fed `percentRate` to the rate. A business day of a study is a date on which every input value it needs is present (C10).

## Change 3: the signal and position of each study

The selected trial and parameters are those of `research/r3/params/<id>.json`. Positions are the rule's positions; none is a trade or a P&L claim.

- **R3-01** (T08, `L` 500, `k` 1.5). On the study's business days up to the row's date, the fly `2 y5 - y2 - y10` in bp; `signal` is `z` at the last of them (amendment 4 item 4), `position` the `hysteresis` target decided at that close (to be executed at the next close, item 4). The path starts flat at the first day with a full window (`hysteresis` of `r3_runner.py`); with fewer than 500 business days, both are null and `signal_status` is `insufficient recorded history: n of 500 business days`.
- **R3-02** (T02, SOFR, `L` 60, `k` 2.0). `E` is the latest month start (`month_starts`) among the study's business days up to the row's date. `signal` is `z` decided for the entry at `E` from spread values dated on or before `E - 1` (amendment 4 item 1, trailing mean of the last 20 fixings), `position` its entry position, held to the next month start (item 2). With no such `E`, or fewer than 60 spread values before `E`, both are null and `signal_status` is `insufficient recorded history: n of 60 spread values`.
- **R3-03** (T01 = T03, own breakeven, `lambda` 0). The forecast for calendar month `m` is the mean of the in-sample month-end changes of the 5Y breakeven for month `m` (amendment 4 item 5, "frozen in-sample means"), computed once by the writer from the in-sample files logged in `research/r3/data_log.csv` (hash-checked; holdout files are not opened) with the formula of `seasonal_returns`, and written with its file hashes to `research/r3/forward_fit.json`; companion rows carry its SHA-256 as `fit_sha256`. A row dated in month `m` carries `signal` = that forecast (bp) and `position` = its sign: the position held over the month, set at the last close of month `m - 1` (item 5). It uses no recorded input; the in-sample fit is a frozen in-sample quantity like the parameters. A month with no in-sample mean gives null.
- `signal_status` is `computed` when `signal` is not null.

## Change 4: back-fill and later rows

Replaces the mechanism of amendment 3 rules 3 and 4; their scope is unchanged.

- `python research/r3_forward.py backfill` writes, once, a companion row for every forward-log study row dated before the J-2 run date, with `"backfilled": true` and `"backfill_commit"` the commit of the clean tree it runs from (which already holds the run lines). It refuses if `research/r3/forward_signals.jsonl` already has a back-filled row for the study, or the tree has uncommitted changes to the writer, the runner, the params or the companion files. The same run writes the rule-3 companion rows (`"backfilled": false`) for forward-log study rows dated on or after the J-2 run date that are already in the log.
- `python research/r3_forward.py daily` writes rule-3 companion rows for forward-log study rows that have none yet, dated on or after the J-2 run date; it never writes a row dated before it. Wiring it into the scheduled job is outside this amendment; until then it is run by hand, and a row's lateness shows in its `knowledge_time`.
- Rule 2 governs the forward-log rows as the recorder wrote them: they keep `"signal": null` and `"position": null`. The recorder never wrote the field `signal_status` that rule 2 names (its rows carry `"status": "no position: study not started"`). This is a stated gap; nothing is edited. Companion rows carry `signal_status`.

## Change 5: the scan check (rule 5)

Names the check of amendment 3 rule 5 and states it for companion rows.

- `research/holdout_scan.py` gains `signal_check`, run by `research/test_preregs.py` over `research/r3/forward_signals.jsonl` and, when fetched, the `study/<id>` rows of `origin/forward-log`. It fails on any study row with a non-null `signal` or `position` and any of: (a) no line for the study in `research/holdout_runs.csv`; (b) a `knowledge_time` date before the J-2 run date; (c) a row date before the J-2 run date without `"backfilled": true` and a `backfill_commit`; (d) the commit that wrote the row (the record's `commit`) cannot be shown to hold the study's line in its `research/holdout_runs.csv`.
- Back-filled rows are dated before the J-2 run date by design (rule 4); for them rule 5's date test is (b) and (d): the value was written after the run, from a tree that holds the run line.
- The check is in place and passing before the first non-null companion row is written, as rule 5 requires.

## What is unchanged

The holdout windows, the parameter grids, the selected trials, the costs, the family count `N = 24`, Holm across the three studies, the pass rule, the secondary statistic, the one-shot holdout runs and every number in `research/r3/holdout.json`, `research/r3/in_sample.json`, `research/r3/params/` and `research/r3/RESULTS.md`; `research/r3_runner.py` and `research/holdout_runs.csv`; the forward judgement (250 business days, amendment 1's rule) and the label.

## Prior knowledge

As in amendments 4 and 5, and the holdout results above, all known to the signer. At signing no forward signal, position or R3-03 forecast value had been computed on any date; the only forward-log quantities read were counts of recorded dates per input and the checks that the replayed states hash to the recorded `state_sha256`.

## AI assistance (`research/TEMPLATE.md` section 7)

- Tool and version: Claude Code, model claude-opus-5-5 (Opus 5.5), 2026-11-14.
- What it did: drafted this amendment from `program/R3_NOTES.md`, amendment 3 and `program/J11_Q6_02_DESIGN.md` section 5, and signed it under the owner's delegation (decision relayed by the stage J coordinator).
- Claims checked by a human: none yet. The second read was by a separate Claude subagent, not a person.
