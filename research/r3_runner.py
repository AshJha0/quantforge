"""R3 study runner (preregs R3-01/02/03 with amendments 1 to 4). numpy and quantforge_core only.

Pure functions take arrays already loaded and aligned (amendment 4 C10); `holdout_guard` refuses any
date past a study's in-sample end unless the in-sample freeze commit and a committed
`research/holdout_runs.csv` line for the study exist (common rules; amendment 3 rule 1).
This module never writes to `holdout_runs.csv`.
"""
from __future__ import annotations

import csv
import hashlib
import io
import math
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "python"))
sys.path.insert(0, str(ROOT / "power"))
import itertools

import r3_power
from quantforge_core.bonds import Bond, price_from_yield
from quantforge_core.research import backtest_run, stats_pbo

Arr = NDArray[np.float64]
SEED = 20261114
E_MAX_24 = 1.9798
FAMILY_N = 24
IN_SAMPLE_END = {"R3-01": date(2012, 12, 31), "R3-02": date(2022, 12, 30),
                 "R3-03": date(2015, 12, 31)}
HOLDOUT = {"R3-01": (date(2013, 1, 2), date(2026, 10, 30)),
           "R3-02": (date(2023, 1, 3), date(2026, 10, 30)),
           "R3-03": (date(2016, 1, 4), date(2026, 10, 30))}


# --- guard -------------------------------------------------------------------------------------

class HoldoutRefused(RuntimeError):
    pass


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                          check=True).stdout


@dataclass(frozen=True)
class GuardInputs:
    study: str
    last_date: date
    freeze_commit: str | None
    script_sha256: str


def holdout_guard(g: GuardInputs, git: Callable[..., str] = _git) -> None:
    """Pass silently for in-sample ranges; otherwise require (a) the freeze commit to exist and be
    an ancestor of HEAD, and (b) a line for the study in the COMMITTED `research/holdout_runs.csv`
    naming this script's SHA-256 and that freeze commit."""
    if g.last_date <= IN_SAMPLE_END[g.study]:
        return
    if not g.freeze_commit:
        raise HoldoutRefused(f"{g.study}: date {g.last_date} past in-sample end, no freeze commit")
    try:
        git("merge-base", "--is-ancestor", g.freeze_commit, "HEAD")
        committed = git("show", "HEAD:research/holdout_runs.csv")
    except subprocess.CalledProcessError as e:
        raise HoldoutRefused(f"{g.study}: freeze commit or committed run log missing") from e
    for row in csv.DictReader(io.StringIO(committed)):
        if (row.get("study") == g.study and row.get("script_sha256") == g.script_sha256
                and (row.get("commit") or "").startswith(g.freeze_commit[:7])):
            return
    raise HoldoutRefused(f"{g.study}: no committed holdout_runs.csv line for this script and commit")


def script_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


# --- statistics (amendment 4 C5, C6, C8) -------------------------------------------------------

def norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def lo(x: Arr, q: int, lags: int) -> tuple[float, float]:
    sr, se = r3_power.lo_sharpe(np.asarray(x, dtype=float)[None, :], q, lags)
    return float(sr[0]), float(se[0])


def boot(x: Arr, q: int = 12, draws: int = 10_000, seed: int = SEED) -> tuple[float, float]:
    sr, se = r3_power.boot_sharpe(np.asarray(x, dtype=float)[None, :], q, 3,
                                  np.random.default_rng(seed), draws=draws, chunk=1)
    return float(sr[0]), float(se[0])


def decision(sr: float, se: float) -> dict[str, float]:
    sr0 = se * E_MAX_24
    return {"sr": sr, "se": se, "sr0": sr0, "p": 1 - norm_cdf((sr - sr0) / se),
            "p2": 1 - norm_cdf(sr / se)}


def thirds_positive(x: Arr) -> bool:
    return bool(r3_power.thirds_positive(np.asarray(x, dtype=float)[None, :])[0])


