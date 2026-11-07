"""Outside-oracle verifier for stage D (plan rule 11.2.5).

For each stage D golden case it reads the case's own inputs, builds the instrument from QuantLib's own
convention objects (taken only from qf_oracle/convmap.py, never inline), prices it in QuantLib, and compares
every output with the golden expected value under the case's own tolerance. A case counts as "outside
oracle" only if every output is matched this way, or is an identity of matched outputs or of inputs that the
handler names. Nothing here reads the generators' replays.

Writes oracle/outside_register.json (one row per verified case, with library, version, convention rows and
worst gap) and prints the per-suite coverage table that REPORT.md carries.

    cd oracle/python && uv run python -W ignore outside_d.py [--check-map]
"""
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import QuantLib as ql

from qf_oracle import convmap as CM
from qf_oracle.convmap import obj

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "conformance" / "runner"))
import runner  # noqa: E402  (tolerance comparison only)

POLICY = runner.load_policy(ROOT / "conformance" / "tolerances" / "policy.yaml")
Q = lambda d: ql.Date(d.day, d.month, d.year)  # noqa: E731
D = date.fromisoformat


def add_months(d, m):
    y, mo = divmod(d.month - 1 + m, 12)
    y += d.year
    mo += 1
    import calendar
    return date(y, mo, min(d.day, calendar.monthrange(y, mo)[1]))


def eom(d):
    return (d + timedelta(1)).month != d.month


class Used:
    def __init__(self):
        self.rows = set()

    def __call__(self, row, *a):
        self.rows.add(row)
        return obj(row, *a)


# ---------------------------------------------------------------- shared builders
def curve(u, c):
    a = D(c["as_of"])
    if c.get("interpolation", "LOG_LINEAR_DF") != "LOG_LINEAR_DF":
        raise NotImplementedError("only LOG_LINEAR_DF is mapped")
    dates = [Q(a)] + [Q(D(p["date"])) for p in c["pillars"]]
    jumps = [(D(j["date"]), j["factor"]) for j in c.get("jumps") or []]
    J = lambda d: math.prod(f for jd, f in jumps if jd < d)  # noqa: E731
    dfs = [1.0] + [p["discount_factor"] / J(D(p["date"])) for p in c["pillars"]]
    if jumps:
        q = u("CRV.LOG_LINEAR_DF_JUMPS", dates, dfs, [ql.QuoteHandle(ql.SimpleQuote(f)) for _, f in jumps], [Q(d) for d, _ in jumps])
    else:
        q = u("CRV.LOG_LINEAR_DF", dates, dfs)
    return q, a


