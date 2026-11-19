# Tutorial 37: trade fast or trade slow: Almgren-Chriss

<!-- tutorial:only python -->

The plain idea: selling a large position quickly costs impact, because you push the price as you sell; selling slowly costs risk, because the price can drift while you still hold the shares. Almgren and Chriss put both on one scale. With linear impact and a trader who dislikes variance, the best schedule sells more at the start and less later, and one number, the risk aversion `lambda`, decides how front-loaded it is.

You will reproduce the paper's test case: the straight-line schedule at `lambda = 0`, the curved one at `lambda = 1e-6`, the paper's own printed `kappa`, and two points of the cost-risk frontier. Budget 10 minutes. The parameters are the paper's (Table 1, p. 25 of the preprint); nothing is fitted to a market.

<p class="note">Available from v0.10.0. The operations on this page are implemented in all four languages (stage H wave 1; each build passes their goldens, observed, local, 2026-11-18). This page stays a hand check: step 1 checks the spec's golden numbers with a plain-Python restatement of the formulas, and step 2 shows the library call without running it. Every number on the page is a spec golden or simple arithmetic on one.</p>

Terms, defined here. `X` is the position to sell over `T` days in `N` steps of length `tau = T/N`. **Holdings** `x_j` are what is left after step `j`; **trades** `n_j = x_{j-1} - x_j`. `sigma` is the daily price volatility in dollars per share, `epsilon` the fixed cost per share (half spread and fees), `eta` the temporary impact per unit of trading rate, `gamma` the permanent impact. `E` is the expected cost and `V` its variance; the trader minimises `E + lambda V`.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/), as in [Tutorial 1](tutorial-1-swap.md): `uv sync --locked --project python`.
- Nothing else. The script below uses the Python standard library only, so it needs no build.

## Step 1: check the goldens by hand

The script restates the formulas of the spec in a few lines of plain Python and runs them on the inputs of the spec's golden cases. It calls no QuantForge operation: it checks the spec's arithmetic independently of the builds. The operations themselves are built in all four languages and pass these goldens through the conformance runner; Tutorials 41 to 44 call the Python build directly. CI runs this block and checks the printed lines.

<!-- tutorial:run python -->
```python
# Hand check of the Almgren-Chriss goldens ac_h-0001, 0002, 0004, 0005 in plain Python (no library call).
import math

X, T, N, sigma, eps, eta, gamma = 1e6, 5.0, 5, 0.95, 0.0625, 2.5e-6, 2.5e-7

def ac(lam, n=N):
    tau = T / n
    eta_t = eta - gamma * tau / 2
    if lam == 0:
        kappa = 0.0
        x = [X * (1 - j / n) for j in range(n + 1)]
    else:
        y = tau * tau * lam * sigma ** 2 / (2 * eta_t)        # cosh(kappa tau) = 1 + y
        kappa = math.acosh(1 + y) / tau
        x = [X * math.sinh(kappa * (T - j * tau)) / math.sinh(kappa * T) for j in range(n + 1)]
    trades = [x[j] - x[j + 1] for j in range(n)]
    e = 0.5 * gamma * X ** 2 + eps * X + eta_t / tau * sum(t * t for t in trades)
    v = sigma ** 2 * tau * sum(xx * xx for xx in x[1:])
    return kappa, x, e, v

k, x, e, v = ac(0.0)
print(f"ac_h-0001 lambda 0: holdings {[round(h) for h in x]}  E {e:,.0f}  V {v:.4g}")
k, x, e, v = ac(1e-6)
print(f"ac_h-0002 lambda 1e-6: kappa {k:.10f}")
print("  holdings " + ", ".join(f"{h:.4f}" for h in x))
print(f"  E {e:,.3f}  V {v:.9e}  E + lambda V {e + 1e-6 * v:,.3f}")
print(f"ac_h-0005 kappa T {k * T:.7f} (paper, p. 24: about 3)")
k, x, e, v = ac(1e-6, n=1)
print(f"ac_h-0004 N = 1: holdings {[round(h) for h in x]}  E {e:,.0f}")
print(f"frontier points: lambda 0 gives (E, V) = (662,500, 1.083e12); lambda 1e-6 gives (911,227, 3.641e11)")
```

Output (CI checks these lines):

<!-- tutorial:expect -->
```text
ac_h-0001 lambda 0: holdings [1000000, 800000, 600000, 400000, 200000, 0]  E 662,500  V 1.083e+12
ac_h-0002 lambda 1e-6: kappa 0.6070761632
  holdings 1000000.0000, 541955.5544, 289854.2194, 147897.4878, 62141.8016, 0.0000
  E 911,226.986  V 3.641285721e+11  E + lambda V 1,275,355.558
ac_h-0005 kappa T 3.0353808 (paper, p. 24: about 3)
ac_h-0004 N = 1: holdings [1000000, 0]  E 562,500
frontier points: lambda 0 gives (E, V) = (662,500, 1.083e12); lambda 1e-6 gives (911,227, 3.641e11)
```

### Reading the numbers

