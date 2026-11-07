import math
"""Checks every golden file against the invariants the specs state, and sweeps day counts by brute force."""
import json
from datetime import date, timedelta

from qf_oracle.common import GOLDEN, note
from qf_oracle.dates import is_business, yf

CONVS = ["ACT_360", "ACT_365F", "ACT_364", "ACT_365_25", "NL_365", "ONE_ONE", "ACT_ACT_ISDA", "ACT_ACT_AFB", "THIRTY_360_BOND",
         "THIRTY_360_US", "THIRTY_E_360", "THIRTY_E_360_ISDA", "THIRTY_E_PLUS_360"]


def sweep():
    n = 0
    ds = [date(2023, 1, 25) + timedelta(i) for i in range(70)] + [date(2024, 1, 25) + timedelta(i) for i in range(70)]
    for c in CONVS:
        for a in ds:
            for b in ds:
                if a > b:
                    continue
                for term in (b, date(2099, 12, 31)):
                    v = yf(c, a, b, termination=term)
                    assert v >= 0 and (a != b or v == 0), (c, a, b, v)
                    n += 1
    note(f"invariants: {n} day-count evaluations, none negative, all equal-date results 0")


def nondecreasing(v):
    return all(a <= b for a, b in zip(v, v[1:]))


def check(c):
    op, i, e = c["operation"], c["inputs"], c["expected"]
    if e["status"] != "ok":
        return
    o = e["outputs"]
    if op == "core.daycount.year_fraction":
        assert o["year_fraction"] >= 0
        assert i["start"] != i["end"] or o["year_fraction"] == 0
    elif op == "core.compounding.discount_factor":
        assert o["discount_factor"] > 0
    elif op == "core.rng.uniforms":
        assert all(0 < u < 1 for u in o["values"])
    elif op == "core.sobol.points":
        assert all(0 < u < 1 for p in o["points"] for u in p) or i["dimensions"] > 0 and all(0 <= u < 1 for p in o["points"] for u in p)
    elif op == "core.calendar.holidays":
        ds = [date.fromisoformat(x) for x in o["dates"]]
        assert ds == sorted(set(ds)) and all(d.year == i["year"] and d.weekday() < 5 for d in ds)
    elif op in ("core.calendar.adjust", "core.calendar.add_tenor", "core.calendar.add_business_days"):
        if i.get("convention") != "UNADJUSTED":
            assert is_business(i["calendar"], date.fromisoformat(o["date"])), c["case_id"]
    elif op == "core.stats.summary":
        assert o["variance"] >= 0 and o["min"] <= o["mean"] <= o["max"]
    elif op == "core.stats.quantile":
        assert nondecreasing(o["values"])
    elif op == "core.stats.covariance":
        assert o["correlation"] is None or abs(o["correlation"]) <= 1
    elif op == "core.stats.ols":
        assert o["r_squared"] is None or 0 <= o["r_squared"] <= 1
    elif op == "core.ts.ewma_variance":
        assert all(v >= 0 for v in o["variance"])
    elif op in ("core.pde.bs_european", "core.cos.european", "core.mc.gbm_european"):
        assert o["price"] >= 0
        assert "stderr" not in o or o["stderr"] > 0
    elif op == "core.interp.evaluate":
        for x, y in zip(i["x"], i["y"]):
            if x in i["at"]:
                assert abs(o["values"][i["at"].index(x)] - y) < 1e-11, c["case_id"]
        if i["method"] == "monotone_pchip":
            for k in range(len(i["x"]) - 1):
                lo, hi = sorted(i["y"][k:k + 2])
                for t, v in zip(i["at"], o["values"]):
                    if i["x"][k] <= t <= i["x"][k + 1]:
                        assert lo - 1e-12 <= v <= hi + 1e-12, c["case_id"]
    elif op == "core.interp.monotone_convex":
        for t, r in zip(i["t"], i["r"]):
            if t in i["at"]:
                assert abs(o["zero_rates"][i["at"].index(t)] - r) < 1e-12, c["case_id"]


def dates_of(p):
    return [date.fromisoformat(x["date"]) for x in p]


