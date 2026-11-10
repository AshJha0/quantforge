"""Stage F wave 1, Q4 and the funding curve (02-curves/joint-solve-and-funding.md). Suite stage_f/joint_f.

Goldens: the instruments of stages B and D (oracle replicas in gen_stage_b, gen_stage_d, gen_stage_d_xccy) joined in one
Newton solve to 1e-15; the Jacobian by the implicit function theorem with dR/dx from Richardson central differences,
checked here against bump-and-rebuild of the whole system. QuantLib appears only in outside_f.py.

    cd oracle/python && uv run python -W ignore gen_stage_f_q4.py
"""
import json
import math
from datetime import date, timedelta

import numpy as np

from qf_oracle import common
from qf_oracle import rates as RT
from qf_oracle.common import Suite, note
import gen_stage_b as B
import gen_stage_d as GD
from gen_stage_d_xccy import float_leg, joint_adjust, xccy_dates
from gen_stage_f_q1 import CurveF

G = "oracle/python/gen_stage_f_q4.py"
E, I = "date_and_convention", "interpolation"
AS = date(2026, 11, 9)
MUT = []


def yrs(d):
    return (d - AS).days / 365


def hw_conv(i):
    t, T = yrs(date.fromisoformat(i["start"])), yrs(date.fromisoformat(i["end"]))
    a, sg = i["mean_reversion"], i["sigma"]
    d = T - t
    Bd = (1 - math.exp(-a * d)) / a if a else d
    L = (1 - math.exp(-2 * a * t)) / a if a else 2 * t
    Bt = (1 - math.exp(-a * t)) / a if a else t
    z = sg * sg / 2 * (L * Bd * Bd + Bd * Bt * Bt)
    fr = (100 - i["price"]) / 100
    return fr, -math.expm1(-z) * (fr + 1 / d), z


class StepC:
    def __init__(self, base, steps, jumps):
        self.c = GD.StepCurve(AS, base, steps, jumps)

    def df(self, d):
        return self.c.df(d)


