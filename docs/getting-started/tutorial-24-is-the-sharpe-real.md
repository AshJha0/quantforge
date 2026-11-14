# Tutorial 24: is the Sharpe real? Regimes, PSR, DSR, power and PBO

The plain idea: a backtest's Sharpe ratio is an estimate from a short, noisy sample, and if it is the best of many strategies tried, it is also biased upward, because the luckiest of many useless strategies looks good. Four questions separate a real result from a lucky one. How likely is the true Sharpe to be above zero, given the sample length and the shape of the returns (the probabilistic Sharpe ratio)? How likely is it to be above what the best of `N` useless trials would show (the deflated Sharpe ratio)? Could the study have detected a Sharpe of this size at all (power)? And when the strategy that wins in one half of the data is scored on the other half, how often does it land in the bottom half (the probability of backtest overfitting, PBO)? Before those, a description of the data: which periods were calm and which turbulent.

You will label days as calm or turbulent with a two-state hidden Markov model, compute the PSR of one year of daily returns, reproduce the deflated Sharpe example of Bailey and Lopez de Prado (2014) to four digits and see how it moves with the number of trials, find the minimum detectable Sharpe for 1, 5 and 13.83 years, and compute a PBO by hand. Python first, then the same cases through the Rust, Java and C++ command-line programs. Budget 15 minutes. All data is synthetic except the DSR inputs, which are the paper's own; none of it is a trading claim.

Terms, defined here. The **Sharpe ratio** (SR) is the mean return over its standard deviation; here it is **per period** (per day) unless the line says annual, and an annual figure is the daily one times `sqrt(252)` (or `sqrt(250)` where the paper uses 250 days). **Skew** is the third standardised moment and **kurtosis** the fourth, not excess (3 for a normal distribution). A **trial** is one strategy configuration tried during research, whether or not it was kept. A **regime** is a hidden state of a model, such as calm or turbulent.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/), as in [Tutorial 1](tutorial-1-swap.md): `uv sync --locked --project python`.
- For step 2, the three builds made in Tutorial 1. [Tutorial 23](tutorial-23-backtest-honestly.md) is useful first but not required.

## Step 1: Python

