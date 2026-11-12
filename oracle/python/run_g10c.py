"""Ruling R6-5.3 (G-10c), registered in specifications/r6-rulings.md before this script first ran.

Matched comparison of the smoothed pathwise delta and the central bump for the G-10 digital: each method at its own
best width, judged on mean squared error, not variance alone (G-10b compared variances at a bump 10 times smaller than
the smoothing width, so it passed by construction; review finding 17).

    cd oracle/python && uv run python -W ignore run_g10c.py
"""
import json
import math
from pathlib import Path

from scipy.integrate import quad
from scipy.stats import norm

from qf_oracle.rng import Xo, ppnd16

S = K = 100.0
T, r, q, v = 1.0, 0.03, 0.0, 0.2
N, SEED = 60000, 20261110
EPS_GRID = (0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0)            # smoothing half-width in price units
H_GRID = (0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05)  # relative central bump on S
DF, SD, MU = math.exp(-r * T), v * math.sqrt(T), math.log(S) + (r - q - v * v / 2) * T


def zs(stream):
    g = Xo(seed=SEED, stream=stream)
    return [ppnd16(((g.next() >> 12) + 0.5) * 2.0 ** -52) for _ in range(N)]


def true_delta():
    return DF * norm.pdf((MU - math.log(K)) / SD) / (S * SD)


def mean_pw(eps):
    f = lambda x: math.exp(x) / S * norm.pdf((x - MU) / SD) / SD  # noqa: E731
    return DF / (2 * eps) * quad(f, math.log(K - eps), math.log(K + eps), epsabs=1e-15)[0]


def mean_bump(h):
    price = lambda s0: DF * norm.cdf((math.log(s0 / K) + (r - q - v * v / 2) * T) / SD)  # noqa: E731
    return (price(S * (1 + h)) - price(S * (1 - h))) / (2 * h * S)


def samples(method, w, z):
    out = []
    for x in z:
        g = math.exp((r - q - v * v / 2) * T + SD * x)
        if method == "pathwise":
            ST = S * g
            out.append(DF * ((1 / (2 * w)) if abs(ST - K) < w else 0.0) * ST / S)
        else:
            out.append(DF * ((1.0 if S * (1 + w) * g > K else 0.0) - (1.0 if S * (1 - w) * g > K else 0.0)) / (2 * w * S))
    return out


def var_kurt(xs):
    n = len(xs)
    m = math.fsum(xs) / n
    s2 = math.fsum((x - m) ** 2 for x in xs) / (n - 1)
    return m, s2, math.fsum((x - m) ** 4 for x in xs) / n / (s2 * s2)


def main():
    d = true_delta()
    res = {"ruling": "R6-5.3 (G-10c)", "n": N, "seed": SEED, "true_delta": d, "pilot": {}, "final": {}}
    best = {}
    for method, grid, stream, mean in (("pathwise", EPS_GRID, 2, mean_pw), ("bump", H_GRID, 3, mean_bump)):
        z = zs(stream)
        rows = []
        for w in grid:
            _, s2, _ = var_kurt(samples(method, w, z))
            rows.append({"width": w, "bias": mean(w) - d, "variance": s2, "mse": (mean(w) - d) ** 2 + s2 / N})
        res["pilot"][method] = rows
        best[method] = min(rows, key=lambda x: x["mse"])["width"]
    for method, stream, mean in (("pathwise", 4, mean_pw), ("bump", 5, mean_bump)):
        m, s2, k = var_kurt(samples(method, best[method], zs(stream)))
        b = mean(best[method]) - d
        res["final"][method] = {"width": best[method], "estimate": m, "bias_exact": b, "variance": s2, "kurtosis": k,
                                "mse": b * b + s2 / N, "se_ln_variance": math.sqrt((k - 1) / N)}
    p, b = res["final"]["pathwise"], res["final"]["bump"]
    ratio = p["mse"] / b["mse"]
    # interval: the variance terms carry the sampling error; bias terms are exact
    lo_hi = []
    for sgn in (-1, 1):
        vp = p["variance"] * math.exp(sgn * 1.96 * p["se_ln_variance"])
        vb = b["variance"] * math.exp(-sgn * 1.96 * b["se_ln_variance"])
        lo_hi.append((p["bias_exact"] ** 2 + vp / N) / (b["bias_exact"] ** 2 + vb / N))
    res["mse_ratio_pathwise_over_bump"] = ratio
    res["ratio_interval_95"] = lo_hi
    res["outcome"] = "smoothed pathwise lower MSE" if lo_hi[1] < 1 else ("bump lower MSE" if lo_hi[0] > 1 else "inconclusive")
    print(json.dumps(res, indent=1))
    (Path(__file__).resolve().parent.parent / "G10C_RESULT.json").write_text(json.dumps(res, indent=1) + chr(10), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
