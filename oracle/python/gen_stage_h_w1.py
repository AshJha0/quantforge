"""Stage H wave 1: execution schedules, Almgren-Chriss, impact, TCA shortfall, Avellaneda-Stoikov quotes, use case 5.

Specs: specifications/10-execution/{schedules,almgren-chriss,impact,tca}.md,
specifications/09-microstructure/avellaneda-stoikov.md, specifications/04-pricing/use-cases.md (use case 5).
Rulings: specifications/stage-h-rulings-w1.md HR-1 to HR-10 (confirmed 2026-11-18).

Every case of the five spec golden tables is written here in table order, so case ids match the tables
(sched_h-0001 is the table's sched_h-0001). Rows the tables did not have before this lane (an `exec.ac.frontier`
case, a few error cases, the TCA benchmark case and use case 5) come after them and are marked in the spec tables as
added by the oracle lane: hand calculation and this generator only, not blind re-derived.

Oracle: mpmath at 50 digits on the binary64 inputs (`mp.mpf(float)` is exact); integer schedules by exact rational
arithmetic (fractions) on the binary64 inputs, so a floor or a largest-remainder tie is decided exactly. The
generator asserts each table's printed figures (to the digits printed) before writing, so a spec/oracle mismatch
stops the run.

Evidence, recorded honestly in `verified_by`: the table cases were re-derived blind by a second lane on 2026-11-15
(DR-H2; institutional-quant-engine-plan/STAGE_H_BLIND_REDERIVATION.md, 27/27 MATCH; the lane's plan for wave 2 is
program/STAGE_H_BLIND_LANE.md). Caveat from that record: ac_h-0001's standard deviation was visible to the blind
lane, so that figure is not blind. ac_h-0005 and as_h-0005..0007 are also checked against figures printed in the
papers, as `extra_checks` at the spec's tolerance (0.05 on kappa; 0.005 on the spread); the golden value itself is
the closed form at the case tolerance.

    wsl: cd oracle/python && ~/qf-oracle-venv/bin/python -W ignore gen_stage_h_w1.py
"""
import json
import math
from fractions import Fraction as Fr

import mpmath as mp

from qf_oracle import common
from qf_oracle.common import Suite, note

G = "oracle/python/gen_stage_h_w1.py"
FOLDER = "stage_h"
SCHED = "specifications/10-execution/schedules.md"
AC = "specifications/10-execution/almgren-chriss.md"
IMP = "specifications/10-execution/impact.md"
TCA = "specifications/10-execution/tca.md"
AS = "specifications/09-microstructure/avellaneda-stoikov.md"
UC = "specifications/04-pricing/use-cases.md"
MODEL = "assumed parameters; not calibrated to any venue"  # HR-10

BLIND = "blind re-derivation DR-H2 2026-11-15 (STAGE_H_BLIND_REDERIVATION.md): MATCH"
BLIND_AC1 = ("blind re-derivation DR-H2 2026-11-15 (STAGE_H_BLIND_REDERIVATION.md): MATCH; "
             "the standard deviation 1.0407e6 was visible to the blind lane beforehand, so V is not blind")
ADDED = "added by the oracle lane 2026-11-18: hand calculation and mpmath only, not blind re-derived"
ORACLE = "mpmath 50 digits"
EXACT = "fractions (exact rational on binary64 inputs)"
BLIND_UC5 = "blind re-derivation DR-H2 2026-11-18 (program/STAGE_H_BLIND_UC5.md): MATCH"
UC5_BLIND = {0, 2}  # uc5_h-0001 and -0003; uc5_h-0002's variance leaked through the packet, so it stays not blind


class DomainError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def check(cond, code):
    if not cond:
        raise DomainError(code)


# ---------------------------------------------------------------- schedules (HR-3, HR-4)

def largest_remainder(total, weights):
    """Integers summing to `total`, proportional to `weights` (Fractions); ties to the earliest (HR-3)."""
    s = sum(weights)
    raw = [Fr(total) * w / s for w in weights]
    out = [math.floor(r) for r in raw]
    left = total - sum(out)
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - out[i]), i))
    for i in order[:left]:
        out[i] += 1
    return out


def is_integer(x):
    return float(x).is_integer()


def twap(inp):
    x, n, mode = inp["quantity"], inp["n_buckets"], inp.get("mode", "CONTINUOUS")  # HR-56
    check(x > 0, "E_INPUT")
    check(1 <= n <= 100_000, "E_INPUT")
    if mode == "UNITS":
        check(is_integer(x), "E_INPUT")
        x = int(x)
        q, r = divmod(x, n)
        return {"slices": [q + (1 if i < r else 0) for i in range(n)]}
    return {"slices": [common.f(mp.mpf(x) / n)] * n}


