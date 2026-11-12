"""Exact-date Monte Carlo reference for discretely monitored barriers (R6-2). Oracle only; no build implements it.

Draws: core.rng (specifications/01-core/rng.md, xoshiro256** seeded by splitmix64), vectorised over K independent
streams: stream k is the seeded generator jumped k times (rng.md `jump`), and pair p uses stream p mod K, its draws taken
in date order. Uniforms `((x >> 12) + 0.5) 2^-52` as rng.md; normals by scipy `ndtri` (the exact inverse, not AS 241:
this is a reference, not a common-draw replay). GBM is sampled exactly at the n = floor(m T + 0.5) monitoring dates
T/n, ..., T, so there is no time-step error. Antithetic pairs (z, -z); the standard error is that of the pair means.
"""
import math

import numpy as np
from scipy.special import ndtri

from .rng import Xo

MASK = np.uint64(0xFFFFFFFFFFFFFFFF)


def _rotl(x, k):
    return (x << np.uint64(k)) | (x >> np.uint64(64 - k))


class VecXo:
    def __init__(self, seed, streams):
        g = Xo(seed=seed)
        st = []
        for _ in range(streams):
            st.append(list(g.s))
            g.jump()
        a = np.array(st, dtype=np.uint64).T  # shape (4, K)
        self.s0, self.s1, self.s2, self.s3 = (a[i].copy() for i in range(4))

    def next(self):
        with np.errstate(over="ignore"):
            r = _rotl(self.s1 * np.uint64(5), 7) * np.uint64(9)
        t = self.s1 << np.uint64(17)
        self.s2 ^= self.s0
        self.s3 ^= self.s1
        self.s1 ^= self.s2
        self.s0 ^= self.s3
        self.s2 ^= t
        self.s3 = _rotl(self.s3, 45)
        return r

    def uniform(self):
        return ((self.next() >> np.uint64(12)).astype(np.float64) + 0.5) * 2.0 ** -52


def n_dates(m, T):
    return math.floor(m * T + 0.5)


def price(inp, pairs, seed=20261112, streams=8192):
    """Returns (price, standard error, paths). Knock-out for *_OUT; *_IN by in-out parity on the same paths."""
    m, T = inp["monitoring_per_year"], inp["expiry_years"]
    n = n_dates(m, T)
    dt = T / n
    v, r, q = inp["vol"], inp["rate"], inp["dividend_yield"]
    S, K, H, reb = inp["spot"], inp["strike"], inp["barrier"], inp.get("rebate", 0.0)
    assert reb == 0.0, "rebate rows are a convention (G-8), not an MC target"
    down = inp["barrier_type"].startswith("DOWN")
    out = inp["barrier_type"].endswith("OUT")
    call = inp["option_type"] == "CALL"
    drift, sd = (r - q - v * v / 2) * dt, v * math.sqrt(dt)
    lnH = math.log(H)
    disc = math.exp(-r * T)
    g = VecXo(seed, streams)
    sums = np.zeros(2)
    done = 0
    while done < pairs:
        k = min(streams, pairs - done)
        x1 = np.full(k, math.log(S))
        x2 = x1.copy()
        hit1 = np.zeros(k, bool)
        hit2 = np.zeros(k, bool)
        for _ in range(n):
            z = ndtri(g.uniform()[:k])
            x1 += drift + sd * z
            x2 += drift - sd * z
            if down:
                hit1 |= x1 <= lnH
                hit2 |= x2 <= lnH
            else:
                hit1 |= x1 >= lnH
                hit2 |= x2 >= lnH
        pay = []
        for x, hit in ((x1, hit1), (x2, hit2)):
            ST = np.exp(x)
            van = np.maximum(ST - K, 0.0) if call else np.maximum(K - ST, 0.0)
            pay.append(np.where(hit, 0.0, van) if out else np.where(hit, van, 0.0))
        pm = disc * (pay[0] + pay[1]) / 2
        sums += (pm.sum(), (pm * pm).sum())
        done += k
    mean = sums[0] / pairs
    var = (sums[1] - pairs * mean * mean) / (pairs - 1)
    return mean, math.sqrt(max(var, 0.0) / pairs), 2 * pairs
