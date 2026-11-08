"""Stage E spec B: goldens pinning the cross-language SPEC_QUESTIONS rulings E-B34 to E-B40 (suite rulings_e_b)."""
import json
from pathlib import Path

import mpmath as mp

from qf_oracle.common import note
from gen_stage_e_b import A, E, S, f, write
import gen_stage_e_b as G
from gen_stage_e_b_e4 import opt_mp

mp.mp.dps = 50
GOLD = Path(__file__).resolve().parents[2] / "datasets" / "golden" / "stage_e_b"


def case(suite, op, pick):
    """First ok case of `op` in `suite` for which pick(case) holds. Selected by content, never by id: ids move when cases are inserted."""
    for c in json.loads((GOLD / f"{suite}.json").read_text(encoding="utf-8"))["cases"]:
        if c["operation"] == op and c["expected"]["status"] == "ok" and pick(c):
            return c
    raise KeyError((suite, op))


def neg_var_input():
    return {"as_of": "2026-11-06", "maturity": "2027-11-06", "spot": 100.0, "rate": .2, "dividend_yield": 0.0, "put_strikes": [100.0], "call_strikes": [130.0],
            "vols": [{"strike": 100.0, "vol": .01}, {"strike": 130.0, "vol": .01}], "extension_step": 5.0, "variance_strike": .04, "variance_notional": 1e6}


