"""xVA on given paths: collateralised exposure, valuation adjustments, sensitivity-based IR delta
margin, Hull-White wrong-way risk, and the model-reserve dispersion statistic.

Specifications: specifications/06-risk/xva-framework.md (rulings G-40 to G-44) and
specifications/06-risk/model-reserve.md (ruling G-36).
"""

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .errors import QfError
from .finite import guard
from .numeric import ordered_sum

Floats = Sequence[float]


def _input(message: str, field: str) -> QfError:
    return QfError("E_INPUT", message, field)


def _domain(message: str, field: str) -> QfError:
    return QfError("E_DOMAIN", message, field)


def _increasing(values: Floats) -> bool:
    return all(a < b for a, b in itertools.pairwise(values))


# --- collateralised exposure (G-40) --------------------------------------------------------------


@dataclass(frozen=True)
class Csa:
    threshold_receive: float
    threshold_post: float
    minimum_transfer_amount: float
    mpor_steps: int
    independent_amount: float = 0.0


def _collateral(values: Floats, csa: Csa) -> list[float]:
    def target(v: float) -> float:
        return (
            max(v - csa.threshold_receive, 0.0)
            - max(-v - csa.threshold_post, 0.0)
            + csa.independent_amount
        )

    calls = [target(values[0])]
    for v in values[1:]:
        t = target(v)
        calls.append(t if abs(t - calls[-1]) >= csa.minimum_transfer_amount else calls[-1])
    lag = csa.mpor_steps
    return [calls[max(i - lag, 0)] for i in range(len(values))]


def collateralised(
    times: Floats,
    trades: Sequence[tuple[str, Sequence[Floats]]],
    csa: Mapping[str, Csa],
    pfe_quantile: float,
) -> dict[str, object]:
    """`xva.exposure.collateralised`: EE, ENE, PFE, EPE and effective EPE per netting set."""
    if len(times) < 2 or not _increasing(times):
        raise _input("times needs at least two increasing times", "times")
    if not trades:
        raise _input("trades needs at least one trade", "trades")
    n = len(times)
    sets: dict[str, list[list[float]]] = {}
    for name, paths in trades:
        if not paths or any(len(p) != n for p in paths):
            raise _input("every path needs one value per time", "trades")
        if name in sets:
            if len(sets[name]) != len(paths):
                raise _input("trades of one set need the same number of paths", "trades")
            sets[name] = [
                [a + b for a, b in zip(x, y, strict=True)]
                for x, y in zip(sets[name], paths, strict=True)
            ]
        else:
            sets[name] = [list(p) for p in paths]
    for name, c in csa.items():
        for key, value in (
            ("threshold_receive", c.threshold_receive),
            ("threshold_post", c.threshold_post),
            ("minimum_transfer_amount", c.minimum_transfer_amount),
        ):
            if not value >= 0:
                raise _domain(f"{key} must be >= 0", f"csa.{name}.{key}")
        if c.mpor_steps < 0:
            raise _domain("mpor_steps must be >= 0", f"csa.{name}.mpor_steps")
    for name in csa:
        if name not in sets:
            raise _input(f"CSA for {name}, which has no trades", "csa")
    if not 0 < pfe_quantile <= 1:
        raise _domain("pfe_quantile must be in (0, 1]", "pfe_quantile")
    out: dict[str, object] = {}
    total = [0.0] * n
    span = times[-1] - times[0]
    year = [i for i in range(1, n) if times[i] - times[0] <= 1.0]
    for name in sorted(sets):
        paths = sets[name]
        count = len(paths)
        exp_paths, neg_paths = [], []
        for p in paths:
            coll = _collateral(p, csa[name]) if name in csa else [0.0] * n
            exp_paths.append([max(v - c, 0.0) for v, c in zip(p, coll, strict=True)])
            neg_paths.append([min(v - c, 0.0) for v, c in zip(p, coll, strict=True)])
        ee = [ordered_sum(e[i] for e in exp_paths) / count for i in range(n)]
        ene = [ordered_sum(e[i] for e in neg_paths) / count for i in range(n)]
        rank = math.ceil(pfe_quantile * count)
        pfe = [sorted(e[i] for e in exp_paths)[rank - 1] for i in range(n)]
        epe = ordered_sum(ee[i] * (times[i] - times[i - 1]) for i in range(1, n)) / span
        eee = [ee[0]]
        for v in ee[1:]:
            eee.append(max(eee[-1], v))
        eff = (
            (
                ordered_sum(eee[i] * (times[i] - times[i - 1]) for i in year)
                / (times[year[-1]] - times[0])
            )
            if year
            else eee[0]
        )
        out[name] = {"ee": ee, "ene": ene, "pfe": pfe, "epe": epe, "effective_epe": eff}
        total = [a + b for a, b in zip(total, ee, strict=True)]
    return {"netting_sets": out, "total_ee": total}