class System:
    """Unknown layout and residuals of rates.curve.joint_solve."""

    def __init__(self, inp):
        self.inp = inp
        self.curves = inp["curves"]
        self.ins = inp["instruments"]
        self.labels, self.layout = [], {}
        for c in self.curves:
            nm = c["name"]
            mine = [q for q in self.ins if q["curve"] == nm]
            turns = [date.fromisoformat(t["date"]) for t in c.get("turns", [])]
            assert sum(1 for q in mine if q.get("turn")) == len(turns), "turn count"
            start = len(self.labels)
            if c["type"] == "OIS_STEPS":
                sd = [date.fromisoformat(x) for x in c["step_dates"]]
                assert len(mine) == 1 + len(sd) + len(turns), "steps count"
                self.labels += [f"{nm}:base"] + [f"{nm}:step:{d}" for d in sd]
                pil = sd
            else:
                pil = [self.pillar(c, q) for q in mine if not q.get("turn")]
                assert all(a < b for a, b in zip(pil, pil[1:])), "pillars"
                self.labels += [f"{nm}:pillar:{d}" for d in pil]
            self.labels += [f"{nm}:turn:{d}" for d in turns]
            self.layout[nm] = (start, len(self.labels), pil, turns)
        assert len(self.labels) == len(self.ins), "not square"

    def pillar(self, c, q):
        t = q["type"]
        if t == "OIS":
            return RT.ois_periods(c["convention"], AS, q["tenor"])[-1][2]
        if t == "FUTURE":
            return date.fromisoformat(q["end"])
        if t == "SWAP":
            return B.term_periods(AS, q["months"], 12)[1][-1]
        if t in ("DEPOSIT", "FRA"):
            return self.proj_dates(q)[1]
        if t == "XCCY":
            return xccy_dates(date.fromisoformat(c["start"]), q["months"])[-1]
        raise ValueError(t)

    def proj_dates(self, q):
        cal = B.TERM["calendar"]
        spot = RT.add_bd(cal, AS, B.TERM["spot_lag"])
        s0 = spot if q["type"] == "DEPOSIT" else RT.adjust(cal, RT.add_months(spot, q["start_months"]))
        return s0, RT.adjust(cal, RT.add_months(s0, 3))

    def build(self, x):
        out = {}
        for c in self.curves:
            nm = c["name"]
            a, b, pil, turns = self.layout[nm]
            v = x[a:b]
            np_ = len(v) - len(turns)
            jumps = [(date.fromisoformat(j["date"]), j["factor"]) for j in c.get("jumps", [])] + [(d, math.exp(v[np_ + k])) for k, d in enumerate(turns)]
            jumps.sort()
            if c["type"] == "OIS_STEPS":
                out[nm] = StepC(v[0], list(zip(pil, v[1:np_])), jumps)
            else:
                out[nm] = CurveF(pil, [math.exp(u) for u in v[:np_]], c["interpolation"], c.get("tension"),
                                 date.fromisoformat(c["step_end"]) if c.get("step_end") else None, jumps)
        return out

    def model(self, cs):
        byname = {c["name"]: c for c in self.curves}
        m = []
        for q in self.ins:
            c = byname[q["curve"]]
            cv = cs[q["curve"]]
            t = q["type"]
            if t == "OIS":
                m.append(RT.ois_par(c["convention"], RT.ois_periods(c["convention"], AS, q["tenor"]), cv))
            elif t == "FUTURE":
                s, e = date.fromisoformat(q["start"]), date.fromisoformat(q["end"])
                m.append((cv.df(s) / cv.df(e) - 1) / ((e - s).days / 360))
            elif t == "SWAP":
                an, fl = B.swap_legs(cs[c["discount"]], cv, AS, q["months"])
                m.append(fl / an)
            elif t in ("DEPOSIT", "FRA"):
                s, e = self.proj_dates(q)
                m.append((cv.df(s) / cv.df(e) - 1) / float(RT.yf("ACT_360", s, e)))
            elif t == "XCCY":
                ds = xccy_dates(date.fromisoformat(c["start"]), q["months"])
                m.append(float_leg(ds, cs[c["foreign_projection"]], cv, q["spread"], 1.0))
        return np.array(m)

    def quote_target(self, q):
        if q["type"] == "FUTURE":
            fr, cv, _ = hw_conv(q)
            return fr - cv
        if q["type"] == "XCCY":
            return 0.0
        return q["rate"]

    def res(self, x):
        return self.model(self.build(x)) - np.array([self.quote_target(q) for q in self.ins])

    def dRdq(self):
        out = np.zeros(len(self.ins))
        for j, q in enumerate(self.ins):
            if q["type"] == "FUTURE":
                out[j] = 0.01 * math.exp(-hw_conv(q)[2])
            elif q["type"] == "XCCY":
                c = next(c for c in self.curves if c["name"] == q["curve"])
                ds = xccy_dates(date.fromisoformat(c["start"]), q["months"])
                cs = self.build(self.x)
                out[j] = sum((e - a).days / 360 * cs[q["curve"]].df(e) for a, e in zip(ds, ds[1:]))
            else:
                out[j] = -1.0
        return np.diag(out)

    def x0(self):
        x = []
        for c in self.curves:
            nm = c["name"]
            a, b, pil, turns = self.layout[nm]
            mine = [q for q in self.ins if q["curve"] == nm]
            r0 = next((q.get("rate") for q in mine if "rate" in q), 0.03)
            if c["type"] == "OIS_STEPS":
                x += [r0] * (len(pil) + 1)
            elif c["type"] == "XCCY":
                x += [-0.025 * yrs(d) for d in pil]
            else:
                x += [-r0 * yrs(d) for d in pil]
            x += [0.0] * len(turns)
        return np.array(x)

    def dRdx(self, x, h):
        cols = []
        for k in range(len(x)):
            e = np.zeros(len(x))
            e[k] = h
            cols.append((self.res(x + e) - self.res(x - e)) / (2 * h))
        return np.column_stack(cols)

    def chord(self, x, Jx):
        """Warm-started chord iterations with a fixed dR/dx (for small quote bumps)."""
        for _ in range(50):
            r = self.res(x)
            if max(abs(r)) < 1e-15:
                break
            x = x - np.linalg.solve(Jx, r)
        assert max(abs(self.res(x))) < 1e-14
        return x

    def solve(self):
        x = self.x0()
        for it in range(60):
            r = self.res(x)
            if max(abs(r)) < 1e-15:
                break
            x = x - np.linalg.solve(self.dRdx(x, 1e-7), r)
        err = max(abs(self.res(x)))
        assert err < 1e-14, err
        self.x = x
        return x, err

    def jacobian(self):
        # Richardson central differences at 1e-5 and 5e-6 (ruling F-28: checked against a kink-free bump reference; a
        # build's own stencil must not straddle a kink either, see the ruling)
        h = 1e-5
        Jx = (4 * self.dRdx(self.x, h / 2) - self.dRdx(self.x, h)) / 3
        # exact block structure: a residual never depends on unknowns of later curves
        for c in self.curves:
            a, b, _, _ = self.layout[c["name"]]
            rows = [j for j, q in enumerate(self.ins) if q["curve"] == c["name"]]
            for later in self.curves[self.curves.index(c) + 1:]:
                la, lb, _, _ = self.layout[later["name"]]
                assert np.max(np.abs(Jx[np.ix_(rows, range(la, lb))])) == 0.0
        J = -np.linalg.solve(Jx, self.dRdq())
        return J, Jx


