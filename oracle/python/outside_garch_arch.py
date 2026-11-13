"""Outside check of garch_f and the FHS cases of risk_f4 with the `arch` package (K. Sheppard), rule 11.2.5.

Runs under WSL, because Windows Application Control blocks the pandas DLLs that `arch` imports on the Windows host:

    wsl -e bash -lc "cd /mnt/c/<repo>/oracle/python && uv run --no-project --python 3.12 --with arch==7.2.0 --with scipy python outside_garch_arch.py"

Writes oracle/outside_arch_f.json (computed outputs per case id); outside_f.py judges them against the goldens.
Convention rows (CONVENTION_MAP_F.md): `arch` starts the recursion with sigma2_1 = omega + (alpha + beta) * backcast;
the spec's sigma2_1 = v0, so backcast = (v0 - omega) / (alpha + beta). Variances come from arch's GARCH.compute_variance,
densities from arch Normal and StudentsT loglikelihood (unit-variance t, as the spec). Variance bounds are
set wide so that arch never clips. Fits maximise arch's objective with scipy (Nelder-Mead, then Newton on a
Richardson finite-difference Hessian of that objective); standard errors are sqrt(diag((-H)^{-1})) of the same objective.
"""
import json
import math
from pathlib import Path

import numpy as np
from arch.univariate import GARCH, EWMAVariance, Normal, StudentsT
from scipy import optimize

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "datasets" / "golden" / "stage_f"
VOL, NORM, STT = GARCH(1, 0, 1), Normal(), StudentsT()


def ll(e, omega, alpha, beta, v0, nu=None):
    s2 = np.empty_like(e)
    bc = (v0 - omega) / (alpha + beta)
    VOL.compute_variance(np.array([omega, alpha, beta]), e, s2, bc, np.array([[1e-300, 1e300]] * len(e)))
    d = NORM.loglikelihood(np.array([]), e, s2) if nu is None else STT.loglikelihood(np.array([nu]), e, s2)
    return float(d), s2


def h_loglik(i):
    r = np.array(i["returns"], float)
    e = r - i.get("mean", 0.0)
    v0 = float(np.mean(e * e)) if i["initial_variance"] == "SAMPLE" else i["initial_variance"]
    nu = i.get("degrees_of_freedom") if i.get("distribution", "NORMAL") == "STUDENT_T" else None
    L, s2 = ll(e, i["omega"], i["alpha"], i["beta"], v0, nu)
    nxt = i["omega"] + i["alpha"] * e[-1] ** 2 + i["beta"] * s2[-1]
    return {"loglik": L, "variances": list(map(float, s2)), "next_variance": float(nxt)}


def hessian(f, x, rel=1e-4):
    """Richardson-combined central second differences at steps h and h/2."""
    return (4 * hessian1(f, x, rel / 2) - hessian1(f, x, rel)) / 3


def hessian1(f, x, rel):
    n = len(x)
    h = np.array([rel * max(abs(v), 1e-12) for v in x])
    H = np.empty((n, n))
    for a in range(n):
        for b in range(a, n):
            def g(da, db):
                y = np.array(x, float)
                y[a] += da
                y[b] += db
                return f(y)
            H[a, b] = H[b, a] = (g(h[a], h[b]) - g(h[a], -h[b]) - g(-h[a], h[b]) + g(-h[a], -h[b])) / (4 * h[a] * h[b])
    return H


def grad(f, x, rel=1e-6):
    out = np.empty(len(x))
    for a in range(len(x)):
        h = rel * max(abs(x[a]), 1e-12)
        y1, y2 = np.array(x, float), np.array(x, float)
        y1[a] += h
        y2[a] -= h
        out[a] = (f(y1) - f(y2)) / (2 * h)
    return out


