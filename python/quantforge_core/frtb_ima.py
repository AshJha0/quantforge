"""FRTB internal models approach: PLA test, liquidity horizons, ES with the liquidity-horizon cascade,
stressed ES, IMCC, NMRF stress scenario aggregation (SES), the risk factor eligibility test (RFET) and
the capital aggregation, plan item K-8f.

Specification: specifications/06-risk/frtb-ima.md; rulings KR-50, KR-56 to KR-61, KR-67 to KR-69
(specifications/stage-k-rulings-w2.md) and KR-117 to KR-121 (same file, wave 2 lane A section).
Sources: Basel Framework MAR31, MAR32 and MAR33, version effective 1 January 2023, read 2026-11-19 in
the consolidated PDF generated 11/11/2026, pages 646 to 686.

Parameters are copies of specifications/tables/stage_k/mar31_rfet.json, mar32_pla.json and
mar33_ima.json; python/tests/test_stage_k_w2a.py compares every one with the table (KR-50).
"""

import math
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from datetime import date, timedelta

from . import rng
from .errors import QfError
from .finite import guard
from .var_risk import historical

LABEL = "regulatory formula on caller inputs; not a regulatory return"  # KR-69
MAX_PNL = 1_000_000  # KR-67: P&L points per list
MAX_LIST = 100_000  # KR-67: positions, sensitivities, charges

# MAR32.42 zone thresholds; the KS ones are written as integer tests on d (KR-56)
PLA_GREEN_SPEARMAN = 0.80
PLA_RED_SPEARMAN = 0.70
PLA_GREEN_KS_PERCENT = 9  # green needs 100 d < 9 n (KS below 0.09)
PLA_RED_KS_PERCENT = 12  # red if 100 d > 12 n (KS above 0.12)
PLA_WINDOW = 250  # MAR32.35
PLA_MIN_N = 3  # KR-56

ES_CONFIDENCE = 0.975  # MAR33.3
BASE_HORIZON = 10  # MAR33.4, days
LIQUIDITY_HORIZONS = (10, 20, 40, 60, 120)  # MAR33.4 Table 1
# MAR33.12 Table 2
LH_TABLE = {
    "IR_specified_ccy": 10,
    "IR_unspecified_ccy": 20,
    "IR_volatility": 60,
    "IR_other": 60,
    "CS_sovereign_IG": 20,
    "CS_sovereign_HY": 40,
    "CS_corporate_IG": 40,
    "CS_corporate_HY": 60,
    "CS_volatility": 120,
    "CS_other": 120,
    "EQ_large_cap": 10,
    "EQ_small_cap": 20,
    "EQ_large_cap_volatility": 20,
    "EQ_small_cap_volatility": 60,
    "EQ_other": 60,
    "FX_specified_pairs": 10,
    "FX_pairs": 20,
    "FX_volatility": 40,
    "FX_other": 40,
    "COM_energy_carbon": 20,
    "COM_precious_nonferrous": 20,
    "COM_other": 60,
    "COM_energy_carbon_volatility": 60,
    "COM_precious_nonferrous_volatility": 60,
    "COM_other_volatility": 120,
    "COM_other_types": 120,
}
# MAR33.12 footnote 309: specified currency pairs (either order counts, KR-60)
SPECIFIED_FX_PAIRS = (
    "USD/EUR", "USD/JPY", "USD/GBP", "USD/AUD", "USD/CAD", "USD/CHF", "USD/MXN", "USD/CNY",
    "USD/NZD", "USD/RUB", "USD/HKD", "USD/SGD", "USD/TRY", "USD/KRW", "USD/SEK", "USD/ZAR",
    "USD/INR", "USD/NOK", "USD/BRL", "EUR/JPY", "EUR/GBP", "EUR/CHF", "JPY/AUD",
)  # fmt: skip
IMCC_RHO = 0.5  # MAR33.15(2)
IMCC_CLASSES = ("IR", "EQ", "FX", "COM", "CS")  # MAR33.15 risk classes; output order
SES_RHO = 0.6  # MAR33.17(4)
# MAR32.9 Table 1: multiplier plus 1.5 base, by exceptions 0..9; 10 or more is 2.00 (KR-61)
MULTIPLIER = (1.50, 1.50, 1.50, 1.50, 1.50, 1.70, 1.76, 1.83, 1.88, 1.92)
MULTIPLIER_RED = 2.00
SURCHARGE_K = 0.5  # MAR33.45
# MAR31.13: RFET counts
RFET_MIN_DAYS = 24
RFET_WINDOW_DAYS = 90
RFET_MIN_PER_WINDOW = 4
RFET_ALT_MIN_DAYS = 100
RFET_LOOKBACK_MONTHS = 12
# MAR31.16 Table 1: bucket lower bounds per row (upper bound is the next lower bound, the last open
# except row D, which ends below 1)
RFET_BUCKETS = {
    "A": (0.0, 0.75, 1.5, 4.0, 7.0, 12.0, 18.0, 25.0, 35.0),
    "B": (0.0, 0.75, 4.0, 10.0, 18.0, 30.0),
    "C": (0.0, 1.5, 3.5, 7.5, 15.0),
    "D": (0.0, 0.05, 0.3, 0.7, 0.95),
}
RFET_D_UPPER = 1.0


