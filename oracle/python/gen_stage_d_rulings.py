"""Stage D golden cases pinning rulings D31 to D46: points where the language builds chose differently, or where a
choice was not pinned. Inputs are taken from existing stage D goldens and changed in one place each."""
import copy
import json
import math
from datetime import date

from qf_oracle import common
from qf_oracle.common import note
import gen_stage_d as D
from gen_stage_d import E, A, I, S, write

G = common.ROOT / "datasets" / "golden" / "stage_d"


def case(cid):
    suite = cid.rsplit("-", 1)[0]
    for c in json.loads((G / f"{suite}.json").read_text(encoding="utf-8"))["cases"]:
        if c["case_id"] == cid:
            return copy.deepcopy(c["inputs"])
    raise KeyError(cid)


def main():
    D.estr()
    s = S("rulings_d", "stage-d-rulings.md")
    tag = lambda r: ["ruling", r]  # noqa: E731
    # D31: empty steps is a flat curve.
    i = case("steps_d-0001")
    i["steps"] = []
    sc = D.StepCurve(D.AS_OF, i["base_rate"], [], [(date.fromisoformat(j["date"]), j["factor"]) for j in i["jumps"]])
    s.add("rates.ois.step_curve", i, {"discount_factors": [sc.df(date.fromisoformat(d)) for d in i["dates"]], "overnight_forwards": [i["base_rate"]] * len(i["dates"])},
          cls=A, verified=["exact-rational"], tags=tag("D31"))
    i = case("steps_d-0001")
    i["dates"] = []
    s.add("rates.ois.step_curve", i, error="E_INPUT", cls=E, tags=tag("D31"), description="empty dates")
    # D32: implied financing spread searched on [-0.5, 0.5].
    i = case("equity_d-0007")
    i["futures_price"] = i["futures_price"] * 0.80
    s.add("eq.futures.basis", i, error="E_NOT_BRACKETED", cls=E, tags=tag("D32"), description="needs a spread far above 0.5")
    # D33: wam above 1200 is E_INPUT, not E_LIMIT.
    i = case("mbs_d-0001")
    i["pool"]["wam"] = 1201
    s.add("mbs.cashflows", i, error="E_INPUT", cls=E, tags=tag("D33"))
    # D34: 1 + y/12 <= 0 in mbs.price.
    i = case("mbs_d-0004")
    i["yield"] = -12.5
    s.add("mbs.price", i, error="E_DOMAIN", cls=E, tags=tag("D34"))
    # D35: conversion factor with maturity before the delivery month.
    i = case("repo_d-0015")
    i["bond"]["maturity"] = "2026-11-15"
    s.add("bond.futures.conversion_factor", i, error="E_DATE_ORDER", cls=E, tags=tag("D35"))
    # D36: CDS curves must be as of the trade date.
    i = case("credit_d-0004")
    i["hazard"]["as_of"] = "2026-11-05"
    s.add("credit.cds.price", i, error="E_INPUT", cls=E, tags=tag("D36"), description="hazard as_of differs from trade_date")
    i = case("credit_d-0004")
    i["discount"]["as_of"] = "2026-11-05"
    s.add("credit.cds.price", i, error="E_INPUT", cls=E, tags=tag("D36"), description="discount as_of differs from trade_date")
    # D37: weights: negative or summing to zero is E_DOMAIN.
    i = case("credit_d-0009")
    for n in i["names"]:
        n["weight"] = 0.0
    s.add("credit.index.intrinsic", i, error="E_DOMAIN", cls=E, tags=tag("D37"), description="weights sum to zero")
    i = case("credit_d-0011")
    i["constituents"][1]["weight"] = -1.0
    s.add("credit.curve.composite", i, error="E_DOMAIN", cls=E, tags=tag("D37"))
    i = case("bondfit_d-0001")
    i["weights"] = [1, 1, -1, 1, 1, 1, 1]
    s.add("bond.fit.nelson_siegel", i, error="E_DOMAIN", cls=E, tags=tag("D37"))
    i = case("bondfit_d-0001")
    i["weights"] = [1, 1, 1]
    s.add("bond.fit.nelson_siegel", i, error="E_INPUT", cls=E, tags=tag("D37"), description="weights of the wrong length")
    # D38: robust fit that cannot fix three betas.
    i = case("fits_d-0009")
    i["maturities"] = [5.0] * len(i["maturities"])
    s.add("calib.curve.robust", i, error="E_SINGULAR", cls=E, tags=tag("D38"), description="one maturity repeated: rank 1")
    # D39: cross-currency start before as_of.
    i = case("xccy_d-0001")
    i["start"] = "2026-11-05"
    s.add("fx.xccy.bootstrap", i, error="E_OUT_OF_RANGE", cls=E, tags=tag("D39"))
    # D40: tenor_months below 1.
    i = case("capswaption_d-0001")
    i["trade"]["tenor_months"] = 0
    s.add("rates.cap.price", i, error="E_INPUT", cls=E, tags=tag("D40"))
    i = case("capswaption_d-0010")
    i["trade"]["tenor_months"] = 0
    s.add("rates.swaption.price", i, error="E_INPUT", cls=E, tags=tag("D40"))
    # D41: TRS end on or before start.
    i = case("trs_d-0001")
    i["trade"]["end"] = i["trade"]["start"]
    s.add("eq.trs.pv", i, error="E_DATE_ORDER", cls=E, tags=tag("D41"))
    # D42: two forwards on one date in CSA discounting.
    i = case("csa_d-0004")
    if i["fx"] is not None:
        i["fx"]["forwards"].append(dict(i["fx"]["forwards"][0]))
        s.add("rates.csa.discount", i, error="E_INPUT", cls=E, tags=tag("D42"))
    write(s)
    note(f"rulings_d: {len(s.cases)} cases")
    second()



