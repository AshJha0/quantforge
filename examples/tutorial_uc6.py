#!/usr/bin/env python3
"""Tutorial 21, use case 6, through any language's CLI: hedge an option book in whole lots.

  python examples/tutorial_uc6.py rust/target/release/quantforge
  python examples/tutorial_uc6.py java -jar java25/target/quantforge-cli.jar

Standard library only. It sends golden case uc6_r6-0001 (datasets/golden/r6/uc6_r6.json, synthetic) to
`quantforge batch` and prints the lines shown in docs/getting-started/tutorial-21-hedge-costs.md.
The operation `usecase.option_hedge_lots` is new in CLI contract 1.12.0; a build without it exits with
the error code it returns.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

GOLDEN = Path(__file__).resolve().parent.parent / "datasets" / "golden" / "r6" / "uc6_r6.json"


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def main(cli):
    cli = [shutil.which(cli[0]) or cli[0], *cli[1:], "batch"]  # finds quantforge.exe on Windows
    case = next(c for c in json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]
                if c["case_id"] == "uc6_r6-0001")
    request = {"schema_version": "1.0", **{key: case[key] for key in ("case_id", "operation", "inputs")}}
    p = subprocess.run(cli, input=json.dumps(request) + "\n", capture_output=True, text=True, check=True)
    r = json.loads(p.stdout.splitlines()[0])
    if r["status"] != "ok":
        raise SystemExit(f"{r['case_id']}: {r['error']}")
    o = r["outputs"]
    b, a = o["greeks_before"], o["greeks_after"]
    print(f"delta before {num(b['delta'], 2)}  lots {o['lots']}  delta after {num(a['delta'], 2)}")
    print(f"gamma {num(a['gamma'], 2)}  vega {num(a['vega'], 2)}")
    print(f"hedge_cost {num(o['hedge_cost'], 4)}  rounding_cost {num(o['rounding_cost'], 4)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
