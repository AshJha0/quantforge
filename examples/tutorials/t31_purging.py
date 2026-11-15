"""Tutorial 31: leakage and how purging removes it. Training-set sizes as the label horizon and
the embargo grow, a check that no training label overlaps the test span, and a table of CPCV counts.

  uv run --project python python examples/tutorials/t31_purging.py         # Python
  python examples/tutorials/t31_purging.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-31-leakage-and-purging.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import math
import sys

from qf import connect


def leaks(t0, t1, fold):
    # A training label leaks when its window [t0, t1] overlaps the span of the test labels.
    lo = min(t0[i] for i in fold["test"])
    hi = max(t1[i] for i in fold["test"])
    return sum(1 for i in fold["train"] if t0[i] <= hi and t1[i] >= lo)


def main(cli):
    call = connect(cli)
    n, k = 100, 5
    t0 = list(range(n))

    # 1. Labels that look h bars ahead, 5 folds, no embargo then a 2 % embargo.
    for h in (0, 5, 20):
        t1 = [t + h for t in t0]
        for embargo in (0.0, 0.02):
            r = call("research.cv.purged_kfold", {"t0": t0, "t1": t1, "n_splits": k, "embargo_pct": embargo})
            sizes = [len(f["train"]) for f in r["folds"]]
            leaked = sum(leaks(t0, t1, f) for f in r["folds"])
            print(f"horizon {h:>2} embargo {embargo:.2f}: train sizes {sizes}  embargo_count"
                  f" {r['embargo_count']}  leaking labels {leaked}")

    # 2. What plain k-fold would have kept: the same split with the purge undone (t1 = t0).
    t1 = [t + 20 for t in t0]
    plain = call("research.cv.purged_kfold", {"t0": t0, "t1": t0, "n_splits": k})
    print(f"plain 5-fold with 20-bar labels: leaking labels {sum(leaks(t0, t1, f) for f in plain['folds'])}")

    # 3. Combinatorial purged CV: C(N, k) splits and k/N C(N, k) backtest paths.
    for groups in (6, 8, 10):
        row = []
        for test_groups in (1, 2, 3):
            r = call("research.cv.cpcv_paths", {"n_groups": groups, "n_test_groups": test_groups})
            assert r["n_splits"] == math.comb(groups, test_groups)
            assert r["n_paths"] * groups == test_groups * r["n_splits"]
            row.append(f"k={test_groups}: {r['n_splits']:>3} splits {r['n_paths']:>2} paths")
        print(f"N={groups:>2}  " + "   ".join(row))


if __name__ == "__main__":
    main(sys.argv[1:])