def rulings_e_b():
    s = S("rulings_e_b", "stage-e-rulings-b.md")
    # E-B34: vol.vix.index checks the bracket before either term's own checks
    vix = json.loads((GOLD / "vix_e.json").read_text(encoding="utf-8"))["cases"]
    terms = [c["inputs"] for c in vix if c["operation"] == "vol.vix.term_variance" and c["expected"]["status"] == "ok" and "hand" not in c["tags"]]
    near, nxt = terms[0], terms[1]
    badnear = {**near, "strip": [near["strip"][0] | {"put_bid": -0.05}] + near["strip"][1:]}
    s.add("vol.vix.index", {"near": nxt, "next": badnear}, error="E_INPUT", cls=E, tags=["ruling", "E-B34", "order"],
          description="bracket broken (near after next) and a negative quote in a term: the bracket E_INPUT comes first")
    s.add("vol.vix.index", {"near": badnear, "next": nxt}, error="E_DOMAIN", cls=E, tags=["ruling", "E-B34", "order"],
          description="bracket fine, negative quote in the near term: E_DOMAIN from the term checks")
    # E-B36: replicated variance below zero
    inp = neg_var_input()
    real = mp.sqrt
    G.mp.sqrt = lambda x: real(x) if (not isinstance(x, mp.mpf)) or x >= 0 else mp.mpf(-1)  # noqa: E731
    try:
        assert G.varswap(inp)[0]["fair_variance"] < -0.04
    finally:
        G.mp.sqrt = real
    s.add("vol.varswap.fair_strike", inp, error="E_DOMAIN", cls=E, tags=["ruling", "E-B36"], description="coarse strip with large carry: replicated variance -0.0428, below 0")
    # E-B37: ZC strike ratio
    s.add("infl.cap.zc_price", {"model": "BLACK_76", "type": "CAP", "forward_index_ratio": 1.1268, "years": 5.5, "strike": -1.5, "discount_factor": .83, "vol": .03, "notional": 1e7},
          error="E_DOMAIN", cls=E, tags=["ruling", "E-B37"], description="1 + K <= 0: no strike ratio")
    K, T, FI, D, v = -0.01, 5.0, 1.1268, .8305, .028
    Kr = (1 + mp.mpf(K)) ** T
    s.add("infl.cap.zc_price", {"model": "BLACK_76", "type": "FLOOR", "forward_index_ratio": FI, "years": T, "strike": K, "discount_factor": D, "vol": v, "notional": 1e7},
          {"price": f(1e7 * opt_mp("BLACK_76", False, FI, Kr, v, T, D)), "strike_ratio": f(Kr)}, cls=A, verified=["mpmath-50"], tags=["ruling", "E-B37"],
          output_classes={"strike_ratio": A}, limit={"absolute": 1e-5, "relative": 1e-10, "reason": "1e-12 per unit notional"},
          description="negative ZC strike with 1 + K > 0 is priced under Black (the strike rule is YoY only)")
    # E-B38: vols and CTD inputs
    bf = {"type": "CALL", "futures_price": 111.25, "strike": 110.0, "expiry_years": .1, "discount_factor": .9962, "contract_size": 1e5}
    s.add("rates.bondfut.option_price", {**bf, "vol": -.01}, error="E_DOMAIN", cls=E, tags=["ruling", "E-B38"], description="negative vol")
    intr = .9962 * (111.25 - 110.0)
    s.add("rates.bondfut.option_price", {**bf, "vol": 0.0}, {"price": intr, "contract_value": intr * 1e5 / 100}, cls=A, verified=["hand"], tags=["ruling", "E-B38"],
          limit={"absolute": 1e-9, "relative": 1e-10, "reason": "1e-9 per 100 face"}, description="zero vol: discounted intrinsic")
    iv = case("ratesvol_e", "rates.bondfut.implied_vol", lambda c: True)["inputs"]
    assert "premium" in iv and "ctd_yield" in iv
    s.add("rates.bondfut.implied_vol", {**iv, "ctd_yield": 0.0}, error="E_DOMAIN", cls=E, tags=["ruling", "E-B38"], description="ctd_yield must be above 0")
    s.add("rates.bondfut.implied_vol", {**iv, "ctd_modified_duration": -1.0}, error="E_DOMAIN", cls=E, tags=["ruling", "E-B38"], description="ctd_modified_duration must be above 0")
    per = [{"accrual": 1.0, "discount_factor": .96, "yoy_forward": .0285, "expiry_years": .75, "vol": 0.0}, {"accrual": 1.0, "discount_factor": .93, "yoy_forward": .0262, "expiry_years": 1.75, "vol": 0.0}]
    cpl = [1e7 * p["discount_factor"] * max(p["yoy_forward"] - .027, 0) for p in per]
    s.add("infl.cap.yoy_price", {"model": "BLACK_76", "type": "CAP", "strike": .027, "notional": 1e7, "periods": per}, {"caplets": cpl, "price": sum(cpl)}, cls=A, verified=["hand"],
          tags=["ruling", "E-B38"], limit={"absolute": 1e-5, "relative": 1e-10, "reason": "1e-12 per unit notional"}, description="zero vol: discounted intrinsic per caplet")
    # E-B39: implied correlation index vol
    s.add("risk.corr.implied", {"weights": [.5, .5], "vols": [.2, .3], "index_vol": 0.0}, error="E_DOMAIN", cls=E, tags=["ruling", "E-B39"], description="index_vol must be above 0")
    # E-B40: smaller readings all languages share
    s.add("credit.copula.joint_default", {"copula": "GAUSSIAN", "default_probabilities": [.02, .03, .04], "correlation": .3}, error="E_INPUT", cls=E, tags=["ruling", "E-B40"],
          description="exactly two default probabilities")
    g = case("creditopt_e", "credit.copula.joint_default", lambda c: c["inputs"]["copula"] == "GAUSSIAN" and c["inputs"]["correlation"] == .3)
    s.add("credit.copula.joint_default", {**g["inputs"], "degrees_of_freedom": 4}, g["expected"]["outputs"], cls=g["tolerance_class"], verified=["mpmath-50 quad"], tags=["ruling", "E-B40"],
          limit=g["tolerance_limit"], description="degrees_of_freedom is ignored for GAUSSIAN")
    s.add("credit.lhp.loss_cdf", {"default_probability": .05, "correlation": .3, "recovery": .4, "losses": []}, error="E_INPUT", cls=E, tags=["ruling", "E-B40"], description="empty losses")
    st = case("ratesvol_e", "rates.cap.strip", lambda c: c["inputs"]["model"] == "BLACK_76" and len(c["inputs"]["flat_vols"]) == 5 and "non-annual" not in c["tags"])["inputs"]
    assert st["cap_tenors_months"] == [12, 24, 36, 48, 60]
    s.add("rates.cap.strip", {**st, "flat_vols": [.24, 0.0, .228, .222, .215], "start_months": 0}, error="E_DOMAIN", cls=E, tags=["ruling", "E-B40", "order"],
          description="flat vol 0 and start_months 0: the strip's own checks (E_DOMAIN) come before D7's start_months (E_INPUT)")
    note("rulings_e_b: cross-language SPEC_QUESTIONS rulings E-B34 to E-B40")
    write(s)


if __name__ == "__main__":
    rulings_e_b()
