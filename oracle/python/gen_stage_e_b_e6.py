"""Stage E spec B, E6: correlation matrices (validation, Higham nearest correlation), implied correlation, dispersion.

Nearest correlation goldens come from Higham's alternating projections with Dykstra's correction, run to 1e-15 in the
iterate, and are cross-checked against an independent dual Newton-type solve (Qi and Sun) to 1e-11. The golden is the
unique minimiser, never an iteration path; acceptance is a convergence tolerance on entries (ruling E-B18)."""
import math

import mpmath as mp
import numpy as np
from scipy.optimize import minimize

from qf_oracle.common import note
from gen_stage_e_b import A, E, I, MUTANTS, S, caught, f, write

ENT = {"absolute": 2e-5, "relative": 0.0, "reason": "convergence tolerance on entries (ruling E-B18): a correlation error of 2e-5 moves a 10-name basket vol by under 1e-5 relative"}


def psd_proj(X):
    w, V = np.linalg.eigh((X + X.T) / 2)
    return (V * np.maximum(w, 0)) @ V.T


def higham(Am, tol=1e-15, dykstra=True, maxit=200000):
    Y = Am.copy()
    dS = np.zeros_like(Am)
    for _ in range(maxit):
        R = Y - dS if dykstra else Y
        X = psd_proj(R)
        if dykstra:
            dS = X - R
        Yn = X.copy()
        np.fill_diagonal(Yn, 1.0)
        if np.max(np.abs(Yn - Y)) < tol:
            return Yn
        Y = Yn
    raise RuntimeError("Higham did not converge")


def dual(Am):
    """Qi-Sun dual: minimise theta(y) = 1/2 ||(A + diag y)_+||^2 - sum y; gradient diag((A + diag y)_+) - 1."""
    n = len(Am)

    def fg(y):
        P = psd_proj(Am + np.diag(y))
        return 0.5 * np.sum(P * P) - y.sum(), np.diag(P) - 1
    r = minimize(fg, np.zeros(n), jac=True, method="BFGS", options={"gtol": 1e-14, "maxiter": 10000})
    X = psd_proj(Am + np.diag(r.x))
    np.fill_diagonal(X, 1.0)
    return X


def naive(Am):
    """Wrong convention: clip eigenvalues at 0 and rescale to unit diagonal."""
    P = psd_proj(Am)
    d = np.sqrt(np.diag(P))
    return P / np.outer(d, d)


def min_eig(M):
    n = len(M)
    return f(min(mp.eigsy(mp.matrix([[(mp.mpf(M[i][j]) + mp.mpf(M[j][i])) / 2 for j in range(n)] for i in range(n)]))[0]))


MATS = {
    "higham3": [[1, 1, 0], [1, 1, 1], [0, 1, 1]],
    "pairwise4": [[1, .9, .7, -.6], [.9, 1, .3, .4], [.7, .3, 1, .8], [-.6, .4, .8, 1]],
    "stress5": [[1, .95, .9, .1, -.85], [.95, 1, .5, .2, -.1], [.9, .5, 1, .9, .3], [.1, .2, .9, 1, .6], [-.85, -.1, .3, .6, 1]],
    "near6": None,
    "valid4": [[1, .5, .3, .2], [.5, 1, .4, .1], [.3, .4, 1, .25], [.2, .1, .25, 1]],
}
# R5 audit B2: flags that come out false (validate only; nearest needs a symmetric input)
FLAGS = {
    "asym_ulp": [[1, .3, .2], [.30000000000000004, 1, .1], [.2, .1, 1]],
    "diag_ulp": [[.9999999999999999, .3, .2], [.3, 1, .1], [.2, .1, 1]],
    "range_12": [[1, 1.2, 0], [1.2, 1, 0], [0, 0, 1]],
    "asym_big": [[1, .5, .1], [.2, 1, .3], [.4, 0, 1]],
}
# R5 audit B2/B4: nearest edge inputs
EDGE = {"one": [[.7]], "nonunit_diag": [[2, .5], [.5, .5]], "rho_13": [[1, 1.3], [1.3, 1]], "rankdef20": None}


