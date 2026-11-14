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
