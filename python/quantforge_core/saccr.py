"""Standardised approach for counterparty credit risk, SA-CCR (plan item K-8d).

Specification: specifications/06-risk/sa-ccr.md; rulings KR-30 to KR-39
(specifications/stage-k-rulings-w1b.md). Source: Basel Framework CRE52.1 to CRE52.73, with the five
worked examples of CRE99.20 to CRE99.97 (the BCBS 279 Annex 4a portfolios), read 2026-11-19 in the
Basel Framework PDF generated 11/11/2026, pages 434 to 462 and 524 to 540.

The supervisory parameters (CRE52.72 Table 2) are data shared by the four builds:
specifications/06-risk/sa-ccr-parameters.json. They are repeated here as Python literals and a
test checks that the two agree.
"""

import math
from dataclasses import dataclass

from .errors import QfError

ALPHA = 1.4  # CRE52.1
FLOOR = 0.05  # CRE52.23
YEAR_DAYS = 250  # CRE52.49, CRE52.53: 250 business days a year
MIN_YEARS = 10 / YEAR_DAYS  # CRE52.34 (SD floor), CRE52.48 (M floor)
SD_RATE = 0.05  # CRE52.34
CLASSES = ("IR", "FX", "CREDIT", "EQUITY", "COMMODITY")
TREATMENTS = ("NORMAL", "BASIS", "VOLATILITY")
TREATMENT_SCALE = {"NORMAL": 1.0, "BASIS": 0.5, "VOLATILITY": 5.0}  # CRE52.46, CRE52.47, CRE52.73
KINDS = ("LINEAR", "OPTION", "CDO")
POSITIONS = ("LONG", "SHORT", "BOUGHT", "SOLD")
OPTION_TYPES = ("CALL", "PUT")

# CRE52.72 Table 2: (supervisory factor, correlation or None, supervisory option volatility)
TABLE2: dict[tuple[str, str], tuple[float, float | None, float]] = {
    ("IR", ""): (0.005, None, 0.50),
    ("FX", ""): (0.04, None, 0.15),
    ("CREDIT", "AAA"): (0.0038, 0.50, 1.00),
    ("CREDIT", "AA"): (0.0038, 0.50, 1.00),
    ("CREDIT", "A"): (0.0042, 0.50, 1.00),
    ("CREDIT", "BBB"): (0.0054, 0.50, 1.00),
    ("CREDIT", "BB"): (0.0106, 0.50, 1.00),
    ("CREDIT", "B"): (0.016, 0.50, 1.00),
    ("CREDIT", "CCC"): (0.06, 0.50, 1.00),
    ("CREDIT", "IG"): (0.0038, 0.80, 0.80),
    ("CREDIT", "SG"): (0.0106, 0.80, 0.80),
    ("EQUITY", "SINGLE"): (0.32, 0.50, 1.20),
    ("EQUITY", "INDEX"): (0.20, 0.80, 0.75),
    ("COMMODITY", "ELECTRICITY"): (0.40, 0.40, 1.50),
    ("COMMODITY", "OIL_GAS"): (0.18, 0.40, 0.70),
    ("COMMODITY", "METALS"): (0.18, 0.40, 0.70),
    ("COMMODITY", "AGRICULTURAL"): (0.18, 0.40, 0.70),
    ("COMMODITY", "OTHER"): (0.18, 0.40, 0.70),
}
SUBCLASSES = tuple(sorted({s for (_, s) in TABLE2 if s}))
# CRE52.45(5): four commodity hedging sets; electricity and oil/gas are energy (CRE99.67, KR-33)
COMMODITY_SET = {
    "ELECTRICITY": "ENERGY",
    "OIL_GAS": "ENERGY",
    "METALS": "METALS",
    "AGRICULTURAL": "AGRICULTURAL",
    "OTHER": "OTHER",
}


@dataclass(frozen=True)
class Trade:
    id: str
    asset_class: str
    notional: float
    market_value: float
    maturity: float
    kind: str = "LINEAR"
    position: str = "LONG"
    treatment: str = "NORMAL"
    start: float | None = None
    end: float | None = None
    hedging_set: str | None = None
    entity: str | None = None
    subclass: str | None = None
    option_type: str | None = None
    underlying_price: float | None = None
    strike: float | None = None
    exercise: float | None = None
    shift: float = 0.0
    attachment: float | None = None
    detachment: float | None = None


@dataclass(frozen=True)
class Margin:
    threshold: float
    mta: float
    nica: float
    remargin_days: int
    mpor_days: int | None = None
    illiquid: bool = False
    disputes: bool = False