def check_b(c, counts):
    """Stage B invariants, from the specs. Counts how many each rule saw."""
    op, i, e = c["operation"], c["inputs"], c["expected"]
    if e["status"] != "ok":
        return
    o = e["outputs"]

    def hit(k):
        counts[k] = counts.get(k, 0) + 1
    if "pillars" in o:
        ds = dates_of(o["pillars"])
        assert ds == sorted(set(ds)) and all(x["discount_factor"] > 0 for x in o["pillars"]), c["case_id"]
        hit("pillars increase, discount factors positive")
    if op == "rates.schedule.generate":
        p = o["periods"]
        for a, b2 in zip(p, p[1:]):
            assert a["end"] == b2["start"]
        for x in p:
            assert x["start"] < x["end"] <= x["payment"]
            assert is_business(i["calendar"], date.fromisoformat(x["end"]))
        hit("periods contiguous, ends on business days")
    if op == "rates.curve.discount":
        assert all(v > 0 for v in o["discount_factors"])
        hit("discount factors positive")
    if "valuation" in o:
        v = o["valuation"]
        assert v["data_version"] == i.get("snapshot_id") and len(v["currency"]) == 3
        hit("valuation carries its snapshot")
    if op == "rates.ois.pv":
        t = i["trade"]
        sg = 1 if t["side"] == "PAY" else -1
        assert abs(o["valuation"]["pv"] - sg * t["notional"] * (o["par_rate"] - t["fixed_rate"]) * o["annuity"]) < 1e-6
        hit("OIS PV equals notional x (par - fixed) x annuity")
    if op == "risk.ois.dv01":
        assert abs(sum(o["key_rate"]) - o["dv01"]) < 1e-3 * abs(o["dv01"]) + 1e-3
        assert (o["dv01"] > 0) == (i["trade"]["side"] == "PAY") or abs(o["dv01"]) < 50
        hit("key rates sum to DV01; payers gain")
    if op == "fx.spot_date":
        assert o["spot_date"] > i["trade_date"]
        hit("spot after trade date")
    if op == "fx.forward.pv":
        assert (o["fx_delta"] > 0) == (i["trade"]["side"] == "BUY")
        hit("FX delta sign follows side")
    if op == "fx.forward.outright":
        assert abs(o["points"] * 1e-4 - (o["forward"] - i["spot"])) < 1e-10
        hit("points equal forward minus spot")
    if op == "hedge.solve":
        A, b0, w = i["a"], i["b"], i["weights"]
        r = [sum(p * q for p, q in zip(row, o["x"])) + v for row, v in zip(A, b0)]
        assert max(abs(p - q) for p, q in zip(r, o["residual"])) < 1e-9
        obj = sum(ww * p * p for ww, p in zip(w, r)) + i["lambda"] * sum(cc * abs(x) for cc, x in zip(i["costs"], o["x"]))
        assert abs(obj - o["objective"]) < 1e-7
        for j, x in enumerate(o["x"]):
            g = 2 * sum(A[k][j] * w[k] * r[k] for k in range(len(A)))
            lc = i["lambda"] * i["costs"][j]
            assert (abs(g + lc * (1 if x > 0 else -1)) < 1e-7) if abs(x) > 1e-12 else abs(g) <= lc + 1e-7, c["case_id"]
        hit("residual, objective and first-order conditions")
    if op == "calib.fit":
        assert o["objective"] >= 0
        hit("objective not negative")
    if op == "usecase.fx_hedge":
        assert abs(o["hedge_spot_base"] + o["fx_delta"]) < 1e-9 and o["hedge_cost"] >= 0
        hit("hedge offsets delta")
    if op == "usecase.rates_hedge":
        assert sum(x * x for x in o["residual_key_rate"]) < .04 * sum(x * x for x in o["key_rate"])
        hit("hedge cuts key-rate risk")


