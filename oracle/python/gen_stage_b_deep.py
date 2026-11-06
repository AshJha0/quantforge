"""Deeper stage B cases, with outside checks, and mutants: each suite must catch a plausible convention error.

A mutant recomputes a golden with one deliberate mistake. The run stops if the suite's tolerance would not catch it.
All market data is synthetic.
"""
import copy
import json
import math
import os
import random
import subprocess
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import QuantLib as ql
from scipy.optimize import minimize

import gen_stage_b as b
from gen_stage_b import AS_OF, DFLIM, E, I, PVLIM, Q, SONIA_Q, SOFR_Q, SYN, S, jcurve, jq, qper, write
from qf_oracle import rates
from qf_oracle.common import note
from qf_oracle.dates import is_business, yf
from qf_oracle.rates import CONV, Curve, add_bd, add_months, adjust, bootstrap_ois, ois_legs, ois_periods, schedule

STRATA = Path(__file__).parent.parent / "strata"
MUTANTS = []
SAT = date(2026, 11, 7)
NEG = [(t, r - .05) for t, r in SONIA_Q]
STEEP = [(t, .01 + .004 * i) for i, (t, _) in enumerate(SONIA_Q)]


def caught(suite, name, gap, tol):
    assert gap > tol, f"{suite}: mutant '{name}' is not caught: gap {gap:.3e}, tolerance {tol:.3e}"
    MUTANTS.append((suite, name, gap))


def strata(lines):
    src, dst = STRATA / "out" / "rates-in.tsv", STRATA / "out" / "rates-out.tsv"
    src.write_text("\n".join(lines) + "\n", newline="\n")
    java = Path(os.environ.get("JAVA25_HOME", r"C:\Program Files\Eclipse Adoptium\jdk-25.0.5.8-hotspot")) / "bin" / "java"
    subprocess.run([str(java), "-cp", "target/classes;" + (STRATA / "cp.txt").read_text(), "org.quantforge.oracle.StrataRates", "out/rates-in.tsv", "out/rates-out.tsv"], cwd=STRATA, check=True)
    return [x.split("\t") for x in dst.read_text().splitlines()]


def schedules():
    s = S("schedule_deep", "02-curves/schedules.md")
    qc = {"GBLO": ql.UnitedKingdom(ql.UnitedKingdom.Settlement), "EUTA": ql.TARGET()}
    rows = []
    for cal in qc:
        for st in (date(2026, 11, 6), date(2026, 12, 24), date(2027, 1, 29), date(2027, 3, 24), date(2028, 2, 29), date(2026, 8, 28)):
            for m, span, lag in ((1, 7, 0), (3, 26, 2), (6, 41, 0), (12, 61, 1)):
                if is_business(cal, st):
                    rows.append((cal, st, add_months(st, span), m, lag))
    lines = [f"SCHED\t{st}\t{en}\t{m}\t{cal}" for cal, st, en, m, _ in rows]
    back = strata(lines)
    fwd_gap = fol_gap = 0
    n_strata = 0
    for (cal, st, en, m, lag), r in zip(rows, back):
        q = [d.ISO() for d in ql.Schedule(Q(st), Q(en), ql.Period(m, ql.Months), qc[cal], ql.ModifiedFollowing, ql.ModifiedFollowing, ql.DateGeneration.Backward, False)]
        got = schedule(cal, st, en, m)
        assert [str(x) for x in got] == q, (cal, st, en, m)
        ver = ["quantlib-1.44"]
        if r[-1].split(",") == q:
            ver.append("strata-2.12.78")
            n_strata += 1
        per = [{"start": str(x), "end": str(y), "payment": str(add_bd(cal, y, lag))} for x, y in zip(got, got[1:])]
        s.add("rates.schedule.generate", {"start": str(st), "end": str(en), "frequency_months": m, "calendar": cal, "end_of_month": False, "payment_lag": lag}, {"periods": per}, cls=E, verified=ver, tags=["stub", "holiday"])
        f = [d.ISO() for d in ql.Schedule(Q(st), Q(en), ql.Period(m, ql.Months), qc[cal], ql.ModifiedFollowing, ql.ModifiedFollowing, ql.DateGeneration.Forward, False)]
        fol = [d.ISO() for d in ql.Schedule(Q(st), Q(en), ql.Period(m, ql.Months), qc[cal], ql.Following, ql.Following, ql.DateGeneration.Backward, False)]
        fwd_gap += f != q
        fol_gap += fol != q
    note(f"schedule_deep: {len(rows)} cases against QuantLib, {n_strata} also equal to Strata PeriodicSchedule")
    caught("schedule_deep", "generate forward, stub last", fwd_gap, 0)
    caught("schedule_deep", "FOLLOWING in place of MODIFIED_FOLLOWING", fol_gap, 0)
    write(s)


