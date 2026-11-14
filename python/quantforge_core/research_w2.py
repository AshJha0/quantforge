"""Stage J wave 2 operations (rulings J-W2-1 to J-W2-15): mean-variance and risk parity,
Euler risk contributions (07-portfolio/optimisation.md), Ledoit-Wolf and Black-Litterman
(07-portfolio/estimation.md), the Acerbi-Szekely Z2 statistic (06-risk/es-backtest.md) and
Baum-Welch for a Gaussian hidden Markov model (11-research/baum-welch.md)."""
import math
from collections.abc import Sequence
from typing import Any

from .errors import QfError
from .finite import guard
from .research import _check_probabilities

Matrix = Sequence[Sequence[float]]
SYMMETRY_TOLERANCE = 1e-12
BUDGET_TOLERANCE = 1e-12
_SQRT_2PI = math.sqrt(2.0 * math.pi)


# --- Shared linear algebra (J-W2-3) ------------------------------------------------------------

def _square(a: Matrix, n: int, field: str) -> None:
    if len(a) != n or any(len(r) != n for r in a):
        raise QfError("E_INPUT", f"{field} must be {n} x {n}", field)


def _symmetric(a: Matrix, field: str) -> list[list[float]]:
    """J-W2-3: symmetric within 1e-12 max|S|; the upper triangle is used from here on."""
    n = len(a)
    big = max((abs(x) for r in a for x in r), default=0.0)
    for i in range(n):
        for j in range(i + 1, n):
            if abs(a[i][j] - a[j][i]) > SYMMETRY_TOLERANCE * big:
                raise QfError("E_DOMAIN", f"{field} is not symmetric", field)
    return [[a[min(i, j)][max(i, j)] for j in range(n)] for i in range(n)]


def _cholesky(a: Matrix, field: str) -> list[list[float]]:
    """Lower factor L with L L' = a; a pivot that is not > 0 is E_DOMAIN (J-W2-3)."""
    n = len(a)
    low = [[0.0] * n for _ in range(n)]
    for j in range(n):
        d = a[j][j] - sum(low[j][k] * low[j][k] for k in range(j))
        if not d > 0:
            raise QfError("E_DOMAIN", f"{field} is not positive definite", field)
        low[j][j] = math.sqrt(d)
        for i in range(j + 1, n):
            low[i][j] = (a[i][j] - sum(low[i][k] * low[j][k] for k in range(j))) / low[j][j]
    return low


def _chol_solve(low: Matrix, b: Sequence[float]) -> list[float]:
    n = len(low)
    y = [0.0] * n
    for i in range(n):
        y[i] = (b[i] - sum(low[i][k] * y[k] for k in range(i))) / low[i][i]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (y[i] - sum(low[k][i] * x[k] for k in range(i + 1, n))) / low[i][i]
    return x


def _matvec(a: Matrix, x: Sequence[float]) -> list[float]:
    return [sum(r[j] * x[j] for j in range(len(x))) for r in a]


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


# --- Mean-variance (J-W2-2, J-W2-4) ------------------------------------------------------------

def _feasible_start(lower: Sequence[float], upper: Sequence[float]) -> list[float]:
    w = list(lower)
    rest = 1.0 - math.fsum(lower)
    for i, (lo, up) in enumerate(zip(lower, upper, strict=True)):
        if rest <= 0:
            break
        step = min(up - lo, rest)
        w[i] = up if step == up - lo else lo + step
        rest -= step
    return w


def _eqp(sigma: Matrix, mu: Sequence[float], gamma: float, w: Sequence[float],
         free: Sequence[int], fixed: Sequence[int]) -> tuple[list[float], float]:
    """Optimum over the free set with the fixed weights held: weights of the free set and nu."""
    target = 1.0 - math.fsum(w[i] for i in fixed)
    if len(free) == 1:  # the budget fixes the weight; no solve, so no rounding past a bound
        i = free[0]
        full = [target if j == i else w[j] for j in range(len(w))]
        return [target], mu[i] - gamma * _dot(sigma[i], full)
    c = [mu[i] - gamma * sum(sigma[i][j] * w[j] for j in fixed) for i in free]
    low = _cholesky([[sigma[i][j] for j in free] for i in free], "covariance")
    a = _chol_solve(low, c)
    e = _chol_solve(low, [1.0] * len(free))
    nu = (math.fsum(a) - gamma * target) / math.fsum(e)
    return [(x - nu * y) / gamma for x, y in zip(a, e, strict=True)], nu


