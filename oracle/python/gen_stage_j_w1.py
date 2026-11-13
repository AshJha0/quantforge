"""Stage J wave 1: backtester, purged CV, regime labelling, research statistics.

Specs: specifications/11-research/backtester.md, purged-cv.md, regimes.md, research-statistics.md; rulings
specifications/stage-j-rulings-w1.md (J-1 onwards).

Independent oracle: every value is computed here from the formulas in the specs, in exact rational arithmetic
(fractions) where the operation is arithmetic only (backtester, CV indices, PBO with the MEAN metric) and at 50 digits
(mpmath) elsewhere. Error cases are built by breaking one rule; the reference raises, and the generator asserts the code.

Outside checks (plan rule: a value case checked against a hand or textbook example where possible):
- DSR: Bailey and Lopez de Prado (2014) worked example, SR0 = 0.1132 per period and DSR = 0.9004 (recalled printed
  values; the paper was not opened in this session, so J-1 is not closed by this case alone).
- Viterbi: the textbook two-state example (Healthy/Fever, observations normal, cold, dizzy): path H, H, F with joint
  probability 0.01512, computed by hand in the generator and by brute-force enumeration of all K^T paths.
- Power: the MDS table of research/preregs/README.md (2.4865 / sqrt(T); 0.67, 1.27, 0.76).
- Backtester: a 10-trade example hand-computed line by line (J-3), equal in Fractions.
- Purged CV: a 10-observation example written out by hand in the spec.

    cd oracle/python && uv run python -W ignore gen_stage_j_w1.py
"""
import itertools
import math
from fractions import Fraction as Fr

import mpmath as mp

from qf_oracle import common
from qf_oracle.common import Suite, note

mp.mp.dps = 50
G = "oracle/python/gen_stage_j_w1.py"
FOLDER = "stage_j"
SA, EX, PU = "simple_analytic", "date_and_convention", "per_unit"
SPEC_BT = "specifications/11-research/backtester.md"
SPEC_CV = "specifications/11-research/purged-cv.md"
SPEC_RG = "specifications/11-research/regimes.md"
SPEC_ST = "specifications/11-research/research-statistics.md"
LIM = {"bars": 1_000_000, "observations": 1_000_000, "pbo_cells": 10_000_000, "pbo_partitions": 16,
       "pbo_strategies": 10_000, "viterbi_steps": 100_000, "viterbi_states": 32, "cpcv_groups": 64}