def curves():
    s = S("curve_deep", "02-curves/curve-framework.md")
    ql.Settings.instance().evaluationDate = Q(AS_OF)
    sets = [([date(2027, 11, 8), date(2031, 11, 6), date(2036, 11, 6)], [0.965, 0.84, 0.70]), ([date(2027, 11, 8), date(2031, 11, 6)], [1.004, 1.03]), ([date(2029, 3, 1)], [0.9]),
            ([date(2026, 11, 13), date(2026, 12, 8), date(2027, 2, 8)], [0.9993, 0.997, 0.9905])]
    gaps = [0.0, 0.0, 0.0]
    for dates, dfs in sets:
        qd = [AS_OF + timedelta(k) for k in (1, 30, 200, 700, 1800, 4000, 7000)]
        for ip in ("LOG_LINEAR_DF", "LINEAR_ZERO"):
            c = Curve(AS_OF, dates, dfs, ip)
            ver = ["hand"]
            if ip == "LOG_LINEAR_DF":
                q = ql.DiscountCurve([Q(AS_OF)] + [Q(d) for d in dates], [1.0] + dfs, ql.Actual365Fixed())
                q.enableExtrapolation()
                assert max(abs(q.discount(Q(d)) - c.df(d)) for d in qd) < 1e-13
                ver.append("quantlib-1.44")
            else:
                z = [-math.log(v) / t for v, t in zip(dfs, c.t[1:])]
                q = ql.ZeroCurve([Q(AS_OF)] + [Q(d) for d in dates], [z[0]] + z, ql.Actual365Fixed(), ql.NullCalendar(), ql.Linear(), ql.Continuous)
                ins = [d for d in qd if d <= dates[-1]]
                assert max(abs(q.discount(Q(d)) - c.df(d)) for d in ins) < 1e-13
                ver.append("quantlib-1.44")
            v = [c.df(d) for d in qd]
            t = [(d - AS_OF).days / 365 for d in qd]
            zr = [-math.log(x) / y for x, y in zip(v, t)]
            s.add("rates.curve.discount", {"curve": jcurve(c, dates, dfs), "dates": [str(d) for d in qd]}, {"discount_factors": v, "zero_rates": zr}, cls=I, verified=ver, tags=["negative-rates"] if dfs[0] > 1 else [])
            gaps[0] = max(gaps[0], max(abs(a * 365 / 360 - a) for a in zr))
            if ip == "LOG_LINEAR_DF" and len(dates) > 1:
                lin = float(np.interp(t[3], c.t, c.d))
                gaps[1] = max(gaps[1], abs(lin - v[3]))
            flat = math.exp(math.log(dfs[-1]) / c.t[-1] * t[-1])
            gaps[2] = max(gaps[2], abs(flat - v[-1]))
    caught("curve_deep", "ACT/360 curve time", gaps[0], 1e-8)
    caught("curve_deep", "linear in discount factor", gaps[1], 1e-8)
    caught("curve_deep", "flat zero rate beyond the last pillar", gaps[2], 1e-8)
    write(s)


def pillars(per, dfs):
    return [{"date": str(p[-1][2]), "discount_factor": v} for p, v in zip(per, dfs)]


def ois():
    s = S("ois_deep", "02-curves/ois-curves.md")
    op = "rates.ois.bootstrap"
    runs = [(c, a, q, ip) for c, q0 in (("SONIA", SONIA_Q), ("SOFR", SOFR_Q)) for a in (SAT, date(2026, 12, 24), date(2027, 3, 25), date(2027, 2, 26)) for q, ip in ((q0, "LOG_LINEAR_DF"),)]
    runs += [(c, AS_OF, q, ip) for c in ("SONIA", "SOFR") for q in (NEG, STEEP) for ip in ("LOG_LINEAR_DF", "LINEAR_ZERO")]
    for conv, as_of, quotes, ip in runs:
        cv, dfs, per = bootstrap_ois(conv, as_of, quotes, ip)
        q = b.ql_ois(conv, as_of, quotes, ip)
        worst = max(abs(q.discount(Q(p[-1][2])) - v) for p, v in zip(per, dfs))
        assert worst < 2e-11, (conv, as_of, ip, worst)
        s.add(op, {"convention": conv, "as_of": str(as_of), "quotes": jq(quotes), "interpolation": ip, "method": "GLOBAL"}, {"pillars": pillars(per, dfs)}, cls=I, verified=["independent-replay", "quantlib-1.44"], tags=[SYN], limit=DFLIM)
    # Second build of swap PVs, through Strata's own pricer, on the same curve.
    lines, keep = [], []
    for conv, quotes in (("SONIA", SONIA_Q), ("SOFR", SOFR_Q), ("SONIA", NEG), ("SOFR", NEG), ("SOFR", STEEP)):
        cv, dfs, per = bootstrap_ois(conv, AS_OF, quotes)
        pil = [p[-1][2] for p in per]
        nodes = ",".join(f"{d}:{v!r}" for d, v in zip(pil, dfs))
        for tenor, k, side in (("2Y", .03, "PAY"), ("5Y", .034, "RECEIVE"), ("10Y", .036, "PAY"), ("30Y", .037, "RECEIVE")):
            N = 1e6
            p = ois_periods(conv, AS_OF, tenor)
            a, fl = ois_legs(conv, p, cv)
            val = (1 if side == "PAY" else -1) * N * (fl - k * a)
            lines.append(f"OIS\t{conv}\t{AS_OF}\t{tenor}\t{k}\t{N}\t{side}\t{nodes}")
            keep.append((conv, tenor, k, side, val, jcurve(cv, pil, dfs), fl / a, a))
    out = strata(lines)
    worst = 0.0
    for r, (conv, tenor, k, side, val, jc, par, a) in zip(out, keep):
        worst = max(worst, abs(float(r[-1]) - val))
        s.add("rates.ois.pv", {"curve": jc, "trade": {"convention": conv, "tenor": tenor, "fixed_rate": k, "notional": 1e6, "side": side}},
              {"valuation": {"pv": val, "currency": CONV[conv]["currency"], "model": "OIS_DISCOUNTING", "data_version": None, "conventions": conv, "as_of": str(AS_OF)}, "par_rate": par, "annuity": a}, cls=I, verified=["independent-replay", "strata-2.12.78"], tags=[SYN], limit=PVLIM)
    note(f"ois_deep: {len(keep)} swap PVs against Strata's pricer on 1e6, worst difference {worst:.3e}")
    assert worst < 1.0
    # Mutants, on SOFR, whose lags make the errors visible.
    cv, dfs, per = bootstrap_ois("SOFR", AS_OF, SOFR_Q)
    pil = [p[-1][2] for p in per]
    keep_c = copy.deepcopy(CONV["SOFR"])
    for name, key, v in (("payment lag ignored", "payment_lag", 0), ("spot lag ignored", "spot_lag", 0), ("ACT_365F on the fixed leg", "fixed_day_count", "ACT_365F")):
        CONV["SOFR"][key] = v
        m = bootstrap_ois("SOFR", AS_OF, SOFR_Q)[0]
        CONV["SOFR"].update(keep_c)
        caught("ois_deep", name, max(abs(m.df(d) - x) for d, x in zip(pil, dfs)), 1e-9)
    caught("ois_deep", "FOLLOWING before counting the spot lag", abs((add_bd("USGS", SAT, 2) - add_bd("USGS", adjust("USGS", SAT, "FOLLOWING"), 2)).days), 0)
    p = ois_periods("SOFR", AS_OF, "10Y")
    caught("ois_deep", "telescoped floating leg under a payment lag", abs(ois_legs("SOFR", p, cv)[1] - (cv.df(p[0][0]) - cv.df(p[-1][1]))) * 1e6, 1e-3)
    write(s)


