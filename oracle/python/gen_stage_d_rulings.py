"""Stage D golden cases pinning rulings D31 to D46: points where the language builds chose differently, or where a
choice was not pinned. Inputs are taken from existing stage D goldens and changed in one place each."""
import copy
import json
import math
from datetime import date

from qf_oracle import common
from qf_oracle.common import note
import gen_stage_d as D
from gen_stage_d import E, A, S, write

G = common.ROOT / "datasets" / "golden" / "stage_d"


def case(cid):
    suite = cid.rsplit("-", 1)[0]
    for c in json.loads((G / f"{suite}.json").read_text(encoding="utf-8"))["cases"]:
        if c["case_id"] == cid:
            return copy.deepcopy(c["inputs"])
    raise KeyError(cid)


def main():
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


if __name__ == "__main__":
    main()