def vwap(inp):
    x, prof, mode = inp["quantity"], inp["profile"], inp.get("mode", "CONTINUOUS")
    check(x > 0, "E_INPUT")
    check(all(w >= 0 for w in prof), "E_DOMAIN")
    check(sum(prof) > 0, "E_DOMAIN")
    if mode == "UNITS":
        check(is_integer(x), "E_INPUT")
        return {"slices": largest_remainder(int(x), [Fr(w) for w in prof])}
    s = mp.fsum(mp.mpf(w) for w in prof)
    return {"slices": [common.f(mp.mpf(x) * mp.mpf(w) / s) for w in prof]}


def pov(inp):
    x, p, vol, mode = inp["quantity"], inp["participation"], inp["market_volume"], inp.get("mode", "CONTINUOUS")
    check(0 < p < 1, "E_DOMAIN")
    check(x > 0, "E_INPUT")
    check(len(vol) > 0, "E_INPUT")
    check(all(v >= 0 for v in vol), "E_DOMAIN")
    if mode == "UNITS":
        check(is_integer(x), "E_INPUT")
    rem, out = Fr(x), []
    for v in vol:
        child = min(rem, Fr(p) * Fr(v) / (1 - Fr(p)))
        if mode == "UNITS":
            child = Fr(math.floor(child))
        out.append(child)
        rem -= child
    filled = sum(out)
    if mode == "UNITS":
        return {"slices": [int(c) for c in out], "filled": int(filled), "residual": int(rem)}
    return {"slices": [float(c) for c in out], "filled": float(filled), "residual": float(rem)}  # running remaining (HR-56)


# ---------------------------------------------------------------- Almgren-Chriss (HR-5, HR-6)

def ac_core(inp, lam):
    X, T, N = mp.mpf(inp["quantity"]), mp.mpf(inp["horizon"]), inp["n_steps"]
    sigma, eps, eta, gamma = (mp.mpf(inp[k]) for k in ("sigma", "epsilon", "eta", "gamma"))
    check(N >= 1, "E_INPUT")
    check(X > 0, "E_INPUT")  # HR-56
    check(T > 0 and sigma >= 0 and lam >= 0 and eps >= 0 and gamma >= 0, "E_DOMAIN")  # HR-56
    tau = T / N
    eta_t = eta - gamma * tau / 2
    check(eta_t > 0, "E_DOMAIN")
    y = mp.mpf(lam) * sigma ** 2 * tau ** 2 / (2 * eta_t)
    if y == 0:  # lambda = 0 (or sigma = 0): the linear trajectory exactly (HR-5)
        kappa = mp.mpf(0)
        x = [X * (N - j) / N for j in range(N + 1)]
    else:
        kappa = mp.log1p(y + mp.sqrt(y * (y + 2))) / tau  # HR-6
        x = [X * mp.sinh(kappa * (T - j * tau)) / mp.sinh(kappa * T) for j in range(N + 1)]
    n = [x[k - 1] - x[k] for k in range(1, N + 1)]
    E = gamma * X ** 2 / 2 + eps * mp.fsum(abs(v) for v in n) + eta_t / tau * mp.fsum(v ** 2 for v in n)
    V = sigma ** 2 * tau * mp.fsum(v ** 2 for v in x[1:])
    return x, n, kappa, E, V


def ac_trajectory(inp):
    lam = mp.mpf(inp["risk_aversion"])
    x, n, kappa, E, V = ac_core(inp, lam)
    return {"holdings": [common.f(v) for v in x], "trades": [common.f(v) for v in n], "kappa": common.f(kappa),
            "expected_cost": common.f(E), "variance": common.f(V), "objective": common.f(E + lam * V)}


def ac_frontier(inp):
    base = {k: v for k, v in inp.items() if k != "risk_aversions"}
    out = {"risk_aversions": [], "expected_costs": [], "variances": []}
    for lam in inp["risk_aversions"]:
        _, _, _, E, V = ac_core(base, mp.mpf(lam))
        out["risk_aversions"].append(lam)
        out["expected_costs"].append(common.f(E))
        out["variances"].append(common.f(V))
    return out


# ---------------------------------------------------------------- impact

