"""Stage J wave 1 research operations (specifications/11-research/, rulings J-1 to J-19):
the backtester, purged k-fold and CPCV counts, Viterbi regime labels, and the research
statistics PSR, DSR, PBO by CSCV and the Sharpe power calculation."""
import math
from collections.abc import Sequence
from itertools import accumulate, combinations
from typing import Any

from .errors import QfError
from .finite import guard
from .rng import ppnd16

EULER_GAMMA = 0.5772156649015329
ROW_SUM_TOLERANCE = 1e-9


def _phi(x: float) -> float:
    """The standard normal CDF, through erfc so that both tails keep full relative precision."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


# --- Backtester (backtester.md, J-2 to J-6) ---------------------------------------------------

def _positions(targets: Sequence[float], lag: int) -> list[float]:
    return [0.0] * lag + [float(q) for q in targets[:len(targets) - lag]]


def _event(prices: Sequence[float], q: Sequence[float], spread: float, commission: float,
           fixed: float, m: float) -> tuple[list[float], ...]:
    """The normative event loop: one bar at a time, holding P&L on the position before the trade."""
    trades, gross, spreads, comms, fixeds, net, equity = [], [], [], [], [], [], []
    previous, running = 0.0, 0.0
    for t, p in enumerate(prices):
        d = q[t] - previous
        g = previous * (p - prices[t - 1]) * m if t >= 1 else 0.0
        s, c, f = abs(d) * p * spread * m, abs(d) * commission, fixed if d != 0 else 0.0
        n = g - (s + c + f)
        running += n
        trades.append(d)
        gross.append(g)
        spreads.append(s)
        comms.append(c)
        fixeds.append(f)
        net.append(n)
        equity.append(running)
        previous = q[t]
    return trades, gross, spreads, comms, fixeds, net, equity


def _vector(prices: Sequence[float], q: Sequence[float], spread: float, commission: float,
            fixed: float, m: float) -> tuple[list[float], ...]:
    """The same quantities as whole arrays: shift, difference, element-wise product, cumsum."""
    before = [0.0, *q[:-1]]
    moves = [0.0] + [b - a for a, b in zip(prices, prices[1:], strict=False)]
    trades = [a - b for a, b in zip(q, before, strict=True)]
    gross = [h * dp * m for h, dp in zip(before, moves, strict=True)]
    spreads = [abs(d) * p * spread * m for d, p in zip(trades, prices, strict=True)]
    comms = [abs(d) * commission for d in trades]
    fixeds = [fixed if d != 0 else 0.0 for d in trades]
    net = [g - (s + c + f) for g, s, c, f in zip(gross, spreads, comms, fixeds, strict=True)]
    return trades, gross, spreads, comms, fixeds, net, list(accumulate(net))


def _z(values: Sequence[float]) -> list[float]:
    return [v + 0.0 for v in values]  # F-3: no negative zero in the outputs


def backtest_run(prices: Sequence[float], targets: Sequence[float], lag: int = 1,
                 half_spread_bps: float = 0.0, commission_per_unit: float = 0.0,
                 fixed_per_trade: float = 0.0, multiplier: float = 1.0,
                 engine: str = "EVENT") -> dict[str, Any]:
    """`research.backtest.run`: hold `targets` from `lag` bars later, pay spread, commission and
    fixed costs on every change, and book each bar's move on the position held before its trade."""
    t_count = len(prices)
    if len(targets) != t_count or t_count < 2 or not 0 <= lag < t_count:
        raise QfError("E_INPUT", "targets must match prices, T >= 2 and 0 <= lag < T", "targets")
    if any(p <= 0 for p in prices):
        raise QfError("E_DOMAIN", "prices must be positive", "prices")
    if half_spread_bps < 0 or commission_per_unit < 0 or fixed_per_trade < 0:
        raise QfError("E_DOMAIN", "cost inputs must not be negative", "half_spread_bps")
    if multiplier <= 0:
        raise QfError("E_DOMAIN", "multiplier must be positive", "multiplier")
    q = _positions(targets, lag)
    run = _event if engine == "EVENT" else _vector
    trades, gross, spreads, comms, fixeds, net, equity = run(
        prices, q, half_spread_bps / 1e4, commission_per_unit, fixed_per_trade, multiplier)
    peak, drawdown = 0.0, 0.0
    for e in equity:
        peak = max(peak, e)
        drawdown = max(drawdown, peak - e)
    totals = {"total_gross": math.fsum(gross), "total_spread_cost": math.fsum(spreads),
              "total_commission": math.fsum(comms), "total_fixed_cost": math.fsum(fixeds),
              "total_net": math.fsum(net)}
    return {
        "positions": _z(q), "trades": _z(trades), "pnl_gross": _z(gross),
        "cost": _z(s + c + f for s, c, f in zip(spreads, comms, fixeds, strict=True)),
        "pnl_net": _z(net), "equity": _z(equity),
        **{k: v + 0.0 for k, v in totals.items()},
        "turnover": math.fsum(abs(d) * p * multiplier for d, p in zip(trades, prices, strict=True))
        + 0.0,
        "trade_count": sum(1 for d in trades if d != 0),
        "max_drawdown": drawdown + 0.0,
    }