def projection():
    s = S("projection_deep", "02-curves/projection-and-fra.md")
    op = "rates.projection.bootstrap"
    pq = b.proj_quotes()
    negq = [{**q, "rate": q["rate"] - .05} for q in pq]
    for as_of, quotes, disc in ((date(2026, 11, 9), pq, SOFR_Q), (date(2026, 11, 25), pq, SOFR_Q), (date(2026, 12, 23), pq, SOFR_Q), (AS_OF, negq, NEG)):
        ql.Settings.instance().evaluationDate = Q(as_of)
        cv, dfs, per = bootstrap_ois("SOFR", as_of, disc)
        jc = jcurve(cv, [p[-1][2] for p in per], dfs)
        h = ql.YieldTermStructureHandle(b.ql_ois("SOFR", as_of, disc, "LOG_LINEAR_DF"))
        idx = b.ql_term()
        hs = []
        for q in quotes:
            qq = ql.QuoteHandle(ql.SimpleQuote(q["rate"]))
            hs.append(ql.DepositRateHelper(qq, idx) if q["type"] == "DEPOSIT" else ql.FraRateHelper(qq, q["start_months"], idx) if q["type"] == "FRA" else
                      ql.SwapRateHelper(qq, ql.Period(q["months"], ql.Months), idx.fixingCalendar(), ql.Annual, ql.ModifiedFollowing, ql.Thirty360(ql.Thirty360.BondBasis), idx, ql.QuoteHandle(), ql.Period(0, ql.Days), h))
        qp = ql.PiecewiseLogLinearDiscount(Q(as_of), hs, ql.Actual365Fixed())
        qp.enableExtrapolation()
        pc, pd, pp = b.bootstrap_proj(cv, as_of, quotes, "LOG_LINEAR_DF")
        err = max(abs(qp.discount(Q(d)) - v) for d, v in zip(pp, pd))
        assert err < 1e-10, (as_of, err)
        s.add(op, {"discount": jc, "index": "USD-TERM-3M", "as_of": str(as_of), "quotes": quotes, "interpolation": "LOG_LINEAR_DF"}, {"pillars": [{"date": str(d), "discount_factor": v} for d, v in zip(pp, pd)]},
              cls=I, verified=["independent-replay", "quantlib-1.44"], tags=[SYN], limit=DFLIM)
        jp = jcurve(pc, pp, pd)
        idx2 = idx.clone(ql.YieldTermStructureHandle(qp))
        for yrs, k, side in ((2, .034, "PAY"), (5, .036, "RECEIVE"), (10, .037, "PAY")):
            ann, flt = b.swap_legs(cv, pc, as_of, yrs * 12)
            v = (1 if side == "PAY" else -1) * 1e6 * (flt - k * ann)
            sw = ql.MakeVanillaSwap(ql.Period(yrs, ql.Years), idx2, k, ql.Period(0, ql.Days), nominal=1e6, fixedLegTenor=ql.Period(1, ql.Years), fixedLegDayCount=ql.Thirty360(ql.Thirty360.BondBasis),
                                    swapType=ql.Swap.Payer if side == "PAY" else ql.Swap.Receiver, pricingEngine=ql.DiscountingSwapEngine(h))
            assert abs(sw.NPV() - v) < 1e-2, (as_of, yrs, sw.NPV(), v)
            s.add("rates.swap.pv", {"discount": jc, "projection": jp, "trade": {"index": "USD-TERM-3M", "tenor_months": yrs * 12, "fixed_rate": k, "notional": 1e6, "side": side}},
                  {"valuation": {"pv": v, "currency": "USD", "model": "SWAP_DISCOUNTING", "data_version": None, "conventions": "USD-TERM-3M", "as_of": str(as_of)}, "par_rate": flt / ann}, cls=I, verified=["independent-replay", "quantlib-1.44"], tags=[SYN], limit=PVLIM)
        if as_of == AS_OF:
            continue
        a = adjust("USGS", add_months(add_bd("USGS", as_of, 2), 3))
        e = adjust("USGS", add_months(a, 3))
        al = float(yf("ACT_360", a, e))
        F = (pc.df(a) / pc.df(e) - 1) / al
        v = 1e6 * al * (F - .0385) / (1 + al * F) * cv.df(a)
        fra = ql.ForwardRateAgreement(idx2, Q(a), ql.Position.Long, .0385, 1e6, h)
        assert abs(fra.NPV() - v) < 1e-2, (fra.NPV(), v)
        s.add("rates.fra.pv", {"discount": jc, "projection": jp, "trade": {"index": "USD-TERM-3M", "start": str(a), "fixed_rate": .0385, "notional": 1e6, "side": "PAY"}},
              {"valuation": {"pv": v, "currency": "USD", "model": "FRA_DISCOUNTING", "data_version": None, "conventions": "USD-TERM-3M", "as_of": str(as_of)}, "forward_rate": F}, cls=I, verified=["independent-replay", "quantlib-1.44"], tags=[SYN], limit=PVLIM)
    note("projection_deep: pillars, swaps and FRAs match QuantLib, including month-end spot, a holiday in the spot lag and negative rates")
    cv, dfs, per = bootstrap_ois("SOFR", AS_OF, SOFR_Q)
    pc, pd, pp = b.bootstrap_proj(cv, AS_OF, pq, "LOG_LINEAR_DF")
    ann, flt = b.swap_legs(cv, pc, AS_OF, 60)
    a1, f1 = b.swap_legs(pc, pc, AS_OF, 60)
    caught("projection_deep", "discounting on the projection curve", abs((flt - .036 * ann) - (f1 - .036 * a1)) * 1e6, 1e-3)
    keep = b.TERM["fixed_day_count"]
    b.TERM["fixed_day_count"] = "ACT_360"
    pm = b.bootstrap_proj(cv, AS_OF, pq, "LOG_LINEAR_DF")[1]
    b.TERM["fixed_day_count"] = keep
    caught("projection_deep", "ACT_360 on the fixed leg", max(abs(x - y) for x, y in zip(pm, pd)), 1e-9)
    a = date(2027, 2, 10)
    e = date(2027, 5, 10)
    al = float(yf("ACT_360", a, e))
    F = (pc.df(a) / pc.df(e) - 1) / al
    caught("projection_deep", "FRA without the settlement discount", abs(1e6 * al * (F - .03) * (1 - 1 / (1 + al * F))), 1e-3)
    write(s)


