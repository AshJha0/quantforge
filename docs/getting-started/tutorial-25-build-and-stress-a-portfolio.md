# Tutorial 25: build and stress a portfolio: shrinkage, views, mean-variance, risk parity

The plain idea: building a portfolio takes two estimates and one choice. The estimates are how the assets move together (a covariance matrix) and what each is expected to return; the choice is how much risk to take for that return. Both estimates are noisy, and an optimiser leans hardest on exactly the noisiest parts, so the useful habits are to pull the estimates towards something sensible before optimising and, after optimising, to ask where the portfolio's risk actually sits.

You will shrink two small sample covariance matrices with Ledoit-Wolf, recover a set of market weights from the returns they imply, move those returns towards one view with Black-Litterman, optimise with no limits, long-only and with a cap, split each portfolio's volatility into one piece per asset, and build two risk-parity portfolios. Python first, then the same cases through the Rust, Java and C++ command-line programs. Budget 15 minutes. All data is synthetic and none of it is a forecast.

Terms, defined here. A **weight** is the fraction of capital in an asset; weights sum to 1, and a negative weight is a short position. The **covariance matrix** `Sigma` has each asset's variance on the diagonal and the covariances off it; volatility is the square root of a variance. **Shrinkage** replaces an estimate by a weighted average of it and a simpler target. A **view** is an investor's statement about returns, such as "asset 1 will beat asset 2 by 8 % a year", with a stated uncertainty. A **risk contribution** is the part of the portfolio's volatility that one asset accounts for; the parts add up to the whole.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/), as in [Tutorial 1](tutorial-1-swap.md): `uv sync --locked --project python`.
- For step 2, the three builds made in Tutorial 1. [Tutorial 18](tutorial-18-minvar-qp.md), the minimum-variance hedge, uses the same kind of quadratic problem and is useful but not required.

## Step 1: Python

