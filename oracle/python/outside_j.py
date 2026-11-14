"""Stage J wave 1 outside-library checks (J-19, R6-13 outside share). Reads the committed goldens; never writes them.

Each check runs a well-known open-source library on the golden's inputs and compares every compared output at the
golden's own tolerance class (conformance/tolerances/policy.yaml: simple_analytic 1e-12 abs + 1e-10 rel, per_unit
1e-10 abs + 1e-8 rel, date_and_convention exact). A case passes only if every compared output passes. An output
that is plain arithmetic on the inputs or on library outputs (for example 1/sqrt(years), a drawdown of the library's
equity curve) is marked `"via": "arithmetic"`; a case with any such output is classed `library-primitive`, a case
whose outputs all come from the library object is `library-object`. Cases the libraries do not cover are listed
with the reason and are not counted. Disagreements are reported, goldens are not changed
(program/WAVE1_ORACLE_NOTES.md).

Libraries (separate venv, not the uv oracle env; pinned in requirements-outside-j.txt):
  hmmlearn      Viterbi decoding (GaussianHMM; BaseHMM with given per-observation emission log-likelihoods)
  timeseriescv  CombPurgedKFoldCV(n_test_splits=1) purge on (pred_times, eval_times) = (t0, t1)
  scikit-learn  KFold (plain contiguous k-fold, the t1 = t0, no-embargo case)
  skfolio       CombinatorialPurgedCV n_splits and n_test_paths
  statsmodels   NormalIndPower(ratio=0) one-sample power solver (mds, years_required)
  vectorbt      Portfolio.from_orders, target amounts, per-order fees and fixed fees (backtester)

    python -m venv <venv outside the repo> && <venv>/Scripts/pip install -r requirements-outside-j.txt
    cd oracle/python && <venv>/Scripts/python -W ignore outside_j.py      writes oracle/OUTSIDE_J.json
"""
import importlib.metadata as md
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GOLD = ROOT / "datasets" / "golden" / "stage_j"
OUT = ROOT / "oracle" / "OUTSIDE_J.json"
TOL = {"simple_analytic": (1e-12, 1e-10), "per_unit": (1e-10, 1e-8), "date_and_convention": None}


def ver(p):
    return f"{p} {md.version(p)}"


def load(suite):
    return [c for c in json.loads((GOLD / f"{suite}.json").read_text(encoding="utf-8"))["cases"]
            if c["expected"]["status"] == "ok"]


def cls(case, out):
    return case.get("output_classes", {}).get(out, case["tolerance_class"])


def check(case, out, outside, via="library"):
    g = case["expected"]["outputs"][out]
    t = TOL[cls(case, out)]
    if t is None:
        ok = json.loads(json.dumps(g)) == json.loads(json.dumps(outside))
        return {"output": out, "golden": g, "outside": outside, "tolerance": "exact", "via": via, "pass": bool(ok)}
    ga, oa = np.atleast_1d(np.asarray(g, float)), np.atleast_1d(np.asarray(outside, float))
    if ga.shape != oa.shape:
        return {"output": out, "golden": g, "outside": outside, "tolerance": "shape", "via": via, "pass": False}
    tol = t[0] + t[1] * np.abs(ga)
    gap = np.abs(ga - oa)
    return {"output": out, "golden": g if ga.size > 1 else float(ga[0]), "outside": oa.tolist() if ga.size > 1 else float(oa[0]),
            "max_gap": float(gap.max()), "tolerance": f"{t[0]:g} abs + {t[1]:g} rel", "via": via,
            "pass": bool((gap <= tol).all())}


def entry(case, checks, note=""):
    ok = all(c["pass"] for c in checks) and set(c["output"] for c in checks) == set(case["expected"]["outputs"])
    klass = "library-primitive" if any(c["via"] == "arithmetic" for c in checks) else "library-object"
    e = {"case_id": case["case_id"], "class": klass, "checks": checks, "pass": ok}
    if note:
        e["note"] = note
    return e


