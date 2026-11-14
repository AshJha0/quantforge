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