def near6():
    g = np.random.default_rng(6)
    B = g.standard_normal((6, 3))
    C = B @ B.T
    d = np.sqrt(np.diag(C))
    C = C / np.outer(d, d)
    C[0, 5] = C[5, 0] = round(C[0, 5] - .35, 6)
    return [[round(x, 6) for x in row] for row in C]


def perturbed(n, seed, bump):
    """A factor-model correlation with a block of pairs shifted by `bump` (as when pairs are estimated on different windows)."""
    g = np.random.default_rng(seed)
    B = g.standard_normal((n, 3))
    C = B @ B.T + np.diag(g.uniform(.2, 1, n))
    d = np.sqrt(np.diag(C))
    C = C / np.outer(d, d)
    for i in range(0, n - 1, 3):
        C[i, i + 1] = C[i + 1, i] = max(-.99, min(.99, C[i, i + 1] + bump))
    return [[round(float(x), 6) for x in row] for row in C]


def rankdef20():
    g = np.random.default_rng(20)
    U = g.uniform(-1, 1, (20, 20))
    M = np.round((U + U.T) / 2, 6)
    np.fill_diagonal(M, 1.0)
    return M.tolist()


def corr_e():
    s = S("corr_e", "06-risk/correlation.md")
    MATS["near6"] = near6()
    for n, seed, bump in ((7, 71, .4), (8, 81, .5), (10, 101, .3), (12, 121, .25), (8, 82, -.45), (15, 151, .2)):
        MATS[f"perturbed{n}_{seed}"] = perturbed(n, seed, bump)
    vop, nop = "risk.corr.validate", "risk.corr.nearest"
    for key, M in MATS.items():
        Mf = [[float(x) for x in row] for row in M]
        Am = np.array(Mf)
        me = min_eig(Mf)
        sym = all(Mf[i][j] == Mf[j][i] for i in range(len(Mf)) for j in range(len(Mf)))
        diag = all(Mf[i][i] == 1.0 for i in range(len(Mf)))
        rng = all(-1 <= x <= 1 for row in Mf for x in row)
        assert abs(me) > 1e-4, "eigenvalue too close to the PSD boundary for a stable boolean"
        psd = me >= -1e-10
        s.add(vop, {"matrix": Mf}, {"symmetric": sym, "unit_diagonal": diag, "in_range": rng, "min_eigenvalue": me, "psd": psd, "valid": sym and diag and rng and psd},
              cls=I, verified=["mpmath-50 eigsy"], tags=["corr", "validate", key])
        X = higham(Am)
        X2 = dual(Am)
        assert np.max(np.abs(X - X2)) < 1e-6, f"{key}: Higham and dual disagree {np.max(np.abs(X - X2)):.2e}"
        assert np.min(np.linalg.eigvalsh(X)) > -1e-12
        dist = float(np.sqrt(np.sum((X - Am) ** 2)))
        out = {"matrix": [[float(x) for x in row] for row in X], "frobenius_distance": dist}
        s.add(nop, {"matrix": Mf}, out, cls=I, verified=["independent-replay Higham-Dykstra", "dual BFGS (Qi-Sun)"], tags=["corr", "nearest", key],
              limit=ENT)
        if me < 0:
            caught("corr_e", f"{key}: eigenvalue clip and rescale", float(np.max(np.abs(naive(Am) - X))), 2e-5)
            nd = higham(Am, tol=1e-13, dykstra=False)
            if np.max(np.abs(nd - X)) > 2e-5:
                caught("corr_e", f"{key}: alternating projections without Dykstra", float(np.max(np.abs(nd - X))), 2e-5)
        else:
            assert np.max(np.abs(X - Am)) < 1e-12
    for key, M in FLAGS.items():
        Mf = [[float(x) for x in row] for row in M]
        n = len(Mf)
        me = min_eig(Mf)
        assert abs(me) > 1e-4
        sym = all(Mf[i][j] == Mf[j][i] for i in range(n) for j in range(n))
        diag = all(Mf[i][i] == 1.0 for i in range(n))
        rng = all(-1 <= x <= 1 for row in Mf for x in row)
        psd = me >= -1e-10
        s.add(vop, {"matrix": Mf}, {"symmetric": sym, "unit_diagonal": diag, "in_range": rng, "min_eigenvalue": me, "psd": psd, "valid": sym and diag and rng and psd},
              cls=I, verified=["mpmath-50 eigsy"], tags=["corr", "validate", "flags", key])
    EDGE["rankdef20"] = rankdef20()
    for key, M in EDGE.items():
        Am = np.array(M, dtype=float)
        X = higham(Am, tol=1e-13)
        if len(M) > 1:
            X2 = dual(Am)
            assert np.max(np.abs(X - X2)) < 1e-6, f"{key}: solvers disagree {np.max(np.abs(X - X2)):.1e}"
        ev = np.linalg.eigvalsh(X)
        assert ev.min() > -1e-10
        out = {"matrix": X.tolist(), "frobenius_distance": float(np.sqrt(np.sum((X - Am) ** 2)))}
        s.add(nop, {"matrix": [[float(x) for x in r] for r in M]}, out, cls=I, verified=["independent-replay Higham-Dykstra", "dual BFGS (Qi-Sun)"],
              tags=["corr", "nearest", "edge", key] + (["rank-deficient"] if int((ev < 1e-8).sum()) >= 3 else []), limit=ENT)
        if key == "rankdef20":
            note(f"corr_e rankdef20: {int((ev < 1e-8).sum())} zero eigenvalues in the answer")
            caught("corr_e", "rankdef20: eigenvalue clip and rescale", float(np.max(np.abs(naive(Am) - X))), 2e-5)
    # hand: 2x2 already valid; the Higham 3x3 values
    X3 = s.cases[1]["expected"]["outputs"]["matrix"]
    assert abs(X3[0][1] - 0.7607) < 1e-4 and abs(X3[0][2] - 0.1573) < 1e-4  # Higham (2002), section 4 example
    for d, M, code in (("not square", [[1.0, .5], [.5, 1.0], [.2, .3]], "E_INPUT"), ("empty", [], "E_INPUT")):
        s.add(vop, {"matrix": M}, error=code, cls=E, tags=["invalid"], description=d)
        s.add(nop, {"matrix": M}, error=code, cls=E, tags=["invalid"], description=d)
    s.add(nop, {"matrix": [[1.0, .5], [.4, 1.0]]}, error="E_INPUT", cls=E, tags=["invalid", "ruling"], description="nearest needs a symmetric input")
    # implied correlation
    iop, dop = "risk.corr.implied", "risk.corr.dispersion"
    for w, v, vI in (([.5, .5], [.2, .3], .22), ([.4, .35, .25], [.25, .3, .2], .19), ([.2] * 5, [.35, .28, .3, .22, .4], .21), ([.6, .3, .1], [.18, .24, .45], .2),
                     ([.25] * 4, [.3, .3, .3, .3], .3)):
        wm, vm = [mp.mpf(x) for x in w], [mp.mpf(x) for x in v]
        num = mp.mpf(vI) ** 2 - mp.fsum(a * a * b * b for a, b in zip(wm, vm))
        den = mp.fsum(wm[i] * wm[j] * vm[i] * vm[j] for i in range(len(w)) for j in range(len(w)) if i != j)
        rho = num / den
        s.add(iop, {"weights": w, "vols": v, "index_vol": vI}, {"correlation": f(rho)}, cls=A, verified=["hand", "mpmath-50"], tags=["corr", "implied"])
        caught("corr_e", f"implied {len(w)}: sum over i<j without the factor 2", abs(f(num / (den / 2) - rho)), 1e-10)
        num2 = mp.mpf(vI) ** 2 - mp.fsum(a * b * b for a, b in zip(wm, vm))
        caught("corr_e", f"implied {len(w)}: weights not squared", abs(f(num2 / den - rho)), 1e-10)
    s.add(iop, {"weights": [1.0], "vols": [.2], "index_vol": .2}, error="E_INPUT", cls=E, tags=["invalid"], description="at least two names")
    # R5 audit B5 (ruling E-B33): weights >= 0, at least two positive
    wm, vm = [mp.mpf(.5), mp.mpf(.5), mp.mpf(0)], [mp.mpf(.2), mp.mpf(.3), mp.mpf(.25)]
    rho0 = (mp.mpf(.22) ** 2 - mp.fsum(a * a * b * b for a, b in zip(wm, vm))) / mp.fsum(wm[i] * wm[j] * vm[i] * vm[j] for i in range(3) for j in range(3) if i != j)
    s.add(iop, {"weights": [.5, .5, 0.0], "vols": [.2, .3, .25], "index_vol": .22}, {"correlation": f(rho0)}, cls=A, verified=["hand", "mpmath-50"], tags=["corr", "implied", "zero-weight"],
          description="a zero weight drops the name: same value as the two-name case with weights 0.5, 0.5")
    s.add(iop, {"weights": [1.0, 0.0], "vols": [.2, .3], "index_vol": .2}, error="E_DOMAIN", cls=E, tags=["invalid", "ruling"], description="one positive weight: zero denominator")
    s.add(iop, {"weights": [.6, -.4], "vols": [.2, .3], "index_vol": .2}, error="E_DOMAIN", cls=E, tags=["invalid", "ruling"], description="negative weight")
    s.add(iop, {"weights": [.5, .5], "vols": [.2, 0.0], "index_vol": .2}, error="E_DOMAIN", cls=E, tags=["invalid"], description="vols must be positive")
    # dispersion: long constituent variance, short index variance, vega notional split by weight
    for w, K, KI, rv, rI, Nv in (([.5, .5], [.25, .3], .24, [.28, .35], .22, 1e5), ([.4, .35, .25], [.27, .31, .22], .2, [.3, .25, .2], .23, 2e5),
                                 ([.2] * 5, [.33, .3, .29, .24, .41], .22, [.4, .31, .3, .27, .45], .2, 5e4)):
        wm = [mp.mpf(x) for x in w]
        Ni = [Nv * a / (2 * mp.mpf(k)) for a, k in zip(wm, K)]
        NI = Nv / (2 * mp.mpf(KI))
        pnl = mp.fsum(n * (mp.mpf(r) ** 2 - mp.mpf(k) ** 2) for n, r, k in zip(Ni, rv, K)) - NI * (mp.mpf(rI) ** 2 - mp.mpf(KI) ** 2)

        def rho(vI, vs):
            vm = [mp.mpf(x) for x in vs]
            return (mp.mpf(vI) ** 2 - mp.fsum(a * a * b * b for a, b in zip(wm, vm))) / mp.fsum(wm[i] * wm[j] * vm[i] * vm[j] for i in range(len(w)) for j in range(len(w)) if i != j)
        out = {"pnl": f(pnl), "implied_correlation": f(rho(KI, K)), "realized_correlation": f(rho(rI, rv)), "constituent_variance_notionals": [f(x) for x in Ni], "index_variance_notional": f(NI)}
        s.add(dop, {"weights": w, "vol_strikes": K, "index_vol_strike": KI, "realized_vols": rv, "index_realized_vol": rI, "vega_notional": Nv}, out, cls=A,
              verified=["hand", "mpmath-50"], tags=["corr", "dispersion"], output_classes={"implied_correlation": A, "realized_correlation": A},
              limit={"absolute": 1e-12 * Nv, "relative": 1e-10, "reason": "1e-12 per unit vega notional"})
        alt = mp.fsum(Nv * a / (2 * mp.mpf(k)) * (mp.mpf(r) - mp.mpf(k)) * 2 * mp.mpf(k) for a, r, k in zip(wm, rv, K)) - Nv * (mp.mpf(rI) - mp.mpf(KI))
        caught("corr_e", f"dispersion {len(w)}: vol P&L instead of variance P&L", abs(f(alt - pnl)), 1e-12 * Nv + 1e-10 * abs(f(pnl)))
    s.add(dop, {"weights": [.5, .5], "vol_strikes": [.25], "index_vol_strike": .24, "realized_vols": [.28, .35], "index_realized_vol": .22, "vega_notional": 1e5}, error="E_INPUT", cls=E,
          tags=["invalid"], description="one strike per name")
    note("corr_e: nearest correlation by Higham-Dykstra and a dual BFGS solve, agreeing to 1e-6; eigenvalues in mpmath")
    write(s)


def e6():
    MUTANTS.clear()
    corr_e()
    note(f"stage E E6: {len(MUTANTS)} wrong-convention checks, each caught")


if __name__ == "__main__":
    e6()
