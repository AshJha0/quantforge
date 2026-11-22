"""Reverse-mode (adjoint) sensitivities of the G-41 valuation adjustments, written by hand.

Specification: specifications/06-risk/xva-aad-adjustments.md (rulings KR-262 to KR-268). The forward values are
those of `xva.adjustments` (the same code); the backward pass below is the one the spec states, per output, bucket
by bucket from the first.
"""

import math
from collections.abc import Sequence

from .errors import QfError
from .finite import guard
from .numeric import ordered_sum
from .xva import Floats, Name, adjustments

WRAPPED = "xva.adjustments.value"
MAX_BUCKETS = 10_000
BASE_KEYS = (
    "counterparty.hazard_rate",
    "counterparty.hazard_buckets",
    "counterparty.recovery",
    "own.hazard_rate",
    "own.hazard_buckets",
    "own.recovery",
    "discount_factors",
    "ee",
    "ene",
    "funding.borrow_spread",
    "funding.lend_spread",
)
IM_KEYS = ("im", "im_spread")
CAPITAL_KEYS = ("capital", "hurdle_rate")

Gradient = dict[str, float | list[float]]


def _keys(has_im: bool, has_capital: bool) -> tuple[str, ...]:
    return BASE_KEYS + (IM_KEYS if has_im else ()) + (CAPITAL_KEYS if has_capital else ())


def _check_wrt(wrt: Sequence[str] | None, allowed: tuple[str, ...]) -> tuple[str, ...]:
    """KR-267 step 4, before the wrapped operation's structural checks."""
    if wrt is None:
        return allowed
    if not wrt:
        raise QfError("E_INPUT", "wrt is empty", "wrt")
    if len(set(wrt)) != len(wrt):
        raise QfError("E_INPUT", "wrt names a key twice", "wrt")
    for key in wrt:
        if key not in allowed:
            raise QfError("E_INPUT", f"wrt names {key}, which is not a differentiated input", "wrt")
    return tuple(k for k in allowed if k in wrt)


class _Bar:
    """Adjoint accumulators of one output."""

    def __init__(self, n: int) -> None:
        self.sc = [0.0] * (
            n + 1
        )  # survival of the counterparty at t_0 = 0, t_1, ..., t_n, used alone
        self.sb = [0.0] * (n + 1)
        self.pc = [
            0.0
        ] * n  # the difference S_c(t_(i-1)) - S_c(t_i) of bucket i, used as one quantity
        self.pb = [0.0] * n
        self.df = [0.0] * n
        self.ee = [0.0] * n
        self.ene = [0.0] * n
        self.prof = [0.0] * n  # im or capital
        self.hb_direct = [0.0] * n  # own hazard of bucket j through the overlap floor
        self.rc = 0.0
        self.rb = 0.0
        self.spread = 0.0  # borrow, lend, im or hurdle, whichever the output uses


class _Tape:
    """The forward intermediates the backward pass reads."""

    def __init__(self, times: Floats, dfs: Floats, cpty: Name, own: Name) -> None:
        n = len(times)
        self.n = n
        self.t = [0.0, *times]
        self.dt = [times[i] - self.t[i] for i in range(n)]
        self.df = dfs
        self.sc = [math.exp(-cpty.hazard_rate * x) for x in self.t]
        self.sb = [math.exp(-own.hazard_rate * x) for x in self.t]
        # b_i = S(t_i) (1 - e^(-h dt_i)), cancellation free (PT-6); equal to S(t_i) - S(t_(i+1)) in exact arithmetic
        self.bc = [self.sc[i] * -math.expm1(-cpty.hazard_rate * self.dt[i]) for i in range(n)]
        self.bb = [self.sb[i] * -math.expm1(-own.hazard_rate * self.dt[i]) for i in range(n)]
        self.w = [dfs[i] * self.sc[i] * self.sb[i] * self.dt[i] for i in range(n)]

    def through_w(self, bar: _Bar, i: int, gw: float) -> None:
        bar.df[i] += gw * self.sc[i] * self.sb[i] * self.dt[i]
        bar.sc[i] += gw * self.df[i] * self.sb[i] * self.dt[i]
        bar.sb[i] += gw * self.df[i] * self.sc[i] * self.dt[i]


def _cva_bar(tp: _Tape, ee: Floats, cpty: Name) -> _Bar:
    bar, lc = _Bar(tp.n), 1 - cpty.recovery
    for i in range(tp.n):
        b = tp.bc[i]
        bar.rc -= tp.df[i] * ee[i] * b * tp.sb[i]
        bar.df[i] += lc * ee[i] * b * tp.sb[i]
        bar.ee[i] += lc * tp.df[i] * b * tp.sb[i]
        bar.pc[i] += lc * tp.df[i] * ee[i] * tp.sb[i]
        bar.sb[i] += lc * tp.df[i] * ee[i] * b
    return bar


def _dva_bar(tp: _Tape, ene: Floats, own: Name) -> _Bar:
    bar, lb = _Bar(tp.n), 1 - own.recovery
    for i in range(tp.n):
        x, b = -ene[i], tp.bb[i]
        bar.rb -= tp.df[i] * x * b * tp.sc[i]
        bar.df[i] += lb * x * b * tp.sc[i]
        bar.ene[i] -= lb * tp.df[i] * b * tp.sc[i]
        bar.pb[i] += lb * tp.df[i] * x * tp.sc[i]
        bar.sc[i] += lb * tp.df[i] * x * b
    return bar


def _funding_bar(tp: _Tape, coef: float, prof: Floats, sink: str) -> _Bar:
    """FCA (sink "ee"), MVA and KVA (sink "prof"): coef sum W_i x_i."""
    bar = _Bar(tp.n)
    target = bar.ee if sink == "ee" else bar.prof
    for i in range(tp.n):
        target[i] += coef * tp.w[i]
        bar.spread += tp.w[i] * prof[i]
        tp.through_w(bar, i, coef * prof[i])
    return bar


