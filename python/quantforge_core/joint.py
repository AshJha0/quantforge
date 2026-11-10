"""Joint multi-curve solve, calibrated turns, futures-fitted meeting steps, funding curve
(specifications/02-curves/joint-solve-and-funding.md, rulings F-24 to F-27)."""
import itertools
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from . import curves, futures, linalg, ois, projection, xccy
from .curves import Curve, CurveData
from .errors import QfError
from .finite import guard
from .steps import StepCurve

Jumps = tuple[tuple[date, float], ...]
TOLERANCE = 1e-13
_H = 1e-7
_CURVE_TYPES = ("OIS", "OIS_STEPS", "PROJECTION", "XCCY")
_ALLOWED = {
    "OIS": ("OIS", "FUTURE"), "OIS_STEPS": ("OIS", "FUTURE"),
    "PROJECTION": ("DEPOSIT", "FRA", "SWAP"), "XCCY": ("XCCY",),
}


@dataclass
class CurveSpec:
    """One input curve, as read. Keys a type does not use stay at their defaults."""

    name: str
    type: str
    convention: str = ""
    interpolation: str = "LOG_LINEAR_DF"
    tension: float | None = None
    step_end: date | None = None
    jumps: Jumps = ()
    turns: tuple[date, ...] = ()
    step_dates: tuple[date, ...] = ()
    index: str = ""
    discount: str = ""
    domestic: str = ""
    foreign_projection: str = ""
    domestic_convention: str = ""
    foreign_convention: str = ""
    start: date | None = None


@dataclass
class InstrumentSpec:
    id: str
    curve: str
    type: str
    turn: bool = False
    tenor: str = ""
    rate: float = 0.0
    start: date | None = None
    end: date | None = None
    price: float = 0.0
    sigma: float = 0.0
    mean_reversion: float = 0.0
    months: int = 0
    start_months: int = 0
    spread: float = 0.0


Model = Callable[[dict[str, Any]], float]


@dataclass
class _Instrument:
    spec: InstrumentSpec
    model: Model
    target: float
    d_quote: float  # dR/dq
    dates: list[date]
    pillar: date | None
    spread_slope: Model | None = None  # XCCY: dR/dq depends on the solved curves


@dataclass
class _Block:
    spec: CurveSpec
    instruments: list[_Instrument] = field(default_factory=list)
    pillars: list[date] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    offset: int = 0

    @property
    def size(self) -> int:
        return len(self.labels)


def _check_increasing(as_of: date, dates: Sequence[date], key: str) -> None:
    if any(b <= a for a, b in itertools.pairwise([as_of, *dates])):
        raise QfError("E_INPUT", f"{key} must be increasing and after as_of", key)


def _check_structure(as_of: date, specs: Sequence[CurveSpec],
                     instruments: Sequence[InstrumentSpec]) -> None:
    seen: dict[str, CurveSpec] = {}
    for c in specs:
        if c.type not in _CURVE_TYPES:
            raise QfError("E_SCHEMA", f"unknown curve type {c.type}", "curves")
        refs = {"PROJECTION": [c.discount], "XCCY": [c.domestic, c.foreign_projection]}
        for ref in refs.get(c.type, []):
            if ref not in seen or seen[ref].type not in ("OIS", "OIS_STEPS"):
                raise QfError("E_INPUT", f"{c.name} names {ref}, not an earlier OIS curve",
                              "curves")
        if c.name in seen:
            raise QfError("E_INPUT", f"duplicate curve name {c.name}", "curves")
        seen[c.name] = c
    ids: set[str] = set()
    for inst in instruments:
        if inst.id in ids:
            raise QfError("E_INPUT", f"duplicate instrument id {inst.id}", "instruments")
        ids.add(inst.id)
        if inst.curve not in seen:
            raise QfError("E_INPUT", f"{inst.id} names an unknown curve", "instruments")
        if inst.type not in _ALLOWED[seen[inst.curve].type]:
            raise QfError("E_INPUT", f"{inst.type} cannot calibrate {inst.curve}", "instruments")
    for c in specs:
        _check_increasing(as_of, c.step_dates, "step_dates")
        _check_increasing(as_of, c.turns, "turns")
        mine = [i for i in instruments if i.curve == c.name]
        turns = sum(1 for i in mine if i.turn)
        if turns != len(c.turns):
            raise QfError("E_INPUT", f"{c.name} needs one turn instrument per turn",
                          "instruments")
        if c.type == "OIS_STEPS" and len(mine) != 1 + len(c.step_dates) + len(c.turns):
            raise QfError("E_INPUT", f"{c.name} needs 1 + steps + turns instruments",
                          "instruments")
        if c.type == "OIS_STEPS" and not c.step_dates:
            raise QfError("E_INPUT", "no step dates", "step_dates")