def ql_dv01(conv, as_of, quotes, ip, tr):
    ql.Settings.instance().evaluationDate = Q(as_of)
    c = CONV[conv]
    sq = [ql.SimpleQuote(r) for _, r in quotes]
    hs = [ql.OISRateHelper(c["spot_lag"], qper(t), ql.QuoteHandle(x), b.qindex(conv), ql.YieldTermStructureHandle(), True, c["payment_lag"]) for (t, _), x in zip(quotes, sq)]
    k = ql.PiecewiseLogLinearDiscount if ip == "LOG_LINEAR_DF" else ql.PiecewiseLinearZero
    crv = k(Q(as_of), hs, ql.Actual365Fixed())
    crv.enableExtrapolation()
    h = ql.YieldTermStructureHandle(crv)
    i0 = b.qindex(conv)
    ix = ql.OvernightIndex(i0.name(), 0, i0.currency(), i0.fixingCalendar(), i0.dayCounter(), h)
    sw = ql.MakeOIS(qper(tr["tenor"]), ix, tr["fixed_rate"], settlementDays=c["spot_lag"], paymentLag=c["payment_lag"], nominal=tr["notional"], swapType=ql.Swap.Payer if tr["side"] == "PAY" else ql.Swap.Receiver,
                    pricingEngine=ql.DiscountingSwapEngine(h), telescopicValueDates=True)
    base = [x.value() for x in sq]

    def bump(ix_, d):
        for j in ix_:
            sq[j].setValue(base[j] + d)
        v = sw.NPV()
        for j in ix_:
            sq[j].setValue(base[j])
        return v
    al = range(len(sq))
    return (bump(al, 1e-4) - bump(al, -1e-4)) / 2, [(bump([j], 1e-4) - bump([j], -1e-4)) / 2 for j in al], bump(al, 1e-4), bump(al, 0.0)


def risk():
    s = S("risk_deep", "06-risk/rates-sensitivities.md")
    RL = {"absolute": 1e-3, "relative": 1e-8, "reason": "difference of two curve solves on 1e6"}
    worst = 0.0
    runs = [("SONIA", AS_OF, SONIA_Q, "LOG_LINEAR_DF", "5Y", "PAY"), ("SOFR", AS_OF, SOFR_Q, "LOG_LINEAR_DF", "10Y", "RECEIVE"), ("SONIA", AS_OF, NEG, "LOG_LINEAR_DF", "7Y", "PAY"), ("SONIA", AS_OF, SONIA_Q, "LINEAR_ZERO", "6Y", "PAY"),
            ("SOFR", SAT, SOFR_Q, "LOG_LINEAR_DF", "3Y", "PAY"), ("SOFR", AS_OF, STEEP, "LINEAR_ZERO", "20Y", "RECEIVE")]
    for conv, as_of, q, ip, ten, side in runs:
        tr = {"convention": conv, "tenor": ten, "fixed_rate": .034, "notional": 1e6, "side": side}
        par, keys = b.dv01_replay(conv, q, ip, tr, as_of)
        qp, qk, up, base = ql_dv01(conv, as_of, q, ip, tr)
        worst = max([worst, abs(par - qp)] + [abs(x - y) for x, y in zip(keys, qk)])
        s.add("risk.ois.dv01", {"as_of": str(as_of), "quotes": jq(q), "interpolation": ip, "trade": tr}, {"dv01": par, "key_rate": keys}, cls=I, verified=["independent-replay", "quantlib-1.44"], tags=[SYN], limit=RL)
    note(f"risk_deep: DV01 and every key rate against bumped QuantLib quotes, worst difference {worst:.3e} on 1e6")
    assert worst < 1e-3
    caught("risk_deep", "one-sided bump", abs((up - base) - qp), 1e-3)
    caught("risk_deep", "bump of 1 bp reported per 100 bp", abs(par) * 99, 1e-3)
    caught("risk_deep", "sign flipped", 2 * abs(par), 1e-3)
    write(s)