# ---- PLA test (MAR32.34 to MAR32.44, KR-56, KR-117) ------------------------------------------------


def _doubled_ranks(x: Sequence[float]) -> list[int]:
    """Twice the average rank (ties share the mean of their positions), so every value is an integer."""
    order = sorted(range(len(x)), key=lambda k: x[k])
    out = [0] * len(x)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
            j += 1
        doubled = i + j + 2  # ranks i+1 .. j+1, mean (i + j + 2) / 2
        for k in range(i, j + 1):
            out[order[k]] = doubled
        i = j + 1
    return out


def spearman(hpl: Sequence[float], rtpl: Sequence[float]) -> float:
    """MAR32.36 to MAR32.38: Pearson correlation of the average ranks.

    Computed on centred doubled ranks 2r - (n + 1), which are integers in [-(n-1), n-1], so the sums
    are exact in 64-bit integers for n up to 1,000,000; one rounding at the end, clamped to [-1, 1]."""
    n = len(hpl)
    a = [r - (n + 1) for r in _doubled_ranks(hpl)]
    b = [r - (n + 1) for r in _doubled_ranks(rtpl)]
    sxy = sum(u * v for u, v in zip(a, b, strict=True))
    sxx = sum(u * u for u in a)
    syy = sum(v * v for v in b)
    if sxx == 0 or syy == 0:
        raise QfError(
            "E_DOMAIN",
            "a series is constant: its rank variance is 0",
            "hpl" if sxx == 0 else "rtpl",
        )
    return max(-1.0, min(1.0, sxy / math.sqrt(float(sxx) * float(syy))))


def ks_count(hpl: Sequence[float], rtpl: Sequence[float]) -> int:
    """MAR32.39 to MAR32.41 in counts: max over pooled x of |#{rtpl <= x} - #{hpl <= x}| (KR-56)."""
    h, r = sorted(hpl), sorted(rtpl)
    best = 0
    for x in h + r:
        best = max(best, abs(bisect_right(r, x) - bisect_right(h, x)))
    return best


def kolmogorov_q(x: float) -> float:
    """Kolmogorov tail Q_KS(x) = 2 sum_{k>=1} (-1)^(k-1) exp(-2 k^2 x^2) (KR-56), evaluated as KR-117:
    1 at x <= 0; for 0 < x < 1 through the equivalent theta series
    1 - sqrt(2 pi)/x sum_{k>=1} exp(-(2k-1)^2 pi^2 / (8 x^2)); terms are added until one is 0."""
    if x <= 0:
        return 1.0
    if x < 1:
        c = math.pi * math.pi / (8 * x * x)
        terms = []
        k = 1
        while True:
            t = math.exp(-((2 * k - 1) ** 2) * c)
            if t == 0:
                break
            terms.append(t)
            k += 1
        return max(0.0, 1.0 - math.sqrt(2 * math.pi) / x * math.fsum(terms))
    terms = []
    k = 1
    while True:
        t = math.exp(-2 * k * k * x * x)
        if t == 0:
            break
        terms.append(t if k % 2 == 1 else -t)
        k += 1
    return min(1.0, 2 * math.fsum(terms))


def _pvalue(ks: float, n: int) -> float:
    return kolmogorov_q(ks * math.sqrt(n / 2))


