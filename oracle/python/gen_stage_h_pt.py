"""Stage H paper trading goldens (pt_h) and their non-finite cases (e1_hpt).

Spec: specifications/10-execution/paper-trading.md, table "Golden cases" and "Golden output shapes"; CLI shapes in
specifications/cli-contract.md, "Stage H paper trading operations". The spec table is prose, so each row is
transcribed here by hand: inputs as the row states them, expected values exactly as the row's Expected column gives
them, written as HR-12 decimal strings ("-0.60" becomes "-0.6"). No value is taken from an implementation.
Every output also carries the HR-43 label.

Blind record program/STAGE_H_BLIND_WAVE2B.md: pt_h-0001..0006, 0010..0018, 0020 SHAPE-ONLY (values identical,
shapes invented by the blind lane and then adopted by the spec); 0021..0023 NOT BLIND. pt_h-0018 (live mode,
E_UNSUPPORTED_OPERATION) is checked against the blind value but left out of the file: the conformance runner reads
that code as "not implemented", so each build pins it in its own unit tests (acceptance test A5). The comparison below also
asserts that the blind lane's frozen values (stage_h_blind/wave2b/blind_results.json) agree on every quantity the
spec states.

pt_h-0030 and later are new in this lane (paper.session.run and errors): hand-derived, not blind. Their hashes
are recomputed here with hashlib from the HR-45 canonical bytes, built by this file from the spec's rule
(json.dumps with sorted keys, separators "," and ":", ASCII), not by quantforge_core.

    cd oracle/python && uv run python -W ignore gen_stage_h_pt.py
"""
import hashlib
import json
from decimal import Decimal

from qf_oracle import common
from qf_oracle.common import Suite

G = "oracle/python/gen_stage_h_pt.py"
SPEC = "specifications/10-execution/paper-trading.md"
LABEL = "crypto venue; simulated"
CEILING = "Paper trading on free data; simulated fills; no evidence of tradable profitability."
Z64 = "0" * 64
SHAPE = "blind-rederivation (DR-H2, program/STAGE_H_BLIND_WAVE2B.md): SHAPE-ONLY, values identical"
NOT_BLIND = "not blind: the input names the corruption (program/STAGE_H_BLIND_WAVE2B.md)"
CLS = "date_and_convention"
LSTAR = {"max_order_qty": "10", "max_notional": "1000", "max_abs_position": "5", "price_band": "0.05",
         "max_orders_per_day": 3, "kill_switch": False, "allow_short": True}
TS = "2026-11-18T00:00:01Z"
ORDER_BODY = {"order_id": "O1", "symbol": "BTC-USD", "side": "BUY", "type": "LIMIT", "quantity": "3",
              "limit_price": "101"}


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def rec(seq, ts, kind, body, prev, label=True):
    r = {"seq": seq, "ts": ts, "kind": kind, "body": body, "prev": prev}
    if label:
        r["label"] = LABEL
    r["hash"] = hashlib.sha256(canon(r).encode("ascii")).hexdigest()
    return r


def chain(items):
    out, prev = [], Z64
    for seq, (ts, kind, body) in enumerate(items):
        out.append(rec(seq, ts, kind, body, prev))
        prev = out[-1]["hash"]
    return out


def text(records):
    return "".join(canon(r) + "\n" for r in records)


def L(**kw):
    return {"label": LABEL, **kw}


def day(market, trading, fees, financing, interest, borrow, total, position, cash_close, nav_open=None,
        nav_close=None):
    out = L(market=market, trading=trading, fees=fees, financing=financing, cash_interest=interest,
            short_borrow=borrow, total=total, position=position, cash_close=cash_close)
    if nav_open is not None:
        out.update(nav_open=nav_open, nav_close=nav_close)
    return out


def pre(order, **kw):
    base = {"order": order, "ref_price": "100", "position": "0", "cash": "10000", "orders_today": 0,
            "limits": dict(LSTAR)}
    base.update(kw)
    return base


