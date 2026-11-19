"""Full inputs of the K-8h hand value cases (specifications/06-risk/simm-placeholder.md, section "Hand cases").

Read by simm_make_packet.py (packet side) and simm_ref.py / simm_expected.json (hidden side). Inputs only; no
expected value is written here. Calculation currency USD throughout unless a case says otherwise.
"""


def ir(q, tenor, amt, pc="RatesFX", tid=None):
    r = {"product_class": pc, "risk_type": "IR_DELTA", "qualifier": q, "label1": tenor, "amount": amt}
    return r | ({"trade_id": tid} if tid else {})


def irv(q, expiry, amt, pc="RatesFX"):
    return {"product_class": pc, "risk_type": "IR_VEGA", "qualifier": q, "label1": expiry, "amount": amt}


def fx(q, amt, pc="RatesFX"):
    return {"product_class": pc, "risk_type": "FX_DELTA", "qualifier": q, "amount": amt}


def eq(q, bucket, amt, pc="Equity", tid=None):
    r = {"product_class": pc, "risk_type": "EQ_DELTA", "qualifier": q, "bucket": bucket, "amount": amt}
    return r | ({"trade_id": tid} if tid else {})


def eqv(q, bucket, expiry, amt, pc="Equity"):
    return {"product_class": pc, "risk_type": "EQ_VEGA", "qualifier": q, "bucket": bucket, "label1": expiry, "amount": amt}


def case(*records, ccy="USD"):
    return {"calculation_currency": ccy, "records": list(records)}


CASES = [
    ("simm_k-0001", case(ir("USD", "5Y", 2))),
    ("simm_k-0002", case(ir("USD", "1Y", 3), ir("USD", "10Y", -1))),
    ("simm_k-0003", case(ir("USD", "5Y", 5, tid="T1"), ir("USD", "5Y", -3, tid="T2"))),
    ("simm_k-0004", case(ir("USD", "5Y", 2), ir("EUR", "1Y", 4))),
    ("simm_k-0005", case(ir("USD", "1Y", 1), ir("USD", "10Y", 1), ir("EUR", "5Y", 2))),
    ("simm_k-0006", case(ir("USD", "1Y", -1), ir("USD", "10Y", -1), ir("EUR", "5Y", 2))),
    ("simm_k-0007", case(ir("USD", "1Y", 300), ir("USD", "5Y", 100))),
    ("simm_k-0008", case(ir("USD", "5Y", 400), ir("EUR", "5Y", 900))),
    ("simm_k-0009", case(fx("EUR", 200), fx("JPY", -100))),
    ("simm_k-0010", case(fx("EUR", 4000), fx("JPY", 9000))),
    ("simm_k-0011", case(ir("USD", "5Y", 2), fx("EUR", 200))),
    ("simm_k-0012", case(eq("A", "1", 3), eq("B", "1", -2))),
    ("simm_k-0013", case(eq("A", "2", 400), eq("B", "2", 100))),
    ("simm_k-0014", case(eq("A", "2", 300, tid="T1"), eq("A", "2", -100, tid="T2"))),
    ("simm_k-0015", case(eq("A", "1", 5), eq("C", "3", -2))),
    ("simm_k-0016", case(eq("A", "1", 5), eq("R1", "RESIDUAL", 2), eq("R2", "RESIDUAL", -1))),
    ("simm_k-0017", case(eq("R1", "RESIDUAL", 3))),
    ("simm_k-0018", case(irv("USD", "1Y", 50))),
    ("simm_k-0019", case(irv("USD", "1W", 20), irv("USD", "1Y", -730))),
    ("simm_k-0020", case(irv("USD", "1W", -40))),
    ("simm_k-0021", case(irv("EUR", "5Y", 4000))),
    ("simm_k-0022", case(eqv("A", "1", "1W", 40), eqv("A", "1", "1Y", 365), eqv("R", "RESIDUAL", "1W", 20))),
    ("simm_k-0023", case(ir("USD", "5Y", 2), irv("USD", "1Y", 50))),
    ("simm_k-0024", case(ir("USD", "5Y", 2), eq("A", "1", 5))),
    ("simm_k-0025", case(ir("USD", "5Y", 2), ir("USD", "5Y", -2, pc="Equity"))),
    ("simm_k-0026", case(eq("A", "1", 5), fx("EUR", 200, pc="Equity"), ir("USD", "5Y", 2, pc="Equity"))),
    ("simm_k-0027", case(ir("USD", "5Y", 2, tid="T1"), ir("USD", "5Y", -2, tid="T2"))),
    ("simm_k-0028", case()),
    ("simm_k-0029", case(fx("USD", 500), ccy="EUR")),
]