def imp_sqrt(inp):
    q, v, s, y = (mp.mpf(inp[k]) for k in ("quantity", "daily_volume", "daily_vol", "coefficient"))
    check(q >= 0 and v > 0 and s >= 0 and y >= 0, "E_DOMAIN")  # HR-56: a zero order has zero impact
    return {"impact": common.f(y * s * mp.sqrt(q / v)), "model": MODEL}


def imp_ow(inp):
    x, t, rho = (mp.mpf(inp[k]) for k in ("quantity", "horizon", "resilience"))
    check(x > 0, "E_INPUT")  # HR-56
    check(rho > 0 and t > 0, "E_DOMAIN")
    b = x / (rho * t + 2)
    return {"initial_block": common.f(b), "rate": common.f(rho * b), "final_block": common.f(b)}


# ---------------------------------------------------------------- TCA (HR-8)

def tca(inp):
    s = 1 if inp["side"] == "BUY" else -1
    pd, p0, pc, X = (mp.mpf(inp[k]) for k in ("decision_price", "arrival_price", "end_price", "order_quantity"))
    fills = [(mp.mpf(f_["quantity"]), mp.mpf(f_["price"])) for f_ in inp["fills"]]
    Q = mp.fsum(q for q, _ in fills)
    check(X > 0 and all(q > 0 for q, _ in fills), "E_INPUT")  # HR-56
    check(Q <= X, "E_INPUT")
    check(min([pd, p0, pc] + [p for _, p in fills]) > 0, "E_DOMAIN")
    delay = s * Q * (p0 - pd)
    execution = s * mp.fsum(q * (p - p0) for q, p in fills)
    opp = s * (X - Q) * (pc - pd)
    fees = mp.mpf(inp["fees"])
    total = delay + execution + opp + fees
    out = {"delay": common.f(delay), "execution": common.f(execution), "opportunity": common.f(opp),
           "total": common.f(total), "total_bps": common.f(total / (X * pd) * 10_000)}
    if "benchmark_vwap" in inp:
        avg = mp.fsum(q * p for q, p in fills) / Q
        out["vwap_slippage"] = common.f(s * Q * (avg - mp.mpf(inp["benchmark_vwap"])))
    return out


# ---------------------------------------------------------------- Avellaneda-Stoikov (HR-7)

def as_quotes(inp):
    s, q, g, sig, tl, k = (mp.mpf(inp[x]) for x in ("mid", "inventory", "risk_aversion", "sigma", "time_left", "k"))
    check(g > 0 and k > 0 and sig >= 0 and tl >= 0, "E_DOMAIN")
    r = s - q * g * sig ** 2 * tl
    spread = g * sig ** 2 * tl + 2 / g * mp.log1p(g / k)
    return {"reservation": common.f(r), "spread": common.f(spread), "bid": common.f(r - spread / 2),
            "ask": common.f(r + spread / 2)}


# ---------------------------------------------------------------- use case 5

def uc5(inp):
    """`usecase.execution_tca`: AC trajectory, integer child orders, then the Perold shortfall of the fills."""
    X = inp["quantity"]
    check(is_integer(X) and X >= 1, "E_INPUT")
    N, m = inp["n_steps"], inp["completed_steps"]
    check(N >= 1, "E_INPUT")
    check(len(inp["fill_prices"]) == N, "E_INPUT")
    check(0 <= m <= N, "E_INPUT")
    check(inp["fee_per_unit"] >= 0, "E_DOMAIN")
    _, n, kappa, E, V = ac_core(inp, mp.mpf(inp["risk_aversion"]))
    # Largest remainder on the trades: exact X/N when linear (kappa = 0), else the 50-digit trades; the generator
    # asserts distinct remainders are more than 1e-6 apart, so no build's rounding can flip the order.
    if kappa == 0:
        raw = [Fr(int(X), N)] * N
    else:
        raw = [Fr(mp.nstr(v, 45, strip_zeros=False)) for v in n]
    fr = sorted(set(r - math.floor(r) for r in raw))
    assert all(b - a > Fr(1, 10 ** 6) for a, b in zip(fr, fr[1:])), "near tie in use case 5 lots"
    lots = largest_remainder(int(X), raw)
    fills = [{"quantity": float(lots[i]), "price": inp["fill_prices"][i]} for i in range(m)]
    filled = sum(lots[:m])
    fees = mp.mpf(inp["fee_per_unit"]) * filled
    t = tca({"side": inp["side"], "decision_price": inp["decision_price"], "arrival_price": inp["arrival_price"],
             "end_price": inp["end_price"], "order_quantity": float(X), "fills": fills, "fees": float(fees)})
    return {"lots": lots, "expected_cost": common.f(E), "variance": common.f(V), "filled": filled,
            "fees": common.f(fees), **t}


