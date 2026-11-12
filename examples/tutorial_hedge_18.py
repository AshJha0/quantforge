#!/usr/bin/env python3
"""Tutorial 18 through any language's CLI: minimum-variance, beta, key-rate, minimum-norm and integer hedges.

  python examples/tutorial_hedge_18.py rust/target/release/quantforge
  python examples/tutorial_hedge_18.py java -jar java25/target/quantforge-cli.jar

Standard library only. It sends the cases of docs/getting-started/tutorial-18-minvar-qp.md, built from
examples/hedge_minvar_i.json, hedge_beta_i.json, hedge_qp_keyrate_i.json, hedge_qp_minnorm_i.json,
hedge_integer_i.json and hedge_residual_i.json, to `quantforge batch` and prints the same lines as the
Python section of the tutorial.
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


def without(case, *keys):
    """A copy of the case with the named inputs removed."""
    out = copy.deepcopy(case)
    out["case_id"] += "-without-" + "-".join(keys)
    for key in keys:
        del out["inputs"][key]
    return out


def run(cli, cases):
    """The whole result object of each case, in order; errors are left to the caller."""
    text = "".join(json.dumps(c) + "\n" for c in cases)
    p = subprocess.run(cli, input=text, capture_output=True, text=True, check=True)
    return [json.loads(line) for line in p.stdout.splitlines() if line.strip()]


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def nums(values, places):
    return " ".join(num(v, places) for v in values)


def main(cli):
    cli = [shutil.which(cli[0]) or cli[0], *cli[1:], "batch"]  # finds quantforge.exe on Windows
    keyrate, minnorm = load("hedge_qp_keyrate_i"), load("hedge_qp_minnorm_i")
    results = run(cli, [load("hedge_minvar_i"), load("hedge_beta_i"), keyrate,
                        without(keyrate, "lower", "upper"), without(minnorm, "singular"), minnorm,
                        load("hedge_integer_i"), load("hedge_residual_i")])
    singular = results.pop(4)
    for r in results:
        if r["status"] != "ok":
            raise SystemExit(f"{r['case_id']}: {r['error']}")
    mv, bf, kr, free, mn, it, rr = (r["outputs"] for r in results)

    print(f"min-variance hedge {num(mv['hedge'][0], 4)}  effectiveness {num(mv['effectiveness'], 4)}")
    print(f"beta hedge contracts {num(bf['contracts_held'], 0)}  beta after {num(bf['beta_after'], 4)}")
    print(f"key-rate hedge x {nums(kr['x'], 4)}  objective {num(kr['objective'], 4)}")
    print(f"  without bounds x {nums(free['x'], 4)}  objective {num(free['objective'], 4)}")
    print(f"duplicate instruments, default: {singular['error']['code']}")
    print(f"  MIN_NORM x {nums(mn['x'], 4)}  rank {mn['rank']}")
    print(f"integer lots {it['lots']}  objective {num(it['objective'], 6)}  rounding cost {num(it['rounding_cost'], 6)}")
    print(f"residual vol {num(rr['volatility_after'], 6)}  effectiveness {num(rr['effectiveness'], 4)}"
          f"  contributions {nums(rr['contributions'], 8)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
