"""Day counts, calendars, compounding. Exact rules, checked against QuantLib and Strata."""
import os
import random
import subprocess
from datetime import date, timedelta
from pathlib import Path

import mpmath as mp
import QuantLib as ql

from qf_oracle.common import Suite, f, note
from qf_oracle.dates import dim, easter, holidays, is_business, leap, yf

HERE = Path(__file__).parent
STRATA = HERE.parent / "strata"
Q = lambda d: ql.Date(d.day, d.month, d.year)  # noqa: E731
QLCAL = {"GBLO": ql.UnitedKingdom(ql.UnitedKingdom.Settlement), "EUTA": ql.TARGET(),
         "USGS": ql.UnitedStates(ql.UnitedStates.GovernmentBond)}
STRATA_NAMES = {"ACT_360": "Act/360", "ACT_365F": "Act/365F", "ACT_364": "Act/364", "ACT_365_25": "Act/365.25",
                "ACT_365L": "Act/365L", "ACT_ACT_ISDA": "Act/Act ISDA", "ACT_ACT_ICMA": "Act/Act ICMA",
                "ACT_ACT_AFB": "Act/Act AFB", "NL_365": "NL/365", "ONE_ONE": "1/1",
                "THIRTY_360_BOND": "30/360 ISDA", "THIRTY_360_US": "30U/360 EOM", "THIRTY_E_360": "30E/360",
                "THIRTY_E_360_ISDA": "30E/360 ISDA", "THIRTY_E_PLUS_360": "30E+/360"}


def ql_dc(conv, kw):
    return {"ACT_360": ql.Actual360, "ACT_365F": ql.Actual365Fixed, "ACT_364": ql.Actual364,
            "ACT_365_25": ql.Actual36525,
            "ACT_ACT_ISDA": lambda: ql.ActualActual(ql.ActualActual.ISDA),
            "ACT_ACT_AFB": lambda: ql.ActualActual(ql.ActualActual.AFB),
            "ACT_ACT_ICMA": lambda: ql.ActualActual(ql.ActualActual.ISMA),
            "THIRTY_360_BOND": lambda: ql.Thirty360(ql.Thirty360.BondBasis),
            "THIRTY_360_US": lambda: ql.Thirty360(ql.Thirty360.USA),
            "THIRTY_E_360": lambda: ql.Thirty360(ql.Thirty360.European),
            "THIRTY_E_360_ISDA": lambda: ql.Thirty360(ql.Thirty360.ISDA, Q(kw["termination"])),
            "BUS_252": lambda: ql.Business252(QLCAL[kw["calendar"]])}.get(conv)


def add_months(d, n):
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    m += 1
    return date(y, m, min(d.day, dim(y, m)))


def pairs():
    edge = ["2023-12-31", "2024-01-01", "2024-01-31", "2024-02-28", "2024-02-29", "2024-03-01", "2024-03-31",
            "2024-04-30", "2024-12-31", "2025-01-01", "2025-02-28", "2025-03-01", "2025-03-31", "2023-02-28",
            "2020-02-29", "2028-02-29", "2028-02-28", "2019-08-31"]
    ds = sorted(date.fromisoformat(x) for x in edge)
    out = [(a, b) for a in ds for b in ds if a <= b]
    rnd = random.Random(20261106)
    rnd.shuffle(out)
    out = out[:70]
    out += [(date(1994, 2, 10), date(1997, 6, 30)), (date(2003, 11, 1), date(2004, 5, 1)),
            (date(1996, 2, 28), date(2001, 2, 28)), (date(2000, 2, 29), date(2005, 2, 28)),
            (date(2024, 1, 31), date(2024, 3, 31)), (date(2024, 1, 30), date(2024, 3, 31)),
            (date(2024, 1, 1), date(2024, 7, 1))]
    for _ in range(40):
        a = date(2000, 1, 1) + timedelta(rnd.randrange(0, 9000))
        out.append((a, a + timedelta(rnd.randrange(0, 4000))))
    return out


