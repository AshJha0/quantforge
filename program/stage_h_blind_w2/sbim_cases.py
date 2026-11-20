"""Full inputs of the K-8h hand value cases (specifications/06-risk/sbim-placeholder.md, section "Hand cases").

CASES are the 29 cases of the blind run of 2026-11-19 (renamed from simm_k-NNNN to sbim_k-NNNN after the compare;
numbers unchanged). ADDED_CASES were added after the blind run and are NOT blind-checked; they never enter the
packet, sbim_expected.json or the blind count.

Read by sbim_make_packet.py (packet side) and sbim_ref.py / sbim_expected.json (hidden side). Inputs only; no
expected value is written here. Calculation currency USD throughout unless a case says otherwise.
"""


def ir(q, tenor, amt, pc="RATES", tid=None):
    r = {"group": pc, "risk_type": "IR_DELTA", "name": q, "tenor": tenor, "amount": amt}
    return r | ({"trade_id": tid} if tid else {})


def irv(q, expiry, amt, pc="RATES"):
    return {"group": pc, "risk_type": "IR_VEGA", "name": q, "tenor": expiry, "amount": amt}


def fx(q, amt, pc="RATES"):
    return {"group": pc, "risk_type": "FX_DELTA", "name": q, "amount": amt}


def eq(q, bucket, amt, pc="EQUITY", tid=None):
    r = {"group": pc, "risk_type": "EQ_DELTA", "name": q, "bucket": bucket, "amount": amt}
    return r | ({"trade_id": tid} if tid else {})


def eqv(q, bucket, expiry, amt, pc="EQUITY"):
    return {"group": pc, "risk_type": "EQ_VEGA", "name": q, "bucket": bucket, "tenor": expiry, "amount": amt}


def case(*records, ccy="USD"):
    return {"calculation_currency": ccy, "records": list(records)}


CASES = [
    ("sbim_k-0001", case(ir("USD", "5Y", 2))),
    ("sbim_k-0002", case(ir("USD", "1Y", 3), ir("USD", "10Y", -1))),
    ("sbim_k-0003", case(ir("USD", "5Y", 5, tid="T1"), ir("USD", "5Y", -3, tid="T2"))),
    ("sbim_k-0004", case(ir("USD", "5Y", 2), ir("EUR", "1Y", 4))),
    ("sbim_k-0005", case(ir("USD", "1Y", 1), ir("USD", "10Y", 1), ir("EUR", "5Y", 2))),
    ("sbim_k-0006", case(ir("USD", "1Y", -1), ir("USD", "10Y", -1), ir("EUR", "5Y", 2))),
    ("sbim_k-0007", case(ir("USD", "1Y", 300), ir("USD", "5Y", 100))),
    ("sbim_k-0008", case(ir("USD", "5Y", 400), ir("EUR", "5Y", 900))),
    ("sbim_k-0009", case(fx("EUR", 200), fx("JPY", -100))),
    ("sbim_k-0010", case(fx("EUR", 4000), fx("JPY", 9000))),
    ("sbim_k-0011", case(ir("USD", "5Y", 2), fx("EUR", 200))),
    ("sbim_k-0012", case(eq("A", "1", 3), eq("B", "1", -2))),
    ("sbim_k-0013", case(eq("A", "2", 400), eq("B", "2", 100))),
    ("sbim_k-0014", case(eq("A", "2", 300, tid="T1"), eq("A", "2", -100, tid="T2"))),
    ("sbim_k-0015", case(eq("A", "1", 5), eq("C", "3", -2))),
    ("sbim_k-0016", case(eq("A", "1", 5), eq("R1", "RESIDUAL", 2), eq("R2", "RESIDUAL", -1))),
    ("sbim_k-0017", case(eq("R1", "RESIDUAL", 3))),
    ("sbim_k-0018", case(irv("USD", "1Y", 50))),
    ("sbim_k-0019", case(irv("USD", "1W", 20), irv("USD", "1Y", -730))),
    ("sbim_k-0020", case(irv("USD", "1W", -40))),
    ("sbim_k-0021", case(irv("EUR", "5Y", 4000))),
    ("sbim_k-0022", case(eqv("A", "1", "1W", 40), eqv("A", "1", "1Y", 365), eqv("R", "RESIDUAL", "1W", 20))),
    ("sbim_k-0023", case(ir("USD", "5Y", 2), irv("USD", "1Y", 50))),
    ("sbim_k-0024", case(ir("USD", "5Y", 2), eq("A", "1", 5))),
    ("sbim_k-0025", case(ir("USD", "5Y", 2), ir("USD", "5Y", -2, pc="EQUITY"))),
    ("sbim_k-0026", case(eq("A", "1", 5), fx("EUR", 200, pc="EQUITY"), ir("USD", "5Y", 2, pc="EQUITY"))),
    ("sbim_k-0027", case(ir("USD", "5Y", 2, tid="T1"), ir("USD", "5Y", -2, tid="T2"))),
    ("sbim_k-0028", case()),
    ("sbim_k-0029", case(fx("USD", 500), ccy="EUR")),
]

# Added after the blind run (2026-11-19), not blind-checked: two different issuers in one equity bucket for vega
# and curvature (the gap the deriver recorded, stage_k_blind/sbim/notes.md item 6).
ADDED_CASES = [
    ("sbim_k-0030", case(eqv("A", "2", "1Y", 365), eqv("B", "2", "1W", -40))),
]