def _jumps(c: CurveSpec, turn_logs: Sequence[float]) -> Jumps:
    merged = sorted([*c.jumps, *((d, math.exp(x)) for d, x in zip(c.turns, turn_logs,
                                                                   strict=True))])
    return tuple(merged)


def _ois_instrument(as_of: date, c: CurveSpec, inst: InstrumentSpec) -> _Instrument:
    name = c.name
    if inst.type == "OIS":
        ps = ois.periods(c.convention, as_of, inst.tenor)
        conv = c.convention

        def par(cs: dict[str, Any]) -> float:
            return ois.par_rate(conv, ps, cs[name])

        dates = sorted({d for p in ps for d in (p.start, p.end, p.payment)})
        return _Instrument(inst, par, inst.rate, -1.0, dates, ps[-1].payment)
    assert inst.start is not None and inst.end is not None
    s, e = inst.start, inst.end
    if e <= s:
        raise QfError("E_INPUT", f"{inst.id}: end is not after start", "instruments")
    t, big_t = (s - as_of).days / 365, (e - as_of).days / 365
    rate, bias, _ = futures.convexity(inst.price, t, big_t, inst.sigma, inst.mean_reversion)
    z = futures.exponent(t, big_t, inst.sigma, inst.mean_reversion)
    alpha = (e - s).days / 360

    def simple(cs: dict[str, Any]) -> float:
        d = cs[name]
        value: float = (d.discount(s) / d.discount(e) - 1) / alpha
        return value

    return _Instrument(inst, simple, rate - bias, 0.01 * math.exp(-z), [s, e], e)


def _blocks(as_of: date, specs: Sequence[CurveSpec],
            instruments: Sequence[InstrumentSpec]) -> list[_Block]:
    blocks: list[_Block] = []
    offset = 0
    for c in specs:
        b = _Block(c)
        mine = [i for i in instruments if i.curve == c.name]
        if c.type in ("OIS", "OIS_STEPS"):
            b.instruments = [_ois_instrument(as_of, c, i) for i in mine]
        elif c.type == "PROJECTION":
            quotes = [projection.ProjectionQuote(
                i.type, i.start_months if i.type == "FRA" else i.months, i.rate) for i in mine]
            pillars, terms, dates = projection.term_models(c.index, as_of, quotes)
            for i, p, m, ds in zip(mine, pillars, terms, dates, strict=True):
                def model(cs: dict[str, Any], m: projection.TermModel = m,
                          own: str = c.name, disc: str = c.discount) -> float:
                    return m(cs[own], cs[disc])

                b.instruments.append(_Instrument(i, model, i.rate, -1.0, ds, p))
        else:
            assert c.start is not None
            if c.start < as_of:
                raise QfError("E_OUT_OF_RANGE", "start is before the curve date", "start")
            for i in mine:
                ends = xccy.schedule((c.domestic_convention, c.foreign_convention), c.start,
                                     i.months)

                def leg(cs: dict[str, Any], ends: list[date] = ends, spread: float = i.spread,
                        own: str = c.name, fp: str = c.foreign_projection,
                        start: date = c.start) -> float:
                    return xccy.leg(1.0, start, ends, cs[fp], cs[own], spread)

                def slope(cs: dict[str, Any], ends: list[date] = ends, own: str = c.name,
                          start: date = c.start) -> float:
                    """d L_foreign / d spread: the spread annuity on ACT/360."""
                    d = cs[own]
                    total = 0.0
                    for s, e in zip([start, *ends[:-1]], ends, strict=True):
                        total += (e - s).days / 360 * d.discount(e)
                    return total

                b.instruments.append(_Instrument(i, leg, 0.0, 0.0, [c.start, *ends], ends[-1],
                                                 slope))
        if c.type == "OIS_STEPS":
            b.labels = [f"{c.name}:base", *(f"{c.name}:step:{d}" for d in c.step_dates)]
        else:
            b.pillars = [x.pillar for x in b.instruments if not x.spec.turn
                         and x.pillar is not None]
            if any(q <= p for p, q in itertools.pairwise([as_of, *b.pillars])):
                raise QfError("E_INPUT", f"{c.name}: pillars are not increasing",
                              "instruments")
            curves.check_options(c.interpolation, c.tension, c.step_end, b.pillars)
            b.labels = [f"{c.name}:pillar:{d}" for d in b.pillars]
        b.labels += [f"{c.name}:turn:{d}" for d in c.turns]
        if b.size != len(b.instruments):
            raise QfError("E_INPUT", f"{c.name}: the system is not square", "instruments")
        curves.check_jumps(as_of, _jumps(c, [0.0] * len(c.turns)))
        b.offset = offset
        offset += b.size
        blocks.append(b)
    return blocks