def pla(hpl: Sequence[float], rtpl: Sequence[float]) -> dict[str, object]:
    """P&L attribution test statistics and zone for one desk (MAR32.34 to MAR32.44)."""
    n = len(hpl)
    if n > MAX_PNL or len(rtpl) > MAX_PNL:
        raise QfError(
            "E_LIMIT",
            f"a P&L list is above its limit of {MAX_PNL}",
            "hpl" if n > MAX_PNL else "rtpl",
        )
    if len(rtpl) != n:
        raise QfError("E_INPUT", "hpl and rtpl differ in length", "rtpl")
    if n < PLA_MIN_N:
        raise QfError("E_DOMAIN", f"at least {PLA_MIN_N} observations are needed", "hpl")
    rs = spearman(hpl, rtpl)
    d = ks_count(hpl, rtpl)
    ks = d / n
    if rs > PLA_GREEN_SPEARMAN and 100 * d < PLA_GREEN_KS_PERCENT * n:
        zone = "GREEN"
    elif rs < PLA_RED_SPEARMAN or 100 * d > PLA_RED_KS_PERCENT * n:
        zone = "RED"
    else:
        zone = "AMBER"
    return {
        "n": n,
        "spearman": rs,
        "ks": ks,
        "ks_count": d,
        "zone": zone,
        "ks_pvalue_asymptotic": _pvalue(ks, n),
        "regulatory_window": n == PLA_WINDOW,
        "label": LABEL,
    }


def pla_ks_pvalue(ks: float, n: int) -> dict[str, object]:
    """Q_KS(ks sqrt(n/2)), so the printed p-values of MAR32.42 can be checked (KR-117: n >= 1)."""
    if not 0 <= ks <= 1:
        raise QfError("E_DOMAIN", "ks must be in [0, 1]", "ks")
    if n < 1:
        raise QfError("E_DOMAIN", "n must be at least 1", "n")
    return {"pvalue": _pvalue(ks, n), "label": LABEL}


# ---- Liquidity horizons (MAR33.12, KR-60, KR-118) --------------------------------------------------


def _pair(text: str) -> tuple[str, str]:
    a, _, b = text.partition("/")
    return a, b


def fx_pair_specified(pair: str) -> bool:
    """KR-60: listed in footnote 309 in either order, or a first-order cross of two listed pairs."""
    a, b = _pair(pair)
    listed = {frozenset(_pair(p)) for p in SPECIFIED_FX_PAIRS}
    if frozenset((a, b)) in listed:
        return True
    partners = {c for p in listed for c in p}
    return any(frozenset((a, c)) in listed and frozenset((b, c)) in listed for c in partners)


def _next_horizon(x: float) -> int:
    for h in LIQUIDITY_HORIZONS:
        if h >= x:
            return h
    return LIQUIDITY_HORIZONS[-1]


def liquidity_horizon(
    category: str | None = None,
    fx_pair: str | None = None,
    constituents: Sequence[tuple[float, int]] | None = None,
    maturity_days: float | None = None,
) -> dict[str, object]:
    """MAR33.12 Table 2, footnote 309, FAQ4 (maturity) and FAQ5 (index constituents); KR-60, KR-118.

    Exactly one of `category`, `fx_pair` and `constituents` ((weight, n) pairs)."""
    given = [v is not None for v in (category, fx_pair, constituents)]
    if sum(given) != 1:
        raise QfError(
            "E_INPUT", "give exactly one of category, fx_pair and constituents", "category"
        )
    if constituents is not None:
        if not constituents:
            raise QfError("E_INPUT", "constituents is empty", "constituents")
        if len(constituents) > MAX_LIST:
            raise QfError(
                "E_LIMIT", f"constituents is above its limit of {MAX_LIST}", "constituents"
            )
    if fx_pair is not None:
        a, b = _pair(fx_pair)
        if a == b:
            raise QfError("E_DOMAIN", "an FX pair needs two different currencies", "fx_pair")
    if maturity_days is not None and not maturity_days > 0:
        raise QfError("E_DOMAIN", "maturity_days must be above 0", "maturity_days")
    if constituents is not None:
        for k, (w, h) in enumerate(constituents):
            if not w >= 0:
                raise QfError(
                    "E_DOMAIN", "a constituent weight is negative", f"constituents/{k}/weight"
                )
            if h not in LIQUIDITY_HORIZONS:
                raise QfError(
                    "E_DOMAIN",
                    "a constituent n is not 10, 20, 40, 60 or 120",
                    f"constituents/{k}/n",
                )
        total = math.fsum(w for w, _ in constituents)
        if abs(total - 1) > 1e-12:
            raise QfError(
                "E_DOMAIN", "constituent weights must sum to 1 within 1e-12", "constituents"
            )
    if category is not None:
        base = LH_TABLE[category]
        rule = "table"
    elif fx_pair is not None:
        base = (
            LH_TABLE["FX_specified_pairs"] if fx_pair_specified(fx_pair) else LH_TABLE["FX_pairs"]
        )
        rule = "fx_pair"
    else:
        assert constituents is not None
        weighted = math.fsum(w * h for w, h in constituents)
        base = _next_horizon(weighted)
        rule = "index"
    n = base
    if maturity_days is not None and maturity_days < base:
        n = _next_horizon(maturity_days)
        rule += "+maturity"
    return {"n": n, "table_n": base, "rule": rule, "label": LABEL}


