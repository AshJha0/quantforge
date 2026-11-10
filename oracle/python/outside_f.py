"""Stage F outside-oracle verifier (plan rule 11.2.5). Never writes an expected value.

A case counts only if an outside source reproduces every output within the case's own tolerance:
- QuantLib 1.44 through its own convention objects (rows below, reviewed copy in oracle/CONVENTION_MAP_F.md);
- a published worked example by the methodology owner (the Cboe VIX sample calculation), counted as outside because the
  numbers come from the index provider, not from QuantForge (vix_f, plan R10).
Cases checked only in part (an output QuantLib does not expose) are listed as partly outside and not counted.

    cd oracle/python && uv run python -W ignore outside_f.py
"""
import json
import math
import sys
from datetime import date

import QuantLib as ql

from outside_d import ROOT, judge
from qf_oracle import convmap as CM

Q = lambda d: ql.Date(d.day, d.month, d.year)  # noqa: E731
D = date.fromisoformat
A365 = ql.Actual365Fixed()
REVIEW = "self-reviewed 2026-11-09 (spec session); second review by the R5 audit"

ROWS = {
    "CRV.MONOTONE_CONVEX": ("02-curves/curve-framework.md MONOTONE_CONVEX = QuantLib ConvexMonotone(quadraticity 0, monotonicity 1, forcePositive false), ruling F-19",
                            "PiecewiseConvexMonotoneForward(ref, helpers, Actual365Fixed, [], [], ConvexMonotone(0, 1, False)); ConvexMonotoneInterpolation on discrete forwards"),
    "CRV.MONOTONIC_LOG_CUBIC": ("02-curves/curve-framework.md MONOTONIC_LOG_CUBIC = QuantLib MonotonicLogCubic",
                                "MonotonicLogCubicDiscountCurve(dates, dfs, Actual365Fixed) for D; MonotonicCubicNaturalSpline(t, ln D).derivative for f; PiecewiseLogCubicDiscount(ref, helpers, Actual365Fixed[, jumps])"),
    "OIS.HELPER": ("02-curves/ois-curves.md periods and lags", "OISRateHelper(settlementDays, tenor, quote, index, discount=None, telescopic=True, paymentLag)"),
    "IDX": ("01-core/conventions.md SOFR, SONIA, ESTR", "ql.Sofr(), ql.Sonia(), ql.Estr()"),
    "TERM.HELPERS": ("02-curves/projection-and-fra.md USD-TERM-3M deposits, FRAs, swaps", "IborIndex TERM 3M (2 days, US GovernmentBond, ModifiedFollowing, Actual360); DepositRateHelper, FraRateHelper, SwapRateHelper(Annual, ModifiedFollowing, Thirty360 BondBasis, exogenous discount)"),
    "CRV.LOG_LINEAR_DF": ("02-curves/curve-framework.md LOG_LINEAR_DF", "PiecewiseLogLinearDiscount(ref, helpers, Actual365Fixed)"),
    "SCIPY.CHI2": ("06-risk/var-es-and-backtests.md Kupiec, Christoffersen p-values", "scipy.stats.chi2.sf(lr, dof); likelihood ratios from scipy.stats.binom.logpmf and scipy.special.xlogy"),
    "SCIPY.BINOM": ("06-risk/var-es-and-backtests.md traffic light", "scipy.stats.binom.cdf(x, n, 1 - c); zones at 0.95 and 0.9999; plus factor Basel 1996 Table 2"),
    "SCIPY.NORM": ("06-risk/var-es-and-backtests.md parametric VaR and ES", "scipy.stats.norm.ppf; ES by scipy.integrate.quad of the normal tail (not the closed form)"),
    "NUMPY.QUANTILE": ("06-risk/var-es-and-backtests.md historical VaR", "numpy.quantile(losses, c, method='inverted_cdf') (Hyndman and Fan type 1); ES as the mean of the sorted losses from the first position holding that quantile (agrees with the spec without ties; a tie at the VaR scenario, risk_f4-0107, is not outside-checked)"),
    "SCIPY.EIGH": ("06-risk/book-sensitivities.md PCA", "numpy.cov(ddof=1); scipy.linalg.eigh (LAPACK syevr); sign rule of the spec"),
    "SCIPY.LSTSQ": ("04-pricing/use-cases.md use case 4 factor attribution", "scipy.linalg.lstsq on [1, F] (LAPACK gelsd); R^2, residual vol and standard errors from its residuals and numpy.linalg.inv of X'X"),
    "SCIPY.QUAD": ("02-curves/curve-framework.md discount factors of MONOTONE_CONVEX from its forward", "scipy.integrate.quad (QUADPACK qags) of QuantLib ConvexMonotoneInterpolation, per section, epsrel 1e-13"),
    "ARCH.GARCH": ("05-volatility/garch.md loglik, estimate; 06-risk/var-es-and-backtests.md FHS", "arch 7.2.0 (run under WSL): GARCH(1,0,1).compute_variance with backcast = (v0 - omega)/(alpha + beta) so that sigma2_1 = v0; Normal / StudentsT (standardised) loglikelihood; EWMAVariance(lam) with backcast = mean square; fits maximise that objective (scipy Nelder-Mead, Newton on a finite-difference Hessian); oracle/python/outside_garch_arch.py"),
    "CBOE.SAMPLE": ("05-volatility/vix-index.md Cboe sample", "Cboe Volatility Index Methodology v6.0, Appendix 3 printed values (F, K0, sigma^2, VIX)"),
}
LAGS = {"SOFR": (2, 2), "ESTR": (2, 2), "SONIA": (0, 0)}
IDX = {"SOFR": ql.Sofr, "SONIA": ql.Sonia, "ESTR": ql.Estr}


