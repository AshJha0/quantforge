# Tutorial 32: shrinkage against sample length: when Ledoit-Wolf helps and when it does not

The plain idea: a covariance matrix estimated from a short history is noisy, and Ledoit-Wolf shrinkage pulls it towards a simple target to reduce that noise. How much it pulls depends on how short the history is. But shrinkage is not free: it trades noise for bias towards the target, and when the target is far from the truth, the trade can go either way. The only way to see this is to know the truth, so this tutorial simulates returns from a covariance it chose and measures how close each estimate gets, and what each does to a risk-parity portfolio.

You will compute risk parity on the true covariance and check it by hand, draw histories of 10, 30, 120 and 1,000 months from that covariance, compare the sample and shrunk estimates with the truth, compare the risk-parity weights each produces, and measure, with the true covariance, how concentrated the ten-month portfolios really are. Python first, then the same cases through the Rust, Java and C++ command-line programs. Budget 15 minutes. All returns are simulated from a seeded generator.

Terms, defined here. The **sample covariance** here divides by `T`, as the spec does. The **shrinkage** `delta` is the weight Ledoit-Wolf puts on its target, a multiple of the identity matrix; `delta = 0` keeps the sample, `delta = 1` the target. The **estimation error** is the Frobenius distance `sqrt(sum_ij (C_ij - Sigma_ij)^2)` between an estimate `C` and the truth. The **risk-parity gap** is the sum of absolute differences between two sets of weights.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/), as in [Tutorial 1](tutorial-1-swap.md): `uv sync --locked --project python`.
- For step 2, the three builds made in Tutorial 1. [Tutorial 25](tutorial-25-build-and-stress-a-portfolio.md) introduces Ledoit-Wolf and risk parity and is useful first.

## Step 1: Python