The script `examples/tutorials/t24_sharpe.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t24_sharpe.py -->
```python
"""Tutorial 24: regime labels from a Viterbi path, the probabilistic and deflated Sharpe
ratios, the minimum detectable Sharpe, and the probability of backtest overfitting.

  uv run --project python python examples/tutorials/t24_sharpe.py         # Python
  python examples/tutorials/t24_sharpe.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-24-is-the-sharpe-real.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import math
import sys

from qf import connect


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def main(cli):
    call = connect(cli)  # the Python package with no arguments, else that build's batch command

    # 1. Regimes. The textbook example: Healthy (0) or Fever (1), seen through normal, cold, dizzy.
    r = call("research.regime.viterbi", {"initial": [0.6, 0.4], "transition": [[0.7, 0.3], [0.4, 0.6]],
                                         "emission": [[0.5, 0.1], [0.4, 0.3], [0.1, 0.6]]})
    print(f"textbook path {r['states']}  probability {num(math.exp(r['log_probability']), 5)}")
    # Daily returns in percent, calm (sd 0.5) or turbulent (sd 2), regimes that persist.
    returns = [0.3, -0.2, 0.4, 0.1, -2.5, 3.1, -1.8, 2.2, 0.2, -0.3, 0.1, 0.4]
    r = call("research.regime.viterbi", {"initial": [0.5, 0.5], "transition": [[0.9, 0.1], [0.2, 0.8]],
                                         "observations": returns, "means": [0.0, 0.0], "sds": [0.5, 2.0]})
    print(f"return regimes {''.join(map(str, r['states']))}  log probability {num(r['log_probability'], 4)}")

    # 2. PSR: annual Sharpe 1.0 from one year of daily returns (per-period 1/sqrt(252)).
    sr = 1.0 / math.sqrt(252)
    for skew, kurt in ((0.0, 3.0), (-1.0, 6.0)):
        r = call("research.stats.psr", {"sr": sr, "n_obs": 252, "skew": skew, "kurtosis": kurt})
        print(f"PSR skew {num(skew, 0)} kurtosis {num(kurt, 0)}: z {num(r['z'], 4)}  psr {num(r['psr'], 4)}")

    # 3. DSR: the worked example of Bailey and Lopez de Prado (2014), then fewer trials.
    sr = 2.5 / math.sqrt(250)
    for n in (100, 46, 1):
        r = call("research.stats.dsr", {"sr": sr, "n_obs": 1250, "skew": -3.0, "kurtosis": 10.0,
                                        "n_trials": n, "sr_variance": 0.5 / 250})
        print(f"DSR trials {n:>3}: sr0 {num(r['sr0'], 4)}  dsr {num(r['dsr'], 4)}")

    # 4. Power: the smallest annual Sharpe a study can detect, and the years a Sharpe of 0.5 needs.
    for years in (1.0, 5.0, 13.83):
        r = call("research.stats.power", {"years": years, "sr_target": 0.5})
        print(f"power years {num(years, 2):>5}: mds {num(r['mds'], 4)}  se at 0.5 {num(r['se_at_target'], 4)}")
    print(f"years to detect 0.5: {num(r['years_required'], 2)}  (z_sum {num(r['z_sum'], 4)})")

    # 5. PBO: eight periods, three strategies, four blocks. Strategy 2 wins in the first half only.
    perf = [[0.1, 0.2, 0.9], [0.3, 0.1, 0.8], [0.2, 0.2, 0.7], [0.1, 0.3, 0.9],
            [0.2, 0.1, -0.5], [0.3, 0.2, -0.4], [0.1, 0.3, -0.6], [0.2, 0.2, -0.3]]
    r = call("research.stats.pbo", {"performance": perf, "n_partitions": 4, "metric": "MEAN"})
    print(f"PBO {num(r['pbo'], 4)} over {r['n_combinations']} splits;"
          f" logits {' '.join(num(x, 4) for x in r['logits'])}")


if __name__ == "__main__":
    main(sys.argv[1:])
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t24_sharpe.py
```

Real output, 2026-11-14, Windows 11:

<!-- tutorial:expect -->
```text
textbook path [0, 0, 1]  probability 0.01512
return regimes 000011110000  log probability -18.3539
PSR skew 0 kurtosis 3: z 0.9970  psr 0.8406
PSR skew -1 kurtosis 6: z 0.9657  psr 0.8329
DSR trials 100: sr0 0.1132  dsr 0.9004
DSR trials  46: sr0 0.1004  dsr 0.9505
DSR trials   1: sr0 0.0000  dsr 1.0000
power years  1.00: mds 2.4865  se at 0.5 1.0607
power years  5.00: mds 1.1120  se at 0.5 0.4743
power years 13.83: mds 0.6686  se at 0.5 0.2852
years to detect 0.5: 24.73  (z_sum 2.4865)
PBO 0.8333 over 6 splits; logits -1.0986 -1.0986 0.5108 -1.0986 -1.0986 -1.0986
```

### Reading the numbers

- **The textbook path.** Start Healthy with probability 0.6. The path Healthy, Healthy, Fever for the observations normal, cold, dizzy has joint probability 0.6 x 0.5 (normal when Healthy) x 0.7 x 0.4 (stay Healthy, cold) x 0.3 x 0.6 (fall ill, dizzy) = 0.01512, the widely reproduced answer the spec's golden `regime_j-0001` checks by enumerating all 8 paths.
- **Calm and turbulent.** Twelve daily returns, in percent; state 0 has standard deviation 0.5 and state 1 has 2, and each state tends to persist (0.9 and 0.8 on the diagonal). The four large moves, -2.5, 3.1, -1.8, 2.2, get state 1 and the rest state 0: `000011110000`. The labels use the whole sample, so day 5's label already knows days 6 to 8. They describe the past; they must never feed a signal at time `t` (spec limitation).
- **PSR.** One year of daily returns with an annual Sharpe of 1.0 is a daily Sharpe of 1/sqrt(252) = 0.0630. With normal returns `z = 0.0630 x sqrt(251) / sqrt(1 + 0.0630^2 / 2) = 0.9970`, so the probability that the true Sharpe is above zero is only 0.8406. Negative skew and fat tails (skew -1, kurtosis 6) widen the uncertainty and lower it to 0.8329. A whole year at Sharpe 1 is well short of the 0.95 a 5 % test asks for.
- **DSR, the paper's example.** Five years of daily returns (`T = 1250`), annual Sharpe 2.5 (daily 2.5/sqrt(250)), skew -3, kurtosis 10, chosen from 100 trials whose annual Sharpe ratios have variance 0.5 (0.5/250 per day). The best of 100 useless trials would show a daily Sharpe of 0.1132, close to the 0.1581 observed, and the DSR is 0.9004: below 0.95, so not significant at 5 %. With 46 trials it is 0.9505. Both match the printed values of [BLdP14] pp. 9-10 to four digits. With one trial there is no selection, `SR0 = 0` by ruling J-13, and the DSR is the PSR, 1.0000 at this sample length.
- **Power.** `z_sum = 1.6449 + 0.8416 = 2.4865`, the one-sided 5 % critical value plus the 80 % power quantile. The minimum detectable annual Sharpe is `z_sum / sqrt(years)`: 2.49 with one year of data, 1.11 with five, and 0.67 with 13.83, the figure of the R3-01 preregistration (`rstats_j-0017`). To detect a Sharpe of 0.5 you need `(2.4865 / 0.5)^2 = 24.73` years. Most strategies people backtest on a few years of data are below what that data can detect.
- **PBO.** Eight periods in four blocks of two; strategy 2 earns 0.8 a period in the first half and loses 0.45 in the second. Six ways to choose two blocks for training. When the training half is blocks 0 and 1, strategy 2 wins and then ranks last out of sample: relative rank `1 / (3 + 1) = 0.25`, logit `log(0.25 / 0.75) = -1.0986`. In split 3 (blocks 0 and 3) strategies 1 and 2 tie in training at 0.2, the lower index wins (ruling J-16), and strategy 1 ties for first and second out of sample, average rank 2.5, logit `log(0.625 / 0.375) = 0.5108`. Five of six logits are at or below zero: PBO = 5/6 = 0.8333. Picking the in-sample winner here is worse than picking at random.

### The formal statement, checked against the spec

From [`11-research/regimes.md`](../../specifications/11-research/regimes.md) (rulings J-10 to J-12) and [`11-research/research-statistics.md`](../../specifications/11-research/research-statistics.md) (J-13 to J-18).

Viterbi, in logs: `delta_0(j) = log initial_j + log e_0(j)`, `delta_t(j) = max_i (delta_{t-1}(i) + log A_ij) + log e_t(j)`, back-pointers to the maximising `i`, ties to the smallest index; `log_probability = max_j delta_{T-1}(j)` [Rab89, section III.B]. Gaussian emissions use `-log sd - log(2 pi)/2 - (y - mean)^2 / (2 sd^2)`.

PSR [BLdP12]: with `v = 1 - skew SR + (kurtosis - 1)/4 SR^2`, `z = (SR - SR*) sqrt(T - 1) / sqrt(v)` and `PSR = Phi(z)`.

DSR [BLdP14]: the benchmark is `SR0 = sqrt(V) ((1 - gamma) Phi^{-1}(1 - 1/N) + gamma Phi^{-1}(1 - 1/(N e)))`, with `V` the variance of the trials' per-period Sharpe ratios and `gamma = 0.5772156649...` the Euler-Mascheroni constant; `DSR = PSR` against `SR0`. `N` is the count in the trial registry, `research/trials.csv`; a study never passes a smaller one.

Power: `mds = (Phi^{-1}(1 - alpha) + Phi^{-1}(power)) / sqrt(years)`, `years_required = (z_sum / SR_target)^2`, and `se_at_target = sqrt((1 + SR^2/2) / years)` [Lo02].

PBO by CSCV [BBLdPZ17]: split `T` rows into `S` blocks; for each of the `C(S, S/2)` choices of training blocks, take the best strategy in training, its relative rank out of sample `omega = r / (N + 1)` (average ranks on ties), and the logit `log(omega / (1 - omega))`; `PBO` is the share of logits at or below zero.

The checks behind the goldens: the DSR example is from the paper, read 2026-11-13; the Viterbi example is checked by hand and brute force, and hmmlearn 0.3.3 reproduces all 10 `regime_j` cases; statsmodels reproduces 5 power cases. PSR, DSR and PBO have no free outside library and stay hand and paper checked (ruling J-19a).

## Step 2: the same in Rust, Java and C++

`examples/tutorials/t24_sharpe.py` sends the same cases (two `research.regime.viterbi`, two `research.stats.psr`, three `research.stats.dsr`, three `research.stats.power`, one `research.stats.pbo`) to whichever CLI you name and prints the same lines.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t24_sharpe.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t24_sharpe.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t24_sharpe.py cpp26/build/quantforge
```

Each prints the twelve lines of step 1, digit for digit. The full checks are `python conformance/runner/runner.py --impl rust --suite regime_j` and `--suite rstats_j`.

## For practitioners

- **Count every trial.** The DSR is only as honest as `N`. Parameter grids, discarded features and reruns after a bug fix all count. QuantForge's studies log each one in `research/trials.csv` before the result is seen.
- **`sr_variance` is across trials.** It is the variance of the Sharpe ratios of the configurations you tried, per period, not the standard error of one Sharpe. Many near-identical trials have a small variance, and the DSR barely deflates them; that is the formula working, not a loophole, as long as `N` is honest.
- **The iid formulas are optimistic.** PSR, DSR and the power formula assume independent returns. Under serial correlation the effective sample is smaller; the R3 preregistrations report a block-bootstrap interval and a simulated power beside these numbers.
- **PBO needs a strategy matrix.** Keep the per-period returns of every configuration, not only the winner's, or PBO cannot be computed afterwards.
- **Regimes describe; they do not forecast.** A real-time label is the forward algorithm's filtered argmax, a later item. The Viterbi path is smoothed over the whole sample.

## Common mistakes

- **Passing an annual Sharpe to `psr` or `dsr`.** Both take per-period Sharpe ratios; annualise outside.
- **Excess kurtosis.** `kurtosis` is the raw fourth moment, 3 for a normal. Passing 0 for a normal is out of range or, worse, silently wrong when it is above 1.
- **Reading PSR 0.84 as "84 % chance of making money".** It is the probability that the true Sharpe exceeds the benchmark under the model's assumptions.
- **Choosing `n_partitions` so blocks are tiny.** Two rows per block is the floor the spec allows, not a recommendation; Sharpe on two rows is noise.
- **Feeding Viterbi labels into a backtest signal.** That is look-ahead, exactly the canary of Tutorial 23.

## What you just did

You labelled twelve days as calm or turbulent, saw that one year at Sharpe 1 gives a PSR of only 0.84, reproduced the paper's DSR of 0.9004 for 100 trials and 0.9505 for 46, found that detecting a Sharpe of 0.5 takes 24.73 years of data, and computed a PBO of 5/6 by hand. Four implementations printed the same lines.

## Try next

- Rerun the DSR with skew 0 and kurtosis 3 and find the `N` at which it crosses 0.95 (the paper gives 88).
- Change strategy 2 in the PBO matrix to earn 0.8 in every period and predict the new PBO.
- Add a third, very volatile state to the regime model and see whether any day takes it.
- Read [LEARN, stage J](../../LEARN.md#stage-j-backtest-overfitting-and-research-statistics), the [COOKBOOK stage J recipes](../../COOKBOOK.md) and the [research workflow page](../curves/research-workflow.md).

## References and further reading

The specs list these as sources; "not opened" there means the spec authors cited them from memory.

- D. H. Bailey, M. Lopez de Prado, "The deflated Sharpe ratio: correcting for selection bias, backtest overfitting and non-normality", *Journal of Portfolio Management* 40(5), 2014, 94-107. Read 2026-11-13 per the spec (author copy, SSRN 2460551).
- D. H. Bailey, J. M. Borwein, M. Lopez de Prado, Q. J. Zhu, "The probability of backtest overfitting", *Journal of Computational Finance* 20(4), 2017, 39-69. Read 2026-11-13 per the spec.
- D. H. Bailey, M. Lopez de Prado, "The Sharpe ratio efficient frontier", *Journal of Risk* 15(2), 2012, 3-44 (PSR). Not opened per the spec.
- A. W. Lo, "The statistics of Sharpe ratios", *Financial Analysts Journal* 58(4), 2002, 36-52. Not opened per the spec.
- L. R. Rabiner, "A tutorial on hidden Markov models and selected applications in speech recognition", *Proceedings of the IEEE* 77(2), 1989, 257-286. Not opened per the spec.
- This project: [`11-research/regimes.md`](../../specifications/11-research/regimes.md), [`11-research/research-statistics.md`](../../specifications/11-research/research-statistics.md), rulings in [`stage-j-rulings-w1.md`](../../specifications/stage-j-rulings-w1.md), all sources in [References](../references.md).
