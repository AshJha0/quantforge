"""Stage G, slice Q9 part 1: Monte Carlo Greeks under GBM - pathwise, likelihood ratio, smoothed pathwise digital and
central bump with common draws - on the core.rng stream (01-core/rng.md: SplitMix64 seed, xoshiro256**, stream 0,
AS 241 normals, one normal per path). Goldens are the exact estimator values on those draws (class common_rng).
The plan 12.3 Q9 acceptance (ruling G-10) runs at 100,000 paths and is written to oracle/Q9_ACCEPTANCE.json.

    cd oracle/python && uv run python -W ignore gen_stage_g_q9.py
"""
import json
import math
from pathlib import Path

from qf_oracle import common
from qf_oracle.common import Suite, note
from qf_oracle.rng import Xo, ppnd16

G = "oracle/python/gen_stage_g_q9.py"
OP = "risk.mc.greeks"
HERE = Path(__file__).resolve().parent
MARGIN = 1e-9  # no path's S_T within this relative distance of a payoff kink (K, K - eps, K + eps)


def normals(seed, n):
    g = Xo(seed)
    return [ppnd16(((g.next() >> 12) + 0.5) * 2.0 ** -52) for _ in range(n)]


def payoff(kind, ST, K):
    if kind == "CALL":
        return max(ST - K, 0.0)
    if kind == "PUT":
        return max(K - ST, 0.0)
    return 1.0 if ST > K else 0.0  # DIGITAL_CALL pays 1


def mean_se(xs):
    n = len(xs)
    m = math.fsum(xs) / n
    v = math.fsum((x - m) ** 2 for x in xs) / (n - 1)
    return m, math.sqrt(v / n)


def greeks(inp, zs=None):
    S, K, T, r, q, v = (inp[k] for k in ("spot", "strike", "expiry_years", "rate", "dividend_yield", "vol"))
    kind, meth, n = inp["payoff"], inp["method"], inp["paths"]
    zs = zs if zs is not None else normals(int(inp["seed"]), n)
    df, sT = math.exp(-r * T), math.sqrt(T)
    drift = (r - q - v * v / 2) * T
    eps = inp.get("smoothing_width")
    h = inp.get("bump_relative")
    P, D, V = [], [], []
    for z in zs:
        ST = S * math.exp(drift + v * sT * z)
        for kink in (K,) + ((K - eps, K + eps) if eps else ()):
            assert abs(ST - kink) > MARGIN * K, "path on a kink: move the inputs"
        P.append(df * payoff(kind, ST, K))
        dST_dv = ST * (sT * z - v * T)
        if meth == "PATHWISE":
            if kind == "CALL":
                g = 1.0 if ST > K else 0.0
            elif kind == "PUT":
                g = -1.0 if ST < K else 0.0
            else:
                g = (1.0 / (2 * eps)) if abs(ST - K) < eps else 0.0
            D.append(df * g * ST / S)
            V.append(df * g * dST_dv)
        elif meth == "LIKELIHOOD_RATIO":
            f = df * payoff(kind, ST, K)
            D.append(f * z / (S * v * sT))
            V.append(f * ((z * z - 1) / v - z * sT))
        else:  # BUMP: central, common draws, relative bump h on S and on v
            for Sb in (S * (1 + h), S * (1 - h)):
                STb = Sb * math.exp(drift + v * sT * z)
                assert abs(STb - K) > MARGIN * K, "bumped path on a kink: move the inputs"
            up = df * payoff(kind, S * (1 + h) * math.exp(drift + v * sT * z), K)
            dn = df * payoff(kind, S * (1 - h) * math.exp(drift + v * sT * z), K)
            D.append((up - dn) / (2 * h * S))
            vu, vd = v * (1 + h), v * (1 - h)
            up = df * payoff(kind, S * math.exp((r - q - vu * vu / 2) * T + vu * sT * z), K)
            dn = df * payoff(kind, S * math.exp((r - q - vd * vd / 2) * T + vd * sT * z), K)
            V.append((up - dn) / (2 * h * v))
    p, pse = mean_se(P)
    d, dse = mean_se(D)
    vg, vse = mean_se(V)
    return {"price": p, "price_se": pse, "delta": d, "delta_se": dse, "vega": vg, "vega_se": vse}, D


def N(x):
    return 0.5 * math.erfc(-x / math.sqrt(2))


def closed(inp):
    S, K, T, r, q, v = (inp[k] for k in ("spot", "strike", "expiry_years", "rate", "dividend_yield", "vol"))
    d1 = (math.log(S / K) + (r - q + v * v / 2) * T) / (v * math.sqrt(T))
    d2 = d1 - v * math.sqrt(T)
    phi = math.exp(-d2 * d2 / 2) / math.sqrt(2 * math.pi)
    return {"price": math.exp(-r * T) * N(d2), "delta": math.exp(-r * T) * phi / (S * v * math.sqrt(T))}