def portfolio_mean_variance(expected_returns: Sequence[float], covariance: Matrix,
                            risk_aversion: float, lower: Sequence[float] | None = None,
                            upper: Sequence[float] | None = None) -> dict[str, Any]:
    """`research.portfolio.mean_variance`: primal active set from a feasible start [NW06, 16.5]."""
    n = len(expected_returns)
    if n < 1:
        raise QfError("E_INPUT", "need at least one asset", "expected_returns")
    _square(covariance, n, "covariance")
    lo = [0.0] * n if lower is None else list(lower)
    up = [1.0] * n if upper is None else list(upper)
    if len(lo) != n or len(up) != n:
        raise QfError("E_INPUT", "lower and upper must have length N", "lower")
    gamma = risk_aversion
    if not gamma > 0:
        raise QfError("E_DOMAIN", "risk_aversion must be positive", "risk_aversion")
    if any(a > b for a, b in zip(lo, up, strict=True)):
        raise QfError("E_DOMAIN", "a lower bound is above its upper bound", "lower")
    if math.fsum(lo) > 1 or math.fsum(up) < 1:
        raise QfError("E_DOMAIN", "the bounds admit no fully invested portfolio", "lower")
    sigma = _symmetric(covariance, "covariance")
    _cholesky(sigma, "covariance")
    mu = list(expected_returns)
    w = _feasible_start(lo, up)
    # Working set: +1 at upper, -1 at lower, 0 free.
    state = [-1 if w[i] == lo[i] else (1 if w[i] == up[i] else 0) for i in range(n)]
    for i in range(n):
        if lo[i] == up[i]:
            state[i] = -1
    for _ in range(50 * n + 100):
        free = [i for i in range(n) if state[i] == 0]
        fixed = [i for i in range(n) if state[i] != 0]
        if not free:
            h = [mu[i] - gamma * _dot(sigma[i], w) for i in range(n)]
            cands = [i for i in range(n) if lo[i] < up[i]]
            if not cands:
                break
            low_set = [i for i in cands if state[i] < 0]
            pick = (max(low_set, key=lambda i: (h[i], -i)) if low_set
                    else min(cands, key=lambda i: (h[i], i)))
            state[pick] = 0
            continue
        target, nu = _eqp(sigma, mu, gamma, w, free, fixed)
        step = [t - w[i] for t, i in zip(target, free, strict=True)]
        alpha, block = 1.0, -1
        for p, i in zip(step, free, strict=True):
            if p < 0 and lo[i] - w[i] > alpha * p:
                alpha, block = (lo[i] - w[i]) / p, i
            elif p > 0 and up[i] - w[i] < alpha * p:
                alpha, block = (up[i] - w[i]) / p, i
        if block >= 0:
            for p, i in zip(step, free, strict=True):
                w[i] += alpha * p
            w[block] = lo[block] if w[block] - lo[block] <= up[block] - w[block] else up[block]
            state[block] = -1 if w[block] == lo[block] else 1
            for i in free:  # weights pushed onto a bound by rounding join the working set
                if state[i] == 0 and (w[i] <= lo[i] or w[i] >= up[i]):
                    w[i] = lo[i] if w[i] <= lo[i] else up[i]
                    state[i] = -1 if w[i] == lo[i] else 1
            continue
        for t, i in zip(target, free, strict=True):
            w[i] = t
        scale = max(abs(x) for x in mu) + gamma * max(abs(x) for r in sigma for x in r)
        worst, which = 1e-14 * scale, -1
        for i in fixed:
            if lo[i] == up[i]:
                continue
            g = mu[i] - gamma * _dot(sigma[i], w) - nu
            bad = g if state[i] < 0 else -g
            if bad > worst:
                worst, which = bad, i
        if which < 0:
            break
        state[which] = 0
    else:  # pragma: no cover - finite under strict convexity
        raise QfError("E_DOMAIN", "the active-set method did not terminate", "covariance")
    sw = _matvec(sigma, w)
    var = _dot(w, sw)
    ret = _dot(mu, w)
    at_bound = [-1 if w[i] == lo[i] else (1 if w[i] == up[i] else 0) for i in range(n)]
    return {"weights": w, "expected_return": ret, "volatility": math.sqrt(var),
            "objective": ret - 0.5 * gamma * var, "at_bound": at_bound}