def O(side, qty, typ, limit=None, **kw):
    o = {"side": side, "type": typ, "quantity": qty, **kw}
    if limit is not None:
        o["limit_price"] = limit
    return o


F1 = [{"side": "BUY", "quantity": "2", "price": "100", "fee": "0.20"},
      {"side": "SELL", "quantity": "1", "price": "110", "fee": "0.11"}]


def spec_cases():
    """(case id, op, inputs, expected outputs or error code) for the spec table rows."""
    r0 = rec(0, TS, "ORDER", dict(ORDER_BODY), Z64)
    bytes0 = canon({k: v for k, v in r0.items() if k != "hash"})
    t21 = json.loads(json.dumps(r0))
    t21["body"]["limit_price"] = "102"
    r1 = rec(1, "2026-11-18T00:00:02Z", "ORDER", dict(ORDER_BODY, order_id="O2"), Z64)
    nl = rec(0, TS, "ORDER", dict(ORDER_BODY), Z64, label=False)
    pay = lambda ok, n, bad, reason, head=None: L(ok=ok, records=n, first_bad_seq=bad, reason=reason, head=head)
    a = "paper.book.apply_fill"
    d = "paper.book.end_of_day"
    p = "paper.pretrade.check"
    return [
        ("pt_h-0001", a, {"cash": "10000", "fills": F1},
         L(position="1", avg_cost="100", realised="10", fees="0.31", cash="9909.69")),
        ("pt_h-0002", d, {"cash_open": "10000", "fills": F1, "close": "105", "days": 1},
         day("0", "15", "-0.31", "0", "0", "0", "14.69", "1", "9909.69", "10000", "10014.69")),
        ("pt_h-0003", d, {"cash_open": "9909.69", "position_open": "1", "avg_cost_open": "100", "prev_close": "105",
                          "close": "102", "days": 1, "cash_rate": "0.0365"},
         day("-3", "0", "0", "0.99", "0.99", "0", "-2.01", "1", "9910.68", "10014.69", "10012.68")),
        ("pt_h-0004", d, {"cash_open": "10100", "position_open": "-2", "prev_close": "50", "close": "50", "days": 1,
                          "cash_rate": "0.0365", "borrow_rate": "0.0730"},
         day("0", "0", "0", "0.99", "1.01", "-0.02", "0.99", "-2", "10100.99", "10000", "10000.99")),
        ("pt_h-0005", a, {"position": "1", "avg_cost": "100",
                          "fills": [{"side": "SELL", "quantity": "3", "price": "90", "fee": "0"}]},
         L(position="-2", avg_cost="90", realised="-10", fees="0", cash_delta="270")),
        ("pt_h-0006", d, {"cash_open": "-1000", "days": 3, "debit_rate": "0.0730"},
         day("0", "0", "0", "-0.6", "-0.6", "0", "-0.6", "0", "-1000.6")),
        ("pt_h-0010", p, pre(O("BUY", "3", "LIMIT", "101")), L(accepted=True, reasons=[])),
        ("pt_h-0011", p, pre(O("BUY", "11", "LIMIT", "100")),
         L(accepted=False, reasons=["MAX_QTY", "MAX_NOTIONAL", "MAX_POSITION"])),
        ("pt_h-0012", p, pre(O("BUY", "3", "LIMIT", "106")), L(accepted=False, reasons=["PRICE_BAND"])),
        ("pt_h-0013", p, pre(O("SELL", "10", "LIMIT", "100"), position="4"),
         L(accepted=False, reasons=["MAX_POSITION"])),
        ("pt_h-0014", p, pre(O("BUY", "3", "MARKET"), cash="300"), L(accepted=False, reasons=["INSUFFICIENT_CASH"])),
        ("pt_h-0015", p, pre(O("BUY", "3", "LIMIT", "101"), orders_today=3), L(accepted=False, reasons=["MAX_ORDERS"])),
        ("pt_h-0016", p, pre(O("BUY", "3", "LIMIT", "101"), limits=dict(LSTAR, kill_switch=True)),
         L(accepted=False, reasons=["KILL_SWITCH"])),
        ("pt_h-0017", p, pre(O("SELL", "2", "LIMIT", "100"), position="1", limits=dict(LSTAR, allow_short=False)),
         L(accepted=False, reasons=["NO_SHORT"])),
        ("pt_h-0018", p, pre(O("BUY", "3", "LIMIT", "101", mode="live")), "E_UNSUPPORTED_OPERATION"),
        ("pt_h-0020", "paper.ledger.append",
         {"seq": 0, "ts": TS, "kind": "ORDER", "body": dict(ORDER_BODY), "prev": Z64},
         L(canonical_bytes=bytes0, hash=r0["hash"], record=r0)),
        ("pt_h-0021", "paper.ledger.verify", {"text": text([t21])}, {"verify": pay(False, 0, 0, "HASH")}),
        ("pt_h-0022", "paper.ledger.verify", {"text": text([r0, r1])}, {"verify": pay(False, 1, 1, "LINK")}),
        ("pt_h-0023", "paper.ledger.verify", {"text": text([nl])}, {"verify": pay(False, 0, 0, "LABEL")}),
    ]


