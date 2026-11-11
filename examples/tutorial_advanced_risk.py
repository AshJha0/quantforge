#!/usr/bin/env python3
"""Tutorial 15 through any language's CLI: AAD ladder, Monte Carlo Greeks, model reserve, FRTB, SIMM.

  python examples/tutorial_advanced_risk.py rust/target/release/quantforge
  python examples/tutorial_advanced_risk.py java -jar java25/target/quantforge-cli.jar

Standard library only. It sends the cases of docs/getting-started/tutorial-15-advanced-risk.md to
`quantforge batch` and prints the same lines as the Python section of the tutorial.
"""
import json
import shutil
import subprocess
import sys

CURVE = {"times": [0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795,
                   10.005479452054795, 15.01095890410959, 20.013698630136986, 30.019178082191782],
         "discount_factors": [0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332]}
LADDER = {"mean_reversion": 0.05, "sigma": 0.01, "curve": CURVE, "notional": 1_000_000.0, "start_years": 1.0,
          "payment_times": [2.0, 3.0, 4.0, 5.0, 6.0], "grid": {"nx": 101, "steps_per_year": 50, "width": 6.0},
          "fixed_rate": 0.039462, "swaption_type": "PAYER", "exercise_times": [1.0, 2.0, 3.0, 4.0, 5.0]}
OPTION = {"spot": 100.0, "strike": 100.0, "expiry_years": 1.0, "rate": 0.03, "dividend_yield": 0.01, "vol": 0.2,
          "paths": 10_000, "seed": "20261109", "payoff": "CALL"}
RESERVE = {"prices": {"HESTON": 4.1832, "LOCAL_VOL": 4.6021, "SLV": 4.3907}, "reference_model": "SLV"}
VEGA = {"risk_class": "GIRR", "sensitivities": [
    {"bucket": "EUR", "option_maturity": 1.0, "underlying_maturity": 5.0, "vega": 1_000_000.0},
    {"bucket": "EUR", "option_maturity": 5.0, "underlying_maturity": 10.0, "vega": -600_000.0},
    {"bucket": "USD", "option_maturity": 1.0, "underlying_maturity": 5.0, "vega": 800_000.0}]}
CURVATURE = {"risk_class": "GIRR", "factors": [{"bucket": "EUR", "cvr_up": 500_000.0, "cvr_down": 300_000.0},
                                               {"bucket": "USD", "cvr_up": -200_000.0, "cvr_down": 400_000.0}]}
RHO = [[1.0, 0.659754, 0.535887, 0.407091, 0.33066, 0.237818],
       [0.659754, 1.0, 0.812252, 0.617034, 0.501187, 0.360465],
       [0.535887, 0.812252, 1.0, 0.759658, 0.617034, 0.443785],
       [0.407091, 0.617034, 0.759658, 1.0, 0.812252, 0.584191],
       [0.33066, 0.501187, 0.617034, 0.812252, 1.0, 0.719223],
       [0.237818, 0.360465, 0.443785, 0.584191, 0.719223, 1.0]]
SIMM = {"sensitivities": [1000.0, -500.0, 2500.0, 4000.0, -1200.0, 300.0],
        "risk_weights": [109.0, 105.0, 90.0, 71.0, 66.0, 66.0], "correlations": RHO,
        "concentration_threshold": 1e9}
METHODS = ("PATHWISE", "LIKELIHOOD_RATIO")


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
    lad, g1, g2, r, v, c, m = batch(cli, [
        case("t15-ladder", "rates.shortrate.bermudan_ladder", LADDER),
        *[case(f"t15-mc-{k}", "risk.mc.greeks", {**OPTION, "method": k}) for k in METHODS],
        case("t15-reserve", "risk.model_reserve.dispersion", RESERVE),
        case("t15-vega", "risk.frtb.vega", VEGA),
        case("t15-curv", "risk.frtb.curvature", CURVATURE),
        case("t15-simm", "xva.simm.ir_delta", SIMM)])
    print(f"bermudan price {lad['price']:.4f}")
    print("dV/dP " + " ".join(f"{x:.1f}" for x in lad["d_price_d_discount_factors"][:6]))
    print(f"dV/da {lad['d_price_d_mean_reversion']:.1f}  dV/dsigma {lad['d_price_d_sigma']:.1f}")
    for method, g in zip(METHODS, (g1, g2)):
        print(f"{method:<16} delta {g['delta']:.6f} +- {g['delta_se']:.6f}  vega {g['vega']:.4f} +- {g['vega_se']:.4f}")
    print(f"reserve {r['reserve']:.4f} ({r['relative_reserve']:.4%}) worst {r['worst_model']} range {r['range']:.4f}")
    print(f"FRTB vega      {v['capital']:.2f} ({v['binding_scenario']}); medium K_EUR {v['scenarios']['medium']['buckets'][0]['k']:.2f}")
    picks = ", ".join(f"{b['bucket']} {b['selected']}" for b in c["scenarios"]["high"]["buckets"])
    print(f"FRTB curvature {c['capital']:.2f} ({c['binding_scenario']}); {picks}")
    print(f"SIMM IR delta margin {m['margin']:.2f} (CR {m['concentration_factor']:.1f})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