# ---------------------------------------------------------------- regime_j: hmmlearn Viterbi
def regime():
    from hmmlearn import hmm
    from hmmlearn.base import BaseHMM

    class GivenEmission(BaseHMM):
        """hmmlearn's own Viterbi on a per-observation emission table: observation t is the integer t."""

        def __init__(self, table, **kw):
            super().__init__(n_components=table.shape[1], **kw)
            self.table = table

        def _compute_log_likelihood(self, X):
            with np.errstate(divide="ignore"):
                return np.log(self.table[X[:, 0].astype(int)])

        def _get_n_fit_scalars_per_param(self):
            return {}

        def _init(self, X, lengths=None):
            pass

    rows = []
    for c in load("regime_j"):
        i = c["inputs"]
        if "emission" in i:
            em = np.asarray(i["emission"], float)
            m = GivenEmission(em, implementation="log")
            X = np.arange(len(em)).reshape(-1, 1)
        else:
            m = hmm.GaussianHMM(n_components=len(i["means"]), covariance_type="diag", implementation="log")
            m.means_ = np.asarray(i["means"], float).reshape(-1, 1)
            m.covars_ = (np.asarray(i["sds"], float) ** 2).reshape(-1, 1)
            m.n_features = 1
            X = np.asarray(i["observations"], float).reshape(-1, 1)
        m.startprob_ = np.asarray(i["initial"], float)
        m.transmat_ = np.asarray(i["transition"], float)
        lp, states = m.decode(X, algorithm="viterbi")
        rows.append(entry(c, [check(c, "states", [int(s) for s in states]), check(c, "log_probability", float(lp))]))
    return {"library": f"{ver('hmmlearn')} decode(algorithm='viterbi'), implementation='log' (GaussianHMM diag; BaseHMM "
                       "with the given emission table as log-likelihoods)", "cases": rows}


# ---------------------------------------------------------------- purgedcv_j: timeseriescv, scikit-learn, skfolio
def purgedcv():
    from sklearn.model_selection import KFold
    from skfolio.model_selection import CombinatorialPurgedCV
    from timeseriescv.cross_validation import CombPurgedKFoldCV

    rows, skipped = [], []
    epoch = pd.Timestamp("2000-01-01")
    for c in load("purgedcv_j"):
        i = c["inputs"]
        if c["operation"] == "research.cv.cpcv_paths":
            try:
                cv = CombinatorialPurgedCV(n_folds=i["n_groups"], n_test_folds=i["n_test_groups"])
            except ValueError as exc:
                skipped.append({"case_id": c["case_id"], "reason": f"skfolio refuses the inputs: {exc}"})
                continue
            rows.append(entry(c, [check(c, "n_splits", int(cv.n_splits)), check(c, "n_paths", int(cv.n_test_paths))]))
            continue
        n, k = len(i["t0"]), i["n_splits"]
        h = math.floor(i.get("embargo_pct", 0.0) * n)
        t0 = pd.Series([epoch + pd.Timedelta(seconds=float(x)) for x in i["t0"]])
        t1 = pd.Series([epoch + pd.Timedelta(seconds=float(x)) for x in i["t1"]])
        X = pd.DataFrame({"x": np.zeros(n)})
        lib = {}
        for tr, te in CombPurgedKFoldCV(n_splits=k, n_test_splits=1).split(X, pred_times=t0, eval_times=t1):
            lib[int(te[0])] = ([int(x) for x in te], [int(x) for x in tr])
        folds = [{"test": lib[a][0], "train": lib[a][1]} for a in sorted(lib)]
        note = ""
        if h:
            # The spec's embargo is an index count after the block (J-8); timeseriescv's is a time span. The library
            # check covers the case only if the h embargoed indices are already purged by the library.
            extra = [sorted(set(range(f["test"][-1] + 1, min(f["test"][-1] + 1 + h, n))) & set(f["train"])) for f in folds]
            if any(extra):
                skipped.append({"case_id": c["case_id"], "reason": f"index embargo h = {h} drops indices the library "
                                "purge keeps; timeseriescv has no index-count embargo, so the case is not library-checked",
                                "library_purge_agrees_before_embargo": None})
                g = c["expected"]["outputs"]["folds"]
                # Library purge minus the spec's index embargo, against the golden train set, fold by fold.
                agree = [set(f["train"]) - set(range(f["test"][-1] + 1, f["test"][-1] + 1 + h)) == set(gg["train"])
                         and f["test"] == gg["test"] for f, gg in zip(folds, g)]
                if not all(agree):
                    skipped[-1]["folds_disagreeing_after_embargo"] = [j for j, a in enumerate(agree) if not a]
                agree = all(agree)
                skipped[-1]["library_purge_agrees_before_embargo"] = bool(agree)
                continue
            note = "every embargoed index is already purged by the library (label overlap), so the embargo adds nothing"
        chk = [check(c, "folds", folds), check(c, "embargo_count", h, via="arithmetic")]
        if h == 0 and i["t0"] == i["t1"]:
            kf = [{"test": [int(x) for x in te], "train": [int(x) for x in tr]} for tr, te in KFold(n_splits=k).split(X)]
            chk.append(dict(check(c, "folds", kf), output="folds", source=ver("scikit-learn") + " KFold"))
        rows.append(entry(c, chk, note))
    return {"library": f"{ver('timeseriescv')} CombPurgedKFoldCV(n_test_splits=1, embargo_td=0) purge; "
                       f"{ver('scikit-learn')} KFold; {ver('skfolio')} CombinatorialPurgedCV.n_splits/.n_test_paths; "
                       "embargo_count = floor(pct n) is arithmetic", "cases": rows, "not_checked": skipped}


