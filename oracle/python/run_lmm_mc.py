"""Stage G wave 3c acceptance: simulated LMM (terminal measure, log-Euler with predictor-corrector drift) against the
wave 3b closed forms. Caplets must agree within 3 standard errors (judged); swaptions against Rebonato are evidence only
(ruling G-25). Writes oracle/LMM_ACCEPTANCE.json.

    cd oracle/python && uv run python -W ignore run_lmm_mc.py
"""
import json
from pathlib import Path

import numpy as np

from gen_stage_g_lmm import ABCD, CURVE, cap_value, swn_value
from gen_stage_g_w1 import Curve

HERE = Path(__file__).resolve().parent
PATHS, SEED, STEPS_PER_YEAR = 100_000, 20261111, 20


def sig(v, T, t):
    x = T - t
    return (v["a"] + v["b"] * x) * np.exp(-v["c"] * x) + v["d"]


def simulate(grid, v, beta, horizon, rng):
    """Forwards F_k on [grid[k], grid[k+1]] under the measure of the last grid date. Returns F at `horizon`-indexed fixings
    and the realised discount numeraire ratios needed for pricing."""
    cv = Curve(**CURVE)
    P = np.array([float(cv.P(t)) for t in grid])
    tau = np.diff(grid)
    F0 = (P[:-1] / P[1:] - 1) / tau
    n = len(F0)
    fix = np.array(grid[:-1])
    rho = np.exp(-beta * np.abs(fix[:, None] - fix[None, :]))
    L = np.linalg.cholesky(rho + 1e-14 * np.eye(n))
    lnF = np.tile(np.log(F0), (PATHS, 1))
    snap = {}
    marks = np.array(grid)
    times = np.unique(np.concatenate([np.linspace(0, horizon, int(round(horizon * STEPS_PER_YEAR)) + 1), marks[marks <= horizon]]))
    for t0, t1 in zip(times[:-1], times[1:]):
        dt = t1 - t0
        s = np.where(fix >= t1 - 1e-12, sig(v, fix, 0.5 * (t0 + t1)), 0.0)
        z = rng.standard_normal((PATHS, n)) @ L.T

        def drift(lf):
            F = np.exp(lf)
            g = tau * s * F / (1 + tau * F)  # (paths, n)
            # terminal measure: mu_k = -s_k sum_{j>k} rho_kj g_j
            upper = np.triu(rho, 1)
            return -s * (g @ upper.T)

        mu0 = drift(lnF)
        pred = lnF + (mu0 - 0.5 * s * s) * dt + s * np.sqrt(dt) * z
        mu1 = drift(pred)
        lnF = lnF + (0.5 * (mu0 + mu1) - 0.5 * s * s) * dt + s * np.sqrt(dt) * z
        for m in np.where(np.abs(marks - t1) < 1e-12)[0]:
            snap[int(m)] = np.exp(lnF)
    return P, tau, snap, np.exp(lnF)


def numeraire_ratio(P, tau, F_from, k_pay):
    """P(T_pay)/P(T_N) along a path, from forwards at the payment-relevant time: prod_{j>=k_pay} (1 + tau_j F_j)."""
    return np.prod(1 + tau[k_pay:] * F_from[:, k_pay:], axis=1)


def main():
    rng = np.random.default_rng(SEED)
    out = {"paths": PATHS, "seed": SEED, "steps_per_year": STEPS_PER_YEAR, "generator": "numpy PCG64", "caplets": [], "swaptions": []}
    # caplets on the annual grid to 7y (forwards fix 1..6), K = 4.5%, terminal measure T_N = 7
    grid = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    g = [0.0] + grid  # include a first forward so indices align; forward 0 fixes at 0 (ignored)
    P, tau, Ffix, _ = simulate(g, ABCD, 0.1, 7.0, rng)
    K, PN = 0.045, P[-1]
    cf = cap_value(dict(curve=CURVE, abcd=ABCD, period_times=grid, strike=K, cap_floor="CAP", notional=1.0))
    for i, k in enumerate(range(1, len(grid))):
        # caplet on F_k fixing at g[k], paid g[k+1]; value = P_N E^N[ tau max(F-K,0) / P(T_pay,T_N)] with P(Tpay,TN) at fixing
        # P(T_pay)/P(T_N) at the fixing date = prod_{j>k} (1 + tau_j F_j(fix)); later forwards are evaluated at fixing time
        Fk = Ffix[k][:, k]
        later = np.prod(1 + tau[k + 1:] * Ffix[k + 1][:, k + 1:], axis=1) if k + 1 < len(tau) else 1.0
        pay = tau[k] * np.maximum(Fk - K, 0) * later
        mc, se = PN * pay.mean(), PN * pay.std(ddof=1) / np.sqrt(PATHS)
        ref = cf["caplet_prices"][i]
        out["caplets"].append({"fixing": g[k], "closed_form": ref, "mc": mc, "se": se, "z": (mc - ref) / se})
    out["caplets_pass"] = all(abs(c["z"]) < 3 for c in out["caplets"])
    # swaption 5y into 5y, payer K = 3.5%, terminal measure T_N = 10: evidence only (G-25)
    for beta in (0.0, 0.5):
        rng = np.random.default_rng(SEED + 1)
        g = [5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        P, tau, Ffix, FT = simulate(g, ABCD, beta, 5.0, rng)
        F = Ffix[0]  # state at expiry 5.0: every forward still alive
        disc_to_N = np.cumprod(1 / (1 + tau * F), axis=1)  # P(T0, T_{j+1}) along path
        P_T0_TN = disc_to_N[:, -1]
        ann = (tau * disc_to_N).sum(axis=1)
        S = (1 - P_T0_TN) / ann
        pay = ann * np.maximum(S - 0.035, 0) / P_T0_TN
        mc, se = P[-1] * pay.mean(), P[-1] * pay.std(ddof=1) / np.sqrt(PATHS)
        ref = swn_value(dict(curve=CURVE, abcd=ABCD, correlation_beta=beta, expiry_years=5.0, payment_times=g[1:], fixed_rate=0.035, side="PAY", notional=1.0))["price"]
        out["swaptions"].append({"beta": beta, "rebonato": ref, "mc": mc, "se": se, "rel_diff": (ref - mc) / mc})
    (HERE.parent / "LMM_ACCEPTANCE.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