def run(fn, inp):
    try:
        return fn(inp), None
    except DomainError as e:
        return None, e.code


# ---------------------------------------------------------------- cases

def close(a, b, digits):
    return abs(a - b) <= 0.5 * 10 ** (-digits) * max(1.0, abs(b))


P = {"quantity": 1e6, "horizon": 5.0, "n_steps": 5, "sigma": 0.95, "epsilon": 0.0625, "eta": 2.5e-6, "gamma": 2.5e-7}

SCHED_CASES = [
    ("exec.schedule.twap", {"quantity": 1000, "n_buckets": 3, "mode": "UNITS"}, {"slices": [334, 333, 333]},
     "floor 333, remainder 1 to slice 0 (HR-3)", True),
    ("exec.schedule.twap", {"quantity": 1000.0, "n_buckets": 4, "mode": "CONTINUOUS"}, {"slices": [250.0] * 4},
     "X/N", True),
    ("exec.schedule.vwap", {"quantity": 1000.0, "profile": [1.0, 2.0, 3.0, 4.0], "mode": "CONTINUOUS"},
     {"slices": [100.0, 200.0, 300.0, 400.0]}, "weights over 10", True),
    ("exec.schedule.vwap", {"quantity": 10, "profile": [1.0, 1.0, 1.0], "mode": "UNITS"}, {"slices": [4, 3, 3]},
     "3.333 each, equal remainders, earliest wins (HR-3)", True),
    ("exec.schedule.pov", {"quantity": 1000, "participation": 0.2, "market_volume": [1000.0, 2000.0, 4000.0],
                           "mode": "UNITS"}, {"slices": [250, 500, 250], "filled": 1000, "residual": 0},
     "p/(1-p) = 0.25; third capped at the remaining 250 (HR-4)", True),
    ("exec.schedule.pov", {"quantity": 1000.0, "participation": 0.1, "market_volume": [900.0, 900.0],
                           "mode": "CONTINUOUS"}, {"slices": [100.0, 100.0], "filled": 200.0, "residual": 800.0},
     "0.1/0.9 x 900; residual 800 is not an error", True),
    ("exec.schedule.pov", {"quantity": 1000, "participation": 1.0, "market_volume": [1000.0], "mode": "UNITS"},
     "E_DOMAIN", "p = 1 is outside (0, 1) (HR-4)", True),
    ("exec.schedule.vwap", {"quantity": 1000, "profile": [0.0, 0.0], "mode": "UNITS"}, "E_DOMAIN",
     "all-zero profile", True),
    ("exec.schedule.twap", {"quantity": 1000.5, "n_buckets": 2, "mode": "UNITS"}, "E_INPUT",
     "non-integer X in UNITS mode", False),
    ("exec.schedule.twap", {"quantity": 1000.0, "n_buckets": 4}, {"slices": [250.0] * 4},
     "mode absent: CONTINUOUS (HR-56)", False),
    ("exec.schedule.pov", {"quantity": 0.0, "participation": 0.1, "market_volume": [900.0]}, "E_INPUT",
     "quantity 0 (HR-56)", False),
    ("exec.schedule.pov", {"quantity": 1000.0, "participation": 0.1, "market_volume": [], "mode": "CONTINUOUS"},
     "E_INPUT", "empty market_volume (HR-56)", False),
    ("exec.schedule.pov", {"quantity": 1.0, "participation": 0.5, "market_volume": [0.75, 0.75, 0.75], "mode": "CONTINUOUS"},
     {"slices": [0.75, 0.25, 0.0], "filled": 1.0, "residual": 0.0},
     "residual is the running remaining after each child, never negative (HR-56)", False),
]