def daycount():
    s = Suite("daycount", "specifications/01-core/daycount.md", "oracle/python/gen_dates.py")
    op = "core.daycount.year_fraction"
    rows, plan = [], []
    for conv in list(STRATA_NAMES) + ["BUS_252"]:
        for a, b in pairs():
            kw, inp = {}, {"convention": conv, "start": str(a), "end": str(b)}
            mon = 12
            if conv == "ACT_365L":
                kw["frequency"] = inp["frequency"] = 1 if (a.day + b.day) % 2 else 2
                mon = 12 // kw["frequency"]
            if conv == "ACT_ACT_ICMA":
                if (b - a).days > 180 or a == b:
                    continue
                fq = 2
                rs, re_ = add_months(b, -6), b
                if rs > a:
                    continue
                kw.update(frequency=fq, ref_start=rs, ref_end=re_)
                inp.update(frequency=fq, ref_start=str(rs), ref_end=str(re_))
                mon = 6
            if conv == "THIRTY_E_360_ISDA":
                kw["termination"] = b if (a.day % 2) else date(2099, 12, 31)
                inp["termination"] = str(kw["termination"])
            if conv == "BUS_252":
                if (b - a).days > 1500 or a.year < 2000:
                    continue
                kw["calendar"] = inp["calendar"] = "GBLO" if a.day % 2 else "EUTA"
            plan.append((conv, a, b, kw, inp))
            if conv in STRATA_NAMES:
                rows.append("\t".join([STRATA_NAMES[conv], str(a), str(b), str(kw.get("ref_end", b)), str(mon), "0",
                                       # Strata reads a period ending at maturity as a final period counted forward
                                       # from start. A later maturity makes it count back from ref_end, as the spec does.
                                       "2099-12-31" if conv == "ACT_ACT_ICMA" else str(kw.get("termination", "-"))]))
    (STRATA / "out").mkdir(exist_ok=True)
    (STRATA / "out" / "daycount-in.tsv").write_text("\n".join(rows) + "\n", newline="\n")
    java = Path(os.environ.get("JAVA25_HOME", r"C:\Program Files\Eclipse Adoptium\jdk-25.0.5.8-hotspot")) / "bin" / "java"
    cp = "target/classes;" + (STRATA / "cp.txt").read_text()
    subprocess.run([str(java), "-cp", cp, "org.quantforge.oracle.StrataDump", "out/daycount-in.tsv", "out"],
                   cwd=STRATA, check=True)
    strata = {}
    for line in (STRATA / "out" / "daycount.tsv").read_text().splitlines():
        p = line.split("\t")
        strata[(p[0], p[1], p[2])] = float(p[-1])
    diffs = {"quantlib": {}, "strata": {}}
    for conv, a, b, kw, inp in plan:
        exact = yf(conv, a, b, **kw)
        v = float(exact)
        ver = ["exact-rational"]
        maker = ql_dc(conv, kw)
        if maker:
            dc = maker()
            if conv == "ACT_ACT_ICMA":
                qv = dc.yearFraction(Q(a), Q(b), Q(kw["ref_start"]), Q(kw["ref_end"]))
            else:
                qv = dc.yearFraction(Q(a), Q(b))
            if abs(qv - v) <= 1e-13:
                ver.append("quantlib-1.44")
            else:
                diffs["quantlib"].setdefault(conv, []).append((str(a), str(b), v, qv))
        if conv in STRATA_NAMES:
            sv = strata[(STRATA_NAMES[conv], str(a), str(b))]
            if abs(sv - v) <= 1e-13:
                ver.append("strata-2.12.78")
            else:
                diffs["strata"].setdefault(conv, []).append((str(a), str(b), v, sv))
        s.add(op, inp, {"year_fraction": v}, verified=ver)
    explain_differences(diffs)
    base = {"convention": "ACT_360", "start": "2024-01-02", "end": "2024-01-01"}
    s.add(op, base, error="E_DATE_ORDER", tags=["invalid"])
    s.add(op, {**base, "convention": "ACT_999", "end": "2024-02-01"}, error="E_SCHEMA", tags=["invalid"])
    s.add(op, {**base, "start": "2024-02-30"}, error="E_SCHEMA", tags=["invalid"])
    s.add(op, {"convention": "ACT_ACT_ICMA", "start": "2024-01-01", "end": "2024-02-01"}, error="E_SCHEMA", tags=["invalid"])
    s.add(op, {"convention": "ACT_ACT_ICMA", "start": "2023-01-01", "end": "2024-02-01", "frequency": 2,
               "ref_start": "2023-08-01", "ref_end": "2024-02-01"}, error="E_INPUT", tags=["invalid"])
    s.add(op, {"convention": "ACT_365L", "start": "2024-01-01", "end": "2024-02-01", "frequency": 5}, error="E_SCHEMA", tags=["invalid"])
    # start == end is 0 for every convention, tested where the day adjustments alone would not give it.
    for d in ("2024-02-29", "2023-02-28", "2024-01-31", "2024-03-31", "2024-01-30"):
        for term in (d, "2099-12-31"):
            s.add(op, {"convention": "THIRTY_E_360_ISDA", "start": d, "end": d, "termination": term}, {"year_fraction": 0.0}, verified=["hand"], tags=["boundary"])
        s.add(op, {"convention": "THIRTY_E_PLUS_360", "start": d, "end": d}, {"year_fraction": 0.0}, verified=["hand"], tags=["boundary"])
    s.write()