def bump_jacobian(inp, h, x0, Jx):
    """Reference: re-solve the whole system with each quote moved by +-h and +-h/2 (chord iterations from the solution to
    1e-15, so the bumped curves are the exact bumped solutions), Richardson-combined."""
    def solve_with(j, dq):
        q2 = [dict(q) for q in inp["instruments"]]
        key = {"FUTURE": "price", "XCCY": "spread"}.get(q2[j]["type"], "rate")
        q2[j][key] += dq
        s = System({**inp, "instruments": q2})
        return s.chord(np.array(x0), Jx)
    cols = []
    for j in range(len(inp["instruments"])):
        d1 = (solve_with(j, h) - solve_with(j, -h)) / (2 * h)
        d2 = (solve_with(j, h / 2) - solve_with(j, -h / 2)) / h
        cols.append((4 * d2 - d1) / 3)
    return np.column_stack(cols)


def cm_kinds(sysm, x):
    """Rule kinds of the interior monotone-convex sections of every MONOTONE_CONVEX curve (ruling F-28). The first and
    last sections are left out: the endpoint rule puts them at g1/g0 = -2 and -1/2 exactly, where the neighbouring
    rules give the same function, so a rounding flip there is not a kink."""
    cs = sysm.build(x)
    return tuple((c["name"], tuple(cs[c["name"]].ip.secs[i][0] for i in sorted(cs[c["name"]].ip.secs)[1:-1]))
                 for c in sysm.curves if c.get("interpolation") == "MONOTONE_CONVEX")


def reference_jacobian(inp, x0, Jx, h=1e-4, floor=1e-6):
    """Bump-and-rebuild reference with a step it proves sound (ruling F-28). Halve h from 1e-4 until (a) no interior
    convex-monotone section changes rule under any quote bump of +-h or +-h/2, and (b) the h^4 error estimate of the
    h/2 Richardson value, |R(h) - R(h/2)| / 15, is below half the check tolerance, 0.5 (1e-9 + 1e-6 |ref|). Returns the
    finer step and its estimate. A piecewise
    method can be smooth but strongly curved near a kink, so (a) alone is not enough."""
    sysm = System(inp)
    base = cm_kinds(sysm, x0)

    def stable(hh):
        for j, q in enumerate(inp["instruments"]):
            key = {"FUTURE": "price", "XCCY": "spread"}.get(q["type"], "rate")
            for dq in (hh, -hh, hh / 2, -hh / 2):
                q2 = [dict(v) for v in inp["instruments"]]
                q2[j][key] += dq
                s2 = System({**inp, "instruments": q2})
                if cm_kinds(s2, s2.chord(np.array(x0), Jx)) != base:
                    return False
        return True

    prev = None
    while h >= floor:
        if not base or stable(h):
            cur = bump_jacobian(inp, h, x0, Jx)
            # Richardson error estimate for an h^4 method: |R(h) - R(h/2)| / (2^4 - 1)
            if prev is not None and np.max(np.abs(cur - prev) / 15 - 0.5 * (1e-9 + 1e-6 * np.abs(cur))) <= 0:
                return h, cur  # h is already the finer step: prev was computed at 2h
            prev = cur
        else:
            prev = None
        h /= 2
    raise AssertionError(f"bump-and-rebuild reference not converged down to h = {floor}")