# --- Risk parity (J-W2-5) ---------------------------------------------------------------------

def portfolio_risk_parity(covariance: Matrix,
                          budgets: Sequence[float] | None = None) -> dict[str, Any]:
    """`research.portfolio.risk_parity`: Newton on `Sigma y = b / y` [Spinu13], `w = y / sum y`."""
    n = len(covariance)
    if n < 1:
        raise QfError("E_INPUT", "need at least one asset", "covariance")
    _square(covariance, n, "covariance")
    raw = [1.0 / n] * n if budgets is None else list(budgets)
    if len(raw) != n:
        raise QfError("E_INPUT", "budgets must have length N", "budgets")
    if any(not x > 0 for x in raw):
        raise QfError("E_DOMAIN", "every budget must be positive", "budgets")
    total = math.fsum(raw)
    if abs(total - 1.0) > BUDGET_TOLERANCE:
        raise QfError("E_DOMAIN", "budgets must sum to 1", "budgets")
    b = [x / total for x in raw]
    sigma = _symmetric(covariance, "covariance")
    _cholesky(sigma, "covariance")
    y = [math.sqrt(b[i] / sigma[i][i]) for i in range(n)]
    bnorm = math.sqrt(_dot(b, b))
    for _ in range(500):
        f = [s - bi / yi for s, bi, yi in zip(_matvec(sigma, y), b, y, strict=True)]
        if math.sqrt(_dot(f, f)) < 1e-14 * bnorm:
            break
        jac = [[sigma[i][j] + (b[i] / (y[i] * y[i]) if i == j else 0.0) for j in range(n)]
               for i in range(n)]
        d = _chol_solve(_cholesky(jac, "covariance"), f)
        t = 1.0
        while any(yi - t * di <= 0 for yi, di in zip(y, d, strict=True)):
            t *= 0.5
        y = [yi - t * di for yi, di in zip(y, d, strict=True)]
        if t * math.sqrt(_dot(d, d)) < 1e-15:
            break
    s = math.fsum(y)
    w = [yi / s for yi in y]
    sw = _matvec(sigma, w)
    vol = math.sqrt(_dot(w, sw))
    return {"weights": w, "volatility": vol,
            "contributions": [wi * x / vol for wi, x in zip(w, sw, strict=True)]}


# --- Euler contributions (J-W2-6) -------------------------------------------------------------

def contrib_euler(weights: Sequence[float], covariance: Matrix) -> dict[str, Any]:
    """`risk.contrib.euler`: marginal, contribution and share of volatility per asset [Tas99]."""
    n = len(weights)
    if n < 1:
        raise QfError("E_INPUT", "need at least one asset", "weights")
    _square(covariance, n, "covariance")
    sigma = _symmetric(covariance, "covariance")
    sw = _matvec(sigma, weights)
    var = _dot(weights, sw)
    if not var > 0:
        raise QfError("E_DOMAIN", "w' Sigma w must be positive", "covariance")
    vol = math.sqrt(var)
    marginal = [x / vol for x in sw]
    contributions = [w * m for w, m in zip(weights, marginal, strict=True)]
    return {"volatility": vol, "marginal": marginal, "contributions": contributions,
            "shares": [c / vol for c in contributions]}


# --- Ledoit-Wolf (J-W2-7) ---------------------------------------------------------------------

def estimate_ledoit_wolf(returns: Matrix) -> dict[str, Any]:
    """`research.estimate.ledoit_wolf`: shrinkage towards `m I` [LW04], divisor `T`."""
    t = len(returns)
    if t < 2:
        raise QfError("E_INPUT", "need at least two rows", "returns")
    n = len(returns[0])
    if n < 1 or any(len(r) != n for r in returns):
        raise QfError("E_INPUT", "rows must be non-empty and of equal length", "returns")
    means = [sum(r[j] for r in returns) / t for j in range(n)]
    x = [[r[j] - means[j] for j in range(n)] for r in returns]
    s = [[sum(row[i] * row[j] for row in x) / t for j in range(n)] for i in range(n)]
    m = sum(s[i][i] for i in range(n)) / n
    d2 = sum((s[i][j] - (m if i == j else 0.0)) ** 2 for i in range(n) for j in range(n)) / n
    acc = 0.0
    for row in x:
        acc += sum((row[i] * row[j] - s[i][j]) ** 2 for i in range(n) for j in range(n))
    bbar2 = acc / (t * t) / n
    b2 = min(bbar2, d2)
    delta = 0.0 if b2 == 0 else b2 / d2
    cov = [[(1 - delta) * s[i][j] + (delta * m if i == j else 0.0) for j in range(n)]
           for i in range(n)]
    return {"covariance": cov, "shrinkage": delta, "mu": m}


