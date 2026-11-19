"""Leverage ratio and large exposures, simplified (plan item K-8i).

Specification: specifications/06-risk/leverage-large-exposures.md; rulings KR-50 to KR-53, KR-65 to
KR-69 (specifications/stage-k-rulings-w2.md) and KR-128 to KR-135 (same file, wave 2b section).
Source: Basel Framework LEV20, LEV30 (leverage ratio) and LEX10, LEX20, LEX30 (large exposures), read
2026-11-19 in the PDF generated 11/11/2026, pages 787 to 810 and 937 to 956.

"Simplified" means exactly what the spec's Limits section lists: Tier 1, PFE, eligibility of
purchased protection, connectedness, exemptions and the standardised CCFs are the caller's; nothing
else of LEV30 or LEX30 is modelled. Parameters come from specifications/tables/stage_k/
lev_leverage.json and lex_large_exposures.json through `_k_w2b_tables.py`.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from ._k_w2b_tables import LEV, LEX
from .errors import QfError
from .finite import guard

LEVERAGE_LABEL = "simplified leverage ratio (LEV30 subset); not a regulatory return"  # KR-65
LARGE_EXPOSURES_LABEL = "simplified large exposures (LEX subset); not a regulatory return"  # KR-66

ALPHA = float(LEV["deriv.alpha"])  # LEV30.14
MIN_RATIO = float(LEV["min_leverage_ratio"])  # LEV20.7
# LEV30.49-30.54: input category (KR-65) to the table key
CCF_CATEGORIES = {
    "DIRECT_CREDIT_SUBSTITUTE": "direct_credit_substitutes_and_other_100pct_items",
    "FORWARD_PURCHASE": "direct_credit_substitutes_and_other_100pct_items",
    "OTHER_CREDIT_SUBSTITUTE": "direct_credit_substitutes_and_other_100pct_items",
    "NIF_RUF": "nif_ruf",
    "TRANSACTION_CONTINGENT": "transaction_related_contingent",
    "COMMITMENT": "commitments",
    "TRADE_LC": "short_term_trade_lc",
    "UNCONDITIONALLY_CANCELLABLE": "unconditionally_cancellable",
}
LARGE = float(LEX["large_exposure_threshold"])  # LEX10.8
LIMIT = float(LEX["limit"])  # LEX20.1
LIMIT_GSIB = float(LEX["limit.gsib_to_gsib"])  # LEX20.1, LEX40
CCF_FLOOR = float(LEX["exposure.obs_ccf_floor"])  # LEX30.6
TOP_N = int(LEX["report.top_n"])  # LEX20.4(4)
# KR-53 seniority ranks (a short offsets longs of equal or higher rank)
RANKS = {"COVERED": 4, "SENIOR": 3, "NON_SENIOR": 2, "EQUITY": 1}


def _schema(message: str, field: str) -> QfError:
    return QfError("E_SCHEMA", message, field)


def _input(message: str, field: str) -> QfError:
    return QfError("E_INPUT", message, field)


def _domain(message: str, field: str) -> QfError:
    return QfError("E_DOMAIN", message, field)


def _not_negative(value: float, field: str) -> None:
    if value < 0:
        raise _domain(f"{field} must not be negative", field)


# --- leverage ratio -------------------------------------------------------------------------------


@dataclass(frozen=True)
class DerivativeSet:
    v: float
    pfe: float
    cvm_received: float = 0.0
    cvm_provided: float = 0.0


@dataclass(frozen=True)
class WrittenCreditDerivative:
    notional: float
    fair_value: float
    purchased_offset: float = 0.0


@dataclass(frozen=True)
class Sft:
    gross_assets: float
    mna: bool
    exposures: tuple[float, ...] = ()
    collateral: tuple[float, ...] = ()


@dataclass(frozen=True)
class OffBalance:
    notional: float
    ccf_category: str


def derivative_exposure(d: DerivativeSet) -> float:
    """LEV30.14-30.16: alpha (RC + PFE), RC = max(V - CVM received + CVM provided, 0)."""
    return ALPHA * (max(d.v - d.cvm_received + d.cvm_provided, 0.0) + d.pfe)


def written_cd_effective_notional(w: WrittenCreditDerivative) -> float:
    """LEV30.31 and footnote 384: reduced by a negative fair value only, then by purchased
    protection, never below 0."""
    return max(w.notional - max(0.0, -w.fair_value) - w.purchased_offset, 0.0)


def sft_exposure(s: Sft) -> float:
    """LEV30.37: gross assets plus the counterparty measure, netted only under an MNA."""
    if s.mna:
        add = max(0.0, math.fsum(s.exposures) - math.fsum(s.collateral))
    else:
        add = math.fsum(max(0.0, e - c) for e, c in zip(s.exposures, s.collateral, strict=True))
    return s.gross_assets + add


def leverage(
    tier1: float,
    on_balance: Sequence[float] = (),
    derivatives: Sequence[DerivativeSet] = (),
    written_credit_derivatives: Sequence[WrittenCreditDerivative] = (),
    sfts: Sequence[Sft] = (),
    off_balance: Sequence[OffBalance] = (),
) -> dict[str, object]:
    """Leverage ratio exposure measure (LEV20.5) and ratio (LEV20.3), simplified (KR-65)."""
    for o in off_balance:
        if o.ccf_category not in CCF_CATEGORIES:
            raise _schema(f"ccf_category {o.ccf_category} is not listed", "ccf_category")
    for s in sfts:
        if len(s.exposures) != len(s.collateral):
            raise _input("exposures and collateral differ in length", "collateral")
    if not tier1 > 0:
        raise _domain("tier1 must be positive", "tier1")
    for x in on_balance:
        _not_negative(x, "on_balance")
    for d in derivatives:
        _not_negative(d.cvm_received, "cvm_received")
        _not_negative(d.cvm_provided, "cvm_provided")
        _not_negative(d.pfe, "pfe")
    for w in written_credit_derivatives:
        _not_negative(w.notional, "notional")
        _not_negative(w.purchased_offset, "purchased_offset")
    for s in sfts:
        _not_negative(s.gross_assets, "gross_assets")
        for e in s.exposures:
            _not_negative(e, "exposures")
        for c in s.collateral:
            _not_negative(c, "collateral")
    for o in off_balance:
        _not_negative(o.notional, "notional")
    on = math.fsum(on_balance)
    netting_sets = math.fsum(derivative_exposure(d) for d in derivatives)
    written = math.fsum(written_cd_effective_notional(w) for w in written_credit_derivatives)
    deriv = netting_sets + written  # KR-129: written credit derivatives sit in the derivatives part
    sft = math.fsum(sft_exposure(s) for s in sfts)
    obs = math.fsum(
        o.notional * float(LEV["ccf"][CCF_CATEGORIES[o.ccf_category]]) for o in off_balance
    )
    exposure = math.fsum((on, deriv, sft, obs))  # LEV20.5
    if not exposure > 0:
        raise _domain("the exposure measure is zero: no ratio (KR-130)", "on_balance")
    return {
        "on_balance": on,
        "derivatives": deriv,
        "derivative_netting_sets": netting_sets,
        "written_credit_derivatives": written,
        "sfts": sft,
        "off_balance": obs,
        "exposure": exposure,
        "ratio": tier1 / exposure,  # LEV20.3
        "meets_minimum": tier1 >= MIN_RATIO * exposure,  # LEV20.7, binary64 as the spec states
        "label": LEVERAGE_LABEL,
    }


# --- large exposures ------------------------------------------------------------------------------


@dataclass(frozen=True)
class LeCounterparty:
    id: str
    group: str | None = None
    gsib: bool = False
    exempt: bool = False


@dataclass(frozen=True)
class BankingBookExposure:
    counterparty: str
    value: float


@dataclass(frozen=True)
class OffBalanceExposure:
    counterparty: str
    notional: float
    ccf: float


@dataclass(frozen=True)
class Protection:
    counterparty: str
    provider: str
    protected: float


@dataclass(frozen=True)
class TradingPosition:
    """A trading book position as KR-51 with a counterparty (KR-66); maturity_years, cash_equity
    and lgd_applies are read and ignored (LEX30.17-30.18, KR-131)."""

    id: str
    counterparty: str
    seniority: str
    notional: float
    market_value: float
    maturity_years: float | None = None
    cash_equity: bool = False
    lgd_applies: bool = True


def offset_by_seniority(positions: Sequence[tuple[int, float]]) -> tuple[float, float]:
    """KR-53 for one obligor: (rank, signed JTD) pairs to (net long, net short).

    Shorts are taken in descending rank (ties: input order); each consumes the longs of equal or
    higher rank in ascending rank (ties: input order) until it is used up."""
    longs = [[r, j] for r, j in positions if j > 0]
    long_order = sorted(range(len(longs)), key=lambda i: (longs[i][0], i))
    shorts = [(r, -j) for r, j in positions if j < 0]
    left_short: list[float] = []
    for r, amount in sorted(shorts, key=lambda x: -x[0]):  # stable: input order on ties
        for i in long_order:
            if amount <= 0:
                break
            if longs[i][0] >= r and longs[i][1] > 0:
                used = min(amount, longs[i][1])
                longs[i][1] -= used
                amount -= used
        left_short.append(amount)
    return math.fsum(x[1] for x in longs), -math.fsum(left_short)


def jtd(p: TradingPosition) -> float:
    """LEX30.17: gross JTD of MAR22.11 with LGD 100%: LGD x notional + (market value - notional)
    is the market value, kept on the side of the position (notional >= 0 is long, KR-132)."""
    return max(p.market_value, 0.0) if p.notional >= 0 else min(p.market_value, 0.0)


def _le_structure(
    counterparties: Sequence[LeCounterparty],
    refs: Sequence[tuple[str, str]],
    crm: Sequence[Protection],
    trading_book: Sequence[TradingPosition],
) -> None:
    group_of: dict[str, str | None] = {}
    for c in counterparties:
        if c.id in group_of:
            raise _input(f"counterparty {c.id} appears twice (so possibly in two groups)", "id")
        group_of[c.id] = c.group
    for c in counterparties:
        if c.group is not None and c.group in group_of and group_of[c.group] != c.group:
            raise _input(f"group {c.group} is also a counterparty outside it (KR-133)", "group")
    for field, name in refs:
        if name not in group_of:
            raise _input(f"unknown counterparty {name}", field)
    for p in crm:
        if p.provider == p.counterparty:
            raise _input("a counterparty cannot protect itself", "provider")
    ids: set[str] = set()
    for t in trading_book:
        if t.id in ids:
            raise _input(f"position id {t.id} appears twice", "id")
        ids.add(t.id)


def large_exposures(
    tier1: float,
    counterparties: Sequence[LeCounterparty],
    banking_book: Sequence[BankingBookExposure] = (),
    off_balance: Sequence[OffBalanceExposure] = (),
    crm: Sequence[Protection] = (),
    trading_book: Sequence[TradingPosition] = (),
    bank_gsib: bool = False,
) -> dict[str, object]:
    """Exposure per counterparty and per group against the LEX20.1 limit, simplified (KR-66)."""
    for t in trading_book:
        if t.seniority not in RANKS:
            raise _schema(f"seniority {t.seniority} is not listed", "seniority")
    refs = (
        [("counterparty", b.counterparty) for b in banking_book]
        + [("counterparty", o.counterparty) for o in off_balance]
        + [("counterparty", p.counterparty) for p in crm]
        + [("provider", p.provider) for p in crm]
        + [("counterparty", t.counterparty) for t in trading_book]
    )
    _le_structure(counterparties, refs, crm, trading_book)
    if not tier1 > 0:
        raise _domain("tier1 must be positive", "tier1")
    for b in banking_book:
        _not_negative(b.value, "value")
    for o in off_balance:
        _not_negative(o.notional, "notional")
        if not 0 <= o.ccf <= 1:
            raise _domain("ccf must lie in [0, 1]", "ccf")
    for p in crm:
        _not_negative(p.protected, "protected")

    def parts(items: Sequence[tuple[str, float]]) -> dict[str, float]:
        by: dict[str, list[float]] = {c.id: [] for c in counterparties}
        for name, x in items:
            by[name].append(x)
        return {k: math.fsum(v) for k, v in by.items()}

    bb = parts([(b.counterparty, b.value) for b in banking_book])
    obs = parts([(o.counterparty, o.notional * max(o.ccf, CCF_FLOOR)) for o in off_balance])
    protected = parts([(p.counterparty, p.protected) for p in crm])
    received = parts([(p.provider, p.protected) for p in crm])
    positions: dict[str, list[tuple[int, float]]] = {c.id: [] for c in counterparties}
    for t in trading_book:
        positions[t.counterparty].append((RANKS[t.seniority], jtd(t)))
    rows: list[dict[str, object]] = []
    exposure: dict[str, float] = {}
    for c in counterparties:
        net_long, net_short = offset_by_seniority(positions[c.id])  # LEX30.22-30.23, 30.30
        gross = math.fsum((bb[c.id], obs[c.id], net_long))
        if protected[c.id] > gross:
            raise _domain(f"counterparty {c.id}: protected amount above its exposure", "protected")
        exposure[c.id] = math.fsum((gross, -protected[c.id], received[c.id]))  # LEX30.13-30.15
        rows.append({
            "id": c.id, "banking_book": bb[c.id], "off_balance": obs[c.id],
            "trading_book_net_long": net_long, "trading_book_net_short": net_short,
            "protected": protected[c.id], "received": received[c.id], "exposure": exposure[c.id],
        })  # fmt: skip
    members: dict[str, list[LeCounterparty]] = {}
    for c in counterparties:
        members.setdefault(c.group if c.group is not None else c.id, []).append(c)
    groups: list[dict[str, object]] = []
    totals: list[tuple[float, str, bool]] = []
    for name in sorted(members):
        ms = members[name]
        total = math.fsum(exposure[c.id] for c in ms)  # LEX10.9
        counted = math.fsum(exposure[c.id] for c in ms if not c.exempt)  # KR-134
        gsib = bank_gsib and any(c.gsib for c in ms)  # KR-133
        limit = (LIMIT_GSIB if gsib else LIMIT) * tier1
        large = total >= LARGE * tier1  # LEX10.8, binary64 (KR-135)
        totals.append((total, name, large))
        groups.append({
            "group": name, "members": [c.id for c in ms], "exposure": total,
            "share": total / tier1, "large": large, "limit": limit,
            "breach": counted > limit, "exempt": all(c.exempt for c in ms),
        })  # fmt: skip
    ranked = sorted(totals, key=lambda g: (-g[0], g[1]))  # LEX20.4: largest first, ties by name
    report = [name for n, (_, name, large) in enumerate(ranked) if large or n < TOP_N]
    return {
        "counterparties": rows,
        "groups": groups,
        "report": report,
        "label": LARGE_EXPOSURES_LABEL,
    }


guard(globals())
