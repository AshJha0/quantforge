"""CVA risk capital: BA-CVA, reduced and full, and SA-CVA (plan item K-8g).

Specification: specifications/06-risk/cva-capital.md; rulings KR-50, KR-62 to KR-64, KR-67 to KR-69
(specifications/stage-k-rulings-w2.md) and KR-120 to KR-127 (same file, wave 2b section). Source:
Basel Framework MAR50.14 to MAR50.26 (BA-CVA) and MAR50.41 to MAR50.77 (SA-CVA), read 2026-11-19
in the PDF generated 11/11/2026, pages 726 to 750.

Every parameter comes from specifications/tables/stage_k/mar50_cva.json through the generated copy
`_k_w2b_tables.py` (tools/gen_k_w2b_tables.py); nothing is typed here. SA-CVA reuses the
sensitivity-based aggregation of FRTB SA (`frtb.bucket_radicand`, `frtb.cross_radicand`,
`frtb.bucket_key`) and adds what MAR50.53 changes: the hedging disallowance term R, the clipped S_b
always (no unclipped first attempt), no correlation scenarios, and the multiplier m_CVA.
"""

import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from ._k_w2b_tables import MAR50
from .errors import QfError
from .finite import guard
from .frtb import Factor, bucket_key, bucket_radicand, cross_radicand

LABEL = "regulatory formula on caller inputs; not a regulatory return"  # KR-69


def _num(key: str) -> float:
    return float(MAR50[key])


RWA_MULTIPLIER = _num("rwa_multiplier")  # MAR50.1
DS = _num("ba.ds")  # MAR50.14
RHO = _num("ba.rho")  # MAR50.14(2)
ALPHA = _num("ba.alpha")  # MAR50.15(5)
DF_RATE = _num("ba.df_rate")  # MAR50.15(4), footnote 357
BETA = _num("ba.beta")  # MAR50.20
INDEX_SCALAR = _num("ba.index_rw_scalar")  # MAR50.24(4)
R_HEDGE = _num("sa.R")  # MAR50.53(1)
M_CVA = _num("sa.m_cva")  # MAR50.41
WEIGHT_TOLERANCE = 1e-12  # index weights sum to 1 (cva-capital.md, Errors)

SECTORS = tuple(MAR50["ba.rw"])
QUALITIES = ("IG", "HY_NR")  # MAR50.16 Table 1 columns, in that order
VERSIONS = ("REDUCED", "FULL")
# MAR50.26 Table 2, input names (KR-64) to table keys
RELATIONS = {"DIRECT": "direct", "LEGAL": "legally_related", "SECTOR_REGION": "same_sector_region"}


def _rw(sector: str, quality: str) -> float:
    return float(MAR50["ba.rw"][sector][QUALITIES.index(quality)])


def _schema(message: str, field: str) -> QfError:
    return QfError("E_SCHEMA", message, field)


def _input(message: str, field: str) -> QfError:
    return QfError("E_INPUT", message, field)


def _domain(message: str, field: str) -> QfError:
    return QfError("E_DOMAIN", message, field)


# --- BA-CVA -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class NettingSet:
    ead: float
    m: float
    imm: bool = False


@dataclass(frozen=True)
class Counterparty:
    id: str
    sector: str
    quality: str
    netting_sets: tuple[NettingSet, ...] = ()


@dataclass(frozen=True)
class SingleNameHedge:
    counterparty: str
    relation: str
    sector: str
    quality: str
    m: float
    notional: float


@dataclass(frozen=True)
class Constituent:
    sector: str
    quality: str
    weight: float


@dataclass(frozen=True)
class IndexHedge:
    m: float
    notional: float
    constituents: tuple[Constituent, ...] = ()


def discount_factor(m: float, imm: bool = False) -> float:
    """MAR50.15(4): 1 for IMM, else the average discount factor at 5% to M (footnote 357),
    computed as -expm1(-0.05 M) / (0.05 M) (KR-64)."""
    if not m > 0:
        raise _domain("m must be positive", "m")
    if imm:
        return 1.0
    x = DF_RATE * m
    return -math.expm1(-x) / x


