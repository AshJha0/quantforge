#!/usr/bin/env python3
"""Q6 as a method test on SYNTHETIC noisy quotes (R6-24, owner decision D4). Not real quotes: "real quotes" stays not done.

Runs the procedure fixed in research/preregs/Q6-01-churn-bound.md on quotes drawn from a known, arbitrage-free surface,
so the answer is known and the procedure itself is what is tested.

Truth: an SSVI surface (Gatheral and Jacquier 2014, "Arbitrage-free SVI volatility surfaces", Quantitative Finance
14(1)), total variance w(k, theta) = theta/2 * (1 + rho*phi*k + sqrt((phi*k + rho)^2 + 1 - rho^2)), phi = eta/theta^g
with g = 0.5. Free of calendar arbitrage when theta rises with T and of butterfly arbitrage when eta*(1+|rho|) <= 2
(their theorem 4.2 and corollary 4.1). Each day the at-the-money level does a random walk and rho drifts.

Quotes (in implied volatility; the prereg writes the fit error in price over the half-spread, and for synthetic quotes
the same ratio is taken in volatility, which equals it to first order through vega): 5 expiries x 15 strikes a day,
half-spread h = 0.002 + 0.01|k| (wider in the wings), mid = truth + N(0, (h/2)^2); 10% of quotes are stale (yesterday's
mid); 2% are outliers (mid shifted by +-5h).

Fit: SSVI with the same arbitrage-free parameterisation (theta increments >= 0 through squares, eta*(1+|rho|) < 2
through a logistic map), so the arbitrage repair is built into the model; the grid check of prereg rule 5 is still
run on every test day. Loss and penalty exactly as the prereg: sum((model-mid)/h)^2 + lambda*|G|*C_t^2/0.001^2.

  python research/q6/q6_method_test.py [--days 60] [--seed 20261112]
"""
import argparse
import json
import math

import numpy as np
from scipy.optimize import minimize

K_GRID = np.array([-0.20, -0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15, 0.20])
T_GRID = np.array([30, 60, 91, 182, 365]) / 365.0
LAMBDAS = (0, 0.1, 0.3, 1, 3, 10)
K_QUOTES = np.linspace(-0.3, 0.3, 15)
GAMMA = 0.5
LABEL = "Synthetic quotes from a known SSVI surface; a method test, not a calibration to real option quotes."


def ssvi_w(k, theta, rho, eta):
    phi = eta / theta ** GAMMA
    return theta / 2 * (1 + rho * phi * k + np.sqrt((phi * k + rho) ** 2 + 1 - rho ** 2))


def vols(theta_by_T, rho, eta, k, T):
    """Implied vols at (k, T) arrays: theta interpolated linearly in T (total ATM variance), as the prereg reads w."""
    th = np.interp(T, T_GRID, theta_by_T)
    return np.sqrt(ssvi_w(k, th, rho, eta) / T)


def truth_path(days, rng):
    lvl, rho, out = 0.20, -0.5, []
    for _ in range(days):
        lvl = max(0.08, lvl * math.exp(0.04 * rng.standard_normal()))
        rho = float(np.clip(rho + 0.02 * rng.standard_normal(), -0.8, -0.2))
        term = lvl * (1 + 0.15 * np.sqrt(T_GRID))  # upward ATM term structure
        out.append({"theta": term ** 2 * T_GRID, "rho": rho, "eta": 1.0})
    return out


def quotes(truth, rng, prev_mid=None):
    k, T = np.meshgrid(K_QUOTES, T_GRID)
    k, T = k.ravel(), T.ravel()
    h = 0.002 + 0.01 * np.abs(k)
    mid = vols(truth["theta"], truth["rho"], truth["eta"], k, T) + rng.normal(0, h / 2)
    if prev_mid is not None:
        stale = rng.random(k.size) < 0.10
        mid[stale] = prev_mid[stale]
    out = rng.random(k.size) < 0.02
    mid[out] += rng.choice([-5, 5], out.sum()) * h[out]
    return {"k": k, "T": T, "h": h, "mid": mid}


def unpack(x):
    theta = np.cumsum(x[:5] ** 2) + 1e-8
    rho = math.tanh(x[5])
    eta = 2 / (1 + abs(rho)) / (1 + math.exp(-x[6]))  # eta*(1+|rho|) in (0, 2)
    return theta, rho, eta


def grid_vols(p):
    k, T = np.meshgrid(K_GRID, T_GRID)
    return vols(p[0], p[1], p[2], k.ravel(), T.ravel())


def fit_day(q, lam, prev_grid, x0):
    def loss(x):
        p = unpack(x)
        r = (vols(p[0], p[1], p[2], q["k"], q["T"]) - q["mid"]) / q["h"]
        val = float(r @ r)
        if lam and prev_grid is not None:
            c2 = float(np.mean((grid_vols(p) - prev_grid) ** 2))
            val += lam * K_GRID.size * T_GRID.size * c2 / 0.001 ** 2
        return val
    res = minimize(loss, x0, method="L-BFGS-B")
    return res.x