# --- adjustments (G-41) ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Name:
    hazard_rate: float
    recovery: float


def _check_name(n: Name, key: str) -> None:
    if not n.hazard_rate >= 0:
        raise _domain("hazard_rate must be >= 0", f"{key}.hazard_rate")
    if not 0 <= n.recovery < 1:
        raise _domain("recovery must be in [0, 1)", f"{key}.recovery")


def adjustments(
    times: Floats,
    dfs: Floats,
    ee: Floats,
    ene: Floats,
    cpty: Name,
    own: Name,
    borrow_spread: float,
    lend_spread: float,
    exclude_overlap: bool,
    im: Floats | None,
    im_spread: float | None,
    capital: Floats | None,
    hurdle_rate: float | None,
) -> dict[str, float]:
    """`xva.adjustments.value`: CVA, DVA, FCA, FBA, FVA and the optional MVA and KVA."""
    n = len(times)
    if n < 1 or not _increasing(times) or not times[0] > 0:
        raise _input("times must be increasing and above 0", "times")
    for key, arr in (("discount_factors", dfs), ("ee", ee), ("ene", ene)):
        if len(arr) != n:
            raise _input(f"{key} needs one value per time", key)
    if (im is None) != (im_spread is None):
        raise _input("im and im_spread go together", "im")
    if (capital is None) != (hurdle_rate is None):
        raise _input("capital and hurdle_rate go together", "capital")
    for key, arr2 in (("im", im), ("capital", capital)):
        if arr2 is not None and len(arr2) != n:
            raise _input(f"{key} needs one value per time", key)
    _check_name(cpty, "counterparty")
    _check_name(own, "own")
    if any(not e >= 0 for e in ee):
        raise _domain("ee must be >= 0", "ee")
    if any(not e <= 0 for e in ene):
        raise _domain("ene must be <= 0", "ene")
    prev = [0.0, *times[:-1]]

    def sc(t: float) -> float:
        return math.exp(-cpty.hazard_rate * t)

    def sb(t: float) -> float:
        return math.exp(-own.hazard_rate * t)

    def qc(t: float, p: float) -> float:
        # bucket default probability S(p) - S(t) written as S(p) (1 - e^(-h (t - p))): no cancellation at tiny h
        return sc(p) * -math.expm1(-cpty.hazard_rate * (t - p))

    def qb(t: float, p: float) -> float:
        return sb(p) * -math.expm1(-own.hazard_rate * (t - p))

    def funding(profile: Floats) -> float:
        return ordered_sum(
            d * x * sc(p) * sb(p) * (t - p)
            for d, x, t, p in zip(dfs, profile, times, prev, strict=True)
        )

    cva = (1 - cpty.recovery) * ordered_sum(
        d * e * qc(t, p) * sb(p) for d, e, t, p in zip(dfs, ee, times, prev, strict=True)
    )
    dva = (1 - own.recovery) * ordered_sum(
        d * abs(e) * qb(t, p) * sc(p)
        for d, e, t, p in zip(dfs, ene, times, prev, strict=True)
    )
    s_l = (
        max(lend_spread - own.hazard_rate * (1 - own.recovery), 0.0)
        if exclude_overlap
        else lend_spread
    )
    fca = borrow_spread * funding(ee)
    fba = s_l * funding([abs(e) for e in ene])
    out = {"cva": cva, "dva": dva, "fca": fca, "fba": fba, "fva": fca - fba}
    if im is not None and im_spread is not None:
        out["mva"] = im_spread * funding(im)
    if capital is not None and hurdle_rate is not None:
        out["kva"] = hurdle_rate * funding(capital)
    return out


