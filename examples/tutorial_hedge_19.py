#!/usr/bin/env python3
"""Tutorial 19 through any language's CLI: a CDS hedge in CS01 and jump to default, and a correlation hedge.

  python examples/tutorial_hedge_19.py rust/target/release/quantforge
  python examples/tutorial_hedge_19.py java -jar java25/target/quantforge-cli.jar

Standard library only. It sends the cases of docs/getting-started/tutorial-19-credit-correlation.md, built
from examples/hedge_credit_i.json and hedge_correlation_i.json, to `quantforge batch` and prints the same
lines as the Python section of the tutorial.
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


def run(cli, cases):
    """The whole result object of each case, in order; errors are left to the caller."""
    text = "".join(json.dumps(c) + "\n" for c in cases)
    p = subprocess.run(cli, input=text, capture_output=True, text=True, check=True)
    return [json.loads(line) for line in p.stdout.splitlines() if line.strip()]


def outputs(result):
    if result["status"] != "ok":
        raise SystemExit(f"{result['case_id']}: {result['error']}")
    return result["outputs"]


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def nums(values, places):
    return " ".join(num(v, places) for v in values)


def main(cli):
    cli = [shutil.which(cli[0]) or cli[0], *cli[1:], "batch"]  # finds quantforge.exe on Windows
    corr = load("hedge_correlation_i")
    exch = [{"instrument": "EXCHANGE", "quantity1": 1.0, "quantity2": 1.0, "expiry_years": t} for t in (0.5, 1.5)]
    call = {"instrument": "CALL_1", "strike": 100.0, "expiry_years": 1.0}
    variants = []
    for name, hedge_set in (("exchange-only", exch), ("exchange-call", [exch[0], call])):
        v = copy.deepcopy(corr)
        v["case_id"] += "-" + name
        v["inputs"]["book"].append({"instrument": "CALL_1", "strike": 110.0, "expiry_years": 1.0, "quantity": 300.0})
        v["inputs"]["hedges"] = hedge_set
        v["inputs"]["targets"] = ["CORRELATION", "VEGA_1"]
        variants.append(v)
    credit, k, *checks = run(cli, [load("hedge_credit_i"), corr, *variants])

    r = outputs(credit)
    print(f"book CS01 {num(r['book']['cs01'], 2)}  JTD {num(r['book']['jtd'], 2)}")
    print(f"buy protection 3y {num(r['notionals'][0], 2)}  10y {num(r['notionals'][1], 2)}")
    print(f"after CS01 {num(r['after']['cs01'], 2)}  JTD {num(r['after']['jtd'], 2)}")
    print(f"after buckets {nums(r['after']['buckets'], 2)}")
    r = outputs(k)
    g = r["greeks_before"]
    print(f"book correlation01 {num(g['correlation01'], 4)}  vega1 {num(g['vega_1'], 2)}  vega2 {num(g['vega_2'], 2)}")
    print(f"hedge {nums(r['quantities'], 4)}")
    for label, result in zip(("two exchange options", "exchange option + call"), checks):
        if result["status"] == "ok":
            print(f"{label}: {nums(result['outputs']['quantities'], 4)}")
        else:
            print(f"{label}: {result['error']['code']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