def x_start(q):
    atm = np.array([np.interp(0.0, q["k"][q["T"] == T], q["mid"][q["T"] == T]) for T in T_GRID])
    th = atm ** 2 * T_GRID
    inc = np.diff(np.concatenate([[0.0], np.maximum.accumulate(th)]))
    return np.concatenate([np.sqrt(np.maximum(inc, 1e-8)), [math.atanh(-0.5), 0.0]])


def atm_vol(p):
    return vols(p[0], p[1], p[2], np.zeros(T_GRID.size), T_GRID)


def durrleman_min(p, T):
    """min over K_GRID of g(k) for the slice at T, by central differences of w (step 1e-4)."""
    th = float(np.interp(T, T_GRID, p[0]))
    e = 1e-4
    k = K_GRID
    w = ssvi_w(k, th, p[1], p[2])
    w1 = (ssvi_w(k + e, th, p[1], p[2]) - ssvi_w(k - e, th, p[1], p[2])) / (2 * e)
    w2 = (ssvi_w(k + e, th, p[1], p[2]) - 2 * w + ssvi_w(k - e, th, p[1], p[2])) / e ** 2
    g = (1 - k * w1 / (2 * w)) ** 2 - w1 ** 2 / 4 * (1 / w + 0.25) + w2 / 2
    return float(g.min())


def arbitrage_ok(p, tol=1e-10):
    k, T = np.meshgrid(K_GRID, T_GRID)
    w = (grid_vols(p) ** 2 * T.ravel()).reshape(T.shape)
    calendar = bool(np.all(np.diff(w, axis=0) >= -tol))
    butterfly = all(durrleman_min(p, T) >= -tol for T in T_GRID)
    return calendar, butterfly


def run_days(qs, lam):
    """Fit every day in order with penalty lam. Returns per-day params, churn ratios and inside-spread flags."""
    fits, ratios, inside = [], [], []
    prev, x = None, x_start(qs[0])
    for q in qs:
        x = fit_day(q, lam, None if prev is None else grid_vols(prev), x)
        p = unpack(x)
        model = vols(p[0], p[1], p[2], q["k"], q["T"])
        inside.extend(np.abs(model - q["mid"]) <= q["h"])
        if prev is not None:
            c = math.sqrt(float(np.mean((grid_vols(p) - grid_vols(prev)) ** 2)))
            a = math.sqrt(float(np.mean((atm_vol(p) - atm_vol(prev)) ** 2)))
            ratios.append(c / max(a, 0.001))
        fits.append(p)
        prev = p
    return fits, np.array(ratios), float(np.mean(inside))


def churn_ok(r):
    return bool(np.median(r) <= 1.5 and np.percentile(r, 95) <= 3.0)


def main(days=60, seed=20261112):
    rng = np.random.default_rng(seed)
    truth = truth_path(days, rng)
    qs, prev = [], None
    for t in truth:
        q = quotes(t, rng, prev)
        qs.append(q)
        prev = q["mid"]
    n_sel = max(2, int(round(0.2 * days)))
    sel, test = qs[:n_sel], qs[n_sel:]
    trials = []
    chosen = None
    for lam in LAMBDAS:  # every evaluated lambda is a logged trial (prereg rule 1)
        _, r, share = run_days(sel, lam)
        trials.append({"lambda": lam, "median_R": float(np.median(r)), "p95_R": float(np.percentile(r, 95)), "inside_share": share})
        if chosen is None and share >= 0.80 and churn_ok(r):
            chosen = lam
    out = {"label": LABEL, "seed": seed, "days": days, "selection_days": n_sel, "trials": trials, "chosen_lambda": chosen}
    if chosen is None:
        out["result"] = "FAIL: no lambda in the grid met the churn bound and fit quality on the selection sample"
        return out
    fits, r, share = run_days(test, chosen)
    arb = [arbitrage_ok(p) for p in fits]
    truth_err = float(np.sqrt(np.mean([(grid_vols(p) - grid_vols(unpack_truth(t))) ** 2 for p, t in zip(fits, truth[n_sel:])])))
    out.update({
        "test_median_R": float(np.median(r)), "test_p95_R": float(np.percentile(r, 95)), "churn_bound_met": churn_ok(r),
        "test_inside_share": share, "fit_quality_met": share >= 0.80,
        "calendar_free_days": sum(a[0] for a in arb), "butterfly_free_days": sum(a[1] for a in arb), "test_days": len(fits),
        "rms_error_to_truth_on_grid_vol": truth_err,
    })
    ok = out["churn_bound_met"] and out["fit_quality_met"] and all(a[0] and a[1] for a in arb)
    out["result"] = "PASS" if ok else "FAIL"
    return out


def unpack_truth(t):
    return t["theta"], t["rho"], t["eta"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--seed", type=int, default=20261112)
    a = ap.parse_args()
    print(json.dumps(main(a.days, a.seed), indent=1))
