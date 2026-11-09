"""Stage F wave 1, Q1: pluggable curve interpolation (02-curves/curve-framework.md, stage F section). Suite stage_f/curve_f.

Goldens come from qf_oracle/interp_f.py (float replicas of the spec text) and a Newton bootstrap to 1e-15. QuantLib 1.44
is used only in `verify_ql`, never to write an expected value; it confirms every MONOTONE_CONVEX and MONOTONIC_LOG_CUBIC
case it can reach (rule 11.2.5), and the run stops if one disagrees beyond the case tolerance.

    cd oracle/python && uv run python -W ignore gen_stage_f_q1.py
"""
import math
from datetime import date, timedelta

import numpy as np

from qf_oracle import common
from qf_oracle import rates as RT
from qf_oracle.common import Suite, note
from qf_oracle.interp_f import make

G = "oracle/python/gen_stage_f_q1.py"
E, I = "date_and_convention", "interpolation"
AS = date(2026, 11, 9)
MUT = []
OUTSIDE = []   # (case index, what was checked) for the register written by outside_f.py

QUOTES = {
    "SOFR": [("1M", .0430), ("3M", .0425), ("6M", .0412), ("1Y", .0390), ("2Y", .0365), ("3Y", .0355), ("5Y", .0352), ("7Y", .0356),
             ("10Y", .0364), ("15Y", .0376), ("20Y", .0380), ("30Y", .0368)],
    "SONIA": [("1M", .0395), ("3M", .0388), ("6M", .0372), ("1Y", .0350), ("2Y", .0331), ("3Y", .0329), ("5Y", .0336), ("10Y", .0371),
              ("20Y", .0402), ("30Y", .0389)],
    "ESTR": [("1W", -.0005), ("1M", -.0003), ("3M", .0002), ("6M", .0011), ("1Y", .0029), ("2Y", .0061), ("5Y", .0118), ("10Y", .0172),
             ("20Y", .0201), ("30Y", .0195)],
}


def yrs(d):
    return (d - AS).days / 365


class CurveF:
    """Curve object of the spec: pillars hold full D; interpolation on S = D/J."""

    def __init__(self, pillars, dfs, kind, tension=None, step_end=None, jumps=()):
        self.jumps = list(jumps)
        self.t = [0.0] + [yrs(d) for d in pillars]
        S = [1.0] + [v / self.J(d) for d, v in zip(pillars, dfs)]
        k = None if step_end is None else 1 + list(pillars).index(step_end)
        if kind in ("LOG_LINEAR_DF", "LINEAR_ZERO"):
            self.old = RT.Curve(AS, list(pillars), [v / self.J(d) for d, v in zip(pillars, dfs)], kind)
            self.ip = None
        else:
            self.ip = make(kind, self.t, S, tension=tension, k=k)
        self.kind = kind

    def J(self, d):
        return math.prod(f for jd, f in self.jumps if jd < d)

    def lnS(self, t):
        if self.ip:
            return self.ip.ln_s(t)
        return math.log(self.old.df(AS + timedelta(days=round(t * 365))))

    def df(self, d):
        return math.exp(self.lnS(yrs(d))) * self.J(d)

    def fwd(self, d):
        t = yrs(d)
        if self.ip:
            return self.ip.fwd(t)
        T, D = self.old.t, self.old.d
        if self.kind == "LOG_LINEAR_DF":
            i = next((k for k in range(len(T) - 1) if t < T[k + 1]), len(T) - 2)
            return math.log(D[i] / D[i + 1]) / (T[i + 1] - T[i])
        # LINEAR_ZERO: z(t) + t z'(t), right-hand slope; flat first segment; last-segment discrete forward beyond
        if t >= T[-1]:
            return -math.log(D[-1] / D[-2]) / (T[-1] - T[-2])
        i = next(k for k in range(len(T) - 1) if t < T[k + 1])
        z = [(-math.log(D[k]) / T[k]) if k else -math.log(D[1]) / T[1] for k in range(len(T))]
        sl = (z[i + 1] - z[i]) / (T[i + 1] - T[i])
        return z[i] + sl * (t - T[i]) + t * sl