def blind_agrees(cases):
    """Every spec-stated quantity equals the blind lane's frozen value (decimal-normalised)."""
    blind = json.loads((common.ROOT / "stage_h_blind/wave2b/blind_results.json").read_text(encoding="utf-8"))
    blind = blind.get("results", blind)

    def same(x, y):
        if isinstance(x, str) and isinstance(y, str):
            try:
                return Decimal(x) == Decimal(y)
            except ArithmeticError:
                return x == y
        return x == y

    for cid, _, _, exp in cases:
        b = blind[cid]
        if isinstance(exp, str):
            assert b == {"error": exp}, cid
            continue
        if "verify" in exp:
            exp, b = exp["verify"], b["verify"]
        for k, v in exp.items():
            if k in ("label", "head", "records") or k not in b:
                continue  # label is not a stated quantity; records/head: blind used its own count
            assert same(v, b[k]), (cid, k, v, b[k])
    assert blind["pt_h-0020"]["hash"] == "72c85984abb1b7c4072c65dbba0567b3de51279645b0ad63cfd242137aed7e81"


# ------------------------------------------------------------------ session (hand-derived, not blind)

LIT = {"tick_size": "0.5", "lot_size": "1", "fee_schedule": {"maker_rebate": "0", "taker_fee": "0.001"}}
SNAP = {"bids": [["99.5", "4"]], "asks": [["100.5", "2"], ["101", "5"]]}
T1, T2, T3 = "2026-11-18T00:00:01Z", "2026-11-18T00:00:02Z", "2026-11-19T00:00:00Z"
OS1 = {"order_id": "O1", "symbol": "BTC-USD", "side": "BUY", "type": "LIMIT", "quantity": "3",
       "limit_price": "101", "venue": "LIT"}
OS2 = dict(OS1, order_id="O2", limit_price="106")


def fstr(x):
    """HR-12 decimal string of a binary64 via its shortest round-trip repr (the TCA record rule)."""
    d = Decimal(repr(x))
    return "0" if d == 0 else format(d.normalize(), "f")