def _curve(as_of: date, b: _Block, x: Sequence[float]) -> Any:
    c = b.spec
    own = x[b.offset:b.offset + b.size]
    turns = own[len(own) - len(c.turns):] if c.turns else []
    jumps = _jumps(c, turns)
    if c.type == "OIS_STEPS":
        m = len(c.step_dates)
        return StepCurve(as_of, own[0], list(zip(c.step_dates, own[1:m + 1], strict=True)),
                         jumps)
    n = len(b.pillars)
    return Curve(CurveData(as_of, c.interpolation, tuple(b.pillars),
                           tuple(math.exp(v) for v in own[:n]), jumps, c.tension, c.step_end))


def _residuals(as_of: date, blocks: Sequence[_Block], x: Sequence[float],
               upto: int | None = None) -> list[float]:
    """Residuals of blocks 0..upto (all by default), in block order."""
    cs: dict[str, Any] = {}
    out: list[float] = []
    last = len(blocks) - 1 if upto is None else upto
    for b in blocks[:last + 1]:
        cs[b.spec.name] = _curve(as_of, b, x)
        out += [i.model(cs) - i.target for i in b.instruments]
    return out


def _start(as_of: date, blocks: Sequence[_Block], x: list[float],
           only: int | None = None) -> None:
    """Flat curves at the first quote, steps at base_rate, turn factors 1."""
    for k, b in enumerate(blocks):
        if only is not None and k != only:
            continue
        c = b.spec
        first = b.instruments[0]
        level = first.target if c.type != "XCCY" else 0.0
        if c.type == "XCCY":
            # The foreign projection curve as solved so far is a better start than flat.
            fp = next(k for k in blocks if k.spec.name == c.foreign_projection)
            curve = _curve(as_of, fp, x)
            for kk, d in enumerate(b.pillars):
                x[b.offset + kk] = math.log(curve.discount(d))
        elif c.type == "OIS_STEPS":
            for kk in range(1 + len(c.step_dates)):
                x[b.offset + kk] = level
        else:
            for kk, d in enumerate(b.pillars):
                x[b.offset + kk] = -level * (d - as_of).days / 365
        for kk in range(len(c.turns)):
            x[b.offset + b.size - len(c.turns) + kk] = 0.0


def _central(as_of: date, blocks: Sequence[_Block], x: list[float], k: int, j: int,
             h: float) -> list[float]:
    b = blocks[k]
    keep = x[j]
    x[j] = keep + h
    up = _residuals(as_of, blocks, x, k)
    x[j] = keep - h
    down = _residuals(as_of, blocks, x, k)
    x[j] = keep
    return [(up[i] - down[i]) / (2 * h) for i in range(b.offset, b.offset + b.size)]


def _column(as_of: date, blocks: Sequence[_Block], x: list[float], k: int, j: int,
            adaptive: bool) -> list[float]:
    """d residuals(block k) / d x[j]. Newton uses one central difference at _H. The IFT
    Jacobian uses Richardson on central differences, on a stencil that shrinks until two
    estimates agree: a piecewise interpolation (monotone convex) has kinks in its data, and a
    stencil that straddles one gives neither one-sided derivative."""
    if not adaptive:
        return _central(as_of, blocks, x, k, j, _H)

    def richardson(h: float) -> list[float]:
        coarse, fine = _central(as_of, blocks, x, k, j, h), _central(as_of, blocks, x, k, j, h / 2)
        return [c if c == f else (4 * f - c) / 3 for c, f in zip(coarse, fine, strict=True)]

    h = 1e-4
    best = richardson(h)
    while h > 2e-6:
        h /= 4
        nxt = richardson(h)
        # Roundoff in a residual is a few 1e-15, so the estimate at h carries about 1e-14/h.
        agree = all(abs(a - c) <= 1e-14 / h + 1e-7 * abs(c) for a, c in zip(best, nxt, strict=True))
        best = nxt
        if agree:
            break
    return best


