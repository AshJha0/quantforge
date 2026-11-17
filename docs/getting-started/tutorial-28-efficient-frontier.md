# Tutorial 28: the efficient frontier and what a constraint costs

The plain idea: mean-variance optimisation does not give one portfolio, it gives a family of them, one for each attitude to risk. Plotting their expected returns against their volatilities traces the efficient frontier. A constraint such as "no short sales" removes part of the frontier, and the honest way to say what that costs is in return: how much expected return, after a charge for risk, the investor gives up by obeying the rule. Where the constraint does not bind, it costs nothing.

You will trace the frontier of four assets at five levels of risk aversion with and without short sales, read which long-only bounds bind, approach the minimum-variance portfolio and check its risk shares, and price the long-only rule in basis points a year. Python first, then the same cases through the Rust, Java and C++ command-line programs. Budget 15 minutes. All inputs are invented round numbers, not estimates of any market.

Terms, defined here. **Risk aversion** `gamma` is the price the investor puts on variance: the optimiser maximises `mu'w - (gamma/2) w' Sigma w`. That objective is the **certainty-equivalent return**, the riskless return the investor would accept instead of the portfolio. The **minimum-variance portfolio** is the fully invested portfolio with the lowest volatility, whatever the expected returns. A **binding** constraint is one the optimum sits on; removing it would change the answer.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/), as in [Tutorial 1](tutorial-1-swap.md): `uv sync --locked --project python`.
- For step 2, the three builds made in Tutorial 1. [Tutorial 25](tutorial-25-build-and-stress-a-portfolio.md) introduces mean-variance and Euler contributions and is useful first.

## Step 1: Python