def fx():
    s = S("fx_deep", "02-curves/fx.md")
    gc, gd, gp = bootstrap_ois("SONIA", AS_OF, SONIA_Q)
    uc, ud, up = bootstrap_ois("SOFR", AS_OF, SOFR_Q)
    nc, nd, npe = bootstrap_ois("SONIA", AS_OF, NEG)
    jg, ju, jn = jcurve(gc, [p[-1][2] for p in gp], gd), jcurve(uc, [p[-1][2] for p in up], ud), jcurve(nc, [p[-1][2] for p in npe], nd)
    qcal = {"GBPUSD": ql.JointCalendar(ql.UnitedKingdom(ql.UnitedKingdom.Settlement), ql.UnitedStates(ql.UnitedStates.GovernmentBond), ql.JoinHolidays),
            "EURUSD": ql.JointCalendar(ql.TARGET(), ql.UnitedStates(ql.UnitedStates.GovernmentBond), ql.JoinHolidays)}
    cals = {"GBPUSD": ("GBLO", "USGS"), "EURUSD": ("EUTA", "USGS")}

    def sd(pair, d):
        n = 0
        while n < 2:
            d += timedelta(1)
            n += all(is_business(c, d) for c in cals[pair])
        return d
    single = 0
    for pair in cals:
        for d in (date(2026, 12, 23), date(2026, 12, 24), date(2027, 3, 24), date(2027, 3, 25), date(2027, 4, 29), date(2026, 11, 25), date(2027, 5, 27), date(2026, 8, 27)):
            r = sd(pair, d)
            assert qcal[pair].advance(Q(d), 2, ql.Days).ISO() == str(r)
            s.add("fx.spot_date", {"pair": pair, "trade_date": str(d)}, {"spot_date": str(r)}, cls=E, verified=["quantlib-1.44"], tags=["holiday"])
            single += add_bd(cals[pair][0], d, 2) != r
    caught("fx_deep", "spot date on one calendar", single, 0)
    S0 = 1.28
    sp = sd("GBPUSD", AS_OF)
    ql.Settings.instance().evaluationDate = Q(AS_OF)
    uq = b.ql_ois("SOFR", AS_OF, SOFR_Q, "LOG_LINEAR_DF")
    worst = 0.0
    for base_c, jb, tag in ((gc, jg, []), (nc, jn, ["negative-rates"])):
        base = {"pair": "GBPUSD", "spot": S0, "as_of": str(AS_OF), "base_curve": jb, "quote_curve": ju}
        for T in (date(2026, 12, 10), date(2027, 5, 10), date(2028, 11, 10), date(2036, 11, 10)):
            F = S0 * (base_c.df(T) / base_c.df(sp)) / (uc.df(T) / uc.df(sp))
            s.add("fx.forward.outright", {**base, "value_date": str(T)}, {"forward": F, "points": (F - S0) / 1e-4}, cls=I, verified=["hand"], tags=[SYN] + tag)
            K = 1.27
            pv = 1e6 * (F - K) * uc.df(T)
            s.add("fx.forward.pv", {**base, "trade": {"notional_base": 1e6, "strike": K, "value_date": str(T), "side": "BUY"}},
                  {"valuation": {"pv": pv, "currency": "USD", "model": "FX_FORWARD_DISCOUNTING", "data_version": None, "conventions": "GBPUSD", "as_of": str(AS_OF)}, "fx_delta": 1e6 * (F / S0) * uc.df(T)}, cls=I, verified=["hand"], tags=[SYN] + tag, limit=PVLIM)
    # Outside: QuantLib's FX swap helper builds the base curve from the same forward points.
    pts = [("3M", -18.5), ("6M", -36.0), ("1Y", -71.0), ("2Y", -140.0)]
    h = ql.YieldTermStructureHandle(uq)
    spot_q = ql.QuoteHandle(ql.SimpleQuote(S0))
    helpers = [ql.FxSwapRateHelper(ql.QuoteHandle(ql.SimpleQuote(p * 1e-4)), spot_q, qper(t), 2, qcal["GBPUSD"], ql.ModifiedFollowing, False, False, h) for t, p in pts]
    qc = ql.PiecewiseLogLinearDiscount(Q(AS_OF), helpers, ql.Actual365Fixed())
    qc.enableExtrapolation()
    nodes = []
    for t, p in pts:
        m = int(t[:-1]) * (12 if t[-1] == "Y" else 1)
        T = adjust("GBLO", add_months(sp, m))
        while not all(is_business(c, T) for c in cals["GBPUSD"]):
            T += timedelta(1)
        ratio = ((S0 + p * 1e-4) / S0) * (uc.df(T) / uc.df(sp))
        tau = (T - sp).days / 365
        worst = max(worst, abs(qc.discount(Q(T)) / qc.discount(Q(sp)) - ratio))
        nodes.append({"value_date": str(T), "implied_ratio": ratio, "basis_bp": (-math.log(ratio) / tau + math.log(gc.df(T) / gc.df(sp)) / tau) * 1e4})
    note(f"fx_deep: implied ratios against QuantLib FxSwapRateHelper, worst difference {worst:.3e}")
    assert worst < 1e-9
    s.add("fx.curve.implied", {"pair": "GBPUSD", "spot": S0, "as_of": str(AS_OF), "base_curve": jg, "quote_curve": ju, "points": [{"tenor": t, "points": p} for t, p in pts]}, {"nodes": nodes}, cls=I, verified=["hand", "quantlib-1.44"], tags=[SYN],
          limit={"absolute": 1e-7, "relative": 0.0, "reason": "basis in bp"})
    T = date(2027, 11, 10)
    F = S0 * (gc.df(T) / gc.df(sp)) / (uc.df(T) / uc.df(sp))
    caught("fx_deep", "curves not measured from spot", abs(S0 * gc.df(T) / uc.df(T) - F) * 1e6 * uc.df(T), 1e-3)
    caught("fx_deep", "ratio inverted", abs(S0 * uc.df(T) / gc.df(T) - F), 1e-9)
    caught("fx_deep", "delta left undiscounted", abs(1e6 * (F / S0) * (1 - uc.df(T))), 1e-3)
    write(s)