def check_d(c, counts):
    """Stage D invariants, from the specs. Counts how many each rule saw."""
    op, i, e = c["operation"], c["inputs"], c["expected"]
    if e["status"] != "ok":
        return
    o, cid = e["outputs"], c["case_id"]

    def hit(k):
        counts[k] = counts.get(k, 0) + 1
    if op == "rates.ois.bootstrap":
        ds = [p["date"] for p in o["pillars"]]
        assert ds == sorted(set(ds)) and all(p["discount_factor"] > 0 for p in o["pillars"]), cid
        hit("OIS pillars strictly increasing, discount factors positive")
    if op == "rates.ois.compound_dated":
        rs = [f["rate"] for f in i["fixings"]]
        assert min(rs) - 1e-15 <= o["compounded_rate"] <= max(rs) * 1.01 + 1e-15, cid
        assert abs(o["interest"] - o["compounded_rate"] * o["accrual"]) < 1e-15, cid
        hit("compounded rate within the fixings' range (plus compounding); interest = rate x accrual")
    if op == "rates.fallback.rate":
        assert abs(o["fallback_rate"] - o["compounded_rate"] - o["spread_adjustment"]) < 1e-15 and o["spread_adjustment"] > 0, cid
        hit("fallback = compounded + positive fixed spread")
    if op == "rates.ois.step_curve":
        dfs, ds = o["discount_factors"], i["dates"]
        assert all(v > 0 for v in dfs), cid
        if i["base_rate"] > 0 and all(st["rate"] > 0 for st in i["steps"]):
            order = sorted(range(len(ds)), key=lambda k: ds[k])
            assert all(dfs[order[k + 1]] <= dfs[order[k]] for k in range(len(order) - 1)), cid
        hit("step curve positive; decreasing when all forwards are positive")
    if op == "rates.futures.convexity":
        assert o["convexity"] >= 0 and abs(o["futures_rate"] - o["convexity"] - o["forward_rate"]) < 1e-15, cid
        assert abs(o["futures_rate"] - (100 - i["price"]) / 100) < 1e-15, cid
        hit("convexity not negative; forward = futures rate - convexity")
    if op == "rates.csa.discount":
        if i["fx"] is None and i["collateral_spread"] > 0:
            assert all(0 < v < 1 for v in o["discount_factors"]), cid
        hit("CSA discount factors positive")
    if op == "rates.curve.joint_bootstrap":
        for k in ("discount_pillars", "projection_pillars"):
            ds = [p["date"] for p in o[k]]
            assert ds == sorted(set(ds)), cid
        hit("joint bootstrap pillars strictly increasing")
    if op == "calib.curve.smooth":
        assert len(o["forwards"]) == len(i["knots"]) and o["objective"] >= 0, cid
        res = sum(w * (f - y) ** 2 for f, y, w in zip(o["fitted"], i["zero_rates"], i.get("weights", [1] * len(i["zero_rates"]))))
        assert res <= o["objective"] * (1 + 1e-9) + 1e-18, cid
        hit("smooth fit: objective not negative and at least the weighted residual sum")
    if op == "bond.price.from_yield":
        assert abs(o["dirty"] - o["clean"] - o["accrued"]) < 1e-9 and o["accrued"] >= 0 and o["modified_duration"] > 0 and o["convexity"] > 0, cid
        assert abs(o["macaulay_duration"] / (1 + i["yield"] / i["bond"]["frequency"]) - o["modified_duration"]) < 1e-9, cid
        hit("bond: dirty = clean + accrued; modified = Macaulay / (1 + y/f); duration and convexity positive")
    if op == "repo.forward":
        assert (i["gc_rate"] is None) == (o["special_spread"] is None), cid
        hit("repo: special outputs null exactly when gc_rate is null")
    if op == "bond.futures.basis":
        irs = [b["implied_repo"] for b in o["bonds"]]
        assert irs[o["ctd"]] == max(irs), cid
        hit("CTD has the highest implied repo")
    if op == "fx.ndf.pv":
        assert o["forward"] > 0 and (i["fixing"] is None or o["forward"] == i["fixing"]), cid
        hit("NDF forward positive, equal to the fixing once known")
    if op == "fx.xccy.pv":
        sg = 1 if i["trade"]["side"] == "RECEIVE_FOREIGN" else -1
        assert abs(o["pv"] - sg * (i["spot"] * o["foreign_leg"] - o["domestic_leg"])) < 1e-6, cid
        hit("xccy pv = sign (spot foreign - domestic)")
    if op in ("credit.cds.bootstrap", "credit.curve.composite"):
        sv = [p["survival"] for p in o["pillars"]]
        assert all(0 < v <= 1 for v in sv) and all(b < a for a, b in zip(sv, sv[1:])), cid
        hit("CDS survival in (0, 1] and strictly falling")
    if op == "credit.cds.price":
        assert o["protection_leg"] > 0 and o["rpv01"] > 0 and o["accrued"] >= 0, cid
        hit("CDS legs positive")
    if op == "credit.index.intrinsic":
        assert abs(o["basis"] - (i["quoted_upfront"] - o["intrinsic_upfront"])) < 1e-15, cid
        hit("index basis = quoted - intrinsic")
    if op == "eq.dividend.implied":
        assert all(abs(a - b) < 1e-9 for a, b in zip(o["pv_dividends"], [sum(o["period_pv_dividends"][:k + 1]) for k in range(len(o["pv_dividends"]))])), cid
        hit("implied dividends: period amounts sum to the cumulative")
    if op == "eq.futures.basis":
        assert abs(o["basis"] - (i["futures_price"] - o["fair_price"])) < 1e-9, cid
        hit("futures basis = market - fair")
    if op == "eq.corporate_action.adjust":
        assert abs(o["adjusted_shares"] * o["ex_price"] - i["shares"] * i["cum_price"]) < 1e-6 * i["shares"] * i["cum_price"], cid
        hit("corporate action keeps shares x price")
    if op == "eq.trs.pv":
        sg = 1 if i["trade"]["side"] == "RECEIVE_EQUITY" else -1
        assert abs(o["pv"] - sg * (o["equity_leg"] - o["funding_leg"])) < 1e-9 * abs(o["equity_leg"]) + 1e-9, cid
        hit("TRS pv = sign (equity - funding)")
    if op == "infl.curve.cpi":
        assert all(v > 0 for v in o["cpi"]), cid
        hit("CPI positive")
    if op == "infl.linker.price":
        assert abs(o["nominal_clean"] - o["real_clean"] * o["index_ratio"]) < 1e-9 * o["nominal_clean"], cid
        hit("linker nominal = real x index ratio")
    if op == "rates.cap.price":
        assert all(c >= 0 for c in o["caplets"]) and abs(sum(o["caplets"]) - o["price"]) < 1e-9 * max(1, o["price"]), cid
        hit("cap = sum of non-negative caplets")
    if op == "rates.swaption.price":
        K, Sw, A, N = i["trade"]["strike"], o["forward_rate"], o["annuity"], i["trade"]["notional"]
        intr = N * A * max(Sw - K if i["trade"]["type"] == "PAYER" else K - Sw, 0)
        assert o["price"] >= intr - 1e-9 * N and A > 0, cid
        hit("swaption at least intrinsic on the annuity")
    if op == "calib.curve.robust":
        d = i["delta"]
        assert o["outliers"] == [j for j, r in enumerate(o["residuals"]) if abs(r) > d], cid
        hit("robust fit: outliers are exactly the residuals beyond delta")


