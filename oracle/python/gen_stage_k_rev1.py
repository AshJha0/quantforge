"""Stage K review-fix goldens (lane k-v1-rev1, rulings KR-340 onwards in specifications/stage-k-rulings-rev1.md).

Suites: sabrz_c and ivdeep_c in datasets/golden/stage_c (regression cases for stage C operations; stage C has no
outside-share floor, and these are not stage K plan items), fuzzrev_k in datasets/golden/stage_k (error cases only).
- sabrz_c: vol.sabr.hagan where z = (nu/alpha) sqrt(A) L is small (|z| about 1e-8 to 1e-4) or large and negative,
  both signs of rho (K-9 review finding 7, ruling KR-340). The direct chi(z) loses digits as eps/|z| for small z
  and cancels in s + z - rho for large negative z; a tight relative limit (1e-12) makes those visible.
- ivdeep_c: vol.option.implied far out of the money (finding 8, ruling KR-341): prices down to about 1e-80 that
  still identify the vol (value cases), and prices of 1e-200 and below, or subnormal, that do not
  (E_NO_CONVERGENCE). The oracle prices at 60 digits and computes the KR-341 estimate at the true vol.
- fuzzrev_k: fuzz inputs from the failed scheduled runs on main (2026-11-09 to 11-16) that were fixed without
  a golden of the exact input (K-9 finding 1).

This oracle is written from specifications/05-volatility/sabr.md in mpmath, at 50 digits plus two digits per
decade of |z| (the reference evaluates the direct formula, so it needs the extra digits where it cancels). It
does not import quantforge_core.

    cd oracle/python && uv run python -W ignore gen_stage_k_rev1.py
"""
import json
import math
from pathlib import Path

import mpmath as mp
from scipy.integrate import quad
from scipy.optimize import brentq
from scipy.special import erfcx, log_ndtr

from qf_oracle import common
from qf_oracle.common import Suite, f

mp.mp.dps = 50
G = "oracle/python/gen_stage_k_rev1.py"
ORACLE = "mpmath 50 digits (independent oracle, gen_stage_k_rev1.py)"
QUAD = "scipy quad of chi = int_0^z dt/sqrt(1 - 2 rho t + t^2), a different formulation (library-primitive), within 1e-14"
LOGSOLVE = "scipy brentq on ln V with log_ndtr / erfcx, a different formulation (library-primitive), within 1e-12"
SABR_LIMIT = {"absolute": 0.0, "relative": 1e-12,
              "reason": "KR-340: chi(z) evaluated without cancellation; the direct form misses by 2.7e-9 at z = 1.01e-7"}


def M(x):
    return mp.mpf(x)


def hagan_ref(f0, x0, t, alpha, beta, rho, nu, shift=0.0):
    """Hagan lognormal vol, written from the spec, at enough digits for the direct chi."""
    fz = abs(float(nu / alpha * ((f0 + shift) * (x0 + shift)) ** ((1 - beta) / 2) * math.log((f0 + shift) / (x0 + shift))))
    extra = int(2 * abs(math.log10(fz))) if fz > 0 else 0
    with mp.workdps(50 + extra):
        fs, xs = M(f0) + M(shift), M(x0) + M(shift)
        al, be, r, n, T = M(alpha), M(beta), M(rho), M(nu), M(t)
        A = (fs * xs) ** (1 - be)
        L = mp.log(fs / xs)
        c = (1 - be) ** 2 * L * L
        z = n / al * mp.sqrt(A) * L
        if z == 0:
            m = mp.mpf(1)
        else:
            chi = mp.log((mp.sqrt(1 - 2 * r * z + z * z) + z - r) / (1 - r))
            m = z / chi
        den = mp.sqrt(A) * (1 + c / 24 + c * c / 1920)
        h = 1 + T * ((1 - be) ** 2 * al * al / (24 * A) + r * be * n * al / (4 * mp.sqrt(A)) + (2 - 3 * r * r) * n * n / 24)
        v = f(al * m * h / den)
    q = quad_vol(f0, x0, t, alpha, beta, rho, nu, shift)
    assert abs(q / v - 1) < 1e-14, (f0, x0, rho, q, v)
    return v, float(z)


def quad_vol(f0, x0, t, alpha, beta, rho, nu, shift=0.0):
    """Hagan vol with chi from scipy quad of its integral form (library-primitive check)."""
    fs, xs = f0 + shift, x0 + shift
    big_a = (fs * xs) ** (1 - beta)
    big_l = math.log(fs / xs)
    c = (1 - beta) ** 2 * big_l * big_l
    z = nu / alpha * math.sqrt(big_a) * big_l
    g = lambda u: 1 / math.sqrt(1 - 2 * rho * u + u * u)  # noqa: E731
    pts = [0.0, z] if abs(z) <= 1 else [0.0] + [math.copysign(10.0 ** e, z) for e in range(int(math.log10(abs(z))) + 1)] + [z]
    pts = sorted(set(pts), key=abs)
    chi = sum(quad(g, a, b, epsabs=0, epsrel=1e-13, limit=200)[0] for a, b in zip(pts, pts[1:]))
    den = math.sqrt(big_a) * (1 + c / 24 + c * c / 1920)
    h = 1 + t * ((1 - beta) ** 2 * alpha * alpha / (24 * big_a) + rho * beta * nu * alpha / (4 * math.sqrt(big_a)) + (2 - 3 * rho * rho) * nu * nu / 24)
    return alpha * (z / chi) * h / den