def _block_jacobian(as_of: date, blocks: Sequence[_Block], x: list[float], k: int,
                    cols: range, adaptive: bool = False) -> list[list[float]]:
    """d residuals(block k) / d x[cols]."""
    size = blocks[k].size
    out = [[0.0] * len(cols) for _ in range(size)]
    for jj, j in enumerate(cols):
        column = _column(as_of, blocks, x, k, j, adaptive)
        for ii in range(size):
            out[ii][jj] = column[ii]
    return out


def _solve_block(as_of: date, blocks: Sequence[_Block], x: list[float], k: int) -> None:
    b = blocks[k]
    cols = range(b.offset, b.offset + b.size)

    def own(v: list[float]) -> list[float]:
        return _residuals(as_of, blocks, v, k)[b.offset:]

    r = own(x)
    for _ in range(60):
        size = max(abs(v) for v in r)
        if size < 1e-15:
            return
        a = _block_jacobian(as_of, blocks, x, k, cols)
        step = linalg.lu_solve(a, [-v for v in r])
        scale = 1.0
        for _ in range(30):  # backtracking keeps a far start from overshooting
            trial = list(x)
            for jj, j in enumerate(cols):
                trial[j] += scale * step[jj]
            try:
                r_new = own(trial)
            except (OverflowError, ValueError, ZeroDivisionError):
                r_new = [math.inf]
            if max(abs(v) for v in r_new) < size or scale < 1e-6:
                break
            scale /= 2
        x[:] = trial
        r = r_new
        if max(abs(s) for s in step) * scale < 1e-16:
            return


@dataclass
class JointResult:
    blocks: list[_Block]
    x: list[float]
    jacobian: list[list[float]]
    quote_ids: list[str]
    turn_sensitivity: list[list[float]]
    max_error: float


def joint_solve(as_of: date, specs: Sequence[CurveSpec],
                instruments: Sequence[InstrumentSpec]) -> JointResult:
    _check_structure(as_of, specs, instruments)
    blocks = _blocks(as_of, specs, instruments)
    n = sum(b.size for b in blocks)
    x = [0.0] * n
    _start(as_of, blocks, x)
    for k in range(len(blocks)):
        if blocks[k].spec.type == "XCCY":
            _start(as_of, blocks, x, k)  # after its foreign projection is solved
        _solve_block(as_of, blocks, x, k)
    residuals = _residuals(as_of, blocks, x)
    worst = max(abs(v) for v in residuals)
    if not worst <= TOLERANCE:
        raise QfError("E_NO_CONVERGENCE", f"joint solve residual {worst}")

    # dR/dx, block lower triangular: blocks after k only.
    full = [[0.0] * n for _ in range(n)]
    for k, b in enumerate(blocks):
        for kk in range(k + 1):
            c = blocks[kk]
            sub = _block_jacobian(as_of, blocks, x, k, range(c.offset, c.offset + c.size),
                                  True)
            for ii in range(b.size):
                full[b.offset + ii][c.offset:c.offset + c.size] = sub[ii]
    rows = [i for b in blocks for i in b.instruments]  # residual row order
    for b in blocks:  # ruling F-26: a turn moves only instruments that span it
        if b.spec.type != "OIS_STEPS":
            # On a pillar curve the unknowns are ln D, so a turn moves S at later pillars and,
            # through a non-local interpolation, sections on both sides (SPEC_QUESTIONS F-Q5).
            continue
        for t_k, day in enumerate(b.spec.turns):
            tcol = b.offset + b.size - len(b.spec.turns) + t_k
            for r, inst in enumerate(rows):
                if all(d <= day for d in inst.dates) or all(d > day for d in inst.dates):
                    full[r][tcol] = 0.0

    solved: dict[str, Any] = {}
    for b in blocks:
        solved[b.spec.name] = _curve(as_of, b, x)
    for inst in (i for b in blocks for i in b.instruments):
        if inst.spread_slope is not None:
            inst.d_quote = inst.spread_slope(solved)

    # J = -(dR/dx)^{-1} dR/dq, column by column, by block forward substitution.
    order = {inst.spec.id: r for r, inst in enumerate(rows)}
    block_of = [k for k, b in enumerate(blocks) for _ in range(b.size)]
    quote_ids = [i.id for i in instruments]
    jac = [[0.0] * len(quote_ids) for _ in range(n)]
    for q, qid in enumerate(quote_ids):
        r0 = order[qid]
        col = [0.0] * n
        for k in range(block_of[r0], len(blocks)):
            b = blocks[k]
            rhs = []
            for ii in range(b.size):
                r = b.offset + ii
                acc = 0.0
                for j in range(b.offset):
                    if col[j] != 0.0 and full[r][j] != 0.0:
                        acc += full[r][j] * col[j]
                rhs.append(-(rows[r].d_quote if r == r0 else 0.0) - acc)
            if k > block_of[r0] and all(v == 0.0 for v in rhs):
                continue
            a = [row[b.offset:b.offset + b.size] for row in full[b.offset:b.offset + b.size]]
            sol = linalg.lu_solve(a, rhs)
            col[b.offset:b.offset + b.size] = sol
        for i in range(n):
            jac[i][q] = col[i]

    inst_rows = [order[qid] for qid in quote_ids]
    sens = []
    for b in blocks:
        for t_k in range(len(b.spec.turns)):
            tc = b.offset + b.size - len(b.spec.turns) + t_k
            sens.append([full[r][tc] for r in inst_rows])
    return JointResult(blocks, x, jac, quote_ids, sens, worst)


