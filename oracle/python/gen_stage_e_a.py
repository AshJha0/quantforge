"""Stage E golden cases, spec A slices (E1, E2, E3, E5). Writes datasets/golden/stage_e/*.json.

All market data is synthetic. Rules as stage D: every value case is checked against a second route
(QuantLib through qf_oracle/convmap_e_a.py, an mpmath replay, or a closed form), and each suite stops
if a tolerance would let a named wrong convention through (`caught`). Booleans and violation lists are
guarded: the generator stops if any compared quantity sits near its threshold, so no golden depends on
libm last-digit rounding. No Monte Carlo, no iteration-path dependence: fits use exact quotes from known
parameters and are judged on parameters within a stated limit.

Run: cd oracle/python && uv run python -W ignore gen_stage_e_a.py [E1|E2|E3|E5 ...]
"""
import math
import sys

import mpmath as mp
import numpy as np

from qf_oracle import common
from qf_oracle.common import Suite, note
from qf_oracle import vol as V

G = "oracle/python/gen_stage_e_a.py"
E, A, I, R, Q, F, N = "date_and_convention", "simple_analytic", "interpolation", "root_finding", "quadrature", "fourier", "numerical_scheme"
QLV = "quantlib-1.44"
MUTANTS = []


def S(name, spec):
    return Suite(name, f"specifications/{spec}", G)


def write(s):
    keep = common.GOLDEN
    for c in s.cases:
        if "synthetic" not in c["tags"]:
            c["tags"].append("synthetic")
    common.GOLDEN = keep.parent / "stage_e"
    s.write()
    common.GOLDEN = keep


def caught(suite, name, gap, tol):
    assert gap > tol, f"{suite}: mutant '{name}' is not caught: gap {gap:.3e}, tolerance {tol:.3e}"
    MUTANTS.append((suite, name, gap))


def away(x, thr, eps, what):
    assert abs(x - thr) > eps, f"guard: {what} = {x!r} within {eps} of {thr}"


# ---------------------------------------------------------------- E1 helpers (spec 05-volatility/arb-free-surfaces.md)
def P5(d):
    return (d["a"], d["b"], d["rho"], d["m"], d["sigma"])


def svi(a, b, rho, m, sigma):
    return {"a": a, "b": b, "rho": rho, "m": m, "sigma": sigma}


def svi_d(P, k):
    """w, w', w'' of raw SVI at k."""
    a, b, rho, m, sg = P
    x = k - m
    R = math.sqrt(x * x + sg * sg)
    return a + b * (rho * x + R), b * (rho + x / R), b * sg * sg / R ** 3


def gfun(k, w, w1, w2):
    return (1 - k * w1 / (2 * w)) ** 2 - w1 * w1 / 4 * (1 / w + .25) + w2 / 2


def wings(P):
    """(left slope, left const, right slope, right const) of the asymptotes in |k|."""
    a, b, rho, m, sg = P
    return b * (1 - rho), a + b * (1 - rho) * m, b * (1 + rho), a - b * (1 + rho) * m


def surface_check(slices, ks, guard=True):
    Ps = [P5(s["svi"]) for s in slices]
    bf, cal, wing = [], [], []
    for j, P in enumerate(Ps):
        for i, k in enumerate(ks):
            w, w1, w2 = svi_d(P, k)
            g = gfun(k, w, w1, w2)
            if guard:
                away(g, 0, 1e-6, f"g slice {j} k {k}")
            if g < 0:
                bf.append({"expiry_index": j, "k_index": i})
    for j in range(1, len(Ps)):
        for i, k in enumerate(ks):
            d = svi_d(Ps[j], k)[0] - svi_d(Ps[j - 1], k)[0]
            if guard:
                away(d, 0, 1e-9, f"calendar gap slice {j} k {k}")
            if d < 0:
                cal.append({"expiry_index": j, "k_index": i})
    for j, P in enumerate(Ps):
        sl, cl, sr, cr = wings(P)
        for side, s_ in (("LEFT", sl), ("RIGHT", sr)):
            if guard and s_ != 2.0:
                away(s_, 2, 1e-6, "Lee slope")
            if s_ >= 2:   # ruling E-A15: GJ14 Lemma 2.2 needs slope strictly below 2
                wing.append({"expiry_index": j, "side": side, "kind": "LEE"})
        if j:
            pl, pcl, pr, pcr = wings(Ps[j - 1])
            for side, s_, c_, ps, pc in (("LEFT", sl, cl, pl, pcl), ("RIGHT", sr, cr, pr, pcr)):
                if s_ == ps:
                    if guard:
                        away(c_ - pc, 0, 1e-6, "wing const")
                    bad = c_ < pc
                else:
                    if guard:
                        away(s_ - ps, 0, 1e-6, "wing slope gap")
                    bad = s_ < ps
                if bad:
                    wing.append({"expiry_index": j, "side": side, "kind": "CALENDAR"})
    return {"butterfly_violations": bf, "calendar_violations": cal, "wing_violations": wing, "arbitrage_free": not (bf or cal or wing)}


def surf_w(slices, T, k, right=True):
    """Total variance and derivatives (w, w_k, w_kk, w_T) on an SVI-slice surface, linear in T (E-A3)."""
    Ts = [s["expiry_years"] for s in slices]
    Ps = [P5(s["svi"]) for s in slices]
    n = len(Ts)
    if T < Ts[0] or n == 1 or T >= Ts[-1]:
        j = 0 if T < Ts[0] else n - 1
        w, w1, w2 = svi_d(Ps[j], k)
        f = T / Ts[j]
        return w * f, w1 * f, w2 * f, w / Ts[j]
    j = max(i for i in range(n - 1) if (Ts[i] <= T if right else Ts[i] < T))
    lam = (T - Ts[j]) / (Ts[j + 1] - Ts[j])
    a, b = svi_d(Ps[j], k), svi_d(Ps[j + 1], k)
    return tuple((1 - lam) * x + lam * y for x, y in zip(a, b)) + ((b[0] - a[0]) / (Ts[j + 1] - Ts[j]),)


def dupire(slices, T, k, right=True):
    w, w1, w2, wT = surf_w(slices, T, k, right)
    g = gfun(k, w, w1, w2)
    return w, g, wT


def mp_dupire(slices, T, k):
    """Independent route: Dupire from undiscounted Black call prices, F = 1, r = q = 0, derivatives at 40 digits."""
    mp.mp.dps = 40
    Ts = [mp.mpf(s["expiry_years"]) for s in slices]
    Ps = [[mp.mpf(x) for x in P5(s["svi"])] for s in slices]

    def wsl(P, kk):
        a, b, rho, m, sg = P
        return a + b * (rho * (kk - m) + mp.sqrt((kk - m) ** 2 + sg ** 2))

    def W(TT, kk):
        n = len(Ts)
        if TT < Ts[0] or n == 1 or TT >= Ts[-1]:
            j = 0 if TT < Ts[0] else n - 1
            return wsl(Ps[j], kk) * TT / Ts[j]
        j = max(i for i in range(n - 1) if Ts[i] <= TT)
        lam = (TT - Ts[j]) / (Ts[j + 1] - Ts[j])
        return (1 - lam) * wsl(Ps[j], kk) + lam * wsl(Ps[j + 1], kk)

    def C(K, TT):
        w = W(TT, mp.log(K))
        s = mp.sqrt(w)
        d1 = -mp.log(K) / s + s / 2
        return mp.ncdf(d1) - K * mp.ncdf(d1 - s)
    K0, T0 = mp.e ** mp.mpf(k), mp.mpf(T)
    cT = mp.diff(lambda t: C(K0, t), T0, direction=1)
    cKK = mp.diff(lambda x: C(x, T0), K0, 2)
    return float(mp.sqrt(2 * cT / (K0 ** 2 * cKK)))


SVI_A = svi(0.02, 0.10, -0.40, 0.02, 0.20)     # 3m
SVI_B = svi(0.035, 0.11, -0.35, 0.03, 0.25)    # 1y
SVI_C = svi(0.06, 0.12, -0.30, 0.04, 0.30)     # 2y
VOGT = svi(-0.0410, 0.1331, 0.3060, 0.3586, 0.4153)  # Gatheral-Jacquier 2014, butterfly arbitrage
KS = [-0.6, -0.4, -0.2, -0.1, 0.0, 0.1, 0.2, 0.4, 0.6]
SURF = [{"expiry_years": 0.25, "svi": SVI_A}, {"expiry_years": 1.0, "svi": SVI_B}, {"expiry_years": 2.0, "svi": SVI_C}]