def _per(t):
    return ql.Period(int(t[:-1]), {"W": ql.Weeks, "M": ql.Months, "Y": ql.Years}[t[-1]])


def ql_build(i):
    a = Q(D(i["as_of"]))
    ql.Settings.instance().evaluationDate = a
    sl, pl = LAGS[i["convention"]]
    hs = [ql.OISRateHelper(sl, _per(q["tenor"]), ql.QuoteHandle(ql.SimpleQuote(q["rate"])), IDX[i["convention"]](), ql.YieldTermStructureHandle(), True, pl)
          for q in i["quotes"]]
    js = i.get("jumps") or []
    jq, jd = [ql.QuoteHandle(ql.SimpleQuote(j["factor"])) for j in js], [Q(D(j["date"])) for j in js]
    if i["interpolation"] == "MONOTONE_CONVEX":
        c = ql.PiecewiseConvexMonotoneForward(a, hs, A365, jq, jd, ql.ConvexMonotone(0.0, 1.0, False))
    elif i["interpolation"] == "MONOTONIC_LOG_CUBIC":
        c = ql.PiecewiseLogCubicDiscount(a, hs, A365, jq, jd) if js else ql.PiecewiseLogCubicDiscount(a, hs, A365)
    else:
        raise NotImplementedError(i["interpolation"])
    c.enableExtrapolation()
    return c, hs


def h_bootstrap(i):
    c, hs = ql_build(i)
    return {"pillars": [{"date": h.pillarDate().ISO(), "discount_factor": c.discount(h.pillarDate())} for h in hs]}, {"CRV." + i["interpolation"], "OIS.HELPER", "IDX"}


def h_inspect_cm(i):
    """MONOTONE_CONVEX: forwards from QuantLib ConvexMonotoneInterpolation(0, 1, forcePositive false) on the discrete
    forwards of the pillars (ruling F-19); discount factors by scipy.integrate.quad of that forward, section by section
    (the wheel does not expose the primitive); flat f(t_n-) beyond the last pillar (ruling F-20)."""
    from scipy import integrate
    cv = i["curve"]
    a = D(cv["as_of"])
    tn = [0.0] + [(D(p["date"]) - a).days / 365 for p in cv["pillars"]]
    S = [1.0] + [p["discount_factor"] for p in cv["pillars"]]
    fd = [math.log(S[k - 1] / S[k]) / (tn[k] - tn[k - 1]) for k in range(1, len(tn))]
    ip = ql.ConvexMonotoneInterpolation(tn, [fd[0]] + fd, 0.0, 1.0, False)
    fend = ip(tn[-1], True)
    fwd = lambda u: ip(u, True) if u < tn[-1] else fend  # noqa: E731

    def prim(u):
        acc, lo = 0.0, 0.0
        for k in range(1, len(tn)):
            hi = min(u, tn[k])
            if hi > lo:
                acc += integrate.quad(fwd, lo, hi, epsabs=1e-16, epsrel=1e-13, limit=200)[0]
            lo = tn[k]
            if u <= tn[k]:
                return acc
        return acc + fend * (u - tn[-1])
    out = {"discount_factors": [], "zero_rates": [], "instantaneous_forwards": []}
    for s in i["dates"]:
        u = (D(s) - a).days / 365
        df = math.exp(-prim(u))
        out["discount_factors"].append(df)
        out["zero_rates"].append(None if u == 0 else -math.log(df) / u)
        out["instantaneous_forwards"].append(fwd(min(u, tn[-1])) if u < tn[-1] else fend)
    return out, {"CRV.MONOTONE_CONVEX", "SCIPY.QUAD"}