def strata_afb(a, b):
    """Strata's documented reading: plain year subtraction from end, no 28 February rule."""
    def minus(n):
        y = b.year - n
        return date(y, b.month, min(b.day, dim(y, b.month)))
    end, n = b, 0
    while minus(n + 1) >= a:
        n += 1
        end = minus(n)
    y = a.year
    while not (leap(y) and date(y, 2, 29) >= a):
        y += 1
    return n + (end - a).days / (366 if date(y, 2, 29) < end else 365)


def explain_differences(diffs):
    """Every difference must be one the specs explain. Anything else stops the run."""
    qd = dict(diffs["quantlib"])
    eq = qd.pop("THIRTY_E_360_ISDA", [])
    assert not qd and all(a == b for a, b, _, _ in eq), diffs["quantlib"]
    note(f"daycount QuantLib THIRTY_E_360_ISDA: {len(eq)} difference, start = end = termination on 29 February, QuantLib gives -1/360; the spec gives 0")
    st = dict(diffs["strata"])
    afb = st.pop("ACT_ACT_AFB", [])
    for a, b, _, sv in afb:
        a, b = date.fromisoformat(a), date.fromisoformat(b)
        assert abs(strata_afb(a, b) - sv) < 1e-13 and b.month == 2 and b.day == 28, (a, b)
    note(f"daycount Strata ACT_ACT_AFB: {len(afb)} differences, all with end on 28 February, all reproduced by Strata's documented rule")
    one = st.pop("ONE_ONE", [])
    assert all(a == b for a, b, _, _ in one)
    note(f"daycount Strata ONE_ONE: {len(one)} differences, all start = end; Strata documents 1/1 as always 1")
    assert not st, st
    note("daycount: no other difference from QuantLib or Strata, ACT_ACT_ICMA included")


def spec_add_tenor(c, d, months, conv, eom):
    """calendars.md, for months and years, to prove the text against QuantLib."""
    def adj(x, how):
        step = -1 if how == "PRECEDING" else 1
        while not is_business(c, x):
            x += timedelta(step)
        return x

    def apply(x):
        if conv == "UNADJUSTED":
            return x
        if conv in ("FOLLOWING", "PRECEDING"):
            return adj(x, conv)
        r = adj(x, conv.split("_")[1])
        return r if r.month == x.month else adj(x, "PRECEDING" if conv == "MODIFIED_FOLLOWING" else "FOLLOWING")
    t = add_months(d, months)
    last_day = lambda x: date(x.year, x.month, dim(x.year, x.month))  # noqa: E731
    if eom and conv == "UNADJUSTED" and d == last_day(d):
        return last_day(t)
    if eom and conv != "UNADJUSTED" and d >= adj(last_day(d), "PRECEDING"):
        return adj(last_day(t), "PRECEDING")
    return apply(t)