def check_c(c, counts):
    """Stage C invariants, from the specs. Counts how many each rule saw."""
    op, i, e = c["operation"], c["inputs"], c["expected"]
    if e["status"] != "ok":
        return
    o, cid = e["outputs"], c["case_id"]

    def hit(k):
        counts[k] = counts.get(k, 0) + 1
    if op == "vol.option.price":
        F = o["forward"]
        D = i.get("discount_factor", math.exp(-i.get("rate", 0) * i["expiry_years"]))
        K, ph = i["strike"], 1 if i["option_type"] == "CALL" else -1
        lo = D * max(ph * (F - K), 0)
        assert o["price"] >= lo - 1e-12 * max(1, abs(lo)), cid
        if i["model"] != "BACHELIER":
            assert o["price"] <= D * (F + i.get("shift", 0) if ph == 1 else K + i.get("shift", 0)) + 1e-12, cid
        hit("option price within no-arbitrage bounds")
    if op == "vol.option.implied":
        assert o["vol"] >= 0, cid
        hit("implied vol not negative")
    if op in ("risk.vol.greeks", "vol.equity.price") or (op == "risk.vol.bump_greeks"):
        sign = -1 if i.get("side") == "SELL" else 1
        assert sign * o["gamma"] >= -1e-9 and sign * o["vega"] >= -1e-9, cid
        hit("gamma and vega not negative for a long option")
    if op == "eq.forward.outright":
        assert 0 < o["discount_factor"] and 0 < o["carry_factor"] and o["pv_dividends"] >= 0 and o["forward"] > 0, cid
        hit("forward positive, factors positive, dividends not negative")
    if op == "eq.forward.parity":
        assert o["max_residual"] >= 0 and o["outside_spread"] == sorted(o["outside_spread"]), cid
        hit("parity residual not negative, breaches ascending")
    if op == "vol.svi.evaluate":
        assert all(w > 0 for w in o["total_variance"]) and o["butterfly_free"] == (o["min_g"] >= 0) and o["min_g"] == min(o["g"]), cid
        hit("SVI variance positive, flag matches min g")
    if op == "vol.ssvi.evaluate" and 0.0 in i["log_moneyness"]:
        j = i["log_moneyness"].index(0.0)
        assert all(abs(r[j] - t) < 1e-14 for r, t in zip(o["total_variance"], i["thetas"])), cid
        hit("SSVI ATM total variance equals theta")
    if op == "vol.surface.query":
        assert all(w > 0 for w in o["total_variance"]), cid
        hit("surface variance positive")
    if op == "vol.surface.check":
        assert o["arbitrage_free"] == (not o["calendar_violations"] and not o["butterfly_violations"]), cid
        hit("surface flag matches violation lists")
    if op == "vol.sabr.density":
        assert o["negative_density"] == (o["min_density"] < -1e-9) and o["min_density"] == min(o["density"]), cid
        hit("SABR density flag matches minimum")
    if op == "vol.sabr.arbfree":
        f = i["forward"] + i["shift"]
        xs = [k + i["shift"] for k in i["strikes"]]
        cs = o["call_prices"]
        assert abs(o["mass"] - 1) < 1e-10 and abs(o["mean"] - f) < 1e-9 * f and o["min_density"] >= 0 and o["absorbed"] >= 0, cid
        assert all(max(f - x, 0) - 1e-12 <= p <= f + 1e-12 for x, p in zip(xs, cs)), cid
        assert all(cs[j + 1] <= cs[j] + 1e-12 for j in range(len(cs) - 1)), cid
        hit("arbitrage-free SABR: mass 1, mean f, density not negative, calls bounded and decreasing")
    if op == "usecase.vol_surface":
        assert o["vol"] > 0 and all(f > 0 for f in o["forwards"]), cid
        hit("use case 3 vol and forwards positive")


