# Tutorial 26: test your ES model and fit regimes: the Z2 backtest, Baum-Welch, Viterbi

The plain idea: a risk model makes two claims about bad days. Value at risk (VaR) says how often losses should beat a level; expected shortfall (ES) says how large they should be, on average, when they do. Counting VaR breaks tests the first claim only. The Acerbi-Szekely Z2 statistic tests the second, by comparing the size of the breaks with the ES the model forecast. The second half of the page turns from testing a model to fitting one: a two-state hidden Markov model whose parameters (how calm and turbulent days differ, and how long each spell lasts) are estimated from the returns alone by the Baum-Welch algorithm, after which Viterbi labels each day.

You will run a VaR count test that cannot tell three ES models apart, then Z2, which can; fit a one-state model you can check by hand; stop a two-state fit early and then let it converge; and label twenty-four days with the fitted model. Python first, then the same cases through the Rust, Java and C++ command-line programs. Budget 15 minutes. All data is synthetic.

Terms, defined here. A **loss** is a positive number here: a loss of 3 is `3`, a gain of 3 is `-3`. **Alpha** is the tail probability, 10 % in this tutorial so that twenty days are enough to see something (2.5 % is the level the Basel market-risk rules use for ES). An **exception** is a day whose loss is strictly above that day's VaR. A **regime** is a hidden state of the model; here state 0 turns out calm and state 1 turbulent. The **log-likelihood** is the log of the probability density the model gives to the whole series; higher is a better fit.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/), as in [Tutorial 1](tutorial-1-swap.md): `uv sync --locked --project python`.
- For step 2, the three builds made in Tutorial 1. [Tutorial 5](tutorial-5-risk.md) covers VaR and its exception tests, and [Tutorial 24](tutorial-24-is-the-sharpe-real.md) Viterbi with given parameters; both are useful but not required.

## Step 1: Python

