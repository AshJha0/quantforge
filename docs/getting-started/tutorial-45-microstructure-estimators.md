# Tutorial 45: estimate what the book is doing, with a standard error

<!-- tutorial:only python -->

The plain idea: a book has a few rates worth knowing. How often orders arrive, how fast resting orders are cancelled, how quickly the spread recovers after a shock, how fast depth thins away from the touch, and how far the mid moves after a trade of a given size. Each is estimated here by the simplest textbook method, and each comes with a standard error, so you can say whether an estimate is distinguishable from a planted value.

You will recompute seven estimator goldens by hand. Budget 10 minutes. The inputs are tiny hand cases; the real test of each estimator is the planted-truth recovery run in the spec.

<p class="note">Available from v0.10.0 (unreleased). The seven operations (`micro.est.arrival_rate`, `micro.est.cancel_rate`, `micro.est.resilience`, `micro.est.liquidity_decay`, `micro.est.adverse_selection`, `micro.est.regime_impact`, `micro.est.passive_vs_aggressive`) are specified and implemented on a branch not yet merged, so this page restates the spec's formulas in plain Python on the golden inputs. Every number is a golden from <code>specifications/09-microstructure/micro-estimators.md</code> (H-4b), hand calculations checked with mpmath by the spec lane, not yet blind re-derived. Method tests on simulated data only; no claim on real markets.</p>

Terms, defined here. **SE** is the standard error. **OLS through the origin** fits `y = beta x` with `beta = sum x y / sum x^2` and `SE = sqrt(s2 / sum x^2)`, `s2` the residual variance with `n - 1` degrees of freedom. **Resilience** `kappa` is the rate at which the spread `S_t` returns to its resting level `S_inf`; **liquidity decay** `alpha` the rate at which depth falls per tick from the touch; `lambda_as` the mid move per unit of signed traded size (adverse selection).

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`. The script uses the Python standard library only.

## Step 1: check the goldens by hand

<!-- tutorial:run python -->
```python
# Microstructure estimators restated from the spec, goldens mest_h-0001, 0003, 0005, 0007, 0008, 0009, 0010.
import math


def ols_origin(x, y):
    sxx = sum(a * a for a in x)
    beta = sum(a * b for a, b in zip(x, y)) / sxx
    s2 = sum((b - beta * a) ** 2 for a, b in zip(x, y)) / (len(x) - 1)
    return beta, math.sqrt(s2 / sxx)


def ols_slope(t, z):
    n, mt, mz = len(t), sum(t) / len(t), sum(z) / len(z)
    stt = sum((a - mt) ** 2 for a in t)
    slope = sum((a - mt) * (b - mz) for a, b in zip(t, z)) / stt
    rss = sum((b - mz - slope * (a - mt)) ** 2 for a, b in zip(t, z))
    return slope, math.sqrt(rss / (n - 2) / stt)


lam = 12 / 4
print(f"mest_h-0001 arrival: lambda {lam:g} se {math.sqrt(lam / 4):.15g}")
orders = [(2, "CANCEL"), (3, "FILL"), (5, "CANCEL")]
c = sum(o == "CANCEL" for _, o in orders)
theta = c / sum(life for life, _ in orders)
print(f"mest_h-0003 cancel: theta {theta:g} se {theta / math.sqrt(c):.15g}")
slope, se = ols_slope([0, 1, 2], [math.log(s - 1) for s in (5, 3, 2)])
print(f"mest_h-0005 resilience: kappa {-slope:.15g} se {abs(se):.0f}")
slope, se = ols_slope([0, 1, 2, 3], [math.log(d) for d in (800, 400, 200, 100)])
print(f"mest_h-0007 liquidity decay: alpha {-slope:.15g} se {abs(se):.0f}")
b, se = ols_origin([1, -1, 2], [0.02, -0.01, 0.05])
print(f"mest_h-0008 adverse selection: lambda_as {b:.15g} se {se:.15g}")
calm, _ = ols_origin([1, 2], [0.01, 0.02])
stressed, se = ols_origin([1, -1, 1], [0.05, -0.03, 0.04])
print(f"mest_h-0009 regimes: calm {calm:.15g} stressed {stressed:.15g} se {se:.15g} ratio {stressed / calm:.15g}")
p, a = [-1, -0.5, 0], [1, 1.5, 2]