def jc_curve(j):
    from qf_oracle.rates import Curve
    return Curve(date.fromisoformat(j["as_of"]), [date.fromisoformat(p["date"]) for p in j["pillars"]], [p["discount_factor"] for p in j["pillars"]], j["interpolation"])


def second():
    """Rulings D47 to D60: the second pass over the builds' open questions."""
    from qf_oracle.dates import yf
    from qf_oracle.rates import add_bd, add_months, adjust, ois_legs, ois_periods, schedule
    import gen_stage_d_vol as V
    s = S("rulings2_d", "stage-d-rulings.md")
    tag = lambda r: ["ruling", r]  # noqa: E731
    # D47: ESTR in rates.basis.ois_spread (any overnight convention).
    i = case("csa_d-0008")
    i["convention"] = "ESTR"
    d, pa, pb = jc_curve(i["discount"]), jc_curve(i["projection_a"]), jc_curve(i["projection_b"])
    p = ois_periods("ESTR", d.as_of, i["tenor"])
    a, fa = ois_legs("ESTR", p, d)
    fb = sum((pb.df(x) / pb.df(y) - 1) * d.df(z) for x, y, z in p)
    fa = sum((pa.df(x) / pa.df(y) - 1) * d.df(z) for x, y, z in p)
    s.add("rates.basis.ois_spread", i, {"spread": (fa - fb) / a}, cls=I, verified=["independent-replay"], tags=tag("D47"), limit={"absolute": 1e-10, "relative": 0.0, "reason": "curve tolerance"})
    # D48: curve checks before the shared as_of check.
    i = case("csa_d-0008")
    i["projection_b"]["as_of"] = "2026-11-05"
    i["projection_b"]["pillars"][0]["discount_factor"] = -0.5
    s.add("rates.basis.ois_spread", i, error="E_DOMAIN", cls=E, tags=tag("D48"))
    # D49: ois_quotes and term_quotes are quote lists: 100 at most.
    i = case("csa_d-0011")
    i["ois_quotes"] = [{"tenor": f"{k}W", "rate": .04} for k in range(1, 102)]
    s.add("rates.curve.joint_bootstrap", i, error="E_LIMIT", cls=E, tags=tag("D49"))
    # D50: a lookback reaching before the calendar range.
    i = case("compound_d-0002")
    i["shift_days"] = 10000
    s.add("rates.ois.compound_dated", i, error="E_DATE_RANGE", cls=E, tags=tag("D50"))
    # D51: fit_steps quotes out of tenor order break the pillar rule.
    i = case("steps_d-0007")
    i["quotes"][0], i["quotes"][1] = i["quotes"][1], i["quotes"][0]
    s.add("rates.ois.fit_steps", i, error="E_INPUT", cls=E, tags=tag("D51"))
    # D52: hazard curve checks.
    i = case("credit_d-0004")
    i["hazard"]["pillars"][0]["survival"] = 1.2
    s.add("credit.cds.price", i, error="E_DOMAIN", cls=E, tags=tag("D52"), description="survival above 1")
    i = case("credit_d-0004")
    i["hazard"]["pillars"][0], i["hazard"]["pillars"][1] = i["hazard"]["pillars"][1], i["hazard"]["pillars"][0]
    s.add("credit.cds.price", i, error="E_INPUT", cls=E, tags=tag("D52"), description="pillars not increasing")
    i = case("credit_d-0004")
    i["trade"]["maturity"] = "2026-09-20"
    s.add("credit.cds.price", i, error="E_INPUT", cls=E, tags=tag("D52"), description="maturity before trade date")
    # D53: equity details.
    i = case("equity_d-0001")
    i["futures"] = []
    s.add("eq.dividend.implied", i, error="E_INPUT", cls=E, tags=tag("D53"))
    i = case("equity_d-0004")
    i["expiry"] = "2026-11-06"
    s.add("eq.borrow.implied", i, error="E_DATE_ORDER", cls=E, tags=tag("D53"))
    i = case("index_d-0005")
    i["divisor"] = 0.0
    i["new_constituents"] = [i["new_constituents"][0], i["new_constituents"][0]]
    s.add("eq.index.rebalance", i, error="E_INPUT", cls=E, tags=tag("D53"), description="duplicate id checked before divisor")
    # D54: seasonality is a required key (may be null); years at most 100.
    i = case("inflation_d-0001")
    del i["seasonality"]
    s.add("infl.curve.cpi", i, error="E_SCHEMA", cls=E, tags=tag("D54"))
    i = case("commodity_d-0001")
    del i["seasonality"]
    s.add("cmdty.curve.forward", i, error="E_SCHEMA", cls=E, tags=tag("D54"))
    i = case("inflation_d-0001")
    i["quotes"].append({"years": 101, "rate": .025})
    s.add("infl.curve.cpi", i, error="E_INPUT", cls=E, tags=tag("D54"))
    # D55: BACHELIER caps take any strike.
    i = case("capswaption_d-0003")
    i["trade"]["strike"] = -0.005
    disc, pc = jc_curve(i["discount"]), jc_curve(i["projection"])
    spot = add_bd("USGS", disc.as_of, 2)
    st = adjust("USGS", add_months(spot, i["trade"]["start_months"]))
    ds = schedule("USGS", st, add_months(st, i["trade"]["tenor_months"]), 3)
    N, K, v = i["trade"]["notional"], i["trade"]["strike"], i["vol"]
    caps = []
    for a_, e_ in zip(ds, ds[1:]):
        al = float(yf("ACT_360", a_, e_))
        caps.append(N * al * disc.df(e_) * V.opt("BACHELIER", True, (pc.df(a_) / pc.df(e_) - 1) / al, K, v, (a_ - disc.as_of).days / 365))
    s.add("rates.cap.price", i, {"price": sum(caps), "caplets": caps}, cls=I, verified=["independent-replay", "quantlib-1.44"], tags=tag("D55"), limit={"absolute": 1e-9 * N, "relative": 1e-9, "reason": "curve tolerance on notional"})
    # D56: model enum and vol type.
    i = case("capswaption_d-0001")
    i["model"] = "BLACK_SCHOLES"
    s.add("rates.cap.price", i, error="E_SCHEMA", cls=E, tags=tag("D56"))
    i = case("capswaption_d-0001")
    i["vol"] = "0.2"
    s.add("rates.cap.price", i, error="E_SCHEMA", cls=E, tags=tag("D56"))
    # D57: swaption checks: expiry and tenor before vol.
    i = case("capswaption_d-0010")
    i["trade"]["expiry_months"] = 0
    i["vol"] = -0.1
    s.add("rates.swaption.price", i, error="E_INPUT", cls=E, tags=tag("D57"))
    # D58: storage forward price <= 0.
    i = case("commodity_d-0007")
    i["forwards"][1]["price"] = 0.0
    s.add("cmdty.storage.carry", i, error="E_DOMAIN", cls=E, tags=tag("D58"))
    # D59: xccy months at most 1200; pv start before as_of.
    i = case("xccy_d-0001")
    i["quotes"].append({"months": 1203, "spread": -.002})
    s.add("fx.xccy.bootstrap", i, error="E_INPUT", cls=E, tags=tag("D59"))
    i = case("xccy_d-0002")
    i["trade"]["start"] = "2026-11-05"
    s.add("fx.xccy.pv", i, error="E_OUT_OF_RANGE", cls=E, tags=tag("D59"))
    # D61: bond futures basis date and list checks.
    i = case("repo_d-0019")
    i["delivery"] = "2026-11-09"
    s.add("bond.futures.basis", i, error="E_DATE_ORDER", cls=E, tags=tag("D61"), description="delivery on settlement")
    i = case("repo_d-0019")
    i["delivery"] = "2033-09-01"
    s.add("bond.futures.basis", i, error="E_INPUT", cls=E, tags=tag("D61"), description="delivery after a bond's maturity")
    i = case("repo_d-0019")
    i["bonds"] = []
    s.add("bond.futures.basis", i, error="E_INPUT", cls=E, tags=tag("D61"))
    write(s)
    note(f"rulings2_d: {len(s.cases)} cases")


if __name__ == "__main__":
    main()
