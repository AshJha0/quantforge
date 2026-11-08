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
            if guard:
                away(s_, 2, 1e-6, "Lee slope")
            if s_ > 2:
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


SLICES = {"E1": (e1_surf, e1_lv)}


def main():
    want = sys.argv[1:] or list(SLICES)
    for w in want:
        for f in SLICES[w]:
            f()
    for m in MUTANTS:
        note(f"mutant caught: {m[0]}: {m[1]} (gap {m[2]:.3e})")


if __name__ == "__main__":
    main()
