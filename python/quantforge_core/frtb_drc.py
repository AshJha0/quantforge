"""FRTB standardised approach: default risk charge (DRC) and residual risk add-on (RRAO), plan item K-8a.

Specification: specifications/06-risk/frtb-drc-rrao.md; rulings KR-50 to KR-55 and KR-67 to KR-69
(specifications/stage-k-rulings-w2.md) and KR-112 to KR-116 (same file, wave 2 lane A section).
Sources: Basel Framework MAR22 and MAR23, version effective 1 January 2023, read 2026-11-19 in the
consolidated PDF generated 11/11/2026, pages 619 to 637.

The parameters below are copies of specifications/tables/stage_k/mar22_drc.json and mar23_rrao.json;
python/tests/test_stage_k_w2a.py compares every one of them with the table (KR-50).

Error order (KR-67, HR-122): E_SCHEMA in the input layer; E_LIMIT; the finite rule; structural
E_INPUT (every position checked before any domain rule); E_DOMAIN.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .errors import QfError
from .finite import guard

LABEL = "regulatory formula on caller inputs; not a regulatory return"  # KR-69
RW_SOURCE = (
    "securitisation risk weights supplied by the caller (CRE40-CRE44 not implemented)"  # KR-55
)
MAX_POSITIONS = 100_000  # KR-67

BUCKETS = ("CORPORATE", "SOVEREIGN", "LOCAL_GOV")  # MAR22.22; output order (KR-114)
SENIORITIES = ("COVERED", "SENIOR", "NON_SENIOR", "EQUITY")
RATINGS = ("AAA", "AA", "A", "BBB", "BB", "B", "CCC", "UNRATED", "DEFAULTED")
# MAR22.12: loss given default by seniority
LGD = {"COVERED": 0.25, "SENIOR": 0.75, "NON_SENIOR": 1.0, "EQUITY": 1.0}
# KR-53: offsetting rank (a short of rank r offsets longs of rank r or above)
RANK = {"COVERED": 4, "SENIOR": 3, "NON_SENIOR": 2, "EQUITY": 1}
# MAR22.24 Table 2: default risk weights by credit quality
RISK_WEIGHT = {
    "AAA": 0.005,
    "AA": 0.02,
    "A": 0.03,
    "BBB": 0.06,
    "BB": 0.15,
    "B": 0.30,
    "CCC": 0.50,
    "UNRATED": 0.15,
    "DEFAULTED": 1.0,
}
CAPITAL_HORIZON = 1.0  # MAR22.15, years
MATURITY_FLOOR = 0.25  # MAR22.18
CASH_EQUITY_SHORT = 0.25  # MAR22.16: cash equity maturity is 0.25 or at least one year
CTP_CROSS_FACTOR = 0.5  # MAR22.45
RW_CAP = 12.5  # frtb-drc-rrao.md Errors: a caller rw above 1250% is E_DOMAIN
RRAO_WEIGHT = {"EXOTIC": 0.01, "OTHER": 0.001}  # MAR23.8(2)


@dataclass(frozen=True)
class Position:
    """A non-securitisation position (KR-51). `notional` and `market_value` are signed: long > 0."""

    id: str
    obligor: str
    bucket: str
    seniority: str
    notional: float
    market_value: float
    maturity_years: float
    cash_equity: bool = False
    lgd_applies: bool = True


@dataclass(frozen=True)
class SecPosition:
    """A securitisation (non-CTP) position: JTD is the market value (MAR22.27); `rw` from the caller (KR-55)."""

    id: str
    bucket: str
    pool: str
    tranche: str
    market_value: float
    maturity_years: float
    rw: float


@dataclass(frozen=True)
class CtpPosition:
    """A correlation trading position: netting key (index, series, tranche), bucket = index (MAR22.39)."""

    id: str
    index: str
    series: str
    tranche: str
    market_value: float
    maturity_years: float
    rw: float


@dataclass(frozen=True)
class Instrument:
    """An instrument subject to the residual risk add-on (MAR23)."""

    id: str
    gross_notional: float
    kind: str
    listed_or_clearable: bool
    back_to_back: bool


def maturity_weight(maturity_years: float) -> float:
    """MAR22.15, MAR22.18, KR-52: 1 at one year or more, else the maturity floored at 0.25."""
    return 1.0 if maturity_years >= CAPITAL_HORIZON else max(maturity_years, MATURITY_FLOOR)


def gross_jtd(p: Position) -> float:
    """MAR22.11, MAR22.12: LGD x notional + P&L, floored at 0 for a long and capped at 0 for a short."""
    lgd = LGD[p.seniority] if p.lgd_applies else 1.0
    pnl = p.market_value - p.notional
    raw = lgd * p.notional + pnl
    if p.notional > 0:
        return max(raw, 0.0)
    if p.notional < 0:
        return min(raw, 0.0)
    return 0.0


def _limit(n: int, field: str) -> None:
    if n > MAX_POSITIONS:
        raise QfError("E_LIMIT", f"{field} is above its limit of {MAX_POSITIONS}", field)


def _unique(ids: Sequence[str], field: str) -> None:
    seen: set[str] = set()
    for k, i in enumerate(ids):
        if i in seen:
            raise QfError("E_INPUT", f"duplicate id {i!r}", f"{field}/{k}/id")
        seen.add(i)


def _maturity(m: float, path: str) -> None:
    if not m > 0:
        raise QfError("E_DOMAIN", "maturity_years must be above 0", path)


def offset(
    longs: Sequence[tuple[int, float]], shorts: Sequence[tuple[int, float]]
) -> tuple[float, float]:
    """KR-53 greedy offsetting within one obligor. `longs` and `shorts` are (rank, scaled JTD) in input
    order (longs > 0, shorts < 0). Shorts are served in descending rank (ties: input order); each
    consumes the eligible longs (rank at least its own) in ascending rank (ties: input order).
    Returns (net long >= 0, net short <= 0)."""
    left = [[r, v] for r, v in longs]
    order = sorted(range(len(left)), key=lambda k: (left[k][0], k))
    rest: list[float] = []
    for _, k in sorted(((-r, k) for k, (r, _) in enumerate(shorts))):
        rank, need = shorts[k][0], -shorts[k][1]
        for j in order:
            if need <= 0:
                break
            if left[j][0] < rank or left[j][1] <= 0:
                continue
            used = min(need, left[j][1])
            left[j][1] -= used
            need -= used
        if need > 0:
            rest.append(-need)
    return math.fsum(v for _, v in left), math.fsum(rest)


def _bucket_drc(pairs: Sequence[tuple[float, float, float]]) -> dict[str, object]:
    """MAR22.23, MAR22.25 and KR-54 over (rw, net long, net short) of one bucket."""
    long_sum = math.fsum(nl for _, nl, _ in pairs)
    short_sum = math.fsum(-ns for _, _, ns in pairs)
    wtd_long = math.fsum(rw * nl for rw, nl, _ in pairs)
    wtd_short = math.fsum(rw * -ns for rw, _, ns in pairs)
    total = long_sum + short_sum
    hbr = long_sum / total if total > 0 else None
    drc = max(wtd_long - hbr * wtd_short, 0.0) if hbr is not None else 0.0
    return {"hbr": hbr, "wtd_long": wtd_long, "wtd_short": wtd_short, "drc": drc}


def drc_nonsec(positions: Sequence[Position], ratings: Mapping[str, str]) -> dict[str, object]:
    """Default risk charge for non-securitisations (MAR22.9 to MAR22.26)."""
    _limit(len(positions), "positions")
    if not positions:
        raise QfError("E_INPUT", "positions is empty", "positions")
    _unique([p.id for p in positions], "positions")
    bucket_of: dict[str, str] = {}
    for k, p in enumerate(positions):
        if p.obligor not in ratings:
            raise QfError(
                "E_INPUT", f"obligor {p.obligor!r} has no rating", f"positions/{k}/obligor"
            )
        if bucket_of.setdefault(p.obligor, p.bucket) != p.bucket:  # KR-113
            raise QfError(
                "E_INPUT", f"obligor {p.obligor!r} is in two buckets", f"positions/{k}/bucket"
            )
    for k, p in enumerate(positions):
        path = f"positions/{k}"
        _maturity(p.maturity_years, f"{path}/maturity_years")
        if p.cash_equity:
            m = p.maturity_years
            if m != CASH_EQUITY_SHORT and m < CAPITAL_HORIZON:  # KR-52
                raise QfError("E_DOMAIN", "cash equity maturity must be 0.25 or at least 1", path)
            if p.seniority != "EQUITY" or p.notional != p.market_value:  # KR-112
                raise QfError(
                    "E_DOMAIN", "cash equity must be EQUITY with notional = market value", path
                )
        if p.notional == 0 and p.market_value != 0:
            raise QfError(
                "E_DOMAIN", "zero notional with a nonzero market value", f"{path}/notional"
            )

    rows = []
    longs: dict[str, list[tuple[int, float]]] = {}
    shorts: dict[str, list[tuple[int, float]]] = {}
    for p in positions:
        jtd = gross_jtd(p)
        w = maturity_weight(p.maturity_years)
        scaled = w * jtd
        rows.append({"id": p.id, "gross_jtd": jtd, "weight": w, "scaled_jtd": scaled})
        longs.setdefault(p.obligor, [])
        shorts.setdefault(p.obligor, [])
        if scaled > 0:
            longs[p.obligor].append((RANK[p.seniority], scaled))
        elif scaled < 0:
            shorts[p.obligor].append((RANK[p.seniority], scaled))

    obligors = []
    per_bucket: dict[str, list[tuple[float, float, float]]] = {}
    for name in sorted(longs):
        net_long, net_short = offset(longs[name], shorts[name])
        rw = RISK_WEIGHT[ratings[name]]
        obligors.append({"obligor": name, "net_long": net_long, "net_short": net_short, "rw": rw})
        per_bucket.setdefault(bucket_of[name], []).append((rw, net_long, net_short))
    buckets = [{"bucket": b, **_bucket_drc(per_bucket[b])} for b in BUCKETS if b in per_bucket]
    return {
        "positions": sorted(rows, key=lambda r: str(r["id"])),
        "obligors": obligors,
        "buckets": buckets,
        "drc": math.fsum(float(b["drc"]) for b in buckets),  # type: ignore[arg-type]
        "label": LABEL,
    }


def _caller_rw(rws: Sequence[float], maturities: Sequence[float], field: str) -> None:
    for k, (rw, m) in enumerate(zip(rws, maturities, strict=True)):
        _maturity(m, f"{field}/{k}/maturity_years")
        if not 0 <= rw <= RW_CAP:
            raise QfError("E_DOMAIN", f"rw must be in [0, {RW_CAP}]", f"{field}/{k}/rw")


def _net_groups(
    keys: Sequence[tuple[str, ...]], rws: Sequence[float], scaled: Sequence[float], field: str
) -> dict[tuple[str, ...], tuple[float, float]]:
    """Sum the scaled JTDs per netting key (MAR22.29, MAR22.39(1)); one rw per key (KR-115)."""
    rw_of: dict[tuple[str, ...], float] = {}
    for k, (key, rw) in enumerate(zip(keys, rws, strict=True)):
        if rw_of.setdefault(key, rw) != rw:
            raise QfError(
                "E_INPUT", "positions netted together carry different rw", f"{field}/{k}/rw"
            )
    parts: dict[tuple[str, ...], list[float]] = {}
    for key, v in zip(keys, scaled, strict=True):
        parts.setdefault(key, []).append(v)
    return {key: (rw_of[key], math.fsum(vs)) for key, vs in parts.items()}


def drc_sec_nonctp(positions: Sequence[SecPosition]) -> dict[str, object]:
    """Default risk charge for securitisations outside the CTP (MAR22.27 to MAR22.35, KR-55)."""
    _limit(len(positions), "positions")
    _unique([p.id for p in positions], "positions")
    keys = [(p.bucket, p.pool, p.tranche) for p in positions]
    rws = [p.rw for p in positions]
    weights = [
        maturity_weight(p.maturity_years) if p.maturity_years > 0 else 0.0 for p in positions
    ]
    scaled = [w * p.market_value for w, p in zip(weights, positions, strict=True)]
    nets = _net_groups(keys, rws, scaled, "positions")
    _caller_rw(rws, [p.maturity_years for p in positions], "positions")
    per_bucket: dict[str, list[tuple[float, float, float]]] = {}
    for (bucket, _, _), (rw, net) in nets.items():
        per_bucket.setdefault(bucket, []).append((rw, max(net, 0.0), min(net, 0.0)))
    buckets = [{"bucket": b, **_bucket_drc(per_bucket[b])} for b in sorted(per_bucket)]
    rows = [
        {"id": p.id, "weight": w, "scaled_jtd": v}
        for p, w, v in sorted(zip(positions, weights, scaled, strict=True), key=lambda t: t[0].id)
    ]
    return {
        "positions": rows,
        "buckets": buckets,
        "drc": math.fsum(float(b["drc"]) for b in buckets),  # type: ignore[arg-type]
        "label": LABEL,
        "rw_source": RW_SOURCE,
    }


def ctp_total(bucket_drc: Sequence[float]) -> float:
    """MAR22.45: max(sum_b (max(DRC_b, 0) + 0.5 min(DRC_b, 0)), 0)."""
    terms = [max(d, 0.0) + CTP_CROSS_FACTOR * min(d, 0.0) for d in bucket_drc]
    return max(math.fsum(terms), 0.0)


def drc_ctp(
    positions: Sequence[CtpPosition] | None = None, bucket_drc: Sequence[float] | None = None
) -> dict[str, object]:
    """Default risk charge for the correlation trading portfolio (MAR22.36 to MAR22.45, KR-55).

    Exactly one of `positions` and `bucket_drc` (a list of index-level DRC_b)."""
    if (positions is None) == (bucket_drc is None):
        raise QfError("E_INPUT", "give exactly one of positions and bucket_drc", "positions")
    if bucket_drc is not None:
        _limit(len(bucket_drc), "bucket_drc")
        return {"drc": ctp_total(bucket_drc), "label": LABEL, "rw_source": RW_SOURCE}
    assert positions is not None
    _limit(len(positions), "positions")
    _unique([p.id for p in positions], "positions")
    keys = [(p.index, p.series, p.tranche) for p in positions]
    rws = [p.rw for p in positions]
    weights = [
        maturity_weight(p.maturity_years) if p.maturity_years > 0 else 0.0 for p in positions
    ]
    scaled = [w * p.market_value for w, p in zip(weights, positions, strict=True)]
    nets = _net_groups(keys, rws, scaled, "positions")
    _caller_rw(rws, [p.maturity_years for p in positions], "positions")
    long_sum = math.fsum(max(n, 0.0) for _, n in nets.values())
    short_sum = math.fsum(-min(n, 0.0) for _, n in nets.values())
    total = long_sum + short_sum
    hbr = long_sum / total if total > 0 else None  # KR-54 analogue
    per_index: dict[str, list[tuple[float, float]]] = {}
    for (index, _, _), (rw, net) in nets.items():
        per_index.setdefault(index, []).append((rw, net))
    buckets = []
    for index in sorted(per_index):
        wl = math.fsum(rw * n for rw, n in per_index[index] if n > 0)
        ws = math.fsum(rw * -n for rw, n in per_index[index] if n < 0)
        drc_b = wl - (hbr if hbr is not None else 0.0) * ws  # MAR22.44: no floor
        buckets.append({"bucket": index, "wtd_long": wl, "wtd_short": ws, "drc": drc_b})
    rows = [
        {"id": p.id, "weight": w, "scaled_jtd": v}
        for p, w, v in sorted(zip(positions, weights, scaled, strict=True), key=lambda t: t[0].id)
    ]
    return {
        "positions": rows,
        "hbr_ctp": hbr,
        "buckets": buckets,
        "drc": ctp_total([float(b["drc"]) for b in buckets]),  # type: ignore[arg-type]
        "label": LABEL,
        "rw_source": RW_SOURCE,
    }


def rrao(instruments: Sequence[Instrument]) -> dict[str, object]:
    """Residual risk add-on (MAR23.7, MAR23.8)."""
    _limit(len(instruments), "instruments")
    _unique([x.id for x in instruments], "instruments")
    for k, x in enumerate(instruments):
        if not x.gross_notional >= 0:
            raise QfError(
                "E_DOMAIN", "gross_notional must be 0 or above", f"instruments/{k}/gross_notional"
            )
    rows = []
    for x in instruments:
        excluded = x.back_to_back or (x.kind == "OTHER" and x.listed_or_clearable)
        w = RRAO_WEIGHT[x.kind]
        rows.append(
            {
                "id": x.id,
                "weight": w,
                "excluded": excluded,
                "addon": 0.0 if excluded else w * x.gross_notional,
            }
        )
    return {
        "instruments": rows,
        "rrao": math.fsum(float(r["addon"]) for r in rows),  # type: ignore[arg-type]
        "label": LABEL,
    }


guard(globals())
