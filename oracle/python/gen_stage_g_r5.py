"""R5 audit fixes M4, M5, M6: cases appended to existing stage G suites (tag `r5`), idempotent: earlier `r5` cases are
removed and re-added, so the original case ids never move.

M4 (ruling G-31): one E_LIMIT case per operation family, including the combined grid-work bound.
M5 (ruling G-32): CIR bond options with a large noncentrality (sigma = 0.005) and with rbar < 0 (CDF argument <= 0).
M6 (ruling G-33): G2++ with a = 1e-4 and with a = b.

    cd oracle/python && uv run python -W ignore gen_stage_g_r5.py
"""
import json
from pathlib import Path

import QuantLib as ql

from qf_oracle.common import note
from gen_stage_g_w1 import CURVE, opt_value, ql_opt, ql_bonds, close, g2_zcb, g2_opt, ql_g2

HERE = Path(__file__).resolve().parent
GOLD = HERE.parent.parent / "datasets" / "golden" / "stage_g"
G = "oracle/python/gen_stage_g_r5.py"
LIM = {"absolute": 1e-6, "relative": 1e-9, "reason": "1e-9 relative"}


def load(suite):
    d = json.loads((GOLD / f"{suite}.json").read_text(encoding="utf-8"))
    d["cases"] = [c for c in d["cases"] if "r5" not in c["tags"]]
    return d


def add(d, op, inputs, outputs=None, error=None, cls="simple_analytic", verified=(), tags=(), limit=None, description=""):
    cid = f"{d['suite']}-{len(d['cases']) + 1:04d}"
    exp = {"status": "error", "error_code": error} if error else {"status": "ok", "outputs": outputs}
    c = {"case_id": cid, "operation": op, "inputs": inputs, "expected": exp, "tolerance_class": cls, "verified_by": list(verified),
         "tags": list(tags) + ["r5", "synthetic"], "description": description}
    if limit:
        c["tolerance_limit"] = limit
    d["cases"].append(c)
    return cid


def save(d):
    (GOLD / f"{d['suite']}.json").write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8", newline="\n")
    note(f"suite {d['suite']}: {len(d['cases'])} cases")


def lim(d, op, inp, desc):
    add(d, op, inp, error="E_LIMIT", cls="date_and_convention", tags=["invalid", "limit"], description=desc)