# --- Black-Litterman (J-W2-8) -----------------------------------------------------------------

def estimate_black_litterman(covariance: Matrix, prior_returns: Sequence[float], pick: Matrix,
                             views: Sequence[float], view_covariance: Matrix,
                             tau: float) -> dict[str, Any]:
    """`research.estimate.black_litterman`: [HL99] update form, K x K Cholesky solve only."""
    n, k = len(prior_returns), len(views)
    if n < 1:
        raise QfError("E_INPUT", "need at least one asset", "prior_returns")
    _square(covariance, n, "covariance")
    if k < 1:
        raise QfError("E_INPUT", "need at least one view", "views")
    if len(pick) != k or any(len(r) != n for r in pick):
        raise QfError("E_INPUT", "pick must be K x N", "pick")
    _square(view_covariance, k, "view_covariance")
    if not tau > 0:
        raise QfError("E_DOMAIN", "tau must be positive", "tau")
    sigma = _symmetric(covariance, "covariance")
    _cholesky(sigma, "covariance")
    omega = _symmetric(view_covariance, "view_covariance")
    _cholesky(omega, "view_covariance")
    ts = [[tau * x for x in r] for r in sigma]
    bt = [_matvec(ts, p) for p in pick]  # rows of (tau Sigma P')', K x N
    mat = [[_dot(pick[a], bt[c]) + omega[a][c] for c in range(k)] for a in range(k)]
    low = _cholesky(mat, "view_covariance")
    resid = [q - _dot(p, prior_returns) for q, p in zip(views, pick, strict=True)]
    z = _chol_solve(low, resid)
    post = [prior_returns[i] + sum(bt[a][i] * z[a] for a in range(k)) for i in range(n)]
    cols = [_chol_solve(low, [bt[a][j] for a in range(k)]) for j in range(n)]
    pc = [[ts[i][j] - sum(bt[a][i] * cols[j][a] for a in range(k)) for j in range(n)]
          for i in range(n)]
    pc = [[pc[min(i, j)][max(i, j)] for j in range(n)] for i in range(n)]
    pred = [[sigma[i][j] + pc[i][j] for j in range(n)] for i in range(n)]
    return {"posterior_returns": post, "posterior_covariance": pc, "predictive_covariance": pred}


# --- Acerbi-Szekely Z2 (J-W2-10) --------------------------------------------------------------

def backtest_es_z2(losses: Sequence[float], var: Sequence[float], es: Sequence[float],
                   alpha: float) -> dict[str, Any]:
    """`risk.backtest.es_z2`: `Z2 = 1 - sum L_t 1{L_t > VaR_t} / (T alpha ES_t)` [AS14]."""
    t = len(losses)
    if t < 1 or len(var) != t or len(es) != t:
        raise QfError("E_INPUT", "losses, var and es must be non-empty and of equal length",
                      "losses")
    if not 0 < alpha < 1:
        raise QfError("E_DOMAIN", "alpha must lie in (0, 1)", "alpha")
    if any(not e > 0 for e in es):
        raise QfError("E_DOMAIN", "every es must be positive", "es")
    ta = t * alpha
    total, count = 0.0, 0
    for loss, v, e in zip(losses, var, es, strict=True):
        if loss > v:
            total += loss / (ta * e)
            count += 1
    return {"z2": 1.0 - total, "exceptions": count, "expected_exceptions": ta}


# --- Baum-Welch (J-W2-9, J-W2-11 to J-W2-13) --------------------------------------------------

