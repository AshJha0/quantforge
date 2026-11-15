"""Stage J wave 3: scenario stress engine, interpolation backtests, drift detectors.

Specs: specifications/06-risk/scenario-stress.md, 11-research/interp-backtest.md, 11-research/drift-detectors.md;
rulings specifications/stage-j-rulings-w3.md (J-W3-1 onwards).

Independent oracle (no golden is taken from an implementation under test):
- Scenarios: exact rational arithmetic (fractions) on the binary64 inputs; real rows from the stored Treasury files
  (datasets/scenarios/raw, hash-checked), whose values the library build checked against H.15 (J-W3-7).
- Interpolation LOO and surface holdout: scipy CubicSpline(bc_type="natural") and PchipInterpolator, numpy.interp
  for linear (library-object); log_linear by mpmath at 50 digits.
- KS: exact lattice-path count in fractions (written here, separate from the build), checked against scipy
  ks_2samp(method="exact"); the largest gap is printed.
- CUSUM, Page-Hinkley, PSI: fractions re-implementation (does not count as an outside check) plus hand cases.

    cd oracle/python && uv run python -W ignore gen_stage_j_w3.py
"""
import csv
import hashlib
import io
import math
from datetime import date
from fractions import Fraction as Fr
from pathlib import Path

import mpmath as mp
import numpy as np
from scipy import interpolate, stats

from qf_oracle import common
from qf_oracle.common import Suite, note

mp.mp.dps = 50
G = "oracle/python/gen_stage_j_w3.py"
FOLDER = "stage_j"
SA, EX, IP, ST = "simple_analytic", "date_and_convention", "interpolation", "statistics"
SPEC_SC = "specifications/06-risk/scenario-stress.md"
SPEC_BT = "specifications/11-research/interp-backtest.md"
SPEC_DR = "specifications/11-research/drift-detectors.md"
ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "datasets" / "scenarios" / "raw"
OUTSIDE = {"ks_gap": 0.0, "interp_lib": 0, "ks_lib": 0}


