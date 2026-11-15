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