# --- Purged CV (purged-cv.md, J-7 to J-9) ------------------------------------------------------

def cv_purged_kfold(t0: Sequence[float], t1: Sequence[float], n_splits: int,
                    embargo_pct: float = 0.0) -> dict[str, Any]:
    """`research.cv.purged_kfold`: contiguous folds in `array_split` order; training labels that
    overlap the test span (closed intervals) are purged, and `floor(pct n)` indices after each test
    block are embargoed."""
    n = len(t0)
    if len(t1) != n:
        raise QfError("E_INPUT", "t0 and t1 differ in length", "t1")
    if not 2 <= n_splits <= n:
        raise QfError("E_INPUT", "n_splits must lie in [2, n]", "n_splits")
    if any(b < a for a, b in zip(t0, t0[1:], strict=False)):
        raise QfError("E_INPUT", "t0 must be non-decreasing", "t0")
    if any(e < s for s, e in zip(t0, t1, strict=True)):
        raise QfError("E_DOMAIN", "a label ends before it starts", "t1")
    if not 0 <= embargo_pct < 1:
        raise QfError("E_DOMAIN", "embargo_pct must lie in [0, 1)", "embargo_pct")
    h = math.floor(embargo_pct * n)
    size, extra = divmod(n, n_splits)
    folds, a = [], 0
    for f in range(n_splits):
        b = a + size + (1 if f < extra else 0)
        lo, hi = t0[a], max(t1[a:b])
        dropped = set(range(b, min(b + h, n)))
        train = [j for j in range(n) if not a <= j < b and j not in dropped
                 and not (t0[j] <= hi and t1[j] >= lo)]
        folds.append({"test": list(range(a, b)), "train": train})
        a = b
    return {"folds": folds, "embargo_count": h}