def _check_enums(
    counterparties: Sequence[Counterparty],
    version: str,
    single: Sequence[SingleNameHedge],
    index: Sequence[IndexHedge],
) -> None:
    if version not in VERSIONS:
        raise _schema(f"version {version} is not listed", "version")
    for c in counterparties:
        if c.sector not in SECTORS:
            raise _schema(f"sector {c.sector} is not listed", "sector")
        if c.quality not in QUALITIES:
            raise _schema(f"quality {c.quality} is not listed", "quality")
    for h in single:
        if h.relation not in RELATIONS:
            raise _schema(f"relation {h.relation} is not listed", "relation")
        if h.sector not in SECTORS:
            raise _schema(f"sector {h.sector} is not listed", "sector")
        if h.quality not in QUALITIES:
            raise _schema(f"quality {h.quality} is not listed", "quality")
    for ih in index:
        for k in ih.constituents:
            if k.sector not in SECTORS:
                raise _schema(f"sector {k.sector} is not listed", "sector")
            if k.quality not in QUALITIES:
                raise _schema(f"quality {k.quality} is not listed", "quality")


def _ba_structure(
    counterparties: Sequence[Counterparty],
    version: str,
    single: Sequence[SingleNameHedge],
    index: Sequence[IndexHedge],
) -> None:
    """Structural checks (E_INPUT), all before any domain check (KR-67)."""
    ids: set[str] = set()
    for c in counterparties:
        if c.id in ids:
            raise _input(f"counterparty {c.id} appears twice", "id")  # KR-121
        ids.add(c.id)
    if version == "REDUCED" and (single or index):
        raise _input("hedges are recognised only in the FULL version", "single_name_hedges")
    for h in single:
        if h.counterparty not in ids:
            raise _input(f"hedge references unknown counterparty {h.counterparty}", "counterparty")


def _ba_domain(
    counterparties: Sequence[Counterparty],
    single: Sequence[SingleNameHedge],
    index: Sequence[IndexHedge],
) -> None:
    for c in counterparties:
        for ns in c.netting_sets:
            if ns.ead < 0:
                raise _domain(f"counterparty {c.id}: ead must not be negative", "ead")
            if not ns.m > 0:
                raise _domain(f"counterparty {c.id}: m must be positive", "m")
    for h in single:
        if not h.m > 0:
            raise _domain("hedge m must be positive", "m")
        if h.notional < 0:
            raise _domain("hedge notional must not be negative", "notional")
    for ih in index:
        if not ih.m > 0:
            raise _domain("index hedge m must be positive", "m")
        if ih.notional < 0:
            raise _domain("index hedge notional must not be negative", "notional")
        if any(k.weight < 0 for k in ih.constituents):
            raise _domain("index weights must not be negative", "weight")  # KR-122
        total = math.fsum(k.weight for k in ih.constituents)
        if not abs(total - 1.0) <= WEIGHT_TOLERANCE:
            raise _domain("index weights must sum to 1 within 1e-12", "weight")


def _k_reduced(scva: Sequence[float]) -> float:
    """MAR50.14."""
    systematic = RHO * math.fsum(scva)
    return math.sqrt(systematic * systematic + (1.0 - RHO * RHO) * math.fsum(s * s for s in scva))


