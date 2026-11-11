# Cross-asset hedge: equity and rates

Spec version 1.0.0. Status: Specified (stage I, wave 3). Rulings: `stage-i-rulings.md` I-20 to I-23 (and I-1 to I-5 from wave 1). Suite `datasets/golden/stage_i/hedgexa_i`, written by `oracle/python/gen_stage_i_w3.py`.

**Plain idea.** An equity book also has interest-rate risk: an equity forward is worth `S e^{-qT} - K P(T)`, and an option's value moves with the discount curve. A cross-asset hedge treats the equity move and the key rates as one risk vector and finds the hedge that minimises the weighted residual over all of them together. Two separate hedges would each leave the other's risk behind. The plan's traceability adds this item to stage I (TRACEABILITY Domain 08: "Cross-asset hedge curve (equity/rates) ... Multi-instrument solver could carry it"). It is built on `hedge.qp.solve` (wave 1).

Sources:
- [H18] J. C. Hull, *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter 5 (forward price `S e^{(r-q)T}`, value of a forward contract) and chapter 19 (rho) (not opened in this session).
- [T07] B. Tuckman, A. Serrat, *Fixed Income Securities*, 3rd ed., Wiley, 2011, chapter 5 (key-rate exposures and hedging with key-rate bonds) (not opened).
- `08-hedging/hedge-solvers.md` (the weighted least-squares solve and its singularity rule), normative here.

## `hedge.crossasset.solve`

### Inputs

- `spot`, `dividend_yield` (continuous), `volatility` (flat Black-Scholes-Merton).
- `curve`: `{times, zero_rates}`. Pillar times in years (ACT/365F), strictly increasing, the first above 0. Continuously compounded zero rates. The rate is linear in time between pillars and flat before the first; nothing is defined after the last (I-20).
- `book`: positions `{instrument, ..., quantity}`; `hedges`: instruments without `quantity`. `instrument` and its keys:
  - `CALL`, `PUT`: `strike`, `expiry_years` (European, Black-Scholes-Merton with rate `z(T)` and yield `q`);
  - `FORWARD`: `strike`, `expiry_years`; long forward, value `S e^{-qT} - K P(T)`;
  - `ZCB`: `expiry_years`, `notional`; value `notional P(T)`;
  - `UNDERLYING`: no other key; value `S`.
- `weights`: one per risk factor, `1 + P` of them (`P` the number of pillars), each above 0.
- `ridge` (optional, default 0, at least 0), as `hedge.qp.solve`.

`P(T) = exp(-z(T) T)`.

### Checks, in order

1. Curve: no pillars, `zero_rates` of another length, times not strictly increasing, or a first time at or below 0: `E_INPUT`.
2. An instrument with keys other than its kind's; an empty book or hedge list; `weights` not of length `1 + P`: `E_INPUT`.
3. An `expiry_years` beyond the last pillar: `E_INPUT` (I-20).
4. `spot` or `volatility` at or below 0, a weight at or below 0, `ridge < 0`; a `strike`, `expiry_years` or `notional` at or below 0: `E_DOMAIN`.
5. The wave 1 singularity rule on the hedge risk matrix (I-3, I-5 policy `ERROR`): `E_SINGULAR`.

### Risk factors (I-21)

For each instrument, per unit:

- `EQ01 = (V(1.01 S) - V(0.99 S)) / 2`: the value change per 1% equity move, as half the difference of the two prices.
- `KR01_k = (V(z_k + 1bp) - V(z_k - 1bp)) / 2`, `k = 1..P`: only pillar `k`'s zero rate is moved, and the curve is rebuilt (linear in zero rates, so the bump fades to 0 at the neighbouring pillars and stays flat before the first).

These are definitions, not derivative approximations, so every build agrees to rounding. A ZCB has `EQ01 = 0`; an underlying has no key-rate risk; a forward has both.

### Solution

The risk matrix `A` has rows `EQ01, KR01_1..KR01_P` and one column per hedge. The book risk `b` is the quantity-weighted sum of the book's rows. The hedge is `hedge.qp.solve` with `a = A`, `b = b`, `weights`, `ridge`, no bounds or equalities. The singularity test is the wave 1 test (relative `1e-12` on the reduced Hessian). It is not scale-invariant, so hedge instruments should carry comparable risk per unit (I-22): that is why `ZCB` has a `notional`.

### Outputs

- `positions` (one per hedge).
- `book_risk` (length `1 + P`, order `EQ01, KR01_1..KR01_P`).
- `residual_risk = book_risk + A positions`.
- `objective = sum_f w_f residual_f^2 + ridge |positions|^2`.

## Validation cases and oracle

`hedgexa_i`: 9 value cases and 8 error cases. The value cases are: an exact square hedge (a forward and four bonds), least squares with the underlying and two bonds, forwards only (whose rate risk is the point), a heavy equity weight, a rates-only book, a ridge on a near-duplicate bond pair, a maturity between pillars, a maturity before the first pillar, and an inverted curve. Values are computed at 50 digits; the risk matrix goes through the wave 1 reference solver.

Self-checks: the square hedge leaves no residual; the rates-only book has `EQ01 = 0` exactly; a maturity before the first pillar has key-rate risk on pillar 1 only.

Outside (I-2): 9 of 17. The check takes QuantLib 1.44 `ZeroCurve` (linear in continuous zero rates, ACT/365F, the first pillar's rate repeated at the reference date for the flat short end) and `AnalyticEuropeanEngine` on a process that discounts on that curve, with forwards and bonds from its discount factors. It applies the same half-differences, then numpy `linalg.lstsq` on the weighted system. Positions and book risk agree within the case limit. Stage I so far: 72 of 177 = 40.7%.

Mutant caught: a forward priced without the dividend yield.

## Convergence and limit cases

| Method | Asserted behaviour | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Weighted least squares (wave 1 active set, no constraints) | Exact in one solve; the square case leaves no residual | All value cases | Equity weight 100 drives the equity residual to near 0 at the cost of the rates (`hedgexa_i-0004`) | QuantLib values, numpy `lstsq` |
| Key-rate half-differences | Fixed 1bp bump, no step-size limit | All value cases | Maturity before pillar 1: all rate risk on pillar 1 (`-0008`) | QuantLib `ZeroCurve` bumps |

## Limitations

- One equity, one flat volatility, one discount curve with no separate projection curve, and no dividend term structure.
- No bounds, costs or integer contracts here. A user who needs them passes `book_risk` and the risk matrix to `hedge.qp.solve` or `hedge.integer.solve`. The risk matrix itself is not an output in this wave (spec question Q-I8).
- The singularity test depends on the hedge instruments' units (I-22).

## Spec questions and rulings

| # | Question | Ruling |
|---|---|---|
| Q-I8 | Should the risk matrix be an output, so it can be fed to the constrained solvers? | Not in wave 3. It is `(1 + P) x n` numbers and doubles the golden size. A later wave (costs and constraints) can add it as an output, which does not change any existing output |
| Q-I9 | Extrapolate the curve after the last pillar? | No (I-20). A flat-forward or flat-zero choice would move the last bucket's risk, and QuantLib's default differs from both options. Refusing is the least surprising answer |
| Q-I10 | Make the singularity test scale-invariant (equilibrate the columns first)? | Not for wave 3. That would change I-3 for one operation only, and I-3 is registered. Instruments carry a size instead (`ZCB` `notional`, I-22). An owner ruling may later register a scale-invariant test as a new rule for new operations |
