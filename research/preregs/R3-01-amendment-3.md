# R3-01 amendment 3: US Treasury curve butterfly mean reversion, signal withheld until the holdout run

Status: **signed**. Signed by Claude (stage J lane J-11; signing delegated by the owner, 2026-11-07) on 2026-11-14.
- SHA-256 of the body below the marker line: `d7edfcb9dd0663eab2a8587eb96e3a6c42c44556de23ee3e07f09fe21999fb87`
- SHA-256 of the amended prereg `R3-01-treasury-fly.md` (whole file): `57e047579bf2952fad7f1a15197ca1a702fe994d8c77c32f3652105bdd7d7a3e`
- SHA-256 of `R3-01-amendment-1.md` (whole file): `a0b92234f172fe8fc0a846d0378d059a5315230213288cf813a5e767d6a9a77b`
- SHA-256 of `R3-01-amendment-2.md` (whole file): `feb357708a5614be55217500934968fd3dc075338f6475e719ba559d69632f6e`
- SHA-256 of the common rules (`README.md` body): `53566e4c3060d1adfd386a543b8d789b1de0b9b53393a8ffa03e0c3f4b5d58aa`
- SHA-256 of `DEVIATION-2026-11-12.md` (whole file): `b7e9e4d33e14dc164ed2c34312bf52bb894accfa124c3c8c45400d913e67c1db`
- SHA-256 of `DEVIATION-2026-11-12-recorder-rule.md` (whole file): `8a4bdeee378644ae4389b22b81ee259b3c101d6f0dd54c9be72a170fac2e3044`
- No signal has been computed on any date at signing.
- This file is not edited after signing; a further change is a new amendment.

<!-- body -->
Amends each of `R3-01-treasury-fly.md`, `R3-02-bill-repo-spread.md` and `R3-03-breakeven-seasonality.md` (one shared text; the file header names the study it amends) and that study's amendments 1 and 2. They stand; where this amendment differs, this amendment governs. Common rules: `README.md`. Source: plan J-11 (study rows carrying the daily signal), design `program/J11_Q6_02_DESIGN.md` section 5, review `program/J11_REVIEW.md`.

## Rules

1. **Holdout run record.** A study's holdout run (plan J-2) is logged by a line in `research/holdout_runs.csv` with the columns `study,utc_date,script,script_sha256,commit`, committed before any holdout-period value is read by the script. "The J-2 run date" of a study is the `utc_date` of that line.
2. **Withheld until then.** Every forward-log `study/<id>` row dated before the study's J-2 run date, or written while no such line exists, has `"signal": null`, `"position": null` and `"signal_status": "withheld: lookback inside holdout until J-2 run"`. Reason: the trailing window of a forward day reaches into the holdout window, and computing it would be computing a study signal on holdout-period data.
3. **After the run.** Rows dated on or after the J-2 run date carry `signal` (the study's statistic for that day), `position` (the rule's position under the parameters selected in-sample under amendment 1) and `params_sha256` (SHA-256 of the frozen parameter file), computed from recorded forward-log inputs only by the script named in the run line. They carry no P&L claim; the label is unchanged.
4. **Back-fill, once.** Rows dated from the forward log's start to the day before the J-2 run date are filled once by the same script from recorded inputs only, each marked `"backfilled": true` and `"backfill_commit": "<commit hash>"`. They are not filled again.
5. **Scan.** Before the first row with a non-null `signal` is written, `research/holdout_scan.py` gains a check, run by `research/test_preregs.py`, that fails on any `study/<id>` row with a non-null `signal` and either no holdout-run line for that study or a date before its J-2 run date.
6. **Unchanged.** The forward judgement (250 business days, amendment 1's rule), the holdout windows, the parameter grid, the costs, the multiple-testing count and the pass rule.

## Prior knowledge

Unchanged from amendment 2. At signing no signal has been computed on any date, in-sample, holdout or forward; every forward-log study row so far has `"signal": null`.