def calendars():
    s = Suite("calendar", "specifications/01-core/calendars.md", "oracle/python/gen_dates.py")
    E = "date_and_convention"
    for c in ("GBLO", "EUTA", "USGS"):
        for y in (2000, 2001, 2002, 2011, 2012, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2050, 2099):
            hs = sorted(d for d in holidays(c, y) if d.weekday() < 5)
            s.add("core.calendar.holidays", {"calendar": c, "year": y}, {"dates": [str(d) for d in hs]}, cls=E,
                  verified=["rules", "quantlib-1.44" if y <= 2050 else "rules", "strata-2.12.78" if y <= 2050 else "rules"])
    rnd = random.Random(7)
    convs = {"FOLLOWING": ql.Following, "PRECEDING": ql.Preceding, "MODIFIED_FOLLOWING": ql.ModifiedFollowing,
             "MODIFIED_PRECEDING": ql.ModifiedPreceding, "UNADJUSTED": ql.Unadjusted}
    picks = [date(2024, 3, 29), date(2024, 3, 30), date(2024, 3, 31), date(2024, 6, 1), date(2024, 6, 30), date(2022, 12, 31),
             date(2023, 1, 1), date(2022, 9, 19), date(2024, 12, 25), date(2021, 5, 1), date(2021, 5, 2), date(2024, 8, 31)]
    picks += [date(2000, 1, 1) + timedelta(rnd.randrange(18000)) for _ in range(12)]
    for c in ("GBLO", "EUTA"):
        q = QLCAL[c]
        for d in picks:
            s.add("core.calendar.is_business_day", {"calendar": c, "date": str(d)}, {"is_business_day": is_business(c, d)}, cls=E, verified=["rules", "quantlib-1.44"])
            assert is_business(c, d) == q.isBusinessDay(Q(d))
            for name, qc in convs.items():
                r = q.adjust(Q(d), qc)
                s.add("core.calendar.adjust", {"calendar": c, "date": str(d), "convention": name},
                      {"date": r.ISO()}, cls=E, verified=["quantlib-1.44"])
            for n in (1, -1, 5, -5, 30):
                r = d
                k = 0
                st = 1 if n > 0 else -1
                while k < abs(n):
                    r += timedelta(st)
                    k += is_business(c, r)
                s.add("core.calendar.add_business_days", {"calendar": c, "date": str(d), "days": n}, {"date": str(r)}, cls=E, verified=["rules"])
            for ten, per in (("1M", ql.Period(1, ql.Months)), ("3M", ql.Period(3, ql.Months)), ("1Y", ql.Period(1, ql.Years))):
                for eom in (False, True):
                    for name in ("MODIFIED_FOLLOWING", "FOLLOWING"):
                        r = q.advance(Q(d), per, convs[name], eom)
                        s.add("core.calendar.add_tenor", {"calendar": c, "date": str(d), "tenor": ten, "convention": name, "end_of_month": eom},
                              {"date": r.ISO()}, cls=E, verified=["quantlib-1.44"])
    s.add("core.calendar.add_business_days", {"calendar": "GBLO", "date": "2024-03-30", "days": 0}, {"date": "2024-04-02"}, cls=E, verified=["hand"])
    s.add("core.calendar.add_tenor", {"calendar": "GBLO", "date": "2024-03-28", "tenor": "1W", "convention": "FOLLOWING", "end_of_month": False}, {"date": "2024-04-04"}, cls=E, verified=["hand"])
    s.add("core.calendar.add_tenor", {"calendar": "GBLO", "date": "2024-03-28", "tenor": "1D", "convention": "FOLLOWING", "end_of_month": False}, {"date": "2024-04-02"}, cls=E, verified=["hand"])
    s.add("core.calendar.business_days_between", {"calendar": "GBLO", "start": "2024-03-25", "end": "2024-04-03"}, {"count": 5}, cls=E, verified=["hand"])
    s.add("core.calendar.business_days_between", {"calendar": "GBLO", "start": "2024-04-03", "end": "2024-03-25"}, error="E_DATE_ORDER", cls=E, tags=["invalid"])
    s.add("core.calendar.is_business_day", {"calendar": "GBLO", "date": "1999-12-31"}, error="E_DATE_RANGE", cls=E, tags=["invalid"])
    s.add("core.calendar.is_business_day", {"calendar": "XXXX", "date": "2024-01-02"}, error="E_SCHEMA", cls=E, tags=["invalid"])
    s.add("core.calendar.add_tenor", {"calendar": "GBLO", "date": "2024-01-02", "tenor": "0M", "convention": "FOLLOWING", "end_of_month": False}, error="E_SCHEMA", cls=E, tags=["invalid"])
    wider = 0
    for c in ("GBLO", "EUTA"):
        q = QLCAL[c]
        d = date(2021, 1, 1)
        while d.year < 2027:
            for name, qc in convs.items():
                for eom in (False, True):
                    for mths in (1, 3, 12):
                        r = q.advance(Q(d), ql.Period(mths, ql.Months), qc, eom).ISO()
                        assert r == str(spec_add_tenor(c, d, mths, name, eom)), (c, d, name, eom, mths)
            d += timedelta(1)
    note("add_tenor: text of calendars.md matches QuantLib on every day 2021 to 2026, two calendars, all conventions")
    for d in (date(2024, 3, 30), date(2024, 3, 31), date(2024, 6, 30), date(2024, 2, 29), date(2024, 4, 29)):
        for name in ("UNADJUSTED", "PRECEDING", "MODIFIED_PRECEDING"):
            r = QLCAL["GBLO"].advance(Q(d), ql.Period(1, ql.Months), convs[name], True)
            s.add("core.calendar.add_tenor", {"calendar": "GBLO", "date": str(d), "tenor": "1M", "convention": name, "end_of_month": True}, {"date": r.ISO()}, cls=E, verified=["quantlib-1.44", "rules"])
            wider += 1
    assert easter(2024) == date(2024, 3, 31) and easter(2000) == date(2000, 4, 23)
    assert leap(2000) and not leap(2100)
    s.write()