AC_CASES = [
    ("exec.ac.trajectory", dict(P, risk_aversion=0.0), "lambda = 0: linear trajectory exactly (HR-5); "
     "E = 125,000 + 62,500 + 475,000; V = 0.9025e12 x 1.2 ([AC00] eqs. (10), (11))", BLIND_AC1),
    ("exec.ac.trajectory", dict(P, risk_aversion=1e-6), "cosh(kappa) = 1.19; sinh-ratio holdings ([AC00] eq. (17))",
     BLIND),
    ("exec.ac.trajectory", dict(P, gamma=5e-6, risk_aversion=1e-6), "gamma = 2 eta / tau: eta_tilde = 0", BLIND),
    ("exec.ac.trajectory", dict(P, n_steps=1, risk_aversion=1e-6),
     "N = 1, tau = 5, eta_tilde = 1.875e-6: E = 125,000 + 62,500 + 375,000", BLIND),
    ("exec.ac.trajectory", dict(P, risk_aversion=1e-6),
     "P, lambda = 1e-6: kappa against the printed 'about 0.6/day' ([AC00] p. 24), extra check 0.05", BLIND),
    ("exec.ac.frontier", dict({k: v for k, v in P.items()}, risk_aversions=[0.0, 5e-7, 1e-6, 2e-6]),
     "frontier: E non-decreasing, V non-increasing in lambda; points 0 and 1e-6 equal ac_h-0001, ac_h-0002", ADDED),
    ("exec.ac.trajectory", dict(P, n_steps=0, risk_aversion=1e-6), "N < 1", ADDED),
    ("exec.ac.trajectory", dict(P, quantity=0.0, risk_aversion=1e-6), "quantity 0 is E_INPUT (HR-56)", ADDED),
    ("exec.ac.trajectory", dict(P, epsilon=-0.0625, risk_aversion=1e-6), "negative epsilon (HR-56)", ADDED),
    ("exec.ac.trajectory", dict(P, gamma=-2.5e-7, risk_aversion=1e-6), "negative gamma (HR-56)", ADDED),
]

IMP_CASES = [
    ("exec.impact.sqrt", {"quantity": 1e5, "daily_volume": 1e7, "daily_vol": 0.02, "coefficient": 1.0},
     "0.02 x sqrt(0.01)", BLIND),
    ("exec.impact.sqrt", {"quantity": 4e5, "daily_volume": 1e7, "daily_vol": 0.02, "coefficient": 1.0},
     "four times Q, twice the impact", BLIND),
    ("exec.impact.ow_optimal", {"quantity": 1000.0, "horizon": 1.0, "resilience": 8.0},
     "1000/10; 8 x 1000/10 ([OW13] eq. (31))", BLIND),
    ("exec.impact.ow_optimal", {"quantity": 100000.0, "horizon": 1.0, "resilience": 2.231},
     "[OW13] eq. (31) with the Fig. 2 parameters: 1e5 / 4.231; 2.231e5 / 4.231", BLIND),
    ("exec.impact.sqrt", {"quantity": 1e5, "daily_volume": 0.0, "daily_vol": 0.02, "coefficient": 1.0},
     "V <= 0", ADDED),
    ("exec.impact.ow_optimal", {"quantity": 1000.0, "horizon": 1.0, "resilience": 0.0}, "rho <= 0", ADDED),
    ("exec.impact.sqrt", {"quantity": 1e5, "daily_volume": 1e7, "daily_vol": -0.02, "coefficient": 1.0},
     "negative daily_vol (HR-56)", ADDED),
    ("exec.impact.sqrt", {"quantity": 1e5, "daily_volume": 1e7, "daily_vol": 0.02, "coefficient": -1.0},
     "negative coefficient (HR-56)", ADDED),
    ("exec.impact.ow_optimal", {"quantity": 0.0, "horizon": 1.0, "resilience": 8.0}, "quantity 0 is E_INPUT (HR-56)",
     ADDED),
]

FILLS = [{"quantity": 600.0, "price": 100.2}, {"quantity": 200.0, "price": 100.3}]
TCA_BASE = {"side": "BUY", "decision_price": 100.0, "arrival_price": 100.1, "end_price": 101.0,
            "order_quantity": 1000.0, "fills": FILLS, "fees": 5.0}
TCA_CASES = [
    (TCA_BASE, "800 x 0.10; 600 x 0.10 + 200 x 0.20; 200 x 1; + 5 fees; 385 / 1e5 x 1e4 = 38.5 bp", BLIND),
    (dict(TCA_BASE, side="SELL", fees=0.0), "a seller gains when prices rise", BLIND),
    (dict(TCA_BASE, fills=[{"quantity": 600.0, "price": 100.2}, {"quantity": 600.0, "price": 100.3}]),
     "fills sum to 1,200 against X = 1,000: overfill", BLIND),
    (dict(TCA_BASE, benchmark_vwap=100.15), "average fill 100.225; slippage 800 x 0.075 = 60", ADDED),
    (dict(TCA_BASE, arrival_price=0.0), "a price <= 0", ADDED),
    (dict(TCA_BASE, order_quantity=0.0, fills=[]), "order_quantity 0 is E_INPUT (HR-56)", ADDED),
]