def _fba_bar(tp: _Tape, ene: Floats, s_l: float, branch: bool | None, own: Name) -> _Bar:
    """FBA = sum s_l' W_i (-ene_i); branch None: no overlap rule; True: linear; False: the floor (KR-264)."""
    bar, lb = _Bar(tp.n), 1 - own.recovery
    coef = s_l if branch is None else (s_l - own.hazard_rate * lb if branch else 0.0)
    for i in range(tp.n):
        x = -ene[i]
        bar.ene[i] -= coef * tp.w[i]
        g = tp.w[i] * x
        if branch is not False:
            bar.spread += g
        if branch:
            bar.rb += g * own.hazard_rate
            bar.hb_direct[i] -= g * lb
        tp.through_w(bar, i, coef * x)
    return bar


def _hazards(
    s: list[float],
    gs: list[float],
    b: list[float],
    gp: list[float],
    t: list[float],
    dt: list[float],
) -> tuple[float, list[float]]:
    """Survival adjoints to hazard adjoints. `gs[k]`: adjoint of S(t_k) used alone; `gp[i]`: adjoint of the
    bucket difference b_i = S(t_i) - S(t_(i+1)) (t_0 = 0). Flat: d / d h = -sum_k gs_k t_k S_k
    - sum_i gp_i (t_i b_i - dt_i S_(i+1)). Bucket j (S_k depends on h_j for k > j):
    d / d h_j = -dt_j (sum_(k > j) gs_k S_k + sum_(i > j) gp_i b_i - gp_j S_(j+1)). Keeping b_i whole means a
    difference that is 0 (h = 0) gives an exact 0, with no cancellation."""
    n = len(dt)
    flat = -ordered_sum(gs[k] * t[k] * s[k] for k in range(n + 1)) - ordered_sum(
        gp[i] * (t[i] * b[i] - dt[i] * s[i + 1]) for i in range(n)
    )
    buckets = [0.0] * n
    tail = 0.0
    for j in range(n - 1, -1, -1):
        tail += gs[j + 1] * s[j + 1]
        buckets[j] = -dt[j] * (tail - gp[j] * s[j + 1])
        tail += gp[j] * b[j]
    return flat, buckets


def _gradient(tp: _Tape, bar: _Bar, spread_key: str | None, prof_key: str | None) -> Gradient:
    hc, hc_b = _hazards(tp.sc, bar.sc, tp.bc, bar.pc, tp.t, tp.dt)
    hb, hb_b = _hazards(tp.sb, bar.sb, tp.bb, bar.pb, tp.t, tp.dt)
    g: Gradient = {
        "counterparty.hazard_rate": hc,
        "counterparty.hazard_buckets": hc_b,
        "counterparty.recovery": bar.rc,
        "own.hazard_rate": hb + ordered_sum(bar.hb_direct),
        "own.hazard_buckets": [a + b for a, b in zip(hb_b, bar.hb_direct, strict=True)],
        "own.recovery": bar.rb,
        "discount_factors": bar.df,
        "ee": bar.ee,
        "ene": bar.ene,
        "funding.borrow_spread": 0.0,
        "funding.lend_spread": 0.0,
        "im": [0.0] * tp.n,
        "im_spread": 0.0,
        "capital": [0.0] * tp.n,
        "hurdle_rate": 0.0,
    }
    if spread_key is not None:
        g[spread_key] = bar.spread
    if prof_key is not None:
        g[prof_key] = bar.prof
    return g


def _minus(a: Gradient, b: Gradient) -> Gradient:
    out: Gradient = {}
    for k, x in a.items():
        y = b[k]
        if isinstance(x, list) and isinstance(y, list):
            out[k] = [p - q for p, q in zip(x, y, strict=True)]
        elif isinstance(x, float) and isinstance(y, float):
            out[k] = x - y
    return out


def adjustments_aad(
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
    wrt: Sequence[str] | None = None,
) -> dict[str, object]:
    """`xva.sens.aad` on `xva.adjustments.value`: the outputs and their gradient (KR-262 to KR-264)."""
    names = _check_wrt(wrt, _keys(im is not None, capital is not None))
    values = adjustments(
        times, dfs, ee, ene, cpty, own, borrow_spread, lend_spread, exclude_overlap,
        im, im_spread, capital, hurdle_rate,
    )  # fmt: skip
    tp = _Tape(times, dfs, cpty, own)
    branch = (lend_spread - own.hazard_rate * (1 - own.recovery) >= 0) if exclude_overlap else None
    raw = {
        "cva": _gradient(tp, _cva_bar(tp, ee, cpty), None, None),
        "dva": _gradient(tp, _dva_bar(tp, ene, own), None, None),
        "fca": _gradient(
            tp, _funding_bar(tp, borrow_spread, ee, "ee"), "funding.borrow_spread", None
        ),
        "fba": _gradient(
            tp, _fba_bar(tp, ene, lend_spread, branch, own), "funding.lend_spread", None
        ),
    }
    raw["fva"] = _minus(raw["fca"], raw["fba"])
    if im is not None and im_spread is not None:
        raw["mva"] = _gradient(tp, _funding_bar(tp, im_spread, im, "prof"), "im_spread", "im")
    if capital is not None and hurdle_rate is not None:
        raw["kva"] = _gradient(
            tp, _funding_bar(tp, hurdle_rate, capital, "prof"), "hurdle_rate", "capital"
        )
    out: dict[str, object] = dict(values)
    out["gradient"] = {o: {k: raw[o][k] for k in names} for o in values}
    return out


guard(globals())