def _e_step(y: Sequence[float], pi: Sequence[float], a: Matrix, mu: Sequence[float],
            sd: Sequence[float]) -> tuple[float, list[list[float]], list[list[float]]]:
    """Scaled forward-backward [Rab89, III.A]: log-likelihood, gamma (T x K), sum_t xi (K x K)."""
    t_len, k = len(y), len(pi)
    dens = [[math.exp(-0.5 * ((v - mu[j]) / sd[j]) ** 2) / (sd[j] * _SQRT_2PI)
             for j in range(k)] for v in y]
    alpha: list[list[float]] = []
    scale: list[float] = []
    prev: list[float] = []
    for t in range(t_len):
        if t == 0:
            hat = [pi[j] * dens[0][j] for j in range(k)]
        else:
            hat = [sum(prev[i] * a[i][j] for i in range(k)) * dens[t][j] for j in range(k)]
        c = sum(hat)
        if not c > 0:
            raise QfError("E_DOMAIN", "an observation has zero density under every state",
                          "observations")
        prev = [h / c for h in hat]
        alpha.append(prev)
        scale.append(c)
    beta = [[1.0] * k for _ in range(t_len)]
    for t in range(t_len - 2, -1, -1):
        nxt = [dens[t + 1][j] * beta[t + 1][j] for j in range(k)]
        beta[t] = [sum(a[i][j] * nxt[j] for j in range(k)) / scale[t + 1] for i in range(k)]
    gamma = [[alpha[t][i] * beta[t][i] for i in range(k)] for t in range(t_len)]
    xi = [[0.0] * k for _ in range(k)]
    for t in range(t_len - 1):
        c = scale[t + 1]
        for i in range(k):
            for j in range(k):
                xi[i][j] += alpha[t][i] * a[i][j] * dens[t + 1][j] * beta[t + 1][j] / c
    return sum(math.log(c) for c in scale), gamma, xi


def _m_step(y: Sequence[float], gamma: Matrix,
            xi: Matrix) -> tuple[list[float], list[list[float]], list[float], list[float]]:
    """Re-estimation [Rab89, eqs. 40a-40c] with the new means in the variance."""
    t_len, k = len(y), len(gamma[0])
    pi = list(gamma[0])
    a: list[list[float]] = []
    mu: list[float] = []
    sd: list[float] = []
    for i in range(k):
        head = sum(gamma[t][i] for t in range(t_len - 1))
        if not head > 0:
            raise QfError("E_DOMAIN", "a transition update has a zero denominator", "transition")
        a.append([xi[i][j] / head for j in range(k)])
        total = head + gamma[t_len - 1][i]
        m = sum(gamma[t][i] * y[t] for t in range(t_len)) / total
        v = sum(gamma[t][i] * (y[t] - m) ** 2 for t in range(t_len)) / total
        if not v > 0:
            raise QfError("E_DOMAIN", "a state variance collapsed to zero", "sds")
        mu.append(m)
        sd.append(math.sqrt(v))
    return pi, a, mu, sd


def regime_baum_welch(observations: Sequence[float], initial: Sequence[float],
                      transition: Matrix, means: Sequence[float], sds: Sequence[float],
                      tolerance: float = 1e-10, max_iterations: int = 1000) -> dict[str, Any]:
    """`research.regime.baum_welch`: EM from the start values, iteration as ruling J-W2-11."""
    k, t_len = len(initial), len(observations)
    if k < 1 or len(transition) != k or any(len(r) != k for r in transition):
        raise QfError("E_INPUT", "transition must be K x K with K >= 1", "transition")
    if len(means) != k or len(sds) != k:
        raise QfError("E_INPUT", "means and sds must have length K", "means")
    if t_len < 2:
        raise QfError("E_INPUT", "need at least two observations", "observations")
    if max_iterations < 1:
        raise QfError("E_INPUT", "max_iterations must be at least 1", "max_iterations")
    _check_probabilities([initial], "initial")
    _check_probabilities(transition, "transition")
    if any(not s > 0 for s in sds):
        raise QfError("E_DOMAIN", "sds must be positive", "sds")
    if not tolerance > 0:
        raise QfError("E_DOMAIN", "tolerance must be positive", "tolerance")
    pi, a, mu, sd = list(initial), [list(r) for r in transition], list(means), list(sds)
    loglik, gamma, xi = _e_step(observations, pi, a, mu, sd)
    iterations, converged = 0, False
    while iterations < max_iterations:
        iterations += 1
        pi, a, mu, sd = _m_step(observations, gamma, xi)
        new, gamma, xi = _e_step(observations, pi, a, mu, sd)
        gain, loglik = new - loglik, new
        if gain < tolerance:
            converged = True
            break
    return {"initial": pi, "transition": a, "means": mu, "sds": sd, "log_likelihood": loglik,
            "iterations": iterations, "converged": converged}


guard(globals())