def h_inspect_ll(i):
    """LOG_LINEAR_DF: discount factors from QuantLib DiscountCurve (LogLinear on ACT/365F, which extrapolates the last
    segment as the stage B rule does); the forward is -d ln D/dt of that curve, taken on the segment that starts at or
    before t (right-continuous at pillars, the spec's one-sided rule), from QuantLib's discount factors at the segment ends."""
    cv = i["curve"]
    a = D(cv["as_of"])
    ql.Settings.instance().evaluationDate = Q(a)
    ds = [Q(a)] + [Q(D(p["date"])) for p in cv["pillars"]]
    c = ql.DiscountCurve(ds, [1.0] + [p["discount_factor"] for p in cv["pillars"]], A365)
    c.enableExtrapolation()
    tn = [0.0] + [(D(p["date"]) - a).days / 365 for p in cv["pillars"]]
    out = {"discount_factors": [], "zero_rates": [], "instantaneous_forwards": []}
    for s in i["dates"]:
        u = (D(s) - a).days / 365
        df = c.discount(u, True)
        k = next((k for k in range(len(tn) - 1) if u < tn[k + 1]), len(tn) - 2)
        out["discount_factors"].append(df)
        out["zero_rates"].append(None if u == 0 else -math.log(df) / u)
        out["instantaneous_forwards"].append(math.log(c.discount(tn[k], True) / c.discount(tn[k + 1], True)) / (tn[k + 1] - tn[k]))
    return out, {"CRV.LOG_LINEAR_DF"}


def h_inspect(i):
    cv = i["curve"]
    if cv["interpolation"] == "MONOTONE_CONVEX" and not cv.get("jumps"):
        return h_inspect_cm(i)
    if cv["interpolation"] == "LOG_LINEAR_DF" and not cv.get("jumps"):
        return h_inspect_ll(i)
    if cv["interpolation"] != "MONOTONIC_LOG_CUBIC":
        raise NotImplementedError("no QuantLib discount curve from pillars for this method")
    a = D(cv["as_of"])
    # jumps (curve-framework.md): pillars hold full D; the interpolation is on S = D/J, J the product of factors dated
    # strictly before the date; reported forwards are those of S (the smooth curve)
    js = [(D(j["date"]), j["factor"]) for j in cv.get("jumps") or []]
    J = lambda d: math.prod(fc for jd, fc in js if jd < d)  # noqa: E731
    ql.Settings.instance().evaluationDate = Q(a)
    ds = [Q(a)] + [Q(D(p["date"])) for p in cv["pillars"]]
    Sp = [p["discount_factor"] / J(D(p["date"])) for p in cv["pillars"]]
    c = ql.MonotonicLogCubicDiscountCurve(ds, [1.0] + Sp, A365)
    c.enableExtrapolation()
    # instantaneous forward from QuantLib's own spline slope on ln D (forwardRate(t, t) is a 1e-4 finite difference)
    tn = [0.0] + [(D(p["date"]) - a).days / 365 for p in cv["pillars"]]
    sp = ql.MonotonicCubicNaturalSpline(tn, [0.0] + [math.log(v) for v in Sp])
    out = {"discount_factors": [], "zero_rates": [], "instantaneous_forwards": []}
    for s in i["dates"]:
        d = D(s)
        t = (d - a).days / 365
        df = c.discount(t, True) * J(d)
        out["discount_factors"].append(df)
        out["zero_rates"].append(None if t == 0 else -math.log(df) / t)
        out["instantaneous_forwards"].append(-sp.derivative(min(t, tn[-1]), True))
    return out, {"CRV.MONOTONIC_LOG_CUBIC"}