def spans(sysm, q, turn):
    c = next(c for c in sysm.curves if c["name"] == q["curve"])
    t = q["type"]
    if t == "OIS":
        per = RT.ois_periods(c["convention"], AS, q["tenor"])
        ds = [d for p in per for d in p]
    elif t == "FUTURE":
        ds = [date.fromisoformat(q["start"]), date.fromisoformat(q["end"])]
    elif t in ("DEPOSIT", "FRA"):
        ds = list(sysm.proj_dates(q))
    elif t == "SWAP":
        ds = B.term_periods(AS, q["months"], 3)[1]
    else:
        ds = xccy_dates(date.fromisoformat(c["start"]), q["months"])
    return min(ds) <= turn < max(ds)


def outputs(sysm, x, J, Jx):
    cs = sysm.build(x)
    cur, tf = [], []
    for c in sysm.curves:
        a, b, pil, turns = sysm.layout[c["name"]]
        np_ = (b - a) - len(turns)
        if c["type"] == "OIS_STEPS":
            cur.append({"name": c["name"], "base_rate": float(x[a]), "step_rates": [float(v) for v in x[a + 1:a + np_]]})
        else:
            cur.append({"name": c["name"], "pillars": [{"date": d.isoformat(), "discount_factor": cs[c["name"]].df(d)} for d in pil]})
        tf += [{"curve": c["name"], "date": d.isoformat(), "factor": math.exp(x[a + np_ + k])} for k, d in enumerate(turns)]
    ts = []
    for c in sysm.curves:
        a, b, pil, turns = sysm.layout[c["name"]]
        for k, d in enumerate(turns):
            col = Jx[:, b - len(turns) + k]
            row = []
            for j, q in enumerate(sysm.ins):
                affected = q["curve"] == c["name"] or any(c["name"] in (cc.get("discount"), cc.get("domestic"), cc.get("foreign_projection"))
                                                          for cc in sysm.curves if cc["name"] == q["curve"])
                # ruling F-26 (amended): the honest d model / d ln factor; exactly 0 on OIS_STEPS curves for a non-spanning
                # instrument; on pillar curves it need not be (four-curve case: SOFR-1M about -0.023)
                if c["type"] == "OIS_STEPS" and not (affected and spans(sysm, q, d)):
                    assert abs(col[j]) < 1e-9, (q["id"], col[j])  # exactly 0 by construction; the difference is noise
                    row.append(0.0)
                else:
                    row.append(float(col[j]))
            ts.append(row)
    return {"curves": cur, "turn_factors": tf,
            "jacobian": {"unknowns": sysm.labels, "quotes": [q["id"] for q in sysm.ins], "matrix": [[float(v) for v in r] for r in J]},
            "turn_sensitivity": ts}