The script `examples/tutorials/t28_frontier.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t28_frontier.py -->
```python
"""Tutorial 28: the efficient frontier and what constraints cost. Mean-variance across risk
aversion with and without short sales, the minimum-variance portfolio, Euler shares along the way.

  uv run --project python python examples/tutorials/t28_frontier.py         # Python
  python examples/tutorials/t28_frontier.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-28-efficient-frontier.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import sys

from qf import connect


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def nums(values, places):
    return " ".join(num(x, places) for x in values)


# Four assets, annual units: volatilities 20 %, 15 %, 10 % and 5 %; expected returns 8 %, 7 %, 3 %, 2 %.
SIGMA = [[0.0400, 0.0180, 0.0040, 0.0000],
         [0.0180, 0.0225, 0.0030, 0.0005],
         [0.0040, 0.0030, 0.0100, 0.0010],
         [0.0000, 0.0005, 0.0010, 0.0025]]
MU = [0.08, 0.07, 0.03, 0.02]
FREE = {"lower": [-10.0] * 4, "upper": [10.0] * 4}


def main(cli):
    call = connect(cli)

    # 1. The frontier: one portfolio per risk aversion, short sales allowed and long-only.
    for gamma in (1.0, 2.5, 5.0, 20.0, 1000.0):
        line = [f"gamma {num(gamma, 1):>6}:"]
        for name, limits in (("free", FREE), ("long-only", {})):
            r = call("research.portfolio.mean_variance", {"expected_returns": MU, "covariance": SIGMA,
                                                          "risk_aversion": gamma, **limits})
            line.append(f"{name} return {num(r['expected_return'], 4)} vol {num(r['volatility'], 4)}")
        print("  ".join(line))

    # 2. The long-only weights and which bounds bind.
    for gamma in (1.0, 5.0, 1000.0):
        r = call("research.portfolio.mean_variance", {"expected_returns": MU, "covariance": SIGMA,
                                                      "risk_aversion": gamma})
        print(f"long-only gamma {num(gamma, 1)}: weights {nums(r['weights'], 4)}  at_bound {r['at_bound']}")

    # 3. Very high risk aversion approaches the minimum-variance portfolio, whose Euler shares equal its weights;
    # at gamma 1000 they are close but not equal.
    r = call("research.portfolio.mean_variance", {"expected_returns": MU, "covariance": SIGMA,
                                                  "risk_aversion": 1000.0, **FREE})
    e = call("risk.contrib.euler", {"weights": r["weights"], "covariance": SIGMA})
    print(f"near minimum variance: weights {nums(r['weights'], 4)}  Euler shares {nums(e['shares'], 4)}")

    # 4. What the long-only rule costs at gamma 1, where it binds, in certainty-equivalent return mu'w - gamma/2 w'Sigma w.
    ce = {}
    for name, limits in (("free", FREE), ("long-only", {})):
        r = call("research.portfolio.mean_variance", {"expected_returns": MU, "covariance": SIGMA,
                                                      "risk_aversion": 1.0, **limits})
        ce[name] = r["expected_return"] - 0.5 * r["volatility"] ** 2
    print(f"certainty equivalent at gamma 1: free {num(ce['free'], 4)}  long-only {num(ce['long-only'], 4)}"
          f"  cost of the constraint {num(10000 * (ce['free'] - ce['long-only']), 1)} bp a year")


if __name__ == "__main__":
    main(sys.argv[1:])
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t28_frontier.py
```

Real output, 2026-11-15, Windows 11 (Python build):

<!-- tutorial:expect -->
```text
gamma    1.0:  free return 0.1420 vol 0.3455  long-only return 0.0755 vol 0.1597
gamma    2.5:  free return 0.0716 vol 0.1447  long-only return 0.0703 vol 0.1411
gamma    5.0:  free return 0.0482 vol 0.0829  long-only return 0.0482 vol 0.0829
gamma   20.0:  free return 0.0306 vol 0.0497  long-only return 0.0306 vol 0.0497
gamma 1000.0:  free return 0.0249 vol 0.0467  long-only return 0.0249 vol 0.0467
long-only gamma 1.0: weights 0.5472 0.4528 0.0000 0.0000  at_bound [0, 0, -1, -1]
long-only gamma 5.0: weights 0.1644 0.3436 0.1163 0.3757  at_bound [0, 0, 0, 0]
long-only gamma 1000.0: weights 0.0234 0.0469 0.1136 0.8160  at_bound [0, 0, 0, 0]
near minimum variance: weights 0.0234 0.0469 0.1136 0.8160  Euler shares 0.0240 0.0479 0.1139 0.8141
certainty equivalent at gamma 1: free 0.0823  long-only 0.0627  cost of the constraint 195.5 bp a year
```

### Reading the numbers

- **The free frontier is a straight line in `1/gamma`.** With only the budget constraint, `w(gamma) = w_mv + (1/gamma) z`, where `w_mv` is the minimum-variance portfolio and `z` a fixed self-financing tilt. So the expected return is `r_mv + c / gamma`. From the `gamma 1` and `gamma 1000` lines, `c` is about 0.1172 and `r_mv` about 0.0248; that predicts 0.0717 at `gamma 2.5` (printed 0.0716), 0.0482 at 5 and 0.0306 at 20. You can check a frontier without an optimiser.
- **Long-only binds only at low risk aversion.** At `gamma 1` the free portfolio wants a volatility of 34.6 %, which needs short positions in the two low-return assets; long-only stops at 16.0 %. At `gamma 2.5` the two differ in the fourth digit, and from `gamma 5` on they are the same portfolio, because the free optimum already has no shorts.
- **Which bounds bind.** At `gamma 1` the long-only weights are `(0.5472, 0.4528, 0, 0)`, and `at_bound` marks assets 3 and 4 at their lower bound (-1). At `gamma 5` and above no bound binds, and every `at_bound` entry is 0.
- **The minimum-variance end.** At `gamma 1000` the weights are 82 % in the 5 % volatility asset. For the exact minimum-variance portfolio `Sigma w = lambda 1` for some `lambda`, so each asset's Euler share `w_i (Sigma w)_i / (w' Sigma w)` equals its weight. At `gamma 1000` the shares (0.0240, 0.0479, 0.1139, 0.8141) are close to the weights but not equal, because the return term still tilts the portfolio slightly.
- **The price of the rule.** At `gamma 1` the free portfolio's certainty equivalent is `0.1420 - 0.5 x 0.3455^2 = 0.0823`; long-only gives `0.0755 - 0.5 x 0.1597^2 = 0.0627`. The investor gives up 195.5 bp a year by not shorting. At `gamma 5`, where the constraint does not bind, the cost is zero.

### The formal statement, checked against the spec

From [`07-portfolio/optimisation.md`](../../specifications/07-portfolio/optimisation.md) (rulings J-W2-2 to J-W2-6 in [`stage-j-rulings-w2.md`](../../specifications/stage-j-rulings-w2.md)). Mean-variance [Mar52]: maximise `mu'w - (gamma/2) w' Sigma w` subject to `sum w = 1` and `lower <= w <= upper` (defaults 0 and 1), with `Sigma` symmetric positive definite, so the optimum is unique. At the optimum, with `g_i = mu_i - gamma (Sigma w)_i - nu`, a free asset has `g_i = 0`, one at its lower bound `g_i <= 0` and one at its upper bound `g_i >= 0`; `at_bound` reports -1, 0 or 1. Euler contributions [Tas99]: `sigma = sqrt(w' Sigma w)`, contribution `w_i (Sigma w)_i / sigma`, share `contribution / sigma`, adding up to `sigma` and to 1 respectively.

Without bounds the first-order condition is `mu - gamma Sigma w - nu 1 = 0`, so `w = Sigma^-1 (mu - nu 1) / gamma` with `nu` fixed by the budget; writing it out gives `w_mv = Sigma^-1 1 / (1' Sigma^-1 1)` plus a term in `1/gamma`, the straight line used above. The script widens the bounds to plus or minus 10 to stand in for "no bounds"; none of them binds.

## Step 2: the same in Rust, Java and C++

`examples/tutorials/t28_frontier.py` sends the same cases (sixteen `research.portfolio.mean_variance`, one `risk.contrib.euler`) to whichever CLI you name and prints the same lines.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t28_frontier.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t28_frontier.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t28_frontier.py cpp26/build/quantforge
```

Each is to print the ten lines of step 1, digit for digit. The full check is `python conformance/runner/runner.py --impl rust --suite optim_j`.

## For practitioners

- **Price constraints in certainty-equivalent return.** "Long-only costs 195 bp a year at this risk aversion, nothing at a higher one" is a statement a committee can act on; a table of weights is not.
- **A constraint that binds hides a view.** Whatever pushed the optimiser to its bound, usually an expected return, is still there. Look at the multipliers (the sign of `g_i`) before relaxing a limit.
- **Most real portfolios live where the constraints bind.** With noisy expected returns the free optimum often has large offsetting positions; long-only and caps act as crude shrinkage.
- **Check the frontier is monotone.** Return and volatility should both fall as `gamma` rises. If they do not, the inputs (often a covariance that is not positive definite) are wrong.

## Common mistakes

- **Comparing portfolios at different risk aversions by return alone.** The higher return comes with more risk; compare certainty equivalents at one `gamma`.
- **Reading `at_bound 0` as "unconstrained".** It means that asset is strictly inside its bounds; the budget constraint still applies.
- **Expecting minimum variance to ignore the covariance between assets.** It does not hold the lowest-volatility asset alone; correlation lets other assets lower the total.
- **Mixing monthly covariances with annual expected returns.** Scale both to the same period before optimising.

## What you just did

You traced a four-asset frontier at five risk aversions, checked it against the straight line in `1/gamma`, saw long-only bind at `gamma 1` and stop mattering from `gamma 5`, read which bounds bound, approached the minimum-variance portfolio and its risk shares, and priced the long-only rule at 195.5 bp a year.

## Try next

- Cap every weight at 40 % and price that constraint at `gamma 2.5`.
- Raise the expected return of asset 4 to 4 % and predict which `at_bound` entries change at `gamma 1`.
- Use the minimum-variance weights as the market portfolio of [Tutorial 29](tutorial-29-view-confidence.md) and see what prior returns they imply.

## References and further reading

- H. Markowitz, "Portfolio selection", *Journal of Finance* 7(1), 1952, 77-91. Not opened per the spec.
- D. Tasche, "Risk contributions and performance measurement", working paper, TU Munich, 1999. Not opened per the spec.
- This project: [`07-portfolio/optimisation.md`](../../specifications/07-portfolio/optimisation.md), [Tutorial 25](tutorial-25-build-and-stress-a-portfolio.md), all sources in [References](../references.md).