def h_cboe(case):
    """The Cboe printed values: the golden must round to them (checked again here, independently of the generator)."""
    o = case["expected"]["outputs"]
    if case["operation"] == "vol.vix.index":
        ok = round(o["index"], 2) == 13.93 and round(o["index"] / 100, 8) == 0.13927842
    elif case["inputs"]["minutes_to_expiry"] == 34484:
        ok = round(o["forward"], 5) == 1962.89996 and o["k0"] == 1960.0 and round(o["variance"], 9) == 0.019233906
    else:
        ok = round(o["forward"], 5) == 1962.40006 and o["k0"] == 1960.0 and round(o["variance"], 9) == 0.019423884
    return ok


PIECEWISE = {"LOG_LINEAR_DF": lambda a, hs, j=None: ql.PiecewiseLogLinearDiscount(a, hs, A365),
             "MONOTONIC_LOG_CUBIC": lambda a, hs, j=None: ql.PiecewiseLogCubicDiscount(a, hs, A365),
             "MONOTONE_CONVEX": lambda a, hs, j=None: ql.PiecewiseConvexMonotoneForward(a, hs, A365, [], [], ql.ConvexMonotone(0.0, 1.0, False))}


def _term_index(h=None):
    return ql.IborIndex("TERM", ql.Period(3, ql.Months), 2, ql.USDCurrency(), ql.UnitedStates(ql.UnitedStates.GovernmentBond), ql.ModifiedFollowing,
                        False, ql.Actual360(), h or ql.YieldTermStructureHandle())


def ql_joint(i, bump=None):
    """QuantLib build of an OIS + PROJECTION system (no turns, steps or xccy). bump = (instrument index, dq). Returns
    {curve name: (QuantLib curve, pillar dates)}."""
    a = Q(D(i["as_of"]))
    ql.Settings.instance().evaluationDate = a
    built = {}
    for c in i["curves"]:
        if c["type"] not in ("OIS", "PROJECTION") or c.get("turns") or c.get("jumps") or c["interpolation"] not in PIECEWISE:
            raise NotImplementedError(f"{c['type']} {c.get('interpolation')} turns={bool(c.get('turns'))}")
        hs = []
        for k, q in enumerate(i["instruments"]):
            if q["curve"] != c["name"]:
                continue
            r = q["rate"] + (bump[1] if bump and bump[0] == k else 0.0)
            qq = ql.QuoteHandle(ql.SimpleQuote(r))
            if q["type"] == "OIS":
                sl, pl = LAGS[c["convention"]]
                hs.append(ql.OISRateHelper(sl, _per(q["tenor"]), qq, IDX[c["convention"]](), ql.YieldTermStructureHandle(), True, pl))
            elif q["type"] == "DEPOSIT":
                hs.append(ql.DepositRateHelper(qq, _term_index()))
            elif q["type"] == "FRA":
                hs.append(ql.FraRateHelper(qq, q["start_months"], _term_index()))
            elif q["type"] == "SWAP":
                idx = _term_index()
                hs.append(ql.SwapRateHelper(qq, ql.Period(q["months"], ql.Months), idx.fixingCalendar(), ql.Annual, ql.ModifiedFollowing,
                                            ql.Thirty360(ql.Thirty360.BondBasis), idx, ql.QuoteHandle(), ql.Period(0, ql.Days),
                                            ql.YieldTermStructureHandle(built[c["discount"]][0])))
            else:
                raise NotImplementedError(q["type"])
        cv = PIECEWISE[c["interpolation"]](a, hs)
        cv.enableExtrapolation()
        built[c["name"]] = (cv, [h.pillarDate() for h in hs])
    return built


