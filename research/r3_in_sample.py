"""R3 in-sample runs (preregs R3-01/02/03, amendments 1-4): every trial, selection (C4), PBO (C8).

Reads in-sample files only (`r3_data.load_in_sample`); writes `research/r3/in_sample.json`.
  python research/r3_in_sample.py
"""
from __future__ import annotations

import json
import math
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3_data as d
import r3_runner as r
from quantforge_core.errors import QfError

Arr = r.Arr
OUT = Path(__file__).resolve().parent / "r3" / "in_sample.json"
R301_GRID = [(L, k) for L in (60, 120, 250, 500) for k in (1.0, 1.5)]
R302_GRID = [(f, L, k) for f in ("SOFR", "TGCR", "BGCR") for L in (60, 250) for k in (1.0, 2.0)]


def aligned(series: dict[str, d.Series], cols: Sequence[tuple[str, str]]) -> tuple[list[date], Arr]:
    """Business days on which every input is non-missing (C10); values in the order of `cols`."""
    days = sorted(set.intersection(*({x for x, v in series[s].items() if c in v} for s, c in cols)))
    return days, np.array([[series[s][x][c] for s, c in cols] for x in days], dtype=float)


# --- R3-01 -------------------------------------------------------------------------------------

def r301_inputs(series: dict[str, d.Series]) -> tuple[list[date], Arr, Arr, Arr]:
    days, y = aligned(series, [(d.NOMINAL, "2 YR"), (d.NOMINAL, "5 YR"), (d.NOMINAL, "10 YR")])
    fly = (2 * y[:, 1] - y[:, 0] - y[:, 2]) * 100.0
    dv = np.array([[r.par_dv01_closed(y[i, j] / 100, n) for j, n in enumerate((2, 5, 10))]
                   for i in range(len(days))])
    gross = 1 / dv[:, 0] + 2 / dv[:, 1] + 1 / dv[:, 2]
    return days, fly, gross, y


def r301_trials(fly: Arr, gross: Arr, cost_mult: float = 1.0) -> list[Arr]:
    return [r.fly_returns(fly, gross, L, k, cost_mult)["net"] for L, k in R301_GRID]


# --- R3-02 -------------------------------------------------------------------------------------

def r302_inputs(series: dict[str, d.Series]) -> tuple[list[date], Arr]:
    days, v = aligned(series, [(d.BILL, "13 WEEKS COUPON EQUIVALENT"), ("SOFR", "SOFR"),
                               ("TGCR", "TGCR"), ("BGCR", "BGCR")])
    return days, v / 100.0


def r302_trials(days: list[date], v: Arr, cost_mult: float = 1.0) -> list[tuple[list[date], Arr]]:
    col = {"SOFR": 1, "TGCR": 2, "BGCR": 3}
    return [r.bill_month_returns(days, v[:, 0], v[:, col[f]], L, k, cost_mult) for f, L, k in R302_GRID]


def common(trials: list[tuple[list[date], Arr]]) -> tuple[list[date], list[Arr]]:
    """C4: the exit dates of the longest-window trials, the same for every trial."""
    keep = sorted(set.intersection(*(set(t[0]) for t in trials)))
    return keep, [np.array([x for dd, x in zip(*t, strict=True) if dd in set(keep)]) for t in trials]


# --- R3-03 -------------------------------------------------------------------------------------

def r303_inputs(series: dict[str, d.Series]) -> tuple[list[date], Arr, Arr, Arr, Arr]:
    days, v = aligned(series, [(d.NOMINAL, "5 YR"), (d.REAL, "5 YR")])
    ends = [days[i] for i in r.month_ends(days)]
    ve = v[r.month_ends(days)]
    b = (ve[:, 0] - ve[:, 1]) * 100.0
    dn = np.array([r.par_dv01(ve[i, 0] / 100, 5, x) for i, x in enumerate(ends)])
    dr = np.array([r.par_dv01(ve[i, 1] / 100, 5, x) for i, x in enumerate(ends)])
    return ends, b, dn, dr, ve