def main():
    s = Suite("mcgreeks_g", "specifications/06-risk/mc-greeks.md", G)
    base = dict(spot=100.0, strike=100.0, expiry_years=1.0, rate=0.03, dividend_yield=0.01, vol=0.2, paths=10000,
                seed="20261109")
    rows = []
    for kind in ("CALL", "PUT", "DIGITAL_CALL"):
        for meth in ("PATHWISE", "LIKELIHOOD_RATIO", "BUMP"):
            if meth == "PATHWISE" and kind == "DIGITAL_CALL":
                rows.append(dict(base, payoff=kind, method=meth, smoothing_width=1.0))
            elif meth == "BUMP":
                rows.append(dict(base, payoff=kind, method=meth, bump_relative=0.01))
            else:
                rows.append(dict(base, payoff=kind, method=meth))
    rows.append(dict(base, payoff="CALL", method="PATHWISE", strike=120.0, expiry_years=0.25, vol=0.35, seed="7"))
    rows.append(dict(base, payoff="DIGITAL_CALL", method="LIKELIHOOD_RATIO", strike=90.0, expiry_years=2.0, seed="42"))
    rows.append(dict(base, payoff="PUT", method="BUMP", bump_relative=0.001, rate=-0.005, seed="1", paths=2))
    for inp in rows:
        out, _ = greeks(inp)
        s.add(OP, inp, out, cls="common_rng", verified=["python-float64-replica", "core.rng"],
              tags=["q9", inp["method"].lower(), inp["payoff"].lower()],
              description=f"{inp['payoff']} {inp['method']} {inp['paths']} paths seed {inp['seed']}")
    e = dict(base, payoff="CALL", method="PATHWISE")
    errs = [(dict(e, paths=1), "E_INPUT", "paths = 1 (no standard error)"),
            (dict(e, payoff="DIGITAL_CALL"), "E_INPUT", "pathwise digital without smoothing_width"),
            (dict(e, smoothing_width=1.0), "E_INPUT", "smoothing_width on a call"),
            (dict(e, payoff="DIGITAL_CALL", smoothing_width=0.0), "E_DOMAIN", "smoothing_width = 0"),
            (dict(e, method="BUMP"), "E_INPUT", "bump without bump_relative"),
            (dict(e, method="BUMP", bump_relative=1.0), "E_DOMAIN", "bump_relative = 1"),
            (dict(e, method="ADJOINT"), "E_INPUT", "unknown method"),
            (dict(e, seed="-1"), "E_SCHEMA", "seed not a u64 string"),
            (dict(e, vol=0.0), "E_DOMAIN", "vol = 0")]
    for inp, code, d in errs:
        s.add(OP, inp, error=code, cls="date_and_convention", tags=["invalid", "q9"], description=d)
    for c in s.cases:
        c["tags"].append("synthetic")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_g"
    s.write()
    common.GOLDEN = keep
    # Acceptance, ruling G-10: digital call delta, 100,000 paths, seed 20261109
    acc = dict(spot=100.0, strike=100.0, expiry_years=1.0, rate=0.03, dividend_yield=0.0, vol=0.2, paths=100000,
               seed="20261109", payoff="DIGITAL_CALL")
    zs = normals(20261109, 100000)
    pw, _ = greeks(dict(acc, method="PATHWISE", smoothing_width=1.0), zs)
    bp, _ = greeks(dict(acc, method="BUMP", bump_relative=0.01), zs)
    lr, _ = greeks(dict(acc, method="LIKELIHOOD_RATIO"), zs)
    cf = closed(acc)
    var_pw, var_b = pw["delta_se"] ** 2 * 100000, bp["delta_se"] ** 2 * 100000
    z_lr = (lr["delta"] - cf["delta"]) / lr["delta_se"]
    note(f"Q9 acceptance: closed delta {cf['delta']:.6f}; pathwise smoothed {pw['delta']:.6f} (var {var_pw:.5f}); "
         f"bump {bp['delta']:.6f} (var {var_b:.5f}); LR {lr['delta']:.6f} +- {lr['delta_se']:.6f}, z = {z_lr:+.2f}")
    assert var_pw < var_b, "Q9: smoothed pathwise variance not below bump"
    assert abs(z_lr) <= 3, "Q9: LR delta not within 3 SE"
    (HERE.parent / "Q9_ACCEPTANCE.json").write_text(json.dumps(
        {"closed_delta": cf["delta"], "pathwise_smoothed": pw, "bump": bp, "likelihood_ratio": lr,
         "per_path_variance": {"pathwise_smoothed": var_pw, "bump": var_b}, "lr_z": z_lr, "paths": 100000,
         "seed": 20261109, "smoothing_width": 1.0, "bump_relative": 0.01}, indent=1) + chr(10), encoding="utf-8")


if __name__ == "__main__":
    main()
