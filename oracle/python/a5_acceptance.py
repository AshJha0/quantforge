"""A5 surrogate acceptance harness (plan 12.10 row A5, rulings G-11 and G-37). Challenger only: never in goldens.

Builds the fixed test set (core.sobol = unscrambled Joe-Kuo Sobol, index 0 never served, first 1,023 skipped; 100,000
domain points, then 10,000 wing and short-expiry points), prices each point with the full pricer (QuantLib 1.44
AnalyticHestonEngine, or Hagan SABR via ql.sabrVolatility), inverts to Black implied vol, and judges a candidate surrogate:
max abs IV error <= 1e-4 and 99.9th percentile <= 5e-5; E_DOMAIN on each of the 14 Heston faces plus NaN and infinity.

    uv run python -W ignore a5_acceptance.py --self-test [N]     # harness check on the first N points (default 2000)
    uv run python -W ignore a5_acceptance.py --module path.py    # full run: path.py defines heston_iv(p) and sabr_iv(p)
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import QuantLib as ql
from scipy.stats import qmc

HERE = Path(__file__).resolve().parent
HESTON = [("v0", 0.005, 0.25), ("kappa", 0.2, 8.0), ("theta", 0.005, 0.25), ("xi", 0.05, 1.5), ("rho", -0.95, 0.2),
          ("log_moneyness", -0.5, 0.4), ("T", 0.02, 5.0)]
SABR = [("alpha", 0.01, 1.0), ("beta_index", 0.0, 3.0), ("rho", -0.9, 0.9), ("nu", 0.05, 2.0), ("log_moneyness", -0.5, 0.5),
        ("T", 0.02, 10.0)]
N_MAIN, N_EXTRA, SKIP = 100_000, 10_000, 1023
PRICE_FLOOR = 1e-12  # forward-relative; below this the implied vol is not identifiable in binary64 (G-37)


class DomainError(Exception):
    pass


def sobol(d, n, start):
    """core.sobol points with indices start .. start + n - 1 (index 0 is the origin and is never served)."""
    s = qmc.Sobol(d, scramble=False)
    s.fast_forward(start)
    return s.random(n)


def wing_short_map(u, box, mi, ti):
    """G-37: even rows into the wing |ln K/F| > 0.3 (length-proportional over the two wing pieces), odd rows into T < 0.1."""
    x = np.empty_like(u)
    for j, (_, lo, hi) in enumerate(box):
        x[:, j] = lo + (hi - lo) * u[:, j]
    lo_m, hi_m = box[mi][1], box[mi][2]
    left, right = -0.3 - lo_m, hi_m - 0.3
    for r in range(len(u)):
        if r % 2 == 0:
            w = u[r, mi] * (left + right)
            x[r, mi] = lo_m + w if w < left else 0.3 + (w - left)
        else:
            x[r, ti] = 0.02 + (0.1 - 0.02) * u[r, ti]
    return x


def test_set(box):
    d = len(box)
    mi, ti = [k for k, (n, _, _) in enumerate(box) if n == "log_moneyness"][0], [k for k, (n, _, _) in enumerate(box) if n == "T"][0]
    main = sobol(d, N_MAIN, SKIP + 1)
    x = np.empty_like(main)
    for j, (_, lo, hi) in enumerate(box):
        x[:, j] = lo + (hi - lo) * main[:, j]
    extra = wing_short_map(sobol(d, N_EXTRA, SKIP + 1 + N_MAIN), box, mi, ti)
    return np.vstack([x, extra])


def heston_cf(u, T, v0, kappa, theta, xi, rho):
    """phi(u) of X = ln(S_T/F), the Albrecher et al. form of 05-volatility/heston-family.md."""
    b = kappa - rho * xi * 1j * u
    d = np.sqrt(b * b + xi * xi * (1j * u + u * u))
    g = (b - d) / (b + d)
    e = np.exp(-d * T)
    C = kappa / xi ** 2 * ((b - d) * T - 2 * np.log((1 - g * e) / (1 - g)))
    D = (b - d) / xi ** 2 * (1 - e) / (1 - g * e)
    return np.exp(C * theta + D * v0)


def heston_ref(p):
    """Full pricer: Lewis's single integral (F = 1, undiscounted), scipy quad to 1e-14; OTM option; Black IV by QuantLib."""
    from scipy.integrate import quad
    v0, kappa, theta, xi, rho, k, T = p
    K = math.exp(k)
    f = lambda u: (np.exp(-1j * u * k) * heston_cf(u - 0.5j, T, v0, kappa, theta, xi, rho)).real / (u * u + 0.25)  # noqa: E731
    I, _ = quad(f, 0.0, np.inf, limit=4000, epsabs=1e-15, epsrel=1e-13)
    call = 1.0 - math.sqrt(K) / math.pi * I
    price = call if K >= 1 else call - 1.0 + K
    if price < PRICE_FLOOR:
        return None, T
    typ = ql.Option.Call if K >= 1 else ql.Option.Put
    sd = ql.blackFormulaImpliedStdDev(typ, K, 1.0, price, 1.0, 0.0, 0.2 * math.sqrt(T), 1e-14, 1000)
    return sd / math.sqrt(T), T