AS_BASE = {"mid": 100.0, "inventory": 2.0, "risk_aversion": 0.1, "sigma": 2.0, "time_left": 1.0, "k": 1.5}
AS_HALF = {"mid": 100.0, "inventory": 0.0, "risk_aversion": 0.1, "sigma": 2.0, "time_left": 0.5, "k": 1.5}
AS_CASES = [
    (AS_BASE, "100 - 2 x 0.1 x 4; 0.4 + 20 ln(16/15) ([AS08] eqs. (29), (30))", None),
    (dict(AS_BASE, inventory=0.0), "symmetric about the mid", None),
    (dict(AS_BASE, time_left=0.0), "terminal: only (2/gamma) ln(1 + gamma/k)", None),
    (dict(AS_BASE, risk_aversion=0.0), "gamma = 0", None),
    (AS_HALF, "[AS08] Table 1, p. 222, prints 1.49; 0.2 + 20 ln(16/15)", 1.49),
    (dict(AS_HALF, risk_aversion=0.01), "[AS08] Table 2, p. 222, prints 1.35", 1.35),
    (dict(AS_HALF, risk_aversion=1.0), "[AS08] Table 3, p. 223, prints 3.02", 3.02),
]

UC_BASE = dict(P, risk_aversion=1e-6, side="SELL", decision_price=50.0, arrival_price=50.0, end_price=49.5,
               fill_prices=[49.9, 49.8, 49.7, 49.6, 49.5], completed_steps=5, fee_per_unit=0.001)
UC_CASES = [
    (UC_BASE, "sell 1e6 on parameter set P, lambda = 1e-6, all five child orders filled; opportunity 0"),
    (dict(UC_BASE, risk_aversion=0.0, completed_steps=3),
     "lambda = 0: 200,000 per step; three of five filled, 400,000 left at the end price (opportunity)"),
    ({"quantity": 1000, "horizon": 1.0, "n_steps": 3, "sigma": 0.5, "epsilon": 0.01, "eta": 1e-3, "gamma": 1e-4,
      "risk_aversion": 0.0, "side": "BUY", "decision_price": 20.0, "arrival_price": 20.02, "end_price": 20.1,
      "fill_prices": [20.03, 20.05, 20.08], "completed_steps": 3, "fee_per_unit": 0.0},
     "buy 1,000 in three linear steps: lots [334, 333, 333] by largest remainder, ties to the earliest (HR-3)"),
    (dict(UC_BASE, fill_prices=[49.9, 49.8]), "fill_prices shorter than n_steps"),
    (dict(UC_BASE, quantity=1000000.5), "non-integer quantity"),
    (dict(UC_BASE, completed_steps=6), "completed_steps > n_steps"),
    (dict(UC_BASE, fee_per_unit=-0.001), "negative fee"),
    (dict(UC_BASE, gamma=5e-6), "eta_tilde = 0, from exec.ac.trajectory"),
]


