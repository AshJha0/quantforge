"""Stage K wave 2 blind packet (DR-H2): inputs of the 58 hand value cases, and nothing else.

Each case is written out in full from the "Golden cases" tables of the four PROPOSED specs
(specifications/06-risk/frtb-drc-rrao.md, frtb-ima.md, cva-capital.md, leverage-large-exposures.md).
Where a spec row says "as 0001 with ..." or "worked example", the inputs are copied here in full, so the blind
side never needs the stripped text. Where a spec row leaves an input unstated that the operation needs
(a bucket, a Tier 1, a maturity that the rule then ignores), the value chosen here is listed in INPUT_CHOICES
and in program/STAGE_K_BLIND_W2.md; none of them changes a printed expected value.

This module holds inputs only. Expected outputs live in k2_expected.json (hidden side, never in the packet).
"""
import datetime as _dt

ITEMS = {
    "K-8a": "frtb-drc-rrao",
    "K-8f": "frtb-ima",
    "K-8g": "cva-capital",
    "K-8i": "leverage-large-exposures",
}


def _pos(pid, obligor, bucket, seniority, notional, mv, m, **kw):
    d = {"id": pid, "obligor": obligor, "bucket": bucket, "seniority": seniority,
         "notional": notional, "market_value": mv, "maturity_years": m}
    d.update(kw)
    return d