def bootstrap(conv, kind, quotes, tension=None, step_end_idx=None, jumps=()):
    per = [RT.ois_periods(conv, AS, t) for t, _ in quotes]
    pil = [p[-1][2] for p in per]
    se = pil[step_end_idx] if step_end_idx is not None else None
    x = np.array([-r * yrs(d) for (_, r), d in zip(quotes, pil)])

    def res(x):
        c = CurveF(pil, np.exp(x), kind, tension, se, jumps)
        return np.array([RT.ois_par(conv, p, c) - r for p, (_, r) in zip(per, quotes)])
    for _ in range(40):
        r0 = res(x)
        if max(abs(r0)) < 2e-16:
            break
        Jm = np.column_stack([(res(x + h) - res(x - h)) / 2e-7 for h in np.eye(len(x)) * 1e-7])
        x = x - np.linalg.solve(Jm, r0)
    err = max(abs(res(x)))
    assert err < 1e-14, (conv, kind, err)  # the Hyman filter is not smooth: Newton can stall near 2e-15
    return pil, [float(v) for v in np.exp(x)], se


def grid_dates(last):
    out = [AS + timedelta(days=round(0.15 * k * 365)) for k in range(1, 201)]
    return out + [last, last + timedelta(days=1), last + timedelta(days=5 * 365)]


def inspect(c, dates):
    dfs = [c.df(d) for d in dates]
    return {"discount_factors": dfs, "zero_rates": [None if d == AS else -math.log(v) / yrs(d) for d, v in zip(dates, dfs)],
            "instantaneous_forwards": [c.fwd(d) for d in dates]}


def curve_obj(pil, dfs, kind, tension=None, se=None, jumps=()):
    o = {"as_of": AS.isoformat(), "interpolation": kind, "pillars": [{"date": d.isoformat(), "discount_factor": v} for d, v in zip(pil, dfs)]}
    if jumps:
        o["jumps"] = [{"date": d.isoformat(), "factor": f} for d, f in jumps]
    if tension is not None:
        o["tension"] = tension
    if se is not None:
        o["step_end"] = se.isoformat()
    return o


def gap(a, b):
    return max(abs(x - y) for x, y in zip(a, b) if x is not None)


