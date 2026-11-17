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