def assert_tables(out):
    """The spec tables' printed figures, to the digits printed."""
    sc, ac, im, tc, ak = (out[k] for k in ("sched_h", "ac_h", "imp_h", "tca_h", "as_h"))
    a2 = ac[1][0]
    assert close(a2["kappa"], 0.6070761632, 10)
    for got, want in zip(a2["holdings"], [1e6, 541955.5544, 289854.2194, 147897.4878, 62141.8016, 0.0]):
        assert close(got, want, 4) if want else got == 0.0, (got, want)
    assert abs(a2["expected_cost"] - 911226.986) < 5e-4 and abs(a2["variance"] / 3.641285721e11 - 1) < 5e-10
    assert abs(a2["objective"] - 1275355.558) < 5e-4
    a1 = ac[0][0]
    assert a1["holdings"] == [1e6, 8e5, 6e5, 4e5, 2e5, 0.0] and close(a1["expected_cost"], 662500.0, 6)
    assert abs(a1["variance"] / 1.083e12 - 1) < 1e-14
    assert ac[2] == (None, "E_DOMAIN") and ac[3][0]["holdings"] == [1e6, 0.0]
    assert close(ac[3][0]["expected_cost"], 562500.0, 6)
    assert abs(ac[4][0]["kappa"] * 5 - 3.0353808) < 5e-8 and abs(ac[4][0]["kappa"] - 0.6) <= 0.05
    fr = ac[5][0]
    assert fr["expected_costs"] == sorted(fr["expected_costs"]) and fr["variances"] == sorted(fr["variances"])[::-1]
    assert fr["expected_costs"][0] == a1["expected_cost"] and fr["variances"][2] == a2["variance"]
    assert im[0][0]["impact"] == 0.002 and im[1][0]["impact"] == 0.004
    assert im[2][0] == {"initial_block": 100.0, "rate": 800.0, "final_block": 100.0}
    assert close(im[3][0]["initial_block"], 23635.0744504845, 10) and close(im[3][0]["rate"], 52729.8510990310, 10)
    want = [(80, 100, 200, 385, 38.5), (-80, -100, -200, -380, None)]
    for (r, _), w in zip(tc[:2], want):
        got = (r["delay"], r["execution"], r["opportunity"], r["total"], r["total_bps"])
        assert all(abs(g - x) < 1e-9 for g, x in zip(got, w) if x is not None), got
    assert tc[2] == (None, "E_INPUT") and abs(tc[3][0]["vwap_slippage"] - 60) < 1e-9
    r1, r2, r3 = ak[0][0], ak[1][0], ak[2][0]
    assert close(r1["reservation"], 99.2, 12) and close(r1["spread"], 1.6907704228, 10)
    assert close(r1["bid"], 98.3546147886, 10) and close(r1["ask"], 100.0453852114, 10)
    assert close(r2["bid"], 99.1546147886, 10) and close(r2["ask"], 100.8453852114, 10)
    assert r3["reservation"] == 100.0 and close(r3["spread"], 1.2907704228, 10) and ak[3] == (None, "E_DOMAIN")
    for (r, _), w in zip(ak[4:], (1.4907704228, 1.3489085437, 3.0216512475)):
        assert close(r["spread"], w, 10)
    assert sc[0][0]["slices"] == [334, 333, 333] and sc[3][0]["slices"] == [4, 3, 3]
    assert sc[4][0] == {"slices": [250, 500, 250], "filled": 1000, "residual": 0}
    assert sc[5][0]["residual"] == 800.0 and sc[6] == (None, "E_DOMAIN") and sc[7] == (None, "E_DOMAIN")