def main():
    sweep()
    n = 0
    for p in sorted(GOLDEN.glob("*.json")):
        for c in json.loads(p.read_text(encoding="utf-8"))["cases"]:
            check(c)
            n += 1
    note(f"invariants: {n} golden cases checked, none breaks a stated invariant")
    counts, m = {}, 0
    for p in sorted((GOLDEN.parent / "stage_b").glob("*.json")):
        for c in json.loads(p.read_text(encoding="utf-8"))["cases"]:
            check_b(c, counts)
            m += 1
    note(f"invariants: {m} stage B cases checked, none breaks one")
    for k, v in sorted(counts.items()):
        note(f"invariants:   {k}: {v}")
    counts, m = {}, 0
    for p in sorted((GOLDEN.parent / "stage_c").glob("*.json")):
        for c in json.loads(p.read_text(encoding="utf-8"))["cases"]:
            check_c(c, counts)
            m += 1
    note(f"invariants: {m} stage C cases checked, none breaks one")
    for k, v in sorted(counts.items()):
        note(f"invariants:   {k}: {v}")
    counts, m = {}, 0
    for p in sorted((GOLDEN.parent / "stage_d").glob("*.json")):
        for c in json.loads(p.read_text(encoding="utf-8"))["cases"]:
            check_d(c, counts)
            m += 1
    note(f"invariants: {m} stage D cases checked, none breaks one")
    for k, v in sorted(counts.items()):
        note(f"invariants:   {k}: {v}")


if __name__ == "__main__":
    main()