def e1_surf():
    s = S("surf_e", "05-volatility/arb-free-surfaces.md")
    op = "vol.svi.surface_check"
    vq = [QLV, "analytic"]

    def add(slices, ks, tags, desc=None, verified=vq, reject=False):
        out = surface_check(slices, ks)
        if reject and not out["arbitrage_free"]:
            s.add(op, {"slices": slices, "log_moneyness": ks, "reject": True}, error="E_ARBITRAGE", cls=E, tags=tags + ["reject"], description=desc)
        else:
            s.add(op, {"slices": slices, "log_moneyness": ks, "reject": reject}, out, cls=E, verified=verified, tags=tags, description=desc)
        return out
    o = add(SURF, KS, ["clean"], "three SVI slices, no arbitrage")
    assert o["arbitrage_free"]
    add(SURF, KS, ["clean", "reject"], "reject on a clean surface returns the result", reject=True)
    add(SURF[1:], [-0.3, -0.05, 0.0, 0.05, 0.3], ["clean"], "two slices, fine grid near the money")
    add([SURF[2]], [-1.0, -0.5, 0.0, 0.5, 1.0], ["clean", "one-slice"], "one slice: butterfly and Lee only")
    # Butterfly: Vogt slice at T = 1 on a grid where g < 0 near k = 0.8..1.2 (published counterexample).
    kv = [-0.4, 0.0, 0.4, 0.8, 1.0, 1.2, 1.6]
    o = add([{"expiry_years": 1.0, "svi": VOGT}], kv, ["arbitrage", "butterfly"], "Vogt parameters: butterfly arbitrage", verified=["published-counterexample", "analytic"])
    assert o["butterfly_violations"] and not o["arbitrage_free"]
    add([{"expiry_years": 1.0, "svi": VOGT}], kv, ["arbitrage", "butterfly"], reject=True, desc="Vogt parameters rejected")
    # Calendar crossing: the 1y slice moved down in the wings so it dips below 3m on the left only.
    low = svi(0.030, 0.06, -0.10, 0.03, 0.25)
    o = add([SURF[0], {"expiry_years": 1.0, "svi": low}], KS, ["arbitrage", "calendar"], "1y slice below 3m in the left wing")
    assert o["calendar_violations"]
    add([SURF[0], {"expiry_years": 1.0, "svi": low}], KS, ["arbitrage", "calendar"], reject=True, desc="calendar crossing rejected")
    # Wings: Lee bound broken on the right; a wing calendar break the grid does not see.
    lee = svi(0.02, 1.50, 0.50, 0.0, 0.05)
    o = add([{"expiry_years": 0.5, "svi": lee}], [-0.05, 0.0, 0.05], ["arbitrage", "wing", "lee"], "b(1+rho) = 2.25 > 2: Lee moment bound")
    assert o["wing_violations"] == [{"expiry_index": 0, "side": "RIGHT", "kind": "LEE"}], o
    w1, w2 = svi(0.03, 0.20, 0.0, 0.0, 0.2), svi(0.05, 0.15, 0.0, 0.0, 0.2)
    o = add([{"expiry_years": 0.5, "svi": w1}, {"expiry_years": 1.0, "svi": w2}], [-0.2, 0.0, 0.2], ["arbitrage", "wing", "calendar"],
            "later slice has flatter wings: crosses beyond the grid")
    assert not o["calendar_violations"] and len(o["wing_violations"]) == 2, o
    # Equal slopes (exact in binary64: b = 0.5, rho = 0.25 both), tie broken on the asymptote constant.
    t1, t2 = svi(0.02, 0.5, 0.25, 0.0, 0.1), svi(0.03, 0.5, 0.25, 0.1, 0.1)
    o = add([{"expiry_years": 0.5, "svi": t1}, {"expiry_years": 1.0, "svi": t2}], [-0.1, 0.0, 0.1], ["wing", "tie"], "equal wing slopes: constants decide")
    assert o["wing_violations"] == [{"expiry_index": 1, "side": "RIGHT", "kind": "CALENDAR"}], o
    # Wrong conventions.
    vols_cmp = [(math.sqrt(svi_d(P5(low), k)[0] / 1.0), math.sqrt(svi_d(P5(SVI_A), k)[0] / .25)) for k in KS]
    caught("surf_e", "calendar on implied vol instead of total variance", sum(1 for a, b in vols_cmp if a < b) - len(surface_check([SURF[0], {"expiry_years": 1.0, "svi": low}], KS)["calendar_violations"]), 0)
    caught("surf_e", "Lee bound 4 (variance-slope misread) passes the 2.25 slice", 2.25 - 2.0, 0)
    # Errors.
    s.add(op, {"slices": [SURF[1], SURF[0]], "log_moneyness": KS, "reject": False}, error="E_INPUT", cls=E, tags=["invalid"], description="expiries not increasing")
    s.add(op, {"slices": SURF, "log_moneyness": [0.1, 0.0], "reject": False}, error="E_INPUT", cls=E, tags=["invalid"], description="grid not increasing")
    s.add(op, {"slices": SURF, "log_moneyness": [], "reject": False}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {"slices": [], "log_moneyness": KS, "reject": False}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {"slices": [{"expiry_years": 1.0, "svi": svi(0.02, 0.1, 1.0, 0.0, 0.2)}], "log_moneyness": KS, "reject": False}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(op, {"slices": [{"expiry_years": 0.0, "svi": SVI_A}], "log_moneyness": KS, "reject": False}, error="E_DOMAIN", cls=E, tags=["invalid"])

    # SSVI slice to raw SVI (Gatheral-Jacquier 2014, section 3).
    op = "vol.ssvi.to_svi"
    for rho, eta, gam, th in ((-0.7, 1.2, 0.4, 0.04), (-0.3, 0.8, 0.5, 0.25), (0.0, 1.0, 1.0, 0.1), (0.4, 1.5, 0.2, 0.01)):
        ph = V.ssvi_phi(th, eta, gam)
        P = svi(th * (1 - rho * rho) / 2, th * ph / 2, rho, -rho / ph, math.sqrt(1 - rho * rho) / ph)
        for k in (-0.5, -0.1, 0.0, 0.2, 0.7):
            assert abs(V.svi_w(P5(P), k) - V.ssvi_w(k, th, rho, eta, gam)) < 1e-15
        s.add(op, {"rho": rho, "eta": eta, "gamma": gam, "theta": th}, {"svi": P}, cls=A, verified=["analytic", "replay-ssvi-evaluate"], tags=["ssvi"])
    caught("surf_e", "m = +rho/phi", abs(V.svi_w((P["a"], P["b"], P["rho"], -P["m"], P["sigma"]), 0.3) - V.ssvi_w(0.3, th, rho, eta, gam)), 1e-10)
    s.add(op, {"rho": 1.0, "eta": 1.0, "gamma": 0.5, "theta": 0.04}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(op, {"rho": 0.0, "eta": 1.0, "gamma": 0.5, "theta": 0.0}, error="E_DOMAIN", cls=E, tags=["invalid"])

    # Surface fit: per-slice SVI fit (stage C vol.svi.calibrate rule) on one shared grid, then the surface check.
    op = "vol.svi.fit_surface"
    kf = [-0.5, -0.3, -0.15, -0.05, 0.0, 0.05, 0.15, 0.3, 0.5]
    for slices, rej, tag in ((SURF, False, "clean"), ([SURF[0], {"expiry_years": 1.0, "svi": low}], False, "calendar"), ([SURF[0], {"expiry_years": 1.0, "svi": low}], True, "calendar")):
        rows = [[V.svi_w(P5(sl["svi"]), k) for k in kf] for sl in slices]
        fitted, rm = [], []
        for sl, row in zip(slices, rows):
            x, e, spread = V.svi_fit(kf, row)
            assert e < 1e-9 and spread < 1e-7, (e, spread)
            assert max(abs(u - v) for u, v in zip(x, P5(sl["svi"]))) < 1e-7
            fitted.append({"expiry_years": sl["expiry_years"], "svi": sl["svi"]})
            rm.append(0.0)
        chk = surface_check(fitted, kf)
        inp = {"expiry_years": [sl["expiry_years"] for sl in slices], "log_moneyness": kf, "total_variance": rows, "reject": rej}
        if rej and not chk["arbitrage_free"]:
            s.add(op, inp, error="E_ARBITRAGE", cls=E, tags=["fit", "reject", tag])
            continue
        s.add(op, inp, {"slices": fitted, "rmse": rm, **chk}, cls="calibration", verified=["known-truth", "scipy-least-squares-4-starts"], tags=["fit", tag],
              limit={"absolute": 1e-6, "relative": 0.0, "reason": "fit from exact quotes: parameters within 1e-6 (stage C SVI target); lists exact"})
    s.add(op, {"expiry_years": [1.0], "log_moneyness": kf[:4], "total_variance": [[0.04] * 4], "reject": False}, error="E_INPUT", cls=E, tags=["invalid"], description="fewer than 5 points")
    s.add(op, {"expiry_years": [1.0, 0.5], "log_moneyness": kf, "total_variance": [[0.04] * 9, [0.03] * 9], "reject": False}, error="E_INPUT", cls=E, tags=["invalid"])
    # Audit rulings (R5, 2026-11-08), appended so earlier case ids stay put.
    op = "vol.svi.surface_check"
    edge = svi(0.02, 2.0, 0.0, 0.0, 0.05)   # b(1 +- rho) = 2 exactly in binary64
    o = add([{"expiry_years": 0.5, "svi": edge}], [-0.05, 0.0, 0.05], ["wing", "lee", "boundary", "ruling"], "slope exactly 2: flagged on both sides (E-A15)")
    assert o["wing_violations"] == [{"expiry_index": 0, "side": "LEFT", "kind": "LEE"}, {"expiry_index": 0, "side": "RIGHT", "kind": "LEE"}], o
    caught("surf_e", "Lee test strict (> 2) passes a slope of exactly 2", len(o["wing_violations"]), 0)
    s.add(op, {"slices": [{"expiry_years": 0.01 * (i + 1), "svi": SVI_A} for i in range(101)], "log_moneyness": KS, "reject": False}, error="E_LIMIT", cls=E, tags=["invalid", "limit", "ruling"], description="101 slices")
    s.add(op, {"slices": SURF, "log_moneyness": [i * 1e-4 for i in range(10001)], "reject": False}, error="E_LIMIT", cls=E, tags=["invalid", "limit", "ruling"], description="10,001 grid points")
    s.add(op, {"slices": SURF, "log_moneyness": KS}, error="E_SCHEMA", cls=E, tags=["invalid", "ruling"], description="reject missing")
    write(s)


def e1_lv():
    s = S("lv_e", "05-volatility/local-and-forward-vol.md")
    op = "vol.local.dupire"
    pts = [(0.1, 0.0), (0.25, -0.2), (0.5, 0.0), (0.5, 0.15), (1.0, -0.3), (1.0, 0.0), (1.5, 0.1), (2.0, 0.0), (3.0, -0.1)]
    out = {"total_variance": [], "implied_vol": [], "local_vol": []}
    for T, k in pts:
        w, g, wT = dupire(SURF, T, k)
        away(g, 0, 1e-4, "dupire g")
        assert wT > 1e-6
        lv = math.sqrt(wT / g)
        alt = mp_dupire(SURF, T, k)
        assert abs(lv - alt) < 1e-9 * lv, (T, k, lv, alt)
        out["total_variance"].append(w)
        out["implied_vol"].append(math.sqrt(w / T))
        out["local_vol"].append(lv)
    inp = {"slices": SURF, "points": [{"expiry_years": T, "log_moneyness": k} for T, k in pts]}
    s.add(op, inp, out, cls=I, verified=["analytic", "mpmath-price-dupire-40-digits"], tags=["dupire"], description="nodes use the right-hand interval; before and after the grid flat vol")
    caught("lv_e", "local variance = w_T (no smile terms)", abs(math.sqrt(dupire(SURF, 1.0, -0.3)[2]) - out["local_vol"][4]), 1e-8)
    caught("lv_e", "left-hand derivative at a node", abs(math.sqrt(dupire(SURF, 1.0, 0.0, right=False)[2] / dupire(SURF, 1.0, 0.0, right=False)[1]) - out["local_vol"][5]), 1e-8)
    # single slice: w = w1 T/T1, w_T = w1/T1.
    one = [{"expiry_years": 1.0, "svi": SVI_B}]
    p1 = [(0.5, -0.2), (1.0, 0.0), (2.0, 0.25)]
    o1 = {"total_variance": [], "implied_vol": [], "local_vol": []}
    for T, k in p1:
        w, g, wT = dupire(one, T, k)
        away(g, 0, 1e-4, "g")
        assert abs(math.sqrt(wT / g) - mp_dupire(one, T, k)) < 1e-9
        o1["total_variance"].append(w)
        o1["implied_vol"].append(math.sqrt(w / T))
        o1["local_vol"].append(math.sqrt(wT / g))
    s.add(op, {"slices": one, "points": [{"expiry_years": T, "log_moneyness": k} for T, k in p1]}, o1, cls=I, verified=["analytic", "mpmath-price-dupire-40-digits"], tags=["dupire", "one-slice"])
    low = svi(0.030, 0.06, -0.10, 0.03, 0.25)
    s.add(op, {"slices": [SURF[0], {"expiry_years": 1.0, "svi": low}], "points": [{"expiry_years": 0.5, "log_moneyness": -0.6}]}, error="E_ARBITRAGE", cls=E, tags=["arbitrage", "calendar"],
          description="w_T < 0 at this point")
    assert dupire([SURF[0], {"expiry_years": 1.0, "svi": low}], 0.5, -0.6)[2] < -1e-4
    gv = dupire([{"expiry_years": 1.0, "svi": VOGT}], 1.0, 1.0)[1]
    assert gv < -1e-4
    s.add(op, {"slices": [{"expiry_years": 1.0, "svi": VOGT}], "points": [{"expiry_years": 1.0, "log_moneyness": 1.0}]}, error="E_ARBITRAGE", cls=E, tags=["arbitrage", "butterfly"])
    s.add(op, {"slices": SURF, "points": []}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {"slices": SURF, "points": [{"expiry_years": 0.0, "log_moneyness": 0.0}]}, error="E_DOMAIN", cls=E, tags=["invalid"])

    # Forward vol between expiries.
    op = "vol.forward.vol"
    for days, vols in (([73, 182, 365, 730], [0.20, 0.21, 0.215, 0.22]), ([30, 91, 365], [0.30, 0.25, 0.22]), ([365, 730], [0.20, 0.20]),
                       ([7, 14, 30, 61], [0.45, 0.38, 0.33, 0.31]), ([91, 182, 273, 365, 547, 730, 1095, 1825], [0.18, 0.185, 0.19, 0.195, 0.2, 0.205, 0.21, 0.212]),
                       ([182, 365], [0.25, 0.1768])):
        Ts = [d / 365 for d in days]
        fv = [vols[0]] + [math.sqrt((vols[i] ** 2 * Ts[i] - vols[i - 1] ** 2 * Ts[i - 1]) / (Ts[i] - Ts[i - 1])) for i in range(1, len(Ts))]
        s.add(op, {"expiry_years": Ts, "vols": vols}, {"forward_vols": fv}, cls=A, verified=[QLV, "analytic"], tags=["forward-vol"])
    caught("lv_e", "forward vol linear in vol, not variance", abs((0.25 * 91 / 365 - 0.30 * 30 / 365) / (61 / 365) - math.sqrt((0.25 ** 2 * 91 - 0.3 ** 2 * 30) / 61)), 1e-8)
    s.add(op, {"expiry_years": [0.5, 1.0], "vols": [0.30, 0.20]}, error="E_ARBITRAGE", cls=E, tags=["arbitrage", "calendar"], description="total variance falls: 0.045 then 0.04")
    s.add(op, {"expiry_years": [1.0, 0.5], "vols": [0.2, 0.2]}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {"expiry_years": [0.5, 1.0], "vols": [0.2]}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {"expiry_years": [0.5, 1.0], "vols": [0.2, 0.0]}, error="E_DOMAIN", cls=E, tags=["invalid"])
    # Flat total variance with exact binary64 inputs: 0.5^2 x 0.25 = 0.25^2 x 1 = 0.0625, so forward variance is exactly 0.
    s.add(op, {"expiry_years": [0.25, 1.0], "vols": [0.5, 0.25]}, {"forward_vols": [0.5, 0.0]}, cls=A, verified=["analytic"], tags=["forward-vol", "zero"],
          description="flat total variance: forward vol 0 is allowed")

    # Smile dynamics.
    op = "vol.smile.dynamics"
    T, S0, S1, r, q = 0.5, 100.0, 103.0, 0.03, 0.01
    Ks = [85.0, 95.0, 100.0, 105.0, 115.0]
    Psl = P5(SVI_A)
    for sv, TT, SS1, rr, qq in ((SVI_A, T, S1, r, q), (SVI_B, 1.0, 96.0, 0.045, 0.0), (SVI_C, 2.0, 110.0, -0.005, 0.02)):
        for rule in ("STICKY_STRIKE", "STICKY_DELTA"):
            for ot in ("CALL", "PUT"):
                o = dyn(P5(sv), TT, S0, SS1, rr, qq, Ks, rule, ot)
                s.add(op, {"svi": sv, "expiry_years": TT, "spot": S0, "spot_shifted": SS1, "rate": rr, "dividend_yield": qq, "strikes": Ks, "rule": rule, "option_type": ot},
                      o, cls=I, verified=[QLV, "analytic", "mpmath-bump-delta"], tags=["smile-dynamics", rule.lower()] + (["negative-rate"] if rr < 0 else []))
    a = dyn(Psl, T, S0, S1, r, q, Ks, "STICKY_DELTA", "CALL")
    F1 = S1 * math.exp((r - q) * T)
    wrong = math.sqrt(V.svi_w(Psl, math.log(95.0 / S1)) / T)
    caught("lv_e", "sticky delta on spot moneyness K/S, not K/F", abs(wrong - a["vols_shifted"][1]), 1e-8)
    b = dyn(Psl, T, S0, S1, r, q, Ks, "STICKY_STRIKE", "CALL")
    caught("lv_e", "sticky delta delta = sticky strike delta (smile term dropped)", abs(a["deltas"][1] - b["deltas"][1]), 1e-8)
    base = {"svi": SVI_A, "expiry_years": T, "spot": S0, "spot_shifted": S1, "rate": r, "dividend_yield": q, "strikes": Ks, "rule": "STICKY_STRIKE", "option_type": "CALL"}
    s.add(op, {**base, "strikes": []}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {**base, "spot_shifted": 0.0}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(op, {**base, "strikes": [100.0, -5.0]}, error="E_DOMAIN", cls=E, tags=["invalid"])

    # Vol of vol.
    op = "vol.volofvol.measure"
    ser = [0.200, 0.205, 0.198, 0.210, 0.222, 0.215, 0.230, 0.226, 0.219, 0.224, 0.240, 0.233]
    for method in ("LOG", "ABSOLUTE"):
        for ppy in (252, 52):
            x = [math.log(b / a) if method == "LOG" else b - a for a, b in zip(ser, ser[1:])]
            m = math.fsum(x) / len(x)
            sd = math.sqrt(math.fsum((u - m) ** 2 for u in x) / (len(x) - 1))
            mpv = float(mp.sqrt(mp.mpf(ppy)) * mp.sqrt(mp.fsum([(mp.mpf(u) - mp.mpf(m)) ** 2 for u in x]) / (len(x) - 1)))
            assert abs(mpv - math.sqrt(ppy) * sd) < 1e-14
            s.add(op, {"vols": ser, "periods_per_year": ppy, "method": method}, {"vol_of_vol": math.sqrt(ppy) * sd, "mean_change": m}, cls="statistics", verified=[QLV, "mpmath"], tags=["vol-of-vol"])
            if method == "LOG" and ppy == 252:
                caught("lv_e", "population std (n, not n-1)", math.sqrt(ppy) * sd * (1 - math.sqrt((len(x) - 1) / len(x))), 1e-9)
                caught("lv_e", "not annualised", math.sqrt(ppy) * sd - sd, 1e-9)
    s.add(op, {"vols": [0.2, 0.21], "periods_per_year": 252, "method": "LOG"}, error="E_INPUT", cls=E, tags=["invalid"], description="at least 3 observations")
    s.add(op, {"vols": [0.2, 0.0, 0.21], "periods_per_year": 252, "method": "LOG"}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(op, {"vols": [0.2, 0.22, 0.21], "periods_per_year": 0, "method": "LOG"}, error="E_DOMAIN", cls=E, tags=["invalid"])
    # Audit rulings (R5, 2026-11-08), appended.
    s.add("vol.local.dupire", {"slices": SURF, "points": [{"expiry_years": 1.0, "log_moneyness": 0.0}] * 10001}, error="E_LIMIT", cls=E, tags=["invalid", "limit", "ruling"], description="10,001 points")
    s.add("vol.smile.dynamics", {**base, "rule": "STICKY_MONEYNESS"}, error="E_SCHEMA", cls=E, tags=["invalid", "ruling"], description="unlisted rule")
    s.add("vol.volofvol.measure", {"vols": ser, "periods_per_year": 252, "method": "PERCENT"}, error="E_SCHEMA", cls=E, tags=["invalid", "ruling"])
    s.add("vol.forward.vol", {"expiry_years": [], "vols": []}, error="E_INPUT", cls=E, tags=["invalid", "ruling"], description="empty term structure")
    write(s)


def ncdf(x):
    return 0.5 * math.erfc(-x / math.sqrt(2))


def bs(ot, S, K, T, r, q, v):
    F, D = S * math.exp((r - q) * T), math.exp(-r * T)
    sd = v * math.sqrt(T)
    d1 = math.log(F / K) / sd + sd / 2
    if ot == "CALL":
        return D * (F * ncdf(d1) - K * ncdf(d1 - sd)), math.exp(-q * T) * ncdf(d1), S * math.exp(-q * T) * math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi) * math.sqrt(T)
    return D * (K * ncdf(sd - d1) - F * ncdf(-d1)), -math.exp(-q * T) * ncdf(-d1), S * math.exp(-q * T) * math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi) * math.sqrt(T)


def dyn(P, T, S0, S1, r, q, Ks, rule, ot):
    F0, F1 = S0 * math.exp((r - q) * T), S1 * math.exp((r - q) * T)
    vb, vs, pb, ps, de = [], [], [], [], []
    for K in Ks:
        k0 = math.log(K / F0)
        w, w1, _ = svi_d(P, k0)
        v0 = math.sqrt(w / T)
        v1 = v0 if rule == "STICKY_STRIKE" else math.sqrt(svi_d(P, math.log(K / F1))[0] / T)
        p0, d0, vega = bs(ot, S0, K, T, r, q, v0)
        dvds = 0.0 if rule == "STICKY_STRIKE" else -(w1 / (2 * v0 * T)) / S0
        delta = d0 + vega * dvds
        # independent check: central bump of the full price, 40 digits
        mp.mp.dps = 40

        def price(Sx):
            Sx = mp.mpf(Sx)
            Fx = Sx * mp.e ** ((mp.mpf(r) - q) * T)
            kx = mp.log(mp.mpf(K) / (mp.mpf(F0) if rule == "STICKY_STRIKE" else Fx))
            a, b, rho, m, sg = [mp.mpf(z) for z in P]
            vx = mp.sqrt((a + b * (rho * (kx - m) + mp.sqrt((kx - m) ** 2 + sg ** 2))) / T)
            sd = vx * mp.sqrt(T)
            d1 = mp.log(Fx / K) / sd + sd / 2
            cl = mp.e ** (-mp.mpf(r) * T) * (Fx * mp.ncdf(d1) - K * mp.ncdf(d1 - sd))
            return cl if ot == "CALL" else cl - mp.e ** (-mp.mpf(r) * T) * (Fx - K)
        assert abs(float(mp.diff(price, mp.mpf(S0))) - delta) < 1e-12, (K, rule)
        vb.append(v0)
        vs.append(v1)
        pb.append(p0)
        ps.append(bs(ot, S1, K, T, r, q, v1)[0])
        de.append(delta)
    return {"vols_base": vb, "vols_shifted": vs, "prices_base": pb, "prices_shifted": ps, "deltas": de}


# ---------------------------------------------------------------- E3 FX smile (spec 05-volatility/fx-smile.md)
from scipy.optimize import brentq  # noqa: E402

DT = ("SPOT", "FORWARD", "SPOT_PA", "FORWARD_PA")


def fxm(S, T, rd, rf):
    return S * math.exp((rd - rf) * T), math.exp(-rd * T), math.exp(-rf * T)


def fx_delta(ot, dt, S, K, T, rd, rf, v):
    F, Dd, Df = fxm(S, T, rd, rf)
    p = 1 if ot == "CALL" else -1
    sd = v * math.sqrt(T)
    d1 = math.log(F / K) / sd + sd / 2
    d2 = d1 - sd
    return {"SPOT": p * Df * ncdf(p * d1), "FORWARD": p * ncdf(p * d1),
            "SPOT_PA": p * Df * K / F * ncdf(p * d2), "FORWARD_PA": p * K / F * ncdf(p * d2)}[dt]


def pa_kmax(S, T, rd, rf, v):
    """Strike of the largest premium-adjusted call delta: sd N(d2) = n(d2)."""
    F = fxm(S, T, rd, rf)[0]
    sd = v * math.sqrt(T)
    d2 = brentq(lambda d: sd * ncdf(d) - math.exp(-d * d / 2) / math.sqrt(2 * math.pi), -10, 10, xtol=1e-15)
    return F * math.exp(-sd * d2 - sd * sd / 2)


def fx_strike(ot, dt, S, T, rd, rf, v, delta):
    F = fxm(S, T, rd, rf)[0]
    f = lambda K: fx_delta(ot, dt, S, K, T, rd, rf, v) - delta  # noqa: E731
    lo, hi = F * 1e-4, F * 1e4
    if ot == "CALL" and dt.endswith("PA"):
        lo = pa_kmax(S, T, rd, rf, v)
        assert f(lo) > 1e-6, "PA call delta above its maximum"
    K = brentq(f, lo, hi, xtol=1e-15, rtol=1e-15, maxiter=500)
    h = K * 1e-6
    assert abs(f(K + h) - f(K - h)) / (2 * h) * K > 1e-3, "flat delta: strike ill-conditioned"
    return K


def atm_strike(at, dt, S, T, rd, rf, v):
    F = fxm(S, T, rd, rf)[0]
    if at == "SPOT":
        return S
    if at == "FORWARD":
        return F
    return F * math.exp((-0.5 if dt.endswith("PA") else 0.5) * v * v * T)


def gk(ot, S, K, T, rd, rf, v, N):
    F, Dd, Df = fxm(S, T, rd, rf)
    p = 1 if ot == "CALL" else -1
    sd = v * math.sqrt(T)
    d1 = math.log(F / K) / sd + sd / 2
    d2 = d1 - sd
    pr = p * Dd * (F * ncdf(p * d1) - K * ncdf(p * d2))
    nd1 = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)
    return {"price": N * pr, "premium_pct_foreign": pr / S, "forward": F, "delta": N * p * Df * ncdf(p * d1),
            "gamma": N * Df * nd1 / (S * sd), "vega": N * S * Df * nd1 * math.sqrt(T)}


FXM = [  # spot, days, rd, rf, vol: EURUSD-like, USDJPY-like (rd < rf), high-carry EM, long dated
    (1.0850, 91, 0.0430, 0.0310, 0.075),
    (151.20, 182, 0.0010, 0.0450, 0.105),
    (18.40, 365, 0.1050, 0.0430, 0.160),
    (1.2650, 1825, 0.0380, 0.0420, 0.090),
]


def e3_fx():
    s = S("fxs_e", "05-volatility/fx-smile.md")
    vq = [QLV, "analytic"]
    op = "fx.option.price"
    for S0, days, rd, rf, v in FXM:
        T = days / 365
        F = fxm(S0, T, rd, rf)[0]
        for ot, K in (("CALL", F * 1.03), ("PUT", F * 0.97), ("CALL", F * 0.9)):
            K = round(K, 4)
            s.add(op, {"spot": S0, "strike": K, "expiry_years": T, "domestic_rate": rd, "foreign_rate": rf, "vol": v, "option_type": ot, "notional": 1e6},
                  gk(ot, S0, K, T, rd, rf, v, 1e6), cls=A, verified=vq, tags=["garman-kohlhagen"],
                  limit={"absolute": 1e-6, "relative": 1e-10, "reason": "1e-6 currency units on 1m foreign notional"})
    S0, days, rd, rf, v = FXM[0]
    T = days / 365
    g = gk("CALL", S0, 1.10, T, rd, rf, v, 1e6)
    caught("fxs_e", "rates swapped (rf as domestic)", abs(gk("CALL", S0, 1.10, T, rf, rd, v, 1e6)["price"] - g["price"]), 1e-6 + 1e-10 * g["price"])
    caught("fxs_e", "delta discounted at rd", abs(g["delta"] * math.exp((rf - rd) * T) - g["delta"]), 1e-6 + 1e-10 * g["delta"])
    b = {"spot": S0, "strike": 1.1, "expiry_years": T, "domestic_rate": rd, "foreign_rate": rf, "vol": v, "option_type": "CALL", "notional": 1e6}
    for k_, val in (("strike", 0.0), ("vol", 0.0), ("expiry_years", 0.0), ("spot", -1.0), ("notional", 0.0)):
        s.add(op, {**b, k_: val}, error="E_DOMAIN", cls=E, tags=["invalid"])

    op = "fx.delta.from_strike"
    for S0, days, rd, rf, v in FXM:
        T = days / 365
        F = fxm(S0, T, rd, rf)[0]
        for ot, K in (("CALL", F * 1.04), ("PUT", F * 0.95)):
            K = round(K, 4)
            out = {"deltas": {dt: fx_delta(ot, dt, S0, K, T, rd, rf, v) for dt in DT}}
            s.add(op, {"spot": S0, "strike": K, "expiry_years": T, "domestic_rate": rd, "foreign_rate": rf, "vol": v, "option_type": ot}, out, cls=A, verified=vq, tags=["delta"])
    d = fx_delta("CALL", "SPOT", 18.4, 19.5, 1, .105, .043, .16)
    caught("fxs_e", "spot delta = forward delta (no foreign discount)", abs(fx_delta("CALL", "FORWARD", 18.4, 19.5, 1, .105, .043, .16) - d), 1e-10)
    caught("fxs_e", "premium adjustment omitted", abs(fx_delta("CALL", "SPOT_PA", 18.4, 19.5, 1, .105, .043, .16) - d), 1e-10)

    op = "fx.delta.to_strike"
    for S0, days, rd, rf, v in FXM:
        T = days / 365
        for ot, dl in (("CALL", 0.25), ("PUT", -0.25), ("CALL", 0.10), ("PUT", -0.10)):
            for dt in DT:
                K = fx_strike(ot, dt, S0, T, rd, rf, v, dl)
                s.add(op, {"spot": S0, "expiry_years": T, "domestic_rate": rd, "foreign_rate": rf, "vol": v, "option_type": ot, "delta": dl, "delta_type": dt},
                      {"strike": K}, cls=R, verified=vq, tags=["delta", dt.lower()], limit={"absolute": 1e-10, "relative": 1e-9, "reason": "strike to 1e-9 relative: far below a pip; QuantLib strikeFromDelta solves to about 1e-10 relative"})
    S0, days, rd, rf, v = FXM[2]
    T = days / 365
    kmax = pa_kmax(S0, T, rd, rf, v)
    dmax = fx_delta("CALL", "FORWARD_PA", S0, kmax, T, rd, rf, v)
    s.add(op, {"spot": S0, "expiry_years": T, "domestic_rate": rd, "foreign_rate": rf, "vol": v, "option_type": "CALL", "delta": round(dmax + 0.01, 2), "delta_type": "FORWARD_PA"},
          error="E_DOMAIN", cls=E, tags=["invalid", "premium-adjusted"], description="premium-adjusted call delta above its maximum")
    caught("fxs_e", "PA call root on the low-strike branch", abs(brentq(lambda K: fx_delta("CALL", "FORWARD_PA", S0, K, T, rd, rf, v) - .25, S0 * 1e-3, kmax) - fx_strike("CALL", "FORWARD_PA", S0, T, rd, rf, v, .25)), 1e-6)
    bb = {"spot": S0, "expiry_years": T, "domestic_rate": rd, "foreign_rate": rf, "vol": v, "option_type": "CALL", "delta": 0.25, "delta_type": "SPOT"}
    s.add(op, {**bb, "delta": -0.25}, error="E_DOMAIN", cls=E, tags=["invalid"], description="call delta must be positive")
    s.add(op, {**bb, "delta": 0.97}, error="E_DOMAIN", cls=E, tags=["invalid"], description="spot call delta at or above exp(-rf T)")
    s.add(op, {**bb, "option_type": "PUT", "delta": -1.0, "delta_type": "FORWARD"}, error="E_DOMAIN", cls=E, tags=["invalid"])

    op = "fx.atm.strike"
    for S0, days, rd, rf, v in FXM:
        T = days / 365
        for at, dt in (("DNS", "SPOT"), ("DNS", "FORWARD"), ("DNS", "SPOT_PA"), ("DNS", "FORWARD_PA"), ("FORWARD", "SPOT"), ("SPOT", "SPOT")):
            s.add(op, {"spot": S0, "expiry_years": T, "domestic_rate": rd, "foreign_rate": rf, "vol": v, "atm_type": at, "delta_type": dt},
                  {"strike": atm_strike(at, dt, S0, T, rd, rf, v)}, cls=A, verified=vq, tags=["atm", at.lower()])
    caught("fxs_e", "PA DNS with +sigma^2 T/2", abs(atm_strike("DNS", "SPOT", 18.4, 1.0, .105, .043, .16) - atm_strike("DNS", "SPOT_PA", 18.4, 1.0, .105, .043, .16)), 1e-10)

    op = "fx.smile.from_quotes"
    for (S0, days, rd, rf, atm), rr, bf, dl, dt, at in (
            (FXM[0], -0.0045, 0.0020, 0.25, "SPOT", "DNS"), (FXM[0], -0.0080, 0.0065, 0.10, "SPOT", "DNS"),
            (FXM[1], -0.0150, 0.0035, 0.25, "SPOT_PA", "DNS"), (FXM[1], -0.0300, 0.0110, 0.10, "FORWARD_PA", "DNS"),
            (FXM[2], 0.0250, 0.0060, 0.25, "FORWARD_PA", "DNS"), (FXM[3], -0.0060, 0.0030, 0.25, "FORWARD", "FORWARD")):
        T = days / 365
        cv, pv = atm + bf + rr / 2, atm + bf - rr / 2
        out = {"atm_strike": atm_strike(at, dt, S0, T, rd, rf, atm), "call_vol": cv, "put_vol": pv,
               "call_strike": fx_strike("CALL", dt, S0, T, rd, rf, cv, dl), "put_strike": fx_strike("PUT", dt, S0, T, rd, rf, pv, -dl)}
        s.add(op, {"spot": S0, "expiry_years": T, "domestic_rate": rd, "foreign_rate": rf, "atm_vol": atm, "rr": rr, "bf": bf, "delta": dl, "delta_type": dt, "atm_type": at},
              out, cls=R, verified=vq, tags=["rr-bf", dt.lower()], limit={"absolute": 1e-10, "relative": 1e-9, "reason": "strike to 1e-9 relative: far below a pip; QuantLib strikeFromDelta solves to about 1e-10 relative"})
    S0, days, rd, rf, atm = FXM[1]
    T = days / 365
    caught("fxs_e", "RR sign: call vol = atm + bf - rr/2", abs(fx_strike("CALL", "SPOT_PA", S0, T, rd, rf, atm + .0035 + .0075, .25) - fx_strike("CALL", "SPOT_PA", S0, T, rd, rf, atm + .0035 - .0075, .25)), 1e-8)
    q = {"spot": S0, "expiry_years": T, "domestic_rate": rd, "foreign_rate": rf, "atm_vol": atm, "rr": -0.015, "bf": 0.0035, "delta": 0.25, "delta_type": "SPOT", "atm_type": "DNS"}
    s.add(op, {**q, "bf": -0.2}, error="E_DOMAIN", cls=E, tags=["invalid"], description="a wing vol <= 0")
    s.add(op, {**q, "delta": 0.5}, error="E_DOMAIN", cls=E, tags=["invalid"], description="delta must be in (0, 0.5)")
    write(s)


# ---------------------------------------------------------------- E2 Heston, Bates, Merton, SLV (spec 05-volatility/heston-family.md)
import cmath  # noqa: E402

import QuantLib as ql  # noqa: E402

GL_T, GL_W = np.polynomial.legendre.leggauss(256)
GL_T, GL_W = (GL_T + 1) * 100, GL_W * 100   # nodes on (0, 200)


def phi_heston(u, T, v0, kappa, theta, xi, rho):
    """E[exp(i u X)], X = ln(S_T/F): Albrecher et al. 'little trap' form."""
    iu = 1j * u
    b = kappa - rho * xi * iu
    d = cmath.sqrt(b * b + xi * xi * (iu + u * u))
    g = (b - d) / (b + d)
    e = cmath.exp(-d * T)
    C = kappa / xi ** 2 * ((b - d) * T - 2 * cmath.log((1 - g * e) / (1 - g)))
    D = (b - d) / xi ** 2 * (1 - e) / (1 - g * e)
    return cmath.exp(C * theta + D * v0)


def phi_jump(u, T, lam, mu, delta):
    kbar = math.exp(mu + delta * delta / 2) - 1
    return cmath.exp(lam * T * (cmath.exp(1j * u * mu - delta * delta * u * u / 2) - 1 - 1j * u * kbar))


def lewis(phi, S, K, T, r, q, ot):
    """Call by Lewis (2001) single integral; Gauss-Legendre 256 nodes on u in (0, 200). Put by parity."""
    F = S * math.exp((r - q) * T)
    k = math.log(F / K)
    tot = 0.0
    for u, w in zip(GL_T, GL_W):
        tot += w * (cmath.exp(1j * u * k) * phi(u - 0.5j)).real / (u * u + 0.25)
    c = math.exp(-r * T) * (F - math.sqrt(F * K) / math.pi * tot)
    return c if ot == "CALL" else c - math.exp(-r * T) * (F - K)


def mp_lewis(phi_mp, S, K, T, r, q, ot):
    mp.mp.dps = 30
    F = mp.mpf(S) * mp.e ** ((mp.mpf(r) - q) * T)
    k = mp.log(F / K)
    I_ = mp.quad(lambda u: mp.re(mp.e ** (1j * u * k) * phi_mp(u - 0.5j)) / (u * u + 0.25), [0, 1, 10, 100, mp.inf])
    c = mp.e ** (-mp.mpf(r) * T) * (F - mp.sqrt(F * K) / mp.pi * I_)
    return float(c if ot == "CALL" else c - mp.e ** (-mp.mpf(r) * T) * (F - K))


def mp_phi_heston(T, v0, kappa, theta, xi, rho, lam=0.0, mu=0.0, delta=0.0):
    def f(u):
        iu = 1j * u
        b = kappa - rho * xi * iu
        d = mp.sqrt(b * b + xi * xi * (iu + u * u))
        g = (b - d) / (b + d)
        e = mp.e ** (-d * T)
        C = kappa / mp.mpf(xi) ** 2 * ((b - d) * T - 2 * mp.log((1 - g * e) / (1 - g)))
        D = (b - d) / mp.mpf(xi) ** 2 * (1 - e) / (1 - g * e)
        out = mp.e ** (C * theta + D * v0)
        if lam:
            kb = mp.e ** (mp.mpf(mu) + mp.mpf(delta) ** 2 / 2) - 1
            out *= mp.e ** (lam * T * (mp.e ** (1j * u * mu - mp.mpf(delta) ** 2 * u * u / 2) - 1 - 1j * u * kb))
        return out
    return f


def ql_heston(S, K, T, r, q, ot, v0, kappa, theta, xi, rho, jumps=None):
    ref = ql.Date(6, 11, 2026)
    ql.Settings.instance().evaluationDate = ref
    d = round(T * 365)
    assert d / 365 == T
    rt = ql.YieldTermStructureHandle(ql.FlatForward(ref, r, ql.Actual365Fixed(), ql.Continuous))
    qt = ql.YieldTermStructureHandle(ql.FlatForward(ref, q, ql.Actual365Fixed(), ql.Continuous))
    sq = ql.QuoteHandle(ql.SimpleQuote(S))
    if jumps:
        lam, mu, de = jumps
        eng = ql.BatesEngine(ql.BatesModel(ql.BatesProcess(rt, qt, sq, v0, kappa, theta, xi, rho, lam, mu, de)), 1e-13, 1000000)
    else:
        eng = ql.AnalyticHestonEngine(ql.HestonModel(ql.HestonProcess(rt, qt, sq, v0, kappa, theta, xi, rho)), 1e-13, 1000000)
    o = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call if ot == "CALL" else ql.Option.Put, K), ql.EuropeanExercise(ref + d))
    o.setPricingEngine(eng)
    return o.NPV()


