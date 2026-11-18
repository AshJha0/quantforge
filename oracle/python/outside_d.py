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


def h_futures_convexity(u, i, exp):
    fr = (100 - i["price"]) / 100
    cvx = u("HW.CONVEXITY")(i["price"], i["start_years"], i["end_years"], i["sigma"], i["mean_reversion"])
    return {"futures_rate": fr, "convexity": cvx, "forward_rate": fr - cvx}


def _repo_parts(u, i):
    st, en = D(i["start"]), D(i["end"])
    qb, _, _ = bond(u, i["bond"], st)
    rate = lambda r: u("RATE.SIMPLE_ACT_360", r)  # noqa: E731
    dirty = i["clean_price"] + qb.accruedAmount(Q(st))
    cpns = [(cf.date(), cf.amount()) for cf in qb.cashflows() if Q(st) < cf.date() <= Q(en)]
    ai1 = qb.accruedAmount(Q(en))
    return st, en, dirty, cpns, ai1, rate


def h_repo_forward(u, i, exp):
    st, en, dirty, cpns, ai1, rate = _repo_parts(u, i)
    rr = i["repo_rate"]
    fd = dirty * rate(rr).compoundFactor(Q(st), Q(en)) - sum(c * rate(rr).compoundFactor(d, Q(en)) for d, c in cpns)
    tau = u("DC.ACT_360").yearFraction(Q(st), Q(en))
    gc = i.get("gc_rate")
    return {"dirty": dirty, "forward_dirty": fd, "forward_clean": fd - ai1, "interest": dirty * rr * tau,
            "special_spread": None if gc is None else gc - rr, "specialness_value": None if gc is None else dirty * (gc - rr) * tau}


def h_repo_implied(u, i, exp):
    st, en, dirty, cpns, ai1, rate = _repo_parts(u, i)
    dc = u("DC.ACT_360")
    fd = i["forward_clean"] + ai1
    num = fd - dirty + sum(c for _, c in cpns)
    den = dirty * dc.yearFraction(Q(st), Q(en)) - sum(c * dc.yearFraction(d, Q(en)) for d, c in cpns)
    return {"repo_rate": num / den}


def h_csa(u, i, exp):
    if i.get("fx") is not None:
        raise NotImplementedError("CSA with FX forwards has no QuantLib object")
    qc, a = curve(u, i["curve"])
    qc.enableExtrapolation()
    ql.Settings.instance().evaluationDate = Q(a)
    sp = u("CRV.ZERO_SPREAD", ql.YieldTermStructureHandle(qc), i["collateral_spread"])
    sp.enableExtrapolation()
    return {"discount_factors": [sp.discount(Q(D(d))) for d in i["dates"]]}


def _xccy_leg(u, idx_row, proj, disc, start, months, n, spread):
    cal = u("CAL.JOINT_USGS_EUTA")
    sch = ql.Schedule(Q(start), Q(add_months(start, months)), ql.Period(3, ql.Months), cal, u("BDC.MODIFIED_FOLLOWING"), u("BDC.MODIFIED_FOLLOWING"),
                      ql.DateGeneration.Forward, False)
    u.rows.add("GEN.FORWARD")
    ix = u(idx_row, ql.YieldTermStructureHandle(proj))
    leg = ql.OvernightLeg([n], sch, ix, u("DC.ACT_360"), u("BDC.MODIFIED_FOLLOWING"), [1.0], [spread], True)
    dh = ql.YieldTermStructureHandle(disc)
    cpn = ql.CashFlows.npv(leg, dh, False, disc.referenceDate(), disc.referenceDate())
    return cpn + n * disc.discount(sch[len(sch) - 1]) - n * disc.discount(sch[0])


def h_xccy_pv(u, i, exp):
    dom, a = curve(u, i["domestic"])
    fp, _ = curve(u, i["foreign_projection"])
    fd, _ = curve(u, i["foreign_discount"])
    for c in (dom, fp, fd):
        c.enableExtrapolation()
    ql.Settings.instance().evaluationDate = Q(a)
    t = i["trade"]
    st = D(t["start"])
    fl = _xccy_leg(u, "IDX.ESTR", fp, fd, st, t["months"], t["foreign_notional"], t["spread"])
    dl = _xccy_leg(u, "IDX.SOFR", dom, dom, st, t["months"], t["foreign_notional"] * i["spot"], 0.0)
    sign = 1 if t["side"] == "RECEIVE_FOREIGN" else -1
    return {"pv": sign * (i["spot"] * fl - dl), "foreign_leg": fl, "domestic_leg": dl}


