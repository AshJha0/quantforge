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