def merton(S, K, T, r, q, ot, v, lam, mu, delta):
    kbar = math.exp(mu + delta * delta / 2) - 1
    lp = lam * (1 + kbar)
    tot, n, cum = 0.0, 0, 0.0
    while True:
        wgt = math.exp(-lp * T + n * math.log(lp * T) - math.lgamma(n + 1)) if lp > 0 else (1.0 if n == 0 else 0.0)
        vn = math.sqrt(v * v + n * delta * delta / T)
        rn = r - lam * kbar + n * math.log(1 + kbar) / T
        tot += wgt * bs(ot, S, K, T, rn, q, vn)[0]
        cum += wgt
        n += 1
        if cum >= 1 - 1e-16 or n > 200:
            break
    return tot


def ql_merton(S, K, T, r, q, ot, v, lam, mu, delta):
    ref = ql.Date(6, 11, 2026)
    ql.Settings.instance().evaluationDate = ref
    d = round(T * 365)
    rt = ql.YieldTermStructureHandle(ql.FlatForward(ref, r, ql.Actual365Fixed(), ql.Continuous))
    qt = ql.YieldTermStructureHandle(ql.FlatForward(ref, q, ql.Actual365Fixed(), ql.Continuous))
    vt = ql.BlackVolTermStructureHandle(ql.BlackConstantVol(ref, ql.NullCalendar(), v, ql.Actual365Fixed()))
    pr = ql.Merton76Process(ql.QuoteHandle(ql.SimpleQuote(S)), qt, rt, vt, ql.QuoteHandle(ql.SimpleQuote(lam)), ql.QuoteHandle(ql.SimpleQuote(mu)), ql.QuoteHandle(ql.SimpleQuote(delta)))
    o = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call if ot == "CALL" else ql.Option.Put, K), ql.EuropeanExercise(ref + d))
    o.setPricingEngine(ql.JumpDiffusionEngine(pr, 1e-14, 1000))
    return o.NPV()