# --- sensitivity-based IR delta margin (G-43, KR-152) --------------------------------------


def sbim_ir_delta(
    sensitivities: Floats, risk_weights: Floats, correlations: Sequence[Floats], threshold: float
) -> dict[str, object]:
    """`xva.sbim.ir_delta` (deprecated alias `xva.simm.ir_delta`, KR-152): weighted sensitivities,
    concentration factor and margin."""
    n = len(sensitivities)
    if (
        n < 1
        or len(risk_weights) != n
        or len(correlations) != n
        or any(len(r) != n for r in correlations)
    ):
        raise _input("sensitivities, risk_weights and correlations must match", "sensitivities")
    if not threshold > 0:
        raise _domain("concentration_threshold must be above 0", "concentration_threshold")
    if any(not w >= 0 for w in risk_weights):
        raise _domain("risk weights must be >= 0", "risk_weights")
    if any(not -1 <= c <= 1 for r in correlations for c in r):
        raise _domain("correlations must be in [-1, 1]", "correlations")
    cr = max(1.0, math.sqrt(abs(ordered_sum(sensitivities)) / threshold))
    ws = [w * s * cr for w, s in zip(risk_weights, sensitivities, strict=True)]
    total = ordered_sum(
        (1.0 if k == m else correlations[k][m]) * ws[k] * ws[m] for k in range(n) for m in range(n)
    )
    return {
        "weighted_sensitivities": ws,
        "concentration_factor": cr,
        "margin": math.sqrt(max(0.0, total)),
    }


# --- wrong-way risk (G-44) ------------------------------------------------------------------------


def wwr_cva(
    times: Floats,
    values: Sequence[Floats],
    dfs: Floats,
    hazard_rate: float,
    recovery: float,
    b: float,
) -> dict[str, object]:
    """`xva.xva.wwr.cva_hw`: Hull-White (2012) hazard `exp(a_i + b V)`, `a_i` fitted per bucket so
    the path-mean survival equals `exp(-h t_i)`."""
    n = len(times)
    if n < 1 or not _increasing(times) or not times[0] > 0:
        raise _input("times must be increasing and above 0", "times")
    if not values or any(len(p) != n for p in values) or len(dfs) != n:
        raise _input("every path and discount_factors need one value per time", "values")
    if not hazard_rate > 0:
        raise _domain("hazard_rate must be above 0", "hazard_rate")
    if not 0 <= recovery < 1:
        raise _domain("recovery must be in [0, 1)", "recovery")
    if any(abs(b * v) > WWR_MAX_BV for p in values for v in p):
        raise _domain("|wwr_b * value| must be at most 700 (KR-257)", "wwr_b")
    prev = 0.0
    for t in times:
        if (
            math.exp(-hazard_rate * t) < _MIN_NORMAL
            or -math.expm1(-hazard_rate * (t - prev)) < _MIN_NORMAL
        ):
            raise QfError(
                "E_NON_FINITE",
                "the survival target or a bucket default probability is below the smallest normal double",
                "hazard_rate",
            )
        prev = t
    count = len(values)
    surv = [1.0] * count
    a_out, buckets = [], []
    prev = 0.0
    for i, t in enumerate(times):
        dt = t - prev
        cs = [b * p[i] for p in values]
        a = _wwr_root(surv, cs, dt, hazard_rate)
        qr = [_wwr_terms(a + c, dt) for c in cs]
        buckets.append(
            dfs[i]
            * ordered_sum(
                max(p[i], 0.0) * s * x[0] for p, s, x in zip(values, surv, qr, strict=True)
            )
            / count
        )
        surv = [s * x[1] for s, x in zip(surv, qr, strict=True)]
        a_out.append(a)
        prev = t
    return {"cva": (1 - recovery) * ordered_sum(buckets), "a": a_out}