def sabrz():
    s = Suite("sabrz_c", "specifications/05-volatility/sabr.md", G)
    op = "vol.sabr.hagan"
    # beta = 1: A = 1 and z = (nu/alpha) ln(f/x), so x = f exp(-z alpha/nu) puts z where wanted.
    for rho in (-0.4, 0.3, 0.95):
        for zt in (1e-8, 1.01e-7, 1e-6, 1e-4, -1e-8, -1.01e-7, -1e-6, -1e-4):
            fwd, t, al, be, nu = 100.0, 1.5, 0.2, 1.0, 0.4
            ks = [fwd * math.exp(-zt * al / nu)]
            vols, zs = zip(*(hagan_ref(fwd, k, t, al, be, rho, nu) for k in ks))
            s.add(op, dict(forward=fwd, strikes=ks, expiry_years=t, alpha=al, beta=be, rho=rho, nu=nu), {"vols": list(vols)},
                  cls="interpolation", verified=[ORACLE, QUAD], limit=SABR_LIMIT, tags=["stage_k", "sabr_small_z"],
                  description=f"z = {zs[0]:.3g}, rho = {rho}")
    # beta = 0.5 with a shift: z small through a strike next to the forward
    for rho in (-0.3, 0.3):
        fwd, sh, t, al, be, nu = 0.01, 0.02, 2.0, 0.03, 0.5, 0.35
        ks = [fwd * (1 + d) for d in (2e-7, 2e-6, -2e-6, 2e-4)]
        vols, zs = zip(*(hagan_ref(fwd, k, t, al, be, rho, nu, sh) for k in ks))
        s.add(op, dict(forward=fwd, strikes=ks, expiry_years=t, alpha=al, beta=be, rho=rho, nu=nu, shift=sh), {"vols": list(vols)},
              cls="interpolation", verified=[ORACLE, QUAD], limit=SABR_LIMIT, tags=["stage_k", "sabr_small_z", "shift"],
              description="z from " + ", ".join(f"{z:.2g}" for z in zs))
    # large |z|: s + z - rho cancels in the direct form for z far below 0
    for rho in (-0.4, 0.3, 0.95):
        fwd, t, be = 100.0, 1.0, 1.0
        for al, nu in ((0.01, 5.0), (1e-4, 5.0)):
            ks = [fwd * math.exp(2.0), fwd * math.exp(-2.0)]
            vols, zs = zip(*(hagan_ref(fwd, k, t, al, be, rho, nu) for k in ks))
            s.add(op, dict(forward=fwd, strikes=ks, expiry_years=t, alpha=al, beta=be, rho=rho, nu=nu), {"vols": list(vols)},
                  cls="interpolation", verified=[ORACLE, QUAD], limit=SABR_LIMIT, tags=["stage_k", "sabr_large_z"],
                  description="z = " + ", ".join(f"{z:.3g}" for z in zs))
    s.write()


def _bs(F, K, T, s, phi, D=1):
    F, K, T, s, D = map(M, (F, K, T, s, D))
    sd = s * mp.sqrt(T)
    d1 = mp.log(F / K) / sd + sd / 2
    d2 = d1 - sd
    price = D * phi * (F * mp.ncdf(phi * d1) - K * mp.ncdf(phi * d2))
    mag = D * (F * mp.ncdf(phi * d1) + K * mp.ncdf(phi * d2))
    vega = D * F * mp.npdf(d1) * mp.sqrt(T)
    return price, mag, vega


def _bach(F, K, T, s, phi, D=1):
    F, K, T, s, D = map(M, (F, K, T, s, D))
    sd = s * mp.sqrt(T)
    x = (F - K) / sd
    price = D * (phi * (F - K) * mp.ncdf(phi * x) + sd * mp.npdf(x))
    mag = D * (abs(F - K) * mp.ncdf(phi * x) + sd * mp.npdf(x))
    vega = D * mp.sqrt(T) * mp.npdf(x)
    return price, mag, vega


def log_solve(model, kind, F, K, T, p):
    """The vol from scipy brentq on ln V, priced in log space (log_ndtr; erfcx for the Bachelier Mills ratio)."""
    phi = 1 if kind == "CALL" else -1

    def lv(s):
        sd = s * math.sqrt(T)
        if model == "BACHELIER":
            u = -phi * (F - K) / sd
            r = erfcx(u / math.sqrt(2)) * math.sqrt(math.pi / 2)
            return math.log(sd) - u * u / 2 - math.log(2 * math.pi) / 2 + math.log1p(-u * r)
        d1 = math.log(F / K) / sd + sd / 2
        a, b = math.log(F) + log_ndtr(phi * d1), math.log(K) + log_ndtr(phi * (d1 - sd))
        return a + math.log1p(-math.exp(b - a)) if phi > 0 else b + math.log1p(-math.exp(a - b))

    lo, hi = (1e-3, 50.0) if model == "BACHELIER" else (1e-3, 3.0)
    return brentq(lambda s: lv(s) - math.log(p), lo, hi, xtol=1e-15, rtol=8.9e-16, maxiter=500)


