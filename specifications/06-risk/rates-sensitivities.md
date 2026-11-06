# Rates sensitivities

Spec version 1.0.0. Status: Specified. By ADR-0010, stage B uses bump and rebuild, with no AD.

## `risk.ois.dv01`

Inputs: `as_of`, `quotes`, `interpolation`, `trade` (as `rates.ois.pv`, whose `convention` selects the curve). Outputs: `dv01`, `key_rate`.

The trade's periods stay fixed. Bumps are on quotes, and the curve is rebuilt each time.

`dv01 = (PV(all quotes + 1 bp) - PV(all quotes - 1 bp)) / 2`: the change in PV for +1 bp, signed.

`key_rate[j]`: the same, bumping quote `j` only. One entry per quote. The bump shapes sum to the parallel bump, so the entries sum to `dv01` to first order; plan section 2 says no more than that. Measured gap: below 1e-5 relative at 1 bp.

## `risk.cashflows`

Duration and convexity of fixed cashflows at a continuously compounded yield. Inputs: `cashflows` (`{t, amount}`, at least 1, else `E_INPUT`; `t < 0`: `E_DOMAIN`), `yield`. Outputs:

`pv = sum c exp(-y t)`, `duration = sum t c exp(-y t) / pv`, `convexity = sum t^2 c exp(-y t) / pv`. `pv = 0`: `E_DOMAIN`.

Under continuous compounding, Macaulay and modified duration are the same.

## Acceptance

Limits are in `stage-b-targets.md`. Golden DV01s are differences of tight solves; a build must stop its curve solve below 1e-13 or these will fail.