def systems():
    GD.estr() if hasattr(GD, "estr") else None
    sofr_q = [("1M", .0430), ("2M", .0428), ("3M", .0425), ("6M", .0412), ("1Y", .0390), ("2Y", .0365), ("3Y", .0355), ("5Y", .0352), ("10Y", .0364)]
    sofr = [{"id": f"SOFR-{t}", "curve": "USD-SOFR", "type": "OIS", "tenor": t, "rate": r, **({"turn": True} if t == "2M" else {})} for t, r in sofr_q]
    proj = [{"id": "T-DEP", "curve": "USD-TERM-3M", "type": "DEPOSIT", "months": 3, "rate": .0445},
            {"id": "T-FRA3", "curve": "USD-TERM-3M", "type": "FRA", "start_months": 3, "rate": .0432},
            {"id": "T-FRA6", "curve": "USD-TERM-3M", "type": "FRA", "start_months": 6, "rate": .0418},
            {"id": "T-SW2", "curve": "USD-TERM-3M", "type": "SWAP", "months": 24, "rate": .0388},
            {"id": "T-SW5", "curve": "USD-TERM-3M", "type": "SWAP", "months": 60, "rate": .0376},
            {"id": "T-SW10", "curve": "USD-TERM-3M", "type": "SWAP", "months": 120, "rate": .0389}]
    estr_q = [("1M", .0205), ("3M", .0201), ("6M", .0196), ("1Y", .0190), ("2Y", .0189), ("5Y", .0205), ("10Y", .0238)]
    estr = [{"id": f"ESTR-{t}", "curve": "EUR-ESTR", "type": "OIS", "tenor": t, "rate": r} for t, r in estr_q]
    start = joint_adjust(date(2026, 11, 12))
    xc = [{"id": f"XC-{m}", "curve": "EUR-XCCY", "type": "XCCY", "months": m, "spread": s} for m, s in ((12, -.0012), (24, -.0015), (60, -.0019), (120, -.0021))]
    full = {"as_of": AS.isoformat(), "curves": [
        {"name": "USD-SOFR", "type": "OIS", "convention": "SOFR", "interpolation": "MONOTONE_CONVEX", "turns": [{"date": "2026-12-31"}]},
        {"name": "USD-TERM-3M", "type": "PROJECTION", "index": "USD-TERM-3M", "discount": "USD-SOFR", "interpolation": "LOG_LINEAR_DF"},
        {"name": "EUR-ESTR", "type": "OIS", "convention": "ESTR", "interpolation": "MONOTONIC_LOG_CUBIC"},
        {"name": "EUR-XCCY", "type": "XCCY", "domestic": "USD-SOFR", "foreign_projection": "EUR-ESTR", "domestic_convention": "SOFR",
         "foreign_convention": "ESTR", "start": start.isoformat(), "interpolation": "LOG_LINEAR_DF"}],
        "instruments": sofr + proj + estr + xc}
    fut = lambda i, s, e, p: {"id": f"SR3-{i}", "curve": "USD-SOFR-STEPS", "type": "FUTURE", "start": s, "end": e, "price": p, "sigma": .0085, "mean_reversion": .03}  # noqa: E731
    steps = {"as_of": AS.isoformat(), "curves": [
        {"name": "USD-SOFR-STEPS", "type": "OIS_STEPS", "convention": "SOFR", "step_dates": ["2026-12-10", "2027-03-18", "2027-06-17", "2027-09-16"],
         "turns": [{"date": "2026-12-31"}]}],
        "instruments": [{"id": "SOFR-1M", "curve": "USD-SOFR-STEPS", "type": "OIS", "tenor": "1M", "rate": .0431},
                        {"id": "SOFR-2M", "curve": "USD-SOFR-STEPS", "type": "OIS", "tenor": "2M", "rate": .0425, "turn": True},
                        fut("Z6", "2026-12-16", "2027-03-17", 95.82), fut("H7", "2027-03-17", "2027-06-16", 96.01),
                        fut("M7", "2027-06-16", "2027-09-15", 96.18), fut("U7", "2027-09-15", "2027-12-15", 96.30)]}
    simple = {"as_of": AS.isoformat(), "curves": [
        {"name": "USD-SOFR", "type": "OIS", "convention": "SOFR", "interpolation": "LOG_LINEAR_DF"},
        {"name": "USD-TERM-3M", "type": "PROJECTION", "index": "USD-TERM-3M", "discount": "USD-SOFR", "interpolation": "LOG_LINEAR_DF"}],
        "instruments": [dict(q, turn=False) if False else {k: v for k, v in q.items() if k != "turn"} for q in sofr if q["tenor"] != "2M"] + proj}
    mlc = {"as_of": AS.isoformat(), "curves": [
        {"name": "USD-SOFR", "type": "OIS", "convention": "SOFR", "interpolation": "MONOTONIC_LOG_CUBIC"},
        {"name": "USD-TERM-3M", "type": "PROJECTION", "index": "USD-TERM-3M", "discount": "USD-SOFR", "interpolation": "MONOTONIC_LOG_CUBIC"}],
        "instruments": simple["instruments"]}
    return [("full: SOFR (monotone convex, turn) + term + ESTR (monotonic log cubic) + xccy", full),
            ("SOFR meeting steps fitted to SR3 futures with convexity and a year-end turn", steps),
            ("SOFR + term, log-linear (stage D joint_bootstrap equivalent)", simple),
            ("SOFR + term, monotonic log cubic", mlc)]


