#!/usr/bin/env python3
"""Tutorial 21 through any language's CLI: spread, impact and margin in a hedge, the frontier, costs in a
backtest, and slippage.

  python examples/tutorial_hedge_21.py rust/target/release/quantforge
  python examples/tutorial_hedge_21.py java -jar java25/target/quantforge-cli.jar

Standard library only. It sends the cases of docs/getting-started/tutorial-21-hedge-costs.md, built from
examples/hedge_cost_i.json, hedge_frontier_i.json, hedge_backtest_i.json and hedge_slippage_i.json, to
`quantforge batch` and prints the same lines as the Python section of the tutorial.
"""
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent


def load(name):
    return json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def variant(case, suffix, drop=(), **changes):
    out = copy.deepcopy(case)
    out["case_id"] += "-" + suffix
    for key in drop:
        del out["inputs"][key]
    out["inputs"].update(changes)
    return out


def batch(cli, cases):
    text = "".join(json.dumps(c) + "\n" for c in cases)
    p = subprocess.run(cli, input=text, capture_output=True, text=True, check=True)
    results = [json.loads(line) for line in p.stdout.splitlines() if line.strip()]
    for r in results:
        if r["status"] != "ok":
            raise SystemExit(f"{r['case_id']}: {r['error']}")
    return [r["outputs"] for r in results]


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def nums(values, places):
    return " ".join(num(v, places) for v in values)


def main(cli):
    cli = [shutil.which(cli[0]) or cli[0], *cli[1:], "batch"]  # finds quantforge.exe on Windows
    cost, daily = load("hedge_cost_i"), load("hedge_backtest_i")
    n = len(daily["inputs"]["times"])
    keep = list(range(0, n, 5)) + [n - 1]
    weekly = {key: [daily["inputs"][key][k] for k in keep] for key in ("times", "spots")}
    free, r, m, front, d, w, s = batch(cli, [
        variant(cost, "free", drop=("half_spreads",)), cost,
        variant(cost, "impact-margin", impact=[0.05, 0.05, 0.05], margin_rates=[0.1, 0.1, 0.1], margin_limit=0.15),
        load("hedge_frontier_i"),
        variant(daily, "cost", half_spread=0.02), variant(daily, "weekly-cost", half_spread=0.02, **weekly),
        load("hedge_slippage_i")])

    print(f"no cost     x {nums(free['x'], 4)}  risk {num(free['objective'], 4)}")
    print(f"with spread x {nums(r['x'], 4)}  risk {num(r['risk'], 4)}  cost {num(r['cost'], 4)}")
    print(f"impact+margin x {nums(m['x'], 4)}  risk {num(m['risk'], 4)}  cost {num(m['cost'], 4)}  margin {num(m['margin'], 4)}")
    for p in front["points"]:
        print(f"frontier weight {num(p['cost_weight'], 1):>5}  risk {num(p['risk'], 4)}  cost {num(p['cost'], 4)}")
    for label, b in (("daily ", d), ("weekly", w)):
        print(f"{label} with costs: final P&L {num(b['final_pnl'], 2)}  trading cost {num(b['trading_cost'], 2)}")
    t = s["total"]
    print(f"shortfall {num(t['shortfall'], 2)} = execution {num(t['execution_cost'], 2)}"
          f" + opportunity {num(t['opportunity_cost'], 2)};  model {num(t['model_cost'], 2)}  slippage {num(t['slippage'], 2)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
