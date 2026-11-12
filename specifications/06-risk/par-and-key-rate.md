# Par and key-rate risk

Spec version 1.0.0. Status: Specified (phase R2). Builds on `rates-sensitivities.md` (stage B) and keeps its sign and bump rules. Goldens: `datasets/golden/r2/risk_r2.json`, written by `oracle/python/gen_r2_risk.py`.

All risk is bump and revalue (ADR-0010): no AD. Every number is **money per basis point**: the change in the product's value, in its currency, for a +1 bp move, with the sign of that change. Risk is `dV/d(bp)`: the value change for rates **up** 1 bp. A receiver of fixed loses when rates rise, so its DV01 is **negative**; a payer's is positive; a long bond's is negative. This is the sign of `rates-sensitivities.md` and of every golden (ruling R2-A1).

## Products

A `product` object names what is revalued. Each kind reuses an existing pricer, so risk adds no new pricing rule.

| `kind` | Fields | Value | Pricer |
|---|---|---|---|
| `OIS` | `trade` as `rates.ois.pv` | `valuation.pv` | `02-curves/ois-curves.md` |
| `BOND` | `bond`, `settlement`, `notional` (face, `> 0`, else `E_DOMAIN`) | `notional x dirty / 100`, `dirty` from `bond.price.from_curve` | `04-pricing/bonds.md` |

Another `kind` is `E_SCHEMA`. An `OIS` trade whose `convention` differs from the curve's is `E_INPUT`. Later phases add kinds; a kind is added only with its goldens.

## Bump rules

- `bump_bp`: the bump size in bp, `0 < bump_bp <= 100`, else `E_DOMAIN`. Default and goldens: 1.
- `scheme`: `CENTRAL` (default) or `FORWARD`. With bumped value `V(+h)` and `V(-h)` for a bump of `h = bump_bp` bp:
  - `CENTRAL`: `risk = (V(+h) - V(-h)) / (2 bump_bp)`;
  - `FORWARD`: `risk = (V(+h) - V(0)) / bump_bp`.
- Dividing by `bump_bp` puts every result in money per 1 bp, whatever the bump size.

## `risk.curve.par`

Par-quote risk: bump the market quotes and rebuild the curve.

Inputs: `as_of`, `convention`, `quotes`, `interpolation` (as `rates.ois.bootstrap`), `product`, `bump_bp`, `scheme`.

The curve is built by `rates.ois.bootstrap`. A product's own dates (OIS periods, bond cash flows) stay fixed; only the curve moves.

Outputs:
- `value`: `V(0)`.
- `par_dv01`: every quote bumped by `h` together.
- `par_buckets`: one per quote, in quote order; entry `j` bumps quote `j` only.

The buckets sum to `par_dv01` to first order only. Golden check (not an output): the gap is below 1e-4 relative at 1 bp.

## `risk.curve.key_rate`

Zero-rate key-rate risk on a given curve: no rebuild.

Inputs: `curve` (a curve object, `02-curves/curve-framework.md`), `mode` (`TRIANGULAR` or `PILLAR`), `key_dates`, `product`, `bump_bp`, `scheme`. With `TRIANGULAR`, `key_dates` is strictly increasing, each after the curve's `as_of`, at least 1; else `E_INPUT`. With `PILLAR`, `key_dates` must be `null`, else `E_INPUT`.

### `TRIANGULAR`

Triangular weights in curve time `t = (d - as_of)/365`, with key times `k_1 < ... < k_n`:
- `w_1(t) = 1` for `t <= k_1`; `w_n(t) = 1` for `t >= k_n`;
- between neighbours, `w_i` falls linearly from 1 at `k_i` to 0 at `k_{i-1}` and at `k_{i+1}`, and is 0 elsewhere.

So at every `t` the weights sum to 1. Bucket `i` revalues on the curve `D_i(t) = D(t) exp(-w_i(t) h t)`, with `h` in decimal (1 bp = 0.0001). That is a continuously compounded zero-rate shift of `h w_i(t)` at every date, not only at pillars. Jumps and interpolation of `D` are unchanged.

### `PILLAR`