# ---- ES with liquidity horizons, stressed ES, IMCC, SES (MAR33.4 to MAR33.17) ---------------------

NORMAL_ES_FACTOR_DOC = 2.337802792201415  # KR-57 (documentation; the code computes it)


def normal_es_factor() -> float:
    """phi(z) / (1 - 0.975) with z = Phi^-1(0.975) (KR-57)."""
    z = rng.ppnd16(ES_CONFIDENCE)
    return math.exp(-z * z / 2) / math.sqrt(2 * math.pi) / (1 - ES_CONFIDENCE)


def horizon_weights() -> tuple[float, ...]:
    """(LH_j - LH_{j-1}) / T with LH_0 = 0 for j = 1: (1, 1, 2, 2, 6) (MAR33.4)."""
    prev = 0
    out = []
    for j, h in enumerate(LIQUIDITY_HORIZONS):
        out.append(1.0 if j == 0 else (h - prev) / BASE_HORIZON)
        prev = h
    return tuple(out)


def es_cascade(es_by_horizon: Sequence[float]) -> float:
    """MAR33.4: sqrt(ES_1^2 + sum_{j>=2} (ES_j sqrt((LH_j - LH_{j-1}) / 10))^2)."""
    return math.sqrt(
        math.fsum(w * e * e for w, e in zip(horizon_weights(), es_by_horizon, strict=True))
    )


def es_lh(
    es_t: Sequence[float] | None = None,
    sigma: Sequence[float] | None = None,
    pnl: Sequence[Sequence[float]] | None = None,
) -> dict[str, object]:
    """Liquidity-horizon-adjusted ES (MAR33.4, KR-57). Exactly one of the three inputs, five entries."""
    given = [v for v in (es_t, sigma, pnl) if v is not None]
    if pnl is not None:
        for j, lst in enumerate(pnl):
            if len(lst) > MAX_PNL:
                raise QfError("E_LIMIT", f"a P&L list is above its limit of {MAX_PNL}", f"pnl/{j}")
    if len(given) != 1:
        raise QfError("E_INPUT", "give exactly one of es_t, sigma and pnl", "es_t")
    values = given[0]
    field = "es_t" if es_t is not None else "sigma" if sigma is not None else "pnl"
    if len(values) != len(LIQUIDITY_HORIZONS):
        raise QfError("E_INPUT", f"{field} must have exactly five entries", field)
    if es_t is not None or sigma is not None:
        nums = [float(v) for v in values]  # type: ignore[arg-type]
        for j, v in enumerate(nums):
            if v < 0:
                raise QfError("E_DOMAIN", f"{field} entries must be 0 or above", f"{field}/{j}")
        if sigma is not None:
            f = normal_es_factor()
            nums = [f * s for s in nums]
        es = nums
    else:
        assert pnl is not None
        es = []
        for j, lst in enumerate(pnl):
            v = float(historical(lst, ES_CONFIDENCE)["es"]) if lst else 0.0  # type: ignore[arg-type]
            if v < 0:  # KR-119
                raise QfError(
                    "E_DOMAIN", "the ES of a P&L list is negative (its tail is a gain)", f"pnl/{j}"
                )
            es.append(v)
    return {"mode": field, "es_by_horizon": es, "es": es_cascade(es), "label": LABEL}


def _stressed(t: Sequence[float]) -> tuple[float, bool, float]:
    """(ratio, floored, ES_R,S max(1, ratio)) of one (es_rs, es_fc, es_rc) triple."""
    es_rs, es_fc, es_rc = t
    ratio = es_fc / es_rc
    return ratio, ratio < 1, es_rs * max(1.0, ratio)


