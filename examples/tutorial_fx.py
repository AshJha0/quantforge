#!/usr/bin/env python3
"""Tutorial 9 through any language's CLI: FX forwards, a cross-currency swap and FX options.

  python examples/tutorial_fx.py rust/target/release/quantforge
  python examples/tutorial_fx.py java -jar java25/target/quantforge-cli.jar

Standard library only. It sends the cases of docs/getting-started/tutorial-9-fx.md to
`quantforge batch` and prints the same lines as the Python section of the tutorial.
Run it from the repository root: the curves are read from examples/*.json (synthetic data).
"""
import json
import shutil
import subprocess
import sys

EURUSD = {"spot": 1.085, "expiry_years": 0.2493150684931507, "domestic_rate": 0.043, "foreign_rate": 0.031}
USDJPY = {"spot": 151.2, "expiry_years": 0.4986301369863014, "domestic_rate": 0.001, "foreign_rate": 0.045}


def example(name):
    with open(f"examples/{name}.json") as f:
        return json.load(f)["inputs"]


def case(case_id, operation, inputs):
    return {"schema_version": "1.0", "case_id": case_id, "operation": operation, "inputs": inputs}


def batch(cli, cases):
    text = "".join(json.dumps(c) + "\n" for c in cases)
    p = subprocess.run(cli, input=text, capture_output=True, text=True, check=True)
    results = [json.loads(line) for line in p.stdout.splitlines() if line.strip()]
    for r in results:
        if r["status"] != "ok":
            raise SystemExit(f"{r['case_id']}: {r['error']}")
    return results


def main(cli):
    cli = [shutil.which(cli[0]) or cli[0], *cli[1:], "batch"]  # finds quantforge.exe on Windows
    g = example("fx_forward_outright")
    market = {"pair": "GBPUSD", "spot": 1.28, "as_of": "2026-11-06",
              "base_curve": g["base_curve"], "quote_curve": g["quote_curve"]}
    x = example("xccy_bootstrap_d")
    usd, estr = x["domestic"], x["foreign_projection"]
    smile = {"atm_vol": 0.075, "rr": -0.0045, "bf": 0.002, "delta": 0.25, "delta_type": "SPOT", "atm_type": "DNS"}
    jp_smile = {"atm_vol": 0.105, "rr": -0.015, "bf": 0.0035, "delta": 0.25, "delta_type": "SPOT_PA",
                "atm_type": "DNS"}
    option = {**EURUSD, "strike": 1.1209, "vol": 0.075, "option_type": "CALL"}
    first = batch(cli, [
        case("t9-spot", "fx.spot_date", {"pair": "GBPUSD", "trade_date": "2026-11-06"}),
        case("t9-fwd", "fx.forward.outright", {**market, "value_date": "2027-11-10"}),
        case("t9-implied", "fx.curve.implied", {**market, "points": [{"tenor": "1Y", "points": -71.0}]}),
        case("t9-xccy", "fx.xccy.bootstrap", {"domestic": usd, "foreign_projection": estr,
                                              "domestic_convention": "SOFR", "foreign_convention": "ESTR",
                                              "start": "2026-11-10", "quotes": x["quotes"],
                                              "interpolation": "LOG_LINEAR_DF"}),
        case("t9-gk", "fx.option.price", {**option, "notional": 1_000_000.0}),
        case("t9-deltas", "fx.delta.from_strike", option),
        case("t9-eu", "fx.smile.from_quotes", {**EURUSD, **smile}),
        case("t9-jp", "fx.smile.from_quotes", {**USDJPY, **jp_smile}),
    ])
    spot, fwd, implied, boot, gk, deltas, eu, jp = (r["outputs"] for r in first)
    error = first[3]["diagnostics"]["max_repricing_error"]
    eur_disc = {"as_of": usd["as_of"], "interpolation": "LOG_LINEAR_DF", "pillars": boot["pillars"]}
    trade = {"start": "2026-11-10", "months": 24, "foreign_notional": 10_000_000.0, "spread": 0.0015,
             "side": "RECEIVE_FOREIGN"}
    [xpv] = (r["outputs"] for r in batch(cli, [case("t9-xpv", "fx.xccy.pv", {
        "domestic": usd, "foreign_projection": estr, "foreign_discount": eur_disc, "spot": 1.085,
        "trade": trade})]))
    node = implied["nodes"][0]
    print(f"spot date {spot['spot_date']}")
    print(f"1Y forward {fwd['forward']:.8f}  points {fwd['points']:.4f}")
    print(f"1Y node {node['value_date']}  basis {node['basis_bp']:.4f} bp")
    print(f"EUR xccy discount 2Y {boot['pillars'][1]['discount_factor']:.10f}  repriced {error < 1e-13}")
    print(f"xccy PV {xpv['pv']:.2f} USD  EUR leg {xpv['foreign_leg']:.2f} EUR")
    print(f"GK price {gk['price']:.4f} USD  forward {gk['forward']:.8f}")
    print(f"GK delta {gk['delta']:.4f} EUR  vega {gk['vega']:.4f}")
    print("deltas " + "  ".join(f"{k} {deltas['deltas'][k]:.8f}" for k in ("SPOT", "FORWARD", "SPOT_PA", "FORWARD_PA")))
    print(f"EURUSD ATM {eu['atm_strike']:.8f}  25C {eu['call_strike']:.8f}  25P {eu['put_strike']:.8f}")
    print(f"USDJPY ATM {jp['atm_strike']:.6f}  25C {jp['call_strike']:.6f}  25P {jp['put_strike']:.6f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
