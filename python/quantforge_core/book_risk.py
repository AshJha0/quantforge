"""Book sensitivities by the IFT chain rule, curve PCA, cross gamma, jump to default
(specifications/06-risk/book-sensitivities.md, rulings F-29 and F-30)."""
import math
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date

from . import curves, linalg, ois
from .curves import Curve, CurveData
from .errors import QfError
from .finite import guard
from .ois import Quote
from .schedules import Period

Gradient = dict[int, float]  # pillar index (0-based) -> d/dx_k


@dataclass(frozen=True)
class BookSwap:
    id: str
    tenor_years: int
    fixed_rate: float
    side: str


def _log_weights(curve: Curve, d: date) -> Gradient:
    """d ln D(d) / d x_k, x_k = ln D(pillar k). Exact for LOG_LINEAR_DF and LINEAR_ZERO, where
    ln D is linear in x; a Richardson central difference for the stage F methods."""
    t = curve.time(d)
    if t == 0:
        return {}
    ts = curve.times
    n = len(ts) - 1
    method = curve.interpolation
    if method not in ("LOG_LINEAR_DF", "LINEAR_ZERO"):
        return _numeric_weights(curve, d)
    out: Gradient = {}

    def add(node: int, w: float) -> None:
        if node > 0 and w != 0.0:
            out[node - 1] = out.get(node - 1, 0.0) + w

    if t >= ts[n]:
        if n == 1:
            add(1, t / ts[1])  # the forward of the single segment from the curve date
            return out
        h = ts[n] - ts[n - 1]
        add(n, 1 + (t - ts[n]) / h)
        add(n - 1, -(t - ts[n]) / h)
        return out
    i = bisect_right(ts, t) - 1
    u = (t - ts[i]) / (ts[i + 1] - ts[i])
    if method == "LOG_LINEAR_DF":
        add(i, 1 - u)
        add(i + 1, u)
    elif i == 0:
        add(1, t / ts[1])  # flat zero rate on the first segment
    else:
        add(i, t * (1 - u) / ts[i])
        add(i + 1, t * u / ts[i + 1])
    return out


def _numeric_weights(curve: Curve, d: date) -> Gradient:
    data = CurveData(curve.as_of, curve.interpolation, curve.dates,
                     tuple(math.exp(x) * curve.jump(p) for x, p in zip(curve.logs[1:], curve.dates,
                                                                       strict=True)),
                     curve.jumps, curve.tension, curve.step_end)
    out: Gradient = {}
    for k in range(len(curve.dates)):
        def at(h: float, k: int = k) -> float:
            f = list(data.discount_factors)
            f[k] *= math.exp(h)
            return math.log(Curve(replace(data, discount_factors=tuple(f))).discount(d))

        c1 = (at(1e-5) - at(-1e-5)) / 2e-5
        c2 = (at(5e-6) - at(-5e-6)) / 1e-5
        out[k] = (4 * c2 - c1) / 3
    return out


def _legs(convention: str, ps: Sequence[Period], curve: Curve
          ) -> tuple[float, float, Gradient, Gradient]:
    """(A, F, dA/dx, dF/dx) for the legs of ois-curves.md."""
    alphas = ois._alphas(convention, ps)
    cache: dict[date, tuple[float, Gradient]] = {}

    def disc(d: date) -> tuple[float, Gradient]:
        if d not in cache:
            cache[d] = (curve.discount(d), _log_weights(curve, d))
        return cache[d]

    annuity, floating = 0.0, 0.0
    d_a: Gradient = {}
    d_f: Gradient = {}
    for a, p in zip(alphas, ps, strict=True):
        dp, wp = disc(p.payment)
        annuity += a * dp
        for k, w in wp.items():
            d_a[k] = d_a.get(k, 0.0) + a * dp * w
    for p in ps:
        ds, ws = disc(p.start)
        de, we = disc(p.end)
        dp, wp = disc(p.payment)
        ratio = ds / de
        floating += (ratio - 1) * dp
        for k, w in ws.items():
            d_f[k] = d_f.get(k, 0.0) + ratio * w * dp
        for k, w in we.items():
            d_f[k] = d_f.get(k, 0.0) - ratio * w * dp
        for k, w in wp.items():
            d_f[k] = d_f.get(k, 0.0) + (ratio - 1) * dp * w
    return annuity, floating, d_a, d_f


