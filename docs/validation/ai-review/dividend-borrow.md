# Review request: Dividend and borrow (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is a second opinion. It is filed under a labelled "AI review" section and never counts as the human sign-off.

Status: Implemented, not Validated (stage D). Evidence line from the project's status table: 4 golden cases.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.

## Spec

### `specifications/02-curves/equity-curves.md`

# Equity dividend, borrow and financing curves

Spec version 1.0.0. Status: Specified (stage D, D5).

Builds on `equity-forward.md` and ruling C2: dividends carry on `C = D/B`, never on `D` alone. Here `B(t) = exp(-b t)` for a flat `borrow_rate` `b`, and a financing spread `s` multiplies `C` by `exp(-s t)`. `t = (d - as_of)/365`, `as_of` the funding curve's.

`F(T) = [S - sum_{as_of < t_i <= T} div_i C(t_i)] / C(T)`.

## `eq.dividend.implied`

Inputs: `spot`, `funding` (curve), `borrow_rate`, `futures` `[{expiry, price}]` (expiries strictly increasing and after `as_of`, else `E_INPUT`). Outputs, per expiry:

- `pv_dividends`: `X(T) = S - F(T) C(T)`, the carry-discounted dividends to `T`
- `period_pv_dividends`: `X(T_1)`, then `X(T_k) - X(T_{k-1})`
- `dividend_yields`: `q(T) = -ln(F(T) C(T)/S)/T`

`spot` or a price `<= 0`: `E_DOMAIN`.

## `eq.borrow.implied`

Inputs: `spot`, `funding`, `dividends` `[{ex_date, amount}]`, `expiry`, `forward`. Output: `borrow_rate`, the `b` with `F(expiry) = forward`. `F` falls as `b` rises, so `b` is unique; solve below 1e-14 in `b`. No solution in `[-0.5, 0.5]`: `E_NOT_BRACKETED`.

## `eq.futures.basis`

Inputs: `spot`, `funding`, `borrow_rate`, `financing_spread`, `dividends`, `expiry`, `futures_price`. Outputs: `fair_price = F(expiry)` with that spread, `basis = futures_price - fair_price`, `implied_financing_spread` (the `s` that makes them equal, unique, as for borrow). `expiry <= as_of`: `E_DATE_ORDER`.

## Acceptance

`simple_analytic`; implied rates `root_finding`, known truth. Suite `stage_d/equity_d`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Hull, J. C., *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter "Determination of Forward and Futures Prices" (forwards on assets with known income, stock index futures) (not opened)
- [S2] Eurex / CME equity index dividend futures contract specifications (implied dividends from futures) (not opened)


## Golden cases (4 of 4 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"equity_d-0001","operation":"eq.dividend.implied","inputs":{"spot":5012.5,"funding":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2027-05-07","discount_factor":0.9800080230670242},{"date":"2027-11-06","discount_factor":0.9607894391523232},{"date":"2028-11-05","discount_factor":0.9258898536064953},{"date":"2031-11-06","discount_factor":0.8289439483311681}]},"borrow_rate":0.003,"futures":[{"expiry":"2026-12-18","price":5016.176013930697},{"expiry":"2027-03-19","price":5046.793739945202},{"expiry":"2027-06-18","price":5072.614516369763},{"expiry":"2027-12-17","price":5127.681312075034}]},"expected":{"status":"ok","outputs":{"pv_dividends":[17.922496104690254,34.19856718548181,54.72315336158954,89.91207626349205],"period_pv_dividends":[17.922496104690254,16.276071080791553,20.524586176107732,35.188922901902515],"dividend_yields":[0.031129006874493576,0.018787997717501892,0.017887230375510255,0.01627252678696537]}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["analytic"]}
{"case_id":"equity_d-0004","operation":"eq.borrow.implied","inputs":{"spot":5012.5,"funding":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2027-05-07","discount_factor":0.9800080230670242},{"date":"2027-11-06","discount_factor":0.9607894391523232},{"date":"2028-11-05","discount_factor":0.9258898536064953},{"date":"2031-11-06","discount_factor":0.8289439483311681}]},"dividends":[{"ex_date":"2026-12-18","amount":18.0},{"ex_date":"2027-03-19","amount":16.5},{"ex_date":"2027-06-18","amount":21.0},{"ex_date":"2027-09-17","amount":17.5},{"ex_date":"2027-12-17","amount":19.0},{"ex_date":"2028-03-17","amount":17.0}],"expiry":"2027-03-19","forward":5046.793739945202},"expected":{"status":"ok","outputs":{"borrow_rate":0.003}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["known-truth"]}
{"case_id":"equity_d-0005","operation":"eq.borrow.implied","inputs":{"spot":5012.5,"funding":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2027-05-07","discount_factor":0.9800080230670242},{"date":"2027-11-06","discount_factor":0.9607894391523232},{"date":"2028-11-05","discount_factor":0.9258898536064953},{"date":"2031-11-06","discount_factor":0.8289439483311681}]},"dividends":[{"ex_date":"2026-12-18","amount":18.0},{"ex_date":"2027-03-19","amount":16.5},{"ex_date":"2027-06-18","amount":21.0},{"ex_date":"2027-09-17","amount":17.5},{"ex_date":"2027-12-17","amount":19.0},{"ex_date":"2028-03-17","amount":17.0}],"expiry":"2027-12-17","forward":5073.236147581374},"expected":{"status":"ok","outputs":{"borrow_rate":0.0125}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["known-truth"]}
{"case_id":"equity_d-0006","operation":"eq.borrow.implied","inputs":{"spot":5012.5,"funding":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2027-05-07","discount_factor":0.9800080230670242},{"date":"2027-11-06","discount_factor":0.9607894391523232},{"date":"2028-11-05","discount_factor":0.9258898536064953},{"date":"2031-11-06","discount_factor":0.8289439483311681}]},"dividends":[{"ex_date":"2026-12-18","amount":18.0},{"ex_date":"2027-03-19","amount":16.5},{"ex_date":"2027-06-18","amount":21.0},{"ex_date":"2027-09-17","amount":17.5},{"ex_date":"2027-12-17","amount":19.0},{"ex_date":"2028-03-17","amount":17.0}],"expiry":"2027-06-18","forward":5085.166426538437},"expected":{"status":"ok","outputs":{"borrow_rate":-0.001}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["known-truth"]}
```

## Outside-library evidence and limits (from the project's own page)

4 golden cases with status ok in `datasets/golden/stage_d` for `eq.dividend.implied`, `eq.borrow.implied`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| eq.borrow.implied: known-truth | 3 |
| eq.dividend.implied: analytic | 1 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the specs are in `specifications/`.

## Real-data reconciliation

- No free data: the stage C/D data surveys (LEARN.md) found no free dividend or borrow history. No reconciliation is possible without paid data, which the project does not buy.

## Rulings that name this curve's operations

- (stage-d-rulings.md) | D32 | No root for an implied rate in `eq.futures.basis`, `eq.borrow.implied` | Search `[-0.5, 0.5]` only; otherwise `E_NOT_BRACKETED`. Case `rulings_d-0003` (root near -0.65) |
- (stage-d-rulings.md) | D53 | Equity checks | Empty `futures`: `E_INPUT`. `eq.borrow.implied` with `expiry <= as_of`: `E_DATE_ORDER`. `eq.index.rebalance`: duplicate ids (`E_INPUT`) before `divisor <= 0` (`E_DOMAIN`). Cases `rulings2_d-0009` to `-0011` |