# ---------------------------------------------------------------- rstats_j: statsmodels power
def rstats():
    from scipy.optimize import brentq
    from statsmodels.stats.power import NormalIndPower

    rows, skipped = [], []
    for c in load("rstats_j"):
        i = c["inputs"]
        if c["operation"] != "research.stats.power":
            skipped.append({"case_id": c["case_id"], "reason": {
                "research.stats.dsr": "no free library implements the DSR (SR0 Gumbel approximation); scipy.stats.norm "
                                      "around the spec formula is a reimplementation (D6), not counted",
                "research.stats.psr": "no free library implements the PSR from moments; scipy.stats.norm around the "
                                      "spec formula is a reimplementation (D6), not counted",
                "research.stats.pbo": "no installable free CSCV/PBO library (pypbo is not on PyPI); not counted"}[c["operation"]]})
            continue
        yrs, a, p = i["years"], i.get("alpha", 0.05), i.get("power", 0.8)
        pw = NormalIndPower()

        def solve(**kw):
            # statsmodels' own solve_power stops at brentq's default xtol (about 1e-7 here); refine its answer with
            # brentq at full precision on the same statsmodels power function.
            free = [k for k, v in kw.items() if v is None][0]
            x0 = pw.solve_power(alpha=a, power=p, ratio=0, alternative="larger", **kw)
            f = lambda x: pw.power(**{**kw, free: x}, alpha=a, ratio=0, alternative="larger") - p
            return brentq(f, x0 * 0.9, x0 * 1.1, xtol=1e-15, rtol=1e-15, maxiter=200)

        mds = solve(effect_size=None, nobs1=yrs)
        chk = [check(c, "mds", mds), check(c, "z_sum", mds * math.sqrt(yrs), via="arithmetic"),
               check(c, "se_at_zero", 1 / math.sqrt(yrs), via="arithmetic")]
        if "sr_target" in i:
            s = i["sr_target"]
            n_req = solve(effect_size=s, nobs1=None)
            chk += [check(c, "years_required", n_req), check(c, "se_at_target", math.sqrt((1 + s * s / 2) / yrs), via="arithmetic")]
        rows.append(entry(c, chk))
    return {"library": f"{ver('statsmodels')} NormalIndPower(ratio=0, alternative='larger').solve_power, refined by "
                       "scipy brentq (xtol 1e-15) on the same statsmodels power function); z_sum = mds sqrt(years) and the standard errors are arithmetic",
            "cases": rows, "not_checked": skipped}


