# Tutorial 29: how confident is a view? Black-Litterman from certainty to indifference

The plain idea: Black-Litterman blends two estimates of expected returns, the market's and yours, and weights each by how sure it is. Saying a view is "very confident" or "weak" means nothing until it is a number. This tutorial turns the view's variance `Omega` from almost zero to very large and watches the posterior move from your view all the way back to the market's, with a one-line formula that predicts every step. It then shows that only the ratio of `Omega` to `tau` matters for the posterior mean, and that a second view stacks onto the first in the same way.

You will reuse the three assets and the market prior of Tutorial 25, sweep `Omega` across five values, predict each posterior spread by hand, check that doubling `tau` and `Omega` together changes nothing, read the posterior covariance, and add a second view. Python first, then the same cases through the Rust, Java and C++ command-line programs. Budget 15 minutes. All inputs are invented; none is a forecast.

Terms, defined here. The **prior** `pi` is the vector of expected returns that makes the market portfolio optimal. A **view** is a statement `P mu = q` about a combination `P` of expected returns, held with variance `Omega`. **`tau`** scales the covariance `Sigma` to express how uncertain the prior mean is. The **posterior** is the blended estimate. A view's **weight** `c` is the fraction of the distance from prior to view that the posterior travels.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/), as in [Tutorial 1](tutorial-1-swap.md): `uv sync --locked --project python`.
- For step 2, the three builds made in Tutorial 1. Do [Tutorial 25](tutorial-25-build-and-stress-a-portfolio.md) first: this page reuses its covariance, prior and view.

## Step 1: Python

