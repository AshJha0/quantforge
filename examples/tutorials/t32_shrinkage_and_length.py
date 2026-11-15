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
