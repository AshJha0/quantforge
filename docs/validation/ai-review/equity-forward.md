# Review request: Equity forward, discrete dividends (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is a second opinion. It is filed under a labelled "AI review" section and never counts as the human sign-off.

Status: Implemented, not Validated (stage C). Evidence line from the project's status table: 4 golden cases for `eq.forward.outright`, 2 with an outside library in `verified_by`.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.
8. **Disagreement for ruling** (`equity_forward-0012`): the spec ignores a dividend with `ex_date <= as_of` (`specifications/02-curves/equity-forward.md`); QuantLib's `AnalyticDividendEuropeanEngine` counts one dated on the evaluation date. With that dividend removed, QuantLib agrees on all four outputs. The golden was not changed. Is the spec's rule (ex on as_of means already ex) the one the reviewer accepts?
9. `equity_forward-0014` (expiry on as_of) has no outside check: there is no option for the engine to price.

## Spec

### `specifications/02-curves/equity-forward.md`

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


## Golden cases (4 of 4 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"equity_forward-0011","operation":"eq.forward.outright","inputs":{"spot":100.0,"as_of":"2026-11-06","expiry":"2027-11-06","funding_curve":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2046-11-01","discount_factor":0.44932896411722156}]},"borrow_curve":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2046-11-01","discount_factor":0.8187307530779818}]},"dividends":[{"ex_date":"2027-01-18","amount":1.5},{"ex_date":"2027-04-01","amount":1.5},{"ex_date":"2027-11-06","amount":1.0}]},"expected":{"status":"ok","outputs":{"forward":98.98177345393107,"discount_factor":0.9607894391523232,"carry_factor":0.970445533548508,"pv_dividends":3.943580048922307}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["analytic-rolled","quantlib-1.44-dividend-engine"]}
{"case_id":"equity_forward-0012","operation":"eq.forward.outright","inputs":{"spot":100.0,"as_of":"2026-11-06","expiry":"2027-11-06","funding_curve":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2046-11-01","discount_factor":0.44932896411722156}]},"borrow_curve":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2046-11-01","discount_factor":0.8187307530779818}]},"dividends":[{"ex_date":"2026-11-06","amount":9.0},{"ex_date":"2027-11-07","amount":9.0}]},"expected":{"status":"ok","outputs":{"forward":103.0454533953517,"discount_factor":0.9607894391523232,"carry_factor":0.970445533548508,"pv_dividends":0.0}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["hand"]}
{"case_id":"equity_forward-0013","operation":"eq.forward.outright","inputs":{"spot":100.0,"as_of":"2026-11-06","expiry":"2027-11-06","funding_curve":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2046-11-01","discount_factor":0.44932896411722156}]},"borrow_curve":null,"dividends":[]},"expected":{"status":"ok","outputs":{"forward":104.08107741923882,"discount_factor":0.9607894391523232,"carry_factor":0.9607894391523232,"pv_dividends":0.0}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["hand","quantlib-1.44-dividend-engine"]}
{"case_id":"equity_forward-0014","operation":"eq.forward.outright","inputs":{"spot":100.0,"as_of":"2026-11-06","expiry":"2026-11-06","funding_curve":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2046-11-01","discount_factor":0.44932896411722156}]},"borrow_curve":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2046-11-01","discount_factor":0.8187307530779818}]},"dividends":[]},"expected":{"status":"ok","outputs":{"forward":100.0,"discount_factor":1.0,"carry_factor":1.0,"pv_dividends":0.0}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["hand"]}
```

## Outside-library evidence and limits (from the project's own page)

Per `specifications/05-volatility/stage-c-targets.md`, the forward is checked against a rolled route that steps between dividends one at a time, and against a plan check case. Since the validation evidence pack (2026-11-17), QuantLib's escrowed-dividend European engine checks two of the four outright cases through put-call parity (`oracle/OUTSIDE_VALIDATION.json`). It disagrees on the case with a dividend dated on `as_of`, which the spec ignores and QuantLib counts; that is a boundary convention for the reviewer (`docs/validation/equity-forward.md`), and no golden changed. The case with expiry on `as_of` has no option for the engine to price.

Golden cases with an `ok` result for `eq.forward.outright`: 4, counted from `verified_by` in `datasets/golden/stage_c/`. All four builds passed them locally, which is self-assessment.

| Verified by | Operation | Cases |
|---|---|---|
| analytic-rolled, quantlib-1.44-dividend-engine | eq.forward.outright | 1 |
| hand | eq.forward.outright | 2 |
| hand, quantlib-1.44-dividend-engine | eq.forward.outright | 1 |

Limits:

- Each curve has one pillar, so funding and borrow rates are constant. Curve shape is not exercised.
- Three dividends with fixed cash amounts. Dividend curves and forecasting are stage D.
- The chart moves only the expiry. Spot, curves and dividends stay as in the input file.

Synthetic inputs, not market data.

## Real-data reconciliation

- No free data: the stage C/D data surveys (LEARN.md) found no free dividend or borrow history. No reconciliation is possible without paid data, which the project does not buy.

## Rulings that name this curve's operations

None found by operation name.