def cv_cpcv_paths(n_groups: int, n_test_groups: int) -> dict[str, int]:
    """`research.cv.cpcv_paths`: `C(N, k)` splits and `k C(N, k) / N` backtest paths."""
    if not 2 <= n_groups or not 1 <= n_test_groups < n_groups:
        raise QfError("E_INPUT", "need N >= 2 and 1 <= k < N", "n_test_groups")
    splits = math.comb(n_groups, n_test_groups)
    return {"n_splits": splits, "n_paths": n_test_groups * splits // n_groups}


# --- Viterbi (regimes.md, J-10 to J-12) --------------------------------------------------------

def _log(x: float) -> float:
    return math.log(x) if x > 0 else -math.inf


def _check_probabilities(rows: Sequence[Sequence[float]], field: str) -> None:
    for row in rows:
        if any(p < 0 for p in row):
            raise QfError("E_DOMAIN", "a probability is negative", field)
        if abs(math.fsum(row) - 1.0) > ROW_SUM_TOLERANCE:
            raise QfError("E_DOMAIN", "probabilities do not sum to 1", field)


def regime_viterbi(initial: Sequence[float], transition: Sequence[Sequence[float]],
                   emission: Sequence[Sequence[float]] | None = None,
                   observations: Sequence[float] | None = None,
                   means: Sequence[float] | None = None,
                   sds: Sequence[float] | None = None) -> dict[str, Any]:
    """`research.regime.viterbi`: the most likely state path, in logs, smallest index on ties."""
    k = len(initial)
    gaussian = (observations, means, sds)
    if (emission is not None and any(g is not None for g in gaussian)) or (
            emission is None and any(g is None for g in gaussian)):
        raise QfError("E_INPUT", "give exactly one of emission or observations/means/sds",
                      "emission")
    if k < 1 or len(transition) != k or any(len(r) != k for r in transition):
        raise QfError("E_INPUT", "transition must be K x K", "transition")
    if emission is not None:
        if not emission or any(len(r) != k for r in emission):
            raise QfError("E_INPUT", "emission must be T x K with T >= 1", "emission")
    elif not observations or len(means or ()) != k or len(sds or ()) != k:
        raise QfError("E_INPUT", "observations must be non-empty and means, sds of length K",
                      "observations")
    _check_probabilities([initial], "initial")
    _check_probabilities(transition, "transition")
    if emission is not None:
        if any(e < 0 for r in emission for e in r):
            raise QfError("E_DOMAIN", "an emission is negative", "emission")
        log_e = [[_log(e) for e in r] for r in emission]
    else:
        assert observations is not None and means is not None and sds is not None
        if any(s <= 0 for s in sds):
            raise QfError("E_DOMAIN", "sds must be positive", "sds")
        c = math.log(2 * math.pi) / 2
        log_e = [[-math.log(s) - c - (y - mu) ** 2 / (2 * s * s) for mu, s in
                  zip(means, sds, strict=True)] for y in observations]
    log_a = [[_log(a) for a in r] for r in transition]
    delta = [_log(p) + e for p, e in zip(initial, log_e[0], strict=True)]
    pointers: list[list[int]] = []
    for row in log_e[1:]:
        back, nxt = [], []
        for j in range(k):
            best = max(range(k), key=lambda i: (delta[i] + log_a[i][j], -i))
            back.append(best)
            nxt.append(delta[best] + log_a[best][j] + row[j])
        pointers.append(back)
        delta = nxt
    end = max(range(k), key=lambda j: (delta[j], -j))
    if delta[end] == -math.inf:
        raise QfError("E_DOMAIN", "every path has probability zero", "emission")
    states = [end]
    for back in reversed(pointers):
        states.append(back[states[-1]])
    states.reverse()
    return {"states": states, "log_probability": delta[end] + 0.0}


# --- Research statistics (research-statistics.md, J-13 to J-18) --------------------------------

def _sharpe_z(sr: float, n_obs: int, skew: float, kurtosis: float, benchmark: float) -> float:
    v = 1 - skew * sr + (kurtosis - 1) / 4 * sr * sr
    if v <= 0:
        raise QfError("E_DOMAIN", "the Sharpe variance term is not positive (J-14)", "skew")
    return (sr - benchmark) * math.sqrt(n_obs - 1) / math.sqrt(v)


def _check_moments(n_obs: int, kurtosis: float) -> None:
    if n_obs < 2:
        raise QfError("E_INPUT", "n_obs must be at least 2", "n_obs")
    if kurtosis < 1:
        raise QfError("E_DOMAIN", "kurtosis must be at least 1 (J-14)", "kurtosis")


def stats_psr(sr: float, n_obs: int, skew: float = 0.0, kurtosis: float = 3.0,
              sr_benchmark: float = 0.0) -> dict[str, float]:
    """`research.stats.psr`: the probability that the true per-period Sharpe exceeds the
    benchmark [BLdP12]."""
    _check_moments(n_obs, kurtosis)
    z = _sharpe_z(sr, n_obs, skew, kurtosis, sr_benchmark)
    return {"z": z + 0.0, "psr": _phi(z)}


def stats_dsr(sr: float, n_obs: int, n_trials: int, sr_variance: float, skew: float = 0.0,
              kurtosis: float = 3.0) -> dict[str, float]:
    """`research.stats.dsr`: PSR against the expected best Sharpe of `n_trials` useless trials
    [BLdP14]; one trial gives a benchmark of 0 (J-13)."""
    if n_trials < 1:
        raise QfError("E_INPUT", "n_trials must be at least 1", "n_trials")
    _check_moments(n_obs, kurtosis)
    if sr_variance < 0:
        raise QfError("E_DOMAIN", "sr_variance must not be negative", "sr_variance")
    sr0 = 0.0
    if n_trials > 1:
        sr0 = math.sqrt(sr_variance) * ((1 - EULER_GAMMA) * ppnd16(1 - 1 / n_trials)
                                        + EULER_GAMMA * ppnd16(1 - 1 / (n_trials * math.e)))
    z = _sharpe_z(sr, n_obs, skew, kurtosis, sr0)
    return {"sr0": sr0 + 0.0, "z": z + 0.0, "dsr": _phi(z)}


def stats_power(years: float, alpha: float = 0.05, power: float = 0.8,
                sr_target: float | None = None) -> dict[str, float]:
    """`research.stats.power`: minimum detectable annualised Sharpe (one-sided, iid) and, for a
    target Sharpe, the years needed and the [Lo02] standard error there."""
    if years <= 0 or not 0 < alpha < power < 1:
        raise QfError("E_DOMAIN", "need years > 0 and 0 < alpha < power < 1", "alpha")
    if sr_target is not None and sr_target <= 0:
        raise QfError("E_DOMAIN", "sr_target must be positive", "sr_target")
    z_sum = ppnd16(1 - alpha) + ppnd16(power)
    out = {"z_sum": z_sum, "mds": z_sum / math.sqrt(years), "se_at_zero": 1 / math.sqrt(years)}
    if sr_target is not None:
        out["years_required"] = (z_sum / sr_target) ** 2
        out["se_at_target"] = math.sqrt((1 + sr_target * sr_target / 2) / years)
    return out


def _metric(columns: Sequence[Sequence[float]], metric: str) -> list[float]:
    out = []
    for col in columns:
        mean = math.fsum(col) / len(col)
        if metric == "MEAN":
            out.append(mean)
        else:
            sd = math.sqrt(math.fsum((x - mean) ** 2 for x in col) / (len(col) - 1))
            out.append(mean / sd)
    return out


def stats_pbo(performance: Sequence[Sequence[float]], n_partitions: int,
              metric: str = "SHARPE") -> dict[str, Any]:
    """`research.stats.pbo`: probability of backtest overfitting by CSCV [BBLdPZ17]; winners by
    lowest index, out-of-sample ranks averaged with 1 = worst (J-16)."""
    t, s = len(performance), n_partitions
    n = len(performance[0]) if performance else 0
    if any(len(r) != n for r in performance) or n < 2:
        raise QfError("E_INPUT", "performance must be T x N with N >= 2", "performance")
    if s % 2 or s < 2 or t % s or t // s < 2:
        raise QfError("E_INPUT", "S must be even, divide T and leave 2 rows per block (J-15)",
                      "n_partitions")
    size = t // s
    blocks = [performance[b * size:(b + 1) * size] for b in range(s)]
    if metric == "SHARPE" and any(len(set(col)) == 1 for blk in blocks for col in zip(*blk)):
        raise QfError("E_DOMAIN", "a block has zero standard deviation (J-17)", "performance")
    logits = []
    for chosen in combinations(range(s), s // 2):
        train = [r for b in chosen for r in blocks[b]]
        test = [r for b in range(s) if b not in chosen for r in blocks[b]]
        is_metric = _metric(list(zip(*train)), metric)
        best = max(range(n), key=lambda j: (is_metric[j], -j))
        oos = _metric(list(zip(*test)), metric)
        x = oos[best]
        rank = sum(1 for v in oos if v < x) + (sum(1 for v in oos if v == x) + 1) / 2
        omega = rank / (n + 1)
        logits.append(math.log(omega / (1 - omega)))
    return {"pbo": sum(1 for v in logits if v <= 0) / len(logits),
            "logits": [v + 0.0 for v in logits], "n_combinations": len(logits)}


guard(globals())
