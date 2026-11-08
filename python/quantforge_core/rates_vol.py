"""Stage E, E4: SABR swaption cube, caplet stripping, bond futures options and inflation caps.

Spec: specifications/05-volatility/rates-vol-cube.md, rulings E-B8 to E-B13 in
specifications/stage-e-rulings-b.md. Caps and swaptions are D7's (stage_d3.py); the smile is the
stage C Hagan expansion (sabr.py).
"""
import itertools
from collections.abc import Callable, Sequence

from . import black, curves, daycount, projection, roots, sabr
from .black import Option
from .curves import CurveData
from .errors import QfError
from .numeric import ordered_sum
from .stage_d3 import INDEX, _check_black, _check_tenor, _option

Matrix = Sequence[Sequence[float]]


def _input(message: str, field: str | None = None) -> QfError:
    return QfError("E_INPUT", message, field)


def _domain(message: str, field: str | None = None) -> QfError:
    return QfError("E_DOMAIN", message, field)


def _increasing(values: Sequence[float]) -> bool:
    return all(a < b for a, b in itertools.pairwise(values))


# --- SABR cube ---

def _locate(nodes: Sequence[float], x: float, field: str) -> tuple[int, float]:
    """(i, weight) with nodes[i] <= x <= nodes[i + 1]; a single node needs x on it."""
    if not nodes[0] <= x <= nodes[-1]:
        raise _input(f"{field} is outside the cube", field)
    if len(nodes) == 1:
        return 0, 0.0
    i = max(j for j in range(len(nodes) - 1) if nodes[j] <= x)
    return i, (x - nodes[i]) / (nodes[i + 1] - nodes[i])


def _bilinear(m: Matrix, i: int, u: float, j: int, v: float) -> float:
    i1, j1 = min(i + 1, len(m) - 1), min(j + 1, len(m[0]) - 1)
    return ((1 - u) * (1 - v) * m[i][j] + (1 - u) * v * m[i][j1]
            + u * (1 - v) * m[i1][j] + u * v * m[i1][j1])


def price_cube(
    discount: CurveData, proj: CurveData, expiries_months: Sequence[int],
    tenors_months: Sequence[int], params: dict[str, Matrix], kind: str, expiry_months: int,
    tenor_months: int, strike: float, notional: float,
) -> dict[str, object]:
    d, p = curves.build(discount), curves.build(proj)
    rows, cols = len(expiries_months), len(tenors_months)
    if rows == 0 or cols == 0 or any(
            len(m) != rows or any(len(r) != cols for r in m) for m in params.values()):
        raise _input("each parameter must be expiries x tenors", "cube")
    if not _increasing(expiries_months) or not _increasing(tenors_months):
        raise _input("node months must be strictly increasing", "cube")
    if expiry_months < 1:
        raise _input("expiry_months must be at least 1", "expiry_months")
    _check_tenor(tenor_months)
    spot = projection._spot(INDEX, d.as_of)
    node_times = [d.time(projection._plus_months(INDEX, spot, m)) for m in expiries_months]
    node_tenors = [m / 12 for m in tenors_months]
    s = projection._plus_months(INDEX, spot, expiry_months)
    t = d.time(s)
    i, u = _locate(node_times, t, "expiry_months")
    j, v = _locate(node_tenors, tenor_months / 12, "tenor_months")
    alpha, beta, rho, nu = (_bilinear(params[k], i, u, j, v)
                            for k in ("alpha", "beta", "rho", "nu"))
    fixed = projection._fixed_periods(INDEX, s, tenor_months)
    floating = projection._float_periods(INDEX, s, tenor_months)
    annuity, leg = projection._swap_legs(INDEX, fixed, floating, d, p)
    forward = leg / annuity
    # Node parameters are checked, so every interpolated value is in range too.
    cells = {k: [x for row in m for x in row] for k, m in params.items()}
    if any(x <= 0 for x in cells["alpha"]):
        raise _domain("alpha must be above 0", "cube")
    if any(not 0 <= x <= 1 for x in cells["beta"]):
        raise _domain("beta must be in [0, 1]", "cube")
    if any(abs(x) >= 1 for x in cells["rho"]):
        raise _domain("|rho| must be below 1", "cube")
    if any(x < 0 for x in cells["nu"]):
        raise _domain("nu is negative", "cube")
    if strike <= 0:
        raise _domain("strike must be above 0", "strike")
    if forward <= 0:
        raise _domain("the forward rate is not above 0", "strike")
    vol = sabr._hagan(sabr.Sabr(forward, t, alpha, beta, rho, nu), strike)
    price = notional * annuity * _option(black.BLACK_76, kind == "PAYER", forward, strike, vol, t)
    return {"price": price, "forward_rate": forward, "annuity": annuity, "vol": vol,
            "sabr": {"alpha": alpha, "beta": beta, "rho": rho, "nu": nu}}


# --- Caplet stripping ---

def _solve(f: Callable[[float], float], low: float, high: float) -> float:
    return roots.brent(f, low, high, x_tol=1e-15, max_iter=500).root


