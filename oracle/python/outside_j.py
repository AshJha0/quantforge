"""Stage J outside-library checks, waves 1 to 3 (J-19, J-W2-15, R6-13 outside share). Reads the committed goldens; never writes them.

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
Wave 2 (J-W2-15, ruling J-W2-16; program/WAVE2_ORACLE_NOTES.md):
  daqp          dual active-set QP for mean-variance (PyPortfolioOpt max_quadratic_utility on Clarabel as a second
                solver, reported per case, not counted)
  cvxpy+clarabel  risk parity as min 1/2 y'Sy - b'log y (exponential cone), w = y / sum y
  autograd      Euler marginal risk as the derivative of sigma(w)
  scikit-learn  LedoitWolf (same scaled-identity estimator and 1/T convention as J-W2-7)
  PyPortfolioOpt  BlackLittermanModel bl_returns, bl_cov
  hmmlearn      GaussianHMM.fit (Baum-Welch) from the given start values, its own stop rule
  esbt_j        no free library computes the Acerbi-Szekely Z2; not counted
Wave 3 (R6-13): numpy interp, pandas loc (scen_j); numpy interp, scipy CubicSpline/Pchip (interpbt_j);
  scipy ks_2samp exact, numpy quantile inverted_cdf + scipy rel_entr (drift_j KS, PSI). CUSUM and
  Page-Hinkley have no library with the same conventions; not counted.

    python -m venv <venv outside the repo> && <venv>/Scripts/pip install -r requirements-outside-j.txt
    cd oracle/python && <venv>/Scripts/python -W ignore outside_j.py      writes oracle/OUTSIDE_J.json
    ... outside_j.py --wave 2      runs wave 2 only; the other wave's suites are kept from the committed file
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
TOL = {"simple_analytic": (1e-12, 1e-10), "per_unit": (1e-10, 1e-8), "root_finding": (1e-10, 1e-10),
       "likelihood_sum": (1e-9, 1e-10), "interpolation": (1e-10, 1e-8), "statistics": (1e-11, 1e-10),
       "date_and_convention": None}


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
    lim = case.get("tolerance_limit")
    if lim and out not in case.get("output_classes", {}) and t is not None:
        # As conformance/runner/runner.py: a per-case tolerance_limit replaces the base class for outputs without
        # their own class (baumwelch_j parameters, J-W2-9).
        t = (lim.get("absolute", t[0]), lim.get("relative", t[1]))
    if t is None:
        ok = json.loads(json.dumps(g)) == json.loads(json.dumps(outside))
        return {"output": out, "golden": g, "outside": outside, "tolerance": "exact", "via": via, "pass": bool(ok)}
    ga, oa = np.atleast_1d(np.asarray(g, float)), np.atleast_1d(np.asarray(outside, float))
    if ga.shape != oa.shape:
        return {"output": out, "golden": g, "outside": outside, "tolerance": "shape", "via": via, "pass": False}
    tol = t[0] + t[1] * np.abs(ga)
    gap = np.abs(ga - oa)
    sc = ga.size == 1 and np.ndim(g) <= 1  # scalars and length-1 lists print as numbers (wave 1 form); matrices stay nested
    return {"output": out, "golden": float(ga.ravel()[0]) if sc else g, "outside": float(oa.ravel()[0]) if sc else oa.tolist(),
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


# ================================================================ wave 2 (J-W2-15, ruling J-W2-16)
def _at_bound(w, lo, up, eps=1e-9):
    return [1 if abs(x - u) <= eps else (-1 if abs(x - l) <= eps else 0) for x, l, u in zip(w, lo, up)]


# ---------------------------------------------------------------- optim_j: DAQP, PyPortfolioOpt/Clarabel, cvxpy, autograd
def optim():
    import cvxpy as cp
    import daqp
    import autograd.numpy as anp
    from autograd import grad
    from pypfopt import EfficientFrontier

    rows, skipped = [], []
    for c in load("optim_j"):
        i, op = c["inputs"], c["operation"]
        S = np.asarray(i["covariance"], float)
        n = len(S)
        if op == "research.portfolio.mean_variance":
            mu, g = np.asarray(i["expected_returns"], float), i["risk_aversion"]
            lo = np.asarray(i.get("lower", [0.0] * n), float)
            up = np.asarray(i.get("upper", [1.0] * n), float)
            # DAQP (dual active-set QP; the final working set is solved by factorisation, so the answer is exact to
            # rounding): min 1/2 w'(g S)w - mu'w subject to sum w = 1 and lo <= w <= up.
            H = np.ascontiguousarray(g * S)
            A = np.ones((1, n))
            bu = np.concatenate([up, [1.0]])
            bl = np.concatenate([lo, [1.0]])
            sense = np.concatenate([np.zeros(n), [5]]).astype(np.int32)  # 5: equality constraint
            w, _, flag, _ = daqp.solve(H, -mu, A, bu, bl, sense)
            if flag != 1:
                raise RuntimeError(f"DAQP exit flag {flag} on {c['case_id']}")
            w = np.asarray(w, float)
            ret, var = float(mu @ w), float(w @ S @ w)
            chk = [check(c, "weights", w.tolist()), check(c, "expected_return", ret, via="arithmetic"),
                   check(c, "volatility", math.sqrt(var), via="arithmetic"),
                   check(c, "objective", ret - g / 2 * var, via="arithmetic"),
                   check(c, "at_bound", _at_bound(w, lo, up), via="arithmetic")]
            e = entry(c, chk)
            # PyPortfolioOpt max_quadratic_utility on Clarabel at tight tolerance: a second solver, reported only.
            ef = EfficientFrontier(mu, S, weight_bounds=list(zip(lo.tolist(), up.tolist())), solver="CLARABEL",
                                   solver_options={"tol_gap_abs": 1e-14, "tol_gap_rel": 1e-14, "tol_feas": 1e-14,
                                                   "max_iter": 500})
            wp = np.asarray(list(ef.max_quadratic_utility(risk_aversion=g).values()), float)
            e["second_solver"] = {"library": f"{ver('pyportfolioopt')} max_quadratic_utility on {ver('clarabel')}",
                                  "max_gap_weights": float(np.abs(wp - np.asarray(c["expected"]["outputs"]["weights"])).max())}
            rows.append(e)
        elif op == "research.portfolio.risk_parity":
            b = np.asarray(i.get("budgets", [1.0 / n] * n), float)
            # A different formulation from the spec's Newton on S y = b/y: minimise the convex 1/2 y'Sy - b'log y
            # (an exponential-cone program) with Clarabel through cvxpy; w = y / sum y.
            y = cp.Variable(n)
            L = np.linalg.cholesky(S)
            prob = cp.Problem(cp.Minimize(0.5 * cp.sum_squares(L.T @ y) - b @ cp.log(y)))
            prob.solve(solver="CLARABEL", tol_gap_abs=1e-14, tol_gap_rel=1e-14, tol_feas=1e-14, max_iter=500)
            w = np.asarray(y.value, float) / float(np.sum(y.value))
            vol = math.sqrt(float(w @ S @ w))
            rc = w * (S @ w) / vol
            e = entry(c, [check(c, "weights", w.tolist()), check(c, "volatility", vol, via="arithmetic"),
                          check(c, "contributions", rc.tolist(), via="arithmetic")])
            # Clarabel cannot certify 1e-14 and usually reports optimal_inaccurate; the case counts only on agreement
            # at root_finding (1e-10). The settings are fixed for every case, not tuned per case.
            e["solver_status"] = prob.status
            rows.append(e)
        else:  # risk.contrib.euler
            w = np.asarray(i["weights"], float)
            sig = lambda x: anp.sqrt(anp.dot(x, anp.dot(S, x)))
            m = np.asarray(grad(sig)(w), float)  # autograd derivative of sigma(w), not the closed form (S w)/sigma
            vol = float(sig(w))
            rows.append(entry(c, [check(c, "volatility", vol, via="arithmetic"), check(c, "marginal", m.tolist()),
                                  check(c, "contributions", (w * m).tolist(), via="arithmetic"),
                                  check(c, "shares", (w * m / vol).tolist(), via="arithmetic")]))
    return {"library": f"mean_variance: {ver('daqp')} dual active-set QP (PyPortfolioOpt on Clarabel reported as a second "
                       f"solver); risk_parity: {ver('cvxpy')} with {ver('clarabel')} on min 1/2 y'Sy - b'log y; euler: "
                       f"{ver('autograd')} gradient of sigma(w); expected return, volatility, objective, at_bound (within "
                       "1e-9 of a bound), contributions and shares are arithmetic", "cases": rows, "not_checked": skipped}


# ---------------------------------------------------------------- estim_j: scikit-learn LedoitWolf, PyPortfolioOpt BL
def estim():
    from pypfopt.black_litterman import BlackLittermanModel
    from sklearn.covariance import LedoitWolf

    rows = []
    for c in load("estim_j"):
        i = c["inputs"]
        if c["operation"] == "research.estimate.ledoit_wolf":
            X = np.asarray(i["returns"], float)
            lw = LedoitWolf(assume_centered=False, store_precision=False).fit(X)
            cov = lw.covariance_
            rows.append(entry(c, [check(c, "covariance", cov.tolist()), check(c, "shrinkage", float(lw.shrinkage_)),
                                  check(c, "mu", float(np.trace(cov) / X.shape[1]), via="arithmetic")]))
        else:
            S = np.asarray(i["covariance"], float)
            bl = BlackLittermanModel(pd.DataFrame(S), pi=np.asarray(i["prior_returns"], float),
                                     P=np.asarray(i["pick"], float), Q=np.asarray(i["views"], float),
                                     omega=np.asarray(i["view_covariance"], float), tau=i["tau"])
            post = np.asarray(bl.bl_returns(), float).ravel()
            pred = np.asarray(bl.bl_cov(), float)
            rows.append(entry(c, [check(c, "posterior_returns", post.tolist()),
                                  check(c, "posterior_covariance", (pred - S).tolist(), via="arithmetic"),
                                  check(c, "predictive_covariance", pred.tolist())]))
    return {"library": f"{ver('scikit-learn')} LedoitWolf(assume_centered=False) covariance_ and shrinkage_ (mu = trace/N "
                       f"of the library covariance, arithmetic); {ver('pyportfolioopt')} BlackLittermanModel bl_returns "
                       "and bl_cov (posterior_covariance = bl_cov - Sigma, arithmetic)", "cases": rows}


# ---------------------------------------------------------------- esbt_j: no library
def esbt():
    why = ("no pip-installable free library computes the Acerbi-Szekely Z2 statistic (the MATLAB Risk Toolbox is "
           "commercial; the AS14_test class of the Realized_Risk_Measures project is GitHub-only, with an unread licence); "
           "[AS14] prints critical values, not a worked example on data. Not counted (D6)")
    return {"library": None, "cases": [], "not_checked": [{"case_id": c["case_id"], "reason": why} for c in load("esbt_j")]}


# ---------------------------------------------------------------- baumwelch_j: hmmlearn GaussianHMM.fit
def baumwelch():
    from hmmlearn import hmm

    def model(i, n_iter, tol):
        m = hmm.GaussianHMM(n_components=len(i["means"]), covariance_type="diag", n_iter=n_iter, tol=tol,
                            init_params="", params="stmc", implementation="scaling", min_covar=0.0,
                            covars_prior=0.0, covars_weight=1.0, means_prior=0.0, means_weight=0.0,
                            startprob_prior=1.0, transmat_prior=1.0)
        m.startprob_ = np.asarray(i["initial"], float)
        m.transmat_ = np.asarray(i["transition"], float)
        m.means_ = np.asarray(i["means"], float).reshape(-1, 1)
        m.covars_ = (np.asarray(i["sds"], float) ** 2).reshape(-1, 1)
        m.n_features = 1
        return m

    rows = []
    for c in load("baumwelch_j"):
        i = c["inputs"]
        X = np.asarray(i["observations"], float).reshape(-1, 1)
        tol, mx = i.get("tolerance", 1e-10), i.get("max_iterations", 1000)
        # hmmlearn's own stop rule (ConvergenceMonitor): E-step at theta_j gives L_j, then an M-step; stop when
        # L_j - L_{j-1} < tol or after n_iter rounds. Its returned parameters are one M-step past its last E-step.
        # So the spec's k (first j >= 1 with gain < tol, J-W2-11) is len(history) - 1 when the library stops on
        # the gain, else max_iterations; theta_k is taken from a second run with n_iter = k and the stop test off
        # (every earlier gain is >= tol by the first run), and L_k is the library's score(X) at theta_k.
        m = model(i, mx + 1, tol)
        m.fit(X)
        h = list(m.monitor_.history)
        if len(h) >= 2 and h[-1] - h[-2] < tol:
            k, conv = len(h) - 1, True
        else:
            k, conv = mx, False
        mk = model(i, k, -np.inf)
        mk.fit(X)
        chk = [check(c, "initial", mk.startprob_.tolist()), check(c, "transition", mk.transmat_.tolist()),
               check(c, "means", mk.means_.ravel().tolist()),
               check(c, "sds", np.sqrt(mk.covars_.ravel()).tolist(), via="arithmetic"),
               check(c, "log_likelihood", float(mk.score(X))),
               check(c, "iterations", int(k), via="arithmetic"), check(c, "converged", bool(conv), via="arithmetic")]
        e = entry(c, chk)
        e["library_last_gains"] = [h[j] - h[j - 1] for j in range(max(1, len(h) - 3), len(h))]
        rows.append(e)
    return {"library": f"{ver('hmmlearn')} GaussianHMM(diag, implementation='scaling', init_params='', min_covar=0, "
                       "covars_prior=0, means_weight=0, flat Dirichlet priors).fit, stop index from the library's "
                       "ConvergenceMonitor history; theta_k by a re-run with n_iter = k; log_likelihood = score(X); "
                       "sds = sqrt(covars_), iterations and converged read off the history (arithmetic)", "cases": rows}


# ---------------------------------------------------------------- wave 3 (R6-13 floor; program/STAGE_J_HANDOVER.md)
def scen():
    """risk.scenario.replay: numpy.interp (linear, flat outside the end tenors: the J-W3-4 convention) on the
    shock curve; shocked yields and P&L are arithmetic on its output. historical_shock: pandas date-indexed lookup
    (DataFrame.loc) of the two rows; shifts, level and slope are arithmetic on the looked-up rows."""
    rows, skipped = [], []
    for c in load("scen_j"):
        i = c["inputs"]
        if c["operation"] == "risk.scenario.historical_shock":
            # A pandas date lookup plus subtraction is not an outside check of the method (audit 2026-11-15).
            skipped.append({"case_id": c["case_id"], "reason": "date lookup plus arithmetic; no library computes the "
                            "method, so a pandas re-implementation is not counted"})
            continue
        if c["operation"] == "risk.scenario.replay":
            a = i.get("scale", 1.0) * np.interp(i["base_tenors"], i["shock_tenors"], i["shock_bp"])
            chk = [check(c, "applied_bp", a.tolist()),
                   check(c, "shocked_yields", (np.asarray(i["base_yields"]) + a / 100.0).tolist(), via="arithmetic")]
            if "dv01" in i:
                chk.append(check(c, "pnl", float(-np.dot(i["dv01"], a)), via="arithmetic"))
        rows.append(entry(c, chk))
    return {"library": f"{ver('numpy')} interp (replay); the rest is arithmetic (library-primitive); "
                       "historical_shock not counted", "cases": rows, "not_checked": skipped}


def _interp(method, x, y, at):
    from scipy import interpolate
    if method == "linear":
        return np.interp(at, x, y)
    if method == "log_linear":
        return np.exp(np.interp(at, x, np.log(y)))
    if method == "cubic_natural":
        return interpolate.CubicSpline(x, y, bc_type="natural")(at)
    return interpolate.PchipInterpolator(x, y)(at)


def interpbt():
    """Leave-one-out and held-out strikes rebuilt with numpy.interp (linear; log_linear as exp of interp on log y),
    scipy CubicSpline(bc_type="natural") and PchipInterpolator; errors, max and RMSE are arithmetic."""
    rows = []
    for c in load("interpbt_j"):
        i = c["inputs"]
        if c["operation"] == "research.backtest.interp_loo":
            x, y = np.asarray(i["x"], float), np.asarray(i["y"], float)
            e = np.array([_interp(i["method"], np.delete(x, k), np.delete(y, k), [x[k]])[0] - y[k]
                          for k in range(1, len(x) - 1)])
            flat = e
            chk = [check(c, "errors", e.tolist(), via="arithmetic")]
        else:
            k, h = np.asarray(i["strikes"], float), list(i["holdout"])
            keep = [j for j in range(len(k)) if j not in h]
            e = []
            for t, row in zip(i["expiries"], i["vols"], strict=True):
                row = np.asarray(row, float)
                w = _interp(i["method"], k[keep], row[keep] ** 2 * t, k[h])
                e.append((np.sqrt(w / t) - row[h]).tolist())
            flat = np.asarray(e).ravel()
            chk = [check(c, "errors", e, via="arithmetic")]
        chk += [check(c, "max_abs_error", float(np.abs(flat).max()), via="arithmetic"),
                check(c, "rmse", float(np.sqrt(np.mean(flat ** 2))), via="arithmetic")]
        rows.append(entry(c, chk))
    return {"library": f"{ver('numpy')} interp; {ver('scipy')} CubicSpline natural, PchipInterpolator "
                       "(library-primitive)", "cases": rows,
            "note": "the interpbt_j goldens were generated with the same scipy/numpy interpolant calls, so this is a "
                    "library-object golden re-run, not a second independent check"}


def drift():
    """KS: scipy.stats.ks_2samp(method="exact") statistic and p-value. PSI: numpy.quantile(method="inverted_cdf")
    edges (the type-1 quantile of J-W3-12), numpy.searchsorted(side="left") right-closed bins, scipy.special.rel_entr
    for the two KL terms; the 1e-4 floor and the sum are arithmetic. CUSUM and Page-Hinkley are not counted."""
    from scipy import stats
    why = {"research.drift.cusum": "no free library implements the tabular two-sided CUSUM on z = (x - mu0) / sigma "
                                   "with restart (detecta.detect_cusum works on first differences); not counted",
           "research.drift.page_hinkley": "river 0.27 PageHinkley differs in convention: its running minimum starts at "
                                          "+inf (J-W3-11 includes the restart value 0), it has a min_instances gate and "
                                          "reports no direction; not matched honestly, not counted"}
    rows, skipped = [], []
    for c in load("drift_j"):
        i, op = c["inputs"], c["operation"]
        if op == "research.drift.ks":
            r = stats.ks_2samp(i["a"], i["b"], method="exact")
            chk = [check(c, "statistic", float(r.statistic)), check(c, "p_value", float(r.pvalue)),
                   check(c, "reject", bool(r.pvalue <= i.get("level", 0.05)), via="arithmetic")]
        elif op == "research.drift.psi":
            # numpy quantile/searchsorted plus rel_entr re-implements the PSI convention; not a library check
            # of PSI (audit 2026-11-15), so not counted.
            skipped.append({"case_id": c["case_id"], "reason": "no library computes PSI with these conventions; the "
                            "quantile/searchsorted/rel_entr version is a re-implementation, not counted"})
            continue
        else:
            skipped.append({"case_id": c["case_id"], "reason": why[op]})
            continue
        rows.append(entry(c, chk))
    return {"library": f"{ver('scipy')} stats.ks_2samp exact (PSI, CUSUM, Page-Hinkley not counted)", "cases": rows, "not_checked": skipped}


WAVES = {1: ("regime_j", "purgedcv_j", "rstats_j", "backtest_j"), 2: ("optim_j", "estim_j", "esbt_j", "baumwelch_j"),
         3: ("scen_j", "interpbt_j", "drift_j")}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="stage J outside-library checks")
    ap.add_argument("--wave", type=int, choices=sorted(WAVES), action="append",
                    help="run only these waves (default all); suites of other waves are kept from the committed file")
    a = ap.parse_args(argv)
    fns = {"regime_j": regime, "purgedcv_j": purgedcv, "rstats_j": rstats, "backtest_j": backtest,
           "optim_j": optim, "estim_j": estim, "esbt_j": esbt, "baumwelch_j": baumwelch,
           "scen_j": scen, "interpbt_j": interpbt, "drift_j": drift}
    run = [s for w in (a.wave or sorted(WAVES)) for s in WAVES[w]]
    old = json.loads(OUT.read_text(encoding="utf-8"))["suites"] if OUT.is_file() else {}
    suites = {}
    for name in [s for w in sorted(WAVES) for s in WAVES[w]]:
        if name not in run:
            if name in old:
                suites[name] = old[name]
            continue
        try:
            suites[name] = fns[name]()
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
    OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    for k, s in suites.items():
        print(k, s["counted"], "of", len(load(k)), "failed:", s["failed"], s.get("error", ""))
    print(doc["summary"])


if __name__ == "__main__":
    main()