def main():
    reg = json.loads((HERE.parent / "outside_register_g.json").read_text(encoding="utf-8"))
    big = [0.01 * (k + 1) for k in range(10001)]
    hw = dict(mean_reversion=0.05, sigma=0.01, curve=CURVE)
    longcurve = {"times": big, "discount_factors": [1.0 - 1e-6 * (k + 1) for k in range(10001)]}

    # ---- shortrate_g: M5 + M4
    d = load("shortrate_g")
    n_out = 0
    cir = dict(model="CIR", mean_reversion=0.25, long_term_mean=0.04, short_rate=0.03)
    m5 = [dict(cir, sigma=0.005, option_type="CALL", strike=0.95, expiry_years=1.0, maturity_years=2.0, notional=1e6),
          dict(cir, sigma=0.005, option_type="PUT", strike=0.95, expiry_years=1.0, maturity_years=2.0, notional=1e6),
          dict(cir, sigma=0.08, option_type="CALL", strike=0.999, expiry_years=1.0, maturity_years=5.0, notional=1e6)]
    for inp in m5:
        out = opt_value(inp)
        q, qb = ql_opt(inp), ql_bonds(inp)
        ok = abs(q - out["price"]) <= 1e-6 + 1e-9 * abs(out["price"]) and close(qb[0], out["bond_price_expiry"]) and close(qb[1], out["bond_price_maturity"])
        n_out += ok
        note(f"  M5 {inp['option_type']} sigma={inp['sigma']} K={inp['strike']}: {out['price']} QL {q} {'ok' if ok else 'DIFF'}")
        add(d, "rates.shortrate.zcb_option", inp, out, cls="root_finding", verified=["mpmath-50", "put-call-parity"] + (["quantlib-1.44"] if ok else []),
            tags=["shortrate", "cir", "m5"], limit=LIM,
            description=f"CIR {inp['option_type']} sigma={inp['sigma']} K={inp['strike']}: " + ("large noncentrality (log-weight start at the mode)" if inp["sigma"] < 0.01 else "strike above A(T,S): rbar < 0, CDF 0"))
    lim(d, "rates.shortrate.zcb", dict(hw, model="HULL_WHITE", curve=longcurve, t_years=0.0, maturity_years=1.0), "10,001 curve pillars")
    save(d)
    reg["shortrate_r5"] = {"counted": n_out, "total": len(m5) + 1, "rule": "QuantLib CoxIngersollRoss discountBondOption and discountBond (R5 M5)"}

    # ---- g2pp_g: M6
    d = load("g2pp_g")
    n6 = 0
    pars = [dict(a=1e-4, sigma=0.01, b=0.05, eta=0.008, rho=-0.75), dict(a=0.1, sigma=0.01, b=0.1, eta=0.008, rho=0.4)]
    for pr in pars:
        inp = dict(pr, curve=CURVE, t_years=1.5, maturity_years=7.5, x=0.004, y=-0.002)
        out = g2_zcb(inp)
        ok = close(ql_g2(inp).discountBond(1.5, 7.5, ql.Array([0.004, -0.002])), out["discount_factor"])
        n6 += ok
        add(d, "rates.g2pp.zcb", inp, out, verified=["mpmath-50"] + (["quantlib-1.44"] if ok else []), tags=["g2pp", "m6"],
            description=f"G2++ zcb a={pr['a']} b={pr['b']}" + (" (small a: series / expm1)" if pr["a"] < 1e-3 else " (a = b)"))
        for typ in ("CALL", "PUT"):
            inp = dict(pr, curve=CURVE, option_type=typ, strike=0.86, expiry_years=1.0, maturity_years=5.0, notional=1e6)
            out = g2_opt(inp)
            q = 1e6 * ql_g2(inp).discountBondOption(ql.Option.Call if typ == "CALL" else ql.Option.Put, 0.86, 1.0, 5.0)
            ok = abs(q - out["price"]) <= 1e-6 + 1e-9 * abs(out["price"])
            n6 += ok
            note(f"  M6 a={pr['a']} {typ}: {out['price']} QL {q} {'ok' if ok else 'DIFF'}")
            add(d, "rates.g2pp.zcb_option", inp, out, verified=["mpmath-50"] + (["quantlib-1.44"] if ok else []), tags=["g2pp", "m6", typ.lower()],
                limit=LIM, description=f"G2++ {typ} a={pr['a']} b={pr['b']}")
    save(d)
    reg["g2pp_r5"] = {"counted": n6, "total": 6, "rule": "QuantLib G2 discountBond and discountBondOption (R5 M6)"}

    # ---- E_LIMIT in the other families (M4)
    e = dict(hw, notional=1.0, fixed_rate=0.03)
    d = load("swaption_g")
    lim(d, "rates.shortrate.swaption", dict(e, expiry_years=0.005, payment_times=big, swaption_type="PAYER"), "10,001 payment times")
    save(d)
    d = load("exposure_g")
    lim(d, "xva.exposure.swap_ee_hw", dict(e, start_years=0.0, payment_times=[1.0, 2.0], side="PAY", exposure_times=big), "10,001 exposure times")
    save(d)
    berm = dict(hw, notional=1.0, start_years=1.0, payment_times=[2.0, 3.0, 4.0, 5.0, 6.0], fixed_rate=0.03, swaption_type="PAYER",
                exercise_times=[1.0, 2.0, 3.0, 4.0, 5.0])
    d = load("bermudan_g")
    lim(d, "rates.shortrate.bermudan_swaption", dict(berm, grid={"nx": 10001, "steps_per_year": 100000, "width": 6.0}),
        "combined work nx x total steps = 10,001 x 500,000 > 5e8 (each value within its own limit)")
    lim(d, "rates.shortrate.bermudan_swaption", dict(berm, grid={"nx": 10003, "steps_per_year": 10, "width": 6.0}), "nx = 10,003 > 10,001")
    save(d)
    d = load("callable_g")
    lim(d, "rates.shortrate.callable_bond", dict(hw, notional=100.0, payment_times=[float(k) for k in range(1, 31)], coupon_rate=0.045,
                                                 call_times=[], call_price=1.0, grid={"nx": 5001, "steps_per_year": 5000, "width": 6.0}),
        "combined work 5,001 x 150,000 > 5e8")
    save(d)
    d = load("mcgreeks_g")
    lim(d, "risk.mc.greeks", dict(payoff="CALL", method="PATHWISE", spot=100.0, strike=100.0, expiry_years=1.0, rate=0.03, dividend_yield=0.0,
                                  vol=0.2, paths=10_000_001, seed=1), "paths 10,000,001")
    save(d)
    d = load("barrier_g")
    lim(d, "exotic.barrier.price", dict(spot=100.0, strike=100.0, expiry_years=1.0, rate=0.05, dividend_yield=0.02, vol=0.25, rebate=0.0,
                                        barrier=90.0, barrier_type="DOWN_OUT", option_type="CALL", monitoring="DISCRETE",
                                        monitoring_per_year=1_000_001), "monitoring_per_year 1,000,001")
    save(d)
    (HERE.parent / "outside_register_g.json").write_text(json.dumps(reg, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