def scipy_l1(A, c0, w, c, lam):
    A, c0, w, c = map(np.array, (A, c0, w, c))
    n = A.shape[1]

    def f(z):
        x = z[:n] - z[n:]
        r = A @ x + c0
        g = 2 * A.T @ (w * r)
        return (w * r * r).sum() + lam * (c * (z[:n] + z[n:])).sum(), np.r_[g + lam * c, -g + lam * c]
    r = minimize(f, np.zeros(2 * n), jac=True, method="L-BFGS-B", bounds=[(0, None)] * (2 * n), options={"ftol": 1e-15, "gtol": 1e-10, "maxiter": 50000})
    return r.x[:n] - r.x[n:]


def hedge():
    s = S("hedge_deep", "08-hedging/stage-b-hedges.md")
    rnd = random.Random(2026)
    lim = {"absolute": 1e-8, "relative": 0.0, "reason": "the minimiser is unique"}
    worst = 0.0
    gaps = [0.0, 0.0, 0.0]
    for k in range(12):
        m, n = rnd.randint(3, 6), rnd.randint(1, 3)
        A = [[round(rnd.uniform(-2, 2), 3) for _ in range(n)] for _ in range(m)]
        c0 = [round(rnd.uniform(-20, 20), 2) for _ in range(m)]
        w = [round(rnd.uniform(.5, 3), 2) for _ in range(m)]
        c = [round(rnd.uniform(0, 2), 2) for _ in range(n)]
        lam = [0.0, 1.0, 5.0, 20.0][k % 4]
        x, r, o = b.solve_l1(A, c0, w, c, lam)
        worst = max(worst, float(np.abs(scipy_l1(A, c0, w, c, lam) - x).max()))
        s.add("hedge.solve", {"a": A, "b": c0, "weights": w, "costs": c, "lambda": lam}, {"x": [float(v) for v in x], "residual": [float(v) for v in r], "objective": float(o)}, cls=I, verified=["sign-enumeration", "scipy-1.18.1"], limit=lim)
        gaps[0] = max(gaps[0], float(np.abs(b.solve_l1(A, c0, [1.0] * m, c, lam)[0] - x).max()))
        if lam:
            gaps[1] = max(gaps[1], float(np.abs(b.solve_l1(A, c0, w, c, 0.0)[0] - x).max()))
        gaps[2] = max(gaps[2], float(np.abs(b.solve_l1(A, [-v for v in c0], w, c, lam)[0] - x).max()))
    note(f"hedge_deep: exact enumeration against SciPy L-BFGS-B, worst difference {worst:.2e}")
    assert worst < 1e-4
    caught("hedge_deep", "weights ignored", gaps[0], 1e-8)
    caught("hedge_deep", "cost ignored", gaps[1], 1e-8)
    caught("hedge_deep", "sign of b reversed", gaps[2], 1e-8)
    write(s)