class QfErr(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def fin(*xs):
    for x in xs:
        if isinstance(x, list):
            fin(*x)
        elif x is not None and not isinstance(x, str) and not math.isfinite(x):
            raise QfErr("E_DOMAIN")


# ---------------------------------------------------------------- backtester (J-1 .. J-3 rulings)

def backtest_ref(inp):
    p, tg = inp["prices"], inp["targets"]
    lag = inp.get("lag", 1)
    hs, cm, fx, mult = (inp.get("half_spread_bps", 0.0), inp.get("commission_per_unit", 0.0),
                        inp.get("fixed_per_trade", 0.0), inp.get("multiplier", 1.0))
    eng = inp.get("engine", "EVENT")
    if eng not in ("EVENT", "VECTOR"):
        raise QfErr("E_SCHEMA")
    if len(p) > LIM["bars"]:
        raise QfErr("E_LIMIT")
    fin(p, tg, hs, cm, fx, mult)
    if len(p) < 2 or len(tg) != len(p) or not isinstance(lag, int) or lag < 0 or lag >= len(p):
        raise QfErr("E_INPUT")
    if min(p) <= 0 or hs < 0 or cm < 0 or fx < 0 or mult <= 0:
        raise QfErr("E_DOMAIN")
    P, TG = [Fr(x) for x in p], [Fr(x) for x in tg]
    HS, CM, FX, M = Fr(hs) / 10000, Fr(cm), Fr(fx), Fr(mult)
    T = len(P)
    q = [TG[t - lag] if t >= lag else Fr(0) for t in range(T)]
    gross, sc, cc, fc, net, trades, eq = [], [], [], [], [], [], []
    prev, cum, peak, mdd, cnt, turn = Fr(0), Fr(0), Fr(0), Fr(0), 0, Fr(0)
    for t in range(T):
        d = q[t] - prev
        g = prev * (P[t] - P[t - 1]) * M if t else Fr(0)
        s, c, f = abs(d) * P[t] * HS * M, abs(d) * CM, (FX if d != 0 else Fr(0))
        n = g - s - c - f
        cnt += d != 0
        turn += abs(d) * P[t] * M
        cum += n
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
        gross.append(g); sc.append(s); cc.append(c); fc.append(f); net.append(n); trades.append(d); eq.append(cum)
        prev = q[t]
    F = lambda xs: [float(x) for x in xs]
    tot = {"gross": sum(gross), "spread_cost": sum(sc), "commission": sum(cc), "fixed_cost": sum(fc), "net": sum(net)}
    assert tot["gross"] - tot["spread_cost"] - tot["commission"] - tot["fixed_cost"] == tot["net"]
    return {"positions": F(q), "trades": F(trades), "pnl_gross": F(gross), "cost": F([a + b + c for a, b, c in zip(sc, cc, fc)]),
            "pnl_net": F(net), "equity": F(eq), "total_gross": float(tot["gross"]), "total_spread_cost": float(tot["spread_cost"]),
            "total_commission": float(tot["commission"]), "total_fixed_cost": float(tot["fixed_cost"]),
            "total_net": float(tot["net"]), "turnover": float(turn), "trade_count": cnt, "max_drawdown": float(mdd)}


# ---------------------------------------------------------------- purged k-fold, CPCV

def kfold_ref(inp):
    t0, t1, k = inp["t0"], inp["t1"], inp["n_splits"]
    emb = inp.get("embargo_pct", 0.0)
    if len(t0) > LIM["observations"]:
        raise QfErr("E_LIMIT")
    fin(t0, t1, emb)
    n = len(t0)
    if len(t1) != n or not isinstance(k, int) or k < 2 or k > n:
        raise QfErr("E_INPUT")
    if any(t0[i] > t0[i + 1] for i in range(n - 1)):
        raise QfErr("E_INPUT")
    if any(t1[i] < t0[i] for i in range(n)) or emb < 0 or emb >= 1:
        raise QfErr("E_DOMAIN")
    h = math.floor(Fr(emb) * n)
    sizes = [n // k + (1 if i < n % k else 0) for i in range(k)]
    folds, a = [], 0
    for sz in sizes:
        b = a + sz
        lo, hi = t0[a], max(t1[a:b])
        train = [j for j in range(n) if not (a <= j < b) and not (t0[j] <= hi and t1[j] >= lo) and not (b <= j < b + h)]
        folds.append({"test": list(range(a, b)), "train": train})
        a = b
    return {"folds": folds, "embargo_count": h}


def cpcv_ref(inp):
    N, k = inp["n_groups"], inp["n_test_groups"]
    if not isinstance(N, int) or not isinstance(k, int):
        raise QfErr("E_SCHEMA")
    if N > LIM["cpcv_groups"]:
        raise QfErr("E_LIMIT")
    if N < 2 or k < 1 or k >= N:
        raise QfErr("E_INPUT")
    c = math.comb(N, k)
    return {"n_splits": c, "n_paths": c * k // N}


# ---------------------------------------------------------------- Viterbi

def viterbi_ref(inp):
    pi, A = inp["initial"], inp["transition"]
    K = len(pi)
    has_e, has_g = "emission" in inp, any(x in inp for x in ("observations", "means", "sds"))
    if has_e == has_g:
        raise QfErr("E_INPUT")
    Tn = len(inp["emission"]) if has_e else len(inp["observations"])
    if Tn > LIM["viterbi_steps"] or K > LIM["viterbi_states"]:
        raise QfErr("E_LIMIT")
    fin(pi, A, inp.get("emission"), inp.get("observations"), inp.get("means"), inp.get("sds"))
    if K < 1 or Tn < 1 or len(A) != K or any(len(r) != K for r in A):
        raise QfErr("E_INPUT")
    if has_e and any(len(r) != K for r in inp["emission"]):
        raise QfErr("E_INPUT")
    if has_g and (len(inp["means"]) != K or len(inp["sds"]) != K):
        raise QfErr("E_INPUT")
    rows = [pi] + A
    if any(x < 0 for r in rows for x in r) or any(abs(sum(r) - 1) > 1e-9 for r in rows):
        raise QfErr("E_DOMAIN")
    if has_g and min(inp["sds"]) <= 0:
        raise QfErr("E_DOMAIN")
    if has_e and any(x < 0 for r in inp["emission"] for x in r):
        raise QfErr("E_DOMAIN")
    lg = lambda x: mp.log(x) if x > 0 else mp.ninf
    if has_e:
        LE = [[lg(mp.mpf(x)) for x in r] for r in inp["emission"]]
    else:
        LE = [[-mp.log(mp.mpf(s)) - mp.log(2 * mp.pi) / 2 - (mp.mpf(y) - m) ** 2 / (2 * mp.mpf(s) ** 2)
               for m, s in zip(inp["means"], inp["sds"])] for y in inp["observations"]]
    LA = [[lg(mp.mpf(x)) for x in r] for r in A]
    d = [lg(mp.mpf(pi[i])) + LE[0][i] for i in range(K)]
    back = []
    for t in range(1, Tn):
        nd, bk = [], []
        for j in range(K):
            best, arg = mp.ninf, 0
            for i in range(K):  # ties: smallest i (strict >)
                v = d[i] + LA[i][j]
                if v > best:
                    best, arg = v, i
            nd.append(best + LE[t][j]); bk.append(arg)
        d = nd; back.append(bk)
    best, s = mp.ninf, 0
    for i in range(K):
        if d[i] > best:
            best, s = d[i], i
    if best == mp.ninf:
        raise QfErr("E_DOMAIN")
    path = [s]
    for bk in reversed(back):
        path.append(bk[path[-1]])
    path.reverse()
    if K ** Tn <= 4096:  # brute force over every path: independent check of the argmax and its value
        def score(pth):
            v = lg(mp.mpf(pi[pth[0]])) + LE[0][pth[0]]
            for t in range(1, Tn):
                v += LA[pth[t - 1]][pth[t]] + LE[t][pth[t]]
            return v
        allv = sorted(((score(list(pp)), pp) for pp in itertools.product(range(K), repeat=Tn)), key=lambda z: -z[0])
        assert abs(allv[0][0] - best) < mp.mpf("1e-40") and list(allv[0][1]) == path
        if len(allv) > 1 and allv[1][0] != mp.ninf:
            assert allv[0][0] - allv[1][0] > mp.mpf("1e-6"), "near-tie in a golden"
    return {"states": path, "log_probability": float(best)}


# ---------------------------------------------------------------- statistics

def q(p):
    return mp.sqrt(2) * mp.erfinv(2 * p - 1)


def psr_core(sr, T, s3, k4, bench):
    den = 1 - s3 * sr + (k4 - 1) / mp.mpf(4) * sr ** 2
    if den <= 0:
        raise QfErr("E_DOMAIN")
    z = (sr - bench) * mp.sqrt(T - 1) / mp.sqrt(den)
    return z, mp.ncdf(z)


def stat_checks(inp):
    fin(inp["sr"], inp.get("skew", 0.0), inp.get("kurtosis", 3.0))
    if not isinstance(inp["n_obs"], int) or inp["n_obs"] < 2:
        raise QfErr("E_INPUT")
    if inp.get("kurtosis", 3.0) < 1:
        raise QfErr("E_DOMAIN")
    return mp.mpf(inp["sr"]), inp["n_obs"], mp.mpf(inp.get("skew", 0.0)), mp.mpf(inp.get("kurtosis", 3.0))


def psr_ref(inp):
    sr, T, s3, k4 = stat_checks(inp)
    fin(inp.get("sr_benchmark", 0.0))
    z, p = psr_core(sr, T, s3, k4, mp.mpf(inp.get("sr_benchmark", 0.0)))
    return {"z": float(z), "psr": float(p)}


def dsr_ref(inp):
    sr, T, s3, k4 = stat_checks(inp)
    fin(inp["sr_variance"])
    N = inp["n_trials"]
    if not isinstance(N, int) or N < 1:
        raise QfErr("E_INPUT")
    if inp["sr_variance"] < 0:
        raise QfErr("E_DOMAIN")
    g = mp.euler
    sr0 = mp.mpf(0) if N == 1 else mp.sqrt(mp.mpf(inp["sr_variance"])) * ((1 - g) * q(1 - mp.mpf(1) / N) + g * q(1 - 1 / (N * mp.e)))
    z, p = psr_core(sr, T, s3, k4, sr0)
    return {"sr0": float(sr0), "z": float(z), "dsr": float(p)}


def power_ref(inp):
    yrs, al, pw = inp["years"], inp.get("alpha", 0.05), inp.get("power", 0.8)
    fin(yrs, al, pw, inp.get("sr_target"))
    if yrs <= 0 or not 0 < al < 1 or not 0 < pw < 1 or al >= pw:
        raise QfErr("E_DOMAIN")
    zz = q(1 - mp.mpf(al)) + q(mp.mpf(pw))
    out = {"z_sum": float(zz), "mds": float(zz / mp.sqrt(yrs)), "se_at_zero": float(1 / mp.sqrt(yrs))}
    if "sr_target" in inp:
        s = mp.mpf(inp["sr_target"])
        if s <= 0:
            raise QfErr("E_DOMAIN")
        out["years_required"] = float((zz / s) ** 2)
        out["se_at_target"] = float(mp.sqrt((1 + s ** 2 / 2) / yrs))
    return out


def pbo_ref(inp):
    M, S = inp["performance"], inp["n_partitions"]
    metric = inp.get("metric", "SHARPE")
    if metric not in ("SHARPE", "MEAN"):
        raise QfErr("E_SCHEMA")
    T = len(M)
    N = len(M[0]) if T else 0
    if not isinstance(S, int):
        raise QfErr("E_SCHEMA")
    if T * N > LIM["pbo_cells"] or S > LIM["pbo_partitions"] or N > LIM["pbo_strategies"]:
        raise QfErr("E_LIMIT")
    fin(M)
    if T == 0 or N < 2 or any(len(r) != N for r in M) or S < 2 or S % 2 or T % S or T // S < 2:
        raise QfErr("E_INPUT")
    R = [[Fr(x) for x in r] for r in M]
    blk = T // S

    def perf(rows):
        out = []
        for j in range(N):
            xs = [R[i][j] for i in rows]
            m = sum(xs) / len(xs)
            if metric == "MEAN":
                out.append(m)
                continue
            v = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
            if v == 0:
                raise QfErr("E_DOMAIN")
            out.append(mp.mpf(m.numerator) / m.denominator / mp.sqrt(mp.mpf(v.numerator) / v.denominator))
        return out

    logits, below = [], 0
    for J in itertools.combinations(range(S), S // 2):
        tr = [i for b in J for i in range(b * blk, (b + 1) * blk)]
        te = [i for b in range(S) if b not in J for i in range(b * blk, (b + 1) * blk)]
        pi, po = perf(tr), perf(te)
        best = max(pi)
        n = min(j for j in range(N) if pi[j] == best)
        less = sum(1 for x in po if x < po[n]); eq = sum(1 for x in po if x == po[n])
        rank = mp.mpf(2 * less + eq + 1) / 2  # average rank, 1 = worst
        w = rank / (N + 1)
        lam = mp.log(w / (1 - w))
        logits.append(float(lam)); below += lam <= 0
    return {"pbo": below / len(logits), "logits": logits, "n_combinations": len(logits)}


# ---------------------------------------------------------------- case helpers

def mk(suite, op, ref, inp, code=None, cls=SA, desc=None, tags=(), verified=("reference-computed",), oc=None):
    try:
        out = ref(inp)
        assert code is None, f"{suite.name}: expected {code}, got a value"
        suite.add(op, inp, outputs=out, cls=cls, verified=verified, tags=("research", "synthetic") + tuple(tags),
                  description=desc, output_classes=oc)
    except QfErr as e:
        assert e.code == code, f"{suite.name} {desc}: expected {code}, got {e.code}"
        suite.add(op, inp, error=code, cls=EX, verified=("reference-computed",), tags=("invalid", "research") + tuple(tags),
                  description=desc)


def det(seed, n, lo=-1.0, hi=1.0):
    """Deterministic pseudo-random values (LCG, no library RNG), rounded to 6 decimals so goldens are short."""
    x, out = seed, []
    for _ in range(n):
        x = (6364136223846793005 * x + 1442695040888963407) % 2 ** 64
        out.append(round(lo + (hi - lo) * (x >> 11) / 2 ** 53, 6))
    return out


def build():
    suites = []
    # ---- backtester
    s = Suite("backtest_j", SPEC_BT, G); suites.append(s)
    OPB = "research.backtest.run"
    hand = {"prices": [100.0, 101.0, 99.5, 102.0, 103.0, 101.5, 100.0, 104.0, 105.5, 103.0, 106.0, 107.0],
            "targets": [1.0, 2.0, -1.0, 0.0, 3.0, 3.0, -2.0, 1.0, 0.0, 2.0, 0.0, 0.0],
            "lag": 1, "half_spread_bps": 5.0, "commission_per_unit": 0.01, "fixed_per_trade": 1.0}
    out = backtest_ref(hand)
    assert out["trade_count"] == 10, out["trade_count"]
    for eng in ("EVENT", "VECTOR"):
        mk(s, OPB, backtest_ref, dict(hand, engine=eng), desc=f"J-3 ten-trade hand example, {eng} engine",
           verified=("hand", "reference-computed"), oc={"trade_count": EX, "positions": EX, "trades": EX})
    mk(s, OPB, backtest_ref, dict(hand, lag=0), desc="lag 0: same-close execution (look-ahead allowed only by request)")
    mk(s, OPB, backtest_ref, dict(hand, lag=2), desc="lag 2")
    mk(s, OPB, backtest_ref, dict(hand, half_spread_bps=0.0, commission_per_unit=0.0, fixed_per_trade=0.0),
       desc="no costs: net equals gross")
    mk(s, OPB, backtest_ref, dict(hand, multiplier=50.0), desc="futures multiplier 50")
    mk(s, OPB, backtest_ref, {"prices": [10.0, 10.0], "targets": [0.0, 0.0]}, desc="flat: no trades, zero P&L",
       oc={"trade_count": EX})
    mk(s, OPB, backtest_ref, {"prices": [50.0, 51.0, 49.0], "targets": [-4.0, -4.0, -4.0]}, desc="short held, costs default 0")
    for i in range(6):
        n = 20 + 15 * i
        pr = [100.0]
        for r in det(11 + i, n - 1, -0.02, 0.02):
            pr.append(round(pr[-1] * (1 + r), 4))
        tg = [round(x * 5) for x in det(101 + i, n, -1, 1)]
        mk(s, OPB, backtest_ref, {"prices": pr, "targets": [float(x) for x in tg], "lag": 1 + i % 2, "half_spread_bps": 2.0 + i,
                                   "commission_per_unit": 0.005, "fixed_per_trade": 0.5, "engine": "EVENT" if i % 2 else "VECTOR"},
           desc=f"seeded walk {n} bars")
    base = {"prices": [100.0, 101.0, 102.0], "targets": [1.0, 0.0, 0.0]}
    for d, ch, code in [("length mismatch", {"targets": [1.0, 0.0]}, "E_INPUT"), ("one bar", {"prices": [100.0], "targets": [1.0]}, "E_INPUT"),
                        ("lag equal to bars", {"lag": 3}, "E_INPUT"), ("negative lag", {"lag": -1}, "E_INPUT"),
                        ("zero price", {"prices": [100.0, 0.0, 102.0]}, "E_DOMAIN"), ("negative spread", {"half_spread_bps": -1.0}, "E_DOMAIN"),
                        ("negative commission", {"commission_per_unit": -0.1}, "E_DOMAIN"), ("zero multiplier", {"multiplier": 0.0}, "E_DOMAIN"),
                        ("unknown engine", {"engine": "FAST"}, "E_SCHEMA")]:
        mk(s, OPB, backtest_ref, dict(base, **ch), code=code, desc=d)

    # ---- purged k-fold
    s = Suite("purgedcv_j", SPEC_CV, G); suites.append(s)
    OPK = "research.cv.purged_kfold"
    ex = {"t0": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], "t1": [2, 3, 4, 5, 6, 7, 8, 9, 10, 11], "n_splits": 3, "embargo_pct": 0.1}
    mk(s, OPK, kfold_ref, ex, cls=EX, desc="spec hand example: 10 labels spanning 3 bars, k=3, embargo 1", verified=("hand", "reference-computed"))
    mk(s, OPK, kfold_ref, dict(ex, embargo_pct=0.0), cls=EX, desc="no embargo")
    mk(s, OPK, kfold_ref, dict(ex, t1=ex["t0"], embargo_pct=0.0), cls=EX, desc="point labels, no embargo: plain KFold")
    mk(s, OPK, kfold_ref, dict(ex, n_splits=10), cls=EX, desc="leave-one-out")
    mk(s, OPK, kfold_ref, {"t0": [0.0, 0.5, 1.0, 1.5, 4.0, 4.5, 9.0], "t1": [3.0, 1.0, 1.2, 5.0, 4.2, 9.5, 9.1], "n_splits": 3, "embargo_pct": 0.2},
       cls=EX, desc="real times, uneven spans, one long label")
    for i in range(5):
        n = 30 + 20 * i
        t0 = list(range(n)); t1 = [t + 1 + int(abs(x) * 6) for t, x in zip(t0, det(201 + i, n))]
        mk(s, OPK, kfold_ref, {"t0": t0, "t1": t1, "n_splits": 3 + i, "embargo_pct": 0.01 * (i + 1)}, cls=EX, desc=f"seeded spans n={n}")
    for d, ch, code in [("k=1", {"n_splits": 1}, "E_INPUT"), ("k above n", {"n_splits": 11}, "E_INPUT"),
                        ("t0 not sorted", {"t0": [1, 0, 2, 3, 4, 5, 6, 7, 8, 9]}, "E_INPUT"),
                        ("t1 before t0", {"t1": [2, 3, 4, 5, 6, 7, 8, 9, 10, 8]}, "E_DOMAIN"),
                        ("embargo 1", {"embargo_pct": 1.0}, "E_DOMAIN"), ("lengths differ", {"t1": [2, 3]}, "E_INPUT")]:
        mk(s, OPK, kfold_ref, dict(ex, **ch), code=code, desc=d)
    OPC = "research.cv.cpcv_paths"
    for N, k in [(6, 2), (10, 2), (5, 1), (8, 4), (64, 3)]:
        mk(s, OPC, cpcv_ref, {"n_groups": N, "n_test_groups": k}, cls=EX, desc=f"N={N}, k={k}",
           verified=("hand", "reference-computed") if (N, k) == (6, 2) else ("reference-computed",))
    for d, inp, code in [("k=N", {"n_groups": 4, "n_test_groups": 4}, "E_INPUT"), ("N above 64", {"n_groups": 65, "n_test_groups": 2}, "E_LIMIT")]:
        mk(s, OPC, cpcv_ref, inp, code=code, desc=d)

    # ---- Viterbi
    s = Suite("regime_j", SPEC_RG, G); suites.append(s)
    OPV = "research.regime.viterbi"
    tb = {"initial": [0.6, 0.4], "transition": [[0.7, 0.3], [0.4, 0.6]], "emission": [[0.5, 0.1], [0.4, 0.3], [0.1, 0.6]]}
    o = viterbi_ref(tb)
    assert o["states"] == [0, 0, 1] and abs(math.exp(o["log_probability"]) - 0.01512) < 1e-15
    mk(s, OPV, viterbi_ref, tb, desc="textbook Healthy/Fever example: H, H, F with probability 0.01512",
       verified=("hand", "brute-force", "reference-computed"), oc={"states": EX})
    g2 = {"initial": [0.5, 0.5], "transition": [[0.95, 0.05], [0.1, 0.9]], "means": [0.0005, -0.001], "sds": [0.008, 0.025]}
    for i in range(6):
        n = 8 if i < 3 else 40 + 30 * i
        obs = [round(x * (0.01 if (t // 10) % 2 == 0 else 0.04), 6) for t, x in enumerate(det(301 + i, n))]
        mk(s, OPV, viterbi_ref, dict(g2, observations=obs), desc=f"two-state Gaussian volatility regimes, {n} returns",
           verified=("brute-force", "reference-computed") if n == 8 else ("reference-computed",), oc={"states": EX})
    g3 = {"initial": [0.2, 0.5, 0.3], "transition": [[0.8, 0.15, 0.05], [0.1, 0.8, 0.1], [0.05, 0.15, 0.8]],
          "means": [-0.01, 0.0, 0.01], "sds": [0.02, 0.005, 0.01]}
    mk(s, OPV, viterbi_ref, dict(g3, observations=det(399, 7, -0.03, 0.03)), desc="three states, brute-force checked",
       verified=("brute-force", "reference-computed"), oc={"states": EX})
    mk(s, OPV, viterbi_ref, dict(g3, observations=[0.0]), desc="one observation", oc={"states": EX})
    mk(s, OPV, viterbi_ref, {"initial": [1.0, 0.0], "transition": [[0.0, 1.0], [1.0, 0.0]], "emission": [[0.5, 0.5]] * 5},
       desc="deterministic alternation with zero probabilities", verified=("hand", "reference-computed"), oc={"states": EX})
    for d, ch, code in [("rows do not sum to 1", {"transition": [[0.7, 0.2], [0.4, 0.6]]}, "E_DOMAIN"),
                        ("negative probability", {"initial": [1.2, -0.2]}, "E_DOMAIN"),
                        ("emission and observations both given", {"observations": [0.0, 0.1, 0.2], "means": [0, 0], "sds": [1, 1]}, "E_INPUT"),
                        ("ragged transition", {"transition": [[1.0], [0.4, 0.6]]}, "E_INPUT"),
                        ("impossible sequence", {"initial": [1.0, 0.0], "transition": [[1.0, 0.0], [0.0, 1.0]], "emission": [[0.5, 0.5], [0.0, 1.0], [0.5, 0.5]]}, "E_DOMAIN")]:
        mk(s, OPV, viterbi_ref, dict(tb, **ch), code=code, desc=d)
    mk(s, OPV, viterbi_ref, dict(g2, sds=[0.0, 0.01], observations=[0.0]), code="E_DOMAIN", desc="zero sd")

    # ---- statistics
    s = Suite("rstats_j", SPEC_ST, G); suites.append(s)
    OPD, OPP, OPW, OPO = "research.stats.dsr", "research.stats.psr", "research.stats.power", "research.stats.pbo"
    bl = {"sr": 2.5 / math.sqrt(250), "n_obs": 1250, "skew": -3.0, "kurtosis": 10.0, "n_trials": 100, "sr_variance": 0.5 / 250}
    o = dsr_ref(bl)
    assert round(o["sr0"], 4) == 0.1132 and round(o["dsr"], 4) == 0.9004
    mk(s, OPD, dsr_ref, bl, cls=PU, desc="Bailey and Lopez de Prado (2014) worked example: SR0 0.1132, DSR 0.9004",
       verified=("textbook-recalled", "reference-computed"))
    for N in (1, 2, 10, 1000):
        mk(s, OPD, dsr_ref, dict(bl, n_trials=N), cls=PU, desc=f"{N} trials")
    mk(s, OPD, dsr_ref, {"sr": 0.05, "n_obs": 2520, "n_trials": 24, "sr_variance": 0.0004}, cls=PU, desc="normal returns by default (skew 0, kurtosis 3)")
    mk(s, OPD, dsr_ref, dict(bl, sr_variance=0.0), cls=PU, desc="zero variance across trials: SR0 = 0")
    for d, ch, code in [("n_obs 1", {"n_obs": 1}, "E_INPUT"), ("zero trials", {"n_trials": 0}, "E_INPUT"),
                        ("negative variance", {"sr_variance": -1e-4}, "E_DOMAIN"), ("kurtosis below 1", {"kurtosis": 0.5}, "E_DOMAIN"),
                        ("non-positive variance term", {"sr": 1.0, "skew": 5.0, "kurtosis": 3.0}, "E_DOMAIN")]:
        mk(s, OPD, dsr_ref, dict(bl, **ch), code=code, desc=d)
    for sr, b in [(0.1, 0.0), (0.05, 0.02), (-0.02, 0.0), (0.2, 0.1)]:
        mk(s, OPP, psr_ref, {"sr": sr, "n_obs": 500, "skew": -0.5, "kurtosis": 5.0, "sr_benchmark": b}, cls=PU, desc=f"PSR sr {sr} against {b}")
    for yrs, nm in [(13.83, "R3-01 0.67"), (3.83, "R3-02 1.27"), (10.83, "R3-03 0.76"), (1.0, "forward log 2.49")]:
        o = power_ref({"years": yrs})
        assert abs(o["z_sum"] - 2.4865) < 5e-5
        mk(s, OPW, power_ref, {"years": yrs}, cls=PU, desc=f"prereg README table: {nm}", verified=("hand", "reference-computed"))
    mk(s, OPW, power_ref, {"years": 5.0, "alpha": 0.01, "power": 0.9, "sr_target": 1.0}, cls=PU, desc="years required for SR 1")
    for d, inp, code in [("alpha above power", {"years": 1.0, "alpha": 0.9, "power": 0.8}, "E_DOMAIN"),
                         ("zero years", {"years": 0.0}, "E_DOMAIN"), ("negative target", {"years": 1.0, "sr_target": -0.5}, "E_DOMAIN")]:
        mk(s, OPW, power_ref, inp, code=code, desc=d)
    # PBO: hand case, S = 2, MEAN metric, 2 strategies (worked in the spec)
    hp = {"performance": [[1.0, 0.0], [1.0, 0.0], [0.0, 2.0], [0.0, 2.0]], "n_partitions": 2, "metric": "MEAN"}
    o = pbo_ref(hp)
    assert o["pbo"] == 1.0 and o["n_combinations"] == 2
    mk(s, OPO, pbo_ref, hp, cls=PU, desc="spec hand example: the in-sample winner always loses out of sample, PBO 1",
       verified=("hand", "reference-computed"), oc={"n_combinations": EX})
    for i, (T, N, S, met) in enumerate([(16, 4, 4, "MEAN"), (24, 6, 4, "SHARPE"), (40, 10, 8, "SHARPE"), (30, 3, 6, "MEAN"), (64, 20, 8, "SHARPE")]):
        skill = [0.0] * N
        if i % 2:
            skill[0] = 0.3
        M = [[round(x + skill[j], 6) for j, x in enumerate(det(501 + 7 * i + t, N))] for t in range(T)]
        mk(s, OPO, pbo_ref, {"performance": M, "n_partitions": S, "metric": met}, cls=PU,
           desc=f"T={T}, N={N}, S={S}, {met}{', one skilled strategy' if i % 2 else ', pure noise'}", oc={"n_combinations": EX})
    for d, ch, code in [("odd S", {"n_partitions": 3}, "E_INPUT"), ("T not divisible by S", {"performance": hp["performance"][:3]}, "E_INPUT"),
                        ("one strategy", {"performance": [[1.0], [2.0], [3.0], [4.0]]}, "E_INPUT"),
                        ("zero dispersion under SHARPE", {"metric": "SHARPE"}, "E_DOMAIN"), ("S above 16", {"n_partitions": 18}, "E_LIMIT")]:
        mk(s, OPO, pbo_ref, dict(hp, **ch), code=code, desc=d)
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
    note(f"stage J wave 1: {tot[0]} cases, value {tot[1]}, error {tot[2]}")


if __name__ == "__main__":
    main()
