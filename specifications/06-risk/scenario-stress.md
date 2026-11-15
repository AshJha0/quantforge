# Scenario stress engine and historical shock library (G18)

Spec version 1.0.0. Status: specified (stage J, wave 3); Python reference first, Rust, Java and C++ in a later lane. Target CLI contract 1.15.0 (ruling J-W3-1). Rulings: `stage-j-rulings-w3.md` J-W3-2 to J-W3-7, J-W3-14. Suite: `datasets/golden/stage_j/scen_j`, written by `oracle/python/gen_stage_j_w3.py`. Plan 14.5 ("scenario stress engine with a historical shock library (2008, 2013, 2020, 2022) built from public curve history; scenario replay"), 14.6 J-8.

**Plain idea.** A stress test asks: if the curve moved today the way it moved in a past crisis, what would the book lose? Two steps. First measure the past move, tenor by tenor, from published history. Then lay that move on today's curve and price the book with it.

Sources:
- [UST] U.S. Department of the Treasury, Daily Treasury Par Yield Curve Rates, `home.treasury.gov` (public domain; CSV per year, no account). Evidence class: official data.
- [H15] Board of Governors of the Federal Reserve System, H.15 Selected Interest Rates, Treasury constant maturities, via FRED (`fred.stlouisfed.org`, series DGS1MO .. DGS30; free CSV, no account). Evidence class: official data, separate publication.

## `risk.scenario.historical_shock`

Inputs `dates` (ISO dates, strictly increasing), `tenors` (years, strictly increasing, positive), `yields` (one row per date, one column per tenor, percent), `start_date`, `end_date`. Outputs `start_yields`, `end_yields`, `shift_bp` (`100 (end - start)` per tenor), `level_bp` (mean of `shift_bp`), `slope_bp` (last minus first `shift_bp`).

Errors: row count differs from `dates` or a row length differs from `tenors`, empty inputs: `E_INPUT`; dates not increasing or `end_date <= start_date`: `E_DATE_ORDER`; a requested date not in `dates`: `E_DOMAIN` (J-W3-3); tenors not increasing or not positive: `E_DOMAIN`.

Worked example (hand): tenors `(2, 10)`, rows 2020-02-19 `(1.43, 1.56)`, 2020-03-09 `(0.46, 0.54)`: `shift_bp = (-97, -102)` (to binary64 rounding of `100 (0.46 - 1.43)`), level `-99.5`, slope `-5`.

## `risk.scenario.replay`

Inputs `base_tenors`, `base_yields` (percent), `shock_tenors`, `shock_bp`, optional `scale` (default 1, finite), optional `dv01` (one per base tenor). Outputs `applied_bp` (shock interpolated onto the base tenors, J-W3-4), `shocked_yields` (`base + applied_bp / 100`), and `pnl` when `dv01` is given (`- sum dv01_i applied_bp_i`).

Errors: length mismatches or empty: `E_INPUT`; tenors not increasing or not positive: `E_DOMAIN`.

Worked example (hand): base tenors `(1, 5, 10)`, shock at `(2, 10)` of `(-100, -50)` bp: applied `(-100, -100 + 3/8 * 50, -50) = (-100, -81.25, -50)`; with `dv01 = (0, 0, 1000)` the P&L is `+50,000`.

## Historical shock library (J-W3-6, J-W3-7)

`datasets/scenarios/us_treasury_shocks.json` holds, per named scenario, the window, the tenors kept, the start and end rows as published, `shift_bp`, and the SHA-256 of each raw file used. Windows (fixed before download): `gfc_2008` 2008-09-12 to 2008-12-31 (Lehman's last trading day to year end), `taper_2013` 2013-05-01 to 2013-09-05, `covid_2020` 2020-02-19 to 2020-03-09, `hikes_2022` 2021-12-31 to 2022-10-21. The library is data, not a forecast: it says what happened between two dates, not how likely it is.

**J-8 acceptance (J-W3-7):** (1) library shifts equal the stored rows' differences to `1e-9` bp; (2) start and end yields match H.15 within 0.005 percentage points; (3) replaying each shock on its start curve returns its end curve to `1e-12`.

**Date check (plan 14.10 rule 6).** The R3-01 holdout (2013-01-02 to 2026-10-30) and R3-02 holdout (2023 onward) were run and published on 2026-11-14 (`research/holdout_runs.csv`, `research/r3/RESULTS.md`), so the 2013, 2020 and 2022 windows read no unread holdout. No open prereg names these windows.

## Property tests (each language, own data)

- A zero shock leaves the curve unchanged; `scale = 2` doubles `applied_bp` and `pnl`; a flat shock of `c` bp moves every tenor by `c` bp; replay of `historical_shock(start, end)` on the start row returns the end row.

## Limitations

Par yields, not zero rates; first-order P&L only (no convexity, no carry over the window); a window's move is applied in one step. Spreads, vol and other asset classes are not in the library. US Treasury only.