def ba_cva(
    counterparties: Sequence[Counterparty],
    version: str = "REDUCED",
    single_name_hedges: Sequence[SingleNameHedge] = (),
    index_hedges: Sequence[IndexHedge] = (),
) -> dict[str, object]:
    """BA-CVA capital, reduced (MAR50.14) or full (MAR50.20), with its intermediates."""
    _check_enums(counterparties, version, single_name_hedges, index_hedges)
    _ba_structure(counterparties, version, single_name_hedges, index_hedges)
    _ba_domain(counterparties, single_name_hedges, index_hedges)
    rows: list[dict[str, object]] = []
    scva: list[float] = []
    for c in counterparties:
        dfs = [discount_factor(ns.m, ns.imm) for ns in c.netting_sets]
        s = (
            _rw(c.sector, c.quality)
            * math.fsum(ns.m * ns.ead * df for ns, df in zip(c.netting_sets, dfs, strict=True))
            / ALPHA
        )  # MAR50.15
        scva.append(s)
        rows.append({"id": c.id, "scva": s, "snh": None, "hma": None,
                     "netting_sets": [{"df": df} for df in dfs]})  # fmt: skip
    k_reduced = _k_reduced(scva)
    ih: float | None = None
    k_hedged: float | None = None
    k_full: float | None = None
    if version == "FULL":
        position = {c.id: n for n, c in enumerate(counterparties)}
        snh_parts: list[list[float]] = [[] for _ in counterparties]
        hma_parts: list[list[float]] = [[] for _ in counterparties]
        for h in single_name_hedges:
            r = float(MAR50["ba.r_hc"][RELATIONS[h.relation]])
            x = _rw(h.sector, h.quality) * h.m * h.notional * discount_factor(h.m)
            snh_parts[position[h.counterparty]].append(r * x)  # MAR50.23
            hma_parts[position[h.counterparty]].append((1.0 - r * r) * x * x)  # MAR50.25
        snh = [math.fsum(p) for p in snh_parts]
        hma = [math.fsum(p) for p in hma_parts]
        ih = math.fsum(
            INDEX_SCALAR
            * math.fsum(k.weight * _rw(k.sector, k.quality) for k in i.constituents)
            * i.m
            * i.notional
            * discount_factor(i.m)
            for i in index_hedges
        )  # MAR50.24
        net = [s - h for s, h in zip(scva, snh, strict=True)]
        systematic = RHO * math.fsum(net) - ih
        k_hedged = math.sqrt(
            systematic * systematic
            + (1.0 - RHO * RHO) * math.fsum(x * x for x in net)
            + math.fsum(hma)
        )  # MAR50.21
        k_full = BETA * k_reduced + (1.0 - BETA) * k_hedged  # MAR50.20
        for row, a, b in zip(rows, snh, hma, strict=True):
            row["snh"], row["hma"] = a, b
        capital = DS * k_full
    else:
        capital = DS * k_reduced
    return {
        "version": version,
        "counterparties": rows,
        "ih": ih,
        "k_reduced": k_reduced,
        "k_hedged": k_hedged,
        "k_full": k_full,
        "capital": capital,
        "rwa": RWA_MULTIPLIER * capital,
        "label": LABEL,
    }


# --- SA-CVA -----------------------------------------------------------------------------------------

RISK_CLASSES = ("IR", "FX", "CCS", "RCS", "EQ", "COM")  # MAR50.43, KR-63
KINDS = ("DELTA", "VEGA")
CLASS_KEYS = tuple(f"{c}.{k}" for c in RISK_CLASSES for k in KINDS if (c, k) != ("CCS", "VEGA"))
IR_TENORS = tuple(MAR50["ir.tenors_specified"])  # MAR50.56(1), "inflation" included
IR_CURVE = "CURVE"  # KR-120: the parallel-shift factor of an unspecified currency (MAR50.57)
IR_DELTA_FACTORS = (*IR_TENORS, IR_CURVE)
IR_VEGA_FACTORS = ("IR_VOL", "INFLATION_VOL")  # KR-120, MAR50.58(1)
CCS_TENORS = tuple(MAR50["ccs.tenors"])  # MAR50.65(1)
CCS_BUCKETS = tuple(MAR50["ccs.rw"])  # 1a, 1b, 2..8 (MAR50.65(3) Table 7)
_CURRENCY = re.compile(r"[A-Z]{3}")
_NUMBERED = {"RCS": len(MAR50["rcs.rw"]), "EQ": len(MAR50["eq.rw"]), "COM": len(MAR50["com.rw"])}
_EQ_LARGE_CAP = frozenset(range(1, 9)) | {12}  # KR-124: Table 11 "Large" buckets 1-8, index 12


@dataclass(frozen=True)
class CreditFactor:
    """A counterparty credit spread factor (KR-63)."""

    name: str
    tenor: str
    quality: str
    legal_group: str | None = None
    index: str | None = None
    series: str | None = None


@dataclass(frozen=True)
class Sensitivity:
    bucket: str
    factor: str | CreditFactor
    s_cva: float
    s_hdg: float