- **Risk neutral, `lambda = 0`.** The best schedule is the straight line: 200,000 shares a day for five days (`ac_h-0001`). Its expected cost is `1/2 gamma X^2 + epsilon X + eta_tilde X^2 / T = 125,000 + 62,500 + 475,000 = 662,500` dollars, with `eta_tilde = eta - gamma tau / 2 = 2.375e-6`. Its variance is `sigma^2 tau sum x_k^2 = 1.083e12`, a standard deviation of about 1.04 million dollars.
- **Risk averse, `lambda = 1e-6`.** Holdings fall like `sinh(kappa (T - t)) / sinh(kappa T)`: after one day 541,955.5544 shares are left, not 800,000 (`ac_h-0002`). Expected cost rises to 911,226.986 and variance falls to 3.641285721e11, a third of the straight line's. The objective `E + lambda V` is 1,275,355.558.
- **The paper's printed figure.** Almgren and Chriss write that `kappa` is about 0.6 a day, so `kappa T` is about 3 (p. 24). The exact discrete `kappa` is 0.6070761632 and `kappa T` 3.0353808 (`ac_h-0005`); they agree to the one figure printed.
- **One trade.** With `N = 1` the whole position goes at once and `E = 562,500` (`ac_h-0004`). That is lower than the straight line's 662,500 although the trade is faster, because `eta_tilde` depends on the step length: with `tau = 5`, `eta_tilde = 1.875e-6`. Reusing the `tau = 1` value would give 662,500 by mistake.
- **The frontier.** Each `lambda` gives one (cost, variance) point. The two points here, (662,500, 1.083e12) and (911,227, 3.641e11), show the trade: about 250,000 dollars of expected cost buys two thirds less variance.

### The formal statement, checked against the spec

From [`10-execution/almgren-chriss.md`](../../specifications/10-execution/almgren-chriss.md), rulings HR-5 and HR-6, and [AC00] read in the December 2000 preprint (page numbers are the preprint's).

- Cost and variance of any trajectory: `E = 1/2 gamma X^2 + epsilon X + (eta_tilde / tau) sum n_k^2` (eq. (8), p. 11) and `V = sigma^2 tau sum x_k^2` (eq. (5), p. 10).
- Optimal trajectory: `x_j = X sinh(kappa (T - t_j)) / sinh(kappa T)` (eq. (17), p. 14), with `2 (cosh(kappa tau) - 1) = tau^2 lambda sigma^2 / eta_tilde` (eq. (16), p. 14).
- `lambda = 0` returns the straight line exactly, not as the limit of the `sinh` ratio (HR-5). `eta_tilde <= 0` is `E_DOMAIN` (`ac_h-0003`).

Evidence: `ac_h-0005` is checked against the paper's printed figure. `ac_h-0001`, `0002` and `0004` were re-derived blind by a second lane from the inputs only (DR-H2, 2026-11-15); one caveat, the `ac_h-0001` standard deviation was visible to that lane beforehand. No free library implements Almgren-Chriss, so there is no library cross-check.

## Step 2: the library call (shown, not run here)

```json
{"operation": "exec.ac.trajectory", "inputs": {"quantity": 1000000, "horizon": 5, "n_steps": 5, "sigma": 0.95, "epsilon": 0.0625, "eta": 2.5e-6, "gamma": 2.5e-7, "risk_aversion": 1e-6}}
```

Expected, from golden `ac_h-0002`: `kappa` 0.6070761632, `expected_cost` 911,226.986, `variance` 3.641285721e11. `exec.ac.frontier` takes `risk_aversions` as a list and returns one `(lambda, E, V)` per entry; the spec requires `E` non-decreasing and `V` non-increasing in `lambda`.

## For practitioners

- **The model is linear and static.** Linear temporary impact, an arithmetic Brownian price with no drift, and a schedule fixed at the start. Re-optimising as prices move is wave 2.
- **`lambda` has units.** It is per dollar of cost against dollars squared of variance. Compare `lambda` values only on the same position size.
- **The paper's "precisely twice" remark is not reproduced.** On p. 24 the paper says the no-trading standard deviation is twice that of the lowest frontier point; with this discrete grid the ratio is 2.04, so the spec does not use it.

## Common mistakes

- **Reusing `eta_tilde` across step lengths.** It depends on `tau`; see `ac_h-0004`.
- **Computing `kappa` with `acosh(1 + y)` for tiny `y`.** It loses digits; the spec uses a `log1p` form (HR-6). The script above uses `acosh`, which is fine at this `y`.
- **Reading the frontier as a forecast.** It is the trade-off under the model's assumptions, not a cost estimate for a real stock.

## What you just did

You reproduced the Almgren-Chriss test case: the straight line at zero risk aversion, the front-loaded `sinh` schedule at `lambda = 1e-6`, the paper's printed `kappa`, and two points of the frontier.

## Try next

- Read [Tutorial 38](tutorial-38-implementation-shortfall.md) to measure what a schedule actually cost after the fact.
- Read the [Almgren-Chriss frontier page](../curves/ac-frontier.md).

## References and further reading

- R. Almgren, N. Chriss, "Optimal execution of portfolio transactions", *Journal of Risk* 3(2), 2000/01, 5-39; read in the free December 2000 preprint.
- This project: [`10-execution/almgren-chriss.md`](../../specifications/10-execution/almgren-chriss.md); all sources in [References](../references.md).