def mean(v):
    return sum(v) / len(v)


def var(v):
    return sum((x - mean(v)) ** 2 for x in v) / (len(v) - 1)


print(f"mest_h-0010 passive vs aggressive: delta {mean(a) - mean(p):g} se {math.sqrt(var(a) / 3 + var(p) / 3):.15g} bp")
```

Output (CI checks these lines):

<!-- tutorial:expect -->
```text
mest_h-0001 arrival: lambda 3 se 0.866025403784439
mest_h-0003 cancel: theta 0.2 se 0.14142135623731
mest_h-0005 resilience: kappa 0.693147180559945 se 0
mest_h-0007 liquidity decay: alpha 0.693147180559945 se 0
mest_h-0008 adverse selection: lambda_as 0.0216666666666667 se 0.00390867979985286
mest_h-0009 regimes: calm 0.01 stressed 0.04 se 0.00577350269189626 ratio 4
mest_h-0010 passive vs aggressive: delta 2 se 0.408248290463863 bp
```

### Reading the numbers

- **Arrival rate.** 12 orders in 4 seconds is 3 a second; for a Poisson count the SE is `sqrt(lambda / T)`, 0.866 (`mest_h-0001`).
- **Cancel rate.** Two cancels over 10 seconds of total resting life is 0.2 a second. The filled order still counts its 3 seconds of exposure: a fill censors the lifetime, it does not remove it (`mest_h-0003`).
- **Resilience and decay.** The spread excess 4, 2, 1 halves each second, and depth 800, 400, 200, 100 halves each tick, so both rates are `ln 2` with zero residual (`mest_h-0005`, `0007`, exact fits by ruling HR-74).
- **Adverse selection.** Signed sizes 1, -1, 2 against mid moves 0.02, -0.01, 0.05 give 13/600 per unit (`mest_h-0008`).
- **Regimes.** The same fit per label: calm 0.01, stressed 0.04, ratio 4 (`mest_h-0009`).
- **Passive against aggressive.** Mean costs -0.5 bp and 1.5 bp differ by 2 bp, Welch SE 0.408 (`mest_h-0010`).

### The formal statement, checked against the spec

From `specifications/09-microstructure/micro-estimators.md` (available from v0.10.0; rulings HR-70, HR-71, HR-74).

- Arrival `lambda = N / T`, `SE = sqrt(lambda / T)`; cancel `theta = C / sum L_i`, `SE = theta / sqrt(C)`.
- Resilience: OLS with intercept of `ln(S_i - S_inf)` on `t_i`, `kappa = -slope`, slope SE with `n - 2` degrees of freedom; liquidity decay is the same with `k` for `t` and `S_inf = 0`.
- Recovery test (HR-70): on a simulated book with a planted value and a fixed seed (20261118 + j for test j), the estimate must lie within 3 SE of the truth; a coverage run over 200 seeds allows at most 4 misses per estimator.

## For practitioners

- **The SE is only as good as the model.** Poisson arrivals and exponential cancels are the simplest choices; real order flow clusters (Hawkes arrivals), and a cancel depends on queue position. The spec lists both as not covered.
- **Exact fits have SE 0.** That is a property of the hand cases, not a claim of certainty; on the planted runs the SE is positive.

## Common mistakes

- **Dropping filled orders from the cancel rate.** It biases `theta` upward: the fills' time at risk is part of the denominator.
- **Fitting resilience without knowing `S_inf`.** The method takes it as an input; a wrong `S_inf` bends the log line and the slope means nothing.

## What you just did

You recomputed seven microstructure estimates with their standard errors and saw which data feed each one.

## Try next

- Add a fourth point (3, 1.5) to the resilience case and predict whether `kappa` rises or falls before you run it.

## References and further reading

- This project: the spec above; all sources in [References](../references.md). No number on this page comes from a paper.