@dataclass
class _Entry:
    bucket: str  # aggregation bucket
    key: Factor  # risk factor within that bucket
    rw: float
    s: Sensitivity


def _first(text: str) -> float:
    """A table cell such as "0.90 legally related": its leading number."""
    return float(text.split()[0])


def _upper(table: list[list[str | None]], a: int, b: int) -> float:
    i, j = min(a, b), max(a, b)
    cell = table[i][j]
    assert cell is not None  # upper triangle, filled
    return float(cell)


def _ir_rho(a: str, b: str) -> float:
    """MAR50.56(4) Table 4 (specified currencies), symmetric."""
    table = MAR50["ir.rho_specified"]
    i, j = sorted((IR_TENORS.index(a), IR_TENORS.index(b)))
    return float(table[IR_TENORS[i]][IR_TENORS[j]])


def _ccs_rho(bucket: str, f: CreditFactor, g: CreditFactor) -> float:
    """MAR50.65(4)-(5): rho_tenor x rho_name x rho_quality."""
    spec = MAR50["ccs.rho"]
    if bucket == "8":
        p = spec["bucket_8"]
        if (f.index, f.series) == (g.index, g.series):
            name = _first(p["name"][0])
        elif f.index == g.index:
            name = _first(p["name"][1])
        else:
            name = _first(p["name"][2])
    else:
        p = spec["buckets_1_7"]
        if f.name == g.name:
            name = _first(p["name"][0])
        elif f.legal_group is not None and f.legal_group == g.legal_group:
            name = _first(p["name"][1])
        else:
            name = _first(p["name"][2])
    tenor = _first(p["tenor"][0 if f.tenor == g.tenor else 1])
    quality = _first(p["quality"][0 if f.quality == g.quality else 1])
    return tenor * name * quality


def _rcs_row(b: int) -> int:
    """MAR50.67 Table 9 rows: 1/8 .. 7/14 are rows 0..6, then 15, 16, 17 are rows 7, 8, 9."""
    return b - 1 if b <= 7 else b - 8


def _rcs_gamma(b: str, c: str) -> float:
    x, y = int(b), int(c)
    g = _upper(MAR50["rcs.gamma_same_quality"], _rcs_row(x), _rcs_row(y))
    if x <= 14 and y <= 14 and (x <= 7) != (y <= 7):
        g /= float(MAR50["rcs.gamma_cross_quality_divisor"])  # MAR50.67(2)
    return g


def _eq_gamma(b: str, c: str) -> float:
    """MAR50.71."""
    x, y = int(b), int(c)
    g = MAR50["eq.gamma"]
    if 11 in (x, y):
        return float(g["with_11"])
    if x <= 10 and y <= 10:
        return float(g["within_1_10"])
    if {x, y} == {12, 13}:
        return float(g["12_13"])
    return float(g["12_or_13_with_1_10"])


def _com_gamma(b: str, c: str) -> float:
    """MAR50.75."""
    g = MAR50["com.gamma"]
    return float(g["with_11"] if 11 in (int(b), int(c)) else g["within_1_10"])


def _ccs_gamma(b: str, c: str) -> float:
    """MAR50.64 Table 6; buckets 1a and 1b are bucket 1 (KR-121)."""
    return _upper(MAR50["ccs.gamma"], int(b) - 1, int(c) - 1)


def _parse_class_key(key: str) -> tuple[str, str]:
    """`IR.DELTA` to (`IR`, `DELTA`); an unlisted class or kind is E_SCHEMA."""
    cls, _, kind = key.partition(".")
    if cls not in RISK_CLASSES or kind not in KINDS:
        raise _schema(f"class {key} is not listed", "classes")
    return cls, kind


def _check_factor_schema(cls: str, kind: str, s: Sensitivity) -> None:
    """The factor's type and listed values (E_SCHEMA)."""
    if cls == "CCS":
        if not isinstance(s.factor, CreditFactor):
            raise _schema("a CCS factor is an object", "factor")
        if s.factor.tenor not in CCS_TENORS:
            raise _schema(f"tenor {s.factor.tenor} is not listed", "tenor")
        if s.factor.quality not in QUALITIES:
            raise _schema(f"quality {s.factor.quality} is not listed", "quality")
        return
    if not isinstance(s.factor, str):
        raise _schema("the factor is a string outside CCS", "factor")
    if cls == "IR":
        allowed = IR_DELTA_FACTORS if kind == "DELTA" else IR_VEGA_FACTORS
        if s.factor not in allowed:
            raise _schema(f"IR factor {s.factor} is not listed", "factor")