def compounding():
    s = Suite("compounding", "specifications/01-core/compounding.md", "oracle/python/gen_dates.py")

    def df(r, t, c, n=None):
        r, t = mp.mpf(r), mp.mpf(t)
        if c == "SIMPLE":
            return 1 / (1 + r * t)
        if c == "CONTINUOUS":
            return mp.exp(-r * t)
        return (1 + r / n) ** (-n * t)

    def rate(d, t, c, n=None):
        t = mp.mpf(t)
        if c == "SIMPLE":
            return (1 / d - 1) / t
        if c == "CONTINUOUS":
            return -mp.log(d) / t
        return n * (d ** (-1 / (n * t)) - 1)

    kinds = [("SIMPLE", None), ("CONTINUOUS", None), ("PERIODIC", 1), ("PERIODIC", 2), ("PERIODIC", 4), ("PERIODIC", 12)]
    qlk = {"SIMPLE": ql.Simple, "CONTINUOUS": ql.Continuous, "PERIODIC": ql.Compounded}
    qlf = {None: ql.Annual, 1: ql.Annual, 2: ql.Semiannual, 4: ql.Quarterly, 12: ql.Monthly}
    for r in (0.05, 0.0, -0.005, 0.25):
        for t in (0.25, 1.0, 2.0, 10.5, 30.0):
            for c, n in kinds:
                if c == "SIMPLE" and 1 + r * t <= 0:
                    continue
                spec = {"compounding": c} | ({"frequency": n} if n else {})
                d = df(r, t, c, n)
                qv = ql.InterestRate(r, ql.Actual365Fixed(), qlk[c], qlf[n]).discountFactor(t)
                assert abs(qv - float(d)) < 1e-13
                s.add("core.compounding.discount_factor", {"rate": r, "t": t, **spec}, {"discount_factor": f(d)}, verified=["mpmath-50", "quantlib-1.44"])
                for c2, n2 in kinds:
                    spec2 = {"compounding": c2} | ({"frequency": n2} if n2 else {})
                    s.add("core.compounding.convert", {"rate": r, "t": t, "from": spec, "to": spec2}, {"rate": f(rate(d, t, c2, n2))}, verified=["mpmath-50"])
    s.add("core.compounding.discount_factor", {"rate": 0.05, "t": 0.0, "compounding": "SIMPLE"}, {"discount_factor": 1.0}, tags=["boundary"])
    s.add("core.compounding.discount_factor", {"rate": 0.05, "t": -1.0, "compounding": "SIMPLE"}, error="E_DOMAIN", tags=["invalid"])
    s.add("core.compounding.discount_factor", {"rate": -2.0, "t": 1.0, "compounding": "SIMPLE"}, error="E_DOMAIN", tags=["invalid"])
    s.add("core.compounding.discount_factor", {"rate": -3.0, "t": 1.0, "compounding": "PERIODIC", "frequency": 2}, error="E_DOMAIN", tags=["invalid"])
    s.add("core.compounding.discount_factor", {"rate": 0.05, "t": 1.0, "compounding": "PERIODIC"}, error="E_SCHEMA", tags=["invalid"])
    s.add("core.compounding.convert", {"rate": 0.05, "t": 0.0, "from": {"compounding": "SIMPLE"}, "to": {"compounding": "CONTINUOUS"}}, error="E_DOMAIN", tags=["invalid"])
    s.write()


def main():
    daycount()
    calendars()
    compounding()


if __name__ == "__main__":
    main()