# ---------------------------------------------------------------- backtest_j: vectorbt
def backtest():
    import vectorbt as vbt

    rows = []
    for c in load("backtest_j"):
        i = c["inputs"]
        p = np.asarray(i["prices"], float)
        tg = np.asarray(i["targets"], float)
        lag, m = i.get("lag", 1), i.get("multiplier", 1.0)
        hs, cu, fx = i.get("half_spread_bps", 0.0), i.get("commission_per_unit", 0.0), i.get("fixed_per_trade", 0.0)
        T = len(p)
        q = np.zeros(T)
        q[lag:] = tg[:T - lag]
        close = pd.Series(p)
        # One contract = m units of the price; per-order fee as a fraction of order value |d| m p.
        fees = pd.Series(hs / 1e4 + cu / (m * p))
        init = 1e9
        pf = vbt.Portfolio.from_orders(close, size=pd.Series(q * m), size_type="targetamount", fees=fees,
                                       fixed_fees=fx, init_cash=init, cash_sharing=False, freq="1D")
        rec = pf.orders.records_readable
        pos = pf.assets().to_numpy() / m
        # Equity from the library's own cash flows and asset value, not value - init_cash (a 1e9 cash base would
        # round at 1e-7 and hide the comparison).
        eq = pf.cash_flow().cumsum().to_numpy() + pf.asset_value().to_numpy()
        net = np.diff(np.concatenate([[0.0], eq]))
        cost = np.zeros(T)
        trades = np.zeros(T)
        turn = 0.0
        for _, r in rec.iterrows():
            t = int(r["Timestamp"]) if not isinstance(r["Timestamp"], pd.Timestamp) else close.index.get_loc(r["Timestamp"])
            cost[t] += r["Fees"]
            sgn = 1.0 if str(r["Side"]) == "Buy" else -1.0
            trades[t] += sgn * r["Size"] / m
            turn += r["Size"] * r["Price"]
        gross = net + cost
        spread = np.abs(trades) * p * hs / 1e4 * m
        comm = np.abs(trades) * cu
        peak = np.maximum.accumulate(np.maximum(eq, 0.0))
        lib_n = len(rec)
        chk = [check(c, "positions", pos.tolist()), check(c, "trades", trades.tolist()),
               check(c, "pnl_gross", gross.tolist()), check(c, "cost", cost.tolist()),
               check(c, "pnl_net", net.tolist()), check(c, "equity", eq.tolist()),
               check(c, "total_gross", float(gross.sum())), check(c, "total_net", float(eq[-1])),
               check(c, "total_spread_cost", float(spread.sum()), via="arithmetic"),
               check(c, "total_commission", float(comm.sum()), via="arithmetic"),
               check(c, "total_fixed_cost", float(lib_n * fx)),
               check(c, "turnover", turn), check(c, "trade_count", lib_n),
               check(c, "max_drawdown", float((peak - eq).max()), via="arithmetic")]
        rows.append(entry(c, chk))
    return {"library": f"{ver('vectorbt')} Portfolio.from_orders (size_type targetamount on lag-shifted targets, "
                       "fees = half_spread/1e4 + commission/(m p) per order, fixed_fees, init_cash 1e9); spread and "
                       "commission split and the drawdown are arithmetic on the library's orders and equity",
            "cases": rows}


def main():
    suites = {}
    for name, fn in (("regime_j", regime), ("purgedcv_j", purgedcv), ("rstats_j", rstats), ("backtest_j", backtest)):
        try:
            suites[name] = fn()
        except ImportError as exc:
            suites[name] = {"library": None, "cases": [], "error": f"library not installed: {exc}"}
    for s in suites.values():
        s["counted"] = sum(1 for c in s["cases"] if c["pass"])
        s["failed"] = [c["case_id"] for c in s["cases"] if not c["pass"]]
    total = sum(len(json.loads((GOLD / f"{s}.json").read_text(encoding="utf-8"))["cases"]) for s in suites)
    value = sum(len(load(s)) for s in suites)
    doc = {"rule": "per case; a case counts only if every compared output is within the golden's own tolerance class "
                   "from the named library (R6-13; arithmetic outputs make the case library-primitive)",
           "summary": {"counted": sum(s["counted"] for s in suites.values()), "value_checked_cases": value,
                       "all_cases": total},
           "suites": suites}
    OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    for k, s in suites.items():
        print(k, s["counted"], "of", len(load(k)), "failed:", s["failed"], s.get("error", ""))
    print(doc["summary"])


if __name__ == "__main__":
    main()