def h_joint(i):
    b0 = ql_joint(i)
    curves = [{"name": c["name"], "pillars": [{"date": p.ISO(), "discount_factor": b0[c["name"]][0].discount(p)} for p in b0[c["name"]][1]]} for c in i["curves"]]
    x0 = [math.log(p["discount_factor"]) for cv in curves for p in cv["pillars"]]
    labels = [f"{cv['name']}:pillar:{p['date']}" for cv in curves for p in cv["pillars"]]

    def xs(bump):
        b = ql_joint(i, bump)
        return [math.log(b[c["name"]][0].discount(p)) for c in i["curves"] for p in b[c["name"]][1]]
    h = 1e-4
    cols = []
    for k in range(len(i["instruments"])):
        d1 = [(u - v) / (2 * h) for u, v in zip(xs((k, h)), xs((k, -h)))]
        d2 = [(u - v) / h for u, v in zip(xs((k, h / 2)), xs((k, -h / 2)))]
        cols.append([(4 * q2 - q1) / 3 for q1, q2 in zip(d1, d2)])
    matrix = [[cols[k][r] for k in range(len(cols))] for r in range(len(x0))]
    return {"curves": curves, "turn_factors": [], "jacobian": {"unknowns": labels, "quotes": [q["id"] for q in i["instruments"]], "matrix": matrix},
            "turn_sensitivity": []}, {"CRV." + c["interpolation"] for c in i["curves"]} | {"OIS.HELPER", "IDX", "TERM.HELPERS"}


def h_kupiec(i):
    from scipy import stats, special
    n, x, p = i["observations"], i["exceptions"], 1 - i["confidence"]
    lr = max(2 * (stats.binom.logpmf(x, n, x / n) - stats.binom.logpmf(x, n, p)), 0.0)
    lr = 0.0 if lr < 1e-12 else lr  # spec rule, ruling F-32
    return {"lr_uc": lr, "p_value": float(stats.chi2.sf(lr, 1))}, {"SCIPY.CHI2"}


def h_christ(i):
    from scipy import stats
    from scipy.special import xlogy
    I = [int(v) for v in i["exceptions"]]
    out, _ = h_kupiec({"observations": len(I), "exceptions": sum(I), "confidence": i["confidence"]})
    nn = {(a, b): 0 for a in (0, 1) for b in (0, 1)}
    for a, b in zip(I, I[1:]):
        nn[(a, b)] += 1
    n00, n01, n10, n11 = nn[(0, 0)], nn[(0, 1)], nn[(1, 0)], nn[(1, 1)]
    pi = (n01 + n11) / (n00 + n01 + n10 + n11)
    p01 = n01 / (n00 + n01) if n00 + n01 else 0.0
    p11 = n11 / (n10 + n11) if n10 + n11 else 0.0
    l0 = xlogy(n00 + n10, 1 - pi) + xlogy(n01 + n11, pi)
    l1 = xlogy(n00, 1 - p01) + xlogy(n01, p01) + xlogy(n10, 1 - p11) + xlogy(n11, p11)
    ind = max(-2 * (l0 - l1), 0.0)
    ind = 0.0 if ind < 1e-12 else ind  # ruling F-32
    cc = out["lr_uc"] + ind
    return {"lr_uc": out["lr_uc"], "lr_ind": ind, "lr_cc": cc, "p_uc": out["p_value"], "p_ind": float(stats.chi2.sf(ind, 1)), "p_cc": float(stats.chi2.sf(cc, 2)),
            "transitions": {"n00": n00, "n01": n01, "n10": n10, "n11": n11}}, {"SCIPY.CHI2"}


def h_traffic(i):
    from scipy import stats
    n, x, c = i["observations"], i["exceptions"], i["confidence"]
    cum = float(stats.binom.cdf(x, n, 1 - c))
    zone = "GREEN" if cum < 0.95 else ("YELLOW" if cum < 0.9999 else "RED")
    plus = ({5: .40, 6: .50, 7: .65, 8: .75, 9: .85}.get(x, 0.0 if x <= 4 else 1.0)) if (n == 250 and c == .99) else None
    return {"cumulative_probability": cum, "zone": zone, "plus_factor": plus}, {"SCIPY.BINOM"}


def h_param(i):
    from scipy import stats, integrate
    mu, sd, c = i["mean"], i["std"], i["confidence"]
    z = stats.norm.ppf(c)
    tail = integrate.quad(lambda u: u * stats.norm.pdf(u), z, math.inf, epsabs=0, epsrel=1e-13, limit=200)[0] / (1 - c)
    return {"var": -mu + sd * z, "es": -mu + sd * tail}, {"SCIPY.NORM"}