def _days(a, b):
    d0, d1 = _dt.date.fromisoformat(a), _dt.date.fromisoformat(b)
    return [(d0 + _dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def _every15():
    d0 = _dt.date(2025, 7, 5)
    return [(d0 + _dt.timedelta(days=15 * k)).isoformat() for k in range(24)]


def _h():
    return [((7919 * t + 13) % 1009) - 504 for t in range(250)]


# ---- K-8a ----------------------------------------------------------------------------------------------
_X_LONG = _pos("p1", "X", "CORPORATE", "SENIOR", 100, 100, 5)

CASES = [
    ("drc_k-0001", "K-8a", "risk.frtb.drc_nonsec",
     {"positions": [_X_LONG], "ratings": {"X": "BBB"}}),
    ("drc_k-0002", "K-8a", "risk.frtb.drc_nonsec",
     {"positions": [_pos("p1", "X", "CORPORATE", "SENIOR", 100, 100, 0.5)], "ratings": {"X": "BBB"}}),
    ("drc_k-0004", "K-8a", "risk.frtb.drc_nonsec",
     {"positions": [_X_LONG, _pos("p2", "X", "CORPORATE", "SENIOR", -100, -100, 0.25)], "ratings": {"X": "BBB"}}),
    ("drc_k-0005", "K-8a", "risk.frtb.drc_nonsec",
     {"positions": [_pos("p1", "X", "CORPORATE", "SENIOR", 100, 80, 5),
                    _pos("p2", "Y", "CORPORATE", "SENIOR", -100, -80, 5)],
      "ratings": {"X": "A", "Y": "BB"}}),
    ("drc_k-0006", "K-8a", "risk.frtb.drc_nonsec",
     {"positions": [_pos("p1", "X", "CORPORATE", "SENIOR", 100, 80, 5),
                    _pos("p2", "Y", "CORPORATE", "SENIOR", -100, -80, 5)],
      "ratings": {"X": "A", "Y": "AAA"}}),
    ("drc_k-0007", "K-8a", "risk.frtb.drc_nonsec",
     {"positions": [_pos("stock", "Z", "CORPORATE", "EQUITY", 50, 50, 2, cash_equity=True),
                    _pos("bond", "Z", "CORPORATE", "SENIOR", -40, -40, 2)],
      "ratings": {"Z": "BB"}}),
    ("drc_k-0008", "K-8a", "risk.frtb.drc_nonsec",
     {"positions": [_pos("bond", "Z", "CORPORATE", "SENIOR", 40, 40, 2),
                    _pos("stock", "Z", "CORPORATE", "EQUITY", -50, -50, 2, cash_equity=True)],
      "ratings": {"Z": "BB"}}),
    ("drc_k-0009", "K-8a", "risk.frtb.drc_nonsec",
     {"positions": [_pos("p1", "X", "CORPORATE", "SENIOR", 100, 100, 5),
                    _pos("p2", "S", "SOVEREIGN", "SENIOR", 200, 200, 5)],
      "ratings": {"X": "A", "S": "AA"}}),
    ("drc_k-0010", "K-8a", "risk.frtb.drc_nonsec",
     {"positions": [_pos("sold_put", "X", "CORPORATE", "SENIOR", 100, 92, 5)], "ratings": {"X": "BBB"},
      "note": "sold put on a bond already mapped by the caller to (notional, bond-equivalent market value) per MAR22.14 Table 1"}),
    ("drc_k-0011", "K-8a", "risk.frtb.drc_nonsec",
     {"positions": [_pos("p1", "U", "CORPORATE", "SENIOR", 100, 100, 5),
                    _pos("p2", "D", "CORPORATE", "EQUITY", 5, 5, 2, cash_equity=True)],
      "ratings": {"U": "UNRATED", "D": "DEFAULTED"}}),
    ("ctp_k-0002", "K-8a", "risk.frtb.drc_ctp",
     {"positions": [{"id": "a", "index": "A", "series": "S1", "tranche": "T1", "market_value": 1000, "maturity_years": 5, "rw": 0.1},
                    {"id": "b", "index": "B", "series": "S1", "tranche": "T1", "market_value": -1000, "maturity_years": 5, "rw": 0.1}]}),
    ("ctp_k-0003", "K-8a", "risk.frtb.drc_ctp", {"bucket_drc": [-10]}),
    ("sec_k-0001", "K-8a", "risk.frtb.drc_sec_nonctp",
     {"positions": [{"id": "l", "bucket": "RMBS-EU", "pool": "P1", "tranche": "T1", "market_value": 50, "maturity_years": 5, "rw": 0.2},
                    {"id": "s", "bucket": "RMBS-EU", "pool": "P1", "tranche": "T2", "market_value": -20, "maturity_years": 5, "rw": 0.2}]}),
    ("rrao_k-0001", "K-8a", "risk.frtb.rrao",
     {"instruments": [{"id": "e", "gross_notional": 1000000, "kind": "EXOTIC", "listed_or_clearable": False, "back_to_back": False},
                      {"id": "o", "gross_notional": 2000000, "kind": "OTHER", "listed_or_clearable": False, "back_to_back": False}]}),
    ("rrao_k-0002", "K-8a", "risk.frtb.rrao",
     {"instruments": [{"id": "o", "gross_notional": 5000000, "kind": "OTHER", "listed_or_clearable": True, "back_to_back": False},
                      {"id": "e1", "gross_notional": 1000000, "kind": "EXOTIC", "listed_or_clearable": True, "back_to_back": False},
                      {"id": "e2", "gross_notional": 3000000, "kind": "EXOTIC", "listed_or_clearable": False, "back_to_back": True}]}),
    ("rrao_k-0003", "K-8a", "risk.frtb.rrao", {"instruments": []}),

    # ---- K-8f ------------------------------------------------------------------------------------------
    ("es_k-0003", "K-8f", "risk.frtb.ima.es_lh", {"es_t": [10, 8, 6, 4, 2]}),
    ("es_k-0004", "K-8f", "risk.frtb.ima.es_lh", {"es_t": [10, 0, 0, 0, 0]}),
    ("es_k-0005", "K-8f", "risk.frtb.ima.es_lh", {"pnl": [_h(), [], [], [], []]}),
    ("est_k-0001", "K-8f", "risk.frtb.ima.es_stressed", {"es_rs": 12, "es_fc": 10, "es_rc": 8}),
    ("est_k-0002", "K-8f", "risk.frtb.ima.es_stressed", {"es_rs": 12, "es_fc": 7, "es_rc": 8}),
    ("imcc_k-0001", "K-8f", "risk.frtb.ima.imcc",
     {"portfolio": {"es_rs": 12, "es_fc": 10, "es_rc": 8},
      "classes": {"IR": {"es_rs": 6, "es_fc": 5, "es_rc": 4}, "EQ": {"es_rs": 5, "es_fc": 4, "es_rc": 5}}}),
    ("ses_k-0001", "K-8f", "risk.frtb.ima.ses", {"idio_credit": [3, 4], "idio_equity": [5, 12], "other": [1, 2, 2]}),
    ("ses_k-0002", "K-8f", "risk.frtb.ima.ses", {"idio_credit": [], "idio_equity": [], "other": [10]}),
    ("cap_k-0001", "K-8f", "risk.frtb.ima.capital",
     {"imcc_prev": 100, "ses_prev": 20, "imcc_avg": 90, "ses_avg": 15, "exceptions": 6, "qualitative_addon": 0,
      "drc": 0, "desks": [{"zone": "GREEN", "sa": 200}], "c_u": 0, "sa_all": 1000}),
    ("cap_k-0002", "K-8f", "risk.frtb.ima.capital",
     {"imcc_prev": 100, "ses_prev": 20, "imcc_avg": 90, "ses_avg": 15, "exceptions": 6, "qualitative_addon": 0,
      "drc": 30, "desks": [{"zone": "GREEN", "sa": 150}, {"zone": "AMBER", "sa": 100}], "c_u": 40, "sa_all": 300}),
    ("cap_k-0003", "K-8f", "risk.frtb.ima.capital",
     {"imcc_prev": 100, "ses_prev": 20, "imcc_avg": 90, "ses_avg": 15, "exceptions": 6, "qualitative_addon": 0,
      "drc": 30, "desks": [{"zone": "GREEN", "sa": 180}], "c_u": 40, "sa_all": 220}),
    ("rfet_k-0001", "K-8f", "risk.frtb.rfet", {"as_of": "2026-06-30", "observations": _days("2026-03-23", "2026-06-30")}),
    ("rfet_k-0002", "K-8f", "risk.frtb.rfet", {"as_of": "2026-06-30", "observations": _every15()}),
    ("rfet_k-0003", "K-8f", "risk.frtb.rfet", {"as_of": "2026-06-30", "observations": _days("2025-07-01", "2025-07-30")}),
    ("rfet_k-0004", "K-8f", "risk.frtb.rfet",
     {"as_of": "2026-06-30", "observations": [d for d in _every15()[:23] for _ in (0, 1)]}),

    # ---- K-8g ------------------------------------------------------------------------------------------
    ("cva_k-0001", "K-8g", "risk.cva.ba",
     {"version": "REDUCED", "counterparties": [
         {"id": "C1", "sector": "financials", "quality": "IG", "netting_sets": [{"ead": 1000000, "m": 5, "imm": False}]}]}),
    ("cva_k-0002", "K-8g", "risk.cva.ba",
     {"version": "REDUCED", "counterparties": [
         {"id": "C1", "sector": "financials", "quality": "IG", "netting_sets": [{"ead": 1000000, "m": 5, "imm": False}]},
         {"id": "C2", "sector": "sovereign", "quality": "HY_NR", "netting_sets": [
             {"ead": 500000, "m": 1, "imm": False}, {"ead": 2000000, "m": 10, "imm": False}]}]}),
    ("cva_k-0003", "K-8g", "risk.cva.ba",
     {"version": "REDUCED", "counterparties": [
         {"id": "C1", "sector": "basic_materials_energy_industrials", "quality": "IG",
          "netting_sets": [{"ead": 1000000, "m": 2.5, "imm": True}]}]}),
    ("cva_k-0004", "K-8g", "risk.cva.ba",
     {"version": "FULL", "counterparties": [
         {"id": "C1", "sector": "financials", "quality": "IG", "netting_sets": [{"ead": 1000000, "m": 5, "imm": False}]}],
      "single_name_hedges": [{"counterparty": "C1", "relation": "DIRECT", "sector": "financials", "quality": "IG", "m": 5, "notional": 500000}],
      "index_hedges": []}),
    ("cva_k-0005", "K-8g", "risk.cva.ba",
     {"version": "FULL", "counterparties": [
         {"id": "C1", "sector": "financials", "quality": "IG", "netting_sets": [{"ead": 1000000, "m": 5, "imm": False}]},
         {"id": "C2", "sector": "sovereign", "quality": "HY_NR", "netting_sets": [
             {"ead": 500000, "m": 1, "imm": False}, {"ead": 2000000, "m": 10, "imm": False}]}],
      "single_name_hedges": [],
      "index_hedges": [{"m": 5, "notional": 1000000, "constituents": [{"sector": "financials", "quality": "IG", "weight": 1}]}]}),
    ("cva_k-0006", "K-8g", "risk.cva.ba",
     {"version": "FULL", "counterparties": [
         {"id": "C1", "sector": "financials", "quality": "IG", "netting_sets": [{"ead": 1000000, "m": 5, "imm": False}]}],
      "single_name_hedges": [{"counterparty": "C1", "relation": "SECTOR_REGION", "sector": "financials", "quality": "IG", "m": 5, "notional": 500000}],
      "index_hedges": []}),
]

_IR_USD = [{"bucket": "USD", "factor": "1Y", "s_cva": 1000000, "s_hdg": 0},
           {"bucket": "USD", "factor": "5Y", "s_cva": -2000000, "s_hdg": 0}]
_FX = [{"bucket": "EUR", "factor": "EUR", "s_cva": 200000, "s_hdg": 0},
       {"bucket": "JPY", "factor": "JPY", "s_cva": -100000, "s_hdg": 0}]

CASES += [
    ("sacva_k-0001", "K-8g", "risk.cva.sa", {"m_cva": 1, "reporting_currency": "USD", "classes": {"IR.DELTA": _IR_USD}}),
    ("sacva_k-0002", "K-8g", "risk.cva.sa", {"m_cva": 1, "reporting_currency": "USD", "classes": {"IR.DELTA": [
        {"bucket": "USD", "factor": "1Y", "s_cva": 1000000, "s_hdg": 0},
        {"bucket": "USD", "factor": "5Y", "s_cva": -2000000, "s_hdg": -1500000}]}}),
    ("sacva_k-0003", "K-8g", "risk.cva.sa", {"m_cva": 1, "reporting_currency": "USD", "classes": {"IR.DELTA": _IR_USD + [
        {"bucket": "EUR", "factor": "10Y", "s_cva": 3000000, "s_hdg": 0}]}}),
    ("sacva_k-0004", "K-8g", "risk.cva.sa", {"m_cva": 1, "reporting_currency": "USD", "classes": {"IR.DELTA": [
        {"bucket": "USD", "factor": "1Y", "s_cva": 1000000, "s_hdg": 0},
        {"bucket": "USD", "factor": "30Y", "s_cva": 1000000, "s_hdg": 0},
        {"bucket": "EUR", "factor": "10Y", "s_cva": 3000000, "s_hdg": 0}]}}),
    ("sacva_k-0005", "K-8g", "risk.cva.sa", {"m_cva": 1, "reporting_currency": "USD", "classes": {"CCS.DELTA": [
        {"bucket": "2", "factor": {"name": "X", "tenor": "1Y", "quality": "IG", "legal_group": "GX"}, "s_cva": 100000, "s_hdg": 0},
        {"bucket": "2", "factor": {"name": "X", "tenor": "5Y", "quality": "IG", "legal_group": "GX"}, "s_cva": 100000, "s_hdg": 0},
        {"bucket": "2", "factor": {"name": "Y", "tenor": "5Y", "quality": "IG", "legal_group": "GX"}, "s_cva": 0, "s_hdg": 80000}]}}),
    ("sacva_k-0006", "K-8g", "risk.cva.sa", {"m_cva": 1.25, "reporting_currency": "USD", "classes": {"IR.DELTA": _IR_USD}}),
    ("sacva_k-0007", "K-8g", "risk.cva.sa", {"m_cva": 1, "reporting_currency": "USD", "classes": {"FX.DELTA": _FX}}),
    ("sacva_k-0008", "K-8g", "risk.cva.sa", {"m_cva": 1, "reporting_currency": "USD", "classes": {
        "IR.DELTA": _IR_USD, "FX.DELTA": _FX,
        "IR.VEGA": [{"bucket": "USD", "factor": "IR_VOL", "s_cva": 1000, "s_hdg": 0}]}}),
]

# ---- K-8i ------------------------------------------------------------------------------------------------
_LEV10 = {"on_balance": [500],
          "derivatives": [{"v": 60, "cvm_received": 0, "cvm_provided": 0, "pfe": 347}],
          "written_credit_derivatives": [],
          "sfts": [{"gross_assets": 150, "mna": True, "exposures": [100, 50], "collateral": [80, 90]}],
          "off_balance": [{"notional": 1000, "ccf_category": "COMMITMENT"},
                          {"notional": 500, "ccf_category": "UNCONDITIONALLY_CANCELLABLE"},
                          {"notional": 200, "ccf_category": "NIF_RUF"}]}


def _lev(tier1, **parts):
    d = {"tier1": tier1, "on_balance": [], "derivatives": [], "written_credit_derivatives": [], "sfts": [], "off_balance": []}
    d.update(parts)
    return d


def _lex(tier1, cps, bb=(), obs=(), crm=(), tb=(), bank_gsib=False):
    return {"tier1": tier1, "bank_gsib": bank_gsib, "counterparties": list(cps), "banking_book": list(bb),
            "off_balance": list(obs), "crm": list(crm), "trading_book": list(tb)}


CASES += [
    ("lev_k-0006", "K-8i", "risk.capital.leverage", _lev(100, off_balance=_LEV10["off_balance"])),
    ("lev_k-0007", "K-8i", "risk.capital.leverage", _lev(100, sfts=[
        {"gross_assets": 150, "mna": True, "exposures": [100, 50], "collateral": [80, 90]}])),
    ("lev_k-0008", "K-8i", "risk.capital.leverage", _lev(100, sfts=[
        {"gross_assets": 150, "mna": False, "exposures": [100, 50], "collateral": [80, 90]}])),
    ("lev_k-0009", "K-8i", "risk.capital.leverage", _lev(100, derivatives=[
        {"v": 100, "cvm_received": 30, "cvm_provided": 0, "pfe": 50}])),
    ("lev_k-0010", "K-8i", "risk.capital.leverage", _lev(60, **_LEV10)),
    ("lev_k-0011", "K-8i", "risk.capital.leverage", _lev(30, **_LEV10)),
    ("lex_k-0001", "K-8i", "risk.capital.large_exposures", _lex(1000, [{"id": c} for c in "ABCD"], bb=[
        {"counterparty": "A", "value": 260}, {"counterparty": "B", "value": 100},
        {"counterparty": "C", "value": 250}, {"counterparty": "D", "value": 99.99}])),
    ("lex_k-0002", "K-8i", "risk.capital.large_exposures", _lex(1000, [{"id": "A1", "group": "G"}, {"id": "A2", "group": "G"}], bb=[
        {"counterparty": "A1", "value": 150}, {"counterparty": "A2", "value": 120}])),
    ("lex_k-0003", "K-8i", "risk.capital.large_exposures", _lex(1000, [{"id": "E"}, {"id": "F"}], bb=[
        {"counterparty": "E", "value": 300}, {"counterparty": "F", "value": 200}],
        crm=[{"counterparty": "E", "provider": "F", "protected": 100}])),
    ("lex_k-0004", "K-8i", "risk.capital.large_exposures", _lex(1000, [{"id": "G"}], bb=[{"counterparty": "G", "value": 200}], tb=[
        {"id": "bond", "counterparty": "G", "seniority": "SENIOR", "notional": 100, "market_value": 90, "maturity_years": 5},
        {"id": "stock", "counterparty": "G", "seniority": "EQUITY", "notional": -30, "market_value": -30, "maturity_years": 1, "cash_equity": True}])),
    ("lex_k-0005", "K-8i", "risk.capital.large_exposures", _lex(1000, [{"id": "H"}], tb=[
        {"id": "long", "counterparty": "H", "seniority": "SENIOR", "notional": 50, "market_value": 50, "maturity_years": 5},
        {"id": "short", "counterparty": "H", "seniority": "SENIOR", "notional": -80, "market_value": -80, "maturity_years": 5}])),
    ("lex_k-0006", "K-8i", "risk.capital.large_exposures", _lex(1000, [{"id": "O"}], obs=[
        {"counterparty": "O", "notional": 1000, "ccf": 0}])),
    ("lex_k-0007", "K-8i", "risk.capital.large_exposures", _lex(1000, [{"id": "K", "gsib": True}], bb=[
        {"counterparty": "K", "value": 160}], bank_gsib=True)),
]

INPUT_CHOICES = {
    "drc_k-0001..0011": "bucket CORPORATE where the spec names none (drc_k-0009 names SOVEREIGN for S); position ids p1, p2, stock, bond, sold_put",
    "drc_k-0005, 0006": "X and Y in the same bucket (CORPORATE): required for the printed hbr 0.5",
    "drc_k-0007, 0008, 0011": "cash equity written as notional = market value (KR-51), seniority EQUITY, cash_equity true",
    "ctp_k-0002": "series S1 and tranche T1 for both indices (the spec names only the index)",
    "cap_k-0001": "the spec gives only imcc/ses/exceptions; drc 0, one GREEN desk SA 200, c_u 0, sa_all 1000 added so the operation is complete; only m_c and C_A are compared",
    "rfet_k-0004": "rfet_k-0002 dates k = 0..22, each listed twice (adjacent)",
    "sacva_k-0003, 0004": "the EUR bucket is IR delta EUR 10Y s_cva 3,000,000 (WS 22,200, the printed K = S = 22,200)",
    "sacva_k-0005": "names X, Y in legal group GX; bucket 2 (financials)",
    "sacva_k-0008": "IR vega factor named IR_VOL, bucket USD",
    "lev_k-0006..0009": "tier1 100 (not stated; only the named part is compared)",
    "lex_k-0002..0007": "tier1 1000 where not stated; bank_gsib false except lex_k-0007",
    "lex_k-0004, 0005": "maturity_years given (5 for bonds, 1 for the stock) although LEX ignores maturity",
}


def by_item():
    out = {}
    for cid, item, op, inp in CASES:
        out.setdefault(item, []).append({"case_id": cid, "operation": op, "inputs": inp})
    return out


assert len(CASES) == 58 and len({c[0] for c in CASES}) == 58
