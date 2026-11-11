"""Ruling G-10b (registered in specifications/stage-g-rulings.md, commit ea11299, before this script ran).

    cd oracle/python && uv run python -W ignore run_g10b.py
"""
import json
import math
from pathlib import Path

from qf_oracle.rng import Xo, ppnd16

S = K = 100.0
T, r, q, v = 1.0, 0.03, 0.0, 0.2
EPS, H, N, SEED = 1.0, 0.001, 60000, 20261110


def zs(stream):
    g = Xo(seed=SEED, stream=stream)
    return [ppnd16(((g.next() >> 12) + 0.5) * 2.0 ** -52) for _ in range(N)]


def moments(xs):
    n = len(xs)
    m = math.fsum(xs) / n
    s2 = math.fsum((x - m) ** 2 for x in xs) / (n - 1)
    m4 = math.fsum((x - m) ** 4 for x in xs) / n
    return m, s2, m4 / (s2 * s2)


def main():
    df, sT, drift = math.exp(-r * T), math.sqrt(T), (r - q - v * v / 2) * T
    pw = []
    for z in zs(0):
        ST = S * math.exp(drift + v * sT * z)
        pw.append(df * ((1 / (2 * EPS)) if abs(ST - K) < EPS else 0.0) * ST / S)
    bp = []
    for z in zs(1):
        g = math.exp(drift + v * sT * z)
        up = 1.0 if S * (1 + H) * g > K else 0.0
        dn = 1.0 if S * (1 - H) * g > K else 0.0
        bp.append(df * (up - dn) / (2 * H * S))
    m_pw, s_pw, k_pw = moments(pw)
    m_b, s_b, k_b = moments(bp)
    se = math.sqrt((k_pw - 1) / N + (k_b - 1) / N)
    Z = (math.log(s_b) - math.log(s_pw)) / se
    lr = math.log(s_pw / s_b)
    res = {"ruling": "G-10b", "n": N, "seed": SEED, "streams": {"pathwise": 0, "bump": 1},
           "pathwise": {"delta": m_pw, "variance": s_pw, "kurtosis": k_pw},
           "bump": {"delta": m_b, "variance": s_b, "kurtosis": k_b},
           "variance_ratio": s_pw / s_b, "ratio_ci95": [math.exp(lr - 1.96 * se), math.exp(lr + 1.96 * se)],
           "Z": Z, "critical": 1.6449, "outcome": "pass" if Z > 1.6449 else "fail"}
    print(json.dumps(res, indent=1))
    (Path(__file__).resolve().parent.parent / "G10B_RESULT.json").write_text(json.dumps(res, indent=1) + chr(10), encoding="utf-8")


if __name__ == "__main__":
    main()
