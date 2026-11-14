# R3-01 amendment 5: US Treasury curve butterfly mean reversion, closed-form par-bond DV01

Status: **signed**. Signed by Claude (stage J run lane; signing delegated by the owner, 2026-11-07, decision relayed by the stage J coordinator) on 2026-11-14. Second read: `program/R3_A5_REVIEW.md` (a separate Claude subagent; human check: none).
- SHA-256 of the body below the marker line: `1c28d514abe16cd7e0c1eec62a5adc50ecb3f6d7f7ccac81ec1737bb69367c6c`
- SHA-256 of the amended prereg `R3-01-treasury-fly.md` (whole file): `57e047579bf2952fad7f1a15197ca1a702fe994d8c77c32f3652105bdd7d7a3e`
- SHA-256 of `R3-01-amendment-1.md` (whole file): `a0b92234f172fe8fc0a846d0378d059a5315230213288cf813a5e767d6a9a77b`
- SHA-256 of `R3-01-amendment-2.md` (whole file): `feb357708a5614be55217500934968fd3dc075338f6475e719ba559d69632f6e`
- SHA-256 of `R3-01-amendment-3.md` (whole file): `4fc7d3dce832bdf409c713f76d144df9f2c32f46fb661ff8f5197b142433b30d`
- SHA-256 of `R3-01-amendment-4.md` (whole file): `8327fc5b04401d8720719ac6ae08d13cae36c6d39cc3ed58631a13ddd0c47813`
- SHA-256 of the common rules (`README.md` body): `53566e4c3060d1adfd386a543b8d789b1de0b9b53393a8ffa03e0c3f4b5d58aa`
- SHA-256 of `DEVIATION-2026-11-12.md` (whole file): `b7e9e4d33e14dc164ed2c34312bf52bb894accfa124c3c8c45400d913e67c1db`
- SHA-256 of `DEVIATION-2026-11-12-recorder-rule.md` (whole file): `8a4bdeee378644ae4389b22b81ee259b3c101d6f0dd54c9be72a170fac2e3044`
- No R3-01 signal, position, return or statistic has been computed on any date at signing; `research/holdout_runs.csv` has no line.
- This file is not edited after signing; a further change is a new amendment.

<!-- body -->
Amends `R3-01-treasury-fly.md` and its amendments 1 to 4. They stand; where this amendment differs, this amendment governs. Common rules: `README.md`. Source: the stop recorded in `program/R3_NOTES.md` (run lane, 2026-11-14) and the coordinator decision under the owner's delegation. Second read: `program/R3_A5_REVIEW.md`. R3-02 and R3-03 are not amended.

**Why.** Amendment 4 item 1 fixes the leg DV01 as `quantforge_core.bonds.price_from_yield` of a par bond settled on each date. The library's calendars cover 2000 to 2099 only (`calendars.MIN_YEAR = 2000`), so it refuses every date from 1990-01-02 to the end of 1999, and three dates in 2000; the in-sample window starts on 1990-01-02. The study cannot be run as amendment 4 states.

**State at signing.** No R3-01 signal, position, return or statistic has been computed on any date. The R3-01 in-sample run stopped at the first DV01 call. The only R3-01 numbers computed are the DV01 check below, which uses yields and DV01s only (no fly, no z-score, no return). No line exists in `research/holdout_runs.csv` and no holdout file has been parsed.

## Change 1: closed-form par-bond DV01

Replaces the DV01 sentence of amendment 4, R3-01 item 1 (and its use in item 7 and item 8). Everything else in item 1 stands, including `G = 1/D2 + 2/D5 + 1/D10` and the return definition.

- The leg is a par bond with semi-annual coupon equal to its par yield `y` (decimal), maturity `n` years after the date, settled on the date. Settlement falls on a coupon date, so accrued interest is zero, the period fraction to the next coupon is a whole period under the prereg's bond convention (actual/actual by coupon period), and the price is 1 per unit notional.
- DV01 per unit notional per bp: `D = (1 - (1 + y/2)^(-2n)) / y / 10^4`, and `D = n / 10^4` when `y = 0` (the limit). This is the modified duration of a par bond times its price of 1 (Tuckman and Serrat, *Fixed Income Securities*, 3rd ed., the chapter on DV01, duration and convexity: price of a par bond and its yield derivative in closed form; Fabozzi, *Bond Markets, Analysis, and Strategies*, the chapter on measuring interest-rate risk).
- The unit is per unit notional, as in `research/DEVIATION-2026-11-14-a4-dv01-wording.md`.
- Implemented as `par_dv01_closed` in `research/r3_runner.py`; used for every R3-01 date, in-sample and holdout, so one formula covers the whole path (C3).

## Check made before signing (in-sample dates only)

On every in-sample business day from 2000-01-03 to 2012-12-31 and each tenor 2Y, 5Y, 10Y (9,756 leg-days), the closed form was compared with `price_from_yield` (`modified_duration x dirty / 100 / 10^4`):
- 9,747 leg-days: relative difference below 1e-9 (median 4e-15).
- 6 leg-days (2008-02-28 and 2012-02-28, all three tenors): relative difference up to 1.4e-3. In a leap year a maturity of 28 February is treated by the library as month-end, so its schedule rolls to 29 February and the settlement date is not a coupon date; the closed form keeps settlement on a coupon date as this amendment defines.
- 3 leg-days (2000-02-28): refused by the library (its schedule walks back before 2000).
Tolerance stated: relative 1e-9 where settlement is a coupon date in both. The check used no holdout date.

## What is unchanged

Amendment 4 in full apart from the DV01 sentence; the holdout window, grid, costs, `N = 24`, Holm across the three studies, the pass rule, the secondary statistic and the one-shot holdout run.

## Prior knowledge

Unchanged from amendment 4. At signing no R3-01 signal or statistic has been computed on any date. The in-sample results of R3-02 and R3-03 (both negative or modest, `research/r3/in_sample.json`) were known to the signer; they cannot bear on a DV01 formula.

## AI assistance (`research/TEMPLATE.md` section 7)

- Tool and version: Claude Code, model claude-opus-5-5 (Opus 5.5), 2026-11-14.
- What it did: ran the DV01 check, drafted and signed this amendment under the owner's delegation (decision relayed by the stage J coordinator).
- Claims checked by a human: none yet. The second read was by a separate Claude subagent.