def h_hist(i):
    import numpy as np
    L = -np.array(i["pnl"], float)
    v = float(np.quantile(L, i["confidence"], method="inverted_cdf"))
    s = np.sort(L)
    k = int(np.searchsorted(s, v, side="left"))  # first position holding the quantile: the VaR scenario (ties included)
    t = s[k:]
    return {"var": v, "es": float(np.mean(t)), "tail_count": int(t.size)}, {"NUMPY.QUANTILE"}


def h_pca(i):
    import numpy as np
    from scipy import linalg
    X = np.array(i["changes"], float)
    w, V = linalg.eigh(np.cov(X.T, ddof=1))
    o = np.argsort(-w)
    w, V = w[o], V[:, o]
    k = i["components"]
    L = []
    for j in range(k):
        v = V[:, j]
        b = max(range(len(v)), key=lambda r: (abs(v[r]), -r))
        L.append(list(-v if v[b] < 0 else v))
    return {"eigenvalues": list(w), "loadings": L, "explained_ratio": list(w[:k] / w.sum())}, {"SCIPY.EIGH"}


def h_uc4(i):
    import numpy as np
    from scipy import linalg
    y = np.array(i["portfolio_returns"], float)
    F = np.array(i["factor_returns"], float)
    T, K = F.shape
    X = np.column_stack([np.ones(T), F])
    b, ssr, _, _ = linalg.lstsq(X, y)
    res = y - X @ b
    ssr = float(res @ res)
    s2 = ssr / (T - K - 1)
    inv = np.linalg.inv(X.T @ X)
    return {"alpha": float(b[0]), "betas": list(b[1:]), "r_squared": 1 - ssr / float(((y - y.mean()) ** 2).sum()),
            "contributions": list(b[1:] * F.mean(axis=0)), "mean_return": float(y.mean()), "residual_vol": math.sqrt(s2),
            "beta_se": [math.sqrt(s2 * inv[k + 1, k + 1]) for k in range(K)]}, {"SCIPY.LSTSQ"}


def h_cross_gamma(i):
    """06-risk/book-sensitivities.md: the spec's four-point formula, every revaluation by QuantLib: MakeOIS (SOFR, 2
    settlement days, payment lag 2, telescopic value dates) on a DiscountCurve (LogLinear, ACT/365F) of the pillars with
    the PILLAR zero-rate bumps D exp(-h t)."""
    cv, tr, bp = i["curve"], i["product"]["trade"], i["bump_bp"]
    if cv["interpolation"] != "LOG_LINEAR_DF" or cv.get("jumps") or tr["convention"] != "SOFR":
        raise NotImplementedError("log-linear SOFR only")
    a = D(cv["as_of"])
    ql.Settings.instance().evaluationDate = Q(a)
    pd = [D(p["date"]) for p in cv["pillars"]]
    tn = [(d - a).days / 365 for d in pd]
    df0 = [p["discount_factor"] for p in cv["pillars"]]
    h = bp * 1e-4

    def V(dz):
        crv = ql.DiscountCurve([Q(a)] + [Q(d) for d in pd], [1.0] + [v * math.exp(-z * t) for v, z, t in zip(df0, dz, tn)], A365)
        crv.enableExtrapolation()
        hd = ql.YieldTermStructureHandle(crv)
        sw = ql.MakeOIS(ql.Period(tr["tenor"]), ql.Sofr(hd), tr["fixed_rate"], ql.Period(0, ql.Days),
                        swapType=ql.OvernightIndexedSwap.Payer if tr["side"] == "PAY" else ql.OvernightIndexedSwap.Receiver,
                        nominal=tr["notional"], settlementDays=2, paymentLag=2, telescopicValueDates=True, discountingTermStructure=hd)
        return sw.NPV()
    n = len(pd)
    e = lambda pairs: [sum(s * h for k, s in pairs if k == j) for j in range(n)]  # noqa: E731
    base = V([0.0] * n)
    G = [[0.0] * n for _ in range(n)]
    for x in range(n):
        for y in range(x, n):
            if x == y:
                G[x][x] = (V(e([(x, 1)])) - 2 * base + V(e([(x, -1)]))) / bp ** 2
            else:
                G[x][y] = G[y][x] = (V(e([(x, 1), (y, 1)])) - V(e([(x, 1), (y, -1)])) - V(e([(x, -1), (y, 1)])) + V(e([(x, -1), (y, -1)]))) / (4 * bp ** 2)
    return {"value": base, "cross_gamma": G}, {"OIS.HELPER", "IDX", "CRV.LOG_LINEAR_DF"}


