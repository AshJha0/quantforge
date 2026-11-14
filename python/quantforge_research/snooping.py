"""White's Reality Check against a benchmark (plan 14.6 J-4).

Plain idea: after trying many strategies, is the best one's edge over the benchmark (1/N or buy-and-hold) larger than
the best of many useless strategies would show by luck? The Reality Check resamples the excess-return series with the
stationary bootstrap, recentres each strategy's mean, and counts how often the resampled maximum reaches the observed
one.

Sources: H. White, "A reality check for data snooping", Econometrica 68(5), 2000, 1097-1126 (statistic and bootstrap
p-value); D. N. Politis, J. P. Romano, "The stationary bootstrap", JASA 89(428), 1994, 1303-1313 (block lengths
geometric with mean 1/q). Neither opened in this session; evidence class: paper, recalled. Size on simulated nulls is
checked in tests/test_quantforge_research.py. Not a CLI operation (gap G14): the bootstrap draws would need a shared
random stream across four languages.
"""
from __future__ import annotations

import numpy as np


def stationary_indices(n: int, q: float, rng: np.random.Generator) -> np.ndarray:
    idx = np.empty(n, dtype=np.int64)
    idx[0] = rng.integers(n)
    new = rng.random(n) < q
    starts = rng.integers(n, size=n)
    for t in range(1, n):
        idx[t] = starts[t] if new[t] else (idx[t - 1] + 1) % n
    return idx


def reality_check(strategy_returns: np.ndarray, benchmark_returns: np.ndarray, *, n_boot: int = 1000,
                  mean_block: float = 10.0, seed: int = 0) -> dict[str, float]:
    """strategy_returns: T x K; benchmark_returns: length T. Returns sqrt(T) times the best mean excess and its p-value."""
    X = np.asarray(strategy_returns, dtype=float)
    b = np.asarray(benchmark_returns, dtype=float)
    if X.ndim != 2 or b.shape != (X.shape[0],) or X.shape[0] < 2 or n_boot < 1 or mean_block < 1:
        raise ValueError("strategy_returns must be T x K with T >= 2, benchmark length T, n_boot >= 1, mean_block >= 1")
    f = X - b[:, None]
    T = f.shape[0]
    fbar = f.mean(axis=0)
    stat = float(np.sqrt(T) * fbar.max())
    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(n_boot):
        fb = f[stationary_indices(T, 1.0 / mean_block, rng)].mean(axis=0)
        exceed += float(np.sqrt(T) * (fb - fbar).max()) >= stat
    return {"statistic": stat, "p_value": exceed / n_boot, "best": int(fbar.argmax())}
