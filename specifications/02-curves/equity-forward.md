# Equity spot, dividends and forward

Spec version 1.0.0. Status: Specified. Stage C. Rulings in `../stage-c-rulings.md` win where they are more exact.

An equity forward follows from carrying the stock and paying out its dividends. Which curve grows and which curve discounts must be named, as the wrong pair gives a plausible number.

## Curves

Both are curve objects from `curve-framework.md`, with time `t = (date - as_of)/365`.

| Name | Object | Meaning |
|---|---|---|
| Funding curve `D(t)` | `funding_curve` | Discounts cash. With a flat rate, `exp(-r t)`. Option PVs use this curve only |
| Borrow curve `B(t)` | `borrow_curve`, or `null` for `B = 1` | Stock-loan fee earned by the holder. With a flat fee, `exp(-b t)` |
| Carry factor `C(t)` | Derived: `C(t) = D(t)/B(t)` | With flat rates, `exp(-(r-b) t)`. Grows the stock and carries dividends |

## Forward

`F(T) = S/C(T) - sum_i A_i C(t_i)/C(T)`, over dividends with `as_of < ex_date_i <= expiry`.

With flat rates this is `F = S e^{(r-b)T} - sum A_i e^{(r-b)(T-t_i)}`. **Dividends are carried on `C`, never discounted on `D`.** `(S - PV_r(D)) e^{(r-b)T}` is wrong unless `b = 0`.

Check case: `S = 100`, `r = 0.04`, `b = 0.05`, one dividend of 2 at `t = 0.5`, `T = 1`. True `F = 97.0149584`. The wrong form gives `97.0640923`. A date cannot be half a day, so the golden case for these exact numbers uses `eq.forward.flat`, below.

A dividend `{ex_date, amount}` is cash paid on its ex-date. Dividends with `ex_date <= as_of` or `ex_date > expiry` are ignored. A dividend on `expiry` counts: the buyer at expiry does not get it. Spot settles on `as_of`; there is no spot lag in stage C.

## Operations

`eq.forward.outright`. Inputs: `spot`, `as_of`, `expiry`, `funding_curve`, `borrow_curve`, `dividends` (array, may be empty). Outputs: `forward`, `discount_factor` (`D(T)`), `carry_factor` (`C(T)`), `pv_dividends` (`sum A_i C(t_i)`, on the carry factor).

Checks, in order: `spot <= 0` `E_DOMAIN`; each curve's own checks; a curve `as_of` that differs `E_INPUT`; `expiry < as_of` `E_DATE_ORDER`; `amount < 0` `E_DOMAIN`; `ex_date`s not strictly increasing `E_INPUT`; `F <= 0` `E_DOMAIN`. Above 100 dividends: `E_LIMIT`. `expiry = as_of` gives `F = S`, `D = C = 1`.

`eq.forward.flat`. Inputs: `spot`, `rate`, `borrow`, `expiry_years`, `dividends`, each `{time_years, amount}`. Output: `forward`, by the flat form above. Same rules on time as on dates: only `0 < t_i <= T` counts. `spot <= 0`, `expiry_years < 0`, `amount < 0`, `F <= 0`: `E_DOMAIN`. `time_years` not strictly increasing: `E_INPUT`. `rate`, `borrow` may be negative.

## Parity-implied forward

`eq.forward.parity`. Inputs: `quotes`, array of `{strike, call_bid, call_ask, put_bid, put_ask}` for one expiry; `discount_factor`, number or `null`.

With mids `c_i`, `p_i` and `y_i = c_i - p_i`, parity says `y = D (F - K)`.

- `discount_factor` given: `D` is it, and `F = mean(K_i + y_i/D)`.
- `null`: ordinary least squares of `y` on `K`, `y = a + s K`. `D = -s`, `F = a/D`.

Outputs: `forward`, `discount_factor`, `max_residual` (`max |y_i - D (F - K_i)|`), `outside_spread`: the strikes, ascending, where `D (F - K)` lies outside `[call_bid - put_ask, call_ask - put_bid]`.

Checks, in order: empty `quotes` `E_INPUT`; `strike <= 0`, any negative quote, given `discount_factor <= 0` `E_DOMAIN`; strikes not strictly increasing, a bid above its ask `E_INPUT`; `null` with one quote `E_INPUT`; fitted `D <= 0` or `F <= 0` `E_DOMAIN`. Above 100 quotes: `E_LIMIT`.

## Limits of this stage

Cash dividends only, paid on the ex-date. No proportional dividends, dividend curve, financing spread, or implied borrow: these are stage D. Options are European: American options are out, so no de-Americanisation is needed (ruling C1).

## Acceptance

Targets in `../05-volatility/stage-c-targets.md`. Suites `equity_forward`, `equity_forward_deep`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Hull, J. C., *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter "Determination of Forward and Futures Prices" (forward with known cash income) and chapter "Put-Call Parity" material in "Properties of Stock Options" (not opened)