def _inverse(a: list[list[float]]) -> list[list[float]]:
    """a^{-1}; forward substitution when a is lower triangular, so zeros above the diagonal
    stay exact (ruling F-30)."""
    n = len(a)
    lower = all(a[i][j] == 0.0 for i in range(n) for j in range(i + 1, n))
    cols = []
    for j in range(n):
        e = [1.0 if i == j else 0.0 for i in range(n)]
        if lower:
            x = [0.0] * n
            for i in range(n):
                acc = e[i]
                for k in range(i):
                    if a[i][k] != 0.0 and x[k] != 0.0:
                        acc -= a[i][k] * x[k]
                x[i] = acc / a[i][i] if acc != 0.0 else 0.0
            cols.append(x)
        else:
            cols.append(linalg.lu_solve(a, e))
    return [[cols[j][i] for j in range(n)] for i in range(n)]


def ois_sensitivity(as_of: date, convention: str, quotes: Sequence[Quote], interpolation: str,
                    swaps: Sequence[BookSwap]) -> dict[str, object]:
    if not swaps:
        raise QfError("E_INPUT", "the book has no swaps", "swaps")
    if any(s.tenor_years < 1 for s in swaps):
        raise QfError("E_DOMAIN", "tenor_years must be at least 1", "swaps")
    if len({s.id for s in swaps}) != len(swaps):
        raise QfError("E_INPUT", "duplicate swap id", "swaps")
    data, _ = ois.bootstrap(convention, as_of, quotes, interpolation)
    curve = curves.build(data)
    n = len(quotes)
    # dR/dx: R_j = F_j / A_j - q_j.
    d_r = []
    for q in quotes:
        ps = ois.periods(convention, as_of, q.tenor)
        a, f, d_a, d_f = _legs(convention, ps, curve)
        par = f / a
        d_r.append([(d_f.get(k, 0.0) - par * d_a.get(k, 0.0)) / a for k in range(n)])
    dx_dq = _inverse(d_r)  # -(dR/dx)^{-1} dR/dq with dR/dq = -I
    pvs, sens = [], []
    for s in swaps:
        ps = ois.periods(convention, as_of, f"{s.tenor_years}Y")
        a, f, d_a, d_f = _legs(convention, ps, curve)
        sign = 1.0 if s.side == "PAY" else -1.0
        pvs.append(sign * (f - s.fixed_rate * a))
        dpv = [sign * (d_f.get(k, 0.0) - s.fixed_rate * d_a.get(k, 0.0)) for k in range(n)]
        row = []
        for j in range(n):
            acc = 0.0
            for k in range(n):
                if dpv[k] != 0.0 and dx_dq[k][j] != 0.0:
                    acc += dpv[k] * dx_dq[k][j]
            row.append(acc)
        sens.append(row)
    times = [(p - as_of).days / 365 for p in data.dates]
    zero = [[-dx_dq[i][j] / times[i] if dx_dq[i][j] != 0.0 else 0.0 for j in range(n)]
            for i in range(n)]
    labels = [q.tenor for q in quotes]
    book = [0.0] * n
    for row in sens:
        for j in range(n):
            book[j] += row[j]
    return {
        "pv": pvs,
        "book_pv": sum(pvs),
        "quote_sensitivity": {"swaps": [s.id for s in swaps], "quotes": labels, "matrix": sens},
        "book_sensitivity": book,
        "zero_jacobian": {"pillars": [d.isoformat() for d in data.dates], "quotes": labels,
                          "matrix": zero},
    }