The script `examples/tutorials/t32_shrinkage_and_length.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t32_shrinkage_and_length.py -->
```python
"""Tutorial 32: shrinkage against sample length. Ledoit-Wolf on histories of 10 to 1,000 periods
drawn from a known covariance, and what each estimate does to a risk-parity portfolio.

  uv run --project python python examples/tutorials/t32_shrinkage_and_length.py         # Python
  python examples/tutorials/t32_shrinkage_and_length.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-32-shrinkage-and-sample-length.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import math
import random
import sys

from qf import connect


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def nums(values, places):
    return " ".join(num(x, places) for x in values)


# The true covariance of five assets (monthly, in percent squared): volatilities 6, 5, 4, 3, 2,
# correlation 0.5 between every pair. Known here only because the data is simulated.
VOLS = [6.0, 5.0, 4.0, 3.0, 2.0]
TRUE = [[VOLS[i] * VOLS[j] * (1.0 if i == j else 0.5) for j in range(5)] for i in range(5)]


def cholesky(a):
    n = len(a)
    low = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = a[i][j] - sum(low[i][k] * low[j][k] for k in range(j))
            low[i][j] = math.sqrt(s) if i == j else s / low[j][j]
    return low


def draw(t, seed):
    # t rows of correlated normal returns, rounded to 4 places so every build reads the same numbers.
    rng, low = random.Random(seed), cholesky(TRUE)
    rows = []
    for _ in range(t):
        z = [rng.gauss(0.0, 1.0) for _ in range(5)]
        rows.append([round(sum(low[i][k] * z[k] for k in range(i + 1)), 4) for i in range(5)])
    return rows


def sample_cov(rows):
    t = len(rows)
    m = [sum(r[k] for r in rows) / t for k in range(5)]
    return [[sum((r[i] - m[i]) * (r[j] - m[j]) for r in rows) / t for j in range(5)] for i in range(5)]


def main(cli):
    call = connect(cli)
    rp = lambda cov: call("research.portfolio.risk_parity", {"covariance": cov})["weights"]
    w_true = rp(TRUE)
    print(f"risk parity on the true covariance: {nums(w_true, 4)}")

    # 1. Shrinkage intensity falls as the history grows; the shrunk estimate is closer to the truth.
    for t in (10, 30, 120, 1000):
        rows = draw(t, 32)
        r = call("research.estimate.ledoit_wolf", {"returns": rows})
        s = sample_cov(rows)
        err = lambda c: math.sqrt(sum((c[i][j] - TRUE[i][j]) ** 2 for i in range(5) for j in range(5)))
        gap = lambda w: sum(abs(a - b) for a, b in zip(w, w_true))
        print(f"T {t:>4}: shrinkage {num(r['shrinkage'], 4)}  error sample {num(err(s), 2)}"
              f" shrunk {num(err(r['covariance']), 2)}  risk-parity gap sample {num(gap(rp(s)), 4)}"
              f" shrunk {num(gap(rp(r['covariance'])), 4)}")

    # 2. Ten months: the risk the sample-based portfolio really carries, measured with the true covariance.
    rows = draw(10, 32)
    for name, cov in (("sample", sample_cov(rows)),
                      ("shrunk", call("research.estimate.ledoit_wolf", {"returns": rows})["covariance"])):
        e = call("risk.contrib.euler", {"weights": rp(cov), "covariance": TRUE})
        print(f"T 10 {name}: true risk shares {nums(e['shares'], 4)}  largest {num(max(e['shares']), 4)}")


if __name__ == "__main__":
    main(sys.argv[1:])
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t32_shrinkage_and_length.py
```

Real output, 2026-11-15, Windows 11 (Python build):

<!-- tutorial:expect -->
```text
risk parity on the true covariance: 0.1149 0.1379 0.1724 0.2299 0.3448
T   10: shrinkage 0.3040  error sample 40.66 shrunk 41.58  risk-parity gap sample 0.2767 shrunk 0.2581
T   30: shrinkage 0.1391  error sample 18.99 shrunk 19.00  risk-parity gap sample 0.1175 shrunk 0.0583
T  120: shrinkage 0.0404  error sample 4.95 shrunk 4.71  risk-parity gap sample 0.0348 shrunk 0.0401
T 1000: shrinkage 0.0057  error sample 4.17 shrunk 4.37  risk-parity gap sample 0.0126 shrunk 0.0145
T 10 sample: true risk shares 0.1622 0.2581 0.1972 0.2709 0.1117  largest 0.2709
T 10 shrunk: true risk shares 0.1874 0.2735 0.2033 0.2289 0.1068  largest 0.2735
```

### Reading the numbers

- **Risk parity on the truth, by hand.** When every pair of assets has the same correlation, equal risk shares need weights proportional to `1 / vol`: `1/6, 1/5, 1/4, 1/3, 1/2`, which sum to 1.45, so the weights are `0.1149, 0.1379, 0.1724, 0.2299, 0.3448`, as printed.
- **Shrinkage falls with length.** `delta` is 0.3040 for 10 months, 0.1391 for 30, 0.0404 for 120 and 0.0057 for 1,000. The estimator judges, from the data alone, how much the sample can be trusted.
- **Shrinkage did not always reduce the error.** At 120 months the shrunk estimate is closer to the truth (4.71 against 4.95); at 10, 30 and 1,000 months it is no closer or slightly further. The target is a multiple of the identity: equal variances and no correlation. The true matrix has variances from 4 to 36 and correlation 0.5 everywhere, so pulling towards that target adds bias that cancels much of the noise it removes. Ledoit-Wolf minimises expected error under its own assumptions; it does not promise a smaller error on every sample.
- **The portfolio can still benefit.** At 30 months the shrunk estimate gives risk-parity weights twice as close to the true ones (gap 0.0583 against 0.1175), although the two matrices are equally far from the truth. Risk parity depends on the matrix through ratios, and shrinkage damps the extreme ratios. At 120 and 1,000 months the sample is slightly better. One seed is one draw: a claim about which estimator wins needs many seeds, which this page does not run.
- **What ten months really buys.** Measured with the true covariance, the sample-based portfolio meant to give each asset 20 % of the risk actually gives the largest asset 27.1 %, and the shrunk one 27.4 %. With ten observations of five assets neither estimate supports an allocation that fine.

### The formal statement, checked against the spec

From [`07-portfolio/estimation.md`](../../specifications/07-portfolio/estimation.md) (ruling J-W2-7) and [`07-portfolio/optimisation.md`](../../specifications/07-portfolio/optimisation.md) (rulings J-W2-4 and J-W2-5) in [`stage-j-rulings-w2.md`](../../specifications/stage-j-rulings-w2.md). Ledoit-Wolf [LW04]: demean each column; `S = (1/T) sum_t x_t x_t'`; `m = tr S / N`; `d^2 = ||S - m I||^2 / N`; `bbar^2 = (1/T^2) sum_t ||x_t x_t' - S||^2 / N`; `b^2 = min(bbar^2, d^2)`; `delta = b^2 / d^2`; output `delta m I + (1 - delta) S`. `bbar^2` falls roughly as `1/T`, which is why `delta` does. Risk parity [Spinu13]: long-only weights with `w_i (Sigma w)_i / (w' Sigma w) = b_i / sum b` (equal budgets by default). For equal pairwise correlation `rho`, `(Sigma w)_i = sigma_i (rho sum_j sigma_j w_j + (1 - rho) sigma_i w_i)`, and `w_i proportional to 1 / sigma_i` makes every term `w_i (Sigma w)_i` the same, which is the hand check above.

The simulated returns are rounded to four places before they are sent, so every build reads the same numbers; the random draws come from Python's seeded generator in the script, not from the builds.

## Step 2: the same in Rust, Java and C++

`examples/tutorials/t32_shrinkage_and_length.py` sends the same cases (five `research.estimate.ledoit_wolf`, eleven `research.portfolio.risk_parity`, two `risk.contrib.euler`) to whichever CLI you name and prints the same lines.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t32_shrinkage_and_length.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t32_shrinkage_and_length.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t32_shrinkage_and_length.py cpp26/build/quantforge
```

Each is to print the seven lines of step 1, digit for digit. The full checks are `python conformance/runner/runner.py --impl rust --suite estim_j` and `--suite optim_j`.

## For practitioners

- **Pick the target to match the data.** A scaled identity suits assets with similar volatilities and weak correlation. For a correlated equity universe, a constant-correlation or one-factor target is closer; QuantForge implements only the scaled identity (ruling J-W2-7), so standardise returns first if volatilities differ a lot.
- **Judge an estimator by what it does to the decision.** Here the two estimates were equally far from the truth but gave different portfolios. Measure the portfolio's realised risk, not only matrix error.
- **Run more than one seed.** A single simulated history can favour either estimator; a statement about which is better needs a distribution over many draws.
- **Short histories limit how fine an allocation can be.** No estimator turns ten months into a reliable five-asset risk budget.

## Common mistakes

- **Expecting shrinkage to always help.** It reduces expected error when its assumptions hold; on a given sample, or with a poor target, it can do worse, as two of the four lengths show.
- **Comparing estimators on one draw and reporting the winner.** That is a trial like any other; see [Tutorial 30](tutorial-30-trials-and-power.md).
- **Feeding raw returns with very different scales.** The scaled-identity target then pulls all variances towards their mean, distorting the low-volatility assets most.
- **Forgetting that the sample covariance here divides by `T`.** Tools that divide by `T - 1` give slightly larger matrices; the difference matters only for very short histories.

## What you just did

You checked risk parity on a known covariance by hand, watched Ledoit-Wolf's shrinkage fall from 0.30 to 0.006 as the history grew from 10 to 1,000 months, found that shrinkage reduced the estimation error at only one of the four lengths but halved the risk-parity gap at 30 months, and measured how far a ten-month risk budget is from its target.

## Try next

- Change the seed from 32 to another value and see whether the 30-month result holds.
- Set every volatility to 4 and predict whether shrinkage now helps the matrix error.
- Standardise each column of the returns before shrinking, then scale back, and compare the risk-parity gap.

## References and further reading

- O. Ledoit, M. Wolf, "A well-conditioned estimator for large-dimensional covariance matrices", *Journal of Multivariate Analysis* 88(2), 2004, 365-411. Not opened per the spec.
- F. Spinu, "An algorithm for computing risk parity weights", SSRN 2297383, 2013. Not opened per the spec.
- This project: [`07-portfolio/estimation.md`](../../specifications/07-portfolio/estimation.md), [`07-portfolio/optimisation.md`](../../specifications/07-portfolio/optimisation.md), [Tutorial 25](tutorial-25-build-and-stress-a-portfolio.md), all sources in [References](../references.md).