def _phi(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _need(t: Trade, value: object, field: str, why: str) -> None:
    if value is None:
        raise QfError("E_INPUT", f"trade {t.id}: {field} is required {why}", field)


def _structure(trades: list[Trade]) -> None:
    """Structural checks (E_INPUT), all before any domain check (HR-122 order)."""
    if not trades:
        raise QfError("E_INPUT", "trades is empty", "trades")
    seen: set[str] = set()
    for t in trades:
        if t.id in seen:
            raise QfError("E_INPUT", f"duplicate trade id {t.id}", "id")
        seen.add(t.id)
        c = t.asset_class
        if c in ("IR", "CREDIT"):
            _need(t, t.start, "start", "for IR and CREDIT trades")
            _need(t, t.end, "end", "for IR and CREDIT trades")
        if c in ("IR", "FX") or t.treatment != "NORMAL":
            _need(t, t.hedging_set, "hedging_set", "for IR, FX, basis and volatility trades")
        if c in ("CREDIT", "EQUITY", "COMMODITY"):
            _need(t, t.entity, "entity", "for CREDIT, EQUITY and COMMODITY trades")
            _need(t, t.subclass, "subclass", "for CREDIT, EQUITY and COMMODITY trades")
            if (c, t.subclass) not in TABLE2:
                raise QfError(
                    "E_INPUT",
                    f"trade {t.id}: subclass {t.subclass} is not a {c} subclass",
                    "subclass",
                )
        elif t.subclass is not None:
            raise QfError("E_INPUT", f"trade {t.id}: {c} trades take no subclass", "subclass")
        linear = t.position in ("LONG", "SHORT")
        if (t.kind == "LINEAR") != linear:
            raise QfError(
                "E_INPUT",
                f"trade {t.id}: position {t.position} does not fit kind {t.kind}",
                "position",
            )
        if t.kind == "OPTION":
            for field, v in (
                ("option_type", t.option_type),
                ("underlying_price", t.underlying_price),
                ("strike", t.strike),
                ("exercise", t.exercise),
            ):
                _need(t, v, field, "for OPTION trades")
        if t.kind == "CDO":
            if c != "CREDIT":
                raise QfError("E_INPUT", f"trade {t.id}: CDO tranches are CREDIT trades", "kind")
            _need(t, t.attachment, "attachment", "for CDO trades")
            _need(t, t.detachment, "detachment", "for CDO trades")
    entity_sub: dict[tuple[str, str, str, str], str] = {}
    for t in trades:
        if t.entity is None or t.subclass is None:
            continue
        key = (t.asset_class, t.treatment, t.hedging_set or "", t.entity)
        if entity_sub.setdefault(key, t.subclass) != t.subclass:
            raise QfError("E_INPUT", f"entity {t.entity} has two subclasses", "subclass")


def _domain(trades: list[Trade], collateral: float, margin: Margin | None) -> None:
    for t in trades:
        if not t.notional > 0:
            raise QfError("E_DOMAIN", f"trade {t.id}: notional must be positive", "notional")
        if not t.maturity > 0:
            raise QfError("E_DOMAIN", f"trade {t.id}: maturity must be positive", "maturity")
        if t.start is not None and t.end is not None and not 0 <= t.start <= t.end:
            raise QfError("E_DOMAIN", f"trade {t.id}: need 0 <= start <= end", "start")
        if t.kind == "OPTION":
            p = (t.underlying_price or 0.0) + t.shift
            k = (t.strike or 0.0) + t.shift
            if not (p > 0 and k > 0):
                raise QfError(
                    "E_DOMAIN", f"trade {t.id}: shifted price and strike must be positive", "strike"
                )
            if not (t.exercise or 0.0) > 0:
                raise QfError("E_DOMAIN", f"trade {t.id}: exercise must be positive", "exercise")
        if t.kind == "CDO":
            a, d = t.attachment or 0.0, t.detachment or 0.0
            if not 0 <= a < d <= 1:
                raise QfError(
                    "E_DOMAIN",
                    f"trade {t.id}: need 0 <= attachment < detachment <= 1",
                    "attachment",
                )
    del collateral  # any finite value is allowed (CRE52.10)
    if margin is not None:
        if margin.threshold < 0:
            raise QfError("E_DOMAIN", "threshold must not be negative", "threshold")
        if margin.mta < 0:
            raise QfError("E_DOMAIN", "mta must not be negative", "mta")
        if margin.remargin_days < 1:
            raise QfError("E_DOMAIN", "remargin_days must be at least 1", "remargin_days")
        if margin.mpor_days is not None and margin.mpor_days < 1:
            raise QfError("E_DOMAIN", "mpor_days must be at least 1", "mpor_days")


def supervisory_duration(start: float, end: float) -> float:
    """CRE52.34, floored at ten business days."""
    sd = (math.exp(-SD_RATE * start) - math.exp(-SD_RATE * end)) / SD_RATE
    return max(sd, MIN_YEARS)


def mpor_floor(margin: Margin, trade_count: int) -> int:
    """CRE52.50 and CRE52.51 floors, in business days (ruling KR-35)."""
    base = 10 if margin.remargin_days == 1 else 9 + margin.remargin_days
    if trade_count > 5000 or margin.illiquid:
        base = max(base, 20)
    return 2 * base if margin.disputes else base


def _option_vol(t: Trade) -> float:
    return TABLE2[(t.asset_class, t.subclass or "")][2]


def supervisory_delta(t: Trade) -> float:
    """CRE52.39 to CRE52.41."""
    if t.kind == "LINEAR":
        return 1.0 if t.position == "LONG" else -1.0
    if t.kind == "CDO":
        a, d = t.attachment or 0.0, t.detachment or 0.0
        v = 15.0 / ((1.0 + 14.0 * a) * (1.0 + 14.0 * d))
        return v if t.position == "BOUGHT" else -v
    sigma, tt = _option_vol(t), t.exercise or 0.0
    p, k = (t.underlying_price or 0.0) + t.shift, (t.strike or 0.0) + t.shift
    d1 = (math.log(p / k) + 0.5 * sigma * sigma * tt) / (sigma * math.sqrt(tt))
    sign = 1.0 if t.position == "BOUGHT" else -1.0
    return sign * (_phi(d1) if t.option_type == "CALL" else -_phi(-d1))


def _factor(t: Trade) -> float:
    return TABLE2[(t.asset_class, t.subclass or "")][0] * TREATMENT_SCALE[t.treatment]


def _bucket(end: float) -> int:
    """CRE52.57 step 3 on E (CRE52.31(3)); 1 and 5 years fall in bucket 2 (ruling KR-32)."""
    return 1 if end < 1 else 2 if end <= 5 else 3


def _single_factor(addons: list[tuple[float, float]]) -> float:
    """CRE52.61 step 4, CRE52.66 step 4, CRE52.70 step 5: (rho, add-on) pairs."""
    sys_part = math.fsum(r * a for r, a in addons)
    idio = math.fsum((1.0 - r * r) * a * a for r, a in addons)
    return math.sqrt(sys_part * sys_part + idio)


def _addons(
    trades: list[Trade], mf: list[float], d: list[float], ir_offset: bool
) -> tuple[dict[str, float], list[dict[str, object]], list[float], list[float]]:
    """Asset class add-ons, hedging-set rows, trade deltas and trade effective notionals."""
    deltas = [supervisory_delta(t) for t in trades]
    eff = [d[i] * mf[i] * deltas[i] for i in range(len(trades))]
    groups: dict[tuple[str, str, str], list[int]] = {}
    for i, t in enumerate(trades):
        if t.asset_class == "COMMODITY" and t.treatment == "NORMAL":
            key = COMMODITY_SET[t.subclass or ""]
        elif t.asset_class in ("CREDIT", "EQUITY") and t.treatment == "NORMAL":
            key = ""
        else:
            key = t.hedging_set or ""
        groups.setdefault((t.asset_class, t.treatment, key), []).append(i)
    by_class = dict.fromkeys(CLASSES, 0.0)
    rows: list[dict[str, object]] = []
    order = sorted(groups, key=lambda g: (CLASSES.index(g[0]), TREATMENTS.index(g[1]), g[2]))
    for g in order:
        members = groups[g]
        cls, treatment = g[0], g[1]
        if cls == "IR":
            db = [0.0, 0.0, 0.0]
            parts: list[list[float]] = [[], [], []]
            for i in members:
                parts[_bucket(trades[i].end or 0.0) - 1].append(eff[i])
            db = [math.fsum(p) for p in parts]
            if ir_offset:
                en = math.sqrt(
                    max(
                        db[0] ** 2
                        + db[1] ** 2
                        + db[2] ** 2
                        + 1.4 * db[0] * db[1]
                        + 1.4 * db[1] * db[2]
                        + 0.6 * db[0] * db[2],
                        0.0,
                    )
                )
            else:
                en = abs(db[0]) + abs(db[1]) + abs(db[2])
            addon = 0.005 * TREATMENT_SCALE[treatment] * en
        elif cls == "FX":
            addon = 0.04 * TREATMENT_SCALE[treatment] * abs(math.fsum(eff[i] for i in members))
        else:
            entities: dict[str, list[int]] = {}
            for i in members:
                entities.setdefault(trades[i].entity or "", []).append(i)
            pairs = []
            for name in sorted(entities):
                idx = entities[name]
                first = trades[idx[0]]
                rho = TABLE2[(cls, first.subclass or "")][1] or 0.0
                pairs.append((rho, _factor(first) * math.fsum(eff[i] for i in idx)))
            addon = _single_factor(pairs)
        by_class[cls] += addon
        rows.append({"asset_class": cls, "treatment": treatment, "key": g[2], "addon": addon})
    return by_class, rows, deltas, eff


def multiplier(v_minus_c: float, addon: float) -> float:
    """CRE52.23; with a zero aggregate add-on, the limit of the formula (ruling KR-36).

    V - C >= 0 gives exp(...) >= 1 and so exactly 1, without evaluating an exponential that can
    overflow when the add-on is tiny."""
    if v_minus_c >= 0:
        return 1.0
    if addon == 0.0:
        return FLOOR
    return min(1.0, FLOOR + (1.0 - FLOOR) * math.exp(v_minus_c / (2.0 * (1.0 - FLOOR) * addon)))


def _netting(
    trades: list[Trade],
    mf: list[float],
    d: list[float],
    v: float,
    c: float,
    rc: float,
    ir_offset: bool,
) -> tuple[
    float, float, float, dict[str, float], list[dict[str, object]], list[float], list[float]
]:
    by_class, rows, deltas, eff = _addons(trades, mf, d, ir_offset)
    aggregate = math.fsum(by_class[k] for k in CLASSES)  # CRE52.25
    m = multiplier(v - c, aggregate)
    pfe = m * aggregate  # CRE52.20
    ead = ALPHA * (rc + pfe)  # CRE52.1
    return ead, pfe, m, by_class, rows, deltas, eff


def ead(
    trades: list[Trade],
    collateral: float = 0.0,
    margin: Margin | None = None,
    ir_offset: bool = True,
) -> dict[str, object]:
    """EAD of one netting set under SA-CCR (CRE52.1)."""
    _structure(trades)
    _domain(trades, collateral, margin)
    v = math.fsum(t.market_value for t in trades)
    c = collateral
    sd: list[float | None] = []
    d: list[float] = []
    for t in trades:
        if t.asset_class in ("IR", "CREDIT"):
            s = supervisory_duration(t.start or 0.0, t.end or 0.0)
            sd.append(s)
            d.append(t.notional * s)  # CRE52.34
        else:
            sd.append(None)
            d.append(t.notional)  # CRE52.35, CRE52.36
    mf_un = [math.sqrt(min(max(t.maturity, MIN_YEARS), 1.0)) for t in trades]  # CRE52.48
    rc_un = max(v - c, 0.0)  # CRE52.10
    un = _netting(trades, mf_un, d, v, c, rc_un, ir_offset)
    mpor: int | None = None
    if margin is None:
        result, mf, rc = un, mf_un, rc_un
        ead_un: float | None = None
        capped = False
    else:
        floor = mpor_floor(margin, len(trades))
        mpor = max(floor, margin.mpor_days or 0)  # CRE52.50
        mf_m = 1.5 * math.sqrt(mpor / YEAR_DAYS)  # CRE52.52
        mf = [mf_m] * len(trades)
        rc = max(v - c, margin.threshold + margin.mta - margin.nica, 0.0)  # CRE52.18
        result = _netting(trades, mf, d, v, c, rc, ir_offset)
        ead_un = un[0]
        capped = un[0] < result[0]  # CRE52.2: margined EAD capped at the unmargined EAD
    total, pfe, m, by_class, rows, deltas, eff = result
    out_trades = [
        {
            "id": t.id,
            "supervisory_duration": sd[i],
            "adjusted_notional": d[i],
            "maturity_factor": mf[i],
            "delta": deltas[i],
            "effective_notional": eff[i],
            "supervisory_factor": _factor(t),
        }
        for i, t in enumerate(trades)
    ]
    aggregate = math.fsum(by_class[k] for k in CLASSES)
    return {
        "ead": min(total, ead_un) if ead_un is not None else total,
        "rc": rc,
        "pfe": pfe,
        "multiplier": m,
        "addon_aggregate": aggregate,
        "addon": by_class,
        "v": v,
        "c": c,
        "margined": margin is not None,
        "mpor_days": mpor,
        "ead_unmargined": ead_un,
        "capped": capped,
        "hedging_sets": rows,
        "trades": out_trades,
    }