def _triple_domain(t: Sequence[float], path: str) -> None:
    es_rs, es_fc, es_rc = t
    if es_rs < 0 or es_fc < 0:
        raise QfError("E_DOMAIN", "ES must be 0 or above", path)
    if not es_rc > 0:
        raise QfError("E_DOMAIN", "es_rc must be above 0", f"{path}es_rc")


def es_stressed(es_rs: float, es_fc: float, es_rc: float) -> dict[str, object]:
    """MAR33.6 with the ratio floored at 1 (KR-58)."""
    _triple_domain((es_rs, es_fc, es_rc), "")
    ratio, floored, es = _stressed((es_rs, es_fc, es_rc))
    return {"ratio": ratio, "ratio_floored": floored, "es": es, "label": LABEL}


def imcc(portfolio: Sequence[float], classes: Mapping[str, Sequence[float]]) -> dict[str, object]:
    """MAR33.15: 0.5 IMCC(C) + 0.5 sum_i IMCC(C_i), each from (es_rs, es_fc, es_rc) (KR-58)."""
    if not classes:
        raise QfError("E_INPUT", "classes is empty", "classes")
    _triple_domain(portfolio, "portfolio.")
    for c in IMCC_CLASSES:
        if c in classes:
            _triple_domain(classes[c], f"classes.{c}.")
    _, whole_floored, whole = _stressed(portfolio)
    per = {c: _stressed(classes[c]) for c in IMCC_CLASSES if c in classes}
    total = IMCC_RHO * whole + (1 - IMCC_RHO) * math.fsum(v[2] for v in per.values())
    return {
        "imcc_c": whole,
        "portfolio_floored": whole_floored,
        "classes": {c: v[2] for c, v in per.items()},
        "classes_floored": [c for c, v in per.items() if v[1]],
        "imcc": total,
        "label": LABEL,
    }


def ses(
    idio_credit: Sequence[float], idio_equity: Sequence[float], other: Sequence[float]
) -> dict[str, object]:
    """MAR33.17: sqrt(sum ISES_i^2) + sqrt(sum ISES_j^2) + sqrt((0.6 sum SES_k)^2 + 0.64 sum SES_k^2)."""
    for name, lst in (("idio_credit", idio_credit), ("idio_equity", idio_equity), ("other", other)):
        if len(lst) > MAX_LIST:
            raise QfError("E_LIMIT", f"{name} is above its limit of {MAX_LIST}", name)
    for name, lst in (("idio_credit", idio_credit), ("idio_equity", idio_equity), ("other", other)):
        for k, v in enumerate(lst):
            if v < 0:
                raise QfError("E_DOMAIN", "a stress scenario charge is negative", f"{name}/{k}")
    a = math.sqrt(math.fsum(v * v for v in idio_credit))
    b = math.sqrt(math.fsum(v * v for v in idio_equity))
    s = math.fsum(other)
    c = math.sqrt((SES_RHO * s) ** 2 + (1 - SES_RHO * SES_RHO) * math.fsum(v * v for v in other))
    return {"idio_credit": a, "idio_equity": b, "other": c, "ses": a + b + c, "label": LABEL}


# ---- Capital (MAR33.41 to MAR33.45, KR-61, KR-120) ------------------------------------------------


def multiplier(exceptions: int) -> float:
    """MAR32.9 Table 1 (KR-61)."""
    return MULTIPLIER[exceptions] if exceptions < len(MULTIPLIER) else MULTIPLIER_RED