The script `examples/tutorials/t26_es_regimes.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t26_es_regimes.py -->
```python
"""Tutorial 26: test an expected-shortfall model with the Acerbi-Szekely Z2 statistic, then fit a
two-state regime model by Baum-Welch and label the days with Viterbi.

  uv run --project python python examples/tutorials/t26_es_regimes.py         # Python
  python examples/tutorials/t26_es_regimes.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-26-test-es-and-fit-regimes.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import sys

from qf import connect


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def nums(values, places):
    return " ".join(num(x, places) for x in values)


def main(cli):
    call = connect(cli)  # the Python package with no arguments, else that build's batch command

    # 1. Twenty daily losses (positive = loss). Two days break a VaR of 2.0; at alpha = 10 % two are expected.
    losses = [0.4, -0.3, 1.1, 0.2, -0.8, 2.5, 0.6, -1.2, 0.9, 1.5,
              -0.5, 0.3, 1.8, -0.2, 0.7, 3.5, -0.9, 0.1, 1.2, -0.4]
    n, alpha = len(losses), 0.10
    r = call("risk.backtest.kupiec", {"observations": n, "exceptions": 2, "confidence": 1 - alpha})
    print(f"Kupiec, 2 exceptions in {n}: LR {num(r['lr_uc'], 4)}  p-value {num(r['p_value'], 4)}")
    # Three models, the same VaR, different ES forecasts.
    for name, es in (("ES 3.0", 3.0), ("ES 2.2", 2.2), ("ES 4.0", 4.0)):
        r = call("risk.backtest.es_z2", {"losses": losses, "var": [2.0] * n, "es": [es] * n, "alpha": alpha})
        print(f"Z2 {name}: z2 {num(r['z2'], 4)}  exceptions {r['exceptions']}"
              f"  expected {num(r['expected_exceptions'], 1)}")
    # A model whose ES moves with its VaR: the forecasts double on the last ten days.
    var = [1.5] * 10 + [3.0] * 10
    es = [2.0] * 10 + [4.0] * 10
    r = call("risk.backtest.es_z2", {"losses": losses, "var": var, "es": es, "alpha": alpha})
    print(f"Z2 moving forecasts: z2 {num(r['z2'], 4)}  exceptions {r['exceptions']}")

    # 2. Baum-Welch. Twenty-four daily returns, in percent, with two turbulent spells.
    returns = [0.3, -0.2, 0.4, 0.1, -2.5, 3.1, -1.8, 2.2, 0.2, -0.3, 0.1, 0.4,
               -0.5, 0.6, 0.2, -0.1, 1.9, -2.8, 2.4, -1.5, 0.3, 0.0, -0.4, 0.5]
    one = call("research.regime.baum_welch", {"observations": returns, "initial": [1.0],
                                              "transition": [[1.0]], "means": [0.0], "sds": [1.0]})
    print(f"one state: mean {num(one['means'][0], 4)}  sd {num(one['sds'][0], 4)}"
          f"  log-likelihood {num(one['log_likelihood'], 4)}  iterations {one['iterations']}")
    start = {"observations": returns, "initial": [0.5, 0.5], "transition": [[0.9, 0.1], [0.2, 0.8]],
             "means": [0.0, 0.0], "sds": [0.5, 2.0], "tolerance": 1e-6}
    short = call("research.regime.baum_welch", {**start, "max_iterations": 3})
    print(f"two states, 3 iterations: log-likelihood {num(short['log_likelihood'], 4)}"
          f"  converged {short['converged']}")
    fit = call("research.regime.baum_welch", start)
    print(f"two states: iterations {fit['iterations']}  converged {fit['converged']}"
          f"  log-likelihood {num(fit['log_likelihood'], 4)}")
    print(f"  means {nums(fit['means'], 4)}  sds {nums(fit['sds'], 4)}")
    print(f"  stay calm {num(fit['transition'][0][0], 4)}  stay turbulent {num(fit['transition'][1][1], 4)}"
          f"  initial {nums(fit['initial'], 4)}")

    # 3. Viterbi with the fitted parameters: the most likely state of each day.
    r = call("research.regime.viterbi", {"initial": fit["initial"], "transition": fit["transition"],
                                         "observations": returns, "means": fit["means"], "sds": fit["sds"]})
    print(f"Viterbi path {''.join(map(str, r['states']))}  log probability {num(r['log_probability'], 4)}")


if __name__ == "__main__":
    main(sys.argv[1:])
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t26_es_regimes.py
```

Real output, 2026-11-14, Windows 11 (Python build):

<!-- tutorial:expect -->
```text
Kupiec, 2 exceptions in 20: LR 0.0000  p-value 1.0000
Z2 ES 3.0: z2 0.0000  exceptions 2  expected 2.0
Z2 ES 2.2: z2 -0.3636  exceptions 2  expected 2.0
Z2 ES 4.0: z2 0.2500  exceptions 2  expected 2.0
Z2 moving forecasts: z2 -0.0625  exceptions 2
one state: mean 0.1083  sd 1.3675  log-likelihood -41.5653  iterations 2
two states, 3 iterations: log-likelihood -31.8749  converged False
two states: iterations 7  converged True  log-likelihood -31.8744
  means 0.1005 0.1210  sds 0.3170 2.1733
  stay calm 0.8354  stay turbulent 0.7582  initial 1.0000 0.0000
Viterbi path 000011110000000011110000  log probability -32.8716
```

### Reading the numbers

- **The VaR count.** Losses of 2.5 (day 6) and 3.5 (day 16) are the only ones above 2.0. At alpha 10 % over 20 days, `T alpha = 2` exceptions are expected, so Kupiec's likelihood ratio is exactly 0 (ruling F-32) and the p-value 1. The count is perfect, and it is the same whatever ES the model forecast.
- **Z2 sees the size.** `Z2 = 1 - sum L_t 1{L_t > VaR_t} / (T alpha ES_t)`. With ES 3.0 the two breaks average 3.0, as forecast: `Z2 = 1 - (2.5 + 3.5) / (2 x 3.0) = 0`. With ES 2.2 the model understated the tail: `1 - 6 / 4.4 = -0.3636`. With ES 4.0 it overstated it: `1 - 6 / 8 = 0.25`. Negative is the direction a supervisor cares about.
- **Forecasts that move.** VaR 1.5 and ES 2.0 for ten days, then 3.0 and 4.0. Day 10's loss of 1.5 equals its VaR and is not an exception, because the test is strict (ruling J-W2-10). The breaks are 2.5 against ES 2.0 and 3.5 against ES 4.0, each divided by its own day's forecast: `1 - (2.5/2.0 + 3.5/4.0) / 2 = -0.0625`.
- **One state, by hand.** With a single state, Baum-Welch is the maximum-likelihood normal fit. The 24 returns sum to 2.6, so the mean is 0.1083, and the population standard deviation (divisor `T`) is 1.3675. The log-likelihood is `-(T/2)(log(2 pi sd^2) + 1) = -12 x (log 11.749 + 1) = -41.5653`. The first iteration lands on these values and the second leaves them unchanged, so the run stops at iteration 2 (the spec's hand case `baumwelch_j-0001` has the same shape).
- **Stopped early.** With `max_iterations` 3 the fit returns `converged False` and the parameters of its last step; its log-likelihood, -31.8749, is already within 0.0005 of the final value. EM climbs quickly at first and then slowly.
- **Converged.** With tolerance `1e-6` the gain at iteration 6 is about `2.0e-6` and at iteration 7 about `1.3e-7`, so the run stops after iteration 7 with log-likelihood -31.8744, 9.69 above the one-state fit. The two states have nearly the same mean, 0.10 and 0.12, and very different spreads, 0.317 and 2.173: the model has found volatility regimes, not trends. A calm spell lasts `1 / (1 - 0.8354) = 6.1` days on average and a turbulent one `1 / (1 - 0.7582) = 4.1`. The fitted initial probabilities are `(1, 0)` because with one series they are the probabilities of day 1 alone, which is calm.
- **Viterbi with the fitted model.** The path `000011110000000011110000` marks the two four-day spells of large moves, days 5 to 8 and 17 to 20, as turbulent. Tutorial 24 found the first spell with parameters chosen by hand; here the data chose them.

### The formal statement, checked against the spec

From [`06-risk/es-backtest.md`](../../specifications/06-risk/es-backtest.md) (ruling J-W2-10) and [`11-research/baum-welch.md`](../../specifications/11-research/baum-welch.md) (J-W2-9, J-W2-11 to J-W2-13).

Z2 [AS14, test 2]: with losses `L_t`, forecasts `VaR_t` and `ES_t > 0` made before each period, and `I_t = 1{L_t > VaR_t}`, `Z2 = 1 - sum_t L_t I_t / (T alpha ES_t)`. Its expected value is 0 when the model is right and it is negative when ES is understated. Outputs are `z2`, `exceptions` and `expected_exceptions = T alpha`. The paper's critical values depend on the tail model and are not outputs; a study simulates them under its own model.

Baum-Welch [Rab89, sections III.A and III.C] for Gaussian emissions. E-step, scaled forward-backward: `ahat_t(j) = (sum_i a_{t-1}(i) A_ij) b_t(j)`, `c_t = sum_j ahat_t(j)`, `a_t = ahat_t / c_t`, a matching backward pass, `gamma_t(i) = a_t(i) beta_t(i)`, `xi_t(i, j)` from the two, and `loglik = sum_t log c_t`. M-step: `pi_i = gamma_0(i)`, `A_ij = sum_t xi_t(i, j) / sum_t gamma_t(i)` over `t < T - 1`, `mu_i` and `sigma_i^2` as `gamma`-weighted mean and variance. One iteration is an M-step followed by the E-step at the new parameters; the run stops after the first iteration whose gain is below `tolerance` (`converged = true`) or after `max_iterations` (`converged = false`). EM never lowers the likelihood [DLR77], and no variance floor or relabelling is applied: the start values fix which state is which.

The checks behind the goldens (`esbt_j`, `baumwelch_j`): hand cases for both; every Baum-Welch log-likelihood recomputed by an independent log-space forward pass in the oracle; each golden's tolerance chosen so every stop test is decided by at least `1e-11` (ruling J-W2-12). A run of hmmlearn on the `baumwelch_j` cases is still open (J-W2-15). This page's own stop tests are decided by margins of about `1e-6`, so all builds stop at the same iteration.

## Step 2: the same in Rust, Java and C++

`examples/tutorials/t26_es_regimes.py` sends the same cases (one `risk.backtest.kupiec`, four `risk.backtest.es_z2`, three `research.regime.baum_welch`, one `research.regime.viterbi`) to whichever CLI you name and prints the same lines.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t26_es_regimes.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t26_es_regimes.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t26_es_regimes.py cpp26/build/quantforge
```

Each is to print the eleven lines of step 1, digit for digit; the Rust, Java and C++ runs of this page are checked by CI once the wave 2 builds are merged. The full checks are `python conformance/runner/runner.py --impl rust --suite esbt_j` and `--suite baumwelch_j`.

## For practitioners

- **Backtest both claims.** A VaR count can be perfect while ES is badly wrong, as the three models on this page show. Report Z2 next to Kupiec and Christoffersen.
- **Z2 has no universal critical value.** Its null distribution depends on the tails of the model being tested. Simulate it under the model, as [AS14] do, and say how many paths you used.
- **Twenty days is a teaching size.** At alpha 2.5 % a year of daily data gives about 6 expected exceptions, so a single large loss moves Z2 a long way. Read it with an interval, not as a point.
- **EM finds a local maximum.** The answer depends on the start values. Try a few, keep the one with the highest log-likelihood, and report that you did.
- **A better fit is not a test.** The two-state model's log-likelihood is 9.69 higher with five more parameters, but the usual chi-squared test does not apply, because under one state the second state's parameters are not identified. Compare models out of sample, or by simulation.
- **Labels are smoothed.** Viterbi and the fitted parameters use the whole sample. They describe the past and must not feed a signal at time `t`.

## Common mistakes

- **Losses with the wrong sign.** `risk.backtest.es_z2` takes positive losses and positive VaR and ES. Passing returns gives exceptions on the wrong days.
- **A non-strict exception.** A loss equal to VaR is not an exception (day 10 in the moving-forecast case).
- **Using today's ES for yesterday's loss.** The forecasts must be the ones made before each period; a one-day shift is look-ahead.
- **Too small a tolerance on a long series.** EM's gains shrink geometrically; a tolerance near rounding noise makes the stop depend on the last bits. The spec treats a negative gain from rounding as converged (ruling J-W2-11), but a sensible tolerance is better.
- **Expecting state 0 to be calm.** Baum-Welch does not sort the states; the start values decide which is which.

## What you just did

You saw a VaR count that could not tell three ES models apart and a Z2 of 0, -0.3636 and 0.25 that could, fitted a one-state model whose answer you checked by hand, watched a two-state fit stop at iteration 3 unconverged and at iteration 7 converged, and labelled two turbulent spells with the fitted model.

## Try next

- Change the ES 2.2 model to 2.4 and predict Z2 before you run it.
- Start the two-state fit from `sds` of `(2.0, 0.5)` and check that the states swap labels.
- Add a third state and compare the log-likelihood gain with the two you just saw.
- Read [LEARN, stage J](../../LEARN.md#stage-j-backtest-overfitting-and-research-statistics), the [COOKBOOK stage J recipes](../../COOKBOOK.md#stage-j-recipes) and [Tutorial 25](tutorial-25-build-and-stress-a-portfolio.md).

## References and further reading

The specs list these as sources; "not opened" there means the spec authors cited them from memory.

- C. Acerbi, B. Szekely, "Backtesting expected shortfall", *Risk*, December 2014. Not opened per the spec.
- L. R. Rabiner, "A tutorial on hidden Markov models and selected applications in speech recognition", *Proceedings of the IEEE* 77(2), 1989, 257-286. Not opened per the spec.
- A. P. Dempster, N. M. Laird, D. B. Rubin, "Maximum likelihood from incomplete data via the EM algorithm", *Journal of the Royal Statistical Society B* 39(1), 1977, 1-38. Not opened per the spec.
- This project: [`06-risk/es-backtest.md`](../../specifications/06-risk/es-backtest.md), [`11-research/baum-welch.md`](../../specifications/11-research/baum-welch.md), [`06-risk/var-es-and-backtests.md`](../../specifications/06-risk/var-es-and-backtests.md), rulings in [`stage-j-rulings-w2.md`](../../specifications/stage-j-rulings-w2.md), all sources in [References](../references.md).