def holm(p: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    out = {k: False for k in p}
    for j, (k, v) in enumerate(sorted(p.items(), key=lambda kv: kv[1])):
        if v > alpha / (len(p) - j):
            break
        out[k] = True
    return out


def pbo(columns: Sequence[Arr]) -> float | None:
    """CSCV, 16 blocks, earliest rows dropped to a multiple of 16; None = not computable."""
    if len(columns) < 2:
        return None
    m = np.column_stack(columns)
    m = m[len(m) % 16:]
    try:
        return float(stats_pbo(m.tolist(), 16)["pbo"])
    except Exception:  # noqa: BLE001 - any refusal means "not computable" (C8)
        return None


def select(in_sample_sharpes: Sequence[float]) -> int:
    """Highest in-sample net Sharpe at 1x; ties to the lower trial number (C4)."""
    return max(range(len(in_sample_sharpes)), key=lambda j: (in_sample_sharpes[j], -j))


# --- R3-01 -------------------------------------------------------------------------------------

def par_dv01(y: float, years: int, on: date) -> float:
    """DV01 per unit notional per bp of a par bond (coupon = yield, semi-annual)."""
    b = Bond(maturity=on.replace(year=on.year + years) if not (on.month == 2 and on.day == 29)
             else date(on.year + years, 2, 28), coupon=y, frequency=2)
    r = price_from_yield(b, on, y)
    return float(r["modified_duration"] * r["dirty"] / 100 / 1e4)  # dirty is quoted per 100 face


def zscore(x: Arr, window: int) -> Arr:
    z = np.full(len(x), np.nan)
    for t in range(window - 1, len(x)):
        w = x[t - window + 1:t + 1]
        sd = w.std(ddof=1)
        z[t] = (x[t] - w.mean()) / sd if sd > 0 else 0.0
    return z


def hysteresis(z: Arr, k: float) -> Arr:
    pos, out = 0.0, np.zeros(len(z))
    for t, v in enumerate(z):
        if np.isnan(v):
            pos = 0.0
        elif v > k:
            pos = -1.0
        elif v < -k:
            pos = 1.0
        elif abs(v) < 0.5:
            pos = 0.0
        out[t] = pos
    return out


def fly_returns(fly_bp: Arr, gross: Arr, window: int, k: float,
                cost_mult: float = 1.0) -> dict[str, Arr]:
    """Daily net return per unit gross notional (amendment 4, R3-01 items 1-7). `gross[t]` is G
    at close t (1/D2 + 2/D5 + 1/D10, D per bp)."""
    targets = hysteresis(zscore(fly_bp, window), k)
    bt = backtest_run((1000.0 + fly_bp).tolist(), targets.tolist(), lag=1)
    pos = np.asarray(bt["positions"])
    gross_bp = np.asarray(bt["pnl_gross"])  # pos_{t-1} (f_t - f_{t-1})
    g_prev = np.concatenate([[gross[0]], gross[:-1]])
    ret = gross_bp / g_prev
    trade_cost = 0.25 * 4 * np.abs(np.asarray(bt["trades"])) / gross
    held = np.abs(np.concatenate([[0.0], pos[:-1]]))
    bs = 0.0025 / 252 * held
    return {"position": pos, "gross": ret, "net": ret - cost_mult * (trade_cost + bs)}


# --- R3-02 -------------------------------------------------------------------------------------

def bill_basis(d: date) -> int:
    """366 when a 29 February falls in the year after `d` (amendment 4, R3-02 item 3)."""
    for yr in (d.year, d.year + 1):
        if yr % 4 == 0 and (yr % 100 != 0 or yr % 400 == 0):
            leap = date(yr, 2, 29)
            end = d.replace(year=d.year + 1) if not (d.month == 2 and d.day == 29) \
                else date(d.year + 1, 3, 1)
            if d < leap <= end:
                return 366
    return 365


def month_starts(days: Sequence[date]) -> list[int]:
    return [i for i, d in enumerate(days) if i == 0 or d.month != days[i - 1].month][1:]


def bill_month_returns(days: Sequence[date], bill_ce: Arr, funding: Arr, window: int, k: float,
                       cost_mult: float = 1.0, trail: int = 20) -> tuple[list[date], Arr]:
    """Monthly net returns dated by exit (amendment 4, R3-02 items 1-5). Rates in decimals; one
    entry per aligned business day; `funding[i]` is the fixing dated `days[i]`."""
    mm = np.array([bill_ce[i] * 360 / bill_basis(d) for i, d in enumerate(days)])
    trailing = np.array([funding[max(0, i - trail + 1):i + 1].mean() if i >= trail - 1
                         else np.nan for i in range(len(days))])
    s = (mm - trailing) * 1e4
    starts = month_starts(days)
    out_d: list[date] = []
    out: list[float] = []
    for e, x in itertools.pairwise(starts):
        hist = s[:e]  # values dated <= E-1
        hist = hist[~np.isnan(hist)]
        if len(hist) < window:
            continue
        w = hist[-window:]
        sd = w.std(ddof=1)
        z = (w[-1] - w.mean()) / sd if sd > 0 else 0.0
        pos = 1.0 if z > k else (-1.0 if z < -k else 0.0)
        r = 0.0
        if pos:
            n = np.array([(days[i + 1] - days[i]).days for i in range(e, x)], dtype=float)
            h = int(n.sum())
            p0 = 1 / (1 + mm[e] * 91 / 360)
            p1 = 1 / (1 + mm[x] * (91 - h) / 360)
            f = float(np.prod(1 + funding[e:x] * n / 360) - 1)
            cost = 0.5e-4 * 91 / 360 * p0 * p0 + 0.0002 * h / 360
            r = pos * ((p1 - p0) / p0 - f) - cost_mult * cost
        out_d.append(days[x])
        out.append(r)
    return out_d, np.array(out)


# --- R3-03 -------------------------------------------------------------------------------------

def month_ends(days: Sequence[date]) -> list[int]:
    return [i for i in range(len(days)) if i == len(days) - 1 or days[i + 1].month != days[i].month]


def seasonal_returns(month_end_days: Sequence[date], b_bp: Arr, dn: Arr, dr: Arr,
                     in_sample_end: date, cost_mult: float = 1.0) -> tuple[list[date], Arr]:
    """Monthly net returns of T01 (= T03), dated by month end (amendment 4, R3-03 items 2-5).
    Inputs are month-end values: breakeven in bp, nominal and real par DV01s per bp."""
    d = np.diff(b_bp)
    months = [x.month for x in month_end_days[1:]]
    ins = np.array([x <= in_sample_end for x in month_end_days[1:]])
    mean = {m: float(d[ins & (np.array(months) == m)].mean()) for m in range(1, 13)
            if (ins & (np.array(months) == m)).any()}
    pos = np.array([np.sign(mean.get(m, 0.0)) for m in months])
    scale = dn[:-1] / (1 + dn[:-1] / dr[:-1])  # at the entry close
    prev = np.concatenate([[0.0], pos[:-1]])
    cost = 1.0 * np.abs(pos - prev) / 2 * scale + 0.0025 / 12 * np.abs(pos)
    return list(month_end_days[1:]), pos * d * scale - cost_mult * cost


def summarise(net: Arr, q: int, lags: int | None) -> dict[str, Any]:
    sr, se = lo(net, q, lags) if lags is not None else boot(net)
    return {**decision(sr, se), "thirds_positive": thirds_positive(net), "n": len(net)}