def ivdeep():
    s = Suite("ivdeep_c", "specifications/05-volatility/black-models.md", G)
    op = "vol.option.implied"
    lim = {"absolute": 0.0, "relative": 1e-9, "reason": "KR-341: an accepted vol has estimated relative error at most 1e-10"}
    with mp.workdps(60):
        cases = [("BLACK_76", "CALL", 100.0, 160.0, 1.0, 0.2), ("BLACK_76", "CALL", 100.0, 300.0, 1.0, 0.2),
                 ("BLACK_76", "PUT", 100.0, 40.0, 0.5, 0.25), ("BLACK_76", "PUT", 100.0, 10.0, 2.0, 0.3),
                 ("BLACK_76", "CALL", 100.0, 1000.0, 1.0, 0.3), ("BACHELIER", "CALL", 100.0, 160.0, 1.0, 8.0),
                 ("BACHELIER", "PUT", 100.0, 20.0, 1.0, 6.0),
                 # not identified: the two terms of V cancel to below 1e-200, or the price is subnormal
                 ("BLACK_76", "CALL", 100.0, 300.0, 0.1, 0.1), ("BLACK_76", "CALL", 100.0, 500.0, 1.0, 0.05),
                 ("BLACK_76", "CALL", 100.0, 1000.0, 0.1, 0.2), ("BACHELIER", "PUT", 100.0, 86.83731917681901, 2.9082679923151997, 0.20272253589725567),
                 ("BACHELIER", "CALL", 100.0, 130.0, 1.0, 1.0)]
        for model, kind, F, K, T, sig in cases:
            phi = 1 if kind == "CALL" else -1
            price, mag, vega = (_bach if model == "BACHELIER" else _bs)(F, K, T, sig, phi)
            p = f(price)
            assert p > 0, (model, K, T, sig)
            floor = 2 ** mp.mpf(-1070) * (1 + abs(M(F)) + abs(M(K)) + M(sig) * mp.sqrt(M(T)))
            est = (2 ** mp.mpf(-52) * mag + floor) / (M(sig) * vega)
            ins = dict(model=model, option_type=kind, forward=F, strike=K, expiry_years=T, discount_factor=1.0, price=p)
            if est < 1e-12:
                v = log_solve(model, kind, F, K, T, p)
                assert abs(v / sig - 1) < 1e-12, (model, K, T, sig, v)
                s.add(op, ins, {"vol": sig}, cls="root_finding", verified=[ORACLE, LOGSOLVE], limit=lim, tags=["stage_k", "deep_otm"],
                      description=f"price {p:.3g}; KR-341 estimate {float(est):.2g} at the true vol")
            else:
                assert est > 1e-8, (model, K, T, sig, est)
                s.add(op, ins, error="E_NO_CONVERGENCE", cls="date_and_convention", verified=[ORACLE], tags=["stage_k", "deep_otm", "not_identified"],
                      description=f"price {p:.3g}; KR-341 estimate {float(est):.2g}: the price does not identify the vol")
    s.write()


def fuzzrev():
    """Two fuzz inputs fixed before stage K without a golden of the exact input (oracle/python/data/fuzz_k_inputs.jsonl).

    Expected codes follow R6-8.1 (a finite input whose required intermediate is not finite is E_NON_FINITE):
    CIR with sigma = 5e297 needs sigma^2 = 2.5e595 (above the largest binary64, about 1.8e308); the GARCH
    Student-t estimate on a return of 2.68e297 needs its square for the sample variance start.
    """
    s = Suite("fuzzrev_k", "specifications/01-core/limits.md", G)
    big = mp.mpf(2) ** 1024
    for line in (Path(__file__).parent / "data" / "fuzz_k_inputs.jsonl").read_text("utf-8").splitlines():
        row = json.loads(line)
        ins = row["inputs"]
        if row["operation"] == "rates.shortrate.zcb_option":
            assert M(ins["sigma"]) ** 2 >= big
        else:
            assert max(M(abs(r)) for r in ins["returns"]) ** 2 >= big
        s.add(row["operation"], ins, error="E_NON_FINITE", cls="date_and_convention", verified=["R6-8.1 rule (hand)"],
              tags=["stage_k", "fuzz"], description=f"fuzz run {row['fuzz_run']}, seed case {row['seed_case']}")
    s.write()


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_k"
    try:
        common.GOLDEN = keep.parent / "stage_c"
        sabrz()
        ivdeep()
        common.GOLDEN = keep.parent / "stage_k"
        fuzzrev()
    finally:
        common.GOLDEN = keep


if __name__ == "__main__":
    main()