class QfErr(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def F(x):
    return Fr(x)


def inc(xs):
    return all(b > a for a, b in zip(xs, xs[1:]))


# ---------------------------------------------------------------- scenarios

def shock_ref(inp):
    d, t, y = inp["dates"], inp["tenors"], inp["yields"]
    if not d or not t or len(y) != len(d) or any(len(r) != len(t) for r in y):
        raise QfErr("E_INPUT")
    if not inc([date.fromisoformat(x) for x in d]):
        raise QfErr("E_DATE_ORDER")
    if any(v <= 0 for v in t) or not inc(t):
        raise QfErr("E_DOMAIN")
    a, b = date.fromisoformat(inp["start_date"]), date.fromisoformat(inp["end_date"])
    if b <= a:
        raise QfErr("E_DATE_ORDER")
    if inp["start_date"] not in d or inp["end_date"] not in d:
        raise QfErr("E_DOMAIN")
    y0, y1 = y[d.index(inp["start_date"])], y[d.index(inp["end_date"])]
    sh = [100 * (F(q) - F(p)) for p, q in zip(y0, y1)]
    return {"start_yields": y0, "end_yields": y1, "shift_bp": [float(s) for s in sh],
            "level_bp": float(sum(sh) / len(sh)), "slope_bp": float(sh[-1] - sh[0])}


def flat_lin(x, y, t):
    if t <= x[0]:
        return F(y[0])
    if t >= x[-1]:
        return F(y[-1])
    i = max(j for j in range(len(x) - 1) if x[j] <= t)
    u = (F(t) - F(x[i])) / (F(x[i + 1]) - F(x[i]))
    return F(y[i]) + u * (F(y[i + 1]) - F(y[i]))


def replay_ref(inp):
    bt, by, st, sb = inp["base_tenors"], inp["base_yields"], inp["shock_tenors"], inp["shock_bp"]
    dv = inp.get("dv01")
    if not bt or len(by) != len(bt) or not st or len(sb) != len(st) or (dv is not None and len(dv) != len(bt)):
        raise QfErr("E_INPUT")
    for t in (bt, st):
        if any(v <= 0 for v in t) or not inc(t):
            raise QfErr("E_DOMAIN")
    sc = F(inp.get("scale", 1.0))
    ap = [sc * flat_lin(st, sb, t) for t in bt]
    out = {"applied_bp": [float(a) for a in ap], "shocked_yields": [float(F(y) + a / 100) for y, a in zip(by, ap)]}
    if dv is not None:
        out["pnl"] = float(-sum(F(d) * a for d, a in zip(dv, ap)))
    return out


def treasury_rows(year):
    prov = {r["name"]: r["sha256"] for r in csv.DictReader((RAW / "provenance.csv").open(encoding="utf-8"))}
    b = (RAW / f"ust_{year}.csv").read_bytes()
    assert hashlib.sha256(b).hexdigest() == prov[f"ust_{year}.csv"]
    out = {}
    for row in csv.DictReader(io.StringIO(b.decode("utf-8-sig"))):
        m, d, y = (int(x) for x in row.pop("Date").split("/"))
        out[date(y, m, d).isoformat()] = {k.strip(): v for k, v in row.items()}
    return out


LABELS = ("1 Mo", "3 Mo", "6 Mo", "1 Yr", "2 Yr", "3 Yr", "5 Yr", "7 Yr", "10 Yr", "20 Yr", "30 Yr")
TENORS = (1 / 12, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0)
WINDOWS = (("gfc_2008", "2008-09-12", "2008-12-31"), ("taper_2013", "2013-05-01", "2013-09-05"),
           ("covid_2020", "2020-02-19", "2020-03-09"), ("hikes_2022", "2021-12-31", "2022-10-21"))


def real_case(a, b, extra=2):
    rows = {}
    for y in {int(a[:4]), int(b[:4])}:
        rows.update(treasury_rows(y))
    ds = sorted(d for d in rows if a <= d <= b and all(rows[d][lab] != "" for lab in LABELS))
    pick = sorted({ds[0], ds[-1], *ds[1:1 + extra]})
    assert pick[0] == a and pick[-1] == b, (a, b)
    return {"dates": pick, "tenors": list(TENORS), "yields": [[float(rows[d][lab]) for lab in LABELS] for d in pick],
            "start_date": a, "end_date": b}


# ---------------------------------------------------------------- interpolation backtests

def lib_interp(method, x, y, at):
    if method == "linear":
        return [float(v) for v in np.interp(at, x, y)]
    if method == "cubic_natural":
        return [float(v) for v in interpolate.CubicSpline(x, y, bc_type="natural")(at)]
    if method == "monotone_pchip":
        return [float(v) for v in interpolate.PchipInterpolator(x, y)(at)]
    if method == "log_linear":
        out = []
        for t in at:
            i = max(j for j in range(len(x) - 1) if x[j] <= t)
            u = (mp.mpf(t) - x[i]) / (mp.mpf(x[i + 1]) - x[i])
            out.append(float(mp.exp((1 - u) * mp.log(y[i]) + u * mp.log(y[i + 1]))))
        return out
    raise AssertionError(method)


MINK = {"linear": 2, "log_linear": 2, "cubic_natural": 3, "monotone_pchip": 2}


def summ(errs):
    e = [mp.mpf(v) for v in errs]
    return float(max(abs(v) for v in e)), float(mp.sqrt(sum(v * v for v in e) / len(e)))


def loo_ref(inp):
    m, x, y = inp["method"], inp["x"], inp["y"]
    n = len(x)
    if len(y) != n or n < 3 or n - 1 < MINK[m] or not inc(x):
        raise QfErr("E_INPUT")
    if m == "log_linear" and any(v <= 0 for v in y):
        raise QfErr("E_DOMAIN")
    errs = [lib_interp(m, x[:i] + x[i + 1:], y[:i] + y[i + 1:], [x[i]])[0] - y[i] for i in range(1, n - 1)]
    mx, r = summ(errs)
    return {"errors": errs, "max_abs_error": mx, "rmse": r}


def surf_ref(inp):
    m, T, k, V, H = inp["method"], inp["expiries"], inp["strikes"], inp["vols"], inp["holdout"]
    if not T or len(V) != len(T) or any(len(r) != len(k) for r in V) or not inc(k):
        raise QfErr("E_INPUT")
    if not H or any(not 0 < h < len(k) - 1 for h in H) or not inc(H):
        raise QfErr("E_INPUT")
    kept = [j for j in range(len(k)) if j not in H]
    if len(kept) < MINK[m]:
        raise QfErr("E_INPUT")
    if any(t <= 0 for t in T) or any(v <= 0 for r in V for v in r):
        raise QfErr("E_DOMAIN")
    errs = []
    for t, row in zip(T, V):
        fit = lib_interp(m, [k[j] for j in kept], [row[j] * row[j] * t for j in kept], [k[h] for h in H])
        if any(v <= 0 for v in fit):
            raise QfErr("E_DOMAIN")
        errs.append([math.sqrt(v / t) - row[h] for v, h in zip(fit, H)])
    mx, r = summ([e for rr in errs for e in rr])
    return {"errors": errs, "max_abs_error": mx, "rmse": r}


def ssvi_vol(k, T, eta=1.0, gamma=0.5, rho=-0.4):
    th = 0.04 * T
    phi = eta * th ** -gamma * (1 + th) ** (gamma - 1)
    w = th / 2 * (1 + rho * phi * k + math.sqrt((phi * k + rho) ** 2 + 1 - rho * rho))
    return round(math.sqrt(w / T), 10)


# ---------------------------------------------------------------- drift

def cusum_ref(inp):
    x, k, h = inp["x"], F(inp["k"]), F(inp["h"])
    mu, sg, reset = F(inp.get("mu0", 0.0)), F(inp.get("sigma", 1.0)), inp.get("reset", True)
    if not x:
        raise QfErr("E_INPUT")
    if k <= 0 or h <= 0 or sg <= 0:
        raise QfErr("E_DOMAIN")
    sp = sm = Fr(0)
    al, di = [], []
    for t, v in enumerate(x):
        z = (F(v) - mu) / sg
        sp, sm = max(Fr(0), sp + z - k), max(Fr(0), sm - z - k)
        if sp > h or sm > h:
            al.append(t); di.append(1 if sp > h else -1)
            if not reset:
                break
            sp = sm = Fr(0)
    return {"alarms": al, "directions": di, "s_plus": float(sp), "s_minus": float(sm)}


def ph_ref(inp):
    x, dl, lam = inp["x"], F(inp["delta"]), F(inp["lambda"])
    dr, reset = inp.get("direction", "both"), inp.get("reset", True)
    if not x:
        raise QfErr("E_INPUT")
    if dl < 0 or lam <= 0:
        raise QfErr("E_DOMAIN")
    al, di = [], []
    n, tot, up, um, dn, dm = 0, Fr(0), Fr(0), Fr(0), Fr(0), Fr(0)
    for t, v in enumerate(x):
        n += 1; tot += F(v); mean = tot / n
        up += F(v) - mean - dl; dn += mean - F(v) - dl
        um, dm = min(um, up), min(dm, dn)
        hu, hd = dr != "down" and up - um > lam, dr != "up" and dn - dm > lam
        if hu or hd:
            al.append(t); di.append(1 if hu else -1)
            if not reset:
                break
            n, tot, up, um, dn, dm = 0, Fr(0), Fr(0), Fr(0), Fr(0), Fr(0)
    return {"alarms": al, "directions": di}


def psi_ref(inp):
    r, s, B, th = inp["reference"], inp["test"], inp.get("bins", 10), inp.get("threshold", 0.25)
    if B < 2 or len(r) < B or len(s) < B:
        raise QfErr("E_INPUT")
    if th <= 0:
        raise QfErr("E_DOMAIN")
    rs = sorted(r)
    edges = [rs[math.ceil(Fr(j * len(rs), B)) - 1] for j in range(1, B)]

    def shares(xs):
        c = [0] * B
        for v in xs:
            c[next((j for j, e in enumerate(edges) if v <= e), B - 1)] += 1
        return [max(Fr(q, len(xs)), Fr(1, 10 ** 4)) for q in c]
    a, e = shares(s), shares(r)
    val = sum((mp.mpf(p.numerator) / p.denominator - mp.mpf(q.numerator) / q.denominator) * mp.log(mp.mpf(p.numerator) / p.denominator / (mp.mpf(q.numerator) / q.denominator)) for p, q in zip(a, e))
    return {"psi": float(val), "reference_shares": [float(v) for v in e], "test_shares": [float(v) for v in a], "alarm": bool(val > th)}


def ks_ref(inp):
    a, b, lv = inp["a"], inp["b"], inp.get("level", 0.05)
    if not a or not b:
        raise QfErr("E_INPUT")
    if not 0 < lv < 1:
        raise QfErr("E_DOMAIN")
    n, m = len(a), len(b)
    pts = sorted(set(a) | set(b))
    d = max(abs(Fr(sum(v <= p for v in a), n) - Fr(sum(v <= p for v in b), m)) for p in pts)
    # probability (not count) recursion over the lattice, in fractions: P(path stays strictly inside |i/n - j/m| < d)
    P = {(0, 0): Fr(1)}
    for s in range(1, n + m + 1):
        for i in range(max(0, s - m), min(n, s) + 1):
            j = s - i
            if abs(Fr(i, n) - Fr(j, m)) >= d:
                continue
            p = Fr(0)
            if i > 0 and (i - 1, j) in P:
                p += P[(i - 1, j)] * Fr(n - i + 1, n + m - s + 1)
            if j > 0 and (i, j - 1) in P:
                p += P[(i, j - 1)] * Fr(m - j + 1, n + m - s + 1)
            if p:
                P[(i, j)] = p
    pv = float(1 - P.get((n, m), Fr(0)))
    if len(set(a) | set(b)) == n + m:  # scipy's exact method assumes no ties
        sp = stats.ks_2samp(a, b, method="exact")
        OUTSIDE["ks_gap"] = max(OUTSIDE["ks_gap"], abs(sp.pvalue - pv), abs(sp.statistic - float(d)))
        OUTSIDE["ks_lib"] += 1
    return {"statistic": float(d), "p_value": pv, "reject": bool(pv <= lv)}


# ---------------------------------------------------------------- suites

def mk(suite, op, ref, inp, code=None, cls=SA, desc=None, verified=("reference-computed",), oc=None, tags=()):
    try:
        out = ref(inp)
        assert code is None, f"{suite.name}: expected {code}, got a value ({desc})"
        suite.add(op, inp, outputs=out, cls=cls, verified=verified, tags=("research",) + tuple(tags),
                  description=desc, output_classes=oc)
    except QfErr as e:
        assert e.code == code, f"{suite.name} {desc}: expected {code}, got {e.code}"
        suite.add(op, inp, error=code, cls=EX, verified=("reference-computed",), tags=("invalid", "research"),
                  description=desc)


def det(seed, n, lo=-1.0, hi=1.0, nd=6):
    x, out = seed, []
    for _ in range(n):
        x = (6364136223846793005 * x + 1442695040888963407) % 2 ** 64
        out.append(round(lo + (hi - lo) * (x >> 11) / 2 ** 53, nd))
    return out


def gauss(seed, n, nd=6):
    u = det(seed, 2 * n, 1e-9, 1.0, 12)
    return [round(math.sqrt(-2 * math.log(u[2 * i])) * math.cos(2 * math.pi * u[2 * i + 1]), nd) for i in range(n)]


def build():
    suites = []
    # ---- scenarios
    s = Suite("scen_j", SPEC_SC, G); suites.append(s)
    OPH, OPR = "risk.scenario.historical_shock", "risk.scenario.replay"
    hand = {"dates": ["2020-02-19", "2020-03-09"], "tenors": [2.0, 10.0], "yields": [[1.43, 1.56], [0.46, 0.54]],
            "start_date": "2020-02-19", "end_date": "2020-03-09"}
    o = shock_ref(hand)
    assert abs(o["level_bp"] + 99.5) < 1e-9 and abs(o["slope_bp"] + 5) < 1e-9
    mk(s, OPH, shock_ref, hand, desc="hand: 2Y -97 bp, 10Y -102 bp, level -99.5, slope -5", verified=("hand", "reference-computed"))
    for name, a, b in WINDOWS:
        inp = real_case(a, b)
        mk(s, OPH, shock_ref, inp, desc=f"library window {name}: real Treasury par rows {a} to {b} (values checked against H.15, J-W3-7)",
           verified=("published-data", "reference-computed"), tags=("real-data",))
        o = shock_ref(inp)
        mk(s, OPR, replay_ref, {"base_tenors": list(TENORS), "base_yields": o["start_yields"], "shock_tenors": list(TENORS),
                                "shock_bp": o["shift_bp"]},
           desc=f"replay of {name} on its own start curve returns the end curve (J-W3-7 part 3)", tags=("real-data",))
    for d, ch, code in [("start date missing", {"start_date": "2020-02-20"}, "E_DOMAIN"),
                        ("end before start", {"start_date": "2020-03-09", "end_date": "2020-02-19"}, "E_DATE_ORDER"),
                        ("dates not increasing", {"dates": ["2020-03-09", "2020-02-19"]}, "E_DATE_ORDER"),
                        ("row length", {"yields": [[1.43], [0.46, 0.54]]}, "E_INPUT"),
                        ("tenors not increasing", {"tenors": [10.0, 2.0]}, "E_DOMAIN"),
                        ("empty", {"dates": [], "yields": []}, "E_INPUT")]:
        mk(s, OPH, shock_ref, dict(hand, **ch), code=code, desc=d)
    rh = {"base_tenors": [1.0, 5.0, 10.0], "base_yields": [4.0, 4.2, 4.5], "shock_tenors": [2.0, 10.0], "shock_bp": [-100.0, -50.0],
          "dv01": [0.0, 0.0, 1000.0]}
    o = replay_ref(rh)
    assert o["applied_bp"] == [-100.0, -81.25, -50.0] and o["pnl"] == 50000.0
    mk(s, OPR, replay_ref, rh, desc="hand: applied (-100, -81.25, -50), P&L +50,000", verified=("hand", "reference-computed"))
    mk(s, OPR, replay_ref, dict(rh, scale=0.5), desc="scale 0.5 halves the shock and the P&L")
    mk(s, OPR, replay_ref, {k: v for k, v in rh.items() if k != "dv01"}, desc="no dv01: no pnl output")
    mk(s, OPR, replay_ref, dict(rh, base_tenors=[0.25, 15.0, 40.0], dv01=[10.0, -20.0, 5.0]), desc="flat extrapolation both ends, mixed dv01 signs")
    for d, ch, code in [("dv01 length", {"dv01": [1.0]}, "E_INPUT"), ("shock length", {"shock_bp": [1.0]}, "E_INPUT"),
                        ("base tenors not positive", {"base_tenors": [0.0, 5.0, 10.0]}, "E_DOMAIN"),
                        ("shock tenors not increasing", {"shock_tenors": [10.0, 2.0]}, "E_DOMAIN")]:
        mk(s, OPR, replay_ref, dict(rh, **ch), code=code, desc=d)

    # ---- interpolation backtests
    s = Suite("interpbt_j", SPEC_BT, G); suites.append(s)
    OPL, OPS = "research.backtest.interp_loo", "research.backtest.surface_holdout"
    h = {"method": "linear", "x": [0.0, 1.0, 2.0], "y": [0.0, 1.0, 0.0]}
    assert loo_ref(h)["errors"] == [-1.0]
    mk(s, OPL, loo_ref, h, cls=IP, desc="hand: linear, hidden peak, error -1", verified=("hand", "reference-computed"))
    curve = real_case("2020-02-19", "2020-03-09")["yields"][0]
    for meth in ("linear", "log_linear", "cubic_natural", "monotone_pchip"):
        mk(s, OPL, loo_ref, {"method": meth, "x": list(TENORS), "y": curve}, cls=IP, desc=f"{meth}: Treasury par curve 2020-02-19",
           verified=("library-object" if meth != "log_linear" else "reference-computed",), tags=("real-data",))
        OUTSIDE["interp_lib"] += meth != "log_linear"
        x = sorted(set(round(v, 6) for v in det(9100 + len(meth), 12, 0.0, 10.0)))
        y = [round(2 + math.sin(v) + 0.1 * v, 6) for v in x]
        mk(s, OPL, loo_ref, {"method": meth, "x": x, "y": y}, cls=IP, desc=f"{meth}: {len(x)} irregular knots on a smooth curve",
           verified=("library-object" if meth != "log_linear" else "reference-computed",))
        OUTSIDE["interp_lib"] += meth != "log_linear"
    mk(s, OPL, loo_ref, {"method": "cubic_natural", "x": [0.0, 1.0, 2.0, 3.0], "y": [1.0, 3.0, 5.0, 7.0]}, cls=IP,
       desc="linear data: zero error under the natural spline", verified=("library-object",))
    OUTSIDE["interp_lib"] += 1
    K = [round(-0.4 + 0.1 * j, 10) for j in range(9)]
    T = [0.25, 0.5, 1.0, 2.0]
    V = [[ssvi_vol(k, t) for k in K] for t in T]
    for meth in ("linear", "cubic_natural", "monotone_pchip"):
        mk(s, OPS, surf_ref, {"method": meth, "expiries": T, "strikes": K, "vols": V, "holdout": [1, 3, 5, 7]}, cls=IP,
           desc=f"{meth}: SSVI test surface (B1 design b), alternate strikes held out", verified=("library-object",))
        mk(s, OPS, surf_ref, {"method": meth, "expiries": T, "strikes": K, "vols": V, "holdout": [4]}, cls=IP,
           desc=f"{meth}: SSVI test surface, ATM strike held out", verified=("library-object",))
        OUTSIDE["interp_lib"] += 2
    for d, ch, code in [("too few knots for cubic", {"method": "cubic_natural", "x": [0.0, 1.0, 2.0], "y": [0.0, 1.0, 0.0]}, "E_INPUT"),
                        ("knots not increasing", {"x": [0.0, 2.0, 1.0]}, "E_INPUT"),
                        ("log_linear with zero", {"method": "log_linear", "y": [0.0, 1.0, 2.0]}, "E_DOMAIN"),
                        ("length mismatch", {"y": [0.0, 1.0]}, "E_INPUT")]:
        mk(s, OPL, loo_ref, dict(h, **ch), code=code, desc=d)
    sb = {"method": "linear", "expiries": [1.0], "strikes": [-0.1, 0.0, 0.1], "vols": [[0.2, 0.19, 0.2]], "holdout": [1]}
    for d, ch, code in [("holdout at an end", {"holdout": [0]}, "E_INPUT"), ("holdout not sorted", {"strikes": [-0.2, -0.1, 0.0, 0.1], "vols": [[0.2, 0.2, 0.19, 0.2]], "holdout": [2, 1]}, "E_INPUT"),
                        ("expiry zero", {"expiries": [0.0]}, "E_DOMAIN"), ("vol zero", {"vols": [[0.2, 0.0, 0.2]]}, "E_DOMAIN"),
                        ("vols row length", {"vols": [[0.2, 0.2]]}, "E_INPUT")]:
        mk(s, OPS, surf_ref, dict(sb, **ch), code=code, desc=d)

    # ---- drift
    s = Suite("drift_j", SPEC_DR, G); suites.append(s)
    OC, OP_, OPS_, OK = "research.drift.cusum", "research.drift.page_hinkley", "research.drift.psi", "research.drift.ks"
    ex = {"alarms": EX, "directions": EX}
    hc = {"x": [0.0, 3.0, 3.0], "k": 0.5, "h": 4.0}
    assert cusum_ref(hc)["alarms"] == [2]
    mk(s, OC, cusum_ref, hc, desc="hand: S+ = 0, 2.5, 5, alarm at 2", verified=("hand", "reference-computed"), oc=ex)
    mk(s, OC, cusum_ref, {"x": [0.0, -3.0, -3.0], "k": 0.5, "h": 4.0}, desc="hand: downward alarm at 2", verified=("hand", "reference-computed"), oc=ex)
    for i, (shift, reset) in enumerate(((1.0, True), (1.0, False), (-1.5, True), (0.0, True))):
        x = [round(v + (shift if t >= 100 else 0.0), 6) for t, v in enumerate(gauss(9300 + i, 200))]
        mk(s, OC, cusum_ref, {"x": x, "k": 0.5, "h": 5.0, "reset": reset}, desc=f"200 Gaussian steps, shift {shift} at 100, reset {reset}", oc=ex)
    mk(s, OC, cusum_ref, {"x": [10.0, 12.0, 14.0, 9.0], "k": 0.25, "h": 1.0, "mu0": 10.0, "sigma": 2.0}, desc="mu0 and sigma standardise", oc=ex)
    hp = {"x": [0.0, 0.0, 0.0, 5.0, 5.0, 5.0], "delta": 0.1, "lambda": 3.0}
    mk(s, OP_, ph_ref, hp, desc="step up of 5 after three zeros", verified=("reference-computed",), oc=ex)
    for i, (dr, shift) in enumerate((("both", 1.0), ("up", 1.0), ("down", -1.0), ("up", -1.0))):
        x = [round(v + (shift if t >= 150 else 0.0), 6) for t, v in enumerate(gauss(9400 + i, 300))]
        mk(s, OP_, ph_ref, {"x": x, "delta": 0.5, "lambda": 10.0, "direction": dr}, desc=f"300 steps, shift {shift} at 150, direction {dr}", oc=ex)
    mk(s, OP_, ph_ref, {"x": [1.0] * 50, "delta": 0.1, "lambda": 1.0}, desc="constant series: no alarm", oc=ex)
    r = gauss(9500, 400)
    psi_oc = {"alarm": EX}
    mk(s, OPS_, psi_ref, {"reference": r, "test": r}, desc="sample against itself: PSI 0", oc=psi_oc)
    for i, sc in enumerate((1.0, 1.414214, 2.0)):
        mk(s, OPS_, psi_ref, {"reference": r, "test": [round(sc * v, 6) for v in gauss(9510 + i, 300)]}, desc=f"test sd x{sc}", oc=psi_oc)
    mk(s, OPS_, psi_ref, {"reference": [float(v % 5) for v in range(50)], "test": [float(v % 3) for v in range(40)], "bins": 5},
       desc="tied reference values: empty bins take the 1e-4 floor", oc=psi_oc)
    mk(s, OPS_, psi_ref, {"reference": [float(v) for v in range(20)], "test": [float(v) + 0.5 for v in range(20)], "bins": 4, "threshold": 0.01},
       desc="hand-checkable quartile bins, custom threshold", oc=psi_oc)
    ks_oc = {"reject": EX}
    hk = {"a": [1.0, 2.0, 3.0, 4.0], "b": [5.0, 6.0, 7.0, 8.5]}
    o = ks_ref(hk)
    assert o["statistic"] == 1.0 and abs(o["p_value"] - 2 / 70) < 1e-15
    mk(s, OK, ks_ref, hk, cls=ST, desc="hand: complete separation, D = 1, p = 2 / C(8,4) = 1/35", verified=("hand", "library-object"), oc=ks_oc)
    for i, (n, m, sc) in enumerate(((30, 30, 1.0), (40, 25, 1.0), (50, 50, 1.5), (60, 45, 1.0), (25, 70, 2.0))):
        a = gauss(9600 + i, n, 9)
        b = [round(sc * v + (0.5 if i == 3 else 0.0), 9) for v in gauss(9700 + i, m, 9)]
        mk(s, OK, ks_ref, {"a": a, "b": b}, cls=ST, desc=f"n={n}, m={m}, scale {sc}" + (", shift 0.5" if i == 3 else ""), verified=("library-object",), oc=ks_oc)
    mk(s, OK, ks_ref, {"a": [1.0, 2.0, 2.0, 3.0], "b": [2.0, 2.0, 4.0]}, cls=ST, desc="ties: continuous-null p-value (J-W3-13)", oc=ks_oc)
    for d, op, ref, inp, code in [
            ("cusum empty", OC, cusum_ref, {"x": [], "k": 0.5, "h": 5.0}, "E_INPUT"),
            ("cusum k zero", OC, cusum_ref, {"x": [1.0], "k": 0.0, "h": 5.0}, "E_DOMAIN"),
            ("cusum sigma negative", OC, cusum_ref, {"x": [1.0], "k": 0.5, "h": 5.0, "sigma": -1.0}, "E_DOMAIN"),
            ("ph lambda zero", OP_, ph_ref, {"x": [1.0], "delta": 0.5, "lambda": 0.0}, "E_DOMAIN"),
            ("ph delta negative", OP_, ph_ref, {"x": [1.0], "delta": -0.1, "lambda": 1.0}, "E_DOMAIN"),
            ("psi one bin", OPS_, psi_ref, {"reference": r, "test": r, "bins": 1}, "E_INPUT"),
            ("psi test too short", OPS_, psi_ref, {"reference": r, "test": [1.0, 2.0]}, "E_INPUT"),
            ("ks empty", OK, ks_ref, {"a": [], "b": [1.0]}, "E_INPUT"),
            ("ks level 1", OK, ks_ref, {"a": [1.0], "b": [2.0], "level": 1.0}, "E_DOMAIN")]:
        mk(s, op, ref, inp, code=code, desc=d)
    # Audit 2026-11-15: C(500, 250) is far past 128 bits, so Rust and C++ leave the exact count for the probability
    # walk; a large D makes p tiny, and a pure relative limit makes any cancellation in the walk visible.
    big = {"a": gauss(9800, 250, 9), "b": [round(v + 1.0, 9) for v in gauss(9801, 250, 9)]}
    mk(s, OK, ks_ref, big, cls=ST, desc="n = m = 250, shift 1.0: tiny p beyond 128-bit counts (relative limit)",
       verified=("library-object",), oc=ks_oc)
    s.cases[-1]["tolerance_limit"] = {"absolute": 0.0, "relative": 1e-9}
    return suites


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    tot = [0, 0, 0]
    for s in build():
        s.write()
        tot[0] += len(s.cases)
        tot[1] += sum(c["expected"]["status"] == "ok" for c in s.cases)
        tot[2] += sum(c["expected"]["status"] == "error" for c in s.cases)
    common.GOLDEN = keep
    note(f"stage J wave 3: {tot[0]} cases, value {tot[1]}, error {tot[2]}; scipy-checked interp {OUTSIDE['interp_lib']}, "
         f"KS {OUTSIDE['ks_lib']} (max |oracle - scipy| {OUTSIDE['ks_gap']:.2e})")


if __name__ == "__main__":
    main()