def _entry(cls: str, kind: str, s: Sensitivity, specified: frozenset[str], rep: str) -> _Entry:
    """Bucket, factor key and risk weight of one sensitivity; structural checks (E_INPUT)."""
    b = s.bucket
    if cls in ("IR", "FX"):
        if _CURRENCY.fullmatch(b) is None:
            raise _input(f"{cls} bucket {b} is not a currency code", "bucket")
        if cls == "FX":
            if b == rep:
                raise _input("the reporting currency is not an FX bucket (MAR50.59)", "bucket")
            return _Entry(b, (), _num("fx.delta_rw" if kind == "DELTA" else "fx.vega_rw"), s)
        f = str(s.factor)
        if kind == "VEGA":
            return _Entry(b, (f,), _num("ir.vega_rw"), s)
        if b in specified:
            if f == IR_CURVE:
                raise _input(f"{b} is a specified currency: tenor factors (MAR50.56)", "factor")
            return _Entry(b, (f,), float(MAR50["ir.rw_specified"][f]), s)
        if f not in (IR_CURVE, "inflation"):
            raise _input(f"{b} is not a specified currency: CURVE and inflation", "factor")
        return _Entry(b, (f,), _num("ir.rw_other_ccy"), s)
    if cls == "CCS":
        if b not in CCS_BUCKETS:
            raise _input(f"CCS bucket {b} is not listed", "bucket")
        assert isinstance(s.factor, CreditFactor)
        q = QUALITIES.index(s.factor.quality)
        rw = float(MAR50["ccs.rw"][b][q])
        agg = "1" if b in ("1a", "1b") else b
        if b == "8":
            if s.factor.index is None or s.factor.series is None:
                raise _input("bucket 8 factors need index and series (KR-63)", "index")
            return _Entry(agg, (s.factor.index, s.factor.series, s.factor.tenor), rw, s)
        return _Entry(agg, (s.factor.name, s.factor.tenor), rw, s)
    if b not in {str(n) for n in range(1, _NUMBERED[cls] + 1)}:
        raise _input(f"{cls} bucket {b} is not listed", "bucket")
    if kind == "DELTA":
        rw = float(MAR50[f"{cls.lower()}.rw"][b])
    elif cls == "EQ":
        rw = float(MAR50["eq.vega_rw"]["large_cap" if int(b) in _EQ_LARGE_CAP else "other"])
    else:
        rw = _num(f"{cls.lower()}.vega_rw")
    return _Entry(b, (), rw, s)


def _check_names(entries: Sequence[_Entry]) -> None:
    """A CCS name (bucket 8: an index series) has one quality and one legal group (KR-123)."""
    seen: dict[tuple[str, tuple[str | None, ...]], tuple[str, str | None]] = {}
    for e in entries:
        f = e.s.factor
        assert isinstance(f, CreditFactor)
        who = (f.index, f.series) if e.bucket == "8" else (f.name,)
        attrs = (f.quality, f.legal_group)
        if seen.setdefault((e.bucket, who), attrs) != attrs:
            raise _input(f"name {f.name} has two qualities or legal groups", "factor")


def _rho_for(cls: str, kind: str, bucket: str) -> Callable[[Factor, Factor], float]:
    if cls == "IR" and kind == "VEGA":
        return lambda a, b: _num("ir.vega_rho")
    if cls == "IR":
        return lambda a, b: (
            _ir_rho(str(a[0]), str(b[0]))
            if IR_CURVE not in (a[0], b[0])
            else _num("ir.rho_other_ccy_curve_inflation")
        )
    if cls == "CCS":  # the CreditFactor rides at the end of the key (_class_capital)
        return lambda a, b: _ccs_rho(bucket, _credit(a[-1]), _credit(b[-1]))
    return lambda a, b: 1.0  # one factor per bucket: never called with two entries