def rulings():
    s = S("rulings_b", "stage-b-rulings.md")
    gc, gd, gp = bootstrap_ois("SONIA", AS_OF, SONIA_Q)
    uc, ud, up = bootstrap_ois("SOFR", AS_OF, SOFR_Q)
    jg, ju = jcurve(gc, [p[-1][2] for p in gp], gd), jcurve(uc, [p[-1][2] for p in up], ud)
    base = {"pair": "GBPUSD", "spot": 1.28, "as_of": str(AS_OF), "base_curve": jg, "quote_curve": ju}

    def err(op, inp, code, rule):
        s.add(op, inp, error=code, cls=E, tags=["invalid", rule])

    sc = "rates.schedule.generate"
    s.add(sc, {"start": "2027-02-26", "end": "2027-02-28", "frequency_months": 3, "calendar": "GBLO", "end_of_month": False, "payment_lag": 0}, {"periods": []}, cls=E, verified=["hand"], tags=["B1"])
    sb = {"start": "2026-11-06", "end": "2027-11-08", "frequency_months": 3, "calendar": "GBLO", "end_of_month": False}
    err(sc, {**sb, "payment_lag": -1}, "E_INPUT", "B2")
    err(sc, {**sb, "payment_lag": 30001}, "E_LIMIT", "B2")
    cv = jg
    err("rates.curve.discount", {"curve": {**cv, "pillars": []}, "dates": ["2027-01-01"]}, "E_INPUT", "B3")
    err("rates.curve.forward", {"curve": cv, "start": "2027-01-04", "end": "2027-04-05", "day_count": "ACT_ACT_ICMA"}, "E_SCHEMA", "B4")
    over = {**cv, "pillars": [{"date": str(date(2027, 1, 1) + timedelta(i)), "discount_factor": 0.99} for i in range(101)]}
    err("rates.curve.discount", {"curve": over, "dates": ["2027-01-01"]}, "E_LIMIT", "B5")
    err("fx.forward.outright", {**base, "base_curve": over, "value_date": "2027-02-10"}, "E_LIMIT", "B5")
    err("calib.curve_report", {"convention": "SONIA", "as_of": str(AS_OF), "quotes": [{"tenor": f"{i + 1}M", "rate": .03} for i in range(101)], "interpolation": "LOG_LINEAR_DF"}, "E_LIMIT", "B5")
    err("rates.ois.compound", {"rates": [], "days": [], "denominator": 365}, "E_INPUT", "B6")
    err("rates.ois.compound", {"rates": [.05], "days": [1], "denominator": 364}, "E_SCHEMA", "B6")
    err("fx.curve.implied", {**base, "points": [{"tenor": "1W", "points": -1.0}]}, "E_SCHEMA", "B7")
    err("fx.curve.implied", {**base, "points": [{"tenor": "6M", "points": -1.0}, {"tenor": "3M", "points": -1.0}]}, "E_INPUT", "B7")
    err("fx.forward.outright", {**base, "as_of": "2026-11-09", "value_date": "2027-02-10"}, "E_INPUT", "B8")
    tr = {"notional_base": 1e6, "strike": 1.27, "side": "BUY"}
    err("fx.forward.pv", {**base, "trade": {**tr, "value_date": "2026-11-09"}}, "E_DATE_ORDER", "B9")
    err("fx.swap.pv", {**base, "trade": {"notional_base": 1e6, "near_date": "2027-11-10", "near_rate": 1.28, "far_date": "2027-02-10", "far_rate": 1.27, "far_side": "BUY"}}, "E_DATE_ORDER", "B9")
    T, sp = date(2027, 2, 10), date(2026, 11, 10)
    F = 1.28 * (gc.df(T) / gc.df(sp)) / (uc.df(T) / uc.df(sp))
    sid = "sha256:" + "cd" * 32
    s.add("fx.forward.pv", {**base, "snapshot_id": sid, "trade": {**tr, "value_date": str(T)}}, {"valuation": {"pv": 1e6 * (F - 1.27) * uc.df(T), "currency": "USD", "model": "FX_FORWARD_DISCOUNTING", "data_version": sid, "conventions": "GBPUSD", "as_of": str(AS_OF)}, "fx_delta": 1e6 * (F / 1.28) * uc.df(T)},
          cls=I, verified=["hand"], tags=["B10"], limit=PVLIM)
    X = [1.0, 2.0, 3.0]
    y = [1.0, 2.0, 3.0]
    f = {"model": "LINEAR", "x": X, "y": y, "start": [0.0, 0.0], "method": "LEVENBERG_MARQUARDT"}
    err("calib.fit", {**f, "max_iter": 0}, "E_INPUT", "B11")
    err("calib.fit", {**f, "lower": [1.0, 1.0], "upper": [0.0, 0.0]}, "E_INPUT", "B11")
    err("calib.fit", {**f, "weights": [1.0]}, "E_INPUT", "B11")
    err("calib.fit", {**f, "weights": [-1.0], "prior": [0.0]}, "E_INPUT", "B11")
    s.add("calib.fit", {**f, "start": [5.0, 5.0], "lower": [-1.0, -1.0], "upper": [2.0, 2.0]}, {"parameters": [0.0, 1.0], "objective": 0.0}, cls=I, verified=["hand"], tags=["B11"], limit={"absolute": 1e-6, "relative": 0.0, "reason": "start outside the box is projected"})
    s.add("calib.fit", {"model": "ROSENBROCK", "start": [-1.2, 1.0], "method": "BFGS", "weights": [5.0]}, {"parameters": [1.0, 1.0], "objective": 0.0}, cls=I, verified=["analytic"], tags=["B12"], limit={"absolute": 1e-5, "relative": 0.0, "reason": "x, y left out; weights ignored"})
    hb = {"a": [[1.0, 0.0], [0.0, 1.0]], "b": [1.0, 2.0], "costs": [0.0, 0.0], "lambda": 0.0}
    err("hedge.solve", {**hb, "weights": [0.0, 1.0]}, "E_DOMAIN", "B13")
    err("hedge.solve", {**hb, "a": [[1.0, 0.0], [1.0]], "weights": [1.0, 1.0]}, "E_INPUT", "B13")
    err("hedge.solve", {**hb, "a": [], "b": [], "weights": []}, "E_INPUT", "B13")
    err("hedge.solve", {**hb, "b": [1.0], "weights": [-1.0, 1.0]}, "E_INPUT", "B13")
    tq = {"as_of": str(AS_OF), "quotes": jq(SONIA_Q), "interpolation": "LOG_LINEAR_DF", "trade": {"convention": "SONIA", "tenor": "6Y", "fixed_rate": .034, "notional": 1e7, "side": "PAY"}, "hedge_unit_notional": 1e6, "half_spread_bp": 0.25}
    err("usecase.rates_hedge", {**tq, "hedge_tenors": ["5Y"] * 21}, "E_LIMIT", "B14")
    err("usecase.rates_hedge", {**tq, "hedge_tenors": ["5Y", "5Y"]}, "E_SINGULAR", "B14")
    s.add("core.units.add_money", {"a": {"amount": "999999999999999999", "currency": "USD"}, "b": {"amount": "1", "currency": "USD"}}, {"amount": "1000000000000000000", "currency": "USD"}, cls=E, verified=["hand"], tags=["B15"])
    # B19: FRA start_months.
    cv2, d2, p2 = bootstrap_ois("SOFR", AS_OF, SOFR_Q)
    jd = jcurve(cv2, [p[-1][2] for p in p2], d2)
    pb = {"discount": jd, "index": "USD-TERM-3M", "as_of": str(AS_OF), "interpolation": "LOG_LINEAR_DF"}
    q0 = [{"type": "FRA", "start_months": 0, "rate": .0395}]
    pc, pd, pp = b.bootstrap_proj(cv2, AS_OF, q0, "LOG_LINEAR_DF")
    s.add("rates.projection.bootstrap", {**pb, "quotes": q0}, {"pillars": [{"date": str(d), "discount_factor": v} for d, v in zip(pp, pd)]}, cls=I, verified=["independent-replay"], tags=["B19", SYN], limit=DFLIM)
    err("rates.projection.bootstrap", {**pb, "quotes": [{"type": "FRA", "start_months": -1, "rate": .03}]}, "E_INPUT", "B19")
    err("rates.projection.bootstrap", {**pb, "quotes": [{"type": "FRA", "start_months": 1201, "rate": .03}]}, "E_INPUT", "B19")
    err("rates.projection.bootstrap", {**pb, "quotes": [{"type": "FRA", "start_months": 1200, "rate": .03}]}, "E_DATE_RANGE", "B19")
    err("rates.projection.bootstrap", {**pb, "quotes": [{"type": "SWAP", "months": 1200, "rate": .03}]}, "E_DATE_RANGE", "B19")
    # B20: order of checks in fx.*.
    negc = {**jg, "pillars": [{"date": "2027-11-08", "discount_factor": -0.5}]}
    late = {"value_date": "2026-11-09"}
    err("fx.forward.outright", {**base, **late, "spot": -1.0, "as_of": "2026-11-09"}, "E_DOMAIN", "B20")
    err("fx.forward.outright", {**base, **late, "spot": -1.0, "base_curve": {**jg, "pillars": list(reversed(jg["pillars"]))}}, "E_DOMAIN", "B20")
    err("fx.forward.outright", {**base, **late, "base_curve": negc, "as_of": "2026-11-09"}, "E_DOMAIN", "B20")
    err("fx.forward.outright", {**base, **late, "as_of": "2026-11-09"}, "E_INPUT", "B20")
    # B21: points count as a quote list.
    err("fx.curve.implied", {**base, "points": [{"tenor": f"{i + 1}M", "points": -1.0} for i in range(101)]}, "E_LIMIT", "B21")
    s.add("core.root.newton", {"function": "square", "x0": 0.5, "a": 0.0, "b": 1.0}, {"root": 0.0}, cls="root_finding", verified=["hand"], tags=["B23"],
          limit={"absolute": 1e-9, "relative": 0.0, "reason": "a double root: Newton halves its distance, stopping near x_tol"})
    # B22: a start the objective cannot be evaluated at. These overflow in every correct build.
    rb = {"model": "ROSENBROCK"}
    for meth in ("BFGS", "GAUSS_NEWTON", "LEVENBERG_MARQUARDT"):
        err("calib.fit", {**rb, "start": [-1.2e300, 1.0], "method": meth}, "E_NON_FINITE", "B22")
    err("calib.fit", {"model": "LINEAR", "x": X, "y": y, "start": [1e308, 1e308], "method": "BFGS"}, "E_NON_FINITE", "B22")
    err("calib.fit", {"model": "EXPONENTIAL", "x": X, "y": y, "start": [1.0, -1000.0], "method": "LEVENBERG_MARQUARDT"}, "E_NON_FINITE", "B22")
    s.add("calib.fit", {**f, "start": [1e308, 1e308], "lower": [-100.0, -100.0], "upper": [100.0, 100.0]}, {"parameters": [0.0, 1.0], "objective": 0.0}, cls=I, verified=["hand"], tags=["B22"],
          limit={"absolute": 1e-6, "relative": 0.0, "reason": "projected on the box first, so the start is finite"})
    write(s)


def main():
    schedules()
    curves()
    ois()
    projection()
    risk()
    fx()
    hedge()
    rulings()
    assert rates and json
    (Path(__file__).parent.parent / "MUTANTS.md").write_text("# Stage B mutants\n\nWritten by `oracle/python/gen_stage_b_deep.py`. Each row is one deliberate mistake; the gap is how far it lands from the golden, and the run stops if a gap is inside tolerance. Date mutants count differing cases.\n\n| Suite | Mutant | Gap |\n|---|---|---|\n"
                                                             + "".join(f"| `{a}` | {n} | {g:.3g} |\n" for a, n, g in MUTANTS), encoding="utf-8", newline="\n")
    note(f"mutants: {len(MUTANTS)} deliberate errors, all caught")


if __name__ == "__main__":
    main()