Bucket `i` bumps the zero rate of curve pillar `i` only: its discount factor becomes `D(p_i) exp(-h t_i)`, the other pillars stay, and the curve is re-interpolated with its own `interpolation` and jumps. One bucket per pillar, in pillar order.

### Outputs

- `value`;
- `key_rates`: one per key date (`TRIANGULAR`) or per pillar (`PILLAR`);
- `zero_dv01`: the parallel shift `D(t) exp(-h t)`.

In both modes the buckets sum to `zero_dv01` to first order; the goldens show a gap below 1e-6 relative at 1 bp.

## `risk.curve.jacobian`

How the bootstrapped zero rates move with the par quotes.

Inputs: `as_of`, `convention`, `quotes`, `interpolation`, `bump_bp`; the scheme is always central. With `TENSION_SPLINE` or `HYBRID`, `tension` and `step_end` are required exactly as in `rates.ois.bootstrap` (`02-curves/curve-framework.md`, same checks and codes), and every bumped curve is built with them (ruling R6-1.2).

**Basis (ruling R2-A8).** Rows are continuously compounded zero rates on ACT/365F curve time, `z_i = -ln D(p_i) / t_i` at pillar `i` (pillars as `rates.ois.bootstrap`). Columns are the par quotes as decimal rates on their own day counts. Neither is a simply compounded or annually compounded zero, and the matrix changes if either basis changes.

Outputs:
- `pillar_dates`;
- `zero_rates`;
- `jacobian`: a matrix with rows for pillars and columns for quotes, `J[i][j] = (z_i(q + h e_j) - z_i(q - h e_j)) / (2 h)`, dimensionless (bp of zero per bp of quote). Every entry is computed; no entry is set to 0 (ruling R6-1.1, closing R5 audit addendum A1). With the local methods `LOG_LINEAR_DF` and `LINEAR_ZERO` the matrix is lower triangular in exact arithmetic, because a pillar depends only on quotes up to its own, and entries above the diagonal come out at rounding level (below 1e-9). With `MONOTONE_CONVEX`, `MONOTONIC_LOG_CUBIC`, `TENSION_SPLINE` and `HYBRID` the curve is solved globally, so a later quote moves earlier pillars and entries above the diagonal are not zero (up to about 0.03 bp per bp on the golden SOFR curve). Until v0.8.0 the builds zeroed them, which was wrong for those four methods (review finding 3).

**Par from zero.** With `PILLAR` key rates on the bootstrapped curve, `par_buckets[j] ~ sum_i key_rates[i] J[i][j]` to first order, by the chain rule. The oracle checks this on every product (gap below 1e-3 of `par_dv01`). It is the Jacobian test of plan 11.2.1, not an output. It does not hold for `TRIANGULAR` buckets, because a triangular zero shift moves the curve between pillars differently from a pillar bump.

## Checks, in order

`E_SCHEMA` for the envelope, then `bump_bp` and `notional` (`E_DOMAIN`), then `key_dates` and convention rules (`E_INPUT`), then the pricer's own checks for the product at `V(0)`.

## Acceptance

Tolerance is class `interpolation` with per-case limits. Par risk and the Jacobian are differences of curve solves, so a build must stop its solve below 1e-13 in rate (as `rates-sensitivities.md`). Limits: risk within `1e-8 x notional` absolute plus 1e-7 relative; Jacobian entries within 1e-6 absolute in `risk_r2`, and within 1e-8 absolute plus 1e-6 relative in `r6/jacobian_r6` (ruling R6-1.3). Every `jacobian_r6` golden is also checked by the oracle against a Richardson extrapolation of central differences at `h` and `h/2`: within 1e-9 absolute plus 1e-7 relative of the derivative. Key-rate risk needs no solve: `1e-9 x notional` absolute plus 1e-9 relative.

Outside oracle: QuantLib rebuilds the curve from its own `OISRateHelper` quotes after each bump (`SimpleQuote`), and revalues with `MakeOIS` or `DiscountingBondEngine`. `TRIANGULAR` bumps use QuantLib's `PiecewiseZeroSpreadedTermStructure`, whose linear spread between dates with flat ends is the triangle above; `PILLAR` bumps rebuild a QuantLib `DiscountCurve` with the bumped node. Every golden in `risk_r2` is checked this way unless its tags say otherwise.
