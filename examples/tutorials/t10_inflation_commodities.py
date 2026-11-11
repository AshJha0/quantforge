"""Tutorial 10: a CPI curve with seasonality, a zero-coupon inflation
swap, a commodity forward curve and storage carry.

  uv run --project python python examples/tutorials/t10_inflation_commodities.py         # Python
  python examples/tutorials/t10_inflation_commodities.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-10-inflation-commodities.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import json
import sys

from qf import runner

QUOTES = [{"years": y, "rate": r} for y, r in
          [(1, 0.0265), (2, 0.0255), (3, 0.025), (5, 0.0245), (7, 0.0245), (10, 0.025), (20, 0.0255)]]
SEASON = [0.9978, 0.9992, 1.0011, 1.0018, 1.0012, 1.0005,
          0.9989, 0.9994, 1.0006, 1.0003, 0.9995, 0.9997]
DISCOUNT = {"as_of": "2026-11-06", "interpolation": "LOG_LINEAR_DF", "pillars": [
    {"date": d, "discount_factor": v} for d, v in
    [("2027-11-15", 0.9634397330592425), ("2028-11-14", 0.9318539967570951),
     ("2029-11-15", 0.9012037662703272), ("2031-11-13", 0.839287128565213)]]}
GAS = [{"month": m, "price": p} for m, p in
       [("2026-12", 3.42), ("2027-03", 3.105), ("2027-06", 2.88),
        ("2027-12", 3.56), ("2028-12", 3.64), ("2030-12", 3.7)]]
GAS_SEASON = [0.06, 0.045, 0.01, -0.03, -0.045, -0.04, -0.02, -0.015, -0.02, 0.0, 0.025, 0.03]
FUNDING = {"as_of": "2026-11-06", "interpolation": "LOG_LINEAR_DF", "pillars": [
    {"date": d, "discount_factor": v} for d, v in
    [("2027-05-06", 0.9803598150999601), ("2027-11-08", 0.9615452062959098),
     ("2028-11-06", 0.9267197211276171), ("2031-11-06", 0.8310200391947283)]]}
OIL = [{"date": d, "price": p} for d, p in
       [("2026-12-15", 75.2), ("2027-03-15", 74.1), ("2027-06-15", 75.9),
        ("2027-12-15", 78.4), ("2028-12-15", 76.0)]]


def case(case_id, operation, inputs):
    return {"schema_version": "1.0", "case_id": case_id, "operation": operation, "inputs": inputs}


def batch(run, cases):
    results = run(cases)
    for r in results:
        if r["status"] != "ok":
            raise SystemExit(f"{r['case_id']}: {r['error']}")
    return [r["outputs"] for r in results]


def main(cli):
    cli = runner(cli)  # the Python package with no arguments, else that build's batch command
    smooth = {"base_month": "2026-08", "base_cpi": 322.15, "quotes": QUOTES, "seasonality": None}
    seasonal = {**smooth, "seasonality": SEASON}
    months = ["2026-12", "2027-01", "2027-08"]
    trade = {"years": 5, "fixed_rate": 0.026, "notional": 10_000_000.0, "side": "RECEIVE_INFLATION",
             "payment_date": "2031-11-10"}
    cpi_s, cpi_x, zcis, gas, carry = batch(cli, [
        case("t10-cpi-smooth", "infl.curve.cpi", {**smooth, "months": months}),
        case("t10-cpi-seasonal", "infl.curve.cpi", {**seasonal, "months": months}),
        case("t10-zcis", "infl.zcis.pv", {"curve": seasonal, "discount": DISCOUNT, "trade": trade}),
        case("t10-gas", "cmdty.curve.forward", {"quotes": GAS, "seasonality": GAS_SEASON,
                                                "months": ["2027-01", "2027-08", "2028-07"]}),
        case("t10-carry", "cmdty.storage.carry", {"funding": FUNDING, "forwards": OIL,
                                                  "storage_cost": 0.02})])
    for label, out in (("smooth  ", cpi_s), ("seasonal", cpi_x)):
        print(label, " ".join(f"{x:.4f}" for x in out["cpi"]))
    print(f"ZCIS index ratio {zcis['index_ratio']:.10f}")
    print(f"ZCIS PV {zcis['pv']:.2f}")
    print("gas forwards", " ".join(f"{x:.6f}" for x in gas["forwards"]))
    for f, y, v, a in zip(OIL[1:], carry["convenience_yields"], carry["carry_values"], carry["arbitrage"]):
        print(f"to {f['date']} convenience yield {y:+.6f} carry {v:+.6f} arbitrage {a}")


if __name__ == "__main__":
    main(sys.argv[1:])