def _credit(x: object) -> CreditFactor:
    assert isinstance(x, CreditFactor)
    return x


def _gamma_for(cls: str) -> Callable[[str, str], float]:
    if cls == "IR":
        return lambda b, c: _num("ir.gamma")
    if cls == "FX":
        return lambda b, c: _num("fx.gamma")
    return {"CCS": _ccs_gamma, "RCS": _rcs_gamma, "EQ": _eq_gamma, "COM": _com_gamma}[cls]


def _class_capital(
    cls: str, kind: str, entries: Sequence[_Entry], m_cva: float
) -> tuple[dict[str, object], float]:
    """MAR50.53 for one risk class and kind: the output object and K."""
    by_bucket: dict[str, list[_Entry]] = {}
    for e in entries:
        by_bucket.setdefault(e.bucket, []).append(e)
    order = sorted(by_bucket, key=bucket_key)
    ks: list[float] = []
    sb: list[float] = []
    rows: list[dict[str, object]] = []
    for name in order:
        members = by_bucket[name]
        ws = [e.rw * e.s.s_cva - e.rw * e.s.s_hdg for e in members]  # MAR50.51-50.52
        wsh = [e.rw * e.s.s_hdg for e in members]
        items = [
            ((*e.key, e.s.factor) if cls == "CCS" else e.key, w)
            for e, w in zip(members, ws, strict=True)
        ]
        radicand = bucket_radicand(items, _rho_for(cls, kind, name)) + R_HEDGE * sum(
            h * h for h in wsh
        )
        k_b = math.sqrt(max(0.0, radicand))  # KR-62
        total = sum(ws)
        s_b = max(-k_b, min(total, k_b))  # MAR50.53(3)
        ks.append(k_b)
        sb.append(s_b)
        rows.append({"bucket": name, "k_b": k_b, "s_b": s_b, "sum_ws": total,
                     "floored": radicand < 0})  # fmt: skip
    k = m_cva * math.sqrt(max(0.0, cross_radicand(order, ks, sb, _gamma_for(cls))))
    return {"buckets": rows, "k": k}, k


def sa_cva(
    classes: Mapping[str, Sequence[Sensitivity]],
    reporting_currency: str,
    m_cva: float = M_CVA,
) -> dict[str, object]:
    """SA-CVA capital (MAR50.42-50.53): the sum of the delta and vega capital of every class."""
    parsed = {key: _parse_class_key(key) for key in classes}
    for key, items in classes.items():
        for s in items:
            _check_factor_schema(*parsed[key], s)
    if ("CCS", "VEGA") in parsed.values():
        raise _input("counterparty credit spread has no vega (MAR50.45)", "classes")
    if _CURRENCY.fullmatch(reporting_currency) is None:
        raise _input("reporting_currency is not a currency code", "reporting_currency")
    specified = frozenset(
        reporting_currency if c == "reporting" else c for c in MAR50["ir.specified_currencies"]
    )
    built: dict[str, list[_Entry]] = {}
    for key in CLASS_KEYS:
        if key not in classes:
            continue
        cls, kind = parsed[key]
        entries = [_entry(cls, kind, s, specified, reporting_currency) for s in classes[key]]
        seen: set[tuple[str, Factor]] = set()
        for e in entries:
            if (e.bucket, e.key) in seen:
                raise _input(f"{key}: bucket {e.bucket} holds one risk factor twice", "factor")
            seen.add((e.bucket, e.key))
        if cls == "CCS":
            _check_names(entries)
        built[key] = entries
    if not m_cva >= 1:
        raise _domain("m_cva must be at least 1 (MAR50.41)", "m_cva")
    out: dict[str, object] = {}
    ks: list[float] = []
    for key, entries in built.items():
        out[key], k = _class_capital(*parsed[key], entries, m_cva)
        ks.append(k)
    total = math.fsum(ks)
    return {
        "classes": out,
        "m_cva": m_cva,
        "total": total,
        "rwa": RWA_MULTIPLIER * total,
        "label": LABEL,
    }


guard(globals())