def cap_strip(
    discount: CurveData, proj: CurveData, model: str, start_months: int, strike: float,
    tenors: Sequence[int], flat_vols: Sequence[float], notional: float,
) -> tuple[list[float], list[float]]:
    d, p = curves.build(discount), curves.build(proj)
    if not tenors or any(m % 3 for m in tenors):
        raise _input("cap tenors must be multiples of 3 months", "cap_tenors_months")
    if not _increasing(tenors):
        raise _input("cap tenors must be strictly increasing", "cap_tenors_months")
    if len(flat_vols) != len(tenors):
        raise _input("one flat vol per cap tenor", "flat_vols")
    if any(v <= 0 for v in flat_vols):
        raise _domain("a flat vol is not above 0", "flat_vols")
    if start_months < 1:
        raise _input("start_months must be at least 1", "start_months")
    _check_tenor(tenors[-1])
    start = projection._plus_months(INDEX, projection._spot(INDEX, d.as_of), start_months)
    ps = projection._float_periods(INDEX, start, tenors[-1])
    alphas = [daycount.year_fraction("ACT_360", x.start, x.end) for x in ps]
    forwards = [(p.discount(x.start) / p.discount(x.end) - 1) / a
                for x, a in zip(ps, alphas, strict=True)]
    _check_black(model, strike, forwards)
    terms = [(notional * a * d.discount(x.end), f, d.time(x.start))
             for x, a, f in zip(ps, alphas, forwards, strict=True)]

    def caplet(n: int, vol: float) -> float:
        scale, f, t = terms[n]
        return scale * _option(model, True, f, strike, vol, t)

    low = 1e-6 if model == black.BLACK_76 else 1e-7
    vols: list[float] = []
    targets = []
    for count_months, flat in zip(tenors, flat_vols, strict=True):
        n = count_months // 3
        target = ordered_sum(caplet(c, flat) for c in range(n))
        targets.append(target)
        first = len(vols)

        # The caplets fixed by shorter caps are summed once; the new ones are added on in order.
        known = ordered_sum(caplet(c, vols[c]) for c in range(first))

        def gap(v: float, first: int = first, n: int = n, target: float = target,
                known: float = known) -> float:
            total = known
            for c in range(first, n):
                total += caplet(c, v)
            return total - target

        if gap(low) >= 0:
            raise QfError("E_ARBITRAGE", "a caplet segment needs a vol at or below zero",
                          "flat_vols")
        high = max(flat_vols) * 2
        while gap(high) < 0:
            high *= 2
            if high > 1e6:
                raise QfError("E_NO_CONVERGENCE", "no caplet vol bracket", "flat_vols")
        vols += [_solve(gap, low, high)] * (n - first)
    return vols, targets


# --- Bond futures options ---

def _futures_option(kind: str, f: float, k: float, t: float, df: float) -> Option:
    if t <= 0:
        raise _domain("expiry_years must be above 0", "expiry_years")
    if f <= 0:
        raise _domain("futures_price must be above 0", "futures_price")
    if k <= 0:
        raise _domain("strike must be above 0", "strike")
    if df <= 0:
        raise _domain("discount_factor must be above 0", "discount_factor")
    return Option(black.BLACK_76, kind, k, t, f, discount_factor=df)


def bondfut_price(kind: str, f: float, k: float, t: float, df: float, vol: float,
                  contract_size: float) -> tuple[float, float]:
    price = black.price(_futures_option(kind, f, k, t, df), vol)
    return price, price * contract_size / 100


def bondfut_implied(kind: str, f: float, k: float, t: float, df: float, premium: float,
                    ctd_yield: float, duration: float) -> tuple[float, float]:
    o = _futures_option(kind, f, k, t, df)
    intrinsic = df * max(o.phi * (f - k), 0.0)
    bound = df * (f if kind == "CALL" else k)
    if not intrinsic < premium < bound:
        raise _domain("the premium has no implied vol", "premium")

    def gap(v: float) -> float:
        return black.price(o, v) - premium

    high = 1.0
    while gap(high) < 0:
        high *= 2
        if high > 1e6:
            raise QfError("E_NO_CONVERGENCE", "no implied vol bracket", "premium")
    price_vol = _solve(gap, 0.0, high)
    return price_vol, price_vol / (duration * ctd_yield)


# --- Inflation caps ---

def _inflation_option(model: str, kind: str, f: float, k: float, vol: float, t: float) -> float:
    return black.price(Option(model, "CALL" if kind == "CAP" else "PUT", k, t, f), vol)


def yoy_price(model: str, kind: str, strike: float, notional: float,
              periods: Sequence[tuple[float, float, float, float, float]]
              ) -> tuple[list[float], float]:
    if not periods:
        raise _input("periods is empty", "periods")
    if model == black.BLACK_76 and (strike <= 0 or any(p[2] <= 0 for p in periods)):
        raise _domain("BLACK_76 needs a positive strike and forwards", "strike")
    if any(p[3] <= 0 for p in periods):
        raise _domain("an expiry_years is not above 0", "periods")
    caplets = [notional * accrual * _inflation_option(model, kind, f, strike, vol, t) * df
               for accrual, df, f, t, vol in periods]
    return caplets, ordered_sum(caplets)


def zc_price(model: str, kind: str, forward_ratio: float, years: float, strike: float,
             df: float, vol: float, notional: float) -> tuple[float, float]:
    if model == black.BLACK_76 and forward_ratio <= 0:
        raise _domain("BLACK_76 needs a positive forward", "forward_index_ratio")
    if 1 + strike <= 0:  # SPEC_QUESTIONS E-Q8: (1 + K)^T needs 1 + K above 0
        raise _domain("1 + strike must be above 0", "strike")
    if years <= 0:
        raise _domain("years must be above 0", "years")
    ratio = (1 + strike) ** years
    return notional * df * _inflation_option(model, kind, forward_ratio, ratio, vol, years), ratio