The script `examples/tutorials/t29_view_confidence.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t29_view_confidence.py -->
```python
"""Tutorial 29: how confident is a view? Black-Litterman with the view variance swept from
certainty to indifference, the tau and Omega trade-off, and two views at once.

  uv run --project python python examples/tutorials/t29_view_confidence.py         # Python
  python examples/tutorials/t29_view_confidence.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-29-view-confidence.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import sys

from qf import connect


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def nums(values, places):
    return " ".join(num(x, places) for x in values)


SIGMA = [[0.04, 0.006, 0.0], [0.006, 0.01, 0.003], [0.0, 0.003, 0.0225]]  # Tutorial 25's covariance
W_MKT, DELTA = [0.5, 0.3, 0.2], 2.5
PRIOR = [DELTA * sum(SIGMA[i][j] * W_MKT[j] for j in range(3)) for i in range(3)]


def bl(call, pick, views, omega, tau):
    return call("research.estimate.black_litterman", {"covariance": SIGMA, "prior_returns": PRIOR,
                                                      "pick": pick, "views": views,
                                                      "view_covariance": omega, "tau": tau})


def weights(call, mu):
    return call("research.portfolio.mean_variance", {"expected_returns": mu, "covariance": SIGMA,
                                                     "risk_aversion": DELTA,
                                                     "lower": [-10.0] * 3, "upper": [10.0] * 3})["weights"]


def main(cli):
    call = connect(cli)
    pick, view = [[1, -1, 0]], [0.08]  # asset 1 beats asset 2 by 8 % a year
    prior_var = 0.05 * (0.04 + 0.01 - 2 * 0.006)  # tau P Sigma P' = 0.0019

    # 1. Sweep Omega. The weight on the view is c = prior_var / (prior_var + Omega).
    for omega in (1e-8, 0.0002, 0.0019, 0.019, 1.0):
        r = bl(call, pick, view, [[omega]], 0.05)
        post = r["posterior_returns"]
        c = prior_var / (prior_var + omega)
        print(f"Omega {omega:<7g}: spread {num(post[0] - post[1], 4)}  predicted {num(0.038 + c * 0.042, 4)}"
              f"  weights {nums(weights(call, post), 4)}")

    # 2. Only the ratio of Omega to tau matters for the mean: double both, same posterior returns.
    a = bl(call, pick, view, [[0.0002]], 0.05)["posterior_returns"]
    b = bl(call, pick, view, [[0.0004]], 0.10)["posterior_returns"]
    print(f"tau 0.05 Omega 0.0002: {nums(a, 6)}")
    print(f"tau 0.10 Omega 0.0004: {nums(b, 6)}")

    # 3. The posterior covariance (uncertainty of the mean) shrinks along the view, not elsewhere.
    r = bl(call, pick, view, [[0.0002]], 0.05)
    pc = r["posterior_covariance"]
    print(f"posterior covariance diagonal {nums([pc[i][i] for i in range(3)], 6)}"
          f"  prior tau Sigma diagonal {nums([0.05 * SIGMA[i][i] for i in range(3)], 6)}")

    # 4. Two views: the spread view and asset 3 returning 2 % a year, each with its own variance.
    r = bl(call, [[1, -1, 0], [0, 0, 1]], [0.08, 0.02], [[0.0002, 0.0], [0.0, 0.0001]], 0.05)
    post = r["posterior_returns"]
    print(f"two views: posterior {nums(post, 4)}  weights {nums(weights(call, post), 4)}")


if __name__ == "__main__":
    main(sys.argv[1:])
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t29_view_confidence.py
```

Real output, 2026-11-15, Windows 11 (Python build):

<!-- tutorial:expect -->
```text
Omega 1e-08  : spread 0.0800  predicted 0.0800  weights 0.9421 -0.1421 0.2000
Omega 0.0002 : spread 0.0760  predicted 0.0760  weights 0.9000 -0.1000 0.2000
Omega 0.0019 : spread 0.0590  predicted 0.0590  weights 0.7211 0.0789 0.2000
Omega 0.019  : spread 0.0418  predicted 0.0418  weights 0.5402 0.2598 0.2000
Omega 1      : spread 0.0381  predicted 0.0381  weights 0.5008 0.2992 0.2000
tau 0.05 Omega 0.0002: 0.088500 0.012500 0.010500
tau 0.10 Omega 0.0004: 0.088500 0.012500 0.010500
posterior covariance diagonal 0.000624 0.000481 0.001114  prior tau Sigma diagonal 0.002000 0.000500 0.001125
two views: posterior 0.0895 0.0136 0.0192  weights 0.8958 -0.2115 0.3157
```

### Reading the numbers

- **One formula for the whole sweep.** For a single view the prior's variance along the view is `tau P Sigma P' = 0.05 x (0.04 + 0.01 - 2 x 0.006) = 0.0019`. The posterior spread is the prior spread 0.038 plus `c = 0.0019 / (0.0019 + Omega)` times the gap 0.042 between the view and the prior. The "predicted" column is that formula; it matches the optimiser's output to every printed digit.
- **The two ends.** With `Omega = 1e-8` the view is treated as certain and the spread is the view's 0.0800. With `Omega = 1` the view is ignored and the spread, 0.0381, is the prior's 0.038 to within rounding. At `Omega = 0.0019`, equal to the prior's variance, `c = 1/2` and the posterior sits half-way, at 0.0590.
- **The weights follow the view only.** Every portfolio keeps 0.2000 in asset 3. Black-Litterman with one view moves the optimal weights only along the rows of `P`, here `(1, -1, 0)`: from the market's `(0.5, 0.3, 0.2)` to `(0.9421, -0.1421, 0.2)` for a certain view, a tilt of 0.4421 in each direction.
- **Only the ratio matters.** `tau 0.05, Omega 0.0002` and `tau 0.10, Omega 0.0004` give the same posterior mean to six digits, because the mean depends on `tau` and `Omega` only through `Omega / tau`. They do not give the same posterior covariance, which scales with `tau`.
- **What the view teaches you about uncertainty.** The posterior covariance is the uncertainty of the mean after the view. Asset 1's variance falls from 0.002000 (`tau Sigma`) to 0.000624 and asset 2's from 0.000500 to 0.000481: the view was about their spread, and asset 1 has the larger variance, so it learns more. Asset 3, with no view and correlation with asset 2 only, barely moves (0.001125 to 0.001114).
- **A second view.** Adding "asset 3 returns 2 %", with variance 0.0001, lifts asset 3's posterior from 0.0105 to 0.0192 and its weight from 0.20 to 0.3157; the spread view still holds (0.0895 - 0.0136 = 0.0759). With two views the weights can move in two directions, so asset 2 now carries a larger short.

### The formal statement, checked against the spec

From [`07-portfolio/estimation.md`](../../specifications/07-portfolio/estimation.md) (ruling J-W2-8 in [`stage-j-rulings-w2.md`](../../specifications/stage-j-rulings-w2.md)). Black-Litterman [BL92, HL99]: posterior mean `pi + tau Sigma P' (P tau Sigma P' + Omega)^-1 (q - P pi)`; `posterior_covariance = tau Sigma - tau Sigma P' (P tau Sigma P' + Omega)^-1 P tau Sigma`; `predictive_covariance = Sigma + posterior_covariance`. For one view, `P tau Sigma P'` is the scalar 0.0019 and the update along the view is `c (q - P pi)` with `c = 0.0019 / (0.0019 + Omega)`, the formula of the sweep. Dividing numerator and denominator by `tau` shows the mean depends on `Omega / tau` alone. The prior is an input: the script computes `pi = delta Sigma w_mkt` with `delta = 2.5` itself, as the spec leaves that to the caller.

## Step 2: the same in Rust, Java and C++

`examples/tutorials/t29_view_confidence.py` sends the same cases (nine `research.estimate.black_litterman`, six `research.portfolio.mean_variance`) to whichever CLI you name and prints the same lines.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t29_view_confidence.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t29_view_confidence.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t29_view_confidence.py cpp26/build/quantforge
```

Each is to print the nine lines of step 1, digit for digit. The full check is `python conformance/runner/runner.py --impl rust --suite estim_j`.

## For practitioners

- **Calibrate `Omega` from something you can defend.** A common choice is `Omega` proportional to `tau P Sigma P'`, so that `c` is a fixed confidence; another is the variance of past forecast errors for that view. Write down which, before seeing the result.
- **Set `c`, not `Omega`.** Saying "this view gets a quarter of the way from prior to view" is easier to argue about than a variance, and maps to `Omega = 3 x tau P Sigma P'`.
- **`tau` is not free.** Values from 0.01 to 1 appear in practice; because only `Omega / tau` moves the mean, fix `tau` once and express confidence through `Omega`.
- **Views on spreads are safer than views on levels.** A spread view leaves the overall level of expected returns to the market prior.

## Common mistakes

- **Treating `Omega` as a standard deviation.** It is a variance: 0.0002 means a standard deviation of about 1.4 % a year.
- **Expecting a view to move assets it does not mention.** It moves them only through their covariance with the assets in `P`, as asset 3 shows.
- **Changing `tau` to strengthen a view and reporting it as a different model.** Doubling `tau` with `Omega` fixed is the same as halving `Omega`.
- **Reading `posterior_covariance` as the risk of the portfolio.** It is the uncertainty of the mean; the risk to optimise against is `predictive_covariance` or `Sigma`.

## What you just did

You swept a view's variance from near zero to 1, predicted each posterior spread with `c = 0.0019 / (0.0019 + Omega)`, saw the weights move only along the view, showed that `tau` and `Omega` act only through their ratio, read how much each asset's mean uncertainty fell, and stacked a second view.

## Try next

- Choose `Omega` so that `c = 0.25` and check the spread is `0.038 + 0.25 x 0.042`.
- Change the second view's variance to 0.01 and predict whether asset 3's weight goes back towards 0.2.
- Run the two-view posterior through long-only mean-variance and see which bound binds.

## References and further reading

- F. Black, R. Litterman, "Global portfolio optimization", *Financial Analysts Journal* 48(5), 1992, 28-43. Not opened per the spec.
- G. He, R. Litterman, "The intuition behind Black-Litterman model portfolios", Goldman Sachs working paper, 1999. Not opened per the spec.
- This project: [`07-portfolio/estimation.md`](../../specifications/07-portfolio/estimation.md), [Tutorial 25](tutorial-25-build-and-stress-a-portfolio.md), all sources in [References](../references.md).
