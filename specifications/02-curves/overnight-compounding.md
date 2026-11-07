# Overnight compounding by date, and IBOR fallbacks

Spec version 1.0.0. Status: Specified (stage D).

A coupon on an overnight index compounds one published fixing per business day. Market documents move the fixing window so the amount is known before payment. This spec fixes the three standard ways.

## `rates.ois.compound_dated`

Inputs: `convention` (an `OVERNIGHT` record from `01-core/conventions.md`: `SONIA`, `SOFR`, `ESTR`), `start`, `end`, `method` (`NONE`, `LOOKBACK`, `OBSERVATION_SHIFT`, `LOCKOUT`), `shift_days` (integer), `fixings`: `[{date, rate}]`.

Let `cal` be the record's calendar and `B` its day-count denominator (`ACT_360`: 360, `ACT_365F`: 365). `d_0 = start < d_1 < ... < d_n = end` are the business days of `cal` in `[start, end]`. `back(d, k)` is `d` moved `k` business days earlier on `cal`. `r(x)` is the fixing dated `x`.

| `method` | Rate for step `i` (`0 <= i < n`) | Weight `w_i` |
|---|---|---|
| `NONE` | `r(d_i)` | `d_{i+1} - d_i` days |
| `LOOKBACK` | `r(back(d_i, k))` | `d_{i+1} - d_i` days (interest period) |
| `OBSERVATION_SHIFT` | `r(o_i)`, `o_i = back(d_i, k)` | `o_{i+1} - o_i` days (observation period) |
| `LOCKOUT` | `r(d_i)` for `i < n-k`; `r(d_{n-k})` for `i >= n-k` | `d_{i+1} - d_i` days |

`k = shift_days`. Then `growth = prod (1 + r_i w_i / B)`, `compounded_rate = (growth - 1) B / sum w_i`, `accrual = (end - start)/B`, `interest = compounded_rate * accrual`. Outputs: `compounded_rate`, `accrual`, `interest`.

`LOCKOUT` follows the ARRC rule: the rate cut-off date is `d_{n-k}`, and its fixing applies to it and every later day. QuantLib's `lockoutDays = k` locks one day earlier; this spec's `k` is QuantLib's `k-1` (ruling D3). Run the product in day order in binary64.

Checks, in order: `convention` not `OVERNIGHT`: `E_INPUT`. `end <= start`: `E_DATE_ORDER`. `shift_days < 0`; `NONE` with `shift_days != 0`; `LOCKOUT` with `shift_days < 1` or `shift_days > n-1`: `E_INPUT`. `start` or `end` not a business day of `cal`: `E_INPUT`. Two fixings on one date, or a needed fixing missing: `E_INPUT`. Extra fixings are ignored. `fixings` is not a quote list: the general array limit applies.

## `rates.fallback.rate`

The ISDA 2020 IBOR fallback: the compounded risk-free rate over the IBOR period, observation period shifted 2 business days back, plus the spread adjustment fixed on 2021-03-05.

Inputs: `ibor`, `start`, `end` (the IBOR period's value and maturity dates), `fixings`. Outputs: `compounded_rate` (as `rates.ois.compound_dated` with `OBSERVATION_SHIFT`, `shift_days` 2), `spread_adjustment`, `fallback_rate = compounded_rate + spread_adjustment`.

| `ibor` | Index | Spread adjustment |
|---|---|---|
| `USD-LIBOR-1M`, `-3M`, `-6M`, `-12M` | `SOFR` | 0.0011448, 0.0026161, 0.0042826, 0.0071513 |
| `GBP-LIBOR-1M`, `-3M`, `-6M`, `-12M` | `SONIA` | 0.0003260, 0.0011930, 0.0027660, 0.0046440 |

Other values: `E_SCHEMA`. Checks as `rates.ois.compound_dated`.

## Acceptance

`compounded_rate`, `fallback_rate` within 1e-12 absolute of exact-rational goldens. QuantLib `OvernightLeg` with `lookbackDays`, `lockoutDays`, `applyObservationShift` agrees within 5e-14 on every golden. Suite `stage_d/compound_d`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] ISDA, *2021 ISDA Interest Rate Derivatives Definitions*, compounding methods for overnight rates (Compounding with Lookback, with Observation Period Shift, with Lockout) (not opened)
- [S2] ARRC (Alternative Reference Rates Committee, NY Fed), *SOFR "In Arrears" Conventions for Syndicated Business Loans*, 2019, and the ARRC conventions matrix for SOFR products (not opened)
- [S3] ISDA, *Supplement number 70 to the 2006 ISDA Definitions* (IBOR fallbacks), 2020, and Bloomberg Index Services, *IBOR Fallback Rate Adjustments Rule Book*; spread adjustments fixed by the FCA announcement of 5 March 2021 (not opened)
- [S4] Bank of England, *SONIA key features and policies* (not opened)
- [S5] Federal Reserve Bank of New York, SOFR and reference-rate production methodology (statement on the Secured Overnight Financing Rate) (not opened)
- [S6] European Central Bank, *Euro short-term rate (€STR) methodology and policies* (not opened)