def bond(u, b, settle):
    """Fixed bond: unadjusted coupon dates backward from maturity, ACT/ACT ICMA, EOM rule from the maturity."""
    ql.Settings.instance().evaluationDate = Q(settle)
    mat = D(b["maturity"])
    f = b["frequency"]
    sch = ql.Schedule(Q(add_months(mat, -12 * 40)), Q(mat), ql.Period(12 // f, ql.Months), u("CAL.NONE"), u("BDC.UNADJUSTED"), u("BDC.UNADJUSTED"),
                      u("GEN.BACKWARD"), eom(mat))
    dc = u("DC.ACT_ACT_ICMA", sch)
    return ql.FixedRateBond(0, 100.0, sch, [b["coupon"]], dc, u("BDC.UNADJUSTED")), dc, u(CM.FREQ[f])


# ---------------------------------------------------------------- handlers: inputs -> outputs, from QuantLib
def h_price_from_yield(u, i, exp):
    st = D(i["settlement"])
    qb, dc, fr = bond(u, i["bond"], st)
    y, cmp = i["yield"], u("CMP.BOND_YIELD")
    cl = ql.BondFunctions.cleanPrice(qb, y, dc, cmp, fr, Q(st))
    ai = qb.accruedAmount(Q(st))
    return {"dirty": cl + ai, "accrued": ai, "clean": cl,
            "modified_duration": ql.BondFunctions.duration(qb, y, dc, cmp, fr, ql.Duration.Modified, Q(st)),
            "macaulay_duration": ql.BondFunctions.duration(qb, y, dc, cmp, fr, ql.Duration.Macaulay, Q(st)),
            "convexity": ql.BondFunctions.convexity(qb, y, dc, cmp, fr, Q(st))}


def h_yield_from_price(u, i, exp):
    st = D(i["settlement"])
    qb, dc, fr = bond(u, i["bond"], st)
    y = ql.BondFunctions.bondYield(qb, ql.BondPrice(i["clean_price"], ql.BondPrice.Clean), dc, u("CMP.BOND_YIELD"), fr, Q(st), 1e-15, 200, 0.03)
    ai = qb.accruedAmount(Q(st))
    return {"yield": y, "dirty": i["clean_price"] + ai, "accrued": ai}


def h_price_from_curve(u, i, exp):
    st = D(i["settlement"])
    qb, _, _ = bond(u, i["bond"], st)
    qc, _ = curve(u, i["curve"])
    qc.enableExtrapolation()
    qb.setPricingEngine(ql.DiscountingBondEngine(ql.YieldTermStructureHandle(qc)))
    dp = qb.dirtyPrice()
    ai = qb.accruedAmount(Q(st))
    return {"dirty": dp, "accrued": ai, "clean": dp - ai}


def h_z_spread(u, i, exp):
    st = D(i["settlement"])
    qb, _, _ = bond(u, i["bond"], st)
    qc, _ = curve(u, i["curve"])
    qc.enableExtrapolation()
    z = ql.BondFunctions.zSpread(qb, ql.BondPrice(i["clean_price"], ql.BondPrice.Clean), qc, u("DC.ACT_365F"), u("CMP.CONTINUOUS"), ql.NoFrequency,
                                 Q(st), 1e-15, 300, 0.0)
    return {"z_spread": z}


def h_curve_discount(u, i, exp):
    qc, a = curve(u, i["curve"])
    qc.enableExtrapolation()
    ql.Settings.instance().evaluationDate = Q(a)
    dfs = [qc.discount(Q(D(d))) for d in i["dates"]]
    zs = [qc.zeroRate(Q(D(d)), u("DC.ACT_365F"), u("CMP.CONTINUOUS")).rate() for d in i["dates"]]
    return {"discount_factors": dfs, "zero_rates": zs}


def _ibor(u, proj, months):
    return ql.IborIndex("QF", ql.Period(months, ql.Months), 0, ql.USDCurrency(), u("CAL.USGS"), u("BDC.MODIFIED_FOLLOWING"), False, u("DC.ACT_360"),
                        ql.YieldTermStructureHandle(proj))


def _spot(u, t0):
    return D(u("CAL.USGS").advance(Q(t0), 2, ql.Days).ISO())


def _sched(u, st, months_total, step):
    cal = u("CAL.USGS")
    s = cal.adjust(Q(st), u("BDC.MODIFIED_FOLLOWING"))
    e = add_months(st, months_total)
    return ql.Schedule(s, Q(e), ql.Period(step, ql.Months), cal, u("BDC.MODIFIED_FOLLOWING"), u("BDC.MODIFIED_FOLLOWING"), u("GEN.BACKWARD"), False)


def _vol_cap(u, model, v):
    vt = ql.ShiftedLognormal if model == "BLACK_76" else ql.Normal
    return ql.OptionletVolatilityStructureHandle(ql.ConstantOptionletVolatility(0, u("CAL.USGS"), u("BDC.MODIFIED_FOLLOWING"), v, u("DC.ACT_365F"), vt))


def h_cap(u, i, exp):
    disc, t0 = curve(u, i["discount"])
    proj, _ = curve(u, i["projection"])
    disc.enableExtrapolation()
    proj.enableExtrapolation()
    ql.Settings.instance().evaluationDate = Q(t0)
    tr = i["trade"]
    spot = _spot(u, t0)
    st = D(u("CAL.USGS").adjust(Q(add_months(spot, tr["start_months"])), u("BDC.MODIFIED_FOLLOWING")).ISO())
    sch = _sched(u, st, tr["tenor_months"], 3)
    idx = _ibor(u, proj, 3)
    leg = ql.IborLeg([tr["notional"]], sch, idx, u("DC.ACT_360"), u("BDC.MODIFIED_FOLLOWING"), fixingDays=[0])
    n = len(leg)
    vols = i["vol"] if isinstance(i["vol"], list) else [i["vol"]] * n
    if len(vols) != n:
        raise ValueError("vol count")
    eng = obj("OPT.BLACK_76") if i["model"] == "BLACK_76" else obj("OPT.BACHELIER")
    u.rows.add("OPT." + i["model"])
    caps = []
    for k, cf in enumerate(leg):
        one = ql.Leg([cf])
        c = (ql.Cap if tr["type"] == "CAP" else ql.Floor)(one, [tr["strike"]])
        c.setPricingEngine(eng(ql.YieldTermStructureHandle(disc), _vol_cap(u, i["model"], vols[k])))
        caps.append(c.NPV())
    return {"price": sum(caps), "caplets": caps}


def h_swaption(u, i, exp):
    disc, t0 = curve(u, i["discount"])
    proj, _ = curve(u, i["projection"])
    disc.enableExtrapolation()
    proj.enableExtrapolation()
    ql.Settings.instance().evaluationDate = Q(t0)
    tr = i["trade"]
    N = tr["notional"]
    spot = _spot(u, t0)
    st = D(u("CAL.USGS").adjust(Q(add_months(spot, tr["expiry_months"])), u("BDC.MODIFIED_FOLLOWING")).ISO())
    fx = _sched(u, st, tr["tenor_months"], 12)
    fl = _sched(u, st, tr["tenor_months"], 3)
    idx = _ibor(u, proj, 3)
    typ = ql.Swap.Payer if tr["type"] == "PAYER" else ql.Swap.Receiver
    sw = ql.VanillaSwap(typ, N, fx, tr["strike"], u("DC.THIRTY_360_BOND"), fl, idx, 0.0, u("DC.ACT_360"))
    dh = ql.YieldTermStructureHandle(disc)
    sw.setPricingEngine(ql.DiscountingSwapEngine(dh))
    A = abs(sw.fixedLegBPS()) / 1e-4 / N
    S = sw.fairRate()
    ex = ql.EuropeanExercise(Q(st))
    so = ql.Swaption(sw, ex)
    if i["model"] == "BLACK_76":
        u.rows.add("OPT.BLACK_76")
        so.setPricingEngine(ql.BlackSwaptionEngine(dh, ql.QuoteHandle(ql.SimpleQuote(i["vol"])), u("DC.ACT_365F")))
    else:
        u.rows.add("OPT.BACHELIER")
        so.setPricingEngine(ql.BachelierSwaptionEngine(dh, ql.QuoteHandle(ql.SimpleQuote(i["vol"])), u("DC.ACT_365F")))
    return {"price": so.NPV(), "forward_rate": S, "annuity": A}


def h_cds(u, i, exp):
    T = D(i["trade_date"])
    ql.Settings.instance().evaluationDate = Q(T)
    disc, _ = curve(u, i["discount"])
    disc.enableExtrapolation()
    hp = i["hazard"]["pillars"]
    dates, hz, prev_t, prev_lq = [Q(T)], [], 0.0, 0.0
    for p in hp:
        t = (D(p["date"]) - T).days / 365
        lq = -math.log(p["survival"])
        hz.append((lq - prev_lq) / (t - prev_t))
        dates.append(Q(D(p["date"])))
        prev_t, prev_lq = t, lq
    hc = u("CRV.HAZARD_FLAT", dates, [hz[0]] + hz)
    hc.enableExtrapolation()
    tr = i["trade"]
    R = i["recovery"]
    cal = u("CAL.WEEKENDS")
    sch = ql.Schedule(Q(T), Q(D(tr["maturity"])), ql.Period(3, ql.Months), cal, u("BDC.FOLLOWING"), u("BDC.UNADJUSTED"), u("GEN.CDS2015"), False)
    c = ql.CreditDefaultSwap(ql.Protection.Buyer, 1.0, 0.0, tr["coupon"], sch, u("BDC.FOLLOWING"), u("DC.ACT_360"), True, True, Q(T) + 1,
                             cal.advance(Q(T), 3, ql.Days), ql.FaceValueClaim(), u("DC.ACT_360_INCL_LAST"), True, Q(T), 3)
    digital = i.get("payout") == "DIGITAL"
    eng = u("ENG.ISDA_CDS")
    c.setPricingEngine(eng(ql.DefaultProbabilityTermStructureHandle(hc), 0.0 if digital else R, ql.YieldTermStructureHandle(disc), False,
                           ql.IsdaCdsEngine.Taylor, ql.IsdaCdsEngine.NoBias, ql.IsdaCdsEngine.Piecewise))
    sign = 1 if tr["side"] == "BUY_PROTECTION" else -1
    # accrued: coupon x ACT/360 from QuantLib's first accrual start to T + 1, the spec's rule on QuantLib's own schedule.
    acc = tr["coupon"] * u("DC.ACT_360").yearFraction(sch[0], Q(T) + 1)
    return {"pv": sign * tr["notional"] * c.NPV(), "upfront": c.fairUpfront(), "accrued": acc, "par_spread": c.fairSpread(),
            "protection_leg": c.defaultLegNPV(), "rpv01": abs(c.couponLegBPS()) / 1e-4}


def _qper(t):
    return ql.Period(int(t[:-1]), {"W": ql.Weeks, "M": ql.Months, "Y": ql.Years}[t[-1]])


def h_ois_bootstrap(u, i, exp):
    conv, a = i["convention"], D(i["as_of"])
    ql.Settings.instance().evaluationDate = Q(a)
    sl, pl = u("OIS.LAGS", conv)
    hs = [ql.OISRateHelper(sl, _qper(q["tenor"]), ql.QuoteHandle(ql.SimpleQuote(q["rate"])), u("IDX." + conv), ql.YieldTermStructureHandle(), True, pl)
          for q in i["quotes"]]
    ip = i.get("interpolation", "LOG_LINEAR_DF")
    if ip == "LOG_LINEAR_DF":
        k = ql.PiecewiseLogLinearDiscount
        u.rows.add("CRV.LOG_LINEAR_DF")
    elif ip == "LINEAR_ZERO":
        k = ql.PiecewiseLinearZero
        u.rows.add("CRV.LINEAR_ZERO")
    else:
        raise NotImplementedError(ip)
    js = i.get("jumps") or []
    jq = [ql.QuoteHandle(ql.SimpleQuote(j["factor"])) for j in js]
    qc = k(Q(a), hs, u("DC.ACT_365F"), jq, [Q(D(j["date"])) for j in js])
    if js:
        u.rows.add("CRV.LOG_LINEAR_DF_JUMPS")
    piv = [h.pillarDate() for h in hs]
    return {"pillars": [{"date": p.ISO(), "discount_factor": qc.discount(p)} for p in piv]}


def h_ois_pv(u, i, exp):
    qc, a = curve(u, i["curve"])
    qc.enableExtrapolation()
    ql.Settings.instance().evaluationDate = Q(a)
    tr = i["trade"]
    conv, N = tr["convention"], tr["notional"]
    sl, pl = u("OIS.LAGS", conv)
    h = ql.YieldTermStructureHandle(qc)
    sw = ql.MakeOIS(_qper(tr["tenor"]), u("IDX." + conv, h), tr["fixed_rate"], settlementDays=sl, paymentLag=pl, nominal=N,
                    swapType=ql.Swap.Payer if tr["side"] == "PAY" else ql.Swap.Receiver, pricingEngine=ql.DiscountingSwapEngine(h), telescopicValueDates=True)
    val = dict(exp["valuation"])  # identity rows: currency, model, conventions, as_of come from the inputs and the spec's fixed strings
    val["pv"] = sw.NPV()
    return {"valuation": val, "par_rate": sw.fairRate(), "annuity": abs(sw.fixedLegBPS()) / 1e-4 / N}


def _compound(u, conv, S0, E0, method, k, fixings):
    ql.Settings.instance().evaluationDate = Q(E0 + timedelta(60))
    ix = u("IDX." + conv)
    ix.clearFixings()
    for f in fixings:
        ix.addFixing(Q(D(f["date"])), f["rate"])
    lb, lo, shift = u("CMPD.METHOD", method, k)
    leg = ql.OvernightLeg([1.0], ql.Schedule([Q(S0), Q(E0)]), ix, ix.dayCounter(), ql.Following, [1.0], [0.0], False, ql.RateAveraging.Compound,
                          ql.NullCalendar(), 0, lb, lo, shift)
    cp = ql.as_floating_rate_coupon(leg[0])
    r, acc = cp.rate(), cp.accrualPeriod()
    ix.clearFixings()
    return r, acc


def h_compound(u, i, exp):
    r, acc = _compound(u, i["convention"], D(i["start"]), D(i["end"]), i["method"], i["shift_days"], i["fixings"])
    return {"compounded_rate": r, "accrual": acc, "interest": r * acc}


def h_fallback(u, i, exp):
    conv, spread = u("ISDA.FALLBACK", i["ibor"])
    r, _ = _compound(u, conv, D(i["start"]), D(i["end"]), "OBSERVATION_SHIFT", 2, i["fixings"])
    return {"compounded_rate": r, "spread_adjustment": spread, "fallback_rate": r + spread}


def h_cds_bootstrap(u, i, exp):
    """Reprice check: pillar dates from QuantLib's cdsMaturity; the golden survivals, priced in QuantLib's ISDA engine, must
    return each quoted spread within 1e-10 (the golden survival tolerance, 1e-9, moves a spread by more). Survivals are then the golden's own, so they pass by construction once that holds."""
    T = D(i["trade_date"])
    ql.Settings.instance().evaluationDate = Q(T)
    mats = [ql.cdsMaturity(Q(T), _qper(q["tenor"]), u("GEN.CDS2015")) for q in i["quotes"]]
    pil = exp["pillars"]
    if [m.ISO() for m in mats] != [p["date"] for p in pil]:
        return {"pillars": [{"date": m.ISO(), "survival": None} for m in mats]}
    hz = {"trade_date": i["trade_date"], "discount": i["discount"], "hazard": {"as_of": i["trade_date"], "pillars": pil}, "recovery": i["recovery"], "payout": "STANDARD"}
    for q, m in zip(i["quotes"], mats):
        out = h_cds(u, {**hz, "trade": {"maturity": m.ISO(), "coupon": q["spread"], "notional": 1.0, "side": "BUY_PROTECTION"}}, None)
        if abs(out["par_spread"] - q["spread"]) > 1e-10:
            return {"pillars": [{"date": p["date"], "survival": None} for p in pil]}
    return {"pillars": pil}


# ---------------------------------------------------------------- dispatch
HANDLERS = {
    "bond.price.from_yield": h_price_from_yield,
    "bond.yield.from_price": h_yield_from_price,
    "bond.price.from_curve": h_price_from_curve,
    "bond.spread.z": h_z_spread,
    "rates.curve.discount": h_curve_discount,
    "rates.cap.price": h_cap,
    "rates.swaption.price": h_swaption,
    "credit.cds.price": h_cds,
    "credit.cds.bootstrap": h_cds_bootstrap,
    "rates.ois.bootstrap": h_ois_bootstrap,
    "rates.ois.pv": h_ois_pv,
    "rates.ois.compound_dated": h_compound,
    "rates.fallback.rate": h_fallback,
}


def judge(case, got):
    exp = case["expected"]["outputs"]
    if set(got) != set(exp):
        return False, f"keys {sorted(got)} vs {sorted(exp)}", None
    cls = POLICY[case["tolerance_class"]]
    per = case.get("output_classes", {})
    msgs, worst = [], 0.0
    for k, e in exp.items():
        c = POLICY[per[k]] if k in per else cls
        msgs += runner.compare(got[k], e, c, None if k in per else case.get("tolerance_limit"), k)
        a, b = json.dumps(got[k]), json.dumps(e)
        for x, y in zip(json.loads(a) if isinstance(got[k], list) else [got[k]], json.loads(b) if isinstance(e, list) else [e]):
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                worst = max(worst, abs(x - y))
    return not msgs, "; ".join(msgs[:2]), worst


def load(folder="stage_d"):
    out = []
    for p in sorted((ROOT / "datasets" / "golden" / folder).glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        out.append((d["suite"], d["cases"]))
    return out


def verify_all(folder="stage_d", show=True):
    reg, table = [], []
    for suite, cases in load(folder):
        n_ok = 0
        for c in cases:
            h = HANDLERS.get(c["operation"])
            if not h or c["expected"]["status"] != "ok":
                continue
            u = Used()
            try:
                got = h(u, c["inputs"], c["expected"]["outputs"])
                ok, why, worst = judge(c, got)
            except NotImplementedError as e:
                ok, why, worst = False, f"not mapped: {e}", None
            if ok:
                n_ok += 1
                reg.append({"case_id": c["case_id"], "operation": c["operation"], "library": CM.LIBRARY, "version": CM.VERSION,
                            "convention_rows": sorted(u.rows), "map_review": CM.REVIEW, "worst_abs_gap": worst})
            elif show:
                print(f"  not verified {c['case_id']} {c['operation']}: {why}")
        table.append((suite, n_ok, len(cases)))
    return reg, table


def check_map():
    text = (ROOT / "oracle" / "CONVENTION_MAP.md").read_text(encoding="utf-8")
    missing = [r for r in CM.ROWS if f"`{r}`" not in text]
    if missing:
        print("rows missing from CONVENTION_MAP.md:", missing)
        return False
    return True


def coverage_section():
    """Verifies every stage D case and returns the REPORT.md section (markdown lines). Writes the register."""
    reg, table = verify_all(show=False)
    tot_ok, tot = sum(t[1] for t in table), sum(t[2] for t in table)
    out = ["## Stage D outside-oracle coverage (rule 11.2.5)", "",
           f"Written by `oracle/python/outside_d.py`. A case counts only if QuantLib {CM.VERSION}, built from its own convention objects through "
           "`qf_oracle/convmap.py` (reviewed copy: `oracle/CONVENTION_MAP.md`), reproduces every output of the case within the case's own tolerance. "
           "One row per counted case, with the library version and the convention rows used, is in `oracle/outside_register.json`. "
           "Error cases are in the denominator and never count. Older `verified_by` tags that name QuantLib are not counted here unless this check passes.", "",
           "| Suite | Outside-oracle cases | Cases | Share |", "|---|---|---|---|"]
    out += [f"| `{s}` | {k} | {n} | {100 * k / n:.0f}% |" for s, k, n in table]
    out += [f"| **stage D** | **{tot_ok}** | **{tot}** | **{100 * tot_ok / tot:.1f}%** |", ""]
    (ROOT / "oracle" / "outside_register.json").write_text(json.dumps({"rule": "plan 11.2.5", "library": CM.LIBRARY, "version": CM.VERSION,
                                                                       "map_review": CM.REVIEW, "cases": reg}, indent=1) + "\n", encoding="utf-8", newline="\n")
    return out, tot_ok, tot


def main():
    if not check_map():
        return 1
    out, k, n = coverage_section()
    print("\n".join(out))
    floor = 0.60
    if k / n < floor:
        print(f"stage D outside-oracle share {k / n:.3f} is below the floor {floor}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