def session_cases():
    """Mid 100. O1 BUY LIMIT 3 @ 101 walks the asks: 2 @ 100.5 (fee 0.001 x 201 = 0.201) and 1 @ 101 (0.101);
    pre-trade passes (303 <= 1000, band 0.01, |n| 3 <= 5, cash). O2 BUY LIMIT 3 @ 106 next: band 6/100 > 0.05 and
    |3 + 3| = 6 > 5, so REJECT [PRICE_BAND, MAX_POSITION]. Cash 10000 - 201.201 - 101.101 = 9697.698, position 3."""
    items = [
        (T1, "ORDER", dict(OS1, decision_price="100")),
        (T1, "FILL", {"order_id": "O1", "child_id": "O1", "venue": "LIT", "symbol": "BTC-USD", "side": "BUY",
                      "quantity": "2", "price": "100.5", "fee": "0.201"}),
        (T1, "FILL", {"order_id": "O1", "child_id": "O1", "venue": "LIT", "symbol": "BTC-USD", "side": "BUY",
                      "quantity": "1", "price": "101", "fee": "0.101"}),
        (T2, "REJECT", dict(OS2, reasons=["PRICE_BAND", "MAX_POSITION"])),
    ]
    script = [{"op": "SUBMIT", "ts": T1, "order": OS1, "snapshot": SNAP},
              {"op": "SUBMIT", "ts": T2, "order": OS2, "snapshot": SNAP}]
    results = [{"status": "DONE", "filled": "3"}, {"status": "REJECTED", "reasons": ["PRICE_BAND", "MAX_POSITION"]}]
    base = {"cash": "10000", "limits": dict(LSTAR), "lit": LIT}
    recs = chain(items)
    c30 = (dict(base, script=script),
           {"results": results, "records": recs, "head": recs[-1]["hash"], "positions": {"BTC-USD": "3"},
            "cash": "9697.698", "label": LABEL, "ceiling": CEILING})
    # Close at 102, first day, rates 0. TCA for O1 (tca.md, binary64 in this order): decision = arrival = 100,
    # end 102; delay 3 x 0 = 0; execution 2 x 0.5 + 1 x 1 = 2; opportunity 0; fees 0.302; total 2.302;
    # total_bps = total / (3 x 100) x 1e4. Explain: trading 2 x 1.5 + 1 x 1 = 4, fees -0.302, total 3.698,
    # NAV 9697.698 + 3 x 102 = 10003.698 (= 10000 + 3.698, HR-53).
    s, filled, fees = 1.0, 3.0, float(Decimal("0.302"))
    delay = s * filled * (100.0 - 100.0)
    execution = s * sum((q * (p - 100.0) for q, p in ((2.0, 100.5), (1.0, 101.0))), 0.0)
    opportunity = s * (3.0 - filled) * (102.0 - 100.0) + 0.0
    total = delay + execution + opportunity + fees
    tca = {"order_id": "O1", "delay": fstr(delay), "execution": fstr(execution), "opportunity": fstr(opportunity),
           "total": fstr(total), "total_bps": fstr(total / (3.0 * 100.0) * 1e4)}
    eod = {"market": "0", "trading": "4", "fees": "-0.302", "financing": "0", "interest": "0", "borrow": "0",
           "total": "3.698", "nav": "10003.698", "label": LABEL, "ceiling": CEILING}
    recs31 = chain(items + [(T3, "TCA", tca), (T3, "EOD", eod)])
    close = {"op": "CLOSE", "ts": T3, "prev_marks": {}, "marks": {"BTC-USD": "102"}, "days": 1}
    c31 = (dict(base, script=script + [close]),
           {"results": results + [{"status": "CLOSED", "eod": eod}], "records": recs31, "head": recs31[-1]["hash"],
            "positions": {"BTC-USD": "3"}, "cash": "9697.698", "label": LABEL, "ceiling": CEILING})
    return c30, c31