def pca(changes: Sequence[Sequence[float]], components: int) -> dict[str, object]:
    if components < 1:
        raise QfError("E_DOMAIN", "components must be at least 1", "components")
    t = len(changes)
    if t < 2:
        raise QfError("E_INPUT", "need at least 2 rows", "changes")
    width = len(changes[0])
    if width == 0 or any(len(r) != width for r in changes):
        raise QfError("E_INPUT", "rows must have the same length", "changes")
    if components > width:
        raise QfError("E_INPUT", "components above the tenor count", "components")
    import numpy  # loaded only here, to keep CLI start-up short

    x = numpy.array(changes, dtype=float)
    x = x - x.mean(axis=0)
    cov = (x.T @ x) / (t - 1)
    values, vectors = numpy.linalg.eigh(cov)
    order = numpy.argsort(values)[::-1]
    values, vectors = values[order], vectors[:, order]
    lam = [float(v) for v in values]
    upto = min(components + 1, width)
    for i in range(upto - 1):
        if abs(lam[i] - lam[i + 1]) < 1e-6 * lam[0]:
            raise QfError("E_DOMAIN", "repeated eigenvalue: loadings are not unique",
                          "components")
    loadings = []
    for i in range(components):
        v = [float(c) for c in vectors[:, i]]
        big = max(range(width), key=lambda k: (abs(v[k]), -k))
        if v[big] < 0:
            v = [-c for c in v]
        loadings.append(v)
    total = sum(lam)
    return {"eigenvalues": lam, "loadings": loadings,
            "explained_ratio": [lam[i] / total for i in range(components)]}


def cross_gamma(data: CurveData, trade: ois.OisTrade, bump_bp: float) -> dict[str, object]:
    """PILLAR cross gamma of an OIS trade. Each PV term is a product of discount factors,
    T0 exp(-h G.s) with G linear in the pillar shifts s (ln D is linear in the pillar ln D on
    the stage B methods), so the finite differences are written with sinh: no cancellation."""
    if not 0 < bump_bp <= 100:
        raise QfError("E_DOMAIN", "bump_bp must be in (0, 100]", "bump_bp")
    curve = curves.build(data)
    as_of = data.as_of
    ps = ois.periods(trade.convention, as_of, trade.tenor)
    v0 = ois.trade_pv(trade, ps, curve)[0]
    n = len(data.dates)
    times = [(d - as_of).days / 365 for d in data.dates]
    h = bump_bp * 1e-4
    sign = 1.0 if trade.side == "PAY" else -1.0
    scale = sign * trade.notional

    def g(d: date) -> Gradient:  # d ln D / d s_k per unit h: -t_k w_k
        return {k: -times[k] * w for k, w in _log_weights(curve, d).items()}

    terms: list[tuple[float, Gradient]] = []  # (coefficient * T0, exponent vector)
    for a, p in zip(ois._alphas(trade.convention, ps), ps, strict=True):
        terms.append((-trade.fixed_rate * a * curve.discount(p.payment), g(p.payment)))
    for p in ps:
        gs, ge, gp = g(p.start), g(p.end), g(p.payment)
        mono = dict(gs)
        for k, w in gp.items():
            mono[k] = mono.get(k, 0.0) + w
        for k, w in ge.items():
            mono[k] = mono.get(k, 0.0) - w
        value = curve.discount(p.start) * curve.discount(p.payment) / curve.discount(p.end)
        terms.append((value, mono))
        terms.append((-curve.discount(p.payment), gp))

    def sinh2(x: float) -> float:
        return 4 * math.sinh(x / 2) ** 2

    gamma = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            total = 0.0
            for c, mono in terms:
                gi, gj = mono.get(i, 0.0), mono.get(j, 0.0)
                if gi == 0.0 and gj == 0.0:
                    continue
                if i == j:
                    total += c * sinh2(h * gi)
                else:
                    total += c * (sinh2(h * (gi + gj)) - sinh2(h * (gi - gj))) / 4
            gamma[i][j] = gamma[j][i] = scale * total / bump_bp ** 2
    return {"value": v0, "cross_gamma": gamma}


JTD_KINDS = ("BOND", "CDS_PROTECTION_BUYER", "CDS_PROTECTION_SELLER")


def jtd(positions: Sequence[tuple[str, str, float, float, float]]) -> dict[str, object]:
    """positions: (id, kind, notional, recovery, market_value)."""
    if not positions:
        raise QfError("E_INPUT", "no positions", "positions")
    out = []
    for _, kind, notional, recovery, market in positions:
        if not notional >= 0:
            raise QfError("E_DOMAIN", "notional must not be negative", "positions")
        if not 0 <= recovery <= 1:
            raise QfError("E_DOMAIN", "recovery must be in [0, 1]", "positions")
        after = (recovery * notional if kind == "BOND" else
                 (1 - recovery) * notional if kind == "CDS_PROTECTION_BUYER" else
                 -(1 - recovery) * notional)
        out.append(after - market)
    return {"jtd": out, "total": sum(out)}


guard(globals())
