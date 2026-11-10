#!/usr/bin/env python3
"""Tutorial 1 through any language's CLI: build a SOFR curve, price a 5Y swap, take its DV01.

  python examples/tutorial_swap.py rust/target/release/quantforge
  python examples/tutorial_swap.py java -jar java25/target/quantforge-cli.jar

Standard library only. It sends the three cases of docs/getting-started/tutorial-1-swap.md to
`quantforge batch` and prints the same four lines as the Python section of the tutorial.
"""
import json
import shutil
import subprocess
import sys

AS_OF = "2026-11-06"
QUOTES = [{"tenor": t, "rate": r} for t, r in
          [("1Y", 0.035), ("2Y", 0.0335), ("3Y", 0.033), ("5Y", 0.0335), ("7Y", 0.0345), ("10Y", 0.036)]]
TRADE = {"convention": "SOFR", "tenor": "5Y", "fixed_rate": 0.034, "notional": 10_000_000.0, "side": "PAY"}


def case(case_id, operation, inputs):
    return {"schema_version": "1.0", "case_id": case_id, "operation": operation, "inputs": inputs}


def batch(cli, cases):
    text = "".join(json.dumps(c) + "\n" for c in cases)
    p = subprocess.run(cli, input=text, capture_output=True, text=True, check=True)
    results = [json.loads(line) for line in p.stdout.splitlines() if line.strip()]
    for r in results:
        if r["status"] != "ok":
            raise SystemExit(f"{r['case_id']}: {r['error']}")
    return [r["outputs"] for r in results]


def main(cli):
    cli = [shutil.which(cli[0]) or cli[0], *cli[1:], "batch"]  # finds quantforge.exe on Windows
    common = {"as_of": AS_OF, "quotes": QUOTES, "interpolation": "LOG_LINEAR_DF"}
    [curve] = batch(cli, [case("t1-curve", "rates.ois.bootstrap", {"convention": "SOFR", "method": "SEQUENTIAL", **common})])
    curve = {"as_of": AS_OF, "interpolation": "LOG_LINEAR_DF", "pillars": curve["pillars"]}
    priced, risk = batch(cli, [case("t1-pv", "rates.ois.pv", {"curve": curve, "trade": TRADE}),
                               case("t1-dv01", "risk.ois.dv01", {**common, "trade": TRADE})])
    print(f"1Y discount factor {curve['pillars'][0]['discount_factor']:.12f}")
    print(f"PV   {priced['valuation']['pv']:.4f} {priced['valuation']['currency']}")
    print(f"par  {priced['par_rate']:.10f}")
    print(f"DV01 {risk['dv01']:.4f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
