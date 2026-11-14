"""Tutorial 23: a backtest run by both engines, the look-ahead canary, costs and their
attribution, purged k-fold with an embargo, and the combinatorial purged CV counts.

  uv run --project python python examples/tutorials/t23_backtest.py         # Python
  python examples/tutorials/t23_backtest.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-23-backtest-honestly.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import sys

from qf import connect


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def main(cli):
    call = connect(cli)  # the Python package with no arguments, else that build's batch command
    prices = [100.0, 101.0, 99.5, 102.0, 103.0, 101.5, 100.0, 104.0, 105.5, 103.0, 106.0, 107.0]
    targets = [1.0, 2.0, -1.0, 0.0, 3.0, 3.0, -2.0, 1.0, 0.0, 2.0, 0.0, 0.0]
    costs = {"half_spread_bps": 5.0, "commission_per_unit": 0.01, "fixed_per_trade": 1.0}

    # 1. One strategy, both engines, lag 1: the same numbers.
    for engine in ("EVENT", "VECTOR"):
        r = call("research.backtest.run", {"prices": prices, "targets": targets, "lag": 1,
                                           "engine": engine, **costs})
        print(f"{engine:<6} positions {' '.join(num(q, 0) for q in r['positions'])}"
              f"  equity end {num(r['equity'][-1], 5)}")

    # 2. The attribution: gross minus the three costs is net, exactly.
    print(f"gross {num(r['total_gross'], 5)} - spread {num(r['total_spread_cost'], 5)}"
          f" - commission {num(r['total_commission'], 5)} - fixed {num(r['total_fixed_cost'], 5)}"
          f" = net {num(r['total_net'], 5)}")
    print(f"trades {r['trade_count']}  turnover {num(r['turnover'], 2)}"
          f"  max drawdown {num(r['max_drawdown'], 5)}")

    # 3. The look-ahead canary: a target that knows the next move.
    peek = [(1.0 if prices[t + 1] > prices[t] else -1.0) for t in range(len(prices) - 1)] + [0.0]
    for lag in (0, 1):
        r = call("research.backtest.run", {"prices": prices, "targets": peek, "lag": lag})
        print(f"canary lag {lag}: gross {num(r['total_gross'], 2)}")

    # 4. Ten observations in three folds: plain k-fold (labels one bar long), then labels spanning
    #    three bars (purged), then the same with a 30 % embargo.
    t0 = list(range(10))
    for label, span, pct in (("plain ", 0, 0.0), ("purged", 2, 0.0), ("+embargo", 2, 0.3)):
        r = call("research.cv.purged_kfold", {"t0": t0, "t1": [t + span for t in t0],
                                              "n_splits": 3, "embargo_pct": pct})
        folds = "  ".join(f"test {f['test'][0]}-{f['test'][-1]} train {','.join(map(str, f['train']))}"
                          for f in r["folds"])
        print(f"{label:<8} {folds}")

    # 5. Combinatorial purged CV: how many splits and backtest paths.
    for n, k in ((6, 2), (10, 2), (10, 3)):
        r = call("research.cv.cpcv_paths", {"n_groups": n, "n_test_groups": k})
        print(f"CPCV N {n} k {k}: splits {r['n_splits']} paths {r['n_paths']}")


if __name__ == "__main__":
    main(sys.argv[1:])
