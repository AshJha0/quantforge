"""Tutorial 11: prepayment (PSA against CPR), pass-through cash flows,
price, modified duration and WAL, and price at bumped yields and speeds.

  uv run --project python python examples/tutorials/t11_mbs.py         # Python
  python examples/tutorials/t11_mbs.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-11-mbs.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import json
import sys

from qf import runner


def pool(model, speed):
    key = "speed" if model == "PSA" else "rate"
    return {"balance": 2_500_000.0, "wac": 0.0575, "net_coupon": 0.0525, "wam": 357, "age": 3,
            "prepayment": {"model": model, key: speed}}


def case(case_id, operation, inputs):
    return {"schema_version": "1.0", "case_id": case_id, "operation": operation, "inputs": inputs}


def price_case(case_id, model, speed, y):
    return case(case_id, "mbs.price", {"pool": pool(model, speed), "yield": y, "delay_days": 24})


def batch(run, cases):
    results = run(cases)
    for r in results:
        if r["status"] != "ok":
            raise SystemExit(f"{r['case_id']}: {r['error']}")
    return [r["outputs"] for r in results]


def main(cli):
    cli = runner(cli)  # the Python package with no arguments, else that build's batch command
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
    main(sys.argv[1:])