def outputs(as_of: date, result: JointResult) -> dict[str, Any]:
    out_curves: list[dict[str, Any]] = []
    turns: list[dict[str, Any]] = []
    x = result.x
    for b in result.blocks:
        c = b.spec
        own = x[b.offset:b.offset + b.size]
        if c.type == "OIS_STEPS":
            m = len(c.step_dates)
            out_curves.append({"name": c.name, "base_rate": own[0],
                               "step_rates": list(own[1:m + 1])})
        else:
            out_curves.append({"name": c.name, "pillars": [
                {"date": d.isoformat(), "discount_factor": math.exp(v)}
                for d, v in zip(b.pillars, own, strict=False)]})
        for d, v in zip(c.turns, own[len(own) - len(c.turns):], strict=True):
            turns.append({"curve": c.name, "date": d.isoformat(), "factor": math.exp(v)})
    labels = [label for b in result.blocks for label in b.labels]
    return {
        "curves": out_curves,
        "turn_factors": turns,
        "jacobian": {"unknowns": labels, "quotes": result.quote_ids, "matrix": result.jacobian},
        "turn_sensitivity": result.turn_sensitivity,
    }


def funding_curve(discount: CurveData, quotes: Sequence[tuple[date, float]],
                  dates: Sequence[date]) -> tuple[list[float], list[tuple[date, float]],
                                                  list[float]]:
    """Returns (spreads, pillars, discount factors at dates)."""
    curve = curves.build(discount)
    as_of = discount.as_of
    if not quotes:
        raise QfError("E_INPUT", "no quotes", "quotes")
    _check_increasing(as_of, [e for e, _ in quotes], "quotes")
    logs: list[float] = []  # ln(D_ois / P_f) at each end
    times: list[float] = []
    for e, r in quotes:
        growth = 1 + r * (e - as_of).days / 360
        if not growth > 0:
            raise QfError("E_DOMAIN", "1 + rate * alpha must be positive", "quotes")
        logs.append(math.log(curve.discount(e)) + math.log(growth))
        times.append((e - as_of).days / 365)
    spreads = [(logs[0]) / times[0]]
    for i in range(1, len(quotes)):
        spreads.append((logs[i] - logs[i - 1]) / (times[i] - times[i - 1]))

    def integral(t: float) -> float:
        total, left = 0.0, 0.0
        for s, right in zip(spreads, times, strict=True):
            if t <= right:
                return total + s * (t - left)
            total += s * (right - left)
            left = right
        return total + spreads[-1] * (t - left)

    def factor(d: date) -> float:
        if d < as_of:
            raise QfError("E_OUT_OF_RANGE", f"{d} is before as_of", "dates")
        return curve.discount(d) * math.exp(-integral((d - as_of).days / 365))

    pillars = [(e, factor(e)) for e, _ in quotes]
    return spreads, pillars, [factor(d) for d in dates]


guard(globals())