def funding(s):
    op = "rates.funding.curve"
    pil = [AS + timedelta(days=d) for d in (30, 91, 182, 365, 730, 1826)]
    dfs = [math.exp(-r * yrs(d)) for r, d in zip((.0430, .0425, .0412, .0390, .0365, .0352), pil)]
    disc = {"as_of": AS.isoformat(), "interpolation": "LOG_LINEAR_DF", "pillars": [{"date": d.isoformat(), "discount_factor": v} for d, v in zip(pil, dfs)]}
    oc = RT.Curve(AS, pil, dfs)
    for nm, qs in (("unsecured +40 to +90 bp", [(91, .0472), (182, .0465), (365, .0452), (730, .0441), (1826, .0447)]),
                   ("inverted funding spread", [(30, .0485), (365, .0440), (1095, .0410)])):
        ends = [AS + timedelta(days=d) for d, _ in qs]
        Pf = [1 / (1 + r * d / 360) for d, r in qs]
        L = [math.log(oc.df(e) / p) for e, p in zip(ends, Pf)]
        ts = [yrs(e) for e in ends]
        sp = [(L[i] - (L[i - 1] if i else 0.0)) / (ts[i] - (ts[i - 1] if i else 0.0)) for i in range(len(L))]
        dates = [AS + timedelta(days=k * 90) for k in range(0, 50)]

        def Df(d):
            t = yrs(d)
            integ, prev = 0.0, 0.0
            for ti, si in zip(ts, sp):
                integ += si * (min(t, ti) - prev) if t > prev else 0.0
                prev = ti
            if t > ts[-1]:
                integ += sp[-1] * (t - ts[-1])
            return oc.df(d) * math.exp(-integ)
        out = {"spreads": sp, "pillars": [{"date": e.isoformat(), "discount_factor": Df(e)} for e in ends], "discount_factors": [Df(d) for d in dates]}
        for e, p, pv in zip(ends, Pf, out["pillars"]):
            assert abs(pv["discount_factor"] - p) < 1e-15
        s.add(op, {"discount": disc, "quotes": [{"end": e.isoformat(), "rate": r} for e, (_, r) in zip(ends, qs)], "dates": [d.isoformat() for d in dates]}, out, cls=I,
              verified=["analytic", "independent-replay"], tags=["funding", "stage-f"], description=nm)
    # limit: funding at the OIS simple rates gives spreads 0
    ends = [pil[1], pil[3], pil[5]]
    qs = [(e, (1 / oc.df(e) - 1) * 360 / (e - AS).days) for e in ends]
    s.add(op, {"discount": disc, "quotes": [{"end": e.isoformat(), "rate": r} for e, r in qs]},
          {"spreads": [0.0, 0.0, 0.0], "pillars": [{"date": e.isoformat(), "discount_factor": oc.df(e)} for e in ends], "discount_factors": []},
          cls=I, verified=["analytic"], tags=["funding", "limit", "stage-f"], description="funding at the OIS simple rates: zero spreads")
    for d, q, code in (("no quotes", [], "E_INPUT"), ("ends not increasing", [{"end": "2027-11-09", "rate": .045}, {"end": "2027-05-09", "rate": .045}], "E_INPUT"),
                       ("1 + r alpha <= 0", [{"end": "2027-11-09", "rate": -1.5}], "E_DOMAIN")):
        s.add(op, {"discount": disc, "quotes": q}, error=code, cls=E, tags=["invalid", "stage-f"], description=d)


REFS = {}


