#!/usr/bin/env python3
"""Tutorial 17 through any language's CLI: a Greek hedge, a delta-hedge backtest, hedge effectiveness.

  python examples/tutorial_hedge_17.py rust/target/release/quantforge
  python examples/tutorial_hedge_17.py java -jar java25/target/quantforge-cli.jar

Standard library only. It sends the cases of docs/getting-started/tutorial-17-delta-hedge.md, built from
examples/hedge_greeks_i.json, hedge_backtest_i.json and hedge_effectiveness_i.json, to `quantforge batch`
and prints the same lines as the Python section of the tutorial.
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


def main(cli):
    cli = [shutil.which(cli[0]) or cli[0], *cli[1:], "batch"]  # finds quantforge.exe on Windows
    daily = load("hedge_backtest_i")
    n = len(daily["inputs"]["times"])
    weekly = copy.deepcopy(daily)
    keep = list(range(0, n, 5)) + [n - 1]
    for key in ("times", "spots"):
        weekly["inputs"][key] = [daily["inputs"][key][k] for k in keep]
    weekly["case_id"] += "-weekly"
    greeks, d, w, s = batch(cli, [load("hedge_greeks_i"), daily, weekly, load("hedge_effectiveness_i")])

    before, after, q = greeks["greeks_before"], greeks["greeks_after"], greeks["quantities"]
    print(f"book   delta {num(before['delta'], 4)}  gamma {num(before['gamma'], 4)}  vega {num(before['vega'], 2)}")
    print(f"hedge  shares {num(q[0], 4)}  105 calls {num(q[1], 4)}  95 puts {num(q[2], 4)}")
    print(f"after  delta {num(after['delta'], 4)}  gamma {num(after['gamma'], 4)}  vega {num(after['vega'], 2)}")
    for label, r in (("daily ", d), ("weekly", w)):
        print(f"{label} final P&L {num(r['final_pnl'], 2)}  dollar offset {num(r['dollar_offset'], 4)}"
              f"  slope {num(r['regression_slope'], 4)}  R2 {num(r['regression_r2'], 4)}")
    print(f"monthly dollar offset {num(s['dollar_offset'], 4)}  slope {num(s['regression_slope'], 4)}"
          f"  R2 {num(s['regression_r2'], 4)}  variance reduction {num(s['variance_reduction'], 4)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