def build():
    s = Suite("pt_h", SPEC, G)
    cases = spec_cases()
    blind_agrees(cases)
    for cid, op, inp, exp in cases:
        if exp == "E_UNSUPPORTED_OPERATION":
            continue  # the runner reads that code as "not implemented"; A5 unit tests in every build cover live mode
        verified = ["hand", NOT_BLIND] if cid >= "pt_h-0021" else ["hand", SHAPE]
        kw = {"error": exp} if isinstance(exp, str) else {"outputs": exp.get("verify", exp)}
        s.add(op, inp, cls=CLS, verified=verified, tags=["stage_h", "simulated", "paper"],
              description=f"{cid} from the spec table" + ("; not blind" if cid >= "pt_h-0021" else ""), **kw)
        s.cases[-1]["case_id"] = cid
    c30, c31 = session_cases()
    for k, (inp, out, desc) in enumerate((
            (*c30, "session: one LIT order filled across two levels, one rejected; ledger hashes recomputed"),
            (*c31, "session c30 then the daily close: TCA and EOD records, HR-53 identity"))):
        s.add("paper.session.run", inp, out, cls=CLS, verified=["hand", "outside: hashlib sha256 of the canonical bytes"],
              tags=["stage_h", "simulated", "paper", "session"], description=f"hand, not blind: {desc}")
        s.cases[-1]["case_id"] = f"pt_h-{30 + k:04d}"
    errs = [
        ("paper.pretrade.check", pre(O("HOLD", "3", "LIMIT", "101")), "E_INPUT", "unknown side"),
        ("paper.pretrade.check", pre(O("BUY", "0", "LIMIT", "101")), "E_DOMAIN", "quantity 0"),
        ("paper.pretrade.check", pre(O("BUY", "3", "LIMIT")), "E_SCHEMA", "limit_price missing on a LIMIT order"),
        ("paper.pretrade.check", pre(O("BUY", 3, "LIMIT", "101")), "E_SCHEMA", "quantity as a JSON number (HR-44)"),
        ("paper.book.apply_fill", {"cash": "10000", "fills": [dict(F1[0], price="-1")]}, "E_DOMAIN",
         "negative price"),
        ("paper.book.end_of_day", {"cash_open": "100", "position_open": "1", "close": "100"}, "E_SCHEMA",
         "open position without prev_close"),
        ("paper.ledger.append", {"seq": 0, "ts": TS, "kind": "TRADE", "body": {}}, "E_INPUT", "unknown kind"),
        ("paper.session.run", {"cash": "10000", "limits": dict(LSTAR), "lit": LIT,
                               "script": [{"op": "SUBMIT", "ts": T1, "order": dict(OS1, venue="NYSE"),
                                           "snapshot": SNAP}]}, "E_INPUT", "unknown venue"),
    ]
    for k, (op, inp, code, desc) in enumerate(errs):
        s.add(op, inp, error=code, cls=CLS, verified=["hand"], tags=["stage_h", "paper", "error"],
              description=f"hand: {desc}")
        s.cases[-1]["case_id"] = f"pt_h-{40 + k:04d}"
    return s


def e1_suite(s):
    """One non-finite decimal string per paper operation that takes a number. Unlike wave 2 (e1_h2, E_SCHEMA), a
    paper decimal that parses as NaN or Infinity is E_DOMAIN (paper.dec, F-2). paper.ledger.append and
    paper.ledger.verify take no number (a body is hashed as given) and are listed in conformance/E1_EXEMPT.json."""
    e = Suite("e1_hpt", SPEC, G)
    by = {c["operation"]: c for c in s.cases if c["expected"]["status"] == "ok"}
    plan = [
        ("paper.book.apply_fill", ("cash",), "NaN"),
        ("paper.book.end_of_day", ("close",), "Infinity"),
        ("paper.pretrade.check", ("ref_price",), "NaN"),
        ("paper.session.run", ("cash",), "-Infinity"),
    ]
    for op, path, bad in plan:
        inp = json.loads(json.dumps(by[op]["inputs"]))
        node = inp
        for k in path[:-1]:
            node = node[k]
        node[path[-1]] = bad
        e.add(op, inp, error="E_DOMAIN", cls=CLS, verified=["hand"], tags=["stage_h", "e1", "non-finite-input"],
              description=f"F-2: {bad} at {'/'.join(path)} is E_DOMAIN (from {by[op]['case_id']})")
    return e


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_h"
    s = build()
    s.write()
    e1_suite(s).write()
    common.GOLDEN = keep


if __name__ == "__main__":
    main()
