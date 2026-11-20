"""Stage K review-fix goldens (lane k-v1-rev1, rulings KR-340 onwards in specifications/stage-k-rulings-rev1.md).

Suites (all in datasets/golden/stage_k):
- sabrz_k: vol.sabr.hagan where z = (nu/alpha) sqrt(A) L is small (|z| about 1e-8 to 1e-4) or large and negative,
  both signs of rho (K-9 review finding 7, ruling KR-340). The direct chi(z) loses digits as eps/|z| for small z
  and cancels in s + z - rho for large negative z; a tight relative limit (1e-12) makes those visible.
- ivdeep_k: vol.option.implied far out of the money (finding 8, ruling KR-341): prices down to about 1e-80 that
  still identify the vol (value cases), and prices of 1e-200 and below, or subnormal, that do not
  (E_NO_CONVERGENCE). The oracle prices at 60 digits and computes the KR-341 estimate at the true vol.
- fuzzfix_k: fuzz inputs from the failed scheduled runs on main (2026-11-09 to 11-16) that were fixed without
  a golden of the exact input (K-9 finding 1).

This oracle is written from specifications/05-volatility/sabr.md in mpmath, at 50 digits plus two digits per
decade of |z| (the reference evaluates the direct formula, so it needs the extra digits where it cancels). It
does not import quantforge_core.

    cd oracle/python && uv run python -W ignore gen_stage_k_rev1.py
"""
import math

import mpmath as mp

from qf_oracle import common
from qf_oracle.common import Suite, f

mp.mp.dps = 50
G = "oracle/python/gen_stage_k_rev1.py"
ORACLE = "mpmath 50 digits (independent oracle, gen_stage_k_rev1.py)"
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
        return f(al * m * h / den), float(z)


def sabrz():
    s = Suite("sabrz_k", "specifications/05-volatility/sabr.md", G)
    op = "vol.sabr.hagan"
    # beta = 1: A = 1 and z = (nu/alpha) ln(f/x), so x = f exp(-z alpha/nu) puts z where wanted.
    for rho in (-0.4, 0.3, 0.95):
        for zt in (1e-8, 1.01e-7, 1e-6, 1e-4, -1e-8, -1.01e-7, -1e-6, -1e-4):
            fwd, t, al, be, nu = 100.0, 1.5, 0.2, 1.0, 0.4
            ks = [fwd * math.exp(-zt * al / nu)]
            vols, zs = zip(*(hagan_ref(fwd, k, t, al, be, rho, nu) for k in ks))
            s.add(op, dict(forward=fwd, strikes=ks, expiry_years=t, alpha=al, beta=be, rho=rho, nu=nu), {"vols": list(vols)},
                  cls="interpolation", verified=[ORACLE], limit=SABR_LIMIT, tags=["stage_k", "sabr_small_z"],
                  description=f"z = {zs[0]:.3g}, rho = {rho}")
    # beta = 0.5 with a shift: z small through a strike next to the forward
    for rho in (-0.3, 0.3):
        fwd, sh, t, al, be, nu = 0.01, 0.02, 2.0, 0.03, 0.5, 0.35
        ks = [fwd * (1 + d) for d in (2e-7, 2e-6, -2e-6, 2e-4)]
        vols, zs = zip(*(hagan_ref(fwd, k, t, al, be, rho, nu, sh) for k in ks))
        s.add(op, dict(forward=fwd, strikes=ks, expiry_years=t, alpha=al, beta=be, rho=rho, nu=nu, shift=sh), {"vols": list(vols)},
              cls="interpolation", verified=[ORACLE], limit=SABR_LIMIT, tags=["stage_k", "sabr_small_z", "shift"],
              description="z from " + ", ".join(f"{z:.2g}" for z in zs))
    # large |z|: s + z - rho cancels in the direct form for z far below 0
    for rho in (-0.4, 0.3, 0.95):
        fwd, t, be = 100.0, 1.0, 1.0
        for al, nu in ((0.01, 5.0), (1e-4, 5.0)):
            ks = [fwd * math.exp(2.0), fwd * math.exp(-2.0)]
            vols, zs = zip(*(hagan_ref(fwd, k, t, al, be, rho, nu) for k in ks))
            s.add(op, dict(forward=fwd, strikes=ks, expiry_years=t, alpha=al, beta=be, rho=rho, nu=nu), {"vols": list(vols)},
                  cls="interpolation", verified=[ORACLE], limit=SABR_LIMIT, tags=["stage_k", "sabr_large_z"],
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


def ivdeep():
    s = Suite("ivdeep_k", "specifications/05-volatility/black-models.md", G)
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
                s.add(op, ins, {"vol": sig}, cls="root_finding", verified=[ORACLE], limit=lim, tags=["stage_k", "deep_otm"],
                      description=f"price {p:.3g}; KR-341 estimate {float(est):.2g} at the true vol")
            else:
                assert est > 1e-8, (model, K, T, sig, est)
                s.add(op, ins, error="E_NO_CONVERGENCE", cls="date_and_convention", verified=[ORACLE], tags=["stage_k", "deep_otm", "not_identified"],
                      description=f"price {p:.3g}; KR-341 estimate {float(est):.2g}: the price does not identify the vol")
    s.write()


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_k"
    try:
        sabrz()
        ivdeep()
    finally:
        common.GOLDEN = keep


if __name__ == "__main__":
    main()