def h_xccy_boot(u, i, exp):
    """Reprice check: the golden foreign discount pillars, with QuantLib OvernightLeg foreign legs, give L_foreign within 1e-12 per unit
    for every quote, and the pillar dates are QuantLib's schedule ends."""
    fp, a = curve(u, i["foreign_projection"])
    fp.enableExtrapolation()
    ql.Settings.instance().evaluationDate = Q(a)
    fd, _ = curve(u, {"as_of": str(a), "interpolation": i["interpolation"], "pillars": exp["pillars"]})
    fd.enableExtrapolation()
    st = D(i["start"])
    bad = [{"date": p["date"], "discount_factor": None} for p in exp["pillars"]]
    cal = u("CAL.JOINT_USGS_EUTA")
    for q, p in zip(i["quotes"], exp["pillars"]):
        end = cal.adjust(Q(add_months(st, q["months"])), u("BDC.MODIFIED_FOLLOWING")).ISO()
        if end != p["date"] or abs(_xccy_leg(u, "IDX.ESTR", fp, fd, st, q["months"], 1.0, q["spread"])) > 1e-12:
            return {"pillars": bad}
    return {"pillars": exp["pillars"]}


# ---------------------------------------------------------------- H-19 handlers (2026-11-18): FRN, asset swap, conversion factor,
# futures basis, NDF, linker from yield, Black-76 edge prices, USGS calendar edges, OIS basis spread, CSA with FX, credit index and composite.
# Where an output is the spec's algebra on QuantLib objects (not a QuantLib instrument), the docstring says so; CONVENTION_MAP.md
# lists each one under "Known mapping points".
def h_asset_swap(u, i, exp):
    """Par-par asset swap: P_curve from QuantLib's bond engine; the annuity is QuantLib's NPV of a unit ACT/360 leg on the spec's
    floating schedule (quarterly back from maturity, unadjusted, first period from settlement), valued at settlement. The spread is
    arithmetic on the two."""
    st, mat = D(i["settlement"]), D(i["bond"]["maturity"])
    pc = h_price_from_curve(u, {"bond": i["bond"], "settlement": i["settlement"], "curve": i["curve"]}, None)["dirty"]
    qc, _ = curve(u, i["curve"])
    qc.enableExtrapolation()
    sch = ql.Schedule(Q(st), Q(mat), ql.Period(3, ql.Months), u("CAL.NONE"), u("BDC.UNADJUSTED"), u("BDC.UNADJUSTED"), u("GEN.BACKWARD"), False)
    leg = ql.FixedRateLeg(sch, u("DC.ACT_360"), [1.0], [1.0])
    ann = ql.CashFlows.npv(leg, ql.YieldTermStructureHandle(qc), False, Q(st), Q(st))
    return {"spread": (pc - i["dirty_price"]) / (100 * ann), "annuity": ann}