def main():
    s = Suite("joint_f", "specifications/02-curves/joint-solve-and-funding.md", G)
    op = "rates.curve.joint_solve"
    JL = {"jacobian": "jacobian", "turn_sensitivity": "jacobian"}
    for desc, inp in systems():
        sysm = System(inp)
        x, err = sysm.solve()
        J, Jx = sysm.jacobian()
        print(f"  solved {desc[:40]} ({len(x)} unknowns), max residual {err:.1e}", flush=True)
        # F-25: an earlier curve's unknowns do not depend on a later curve's quotes; the LU solve leaves rounding there
        zpos = []
        names = [c["name"] for c in sysm.curves]
        for ci, c in enumerate(sysm.curves):
            a, b, _, _ = sysm.layout[c["name"]]
            later = [j for j, q in enumerate(sysm.ins) if names.index(q["curve"]) > ci]
            for r in range(a, b):
                for j in later:
                    assert abs(J[r, j]) < 1e-12, (r, j, J[r, j])
                    J[r, j] = 0.0
                    zpos.append([r, j])
        h, ref = reference_jacobian(inp, x, Jx)
        print(f"  bump-and-rebuild done (h = {h:.3e})", flush=True)
        gapmax = float(np.max(np.abs(J - ref)))
        dev = np.max(np.abs(J - ref) - (1e-9 + 1e-6 * np.abs(ref)))
        assert dev <= 0, f"{desc}: IFT Jacobian against bump-and-rebuild: {dev:.3e}"
        REFS[desc] = {"h": h, "max_abs_ift_minus_reference": gapmax, "reference": ref.tolist()}
        out = outputs(sysm, x, J, Jx)
        checks = [{"method": "exact_zero", "output": "jacobian.matrix", "positions": zpos}] if zpos else []
        tz = [[k, j] for k, row in enumerate(out["turn_sensitivity"]) for j, v in enumerate(row)
              if v == 0.0 and sysm.curves[0]["type"] == "OIS_STEPS"]
        if tz:
            checks.append({"method": "exact_zero", "output": "turn_sensitivity", "positions": tz})
        piece = desc.startswith("full")
        s.add(op, inp, out, cls=I, verified=["independent-replay newton 1e-14", f"bump-and-rebuild richardson h={h:.3e}, max |IFT - ref| {gapmax:.1e}",
                                             "reference stored in oracle/Q4_REFERENCE_F.json"], tags=["joint", "stage-f"],
              output_classes={"jacobian": "jacobian_piecewise", "turn_sensitivity": "jacobian_piecewise"} if piece else JL,
              extra_checks=checks or None, description=f"{desc}; max residual {err:.1e}")
        # wrong conventions: futures without convexity; turn not solved (factor 1)
        if any(q["type"] == "FUTURE" for q in inp["instruments"]):
            noc = {**inp, "instruments": [dict(q, sigma=0.0) if q["type"] == "FUTURE" else q for q in inp["instruments"]]}
            s2 = System(noc)
            x2 = s2.chord(np.array(x), Jx)
            caught(f"{desc}: no futures convexity", float(np.max(np.abs(x2 - x))), 1e-10)
        if any(c.get("turns") for c in inp["curves"]):
            caught(f"{desc}: turn factor left at 1", max(abs(t["factor"] - 1) for t in out["turn_factors"]), 1e-10)
    # stage D consistency: the log-linear SOFR + term system equals rates.curve.joint_bootstrap's pillars (same instruments)
    base = systems()[0][1]
    for d, chg, code in (("curve names a later curve", lambda i: {**i, "curves": [i["curves"][1], i["curves"][0]] + i["curves"][2:]}, "E_INPUT"),
                         ("turn without a turn instrument", lambda i: {**i, "instruments": [{k: v for k, v in q.items() if k != "turn"} for q in i["instruments"]]}, "E_INPUT"),
                         ("duplicate instrument id", lambda i: {**i, "instruments": i["instruments"] + [i["instruments"][0]]}, "E_INPUT"),
                         ("future with end before start", None, "E_INPUT")):
        if chg is None:
            st = systems()[1][1]
            bad = {**st, "instruments": [dict(q, start=q["end"], end=q["start"]) if q["id"] == "SR3-H7" else q for q in st["instruments"]]}
        else:
            bad = chg(base)
        s.add(op, bad, error=code, cls=E, tags=["invalid", "stage-f"], description=d)
    funding(s)
    # E_NO_CONVERGENCE (R5 audit): two instruments with the same dates and different quotes; dR/dx is singular and no
    # solution exists. Appended last so that earlier case ids do not move.
    st = systems()[1][1]
    one = next(q for q in st["instruments"] if q["id"] == "SOFR-1M")
    bad = {**st, "instruments": [dict(one, id="SOFR-1M-B", rate=one["rate"] + 0.001, turn=True) if q["id"] == "SOFR-2M" else q for q in st["instruments"]]}
    s.add(op, bad, error="E_NO_CONVERGENCE", cls=E, tags=["invalid", "no-convergence", "stage-f"],
          description="two instruments on the same dates with different quotes: dR/dx singular, no solution")
    (common.ROOT / "oracle" / "Q4_REFERENCE_F.json").write_text(json.dumps(REFS) + chr(10), encoding="utf-8", newline=chr(10))
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_f"
    for c in s.cases:
        c["tags"].append("synthetic")
    s.write()
    common.GOLDEN = keep
    note(f"joint_f: {len(s.cases)} cases, {len(MUT)} wrong conventions caught")


def caught(name, g, tol):
    assert g > tol, f"joint_f: '{name}' not caught: {g:.3e} <= {tol:.3e}"
    MUT.append((name, g))


if __name__ == "__main__":
    main()
