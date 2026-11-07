# Commodity forward curves, seasonality and storage carry

Spec version 1.0.0. Status: Specified (stage D, D8).

## `cmdty.curve.forward`

Inputs: `quotes` `[{month, price}]` (delivery months `YYYY-MM`, strictly increasing, else `E_INPUT`; a price `<= 0`: `E_DOMAIN`), `seasonality` (`null`, or 12 additive log terms for January to December; another length: `E_INPUT`), `months`. Output: `forwards`.

With month index `k` and `sigma(k)` the term for its calendar month (0 when `null`): `L_j = ln(price_j) - sigma(k_j)` at the quotes; `L` linear in `k` between quotes; `F(k) = exp(L(k) + sigma(k))`. Every quote reprices. A month outside the quoted range: `E_OUT_OF_RANGE` (no extrapolation, ruling D29).

## `cmdty.storage.carry`

Inputs: `funding` (curve), `forwards` `[{date, price}]` (at least two, dates strictly increasing after `as_of`, else `E_INPUT`), `storage_cost` `u` (continuous, as a fraction of value per year, `>= 0`, else `E_DOMAIN`). For consecutive forwards, `dt = (d1 - d0)/365`, `r = ln(D(d0)/D(d1))/dt`:

- `convenience_yields`: `y = r + u - ln(F1/F0)/dt`
- `carry_values`: `D(d1) F1 - D(d0) F0 exp(u dt)`, the value of buying forward at `d0`, storing and selling forward at `d1`
- `arbitrage`: `carry_values > 0` (cash and carry earns money; `y < 0`)

## Acceptance

`simple_analytic`, analytic; `arbitrage` exact, and no golden carry value is within 1e-6 of zero. Suite `stage_d/commodity_d`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Hull, J. C., *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter "Determination of Forward and Futures Prices" (storage costs, convenience yield, cash and carry) (not opened)
- [S2] Geman, H., *Commodities and Commodity Derivatives*, Wiley, 2005 (forward-curve seasonality) (not opened)
