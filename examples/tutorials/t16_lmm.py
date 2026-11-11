"""Tutorial 16: LMM caplets from an abcd volatility, and a Rebonato swaption.

  uv run --project python python examples/tutorials/t16_lmm.py         # Python
  python examples/tutorials/t16_lmm.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-16-lmm.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines. Inputs are
synthetic and match golden cases lmmcap_g-0001, lmmcap_g-0003, lmmswn_g-0003 and lmmswn_g-0015.
"""
import json
import sys

from qf import runner

CURVE = {"times": [0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795,
                   10.005479452054795, 15.01095890410959, 20.013698630136986, 30.019178082191782],
         "discount_factors": [0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332]}
HUMP = {"a": -0.06, "b": 0.17, "c": 0.54, "d": 0.17}
SEMI = [0.5 * k for k in range(1, 11)]  # fixings 0.5 .. 4.5, last payment 5.0


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
    cap_in = {"curve": CURVE, "abcd": HUMP, "period_times": SEMI, "strike": 0.03, "notional": 1_000_000.0}
    swn_in = {"curve": CURVE, "abcd": HUMP, "expiry_years": 5.0, "payment_times": [6.0, 7.0, 8.0, 9.0, 10.0],
              "fixed_rate": 0.035, "side": "PAY", "notional": 1_000_000.0}
    cap, floor, s0, s5 = batch(cli, [
        case("t16-cap", "rates.lmm.capfloor", {**cap_in, "cap_floor": "CAP"}),
        case("t16-floor", "rates.lmm.capfloor", {**cap_in, "cap_floor": "FLOOR"}),
        case("t16-swn0", "rates.lmm.swaption_rebonato", {**swn_in, "correlation_beta": 0.0}),
        case("t16-swn5", "rates.lmm.swaption_rebonato", {**swn_in, "correlation_beta": 0.5})])

    print(f"cap price   {cap['price']:.2f}")
    print(f"floor price {floor['price']:.2f}")
    print("caplet Black vols " + " ".join(f"{v:.4f}" for v in cap["black_vols"][:3]))
    print(f"first caplet forward {cap['forward_rates'][0]:.6f}  price {cap['caplet_prices'][0]:.2f}")
    print(f"5y5y swap rate {s0['swap_rate']:.6f}  annuity {s0['annuity']:.6f}")
    print(f"5y5y payer, beta 0.0: vol {s0['black_vol']:.4f}  price {s0['price']:.2f}")
    print(f"5y5y payer, beta 0.5: vol {s5['black_vol']:.4f}  price {s5['price']:.2f}")


if __name__ == "__main__":
    main(sys.argv[1:])