def main():
    import gen_stage_d
    gen_stage_d.add_estr() if hasattr(gen_stage_d, "add_estr") else RT.CONV.setdefault("ESTR", dict(gen_stage_d.ESTR))
    s = Suite("curve_f", "specifications/02-curves/curve-framework.md", G)
    bop, iop = "rates.ois.bootstrap", "rates.curve.inspect"
    turn = [(date(2026, 12, 31), math.exp(-0.0025 * 1 / 365))]
    builds, hyman, fpos = [], [], []
    for conv in ("SOFR", "SONIA", "ESTR"):
        for kind in ("MONOTONE_CONVEX", "MONOTONIC_LOG_CUBIC"):
            builds.append((conv, kind, {}))
    builds += [("SOFR", "MONOTONIC_LOG_CUBIC", {"jumps": turn}), ("SOFR", "TENSION_SPLINE", {"tension": 0.5}),
               ("SOFR", "HYBRID", {"step_end_idx": 2})]
    # sweep: 12 more shapes per convention family (seeded perturbations of the base quotes), MC and MLC, all QuantLib-checkable
    rng = np.random.default_rng(20261109)
    for k in range(12):
        conv = ("SOFR", "SONIA", "ESTR")[k % 3]
        base = QUOTES[conv]
        tilt, curv = rng.uniform(-.01, .01), rng.uniform(-.008, .008)
        qs = [(t, round(r + tilt * (j / len(base)) + curv * math.sin(math.pi * j / len(base)) + rng.normal(0, .0004), 6)) for j, (t, r) in enumerate(base)]
        QUOTES[f"{conv}-{k}"] = qs
        for kind in ("MONOTONE_CONVEX", "MONOTONIC_LOG_CUBIC"):
            builds.append((f"{conv}-{k}", kind, {}))
    for convk, kind, kw in builds:
        conv = convk.split("-")[0]
        q = QUOTES[convk]
        pil, dfs, se = bootstrap(conv, kind, q, kw.get("tension"), kw.get("step_end_idx"), kw.get("jumps", ()))
        inp = {"convention": conv, "as_of": AS.isoformat(), "quotes": [{"tenor": t, "rate": r} for t, r in q], "interpolation": kind, "method": "GLOBAL"}
        if "jumps" in kw:
            inp["jumps"] = [{"date": d.isoformat(), "factor": f} for d, f in kw["jumps"]]
        if "tension" in kw:
            inp["tension"] = kw["tension"]
        if se is not None:
            inp["step_end"] = se.isoformat()
        tags = ["curve", "bootstrap", kind.lower(), conv.lower(), "stage-f"] + (["jumps"] if "jumps" in kw else [])
        s.add(bop, inp, {"pillars": [{"date": d.isoformat(), "discount_factor": v} for d, v in zip(pil, dfs)]}, cls=I,
              verified=["independent-replay newton 1e-14"], tags=tags, description=f"{convk} {kind} global build")
        c = CurveF(pil, dfs, kind, kw.get("tension"), se, kw.get("jumps", ()))
        ds = grid_dates(pil[-1])
        out = inspect(c, ds)
        s.add(iop, {"curve": curve_obj(pil, dfs, kind, kw.get("tension"), se, kw.get("jumps", ())), "dates": [d.isoformat() for d in ds]}, out, cls=I,
              verified=["independent-replay"], tags=["curve", "inspect", kind.lower(), conv.lower(), "stage-f"], description=f"{convk} {kind}: 200 dates to 30y, last pillar, extrapolation")
        # wrong conventions
        if kind == "MONOTONE_CONVEX":
            from qf_oracle.interp_f import MonotoneConvex
            c2 = CurveF(pil, dfs, kind)
            c2.ip = MonotoneConvex(c.t, [1.0] + list(dfs), force_positive=True)
            fpos.append((convk, gap(inspect(c2, ds)["discount_factors"], out["discount_factors"])))
        if kind == "MONOTONIC_LOG_CUBIC" and not kw:
            from qf_oracle.interp_f import MonotonicLogCubic
            c2 = CurveF(pil, dfs, kind)
            c2.ip = MonotonicLogCubic(c.t, [1.0] + list(dfs), monotonic=False)
            hyman.append((conv, gap(inspect(c2, ds)["instantaneous_forwards"], out["instantaneous_forwards"])))
        if kind == "HYBRID":
            c2 = CurveF(pil, dfs, "MONOTONE_CONVEX")
            caught("SOFR hybrid: smooth part on all nodes", gap(inspect(c2, ds)["instantaneous_forwards"], out["instantaneous_forwards"]), 1e-9)
        if kind == "TENSION_SPLINE":
            c2 = CurveF(pil, dfs, kind, tension=1e-6)
            caught("SOFR tension: plain cubic spline", gap(inspect(c2, ds)["instantaneous_forwards"], out["instantaneous_forwards"]), 1e-9)
    fc = max(fpos, key=lambda x: x[1])
    caught(f"{fc[0]} MC: QuantLib forcePositive true (binds on {sum(g > 1e-10 for _, g in fpos)} of {len(fpos)} builds)", fc[1], 1e-10)
    note(f"curve_f: Hyman filter gap by OIS build (zero means the filter does not bind there): {hyman}")
    # a kinked curve on which the filter binds: discrete forwards 5% then 0.2% then 4%
    from qf_oracle.interp_f import MonotonicLogCubic
    kt = [.25, .5, 1, 1.5, 2, 3, 5, 10]
    kf = [.05, .05, .002, .002, .002, .04, .04, .04]
    kp = [AS + timedelta(days=round(t * 365)) for t in kt]
    lnS, prev, kd = 0.0, AS, []
    for d, fw in zip(kp, kf):
        lnS -= fw * (d - prev).days / 365
        kd.append(math.exp(lnS))
        prev = d
    ck = CurveF(kp, kd, "MONOTONIC_LOG_CUBIC")
    dk = grid_dates(kp[-1])[:70] + [kp[-1]]
    ok = inspect(ck, dk)
    s.add(iop, {"curve": curve_obj(kp, kd, "MONOTONIC_LOG_CUBIC"), "dates": [d.isoformat() for d in dk]}, ok, cls=I, verified=["independent-replay"],
          tags=["curve", "inspect", "monotonic_log_cubic", "hyman-binds", "stage-f"], description="kinked forwards (5%, 0.2%, 4%): the Hyman filter changes slopes")
    c2 = CurveF(kp, kd, "MONOTONIC_LOG_CUBIC")
    c2.ip = MonotonicLogCubic(ck.t, [1.0] + kd, monotonic=False)
    caught("kinked MLC: no Hyman filter", gap(inspect(c2, dk)["instantaneous_forwards"], ok["instantaneous_forwards"]), 1e-10 + 1e-8 * 0.05)
    # fixed pillars: every interpolation, including the stage B ones (inspect is new for them too)
    tt = [1 / 12, .25, .5, 1, 2, 3, 5, 7, 10, 15, 20, 30]
    zz = [.0430, .0425, .0415, .0395, .0370, .0360, .0355, .0358, .0365, .0378, .0383, .0375]
    pil = [AS + timedelta(days=round(t * 365)) for t in tt]
    dfs = [math.exp(-z * yrs(d)) for z, d in zip(zz, pil)]
    ds = grid_dates(pil[-1])
    fixed = [("LOG_LINEAR_DF", {}), ("LINEAR_ZERO", {}), ("MONOTONE_CONVEX", {}), ("MONOTONIC_LOG_CUBIC", {}),
             ("TENSION_SPLINE", {"tension": 0.01}), ("TENSION_SPLINE", {"tension": 1.0}), ("TENSION_SPLINE", {"tension": 50.0}),
             ("HYBRID", {"se": pil[3]}), ("HYBRID", {"se": pil[-1]})]
    for kind, kw in fixed:
        c = CurveF(pil, dfs, kind, kw.get("tension"), kw.get("se"))
        out = inspect(c, ds)
        s.add(iop, {"curve": curve_obj(pil, dfs, kind, kw.get("tension"), kw.get("se")), "dates": [d.isoformat() for d in ds]}, out, cls=I,
              verified=["independent-replay"], tags=["curve", "inspect", kind.lower(), "fixed-pillars", "stage-f"], description=f"fixed pillars, {kind} {kw or ''}")
        assert min(out["instantaneous_forwards"]) > 0, kind
    # locality: pillar 6 (5y) moved by 1e-4 in S
    dfb = list(dfs)
    dfb[6] *= math.exp(-1e-4)
    for kind in ("MONOTONE_CONVEX", "HYBRID"):
        kw = {"se": pil[3]} if kind == "HYBRID" else {}
        c0, c1 = CurveF(pil, dfs, kind, None, kw.get("se")), CurveF(pil, dfb, kind, None, kw.get("se"))
        o1 = inspect(c1, ds)
        lo, hi = (yrs(pil[4]), yrs(pil[8])) if kind == "MONOTONE_CONVEX" else (yrs(pil[3]), 99)
        for d, a, b in zip(ds, inspect(c0, ds)["instantaneous_forwards"], o1["instantaneous_forwards"]):
            if not (lo <= yrs(d) < hi):
                assert abs(a - b) <= 1e-15, (kind, d, a - b)
        s.add(iop, {"curve": curve_obj(pil, dfb, kind, None, kw.get("se")), "dates": [d.isoformat() for d in ds]}, o1, cls=I, verified=["independent-replay"],
              tags=["curve", "inspect", "locality", kind.lower(), "stage-f"], description=f"{kind}: 5y pillar moved by 1e-4 in ln S; forwards outside sections 5 to 8 unchanged")
    # errors
    base = curve_obj(pil, dfs, "TENSION_SPLINE", 1.0)
    for d, chg, code in (("tension missing", {"tension": None}, "E_INPUT"), ("tension zero", {"tension": 0.0}, "E_DOMAIN"),
                         ("tension above 1000", {"tension": 1001.0}, "E_DOMAIN"),
                         ("hybrid step_end not a pillar", {"interpolation": "HYBRID", "step_end": "2027-01-01"}, "E_INPUT"),
                         ("hybrid without step_end", {"interpolation": "HYBRID"}, "E_INPUT")):
        cur = {**base, **chg}
        if cur.get("tension") is None:
            cur.pop("tension")
        if d == "hybrid without step_end":
            cur.pop("tension")
        s.add(iop, {"curve": cur, "dates": ["2030-01-01"]}, error=code, cls=E, tags=["invalid", "stage-f"], description=d)
    s.add(iop, {"curve": curve_obj(pil, dfs, "MONOTONE_CONVEX"), "dates": ["2026-11-08"]}, error="E_OUT_OF_RANGE", cls=E, tags=["invalid", "stage-f"],
          description="date before as_of")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_f"
    for c in s.cases:
        c["tags"].append("synthetic")
    s.write()
    common.GOLDEN = keep
    note(f"curve_f: {len(s.cases)} cases, {len(MUT)} wrong conventions caught")


def caught(name, g, tol):
    assert g > tol, f"curve_f: '{name}' not caught: {g:.3e} <= {tol:.3e}"
    MUT.append((name, g))


if __name__ == "__main__":
    main()
