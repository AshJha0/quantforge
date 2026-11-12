#!/usr/bin/env python3
"""Tutorial 20 through any language's CLI: one hedge for equity and rates, and choosing the best instruments.

  python examples/tutorial_hedge_20.py rust/target/release/quantforge
  python examples/tutorial_hedge_20.py java -jar java25/target/quantforge-cli.jar

Standard library only. It sends the cases of docs/getting-started/tutorial-20-cross-asset.md, built from
examples/hedge_crossasset_i.json and hedge_select_i.json, to `quantforge batch` and prints the same lines
as the Python section of the tutorial.
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


def variant(case, suffix, **changes):
    out = copy.deepcopy(case)
    out["case_id"] += "-" + suffix
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
    xa, sel = load("hedge_crossasset_i"), load("hedge_select_i")
    hedges = xa["inputs"]["hedges"]
    five = {"instrument": "ZCB", "expiry_years": 5.0, "notional": 1000000.0}
    r, r5, eq, s1, s2 = batch(cli, [xa, variant(xa, "add-5y", hedges=hedges + [five]),
                                    variant(xa, "equity-only", hedges=hedges[:1]),
                                    variant(sel, "k1", max_instruments=1),
                                    variant(sel, "k2", max_instruments=2)])
    print(f"book risk     {nums(r['book_risk'], 2)}")
    print(f"hedge         {nums(r['positions'], 4)}")
    print(f"residual risk {nums(r['residual_risk'], 2)}")
    print(f"add 5y bond   {nums(r5['positions'], 4)}  residual {nums(r5['residual_risk'], 2)}")
    print(f"equity only   {nums(eq['positions'], 4)}  residual {nums(eq['residual_risk'], 2)}")
    for k, s in ((1, s1), (2, s2)):
        print(f"best {k}: instruments {s['selected']}  x {nums(s['x'], 4)}  objective {num(s['objective'], 4)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