def capital(
    imcc_prev: float,
    ses_prev: float,
    imcc_avg: float,
    ses_avg: float,
    exceptions: int,
    drc: float,
    desks: Sequence[tuple[str, float]],
    c_u: float,
    sa_all: float,
    qualitative_addon: float = 0.0,
) -> dict[str, object]:
    """Aggregate capital requirement for market risk (MAR33.41 to MAR33.45). `desks`: (zone, sa)."""
    if len(desks) > MAX_LIST:
        raise QfError("E_LIMIT", f"desks is above its limit of {MAX_LIST}", "desks")
    for name, v in (
        ("imcc_prev", imcc_prev),
        ("ses_prev", ses_prev),
        ("imcc_avg", imcc_avg),
        ("ses_avg", ses_avg),
        ("drc", drc),
        ("c_u", c_u),
        ("sa_all", sa_all),
        ("qualitative_addon", qualitative_addon),
    ):
        if v < 0:  # KR-120
            raise QfError("E_DOMAIN", f"{name} must be 0 or above", name)
    if exceptions < 0:
        raise QfError("E_DOMAIN", "exceptions must be 0 or above", "exceptions")
    for j, (_, sa) in enumerate(desks):
        if sa < 0:  # KR-120
            raise QfError("E_DOMAIN", "a desk SA must be 0 or above", f"desks/{j}/sa")
    sa_ga = math.fsum(sa for _, sa in desks)
    amber = math.fsum(sa for z, sa in desks if z == "AMBER")
    has_amber = any(z == "AMBER" for z, _ in desks)
    if has_amber and sa_ga == 0:
        raise QfError(
            "E_DOMAIN", "SA over the green and amber desks is 0 with an amber desk", "desks"
        )
    m_c = multiplier(exceptions) + qualitative_addon
    c_a = max(imcc_prev + ses_prev, m_c * imcc_avg + ses_avg)
    ima_ga = c_a + drc
    k = SURCHARGE_K * amber / sa_ga if has_amber else 0.0
    surcharge = k * max(0.0, sa_ga - ima_ga)
    acr = min(ima_ga + surcharge + c_u, sa_all) + max(0.0, ima_ga - sa_ga)
    return {
        "m_c": m_c,
        "c_a": c_a,
        "ima_ga": ima_ga,
        "sa_ga": sa_ga,
        "k": k,
        "surcharge": surcharge,
        "acr_total": acr,
        "label": LABEL,
    }


# ---- RFET (MAR31.12 to MAR31.16, KR-59) -----------------------------------------------------------


def months_back(d: date, months: int) -> date:
    """Calendar months back, the day clamped to the end of the target month (KR-59)."""
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12)
    m += 1
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return date(y, m, min(d.day, (nxt - timedelta(days=1)).day))


def rfet(as_of: date, observations: Sequence[date]) -> dict[str, object]:
    """Risk factor eligibility test on real-price observation dates (MAR31.13, KR-59)."""
    if len(observations) > MAX_LIST:
        raise QfError("E_LIMIT", f"observations is above its limit of {MAX_LIST}", "observations")
    start = months_back(as_of, RFET_LOOKBACK_MONTHS) + timedelta(days=1)
    days = sorted({d for d in observations if start <= d <= as_of})
    ordinals = [d.toordinal() for d in days]
    first_bad: date | None = None
    first_bad_count: int | None = None
    lowest: int | None = None
    s = start
    last = as_of - timedelta(days=RFET_WINDOW_DAYS - 1)
    while s <= last:
        lo = s.toordinal()
        count = bisect_right(ordinals, lo + RFET_WINDOW_DAYS - 1) - bisect_right(ordinals, lo - 1)
        lowest = count if lowest is None else min(lowest, count)
        if first_bad is None and count < RFET_MIN_PER_WINDOW:
            first_bad, first_bad_count = s, count
        s += timedelta(days=1)
    crit1 = len(days) >= RFET_MIN_DAYS and first_bad is None
    crit2 = len(days) >= RFET_ALT_MIN_DAYS
    return {
        "window_start": start.isoformat(),
        "distinct_days": len(days),
        "min_window_count": lowest,
        "first_failing_window_start": None if first_bad is None else first_bad.isoformat(),
        "first_failing_window_count": first_bad_count,
        "crit1": crit1,
        "crit2": crit2,
        "pass": crit1 or crit2,
        "label": LABEL,
    }


def rfet_bucket(row: str, t: float | None = None, delta: float | None = None) -> dict[str, object]:
    """MAR31.16 Table 1 bucket (1-based), lower bound inclusive, upper exclusive (KR-59). Rows A to C
    take a maturity `t` in years, row D an option `delta` (KR-121)."""
    field = "delta" if row == "D" else "t"
    if (delta if row == "D" else t) is None or (t if row == "D" else delta) is not None:
        raise QfError("E_INPUT", f"row {row} takes {field} and nothing else", field)
    value = float(delta if row == "D" else t)  # type: ignore[arg-type]
    if value < 0:
        raise QfError("E_DOMAIN", f"{field} must be 0 or above", field)
    if row == "D" and not value < RFET_D_UPPER:
        raise QfError("E_DOMAIN", "delta must be below 1", "delta")
    lows = RFET_BUCKETS[row]
    b = bisect_right(lows, value)
    upper: float | None = lows[b] if b < len(lows) else (RFET_D_UPPER if row == "D" else None)
    return {"bucket": b, "lower": lows[b - 1], "upper": upper, "label": LABEL}


guard(globals())