The script `examples/tutorials/t25_portfolio.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t25_portfolio.py -->
```python
"""Tutorial 25: build and stress a portfolio. Ledoit-Wolf shrinkage, a Black-Litterman view,
mean-variance with bounds, Euler risk contributions and risk parity.

  uv run --project python python examples/tutorials/t25_portfolio.py         # Python
  python examples/tutorials/t25_portfolio.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-25-build-and-stress-a-portfolio.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import math
import sys

from qf import connect


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def nums(values, places):
    return " ".join(num(x, places) for x in values)


def correlation(c, i, j):
    return c[i][j] / math.sqrt(c[i][i] * c[j][j])


def main(cli):
    call = connect(cli)  # the Python package with no arguments, else that build's batch command

    # 1. Ledoit-Wolf. Four rows, two assets: small enough to do by hand.
    r = call("research.estimate.ledoit_wolf", {"returns": [[2, 1], [-2, -1], [1, -1], [-1, 1]]})
    print(f"LW 4 x 2: shrinkage {num(r['shrinkage'], 4)}  m {num(r['mu'], 4)}"
          f"  covariance diagonal {nums([r['covariance'][0][0], r['covariance'][1][1]], 4)}")
    # Six monthly returns, in percent, of three assets. The sample covariance has divisor T (J-W2-7).
    returns = [[2.0, 1.0, 0.5], [-1.0, 0.5, 1.5], [3.0, -0.5, -1.0],
               [-2.0, 1.5, 2.0], [1.0, 0.0, 0.5], [-3.0, 1.5, 2.5]]
    r = call("research.estimate.ledoit_wolf", {"returns": returns})
    t = len(returns)
    mean = [sum(row[k] for row in returns) / t for k in range(3)]
    sample = [[sum((row[i] - mean[i]) * (row[j] - mean[j]) for row in returns) / t for j in range(3)]
              for i in range(3)]
    print(f"LW 6 x 3: shrinkage {num(r['shrinkage'], 4)}  m {num(r['mu'], 4)}"
          f"  correlation 1-3 sample {num(correlation(sample, 0, 2), 4)}"
          f" shrunk {num(correlation(r['covariance'], 0, 2), 4)}")

    # 2. The prior: the returns that make the market weights optimal, pi = delta Sigma w_mkt.
    sigma = [[0.04, 0.006, 0.0], [0.006, 0.01, 0.003], [0.0, 0.003, 0.0225]]  # vols 20 %, 10 %, 15 %
    w_mkt, delta = [0.5, 0.3, 0.2], 2.5
    prior = [delta * sum(sigma[i][j] * w_mkt[j] for j in range(3)) for i in range(3)]
    wide = {"lower": [-10.0] * 3, "upper": [10.0] * 3}
    r = call("research.portfolio.mean_variance", {"expected_returns": prior, "covariance": sigma,
                                                  "risk_aversion": delta, **wide})
    print(f"prior returns {nums(prior, 4)}  optimal weights {nums(r['weights'], 4)}")

    # 3. Black-Litterman: one view, asset 1 beats asset 2 by 8 % a year, with variance 0.0002.
    r = call("research.estimate.black_litterman", {"covariance": sigma, "prior_returns": prior,
                                                   "pick": [[1, -1, 0]], "views": [0.08],
                                                   "view_covariance": [[0.0002]], "tau": 0.05})
    post = r["posterior_returns"]
    print(f"posterior returns {nums(post, 4)}  spread 1-2 prior {num(prior[0] - prior[1], 4)}"
          f" posterior {num(post[0] - post[1], 4)}")

    # 4. Mean-variance on the posterior: no limits, long-only, then long-only with asset 1 capped at 60 %.
    bounds = (("no limits", wide), ("long-only", {}), ("cap 60 %", {"upper": [0.6, 1.0, 1.0]}))
    held = {}
    for name, limits in bounds:
        r = call("research.portfolio.mean_variance", {"expected_returns": post, "covariance": sigma,
                                                      "risk_aversion": delta, **limits})
        held[name] = r["weights"]
        print(f"mean-variance {name}: weights {nums(r['weights'], 4)}  at_bound {r['at_bound']}"
              f"  return {num(r['expected_return'], 4)}  vol {num(r['volatility'], 4)}")

    # 5. Where the risk is: Euler contributions of the market weights and of the capped portfolio.
    for name, w in (("market", w_mkt), ("cap 60 %", held["cap 60 %"])):
        r = call("risk.contrib.euler", {"weights": w, "covariance": sigma})
        print(f"Euler {name}: vol {num(r['volatility'], 4)}  contributions {nums(r['contributions'], 4)}"
              f"  shares {nums(r['shares'], 4)}")

    # 6. Risk parity: equal risk shares, then half the risk budget on asset 1.
    for budgets in ([1 / 3, 1 / 3, 1 / 3], [0.5, 0.25, 0.25]):
        r = call("research.portfolio.risk_parity", {"covariance": sigma, "budgets": budgets})
        shares = [c / r["volatility"] for c in r["contributions"]]
        print(f"risk parity budgets {nums(budgets, 2)}: weights {nums(r['weights'], 4)}"
              f"  shares {nums(shares, 4)}")


if __name__ == "__main__":
    main(sys.argv[1:])
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t25_portfolio.py
```

Real output, 2026-11-14, Windows 11 (Python build):

<!-- tutorial:expect -->
```text
LW 4 x 2: shrinkage 1.0000  m 1.7500  covariance diagonal 1.7500 1.7500
LW 6 x 3: shrinkage 0.1811  m 2.1852  correlation 1-3 sample -0.9688 shrunk -0.7901
prior returns 0.0545 0.0165 0.0135  optimal weights 0.5000 0.3000 0.2000
posterior returns 0.0885 0.0125 0.0105  spread 1-2 prior 0.0380 posterior 0.0760
mean-variance no limits: weights 0.9000 -0.1000 0.2000  at_bound [0, 0, 0]  return 0.0805  vol 0.1794
mean-variance long-only: weights 0.8592 0.0000 0.1408  at_bound [0, -1, 0]  return 0.0775  vol 0.1731
mean-variance cap 60 %: weights 0.6000 0.1887 0.2113  at_bound [1, 0, 0]  return 0.0577  vol 0.1318
Euler market: vol 0.1182  contributions 0.0923 0.0168 0.0091  shares 0.7808 0.1418 0.0774
Euler cap 60 %: vol 0.1318  contributions 0.1145 0.0088 0.0085  shares 0.8687 0.0665 0.0648
risk parity budgets 0.33 0.33 0.33: weights 0.2387 0.4302 0.3311  shares 0.3333 0.3333 0.3333
risk parity budgets 0.50 0.25 0.25: weights 0.3227 0.3717 0.3056  shares 0.5000 0.2500 0.2500
```

### Reading the numbers

- **Ledoit-Wolf, by hand.** Four rows `(2, 1), (-2, -1), (1, -1), (-1, 1)` have zero means, so the sample covariance with divisor `T = 4` is `S = [[2.5, 0.5], [0.5, 1]]` and the target level is `m = tr S / N = 1.75`. The distance of `S` from `m I` is `d^2 = (0.75^2 + 0.5^2 + 0.5^2 + 0.75^2) / 2 = 0.8125`. Each row's `x x' - S` has squared size 6.75, so `bbar^2 = 4 x 6.75 / 16 / 2 = 0.84375`, which is larger than `d^2`; `b^2` is capped at `d^2` and the shrinkage `delta = b^2 / d^2` is exactly 1. With four observations of two assets the estimator throws the sample away and keeps `1.75 I`.
- **Ledoit-Wolf, a short history.** Six months of three assets give `delta = 0.1811`: the output is `0.1811 x 2.1852 I + 0.8189 S`. Off-diagonal entries shrink by the factor 0.8189 and the variances move towards 2.1852, so the sample correlation of assets 1 and 3, -0.9688, becomes -0.7901. Six months cannot support a correlation that close to -1; the shrunk value is the more cautious input for an optimiser.
- **The prior.** For the covariance on the page (volatilities 20 %, 10 % and 15 %), market weights `(0.5, 0.3, 0.2)` and risk aversion 2.5, `Sigma w = (0.0218, 0.0066, 0.0054)` and `pi = 2.5 Sigma w = (0.0545, 0.0165, 0.0135)`. Mean-variance with `gamma = 2.5` and no binding limits returns `(0.5, 0.3, 0.2)` exactly: the optimality condition `pi - gamma Sigma w - nu 1 = 0` holds with `nu = 0`. This round trip is the check that prior and optimiser use the same conventions.
- **One view.** The prior expects asset 1 to beat asset 2 by 0.038; the view says 0.08 with variance 0.0002. The prior's uncertainty about that spread is `tau P Sigma P' = 0.05 x (0.04 + 0.01 - 2 x 0.006) = 0.0019`, so the posterior spread is the precision-weighted average `(0.0002 x 0.038 + 0.0019 x 0.08) / 0.0021 = 0.0760`. Every asset moves by `tau Sigma P'` times `(0.08 - 0.038) / 0.0021 = 20`, that is by `(0.034, -0.004, -0.003)`, giving `(0.0885, 0.0125, 0.0105)`. Asset 3 moves too, because it is correlated with asset 2.
- **No limits.** The weights move from `(0.5, 0.3, 0.2)` to `(0.9, -0.1, 0.2)`: by `0.4 x (1, -1, 0)`, where `0.4 = tau x 20 / gamma = 0.05 x 20 / 2.5`. A Black-Litterman portfolio differs from the market portfolio only along the rows of `P`, so asset 3, about which there is no view, keeps 0.2. The optimiser wants a 10 % short in asset 2.
- **Long-only.** The short is not allowed, asset 2 sits at its lower bound (`at_bound -1`) and the other two share the budget. With `w_2 = 0`, equal marginal utility for the two free assets, `0.0885 - 2.5 x 0.04 w_1 = 0.0105 - 2.5 x 0.0225 (1 - w_1)`, gives `w_1 = 0.13425 / 0.15625 = 0.8592`.
- **A 60 % cap.** Asset 1 is now at its upper bound (`at_bound 1`) and assets 2 and 3 share 0.4. The same condition for those two gives `w_2 = 0.005 / 0.0265 = 10/53 = 0.1887`. The expected return falls from 0.0775 to 0.0577 and the volatility from 0.1731 to 0.1318.
- **Euler contributions.** For the market weights, `w' Sigma w = 0.01396` and the volatility is 0.1182; asset 1's contribution is `0.5 x 0.0218 / 0.1182 = 0.0923`, and the three contributions add up to 0.1182. Asset 1 holds half the capital but 78.1 % of the risk; under the 60 % cap it holds 86.9 %. A cap on weight is not a cap on risk.
- **Risk parity.** Equal risk shares need the most capital in the least volatile asset: `(0.2387, 0.4302, 0.3311)`, volatility 0.0932, each asset one third of it. Giving asset 1 half of the risk budget raises its weight to 0.3227 only, because its volatility is twice asset 2's. Expected returns play no part.

### The formal statement, checked against the spec

From [`07-portfolio/estimation.md`](../../specifications/07-portfolio/estimation.md) (rulings J-W2-7 and J-W2-8) and [`07-portfolio/optimisation.md`](../../specifications/07-portfolio/optimisation.md) (J-W2-2 to J-W2-6).

Ledoit-Wolf [LW04], scaled-identity target: demean each column; `S = (1/T) sum_t x_t x_t'`; `m = tr S / N`; `d^2 = ||S - m I||^2 / N`; `bbar^2 = (1/T^2) sum_t ||x_t x_t' - S||^2 / N`; `b^2 = min(bbar^2, d^2)`; `delta = b^2 / d^2` (0 when `b^2 = 0`); output `delta m I + (1 - delta) S`. These are scikit-learn's conventions with `assume_centered = False`.

Black-Litterman [BL92, HL99]: posterior mean `pi + tau Sigma P' (P tau Sigma P' + Omega)^-1 (q - P pi)`; `posterior_covariance = tau Sigma - tau Sigma P' (P tau Sigma P' + Omega)^-1 P tau Sigma`, the uncertainty of the mean; `predictive_covariance = Sigma + posterior_covariance`. The prior `pi` is an input; the reverse optimisation `pi = delta Sigma w_mkt` is done by the caller, as in the script.

Mean-variance [Mar52]: maximise `mu'w - (gamma/2) w' Sigma w` subject to `sum w = 1` and `lower <= w <= upper` (defaults 0 and 1), `Sigma` symmetric positive definite, so the optimum is unique. At the optimum, with `g_i = mu_i - gamma (Sigma w)_i - nu`, a free asset has `g_i = 0`, one at its lower bound `g_i <= 0` and one at its upper bound `g_i >= 0`; `at_bound` reports which.

Risk parity [Spinu13, Roncalli13]: long-only weights with `w_i (Sigma w)_i / (w' Sigma w) = b_i / sum b`, found by solving `Sigma y = b / y` for `y > 0` and setting `w = y / sum y`.

Euler contributions [Tas99]: `sigma = sqrt(w' Sigma w)`, marginal `(Sigma w) / sigma`, contribution `w_i (Sigma w)_i / sigma`, share `contribution / sigma`. Because `sigma(c w) = c sigma(w)`, Euler's theorem makes the contributions add up to `sigma` exactly.

The checks behind the goldens (`optim_j`, `estim_j`): an exact KKT certificate for every mean-variance case and agreement with scipy SLSQP; every bound pattern enumerated for `N <= 4`; Ledoit-Wolf and Black-Litterman each computed in two algebraic forms that must agree in exact arithmetic (ruling J-W2-15). A run of scikit-learn's `ledoit_wolf` on the `estim_j` cases is still open.

## Step 2: the same in Rust, Java and C++

`examples/tutorials/t25_portfolio.py` sends the same cases (two `research.estimate.ledoit_wolf`, four `research.portfolio.mean_variance`, one `research.estimate.black_litterman`, two `risk.contrib.euler`, two `research.portfolio.risk_parity`) to whichever CLI you name and prints the same lines.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t25_portfolio.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t25_portfolio.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t25_portfolio.py cpp26/build/quantforge
```

Each is to print the eleven lines of step 1, digit for digit; the Rust, Java and C++ runs of this page are checked by CI once the wave 2 builds are merged. The full checks are `python conformance/runner/runner.py --impl rust --suite optim_j` and `--suite estim_j`.

## For practitioners

- **Shrink before you optimise.** The sample covariance of `N` assets from `T` periods is singular when `T <= N` and badly conditioned when `T` is not much larger. Mean-variance divides by it, in effect, so its smallest eigenvalues drive the weights. Ledoit-Wolf costs nothing to run.
- **Expected returns matter far more than covariances.** Small changes in `mu` move mean-variance weights a lot. Starting from the market-implied prior and adding a few views with honest uncertainty keeps the result near a portfolio someone would hold.
- **`tau` and `Omega` together set the strength of a view.** Only the ratio of `Omega` to `tau P Sigma P'` matters for the posterior mean. Choose them once, write the choice down, and do not tune them until the backtest looks good.
- **Look at risk shares, not weights.** A portfolio that looks balanced by weight can be concentrated by risk: asset 1 here has half the capital and 78 % of the risk. Risk parity starts from the risk side instead.
- **Constraints are part of the model.** Long-only and caps change the answer more than most estimation choices; report them with the weights.

## Common mistakes

- **Passing volatilities where covariances are expected.** `Sigma` holds variances on the diagonal: 0.04 for 20 % volatility, not 0.2.
- **Mixing periods.** Monthly returns give a monthly covariance; annual expected returns need an annual covariance. Scale before you combine.
- **Expecting Black-Litterman to touch assets without views.** It moves them only through their correlation with the assets in the views, as asset 3 shows.
- **Reading a negative Euler contribution as an error.** A hedge reduces volatility at the margin and has a negative contribution; the contributions still add up to `sigma`.
- **Budgets that do not sum to 1.** Risk parity rejects them with `E_DOMAIN` rather than rescaling silently (ruling J-W2-5).

## What you just did

You saw Ledoit-Wolf discard a four-row sample entirely and shrink a six-row one by 18 %, recovered the market weights from their implied returns, moved those returns with one view to a spread of 0.0760, watched long-only and a cap push assets to their bounds, found that half the capital carried 78 % of the risk, and built risk-parity portfolios with equal and unequal budgets.

## Try next

- Halve `Omega` and predict the new spread before you run it.
- Add a second view, on asset 3 alone, as a second row of `P`, and check which weights move.
- Feed the shrunk covariance of the six-row history into risk parity and compare the weights with those from the sample covariance.
- Read [LEARN, stage J](../../LEARN.md#stage-j-backtest-overfitting-and-research-statistics), the [COOKBOOK stage J recipes](../../COOKBOOK.md#stage-j-recipes) and [Tutorial 26](tutorial-26-test-es-and-fit-regimes.md), which backtests an expected-shortfall model.

## References and further reading

The specs list these as sources; "not opened" there means the spec authors cited them from memory.

- H. Markowitz, "Portfolio selection", *Journal of Finance* 7(1), 1952, 77-91. Not opened per the spec.
- O. Ledoit, M. Wolf, "A well-conditioned estimator for large-dimensional covariance matrices", *Journal of Multivariate Analysis* 88(2), 2004, 365-411. Not opened per the spec.
- F. Black, R. Litterman, "Global portfolio optimization", *Financial Analysts Journal* 48(5), 1992, 28-43. Not opened per the spec.
- G. He, R. Litterman, "The intuition behind Black-Litterman model portfolios", Goldman Sachs working paper, 1999. Not opened per the spec.
- S. Maillard, T. Roncalli, J. Teiletche, "The properties of equally weighted risk contribution portfolios", *Journal of Portfolio Management* 36(4), 2010, 60-70. Not opened.
- F. Spinu, "An algorithm for computing risk parity weights", SSRN 2297383, 2013. Not opened per the spec.
- D. Tasche, "Risk contributions and performance measurement", working paper, TU Munich, 1999. Not opened per the spec.
- This project: [`07-portfolio/optimisation.md`](../../specifications/07-portfolio/optimisation.md), [`07-portfolio/estimation.md`](../../specifications/07-portfolio/estimation.md), rulings in [`stage-j-rulings-w2.md`](../../specifications/stage-j-rulings-w2.md), all sources in [References](../references.md).
