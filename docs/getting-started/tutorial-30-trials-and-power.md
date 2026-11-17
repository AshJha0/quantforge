# Tutorial 30: how many trials can a result survive, and how long must a study run?

The plain idea: the same backtest Sharpe ratio means different things depending on how it was found and how long the record is. Found on the first try, an annual Sharpe of 1.0 over three years is fairly convincing; found as the best of a thousand tries, it is what luck alone would produce. And before running a study at all, you can work out whether its length gives it any chance of detecting the effect you hope for. This tutorial puts numbers on both questions with the deflated Sharpe ratio (DSR), the probabilistic Sharpe ratio (PSR) and a power calculation.

You will hold one strategy fixed (annual Sharpe 1.0, three years of daily returns, mildly fat-tailed) and raise the number of trials from 1 to 1,000, watch the PSR rise as the history lengthens from one year to ten, find the minimum detectable Sharpe for four study lengths and the years needed for three target Sharpe ratios, and see what a stricter test costs. Python first, then the same cases through the Rust, Java and C++ command-line programs. Budget 15 minutes. All inputs are invented; none describes a real strategy.

Terms, defined here. A **trial** is one configuration tried during research, kept or not. **`SR0`** is the Sharpe ratio the best of `N` worthless trials is expected to show. **PSR** is the probability that the true Sharpe exceeds a benchmark, given the sample; **DSR** is PSR with `SR0` as the benchmark. **Power** is the probability that a test detects an effect of a given size; the **minimum detectable Sharpe** (MDS) is the smallest effect a study detects with the chosen power. **`alpha`** is the false-positive rate the test allows.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/), as in [Tutorial 1](tutorial-1-swap.md): `uv sync --locked --project python`.
- For step 2, the three builds made in Tutorial 1. [Tutorial 24](tutorial-24-is-the-sharpe-real.md) introduces PSR, DSR and power with the paper's own example and is useful first.

## Step 1: Python