def h_estimate(i):
    r = np.array(i["returns"], float)
    mu = float(np.mean(r)) if i["demean"] else 0.0
    e = r - mu
    v0 = float(np.mean(e * e)) if i["initial_variance"] == "SAMPLE" else i["initial_variance"]
    t = i["distribution"] == "STUDENT_T"
    sv = float(np.mean(e * e))

    def f(p):
        om, al, be = p[0] * sv, p[1], p[2]
        if om <= 0 or al < 0 or be < 0 or al + be >= 1 or (t and not 2 < p[3] <= 500):
            return -1e300
        return ll(e, om, al, be, v0, p[3] if t else None)[0]
    best = None
    for s in ([0.05, 0.05, 0.9], [0.1, 0.1, 0.8], [0.02, 0.08, 0.9]):
        for nu0 in ([6.0, 10.0] if t else [None]):
            p0 = s + ([nu0] if t else [])
            res = optimize.minimize(lambda p: -f(p), p0, method="Nelder-Mead", options={"xatol": 1e-12, "fatol": 1e-12, "maxiter": 40000, "maxfev": 40000})
            if best is None or res.fun < best.fun:
                best = res
    x = np.array(best.x)
    for _ in range(30):  # Newton on arch's objective
        g, H = grad(f, x), hessian(f, x)
        step = np.linalg.solve(H, g)
        x = x - step
        if np.max(np.abs(step) / np.abs(x)) < 1e-12:
            break
    scale = np.array([sv, 1, 1] + ([1] if t else []))
    th = x * scale
    # Hessian in the scaled coordinates (omega / sample variance), where rounding noise is small, then back to theta
    Hx = hessian(f, x, rel=1e-3)
    H = Hx / np.outer(scale, scale)
    se = np.sqrt(np.diag(np.linalg.inv(-H)))
    keys = ["omega", "alpha", "beta"] + (["degrees_of_freedom"] if t else [])
    out = {k: float(v) for k, v in zip(keys, th)}
    out.setdefault("degrees_of_freedom", None)
    ses = {k: float(v) for k, v in zip(keys, se)}
    ses.setdefault("degrees_of_freedom", None)
    out.update(mean=mu, loglik=f(x), std_errors=ses, persistence=float(th[1] + th[2]))
    return out


def h_fhs(i):
    """EWMA through arch's EWMAVariance.compute_variance: sigma2_t = lam sigma2_{t-1} + (1 - lam) r_{t-1}^2 with
    backcast = sigma2_1 (the spec's mean square); then the spec's rescaling and order statistic."""
    r = np.array(i["returns"], float)
    lam = i["lambda"]
    ew = EWMAVariance(lam)
    s2 = np.empty_like(r)
    bc = float(np.mean(r * r))
    ew.compute_variance(np.array([]), r, s2, bc, np.array([[1e-300, 1e300]] * len(r)))
    nxt = lam * s2[-1] + (1 - lam) * r[-1] ** 2
    pnl = i["position_value"] * r * math.sqrt(nxt) / np.sqrt(s2)
    L = np.sort(-pnl)
    n = len(L)
    k = math.ceil(n * i["confidence"])
    # ES (R6-3.1, amends F-31): Acerbi-Tasche with a fractional tail weight, written from the paper's form with n alpha
    X = np.sort(pnl)
    na = n * (1.0 - i["confidence"])
    m = int(np.floor(na + 1e-9))
    frac = max(na - m, 0.0)
    es = -(np.sum(X[:m]) + (frac * X[m] if m < n and frac > 1e-9 else 0.0)) / na
    return {"var": float(L[k - 1]), "es": float(es), "tail_count": int(np.ceil(na - 1e-9)), "sigma_next": math.sqrt(nxt)}


def main():
    out = {}
    for suite, ops in (("garch_f", {"vol.garch.loglik": h_loglik, "vol.garch.estimate": h_estimate}),
                       ("risk_f4", {"risk.var.filtered_historical": h_fhs})):
        for c in json.loads((GOLD / f"{suite}.json").read_text(encoding="utf-8"))["cases"]:
            h = ops.get(c["operation"])
            if h and c["expected"]["status"] == "ok":
                out[c["case_id"]] = h(c["inputs"])
                print(c["case_id"], "done", flush=True)
    import arch
    (ROOT / "oracle" / "outside_arch_f.json").write_text(json.dumps({"library": "arch", "version": arch.__version__, "cases": out}, indent=1) + "\n",
                                                        encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