def build():
    out = {}
    s = Suite("sched_h", SCHED, G)
    res = []
    for op, inp, want, desc, in_table in SCHED_CASES:
        fn = {"exec.schedule.twap": twap, "exec.schedule.vwap": vwap, "exec.schedule.pov": pov}[op]
        r, err = run(fn, inp)
        res.append((r, err))
        if isinstance(want, str):
            assert err == want, (inp, err)
        else:
            assert r == want, (r, want)
        ver = ("hand", BLIND) if in_table else ("hand", ADDED)
        tags = ("stage_h", "execution", "schedule", "synthetic") + (("error",) if err else ())
        units = inp.get("mode") == "UNITS"
        if err:
            s.add(op, inp, error=err, verified=ver, tags=tags, description=desc)
        else:
            s.add(op, inp, outputs=r, cls="date_and_convention" if units else "simple_analytic", verified=ver,
                  tags=tags, description=desc)
    out["sched_h"] = res

    a = Suite("ac_h", AC, G)
    res = []
    for i, (op, inp, desc, ver) in enumerate(AC_CASES):
        r, err = run(ac_frontier if op == "exec.ac.frontier" else ac_trajectory, inp)
        res.append((r, err))
        tags = ("stage_h", "execution", "almgren_chriss", "synthetic") + (("error",) if err else ())
        if err:
            a.add(op, inp, error=err, verified=("hand", ver), tags=tags, description=desc)
            continue
        extra = None
        verified = (ORACLE, ver)
        if i == 4:  # ac_h-0005
            extra = [{"method": "absolute", "output": "kappa", "expected": 0.6, "limit": 0.05}]
            verified = (ORACLE, ver, "[AC00] p. 24 printed: kappa about 0.6/day, kappa T about 3 (extra check 0.05)")
        a.add(op, inp, outputs=r, cls="simple_analytic", verified=verified, tags=tags, extra_checks=extra,
              description=desc)
    out["ac_h"] = res

    m = Suite("imp_h", IMP, G)
    res = []
    for op, inp, desc, ver in IMP_CASES:
        r, err = run(imp_sqrt if op == "exec.impact.sqrt" else imp_ow, inp)
        res.append((r, err))
        tags = ("stage_h", "execution", "impact", "synthetic") + (("error",) if err else ())
        if err:
            m.add(op, inp, error=err, verified=("hand", ver), tags=tags, description=desc)
        else:
            m.add(op, inp, outputs=r, cls="simple_analytic", verified=(ORACLE, ver), tags=tags, description=desc)
    out["imp_h"] = res

    t = Suite("tca_h", TCA, G)
    res = []
    for inp, desc, ver in TCA_CASES:
        r, err = run(tca, inp)
        res.append((r, err))
        tags = ("stage_h", "execution", "tca", "synthetic") + (("error",) if err else ())
        if err:
            t.add("exec.tca.shortfall", inp, error=err, verified=("hand", ver), tags=tags, description=desc)
        else:
            t.add("exec.tca.shortfall", inp, outputs=r, cls="simple_analytic", verified=("hand", ORACLE, ver),
                  tags=tags, description=desc)
    out["tca_h"] = res

    q = Suite("as_h", AS, G)
    res = []
    for inp, desc, printed in AS_CASES:
        r, err = run(as_quotes, inp)
        res.append((r, err))
        tags = ("stage_h", "microstructure", "market_making", "synthetic") + (("error",) if err else ())
        if err:
            q.add("micro.mm.as_quotes", inp, error=err, verified=("hand", BLIND), tags=tags, description=desc)
            continue
        extra, ver = None, ("hand", ORACLE, BLIND)
        if printed is not None:
            extra = [{"method": "absolute", "output": "spread", "expected": printed, "limit": 0.005}]
            ver += (f"[AS08] printed average spread {printed} (extra check 0.005)",)
        q.add("micro.mm.as_quotes", inp, outputs=r, cls="simple_analytic", verified=ver, tags=tags,
              extra_checks=extra, description=desc)
    out["as_h"] = res

    u = Suite("uc5_h", UC, G)
    res = []
    for k, (inp, desc) in enumerate(UC_CASES):
        r, err = run(uc5, inp)
        res.append((r, err))
        tags = ("stage_h", "use_case", "execution", "synthetic") + (("error",) if err else ())
        if err:
            u.add("usecase.execution_tca", inp, error=err, verified=("hand", ADDED), tags=tags, description=desc)
        else:
            assert sum(r["lots"]) == inp["quantity"]
            u.add("usecase.execution_tca", inp, outputs=r, cls="simple_analytic", verified=(ORACLE, EXACT, BLIND_UC5) if k in UC5_BLIND else (ORACLE, EXACT, ADDED),
                  tags=tags, output_classes={"lots": "date_and_convention", "filled": "date_and_convention"},
                  description=desc)
    out["uc5_h"] = res
    assert_tables(out)
    e = Suite("e1_h", SCHED, G)
    e1_cases(e, [s, a, m, t, q, u])
    return [s, a, m, t, q, u, e], out


def _first_real(inputs):
    """Path of the first binary64 input (a top-level Real, else the first Real in a top-level list)."""
    for k, v in inputs.items():
        if isinstance(v, float):
            return k, None
    for k, v in inputs.items():
        if isinstance(v, list):
            for i, x in enumerate(v):
                if isinstance(x, float):
                    return k, i
    return None


def e1_cases(e, suites):
    """E1 (ruling F-2): one non-finite input per stage H operation, from its first value case; E_DOMAIN before any
    other check. Written for tools/check_e1_coverage.py."""
    seen = set()
    for su in suites:
        for c in su.cases:
            op = c["operation"]
            if op in seen or c["expected"]["status"] != "ok":
                continue
            path = _first_real(c["inputs"])
            if path is None:  # an all-integer case (UNITS mode); the next value case of the operation has a Real
                continue
            seen.add(op)
            inp = json.loads(json.dumps(c["inputs"]))
            k, i = path
            if i is None:
                inp[k] = "NaN"
            else:
                inp[k][i] = "NaN"
            where = k if i is None else f"{k}/{i}"
            e.add(op, inp, error="E_DOMAIN", cls=c["tolerance_class"], verified=("hand",),
                  tags=("stage_h", "e1", "non-finite-input"), description=f"F-2: NaN at {where} (from {c['case_id']})")
    assert len(seen) == len({c["operation"] for su in suites for c in su.cases}), "an operation has no E1 case"


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    suites, _ = build()
    for s in suites:
        s.write()
    common.GOLDEN = keep
    note("stage H wave 1: " + ", ".join(f"{s.name} {len(s.cases)}" for s in suites))


if __name__ == "__main__":
    main()
