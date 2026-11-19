# Almgren-Chriss efficient frontier

<p class="note">Stage H, v0.10.0. The operations are built in all four languages (spec version 0.1.0, confirmed 2026-11-18), but this page is still written by hand from the spec's golden cases, not generated from CLI runs. It is not yet a generated gallery page. Parameters are the paper's test case; nothing is fitted to a market.</p>

## What it is

The plain idea: sell a block of shares fast and you pay impact; sell it slowly and the price can move against you while you wait. Each schedule has an expected cost and a variance of cost. Plotting expected cost against variance for the best schedule at each level of risk aversion gives a curve, the efficient frontier of execution: no schedule has both lower expected cost and lower variance than a point on it.

Formally ([AC00] eqs. (5), (8), (16), (17), pp. 10-14 of the December 2000 preprint; spec [`10-execution/almgren-chriss.md`](../../specifications/10-execution/almgren-chriss.md)): for `X` shares over `T` days in `N` steps of `tau = T/N`, with temporary impact `eta`, permanent impact `gamma`, fixed cost `epsilon` and daily volatility `sigma`, the trader minimises `E + lambda V`, where

- `E = 1/2 gamma X^2 + epsilon X + (eta_tilde / tau) sum n_k^2`, `eta_tilde = eta - gamma tau / 2`;
- `V = sigma^2 tau sum x_k^2`;
- the optimal holdings are `x_j = X sinh(kappa (T - t_j)) / sinh(kappa T)`, with `2 (cosh(kappa tau) - 1) = tau^2 lambda sigma^2 / eta_tilde`.

`lambda = 0` gives the straight-line schedule, the risk-neutral end of the frontier (ruling HR-5). Larger `lambda` moves along the curve towards lower variance and higher expected cost.

## Points on the frontier, from the goldens

Parameter set P: `X = 1e6`, `T = 5`, `N = 5`, `sigma = 0.95`, `epsilon = 0.0625`, `eta = 2.5e-6`, `gamma = 2.5e-7` ([AC00] Table 1, p. 25).

| `lambda` | Holdings after each day | Expected cost `E` | Variance `V` | Case | Evidence |
|---|---|---|---|---|---|
| 0 | 1e6, 8e5, 6e5, 4e5, 2e5, 0 | 662,500 | 1.083e12 | `ac_h-0001` | blind re-derivation (DR-H2); its standard deviation was visible to that lane beforehand |
| 1e-6 | 1e6, 541,955.5544, 289,854.2194, 147,897.4878, 62,141.8016, 0 | 911,226.986 | 3.641285721e11 | `ac_h-0002` | blind re-derivation (DR-H2); also agrees with the paper's closed form eq. (20) |

At `lambda = 1e-6` the paper prints `kappa` "about 0.6/day" and `kappa T` "about 3" (p. 24); the exact values are 0.6070761632 and 3.0353808 (`ac_h-0005`, outside-checked against the printed figure, tolerance 0.05 and 0.25).

Read the two rows as a trade: about 249,000 dollars more expected cost buys a variance one third as large. Only these two points are goldens; the rest of the curve will be drawn from `exec.ac.frontier` output once it is merged.

## What it does not show

- Linear impact and an arithmetic Brownian price with no drift; a pre-committed schedule (spec limitations). Adaptive re-optimisation is wave 2.
- No real stock: the parameters are the paper's illustration, not an estimate.
- The paper's remark that the no-trading standard deviation is "precisely twice" that of the lowest frontier point is not reproduced on this grid (ratio 2.04 with `N = 5`), and is not used.

## Related

[Tutorial 37](../getting-started/tutorial-37-almgren-chriss.md) works the same cases by hand. The [liquidity cost curve](liquidity.md) uses the variance of the straight-line schedule as its timing-risk term. Diagram H-D5 in [Diagrams](../diagrams/README.md#ac-frontier-cost-against-variance).
