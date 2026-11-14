"""R3 one-shot holdout runs (preregs R3-01/02/03, amendments 1-5): the frozen trial of each study on its
holdout, Holm across the three, written to `research/r3/holdout.json`.

Refuses to read any holdout file unless `r3_runner.holdout_guard` passes (freeze commit an ancestor of HEAD and
a committed `research/holdout_runs.csv` line naming this runner's SHA-256 and that commit).
  python research/r3_holdout.py <freeze_commit>
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3_data as d
import r3_in_sample as s
import r3_runner as r

ROOT = Path(__file__).resolve().parent
PARAMS = ROOT / "r3" / "params"
OUT = ROOT / "r3" / "holdout.json"


def merged(study: str, freeze: str) -> dict[str, d.Series]:
    a, b = d.load_in_sample(study), d.load_holdout(study, freeze)
    return {k: {**a.get(k, {}), **b.get(k, {})} for k in set(a) | set(b)}


def in_holdout(study: str, x: date) -> bool:
    lo, hi = r.HOLDOUT[study]
    return lo <= x <= hi


def corr(a: np.ndarray, b: np.ndarray) -> float | None:
    ok = ~(np.isnan(a) | np.isnan(b))
    if ok.sum() < 3 or a[ok].std() == 0 or b[ok].std() == 0:
        return None
    return round(float(np.corrcoef(a[ok], b[ok])[0, 1]), 4)


def stats(net: np.ndarray, net2: np.ndarray, q: int, lags: int | None) -> dict[str, Any]:
    row = r.summarise(net, q, lags)
    sr2 = r.summarise(net2, q, lags)["sr"]
    return {**{k: (round(v, 6) if isinstance(v, float) else v) for k, v in row.items()},
            "dsr": round(1 - row["p"], 6), "sharpe_net_2x": round(sr2, 6), "mean_net_1x": float(net.mean())}


def r301(freeze: str, p: dict[str, Any]) -> dict[str, Any]:
    days, fly, gross, y = s.r301_inputs(merged("R3-01", freeze))
    run1 = r.fly_returns(fly, gross, p["L"], p["k"])
    net2 = r.fly_returns(fly, gross, p["L"], p["k"], 2.0)["net"]
    h = np.array([in_holdout("R3-01", x) for x in days])
    out = stats(run1["net"][h], net2[h], 252, 20)
    # Reported only (amendment 4 item 8): PCs of in-sample daily yield changes, loadings frozen at in-sample end.
    dy = np.diff(y, axis=0)
    ins = np.array([x <= r.IN_SAMPLE_END["R3-01"] for x in days[1:]])
    _, vec = np.linalg.eigh(np.cov(dy[ins].T))
    scores = dy @ vec[:, ::-1]
    hh = h[1:]
    ret = run1["net"][1:][hh]
    dv = np.array([[r.par_dv01_closed(y[i, j] / 100, n) for j, n in enumerate((2, 5, 10))]
                   for i in range(len(days))])
    carry = (y[:, 0] / 100 / dv[:, 0] - 2 * y[:, 1] / 100 / dv[:, 1] + y[:, 2] / 100 / dv[:, 2]) / (252 * gross)
    pos_prev = np.concatenate([[0.0], run1["position"][:-1]])
    out["reported_correlations"] = {
        **{f"pc{j + 1}": corr(ret, scores[hh, j]) for j in range(3)},
        "carry": corr(ret, (pos_prev * np.concatenate([[np.nan], carry[:-1]]))[1:][hh])}
    return out


def r302(freeze: str, p: dict[str, Any]) -> dict[str, Any]:
    days, v = s.r302_inputs(merged("R3-02", freeze))
    col = {"SOFR": 1, "TGCR": 2, "BGCR": 3}[p["funding"]]
    ex, net = r.bill_month_returns(days, v[:, 0], v[:, col], p["L"], p["k"])
    _, net2 = r.bill_month_returns(days, v[:, 0], v[:, col], p["L"], p["k"], 2.0)
    h = np.array([in_holdout("R3-02", x) for x in ex])
    out = stats(net[h], net2[h], 12, None)
    out["first_exit"], out["last_exit"] = str(np.array(ex)[h][0]), str(np.array(ex)[h][-1])
    out["dummy_controlled_check"] = "not computed in this lane (reported-only; amendment 4 item 8)"
    return out


def r303(freeze: str) -> dict[str, Any]:
    ser = merged("R3-03", freeze)
    ends, b, dn, dr, _ = s.r303_inputs(ser)
    me, net = r.seasonal_returns(ends, b, dn, dr, r.IN_SAMPLE_END["R3-03"])
    _, net2 = r.seasonal_returns(ends, b, dn, dr, r.IN_SAMPLE_END["R3-03"], 2.0)
    # C2: the first holdout return runs from 2015-12-31 to the January 2016 month end.
    h = np.array([r.IN_SAMPLE_END["R3-03"] < x <= r.HOLDOUT["R3-03"][1] for x in me])
    out = stats(net[h], net2[h], 12, 3)
    # Reported only (item 6): 5Y-10Y breakeven slope roll-down, 12-month momentum sign of b5.
    days10, v10 = s.aligned(ser, [(d.NOMINAL, "10 YR"), (d.REAL, "10 YR")])
    b10 = dict(zip(days10, (v10[:, 0] - v10[:, 1]) * 100.0, strict=True))
    roll = np.array([(b10.get(x, np.nan) - b[i]) / 60 for i, x in enumerate(ends[:-1])])
    mom = np.array([np.sign(b[i] - b[i - 12]) if i >= 12 else np.nan for i in range(len(ends) - 1)])
    out["reported_correlations"] = {"rolldown": corr(net[h], roll[h]), "momentum_12m": corr(net[h], mom[h])}
    return out


def main(freeze: str) -> dict[str, Any]:
    prm = {k: json.loads((PARAMS / f"{k}.json").read_text(encoding="utf-8")) for k in ("R3-01", "R3-02", "R3-03")}
    res = {"R3-01": r301(freeze, prm["R3-01"]["params"]), "R3-02": r302(freeze, prm["R3-02"]["params"]),
           "R3-03": r303(freeze)}
    holm = r.holm({k: v["p"] for k, v in res.items()})
    ranks = sorted(res, key=lambda k: res[k]["p"])
    sec_rank = sorted(res, key=lambda k: res[k]["p2"])
    for k, v in res.items():
        v["trial"] = prm[k]["selected"]
        v["holm_level"] = round(0.05 / (3 - ranks.index(k)), 6)
        v["holm_adjusted_p"] = round(min(1.0, max((3 - ranks.index(j)) * res[j]["p"]
                                                  for j in ranks[:ranks.index(k) + 1])), 6)
        v["cond1_holm_rejects"] = holm[k]
        v["cond2_positive_at_2x"] = v["sharpe_net_2x"] > 0
        v["cond3_thirds"] = v["thirds_positive"]
        v["pass"] = bool(holm[k] and v["cond2_positive_at_2x"] and v["cond3_thirds"])
        lvl = 0.05 / (3 - sec_rank.index(k))
        v["secondary"] = "below the Holm level" if v["p2"] <= lvl else "not below"
    res["R3-02"]["label"] = "exploratory (in-sample PBO not computable, amendment 4 C8)"
    res["R3-03"]["cpi_arm"] = "not run (T02, T04; amendment 4 item 1)"
    res["family"] = {"N": r.FAMILY_N, "distinct_strategies_run": 21, "freeze_commit": freeze,
                     "runner_sha256": r.script_sha256()}
    return res


if __name__ == "__main__":
    out = main(sys.argv[1])
    OUT.write_text(json.dumps(out, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1, default=str))
