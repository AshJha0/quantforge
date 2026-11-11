#!/usr/bin/env python3
"""Tutorial 11 through any language's CLI: prepayment (PSA against CPR), pass-through cash flows,
price, modified duration and WAL, and price at bumped yields and speeds.

  python examples/tutorial_mbs.py rust/target/release/quantforge
  python examples/tutorial_mbs.py java -jar java25/target/quantforge-cli.jar

Standard library only. It sends the cases of docs/getting-started/tutorial-11-mbs.md to
`quantforge batch` and prints the same lines as the Python section of the tutorial.
"""
import json
import shutil
import subprocess
import sys


def pool(model, speed):
    key = "speed" if model == "PSA" else "rate"
    return {"balance": 2_500_000.0, "wac": 0.0575, "net_coupon": 0.0525, "wam": 357, "age": 3,
            "prepayment": {"model": model, key: speed}}


def case(case_id, operation, inputs):
    return {"schema_version": "1.0", "case_id": case_id, "operation": operation, "inputs": inputs}


def price_case(case_id, model, speed, y):
    return case(case_id, "mbs.price", {"pool": pool(model, speed), "yield": y, "delay_days": 24})


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
    models = (("PSA", 100.0), ("CPR", 0.06))
    flows = batch(cli, [case(f"t11-flows-{m}", "mbs.cashflows", {"pool": pool(m, s)}) for m, s in models])
    for (model, speed), f in zip(models, flows):
        print(f"{model} {speed:g}: prepayment month 1 {f['prepayment'][0]:.2f}, "
              f"month 27 {f['prepayment'][26]:.2f}, WAL {f['wal']:.4f}")
    yields, speeds = (0.054, 0.064), (50.0, 200.0, 300.0)
    base, *rest = batch(cli, [price_case("t11-base", "PSA", 100.0, 0.059),
                              *(price_case(f"t11-y{y}", "PSA", 100.0, y) for y in yields),
                              *(price_case(f"t11-s{s}", "PSA", s, 0.059) for s in speeds)])
    print(f"price {base['price']:.6f} modified duration {base['modified_duration']:.6f} WAL {base['wal']:.6f}")
    for y, out in zip(yields, rest[:2]):
        print(f"yield {y:.3f}: price {out['price']:.6f}")
    for s, out in zip(speeds, rest[2:]):
        print(f"PSA {s:g}: price {out['price']:.6f} modified duration {out['modified_duration']:.6f} "
              f"WAL {out['wal']:.6f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