def heston_ql_check(p):
    """Outside evidence: QuantLib AnalyticHestonEngine at a whole-day maturity, against heston_ref at the same T."""
    v0, kappa, theta, xi, rho, k, T = p
    today = ql.Date(10, 11, 2026)
    ql.Settings.instance().evaluationDate = today
    dc = ql.Actual365Fixed()
    days = max(1, int(round(T * 365)))
    ex = today + days
    flat = ql.YieldTermStructureHandle(ql.FlatForward(today, 0.0, dc))
    proc = ql.HestonProcess(flat, flat, ql.QuoteHandle(ql.SimpleQuote(1.0)), v0, kappa, theta, xi, rho)
    K = math.exp(k)
    opt = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call if K >= 1 else ql.Option.Put, K), ql.EuropeanExercise(ex))
    opt.setPricingEngine(ql.AnalyticHestonEngine(ql.HestonModel(proc), 1e-13, 100_000))
    q = opt.NPV()
    pp = list(p)
    pp[6] = days / 365
    from scipy.integrate import quad
    kk = k
    f = lambda u: (np.exp(-1j * u * kk) * heston_cf(u - 0.5j, pp[6], v0, kappa, theta, xi, rho)).real / (u * u + 0.25)  # noqa: E731
    I, _ = quad(f, 0.0, np.inf, limit=4000, epsabs=1e-15, epsrel=1e-13)
    call = 1.0 - math.sqrt(K) / math.pi * I
    mine = call if K >= 1 else call - 1.0 + K
    return q, mine


def sabr_ref(p):
    alpha, bi, rho, nu, k, T = p
    beta = (0.0, 0.5, 1.0)[min(2, int(bi))]
    F = 0.03 if beta < 1 else 1.0  # rates-style forward for beta < 1; any F for beta = 1
    return ql.sabrVolatility(F * math.exp(k), F, T, alpha, beta, nu, rho), T


def judge(errs, excluded, n):
    e = np.abs(np.array(errs))
    res = {"points": n, "judged": len(e), "excluded_below_price_floor": excluded,
           "max_abs_error": float(e.max()), "p999_abs_error": float(np.quantile(e, 0.999))}
    res["valid"] = excluded <= 0.01 * n
    res["pass"] = bool(res["valid"] and res["max_abs_error"] <= 1e-4 and res["p999_abs_error"] <= 5e-5)
    return res


def faces(fn, box, centre):
    """Every one of the 2 x dim faces just outside, plus NaN and infinity: all must raise DomainError."""
    out = []
    for j, (name, lo, hi) in enumerate(box):
        for val in (lo - 1e-9 * max(1.0, abs(lo)), hi + 1e-9 * max(1.0, abs(hi))):
            p = list(centre)
            p[j] = val
            out.append((name, val, raises(fn, p)))
    for bad in (float("nan"), float("inf")):
        p = list(centre)
        p[0] = bad
        out.append(("v0", repr(bad), raises(fn, p)))
    return out


def raises(fn, p):
    try:
        fn(p)
    except DomainError:
        return True
    except Exception:  # any other failure, or a silent value, is not the required E_DOMAIN
        return False
    return False


def run(heston_iv, sabr_iv, limit=None):
    report = {}
    for name, box, ref, sur in (("heston", HESTON, heston_ref, heston_iv), ("sabr", SABR, sabr_ref, sabr_iv)):
        X = test_set(box)
        if limit:
            X = np.vstack([X[: limit // 2], X[N_MAIN: N_MAIN + limit // 2]])
        errs, excl = [], 0
        for p in X:
            r, _ = ref(p)
            if r is None:
                excl += 1
                continue
            errs.append(sur(p) - r)
        report[name] = judge(errs, excl, len(X))
        if name == "heston":
            centre = [(lo + hi) / 2 for _, lo, hi in box]
            f = faces(sur, box, centre)
            report[name]["faces"] = sum(ok for *_, ok in f)
            report[name]["faces_total"] = len(f)
            report[name]["pass"] = bool(report[name]["pass"] and report[name]["faces"] == len(f))
    return report


def guarded(fn, box):
    def g(p):
        for (name, lo, hi), v in zip(box, p):
            if not (lo <= v <= hi):  # also false for NaN
                raise DomainError(name)
        return fn(p)
    return g


def self_test(n):
    """The harness must pass the exact pricer and fail a pricer off by 2 bp; otherwise it is vacuous."""
    exact_h = guarded(lambda p: heston_ref(p)[0], HESTON)
    exact_s = guarded(lambda p: sabr_ref(p)[0], SABR)
    good = run(exact_h, exact_s, n)
    bad = run(guarded(lambda p: heston_ref(p)[0] + 2e-4, HESTON), guarded(lambda p: sabr_ref(p)[0] + 2e-4, SABR), n)
    unguarded = run(lambda p: heston_ref(p)[0], lambda p: sabr_ref(p)[0], n)
    X = test_set(HESTON)
    chk = [heston_ql_check(X[i]) for i in range(0, N_MAIN, N_MAIN // 200)]
    gap = max(abs(a - b) for a, b in chk)
    out = {"n": n, "exact": good, "biased_2bp": bad, "no_domain_guard": unguarded,
           "quantlib_heston_check": {"points": len(chk), "max_abs_price_gap": gap}}
    assert good["heston"]["pass"] and good["sabr"]["pass"], good
    assert not bad["heston"]["pass"] and not bad["sabr"]["pass"], bad
    assert not unguarded["heston"]["pass"]
    return out


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        i = sys.argv.index("--self-test")
        n = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 2000
        res = self_test(n)
        (HERE.parent / "A5_HARNESS_SELFTEST.json").write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps(res, indent=1, default=str))
    elif "--module" in sys.argv:
        spec = importlib.util.spec_from_file_location("cand", sys.argv[sys.argv.index("--module") + 1])
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        print(json.dumps(run(m.heston_iv, m.sabr_iv), indent=1))