def h_frn(u, i, exp):
    """QuantLib IborLeg (par coupons, fixing lag 0, unadjusted, ACT/360) on the projection curve, the current period's rate as a
    fixing, plus redemption; discounted on the discount curve with the discount margin as a continuous zero spread, valued at settlement."""
    st, mat, f = D(i["settlement"]), D(i["maturity"]), i["frequency"]
    disc, a = curve(u, i["discount"])
    proj, _ = curve(u, i["projection"])
    disc.enableExtrapolation()
    proj.enableExtrapolation()
    ql.Settings.instance().evaluationDate = Q(a)
    ql.IndexManager.instance().clearHistories()
    sch = ql.Schedule(Q(add_months(mat, -12 * 40)), Q(mat), ql.Period(12 // f, ql.Months), u("CAL.NONE"), u("BDC.UNADJUSTED"), u("BDC.UNADJUSTED"),
                      u("GEN.BACKWARD"), eom(mat))
    idx = u("IDX.TERM_FRN", ql.YieldTermStructureHandle(proj), 12 // f)
    for k in range(len(sch) - 1):
        if sch[k] <= Q(st) < sch[k + 1] and sch[k] <= Q(a):
            idx.addFixing(sch[k], i["current_rate"])
    leg = ql.IborLeg([100.0], sch, idx, u("DC.ACT_360"), u("BDC.UNADJUSTED"), fixingDays=[0], spreads=[i["margin"]])
    leg = ql.Leg([cf for cf in leg if cf.date() > Q(st)] + [ql.SimpleCashFlow(100.0, Q(mat))])
    dm = u("CRV.DISCOUNT_MARGIN", ql.YieldTermStructureHandle(disc), i["discount_margin"])
    dm.enableExtrapolation()
    dirty = ql.CashFlows.npv(leg, ql.YieldTermStructureHandle(dm), False, Q(st), Q(st))
    acc = ql.CashFlows.accruedAmount(leg, False, Q(st))
    ql.IndexManager.instance().clearHistories()
    return {"dirty": dirty, "accrued": acc, "clean": dirty - acc}


CF_QUARTERS = {None, "TEN_YEAR", "ULTRA_TEN_YEAR", "BOND", "ULTRA_BOND"}


def h_conversion_factor(u, i, exp):
    """CME conversion factor as a QuantLib price: a semi-annual bond with the rounded coupon, maturing n years and z months
    (rounded down to a quarter where the contract says so) after the first day of the delivery month, priced at a 6% yield
    compounded semi-annually on THIRTY_360_BOND (all dates on the 1st, so periods are whole months, as CME's v/6), clean,
    per unit. The 1/8 coupon rounding, the month count and the 4-decimal rounding are the spec's arithmetic."""
    b = i["bond"]
    c = math.floor(b["coupon"] * 800 + 0.5) / 800
    y, m = map(int, i["delivery_month"].split("-"))
    st, mat = date(y, m, 1), D(b["maturity"])
    months = (mat.year - st.year) * 12 + mat.month - st.month
    n, z = divmod(months, 12)
    if i.get("contract") in CF_QUARTERS:
        z -= z % 3
    syn = add_months(st, 12 * n + z)
    ql.Settings.instance().evaluationDate = Q(st)
    sch = ql.Schedule(Q(add_months(syn, -12 * 40)), Q(syn), ql.Period(6, ql.Months), u("CAL.NONE"), u("BDC.UNADJUSTED"), u("BDC.UNADJUSTED"),
                      u("GEN.BACKWARD"), False)
    dc = u("DC.THIRTY_360_BOND")
    qb = ql.FixedRateBond(0, 100.0, sch, [c], dc, u("BDC.UNADJUSTED"))
    u.rows.add("CF.CME_SYNTHETIC")
    cl = ql.BondFunctions.cleanPrice(qb, i["notional_coupon"], dc, u("CMP.BOND_YIELD"), u("FREQ.2"), Q(st))
    return {"conversion_factor": round(cl / 100, 4)}


def h_futures_basis(u, i, exp):
    """Accrued and coupon cash flows from QuantLib's bond, growth factors from QuantLib InterestRate on ACT/360; invoice, bases and
    implied repo are the spec's algebra on them (as repo.forward)."""
    F, rr = i["futures_price"], i["repo_rate"]
    out = []
    for b in i["bonds"]:
        r = {"bond": b, "start": i["settlement"], "end": i["delivery"], "clean_price": b["clean_price"]}
        st, en, dirty, cpns, ai1, rate = _repo_parts(u, r)
        inv = F * b["conversion_factor"] + ai1
        fd = dirty * rate(rr).compoundFactor(Q(st), Q(en)) - sum(c * rate(rr).compoundFactor(d, Q(en)) for d, c in cpns)
        dc = u("DC.ACT_360")
        imp = (inv + sum(c for _, c in cpns) - dirty) / (dirty * dc.yearFraction(Q(st), Q(en)) - sum(c * dc.yearFraction(d, Q(en)) for d, c in cpns))
        out.append({"invoice": inv, "gross_basis": b["clean_price"] - F * b["conversion_factor"], "net_basis": fd - inv, "implied_repo": imp})
    ctd = max(range(len(out)), key=lambda k: out[k]["implied_repo"])
    return {"bonds": out, "ctd": ctd}


def h_ndf(u, i, exp):
    """USD and offshore discount factors from QuantLib curves; F (covered parity) and the USD payoff's forward value are arithmetic."""
    du, a = curve(u, i["usd_curve"])
    do, _ = curve(u, i["offshore_curve"])
    du.enableExtrapolation()
    do.enableExtrapolation()
    ql.Settings.instance().evaluationDate = Q(a)
    t = i["trade"]
    p = Q(D(t["payment_date"]))
    F = i["fixing"] if i["fixing"] is not None else i["spot"] * du.discount(p) / do.discount(p)
    sign = 1 if t["side"] == "BUY" else -1
    return {"pv": sign * t["usd_notional"] * (1 - t["strike"] / F) * du.discount(p), "forward": F}


def _treasury_round(x):
    """31 CFR 356 App. B (ruling R6-7.5): truncate to six decimals, then round half up to five. Arithmetic, not library."""
    from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
    return float(Decimal(repr(x)).quantize(Decimal("0.000001"), ROUND_DOWN).quantize(Decimal("0.00001"), ROUND_HALF_UP))


def h_linker(u, i, exp):
    """Ref CPI from QuantLib CPI.laggedFixing (3-month lag, linear) on a USCPI index holding the case's fixings; real prices from
    QuantLib BondFunctions (as bond.price.from_yield); Treasury rounding and the index-ratio products are arithmetic."""
    st = D(i["settlement"])
    ql.Settings.instance().evaluationDate = Q(st)
    ql.IndexManager.instance().clearHistories()
    ix = ql.USCPI()
    for fx in i["cpi_fixings"]:
        y, m = map(int, fx["month"].split("-"))
        ix.addFixing(ql.Date(1, m, y), fx["value"])
    lag, interp = u("CPI.TIPS_REF")
    ref = _treasury_round(ql.CPI.laggedFixing(ix, Q(st), lag, interp))
    ql.IndexManager.instance().clearHistories()
    ratio = _treasury_round(ref / i["base_ref_cpi"])
    r = h_price_from_yield(u, {"bond": i["bond"], "settlement": i["settlement"], "yield": i["real_yield"]}, None)
    return {"ref_cpi": ref, "index_ratio": ratio, "real_clean": r["clean"], "real_accrued": r["accrued"],
            "nominal_clean": r["clean"] * ratio, "nominal_accrued": r["accrued"] * ratio}


def h_option_price(u, i, exp):
    """QuantLib blackFormula (BLACK_76) or bachelierBlackFormula on the case's forward, strike, discount factor and vol x sqrt(T)."""
    ty = ql.Option.Call if i["option_type"] == "CALL" else ql.Option.Put
    sd = i["vol"] * math.sqrt(i["expiry_years"])
    fn = u("OPT.FORMULA." + i["model"])
    return {"price": fn(ty, i["strike"], i["forward"], sd, i["discount_factor"]), "forward": i["forward"]}


def h_is_bd(u, i, exp):
    return {"is_business_day": bool(u("CAL." + i["calendar"]).isBusinessDay(Q(D(i["date"]))))}


def h_add_bd(u, i, exp):
    return {"date": u("CAL." + i["calendar"]).advance(Q(D(i["date"])), i["days"], ql.Days).ISO()}


def h_ois_spread(u, i, exp):
    """Difference of QuantLib MakeOIS fair rates on the two projection curves, both discounted on `discount` (spec acceptance)."""
    disc, a = curve(u, i["discount"])
    disc.enableExtrapolation()
    ql.Settings.instance().evaluationDate = Q(a)
    conv = i["convention"]
    sl, pl = u("OIS.LAGS", conv)
    dh = ql.YieldTermStructureHandle(disc)
    fr = []
    for k in ("projection_a", "projection_b"):
        pc, pa = curve(u, i[k])
        if pa != a:
            raise NotImplementedError("projection as_of differs")
        pc.enableExtrapolation()
        sw = ql.MakeOIS(_qper(i["tenor"]), u("IDX." + conv, ql.YieldTermStructureHandle(pc)), 0.0, settlementDays=sl, paymentLag=pl,
                        pricingEngine=ql.DiscountingSwapEngine(dh), telescopicValueDates=True)
        fr.append(sw.fairRate())
    return {"spread": fr[0] - fr[1]}


def h_csa_fx(u, i, exp):
    """CSA with FX: the collateral discount from QuantLib ZeroSpreadedTermStructure (as rates.csa.discount without FX), times the
    input identity spot / F(d)."""
    fx = i.get("fx")
    if fx is None:
        return h_csa(u, i, exp)
    base = h_csa(u, {**i, "fx": None}, exp)["discount_factors"]
    fwd = {f["date"]: f["forward"] for f in fx["forwards"]}
    return {"discount_factors": [b * fx["spot"] / fwd[d] for b, d in zip(base, i["dates"])]}


def h_index_intrinsic(u, i, exp):
    """Each name's clean upfront from QuantLib IsdaCdsEngine (as credit.cds.price); the weighted mean and basis are arithmetic."""
    ups = []
    for nm in i["names"]:
        c = h_cds(u, {"trade_date": i["trade_date"], "discount": i["discount"], "hazard": nm["hazard"], "recovery": nm["recovery"], "payout": "STANDARD",
                      "trade": {"maturity": i["trade"]["maturity"], "coupon": i["trade"]["coupon"], "notional": 1.0, "side": "BUY_PROTECTION"}}, None)
        ups.append(c["upfront"])
    w = [nm["weight"] for nm in i["names"]]
    iu = sum(a * b for a, b in zip(w, ups)) / sum(w)
    return {"intrinsic_upfront": iu, "basis": i["quoted_upfront"] - iu, "name_upfronts": ups}


def h_composite(u, i, exp):
    """Composite spreads are arithmetic on the inputs; the pillars pass the credit.cds.bootstrap reprice check in QuantLib's ISDA engine."""
    cs = i["constituents"]
    W = sum(c["weight"] for c in cs)
    sc = i.get("scale", 1.0)
    sp = [sc * sum(c["weight"] * c["quotes"][k]["spread"] for c in cs) / W for k in range(len(cs[0]["quotes"]))]
    q = [{"tenor": cs[0]["quotes"][k]["tenor"], "spread": s} for k, s in enumerate(sp)]
    pil = h_cds_bootstrap(u, {"trade_date": i["trade_date"], "discount": i["discount"], "recovery": i["recovery"], "quotes": q}, {"pillars": exp["pillars"]})
    return {"spreads": sp, "pillars": pil["pillars"]}


# ---------------------------------------------------------------- dispatch
HANDLERS = {
    "bond.price.from_yield": h_price_from_yield,
    "bond.yield.from_price": h_yield_from_price,
    "bond.price.from_curve": h_price_from_curve,
    "bond.spread.z": h_z_spread,
    "rates.curve.discount": h_curve_discount,
    "rates.cap.price": h_cap,
    "bond.spread.asset_swap": h_asset_swap,
    "bond.frn.price": h_frn,
    "bond.futures.conversion_factor": h_conversion_factor,
    "bond.futures.basis": h_futures_basis,
    "fx.ndf.pv": h_ndf,
    "infl.linker.price": h_linker,
    "vol.option.price": h_option_price,
    "core.calendar.is_business_day": h_is_bd,
    "core.calendar.add_business_days": h_add_bd,
    "rates.basis.ois_spread": h_ois_spread,
    "credit.index.intrinsic": h_index_intrinsic,
    "credit.curve.composite": h_composite,
    "rates.swaption.price": h_swaption,
    "credit.cds.price": h_cds,
    "rates.csa.discount": h_csa_fx,
    "fx.xccy.pv": h_xccy_pv,
    "fx.xccy.bootstrap": h_xccy_boot,
    "rates.futures.convexity": h_futures_convexity,
    "repo.forward": h_repo_forward,
    "repo.implied_rate": h_repo_implied,
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
            except RuntimeError as e:  # QuantLib refused the inputs (for example a fixing on a day its calendar closes)
                ok, why, worst = False, f"QuantLib refused: {e}", None
            if ok:
                row = {"case_id": c["case_id"], "operation": c["operation"], "library": CM.LIBRARY, "version": CM.VERSION,
                       "convention_rows": sorted(u.rows), "map_review": CM.REVIEW}
                note = spec_closed(c)
                if note:
                    row["evidence_class"], row["evidence_note"] = "reimplementation", note
                else:
                    n_ok += 1  # agreement on a spec-closed output is recorded but not counted (H-19 honesty pass)
                reg.append(row)
                # The raw worst gap is not stored: near 1e-16 it differs between libm builds
                # (Windows against Linux CI), which made the committed register non-reproducible.
            elif show:
                print(f"  not verified {c['case_id']} {c['operation']}: {why}")
        table.append((suite, n_ok, len(cases)))
    return reg, table


NO_ORACLE = {
    "bondfit_d": "Nelson-Siegel fit judged on repricing; QuantLib's FittedBondDiscountCurve fits by its own optimiser path, so it cannot reproduce a golden independently of iteration path",
    "commodity_d": "no QuantLib object for monthly log-linear commodity forwards with additive seasonality or for storage carry",
    "csa_d": "CSA without FX and OIS basis spreads count; CSA with FX (QuantLib curve times the spec identity spot / F(d)) agrees but is reimplementation and does not count; the joint bootstrap's term-rate (USD-TERM-3M) helpers are not mapped to QuantLib objects yet; the rest are error cases",
    "credit_d": "credit_d-0002 not counted: QuantLib IsdaCdsEngine reprices the golden 5Y pillar to 1.95e-10 in spread, above the 1e-10 reprice bar. Cause (found 2026-11-18): the 5Y maturity 2031-12-20 is a Saturday, and for that contract QuantLib reads the hazard on (2031-12-20, 2031-12-21], one day past the pillar, which in the full curve is the 7Y segment; the spec bootstrap solves the 5Y pillar before the 7Y hazard exists. The gap is exactly linear in the hazard jump at the pillar (zero with no later pillar or with the 5Y node moved one day later) and of the size of one day of accrual on default; credit_d-0002 has the largest jump times spread (recovery 0.25, steep curve), so the R6-25 figure of about 1e-11 holds for the other cases (5e-12 to 1.5e-11) but not here. Golden unchanged; whether the pillar belongs at maturity (ruling D20) or one day later is a spec question; the rest are error cases",
    "equity_d": "QuantLib has no implied-dividend, implied-borrow or equity futures-basis object; its dividend handling uses other conventions",
    "fits_d": "smooth and robust curve fits are internal estimators (penalised and Huber); no QuantLib equivalent",
    "index_d": "index dividends, rebalancing and corporate actions have no QuantLib object",
    "inflation_d": "linkers from a real yield agree with QuantLib CPI.laggedFixing and BondFunctions but the index-ratio products are the spec's arithmetic, so they do not count; the CPI curve, ZCIS and linker-from-curve cases use the spec's own log-linear CPI curve with seasonality, which QuantLib's inflation curves (other interpolation and lag conventions) cannot express",
    "mbs_d": "QuantLib has no agency MBS pool cash-flow model",
    "rulings_d": "internal: spec rulings, mostly error and order cases",
    "rulings2_d": "internal: spec rulings, mostly error and order cases",
    "rulings_r1": "conversion factors count (QuantLib bond priced at 6% on the CME synthetic dates); the rest are spec-ruling error cases",
    "steps_d": "meeting-date step fits are internal; QuantLib ForwardCurve could replay a step curve but not the fit",
    "trs_d": "QuantLib has no equity total return swap with these legs",
    "xccy_d": "PV and bootstrap count via QuantLib OvernightLeg; NDF agrees with QuantLib discount factors but the forward and payoff are the spec's arithmetic, so it does not count; the rest are error cases",
}


def write_map():
    import inspect
    import re
    L = ["# Convention map for outside-oracle checks", "",
         "Plan rule 11.2.5: a stage D case counts as \"outside oracle\" only if the QuantLib call uses QuantLib's own convention objects, and the mapping from a "
         "QuantForge spec convention to those objects lives in a separate, reviewed table. This is that table, written from `oracle/python/qf_oracle/convmap.py` "
         "by `outside_d.py --write-map`; `outside_d.py` takes every library convention from it and fails if a row here is missing.", "",
         f"Library: QuantLib {CM.VERSION} (Python wheel, pinned in `oracle/python/uv.lock`). The version is recorded on every counted case in `oracle/outside_register.json`.", "",
         f"Review: {CM.REVIEW}. The spec session read each spec section and the QuantLib documentation or source for the object and found them equal. "
         "That is self-assessment, not an outside review. A row's review must be redone when its spec section or the QuantLib version changes.", "",
         "| Row | Spec | QuantLib object | Note |", "|---|---|---|---|"]
    for k, (spec, fn, nt) in CM.ROWS.items():
        src = inspect.getsource(fn).strip()
        m = re.search(r"lambda[^:]*:\s*(.*)", src)
        body = (m.group(1).rstrip(" ),") if m else src).replace("|", "\\|")
        body = body if len(body) <= 110 else body[:107] + "..."
        L.append(f"| `{k}` | {spec} | `{body}` | {nt} |")
    L += ["", "## Known mapping points", "",
          "- `CMPD.METHOD`: QuantLib's `lockoutDays = k` locks the last k+1 rates; the ARRC lockout in `02-curves/overnight-compounding.md` locks k, so the map passes k-1.",
          "- `ISDA.FALLBACK`: the spread adjustments are published constants (fixed 2021-03-05), not QuantLib values. A fallback case counts because its compounded rate comes from QuantLib.",
          "- `credit.cds.bootstrap` is counted by a reprice check: QuantLib's `cdsMaturity` gives the pillar dates, and the golden survivals priced in QuantLib's ISDA engine return each quoted spread within 1e-10.",
          "- `credit.cds.bootstrap` at a Saturday maturity with a later pillar: QuantLib's ISDA engine reads the hazard one day past the pillar (the next segment), the spec's sequential bootstrap cannot; the reprice gap is linear in the hazard jump (credit_d-0002: 1.95e-10, not counted; other cases 5e-12 to 1.5e-11). See the `credit_d` row in `oracle/REPORT.md`.",
          "- `rates.ois.pv`: the strings in `valuation` are identities of the inputs and the spec's fixed strings; only the numbers come from QuantLib.",
          "- `repo.*`: QuantLib gives the bond's cash flows, accrued and the simple ACT/360 growth factors; the forward-price identity is the spec's own algebra on those objects.",
          "- H-19 (2026-11-18), what is library and what is the spec's arithmetic:",
          "  - `bond.spread.asset_swap`: P_curve from QuantLib's bond engine and the annuity as QuantLib's NPV of a unit ACT/360 leg on the spec's floating schedule; the spread is arithmetic.",
          "  - `bond.frn.price`: QuantLib IborLeg (par coupons) on the projection curve, discount margin as a continuous zero spread; fully library.",
          "  - `bond.futures.conversion_factor`: QuantLib clean price at 6% of a bond on the CME synthetic dates (row `CF.CME_SYNTHETIC`); coupon rounding to 1/8, the month count and the 4-decimal rounding are arithmetic.",
          "  - `bond.futures.basis`: accrued, coupons and ACT/360 growth from QuantLib; invoice, bases and implied repo are the spec's algebra.",
          "  - `fx.ndf.pv`: discount factors from QuantLib curves; covered-parity forward and payoff value are arithmetic (QuantLib has no NDF object).",
          "  - `infl.linker.price`: Ref CPI from QuantLib CPI.laggedFixing, real prices from BondFunctions; Treasury rounding and index-ratio products are arithmetic.",
          "  - `rates.csa.discount` with FX: QuantLib ZeroSpreadedTermStructure times the input identity spot / F(d).",
          "  - `credit.index.intrinsic`: per-name upfronts from QuantLib IsdaCdsEngine; the weighted mean is arithmetic. `credit.curve.composite`: weighted spreads, then the bootstrap reprice check.",
          "  - Counting (honesty pass, 2026-11-18, R6-13 rule D6): where the spec's own formula finishes the compared output (asset swap, futures basis, NDF, linker, CSA with FX, index intrinsic, composite curve), the case agrees with QuantLib but is recorded as `reimplementation` in `oracle/outside_register.json` and does not count. FRN, Black-76, calendars, conversion factors (a rounded QuantLib clean price) and OIS spreads (a difference of two QuantLib fair rates) count.",
          "  - `vol.option.price`: QuantLib blackFormula. `core.calendar.*`: QuantLib UnitedStates(GovernmentBond); it agrees with ruling R1-6 on the 2023 and 2026 Good Friday early closes. `rates.basis.ois_spread`: difference of QuantLib MakeOIS fair rates.",
          "- Strata and the ISDA C library are not used for stage D counting yet.", ""]
    (ROOT / "oracle" / "CONVENTION_MAP.md").write_text("\n".join(L), encoding="utf-8", newline="\n")


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
    out[-2] = "| Suite | Outside-oracle cases | Cases | Share | Why not more |"
    out[-1] = "|---|---|---|---|---|"
    out += [f"| `{s}` | {k} | {n} | {100 * k / n:.0f}% | {NO_ORACLE.get(s, '')} |" for s, k, n in table]
    out += [f"| **stage D** | **{tot_ok}** | **{tot}** | **{100 * tot_ok / tot:.1f}%** | |", "",
            "Caveat: most counted cases are fixed-rate bonds (suite `outside_d`), so the stage-wide share leans on one product family. "
            "Several H-19 handlers (asset swap, futures basis, NDF, linker, CSA with FX, index intrinsic, composite curve) build the instrument "
            "from QuantLib objects but apply the spec's own closing algebra; those 19 cases agree but are `reimplementation` and are not counted here "
            "(`oracle/CONVENTION_MAP.md` lists which part is library and which arithmetic).", ""]
    (ROOT / "oracle" / "outside_register.json").write_text(json.dumps({"rule": "plan 11.2.5", "library": CM.LIBRARY, "version": CM.VERSION,
                                                                       "map_review": CM.REVIEW, "cases": reg}, indent=1) + "\n", encoding="utf-8", newline="\n")
    return out, tot_ok, tot


# H-19 honesty pass (2026-11-18, R6-13 rule D6): where QuantLib builds the instrument but the spec's own formula
# finishes the compared output, the case agrees with QuantLib but is a `reimplementation`, which does not count
# toward the outside share. Fully library outputs (FRN, Black-76, calendars, CME conversion factor = rounded
# QuantLib clean price, OIS spread = difference of two QuantLib fair rates) still count. `repo.*` predates this pass
# and keeps its class under the earlier map review.
SPEC_CLOSED = {
    "bond.spread.asset_swap": "QuantLib bond engine price and unit-leg annuity; the spread (P_curve - P_market) / annuity is the spec formula",
    "bond.futures.basis": "QuantLib accrued, coupons and ACT/360 growth; invoice, bases and implied repo are the spec algebra",
    "fx.ndf.pv": "QuantLib discount factors; covered-parity forward and payoff value are the spec formula (QuantLib has no NDF object)",
    "infl.linker.price": "QuantLib reference CPI and real price; Treasury rounding and index-ratio products are the spec arithmetic",
    "credit.index.intrinsic": "QuantLib IsdaCdsEngine per-name upfronts; the weighted mean is the spec formula",
    "credit.curve.composite": "spec weighting of the name spreads, then a QuantLib bootstrap reprice of the weighted spreads",
}


def spec_closed(c):
    op = c["operation"]
    if op == "rates.csa.discount" and c["inputs"].get("fx"):
        why = "QuantLib spreaded curve times the spec identity spot / F(d)"
    else:
        why = SPEC_CLOSED.get(op)
    return "H-19 honesty pass 2026-11-18 (R6-13: spec formula around library values does not count): " + why if why else None


def main():
    if "--write-map" in sys.argv:
        write_map()
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
