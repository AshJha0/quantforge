"""R3-02 dummy-controlled check (amendment 4, R3-02 item 8; C9: reported only, never deciding).

POST-HOC, REPORT-ONLY. Computed on 2026-11-14 after the one-shot holdout run; it changes no verdict.

The frozen trial (`research/r3/params/R3-02.json`) is re-computed with the month-end business days
(which include every quarter end and year end) removed from the funding inputs:

* the trailing funding mean `r_t` is the mean of the last 20 fixings dated on or before `t` that are not
  month-end days;
* in `F`, a removed day's fixing is replaced by the last kept fixing before it, so its calendar days
  still accrue ("accrual kept").

Bill rates, signal dates, costs and statistics are as in `r3_runner.bill_month_returns`. Holdout files
are read only through `r3_data.load_holdout`, so the `r3_runner.holdout_guard` applies unchanged.
  python research/r3_02_dummy.py <freeze_commit> <data_dir>
"""
from __future__ import annotations

import itertools
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3_data as d
import r3_in_sample as s
import r3_runner as r

Arr = npt.NDArray[np.float64]
ROOT = Path(__file__).resolve().parent
COL = {"SOFR": 1, "TGCR": 2, "BGCR": 3}


def month_end_mask(days: Sequence[date]) -> npt.NDArray[np.bool_]:
    """True on the last business day of each calendar month in `days` (the final day counts only if
    the next calendar day is in another month, since later data are not part of the series)."""
    out = np.zeros(len(days), dtype=bool)
    for i, x in enumerate(days):
        nxt = days[i + 1] if i + 1 < len(days) else date.fromordinal(x.toordinal() + 1)
        out[i] = nxt.month != x.month
    return out


def controlled_funding(funding: Arr, drop: npt.NDArray[np.bool_], trail: int = 20) -> tuple[Arr, Arr]:
    """(trailing mean over kept fixings, fixings for F with dropped days carrying the last kept value)."""
    kept_idx = np.flatnonzero(~drop)
    trailing = np.full(len(funding), np.nan)
    carried = funding.copy()
    last = np.nan
    for i in range(len(funding)):
        if drop[i]:
            carried[i] = last
        else:
            last = funding[i]
        k = kept_idx[kept_idx <= i]
        if len(k) >= trail:
            trailing[i] = funding[k[-trail:]].mean()
    return trailing, carried


def controlled_returns(days: Sequence[date], bill_ce: Arr, funding: Arr, window: int, k: float,
                       cost_mult: float = 1.0) -> tuple[list[date], Arr]:
    """`r3_runner.bill_month_returns` with the funding inputs replaced by `controlled_funding`."""
    mm = np.array([bill_ce[i] * 360 / r.bill_basis(x) for i, x in enumerate(days)])
    trailing, carried = controlled_funding(funding, month_end_mask(days))
    sp = (mm - trailing) * 1e4
    out_d: list[date] = []
    out: list[float] = []
    for e, x in itertools.pairwise(r.month_starts(days)):
        hist = sp[:e]
        hist = hist[~np.isnan(hist)]
        if len(hist) < window:
            continue
        w = hist[-window:]
        sd = w.std(ddof=1)
        z = (w[-1] - w.mean()) / sd if sd > 0 else 0.0
        pos = 1.0 if z > k else (-1.0 if z < -k else 0.0)
        ret = 0.0
        if pos:
            n = np.array([(days[i + 1] - days[i]).days for i in range(e, x)], dtype=float)
            h = int(n.sum())
            p0 = 1 / (1 + mm[e] * 91 / 360)
            p1 = 1 / (1 + mm[x] * (91 - h) / 360)
            f = float(np.prod(1 + carried[e:x] * n / 360) - 1)
            cost = 0.5e-4 * 91 / 360 * p0 * p0 + 0.0002 * h / 360
            ret = pos * ((p1 - p0) / p0 - f) - cost_mult * cost
        out_d.append(days[x])
        out.append(ret)
    return out_d, np.array(out)


def describe(net: Arr) -> dict[str, Any]:
    sd = float(net.std(ddof=1)) if len(net) > 1 else 0.0
    return {"n": len(net), "months_in_position": int(np.count_nonzero(net)),
            "mean_net_1x": float(net.mean()) if len(net) else None,
            "sharpe_net_1x": round(float(net.mean() / sd * np.sqrt(12)), 4) if sd > 0 else None}


def main(freeze: str, data: Path) -> dict[str, Any]:
    p = json.loads((ROOT / "r3" / "params" / "R3-02.json").read_text())["params"]
    log = ROOT / "r3" / "data_log.csv"
    a = d.load_in_sample("R3-02", data=data, log=log)
    b = d.load_holdout("R3-02", freeze, data=data, log=log)
    days, v = s.r302_inputs({key: {**a.get(key, {}), **b.get(key, {})} for key in set(a) | set(b)})
    col = COL[p["funding"]]
    res: dict[str, Any] = {"label": "post-hoc, report-only (amendment 4 R3-02 item 8, C9); no verdict effect",
                           "params": p}
    lo, hi = r.HOLDOUT["R3-02"]
    for name, fn in (("as_run", r.bill_month_returns), ("dummy_controlled", controlled_returns)):
        ex, net = fn(days, v[:, 0], v[:, col], p["L"], p["k"])
        h = np.array([lo <= x <= hi for x in ex])
        ins = np.array([x <= r.IN_SAMPLE_END["R3-02"] for x in ex])
        res[name] = {"in_sample": describe(net[ins]), "holdout": describe(net[h])}
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], Path(sys.argv[2])), indent=1))