WWR_MAX_BV = 700.0
_MIN_NORMAL = 2.2250738585072014e-308


def _wwr_terms(z: float, dt: float) -> tuple[float, float, float]:
    """For hazard `exp(z)` over `dt`: default probability `q = 1 - e^-x`, survival `r = e^-x` and
    `dq/dz = x e^-x`, with `x = exp(z) dt`; an overflowing `exp(z)` is `inf` (q = 1, r = 0)."""
    x = (math.inf if z > 709.0 else math.exp(z)) * dt
    r = math.exp(-x)
    return -math.expm1(-x), r, 0.0 if r == 0.0 else x * r


def _wwr_root(surv: list[float], cs: list[float], dt: float, h: float) -> float:
    """KR-257: `a` with `sum_p S_p (1 - e^(-x_p)) = (1 - e^(-h dt)) sum_p S_p`, `x_p = exp(a + c_p) dt`
    (the G-44 equation divided through by `S(t_(i-1))`; above a bucket default probability of 1/2 the
    survival form `sum_p S_p e^(-x_p) = e^(-h dt) sum_p S_p`). Bracket `[ln h - max c - 1,
    ln h - min c + 1]` (closed form, sign change by monotonicity), safeguarded Newton (rtsafe) from
    `ln h - (S-weighted mean of c)`, step to 1e-15 relative, at most 200 iterations."""
    q_t, r_t = -math.expm1(-h * dt), math.exp(-h * dt)
    use_q = q_t <= 0.5
    total = ordered_sum(surv)

    def f(a: float) -> tuple[float, float]:
        terms = [_wwr_terms(a + c, dt) for c in cs]
        if use_q:
            val = ordered_sum(s * x[0] for s, x in zip(surv, terms, strict=True)) - q_t * total
        else:
            val = r_t * total - ordered_sum(s * x[1] for s, x in zip(surv, terms, strict=True))
        return val, ordered_sum(s * x[2] for s, x in zip(surv, terms, strict=True))

    ln_h = math.log(h)
    lo, hi = ln_h - max(cs) - 1.0, ln_h - min(cs) + 1.0
    a = ln_h - ordered_sum(s * c for s, c in zip(surv, cs, strict=True)) / total
    dx = hi - lo
    val, der = f(a)
    for _ in range(200):
        if val > 0:
            hi = a
        elif val < 0:
            lo = a
        else:
            return a
        dx_old, dx = dx, (val / der if der > 0 else math.inf)
        step = a - dx
        if not (lo < step < hi and abs(dx) <= 0.5 * abs(dx_old)):
            dx = 0.5 * (hi - lo)
            step = lo + dx
        if abs(step - a) <= 1e-15 * max(1.0, abs(a)):
            return step
        a = step
        val, der = f(a)
    raise QfError(
        "E_NO_CONVERGENCE", "the a(t) root did not converge in 200 steps", "wwr_b"
    )  # pragma: no cover


# --- model reserve (G-36) -------------------------------------------------------------------------


def dispersion(prices: Mapping[str, float], reference: str) -> dict[str, object]:
    """`risk.model_reserve.dispersion`: mean, range, reserve against the booked model."""
    if len(prices) < 2:
        raise _input("prices needs at least two models", "prices")
    if reference not in prices:
        raise _input(f"{reference} is not a key of prices", "reference_model")
    names = sorted(prices)
    values = [prices[k] for k in names]
    ref = prices[reference]
    spread = max(values) - min(values)
    devs = [abs(prices[k] - ref) for k in names]
    reserve = max(devs)
    worst = names[devs.index(reserve)]
    return {
        "mean": ordered_sum(values) / len(values),
        "range": spread,
        "half_range": spread / 2,
        "reserve": reserve,
        "worst_model": worst,
        "relative_reserve": None if ref == 0 else reserve / abs(ref),
    }


guard(globals())