HANDLERS = {"risk.curve.cross_gamma": h_cross_gamma, "usecase.factor_attribution": h_uc4, "risk.backtest.kupiec": h_kupiec, "risk.backtest.christoffersen": h_christ, "risk.backtest.traffic_light": h_traffic,
            "risk.var.parametric": h_param, "risk.var.historical": h_hist, "risk.curve.pca": h_pca,
            "rates.ois.bootstrap": h_bootstrap, "rates.curve.inspect": h_inspect, "rates.curve.joint_solve": h_joint}


_A = json.loads((ROOT / "oracle" / "outside_arch_f.json").read_text(encoding="utf-8")) if (ROOT / "oracle" / "outside_arch_f.json").exists() else {"cases": {}, "version": None}
ARCH, ARCH_VERSION = _A["cases"], _A["version"]


def main():
    reg, partly, table = [], [], []
    for p in sorted((ROOT / "datasets" / "golden" / "stage_f").glob("*.json")):
        if p.name.startswith("e1_"):
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        n_ok = n = 0
        for c in doc["cases"]:
            n += 1
            if c["expected"]["status"] != "ok":
                continue
            if "cboe-sample" in c["tags"]:
                if h_cboe(c):
                    n_ok += 1
                    reg.append({"case_id": c["case_id"], "operation": c["operation"], "source": "Cboe Volatility Index Methodology v6.0, Appendix 3",
                                "convention_rows": ["CBOE.SAMPLE"], "map_review": REVIEW})
                continue
            if c["case_id"] in ARCH:
                ok, why, _ = judge(c, ARCH[c["case_id"]])
                if ok:
                    n_ok += 1
                    reg.append({"case_id": c["case_id"], "operation": c["operation"], "library": "arch", "version": ARCH_VERSION,
                                "convention_rows": ["ARCH.GARCH"], "map_review": REVIEW})
                else:
                    print(f"  NOT VERIFIED {c['case_id']} (arch): {why}")
                continue
            h = HANDLERS.get(c["operation"])
            if not h:
                continue
            try:
                got, rows = h(c["inputs"])
            except NotImplementedError:
                if c["operation"] == "rates.curve.inspect" and c["inputs"]["curve"]["interpolation"] == "MONOTONE_CONVEX":
                    partly.append({"case_id": c["case_id"], "why": "forwards checked against ConvexMonotoneInterpolation; its integral is not in the wheel"})
                continue
            ok, why, _ = judge(c, got)
            if ok:
                n_ok += 1
                reg.append({"case_id": c["case_id"], "operation": c["operation"], "library": CM.LIBRARY, "version": CM.VERSION,
                            "convention_rows": sorted(rows), "map_review": REVIEW})
            else:
                print(f"  NOT VERIFIED {c['case_id']}: {why}")
        table.append((doc["suite"], n_ok, n))
    (ROOT / "oracle" / "outside_register_f.json").write_text(json.dumps({"rule": "plan 11.2.5", "library": CM.LIBRARY, "version": CM.VERSION, "map_review": REVIEW,
                                                                         "partly_outside_not_counted": partly, "cases": reg}, indent=1) + "\n", encoding="utf-8", newline="\n")
    lines = ["# Stage F convention map (rule 11.2.5)", "", f"QuantLib {CM.VERSION}. {REVIEW}. Written by `oracle/python/outside_f.py`.", "",
             "| Row | Spec | Library objects |", "|---|---|---|"] + [f"| `{k}` | {a} | {b} |" for k, (a, b) in ROWS.items()]
    (ROOT / "oracle" / "CONVENTION_MAP_F.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    tot = sum(t[1] for t in table), sum(t[2] for t in table)
    for s, k, n in table:
        print(f"{s:<12} outside {k:>3} / {n:>3}")
    print(f"stage F (E1 excluded, ruling F-23): {tot[0]} / {tot[1]} = {100 * tot[0] / max(tot[1], 1):.1f}%; partly outside {len(partly)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