HP = [  # S, days, r, q, v0, kappa, theta, xi, rho
    (100.0, 365, 0.03, 0.01, 0.04, 1.5, 0.04, 0.5, -0.7),
    (100.0, 91, 0.05, 0.0, 0.09, 3.0, 0.05, 0.8, -0.5),
    (100.0, 730, 0.02, 0.02, 0.03, 0.8, 0.06, 0.3, -0.3),
    (100.0, 1825, -0.005, 0.0, 0.05, 2.0, 0.045, 1.0, -0.9),
    (100.0, 182, 0.04, 0.03, 0.0625, 1.0, 0.04, 0.4, 0.3),
]
HK = [70.0, 90.0, 100.0, 110.0, 140.0]
PLIM = {"absolute": 1e-8, "relative": 1e-9, "reason": "1e-8 per unit at spot 100: 1e-3 currency units on 100,000 units; QuantLib adaptive engine to 1e-13"}


def e2_heston():
    s = S("heston_e", "05-volatility/heston-family.md")
    vq = [QLV, "mpmath-lewis-30-digits", "lewis-gauss-legendre-256-on-0-200"]
    op = "vol.heston.price"
    for S0, days, r, q, v0, ka, th, xi, rho in HP:
        T = days / 365
        prm = {"v0": v0, "kappa": ka, "theta": th, "xi": xi, "rho": rho}
        for ot in ("CALL", "PUT"):
            ph = lambda u: phi_heston(u, T, v0, ka, th, xi, rho)  # noqa: E731
            pr = [lewis(ph, S0, K, T, r, q, ot) for K in HK]
            for K, p in zip(HK, pr):
                a1 = mp_lewis(mp_phi_heston(T, v0, ka, th, xi, rho), S0, K, T, r, q, ot)
                a2 = ql_heston(S0, K, T, r, q, ot, v0, ka, th, xi, rho)
                assert abs(p - a1) < 1e-10 and abs(p - a2) < 1e-9, (K, p, a1, a2)
            s.add(op, {"spot": S0, "strikes": HK, "expiry_years": T, "rate": r, "dividend_yield": q, "heston": prm, "option_type": ot}, {"prices": pr},
                  cls=Q, verified=vq, tags=["heston"] + (["negative-rate"] if r < 0 else []), limit=PLIM)
    # Near-zero vol of vol (plan section 8): Black-Scholes with average variance, not v0, not theta.
    S0, T, r, q, v0, ka, th = 100.0, 1.0, 0.03, 0.0, 0.09, 2.0, 0.04
    for xi in (1e-3, 1e-2):
        ph = lambda u: phi_heston(u, T, v0, ka, th, xi, -0.5)  # noqa: E731
        # golden from 30-digit mpmath: in binary64 the kappa/xi^2 factor cancels about 1e-9 away at xi = 1e-3, inside the 1e-8 limit
        pr = [mp_lewis(mp_phi_heston(T, v0, ka, th, xi, -0.5), S0, K, T, r, q, "CALL") for K in HK]
        for K, p in zip(HK, pr):
            assert abs(p - ql_heston(S0, K, T, r, q, "CALL", v0, ka, th, xi, -0.5)) < 1e-12
            assert abs(p - lewis(ph, S0, K, T, r, q, "CALL")) < 5e-9
        s.add(op, {"spot": S0, "strikes": HK, "expiry_years": T, "rate": r, "dividend_yield": q, "heston": {"v0": v0, "kappa": ka, "theta": th, "xi": xi, "rho": -0.5}, "option_type": "CALL"},
              {"prices": pr}, cls=Q, verified=[QLV, "mpmath-lewis-30-digits"], tags=["heston", "small-vol-of-vol"], limit=PLIM)
        vbar = th + (v0 - th) * (1 - math.exp(-ka * T)) / (ka * T)
        bsa = bs("CALL", S0, 100.0, T, r, q, math.sqrt(vbar))[0]
        assert abs(pr[2] - bsa) < 0.05 * xi * 10, (xi, pr[2] - bsa)
        if xi == 1e-3:
            caught("heston_e", "small vol-of-vol limit = BS at sqrt(v0)", abs(bs("CALL", S0, 100.0, T, r, q, 0.3)[0] - pr[2]), 1e-8)
            caught("heston_e", "small vol-of-vol limit = BS at sqrt(theta)", abs(bs("CALL", S0, 100.0, T, r, q, 0.2)[0] - pr[2]), 1e-8)
    S0, days, r, q, v0, ka, th, xi, rho = HP[0]
    T = days / 365
    caught("heston_e", "rho sign flipped", abs(lewis(lambda u: phi_heston(u, T, v0, ka, th, xi, -rho), S0, 70.0, T, r, q, "PUT") - lewis(lambda u: phi_heston(u, T, v0, ka, th, xi, rho), S0, 70.0, T, r, q, "PUT")), 1e-8)
    caught("heston_e", "xi^2 read as xi (variance of variance)", abs(lewis(lambda u: phi_heston(u, T, v0, ka, th, math.sqrt(xi), rho), S0, 70.0, T, r, q, "PUT") - lewis(lambda u: phi_heston(u, T, v0, ka, th, xi, rho), S0, 70.0, T, r, q, "PUT")), 1e-8)
    b = {"spot": S0, "strikes": HK, "expiry_years": T, "rate": r, "dividend_yield": q, "heston": {"v0": v0, "kappa": ka, "theta": th, "xi": xi, "rho": rho}, "option_type": "CALL"}
    for k_, val in (("v0", 0.0), ("kappa", 0.0), ("theta", -0.01), ("xi", 0.0), ("rho", 1.0)):
        s.add(op, {**b, "heston": {**b["heston"], k_: val}}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(op, {**b, "strikes": []}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {**b, "strikes": [100.0, 0.0]}, error="E_DOMAIN", cls=E, tags=["invalid"])

    # Characteristic function values, for builds to localise errors.
    op = "vol.heston.cf"
    us = [0.0, 0.5, 1.0, 5.0, 20.0]
    for S0, days, r, q, v0, ka, th, xi, rho in HP[:3]:
        T = days / 365
        f = mp_phi_heston(T, v0, ka, th, xi, rho)
        ph = [phi_heston(u, T, v0, ka, th, xi, rho) for u in us]
        for u, z in zip(us, ph):
            assert abs(complex(f(mp.mpf(u))) - z) < 1e-13
        s.add(op, {"expiry_years": T, "heston": {"v0": v0, "kappa": ka, "theta": th, "xi": xi, "rho": rho}, "u": us},
              {"re": [z.real for z in ph], "im": [z.imag for z in ph]}, cls=F, verified=["mpmath-30-digits", "analytic"], tags=["heston", "cf"])

    # Bates.
    op = "vol.bates.price"
    for (S0, days, r, q, v0, ka, th, xi, rho), (lam, mu, de) in zip(HP[:3], ((0.3, -0.10, 0.15), (1.0, -0.05, 0.10), (0.1, 0.05, 0.20))):
        T = days / 365
        for ot in ("CALL", "PUT"):
            ph = lambda u: phi_heston(u, T, v0, ka, th, xi, rho) * phi_jump(u, T, lam, mu, de)  # noqa: E731
            pr = [lewis(ph, S0, K, T, r, q, ot) for K in HK]
            for K, p in zip(HK, pr):
                a1 = mp_lewis(mp_phi_heston(T, v0, ka, th, xi, rho, lam, mu, de), S0, K, T, r, q, ot)
                a2 = ql_heston(S0, K, T, r, q, ot, v0, ka, th, xi, rho, (lam, mu, de))
                assert abs(p - a1) < 1e-10 and abs(p - a2) < 1e-9, (K, p, a1, a2)
            s.add(op, {"spot": S0, "strikes": HK, "expiry_years": T, "rate": r, "dividend_yield": q, "heston": {"v0": v0, "kappa": ka, "theta": th, "xi": xi, "rho": rho},
                       "jumps": {"intensity": lam, "mean_log_jump": mu, "log_jump_vol": de}, "option_type": ot}, {"prices": pr}, cls=Q, verified=vq, tags=["bates"], limit=PLIM)
    S0, days, r, q, v0, ka, th, xi, rho = HP[0]
    T = days / 365
    good = lewis(lambda u: phi_heston(u, T, v0, ka, th, xi, rho) * phi_jump(u, T, .3, -.1, .15), S0, 70.0, T, r, q, "PUT")
    caught("bates_e", "jump compensator omitted (not a martingale)", abs(lewis(lambda u: phi_heston(u, T, v0, ka, th, xi, rho) * cmath.exp(.3 * T * (cmath.exp(1j * u * -.1 - .15 ** 2 * u * u / 2) - 1)), S0, 70.0, T, r, q, "PUT") - good), 1e-8)
    s.add(op, {"spot": S0, "strikes": HK, "expiry_years": T, "rate": r, "dividend_yield": q, "heston": {"v0": v0, "kappa": ka, "theta": th, "xi": xi, "rho": rho},
               "jumps": {"intensity": -0.1, "mean_log_jump": 0.0, "log_jump_vol": 0.1}, "option_type": "CALL"}, error="E_DOMAIN", cls=E, tags=["invalid"])

    # Merton jump diffusion.
    op = "vol.merton.price"
    for S0, days, r, q, v, lam, mu, de in ((100.0, 365, 0.03, 0.01, 0.2, 0.5, -0.1, 0.2), (100.0, 91, 0.05, 0.0, 0.15, 2.0, -0.02, 0.05), (100.0, 1095, 0.02, 0.0, 0.25, 0.2, 0.1, 0.3), (100.0, 365, 0.03, 0.0, 0.2, 0.0, 0.0, 0.1)):
        T = days / 365
        for ot in ("CALL", "PUT"):
            pr = [merton(S0, K, T, r, q, ot, v, lam, mu, de) for K in HK]
            for K, p in zip(HK, pr):
                a2 = mp_lewis(lambda u: mp.e ** (-mp.mpf(v) ** 2 * T / 2 * (u * u + 1j * u)) * mp.e ** (lam * T * (mp.e ** (1j * u * mu - mp.mpf(de) ** 2 * u * u / 2) - 1 - 1j * u * (mp.e ** (mp.mpf(mu) + mp.mpf(de) ** 2 / 2) - 1))), S0, K, T, r, q, ot)
                a1 = lewis(lambda u: cmath.exp(-v * v * T / 2 * (u * u + 1j * u)) * phi_jump(u, T, lam, mu, de), S0, K, T, r, q, ot)
                assert abs(p - a2) < 1e-9 and abs(p - a1) < 1e-9, (K, p, a1, a2)
            s.add(op, {"spot": S0, "strikes": HK, "expiry_years": T, "rate": r, "dividend_yield": q, "vol": v,
                       "jumps": {"intensity": lam, "mean_log_jump": mu, "log_jump_vol": de}, "option_type": ot}, {"prices": pr}, cls=Q, verified=["mpmath-lewis-30-digits", "lewis-gauss-legendre-256-on-0-200", "poisson-series"],
                      tags=["merton"] + (["no-jumps"] if lam == 0 else []), limit=PLIM)
    mixed = sum(math.exp(-.5 * (1 + math.exp(-.1 + .02) - 1) * 1 + n * math.log(.5 * math.exp(-.08)) - math.lgamma(n + 1)) * bs("CALL", 100, 100, 1, .03 - .5 * (math.exp(-.08) - 1) + n * (-.08), .01, math.sqrt(.04 + n * .04))[0] * math.exp((-.5 * (math.exp(-.08) - 1) + n * (-.08)) * 1) for n in range(60))
    caught("heston_e", "Merton weights at lambda' with terms re-discounted (two conventions mixed)", abs(mixed - merton(100, 100, 1, .03, .01, "CALL", .2, .5, -.1, .2)), 1e-8)
    caught("heston_e", "Merton drift without -lambda k", abs(merton(100, 100, 1, .03, .01, "CALL", .2, .5, -.1, .2) - merton(100, 100, 1, .03 + .5 * (math.exp(-.1 + .02) - 1), .01, "CALL", .2, .5, -.1, .2)), 1e-8)
    s.add(op, {"spot": 100.0, "strikes": HK, "expiry_years": 1.0, "rate": 0.03, "dividend_yield": 0.0, "vol": 0.2, "jumps": {"intensity": 0.5, "mean_log_jump": 0.0, "log_jump_vol": -0.1}, "option_type": "CALL"},
          error="E_DOMAIN", cls=E, tags=["invalid"])
    write(s)


# ---------------------------------------------------------------- SLV leverage on a fixed grid
def thomas(a, b, c, d):
    n = len(d)
    cp, dp = np.zeros(n), np.zeros(n)
    cp[0], dp[0] = c[0] / b[0], d[0] / b[0]
    for i in range(1, n):
        m = b[i] - a[i] * cp[i - 1]
        cp[i] = c[i] / m if i < n - 1 else 0.0
        dp[i] = (d[i] - a[i] * dp[i - 1]) / m
    x = np.zeros(n)
    x[-1] = dp[-1]
    for i in range(n - 2, -1, -1):
        x[i] = dp[i] - cp[i] * x[i + 1]
    return x


def fp_rows(mu, dd, h, dt, noflux=False):
    """Rows of (I - dt A), A p = -D[mu p] + 1/2 D2[dd p]. Diffusion central on the product; drift by upwind fluxes at the
    cell faces, face drift the mean of its two nodes (the node itself at the two outer faces), density 0 beyond the grid (ruling E-A14)."""
    n = len(mu)
    a, b, c = np.zeros(n), np.ones(n), np.zeros(n)
    face = [mu[0]] + [(mu[i] + mu[i + 1]) / 2 for i in range(n - 1)] + [mu[-1]]   # face k sits between nodes k-1 and k
    if noflux:   # zero flux through both outer faces: drift and diffusion (mass kept)
        face[0] = face[-1] = 0.0
    for i in range(n):
        edge = noflux and i in (0, n - 1)
        b[i] += dt * dd[i] / (h * h) / (2 if edge else 1)
        if i > 0:
            a[i] -= dt * dd[i - 1] / (2 * h * h)
        if i < n - 1:
            c[i] -= dt * dd[i + 1] / (2 * h * h)
        up, lo = face[i + 1], face[i]
        b[i] += dt * (max(up, 0.0) - min(lo, 0.0)) / h
        if i < n - 1:
            c[i] += dt * min(up, 0.0) / h
        if i > 0:
            a[i] -= dt * max(lo, 0.0) / h
    return a, b, c


def slv(inp, guard=True):
    S0, r, q = inp["spot"], inp["rate"], inp["dividend_yield"]
    h = inp["heston"]
    v0, ka, th, xi, rho = h["v0"], h["kappa"], h["theta"], h["xi"], h["rho"]
    gr = inp["grid"]
    nx, nv, nt, T = gr["nx"], gr["nv"], gr["nt"], inp["expiry_years"]
    xs = np.linspace(gr["x_min"], gr["x_max"], nx)
    dv = gr["v_max"] / (nv + 1)
    vs = np.array([dv * (j + 1) for j in range(nv)])
    dx, dt = xs[1] - xs[0], T / nt
    sl = inp["slices"]

    def lv2(t):
        lnF = math.log(S0) + (r - q) * t
        out = np.zeros(nx)
        for i, x in enumerate(xs):
            w, g, wT = dupire(sl, t, x - lnF)
            if guard:
                assert g > 1e-4 and wT > 1e-6
            out[i] = wT / g
        return out

    def lev2(t, p):
        m = p.sum(axis=1)
        mv = (p * vs[None, :]).sum(axis=1)
        eps = 1e-10 * m.max()
        ev = (mv + eps * (mv.sum() / m.sum())) / (m + eps)   # smooth: no branch, so no knife edge (ruling E-A14)
        return lv2(t) / ev
    # initial density at t1 = dt: bivariate normal
    t1 = dt
    lnF0 = math.log(S0)
    w, g, wT = dupire(sl, t1, 0.0)
    L0 = wT / g / v0
    mx, mv_ = lnF0 + (r - q - 0.5 * L0 * v0) * t1, v0 + ka * (th - v0) * t1
    sx, sv = max(math.sqrt(L0 * v0 * t1), 2 * dx), max(xi * math.sqrt(v0 * t1), 2 * dv)   # at least two cells wide (ruling E-A14)
    c = rho
    X, Vv = np.meshgrid(xs, vs, indexing="ij")
    zx, zv = (X - mx) / sx, (Vv - mv_) / sv
    p = np.exp(-(zx * zx - 2 * c * zx * zv + zv * zv) / (2 * (1 - c * c)))
    p /= p.sum() * dx * dv
    for n in range(1, nt):
        t = n * dt
        L2 = lev2(t, p)
        # 1 mixed term, explicit
        f = rho * xi * np.sqrt(L2)[:, None] * vs[None, :] * p
        ps = p.copy()
        ps[1:-1, 1:-1] += dt * (f[2:, 2:] - f[2:, :-2] - f[:-2, 2:] + f[:-2, :-2]) / (4 * dx * dv)
        # 2 x implicit: p_t = -D_x[(r-q-L2 v/2) p] + 1/2 D_xx[L2 v p], Dirichlet 0 at both ends
        pp = np.zeros_like(p)
        for j in range(nv):
            a, b_, cc = fp_rows(r - q - 0.5 * L2 * vs[j], L2 * vs[j], dx, dt)
            a[0] = cc[0] = a[-1] = cc[-1] = 0.0
            b_[0] = b_[-1] = 1.0
            rhs = ps[:, j].copy()
            rhs[0] = rhs[-1] = 0.0
            pp[:, j] = thomas(a, b_, cc, rhs)
        # 3 v implicit: p_t = -D_v[ka(th-v) p] + 1/2 D_vv[xi^2 v p], density 0 at v = 0 and v_max (outside the grid)
        a, b_, cc = fp_rows(ka * (th - vs), xi * xi * vs, dv, dt, noflux=True)
        p = np.array([thomas(a, b_, cc, pp[i, :]) for i in range(nx)])
        p = np.maximum(p, 0.0)   # positivity floor after each full step (ruling E-A14)
    L2 = lev2(T, p)
    return {"x": xs.tolist(), "leverage": np.sqrt(L2).tolist(), "mass": float(p.sum() * dx * dv)}


def flat_slices(vol, Ts=(0.5, 1.0)):
    return [{"expiry_years": t, "svi": svi(vol * vol * t, 1e-9, 0.0, 0.0, 0.1)} for t in Ts]


def e2_slv():
    s = S("slv_e", "05-volatility/heston-family.md")
    op = "vol.slv.leverage"
    G0 = {"nx": 61, "nv": 50, "nt": 50, "x_min": math.log(100) - 1.2, "x_max": math.log(100) + 1.2, "v_max": 0.25}
    hp = {"v0": 0.04, "kappa": 2.0, "theta": 0.04, "xi": 0.3, "rho": -0.7}
    cases = [({"spot": 100.0, "expiry_years": 1.0, "rate": 0.02, "dividend_yield": 0.0, "heston": hp, "slices": SURF, "grid": G0}, ["svi-surface"]),
             ({"spot": 100.0, "expiry_years": 0.5, "rate": 0.0, "dividend_yield": 0.0, "heston": {**hp, "rho": 0.0, "xi": 0.35}, "slices": SURF, "grid": {**G0, "nt": 40}}, ["svi-surface", "zero-rho"]),
             ({"spot": 100.0, "expiry_years": 1.0, "rate": 0.02, "dividend_yield": 0.01, "heston": {**hp, "xi": 0.15, "rho": 0.0}, "slices": flat_slices(0.2), "grid": G0}, ["flat-vol", "small-vol-of-vol"])]
    for inp, tags in cases:
        out = slv(inp)
        # stability of the recipe: 1e-10 input perturbation moves leverage by < 1e-7 (no near-threshold branch)
        pert = slv({**inp, "spot": inp["spot"] * (1 + 1e-12)}, guard=False)
        assert max(abs(a - b) for a, b in zip(out["leverage"], pert["leverage"])) < 1e-8
        assert 0.98 < out["mass"] < 1.01, out["mass"]
        note(f"slv_e: mass at T {out['mass']:.4f}")
        # grid refinement sanity near the spot (not a golden): within 2%
        fine = slv({**inp, "grid": {**inp["grid"], "nx": 121, "nv": 80, "nt": 100}}, guard=False)
        i0 = len(out["x"]) // 2
        assert abs(out["leverage"][i0] - fine["leverage"][len(fine["x"]) // 2]) < 0.02 * fine["leverage"][len(fine["x"]) // 2], "grid not converged"
        if "flat-vol" in tags:
            body = [l for x, l in zip(out["x"], out["leverage"]) if abs(x - math.log(100)) < 0.25]
            assert max(abs(l - 1.0) for l in body) < 0.03, body  # sigma_LV / sqrt(E[v|x]) ~ 0.2/0.2
        s.add(op, inp, out, cls=N, verified=["reference-scheme", "grid-refinement-2pc", "flat-vol-limit"], tags=["slv"] + tags)
    inp = cases[0][0]
    o = slv(inp)
    w = slv({**inp, "heston": {**hp, "rho": 0.7}}, guard=False)
    caught("slv_e", "mixed-term sign (rho flipped)", max(abs(a - b) for a, b in zip(o["leverage"], w["leverage"])), 1e-8)
    s.add(op, {**inp, "grid": {**G0, "nx": 2}}, error="E_INPUT", cls=E, tags=["invalid"], description="nx at least 5")
    s.add(op, {**inp, "grid": {**G0, "x_min": 5.0, "x_max": 4.0}}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {**inp, "grid": {**G0, "x_min": 4.6, "x_max": 4.7}}, error="E_INPUT", cls=E, tags=["invalid"], description="spot outside the x grid interior")
    s.add(op, {**inp, "grid": {**G0, "nx": 2001}}, error="E_LIMIT", cls=E, tags=["invalid"])
    s.add(op, {**inp, "heston": {**hp, "xi": 0.0}}, error="E_DOMAIN", cls=E, tags=["invalid"])
    write(s)


SLICES = {"E1": (e1_surf, e1_lv), "E3": (e3_fx,), "E2": (e2_heston, e2_slv)}


def main():
    want = sys.argv[1:] or list(SLICES)
    for w in want:
        for f in SLICES[w]:
            f()
    for m in MUTANTS:
        note(f"mutant caught: {m[0]}: {m[1]} (gap {m[2]:.3e})")


if __name__ == "__main__":
    main()