The script `examples/tutorials/t30_trials_and_power.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t30_trials_and_power.py -->
```python
"""Tutorial 30: how many trials can a result survive, and how long must a study run? The deflated
Sharpe ratio against the number of trials, the PSR against sample length, and sample sizes for a target power.

  uv run --project python python examples/tutorials/t30_trials_and_power.py         # Python
  python examples/tutorials/t30_trials_and_power.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-30-trials-and-power.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import math
import sys
from statistics import NormalDist

from qf import connect


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def main(cli):
    call = connect(cli)
    sr_annual = 1.0
    sr = sr_annual / math.sqrt(252)  # daily Sharpe 0.0630
    shape = {"skew": -0.5, "kurtosis": 5.0}

    # 1. One strategy, annual Sharpe 1.0, three years of daily returns: the deflated Sharpe as trials grow.
    #    sr_variance is the variance of the daily Sharpe across the trials, here (0.5 / sqrt(252))^2.
    for n_trials in (1, 10, 100, 1000):
        r = call("research.stats.dsr", {"sr": sr, "n_obs": 756, "n_trials": n_trials,
                                        "sr_variance": (0.5 / math.sqrt(252)) ** 2, **shape})
        print(f"trials {n_trials:>4}: SR0 annual {num(r['sr0'] * math.sqrt(252), 3)}  DSR {num(r['dsr'], 4)}")

    # 2. The probabilistic Sharpe against a zero benchmark as the history lengthens.
    for years in (1, 3, 5, 10):
        r = call("research.stats.psr", {"sr": sr, "n_obs": 252 * years, "sr_benchmark": 0.0, **shape})
        print(f"PSR, {years:>2} years: {num(r['psr'], 4)}")

    # 3. Planning: the minimum detectable Sharpe for a given length, and the years for a target.
    for years in (1.0, 5.0, 10.0, 20.0):
        r = call("research.stats.power", {"years": years})
        print(f"{num(years, 0):>2} years: minimum detectable annual Sharpe {num(r['mds'], 3)}")
    for target in (0.5, 1.0, 2.0):
        r = call("research.stats.power", {"years": 1.0, "sr_target": target})
        z = NormalDist().inv_cdf(0.95) + NormalDist().inv_cdf(0.8)
        print(f"target Sharpe {num(target, 1)}: years required {num(r['years_required'], 2)}"
              f"  by hand {num((z / target) ** 2, 2)}")
    r = call("research.stats.power", {"years": 3.0, "alpha": 0.01, "power": 0.9})
    print(f"3 years at alpha 0.01 and power 0.9: minimum detectable annual Sharpe {num(r['mds'], 3)}")


if __name__ == "__main__":
    main(sys.argv[1:])
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t30_trials_and_power.py
```

Real output, 2026-11-15, Windows 11 (Python build):

<!-- tutorial:expect -->
```text
trials    1: SR0 annual 0.000  DSR 0.9555
trials   10: SR0 annual 0.787  DSR 0.6413
trials  100: SR0 annual 1.265  DSR 0.3259
trials 1000: SR0 annual 1.628  DSR 0.1429
PSR,  1 years: 0.8366
PSR,  3 years: 0.9555
PSR,  5 years: 0.9860
PSR, 10 years: 0.9991
 1 years: minimum detectable annual Sharpe 2.486
 5 years: minimum detectable annual Sharpe 1.112
10 years: minimum detectable annual Sharpe 0.786
20 years: minimum detectable annual Sharpe 0.556
target Sharpe 0.5: years required 24.73  by hand 24.73
target Sharpe 1.0: years required 6.18  by hand 6.18
target Sharpe 2.0: years required 1.55  by hand 1.55
3 years at alpha 0.01 and power 0.9: minimum detectable annual Sharpe 2.083
```

### Reading the numbers

- **One trial: DSR equals PSR.** With `N = 1` the spec sets `SR0 = 0` (ruling J-13), so the DSR, 0.9555, is the PSR against zero of the same three years; the `PSR, 3 years` line prints the same 0.9555. By hand: the daily Sharpe is `1 / sqrt(252) = 0.0630`; `z = 0.0630 x sqrt(755) / sqrt(1 + 0.5 x 0.0630 + (5 - 1)/4 x 0.0630^2) = 1.701`, and `Phi(1.701) = 0.9555`.
- **Ten trials.** With the trials' annual Sharpe ratios spread with standard deviation 0.5, `SR0 = 0.5 x ((1 - gamma) Phi^-1(0.9) + gamma Phi^-1(1 - 1/(10 e)))` in annual terms, `= 0.5 x (0.4228 x 1.2816 + 0.5772 x 1.7894) = 0.787`, with `gamma` the Euler-Mascheroni constant. The strategy's 1.0 is only a little above what the best of ten worthless trials would show, and the DSR falls to 0.6413.
- **A hundred and a thousand.** `SR0` reaches 1.265 and 1.628, above the strategy's own Sharpe; the DSR, 0.3259 and 0.1429, says the result is more likely luck than skill. `SR0` grows slowly with `N` (roughly as `sqrt(2 ln N)`), so every factor of ten in trials costs about the same.
- **Length helps, slowly.** PSR against zero is 0.8366 after one year and 0.9991 after ten: `z` grows as `sqrt(T)`.
- **What a study can see.** The minimum detectable annual Sharpe at `alpha = 0.05` and power 0.8 is `2.4865 / sqrt(years)`: 2.486 for one year, 1.112 for five, 0.786 for ten, 0.556 for twenty. A one-year track record cannot tell a Sharpe of 1 from zero with that power.
- **Years needed.** `(2.4865 / SR)^2`: 24.73 years for a Sharpe of 0.5, 6.18 for 1.0, 1.55 for 2.0. The script's "by hand" column computes the same from the standard library's normal quantiles.
- **A stricter test costs length.** At `alpha = 0.01` and power 0.9, `z_sum = 2.3263 + 1.2816 = 3.6079`, so three years detect only a Sharpe of 2.083.

### The formal statement, checked against the spec

From [`11-research/research-statistics.md`](../../specifications/11-research/research-statistics.md) (rulings J-13 to J-18 in [`stage-j-rulings-w1.md`](../../specifications/stage-j-rulings-w1.md)). PSR [BLdP12]: `z = (SR - SR*) sqrt(T - 1) / sqrt(1 - g3 SR + (g4 - 1)/4 SR^2)` with `g3` the skew and `g4` the kurtosis (not excess), `psr = Phi(z)`. DSR [BLdP14]: the same with `SR* = SR0 = sqrt(V) ((1 - gamma) Phi^-1(1 - 1/N) + gamma Phi^-1(1 - 1/(N e)))`, `V = sr_variance` the variance of the per-period Sharpe ratios across trials, and `SR0 = 0` when `N = 1`. Power [Lo02]: `z_sum = Phi^-1(1 - alpha) + Phi^-1(power)`, `mds = z_sum / sqrt(years)`, `years_required = (z_sum / sr_target)^2`. The spec warns that this iid formula understates the MDS under serial correlation, which is why the R3 studies report a simulated power beside it.

All Sharpe inputs to `psr` and `dsr` are per period (daily here); `power` works in annual units. The script converts with `sqrt(252)`.

## Step 2: the same in Rust, Java and C++

`examples/tutorials/t30_trials_and_power.py` sends the same cases (four `research.stats.dsr`, four `research.stats.psr`, eight `research.stats.power`) to whichever CLI you name and prints the same lines.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t30_trials_and_power.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t30_trials_and_power.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t30_trials_and_power.py cpp26/build/quantforge
```

Each is to print the sixteen lines of step 1, digit for digit. The full check is `python conformance/runner/runner.py --impl rust --suite rstats_j`.

## For practitioners

- **Log every trial, including the ones you threw away.** The DSR is only as honest as `N`. In this project the count comes from the trial registry, `research/trials.csv`, and a study may not pass a smaller `N`.
- **Do the power calculation before the study.** If the MDS is above any Sharpe you could plausibly hope for, a null result will be uninformative; the R3 studies of this project had a pass probability of 13 % to 15 % at their MDS, and their write-up says so (`research/r3/RESULTS.md`).
- **`sr_variance` matters as much as `N`.** Trials that are near copies of each other have a small spread and a small `SR0`; genuinely different trials raise it.
- **Fat left tails cost you.** Negative skew and high kurtosis widen the denominator of `z`; a strategy that sells insurance needs a longer record for the same PSR.

## Common mistakes

- **Passing an annual Sharpe to `psr` or `dsr`.** They expect the per-period value; an annual 1.0 passed as daily makes almost anything significant.
- **Counting only the final variants as trials.** Every parameter setting, universe and period tried counts.
- **Reading a high PSR as proof of a high Sharpe.** It is the probability that the true Sharpe exceeds the benchmark, not an estimate of its size.
- **Treating the MDS as the Sharpe you will see.** It is the size that would be detected with probability 0.8; smaller real effects are usually missed.

## What you just did

You saw a Sharpe of 1.0 go from convincing (DSR 0.9555) to doubtful (0.1429) as the trial count rose from 1 to 1,000, checked `SR0` and the one-trial DSR by hand, watched PSR rise with the square root of the sample length, and worked out how long a study must run to detect a given Sharpe at two test strengths.

## Try next

- Halve `sr_variance` and predict how far `SR0` moves for 100 trials.
- Find the number of trials at which the DSR falls below 0.95 for this strategy.
- Set skew to 0 and kurtosis to 3 (normal returns) and compare the PSR after one year.

## References and further reading

- D. H. Bailey, M. Lopez de Prado, "The Sharpe ratio efficient frontier", *Journal of Risk* 15(2), 2012, 3-44. Not opened per the spec.
- D. H. Bailey, M. Lopez de Prado, "The deflated Sharpe ratio: correcting for selection bias, backtest overfitting and non-normality", *Journal of Portfolio Management* 40(5), 2014, 94-107. Paper read per the spec (2026-11-13).
- A. W. Lo, "The statistics of Sharpe ratios", *Financial Analysts Journal* 58(4), 2002, 36-52. Not opened per the spec.
- This project: [`11-research/research-statistics.md`](../../specifications/11-research/research-statistics.md), [Tutorial 24](tutorial-24-is-the-sharpe-real.md), all sources in [References](../references.md).