def _f(x: float) -> float | None:
    return None if math.isnan(x) else round(float(x), 6)


def sharpe_row(net: Arr, q: int, lags: int | None) -> dict[str, Any]:
    sr = r.lo(net, q, lags)[0] if lags is not None else float(net.mean() / net.std(ddof=1) * math.sqrt(q))
    return {"sharpe_net_1x": _f(sr), "n": len(net), "nonzero": int((net != 0).sum())}


def run() -> dict[str, Any]:
    out: dict[str, Any] = {}
    # R3-01
    try:
        out["R3-01"] = r301_run()
    except QfError as e:  # stop, do not improvise (program/R3_NOTES.md)
        out["R3-01"] = {"stopped": f"quantforge_core QfError: {e}"}
    r302_run(out)
    r303_run(out)
    return out


def r301_run() -> dict[str, Any]:
    days, fly, gross, _ = r301_inputs(d.load_in_sample("R3-01"))
    start = 500 - 1  # C4: first date with the 500-day window full
    nets = [x[start:] for x in r301_trials(fly, gross)]
    nets2 = [x[start:] for x in r301_trials(fly, gross, 2.0)]
    rows = [{"trial": f"R3-01-T{j + 1:02d}", "L": L, "k": k, **sharpe_row(nets[j], 252, 20),
             "sharpe_net_2x": _f(r.lo(nets2[j], 252, 20)[0])} for j, (L, k) in enumerate(R301_GRID)]
    sel = r.select([x["sharpe_net_1x"] for x in rows])
    return {"business_days": len(days), "first_day": str(days[0]), "last_day": str(days[-1]),
                    "common_sample_returns": len(nets[0]), "trials": rows, "selected": rows[sel]["trial"],
                    "pbo": r.pbo(nets)}


def r302_run(out: dict[str, Any]) -> None:
    days2, v = r302_inputs(d.load_in_sample("R3-02"))
    keep, nets = common(r302_trials(days2, v))
    _, nets2 = common(r302_trials(days2, v, 2.0))
    rows = [{"trial": f"R3-02-T{j + 1:02d}", "funding": f, "L": L, "k": k,
             **sharpe_row(nets[j], 12, None), "sharpe_net_2x": _f(sharpe_row(nets2[j], 12, None)["sharpe_net_1x"])}
            for j, (f, L, k) in enumerate(R302_GRID)]
    shs = [x["sharpe_net_1x"] for x in rows]
    out["R3-02"] = {"business_days": len(days2), "first_day": str(days2[0]), "last_day": str(days2[-1]),
                    "common_sample_months": len(keep), "first_exit": str(keep[0]), "last_exit": str(keep[-1]),
                    "trials": rows, "pbo": r.pbo(nets),
                    "selected": None if any(s is None for s in shs) else rows[r.select(shs)]["trial"]}


def r303_run(out: dict[str, Any]) -> None:
    ends, b, dn, dr, _ = r303_inputs(d.load_in_sample("R3-03"))
    _, net = r.seasonal_returns(ends, b, dn, dr, r.IN_SAMPLE_END["R3-03"])
    _, net2 = r.seasonal_returns(ends, b, dn, dr, r.IN_SAMPLE_END["R3-03"], 2.0)
    out["R3-03"] = {"month_ends": len(ends), "first_month_end": str(ends[0]), "last_month_end": str(ends[-1]),
                    "trials": [{"trial": "R3-03-T01 (= T03)", **sharpe_row(net, 12, 3),
                                "sharpe_net_2x": _f(r.lo(net2, 12, 3)[0])}],
                    "not_run": ["R3-03-T02", "R3-03-T04"], "selected": "R3-03-T01", "pbo": None,
                    "pbo_note": "not applicable: one distinct trial (amendment 4 C8)"}


if __name__ == "__main__":
    res = run()
    OUT.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1))
