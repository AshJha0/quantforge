"""Stage H multi-asset goldens H-22 (auc_h, eqc_h), H-23 (fxc_h, fxv_h), H-24 (rtc_h, fut_h) and their
E1 non-finite cases (e1_h4).

Specs: specifications/09-microstructure/asset-conventions.md, specifications/10-execution/auction.md,
fx-rfq-venue.md, rates-futures-venue.md; rulings specifications/stage-h-rulings-multiasset.md. The
spec tables are prose, so each row is written out here by hand from the table (inputs in the
HR-100 shapes, expected values exactly as the table states them); fields a row does not state
(auction fills and residuals for auc_h-0003..0008) are hand-derived from the auction.md algorithm.
No value is taken from an implementation. Blind record: program/STAGE_H_BLIND_MULTIASSET.md.

Rule versions (coordinator ruling 2026-11-18 after the HR-98 source check): the current Rule 612
two-tier table and the Rule 610(c) cap of $0.001 are the default; `as_of` before the compliance date
selects the old regime. eqc_h-0009..0013 add the $0.005 tier and the new cap (hand, not blind).

    cd oracle/python && uv run python -W ignore gen_stage_h_ma.py
"""
import json
from decimal import Decimal

from qf_oracle import common
from qf_oracle.common import Suite
from qf_oracle.rng import Xo

G = "oracle/python/gen_stage_h_ma.py"
CONV = "specifications/09-microstructure/asset-conventions.md"
AUC = "specifications/10-execution/auction.md"
FXV = "specifications/10-execution/fx-rfq-venue.md"
FUT = "specifications/10-execution/rates-futures-venue.md"
REC = "program/STAGE_H_BLIND_MULTIASSET.md"
BLIND = f"blind-rederivation (DR-H2, {REC}): MATCH"
REPR = {  # representation-only differences (value equal), counted as agreeing in the blind record
    "fxc_h-0001": '"100.0000" vs "100"', "fxc_h-0002": '"10000.00" vs "10000"', "rtc_h-0008": "12 dp vs 9 dp",
    "rtc_h-0010": "12 dp vs 9 dp", "rtc_h-0009": '"100.000000000000" vs "100"'}
NOT_BLIND = {
    "fut_h-0004": "answer fixed by HR-102 (spec gap)", "fut_h-0005": "answer fixed by HR-102 (spec gap)",
    "fut_h-0006": "answer fixed by HR-103 (spec gap)",
    "rtc_h-0004": "expected value changed by HR-109 (CME quarter-32nds: 7 = 3/4, was 7/8 under HR-90)", "rtc_h-0007": "15.625 printed in the spec text (soft leak)",
}
ADDED = {**{f"eqc_h-{k:04d}": "current Rule 612/610 regime" for k in range(9, 14)},
         **{f"eqc_h-{k:04d}": "round lot by price, Rule 600(b)(93)" for k in range(14, 18)},
         "fxc_h-0008": "USD-only holiday on T+1 rule", "auc_h-0009": "IEX tie-break parameter",
         "rtc_h-0011": "yield solve (HR-92)", "rtc_h-0012": "yield solve (HR-92)",
         **{f"fxv_h-{k:04d}": "last-look draw from core.rng (HR-97)" for k in (10, 11, 12)}}
VENUE_SUITES = ("auc_h", "fxv_h", "fut_h", "ses_h")
EQ = "simulated venue; not a real exchange"
FX = "simulated venue; not a real exchange; no real FX data"
RT = "simulated venue; not a real exchange; no real rates data"


RATES2 = {"rtc_h-0004": "MATCH", "rtc_h-0011": "MATCH", "rtc_h-0012": "MATCH",
          "rtc_h-0007": "MATCH by value; representation only", "fut_h-0004": "MATCH by value; representation only",
          "fut_h-0005": "MATCH by value; representation only", "fut_h-0006": "MATCH by value; representation only"}


def verified(cid):
    if cid in RATES2:  # second blind lane, HR-114 (packet 2 had the rulings and no expected values)
        return ["hand", f"blind-rederivation (DR-H2, {REC}, rates packet 2): {RATES2[cid]}"]
    if cid in NOT_BLIND:
        return ["hand"]
    if cid in REPR:
        return ["hand", f"{BLIND} by value; representation only ({REPR[cid]})"]
    if cid in ADDED:
        return ["hand"]
    return ["hand", BLIND]


def o(oid, side, limit, qty):
    return {"id": oid, "limit": limit, "qty": qty, "side": side}


def f(oid, side, qty, price):
    return {"id": oid, "price": price, "qty": qty, "side": side}


def r(oid, side, limit, qty):
    return {"id": oid, "limit": limit, "qty": qty, "side": side}


def auc_out(price, volume, imb, fills, resid, canc=()):
    return {"cancelled": list(canc), "fills": fills, "imbalance": imb, "label": EQ, "price": price,
            "residual": resid, "volume": volume}


A1 = [o("s1", "BUY", "10.02", 100), o("s2", "BUY", "10.01", 200), o("s3", "BUY", "10.00", 300),
      o("s4", "SELL", "9.99", 150), o("s5", "SELL", "10.01", 250), o("s6", "SELL", "10.03", 100)]
A1_OUT = auc_out("10.01", 300, -100,
                 [f("s1", "B", 100, "10.01"), f("s2", "B", 200, "10.01"), f("s4", "S", 150, "10.01"),
                  f("s5", "S", 150, "10.01")],
                 [r("s3", "B", "10.00", 300), r("s5", "S", "10.01", 100), r("s6", "S", "10.03", 100)])
A3 = [{"limit": "10.02", "qty": 100, "side": "BUY"}, {"limit": "10.00", "qty": 100, "side": "SELL"}]


def a3(price):
    return auc_out(price, 100, 0, [f("b1", "B", 100, price), f("a1", "S", 100, price)], [])


def auc(orders, ref="10.00"):
    return {"orders": orders, "phase": "OPEN", "ref_price": ref, "tick_size": "0.01"}


AUC_ROWS = [
    ("auc_h-0001", auc(A1), A1_OUT),
    ("auc_h-0002", auc(A1), A1_OUT),
    ("auc_h-0003", auc(A3, "10.01"), a3("10.01")),
    ("auc_h-0004", auc(A3, "10.05"), a3("10.02")),
    ("auc_h-0005", auc(A3, "10.005"), a3("10.01")),
    ("auc_h-0006", auc([{"limit": "10.02", "qty": 200, "side": "BUY"}, {"limit": "10.00", "qty": 100, "side": "SELL"},
                        {"limit": "10.01", "qty": 50, "side": "SELL"}]),
     auc_out("10.02", 150, 50, [f("b1", "B", 150, "10.02"), f("a1", "S", 100, "10.02"), f("a2", "S", 50, "10.02")],
             [], ["b1"][:0] + [])),
    ("auc_h-0007", auc([{"limit": "MARKET", "qty": 100, "side": "BUY"}, {"limit": "MARKET", "qty": 100, "side": "SELL"}]),
     auc_out(None, 0, 0, [], [], ["b1", "a1"])),
    ("auc_h-0008", auc([{"limit": "10.00", "qty": 100, "side": "BUY"}, {"limit": "10.01", "qty": 100, "side": "BUY"}]),
     auc_out(None, 0, 0, [], [r("b2", "B", "10.01", 100), r("b1", "B", "10.00", 100)])),
]
# auc_h-0006: b1 buys 200, 150 fill, the 50 left is a limit order and rests.
AUC_ROWS[5][2]["residual"] = [r("b1", "B", "10.02", 50)]
# IEX tie-break (venue parameter, source check retry 2026-11-18): nearest the reference midpoint. Hand.
AUC_ROWS.append(("auc_h-0009", dict(AUC_ROWS[5][1], tie_break="IEX"),
                 auc_out("10.01", 150, 50, [f("b1", "B", 150, "10.01"), f("a1", "S", 100, "10.01"),
                                            f("a2", "S", 50, "10.01")], [r("b1", "B", "10.02", 50)])))


def rp(price, side, **kw):
    return ("micro.eq.round_price", dict({"price": price, "side": side}, **kw))


EQC_ROWS = [
    ("eqc_h-0001", *rp("10.005", "BUY"), {"price": "10.00"}),
    ("eqc_h-0002", *rp("10.005", "SELL"), {"price": "10.01"}),
    ("eqc_h-0003", *rp("0.12345", "BUY"), {"price": "0.1234"}),
    ("eqc_h-0004", *rp("0.12345", "SELL"), {"price": "0.1235"}),
    ("eqc_h-0005", *rp("0.99995", "SELL"), {"price": "1.00"}),
    ("eqc_h-0006", *rp("25.00", "BUY"), {"price": "25.00"}),
    ("eqc_h-0007", "micro.eq.fee_check", {"cap_check": True, "price": "20", "taker_fee": "0.0031"}, "E_DOMAIN"),
    ("eqc_h-0008", "micro.eq.settle_date", {"holidays": [], "settle_lag": 1, "trade_date": "2026-11-20"},
     {"settle_date": "2026-11-23"}),
    # Added 2026-11-18 (source check): current Rule 612 $0.005 tier and Rule 610(c) $0.001 cap. Hand.
    ("eqc_h-0009", *rp("10.003", "BUY", tick_tier="HALF_PENNY"), {"price": "10.000"}),
    ("eqc_h-0010", *rp("10.003", "SELL", tick_tier="HALF_PENNY"), {"price": "10.005"}),
    ("eqc_h-0011", "micro.eq.fee_check", {"price": "20", "taker_fee": "0.0015"}, "E_DOMAIN"),
    ("eqc_h-0012", "micro.eq.fee_check", {"as_of": "2024-01-02", "price": "20", "taker_fee": "0.0015"},
     {"cap": "0.003", "taker_fee": "0.0015"}),
    ("eqc_h-0013", "micro.eq.fee_check", {"price": "0.50", "taker_fee": "0.0005"},
     {"cap": "0.0005", "taker_fee": "0.0005"}),
    # Round lots, amended Reg NMS 242.600(b)(93) (source check retry 2026-11-18). Hand.
    ("eqc_h-0014", "micro.eq.round_lot", {"price": "250.00"}, {"round_lot": 100}),
    ("eqc_h-0015", "micro.eq.round_lot", {"price": "250.01"}, {"round_lot": 40}),
    ("eqc_h-0016", "micro.eq.round_lot", {"price": "10000.01"}, {"round_lot": 1}),
    ("eqc_h-0017", "micro.eq.round_lot", {"as_of": "2024-01-02", "price": "10000.01"}, {"round_lot": 100}),
]


def spot(pair, d, hol=None):
    return ("micro.fx.spot_date", {"holidays": hol or {}, "pair": pair, "trade_date": d})


FXC_ROWS = [
    ("fxc_h-0001", "micro.fx.pip_value", {"notional": "1000000", "pair": "EURUSD"},
     {"currency": "USD", "pip_value": "100"}),
    ("fxc_h-0002", "micro.fx.pip_value", {"notional": "1000000", "pair": "USDJPY"},
     {"currency": "JPY", "pip_value": "10000"}),
    ("fxc_h-0003", *spot("EURUSD", "2026-11-16"), {"spot_date": "2026-11-18"}),
    ("fxc_h-0004", *spot("EURUSD", "2026-11-24", {"USD": ["2026-11-26"]}), {"spot_date": "2026-11-27"}),
    ("fxc_h-0005", *spot("EURUSD", "2026-11-20"), {"spot_date": "2026-11-24"}),
    ("fxc_h-0006", *spot("USDCAD", "2026-11-20"), {"spot_date": "2026-11-23"}),
    ("fxc_h-0007", *spot("USDEUR", "2026-11-16"), "E_INPUT"),
    # USD-only holiday on T+1 does not stop the count (source check retry 2026-11-18). Hand.
    ("fxc_h-0008", *spot("EURUSD", "2026-11-25", {"USD": ["2026-11-26"]}), {"spot_date": "2026-11-27"}),
]

Q = {"ask": "1.0852", "bid": "1.0850", "quote_mid": "1.0851"}


def req(side="BUY", after="1.0855", sym=True, u="0.50"):
    return {"mid_after": after, "p_random_reject": "0.05", "pair": "EURUSD", "qty": "1000000", "quote": Q,
            "side": side, "symmetric": sym, "threshold_pips": "2", "u": u}


def res(outcome, move, price=None):
    return {"label": FX, "move_pips": move, "outcome": outcome, "price": price}


def rng_row(cid, idx, seed=20261118, p="0.5"):
    """HR-97 in simulation: u is the first uniform of stream `idx` of core.rng seeded by `seed`
    (rng.md: stream k = the seeded generator jumped k times), computed with the oracle's own Xo."""
    u = Xo(seed=seed, stream=idx).uniform()
    inp = {k: v for k, v in req(after="1.0852").items() if k != "u"}
    inp.update(p_random_reject=p, request_index=idx, seed=seed)
    out = res("LL_RANDOM", "1") if u < float(p) else res("FILL", "1", "1.0852")
    out["u"] = u
    return (cid, "exec.sim.fx.request", inp, out)


def stream(mid):
    return {"half_spread_pips": "1", "mid_path": [{"mid": mid, "time": 0}], "pair": "EURUSD", "tick": "0.00001"}


FXV_ROWS = [
    ("fxv_h-0001", "exec.sim.fx.stream", stream("1.08512"),
     {"label": FX, "quotes": [{"ask": "1.08522", "bid": "1.08502", "mid": "1.08512", "time": 0}]}),
    ("fxv_h-0002", "exec.sim.fx.stream", stream("1.085125"),
     {"label": FX, "quotes": [{"ask": "1.08523", "bid": "1.08502", "mid": "1.085125", "time": 0}]}),
    ("fxv_h-0003", "exec.sim.fx.request", req(), res("LL_PRICE", "4")),
    ("fxv_h-0004", "exec.sim.fx.request", req(after="1.0852"), res("FILL", "1", "1.0852")),
    ("fxv_h-0005", "exec.sim.fx.request", req(after="1.0852", u="0.03"), res("LL_RANDOM", "1")),
    ("fxv_h-0006", "exec.sim.fx.request", req(after="1.0847"), res("LL_PRICE", "-4")),
    ("fxv_h-0007", "exec.sim.fx.request", req(after="1.0847", sym=False), res("FILL", "-4", "1.0852")),
    ("fxv_h-0008", "exec.sim.fx.request", req("SELL", "1.0848", False), res("LL_PRICE", "-3")),
    ("fxv_h-0009", "exec.sim.fx.request", req(after="1.0853"), res("FILL", "2", "1.0852")),
    rng_row("fxv_h-0010", 0), rng_row("fxv_h-0011", 1), rng_row("fxv_h-0012", 2),
]


def parse(t, v):
    return ("micro.rates.parse_32nds", {"text": t}, {"value": v})


RTC_ROWS = [
    ("rtc_h-0001", *parse("99-16", "99.5")),
    ("rtc_h-0002", *parse("99-16+", "99.515625")),
    ("rtc_h-0003", *parse("99-162", "99.5078125")),
    ("rtc_h-0004", *parse("99-167", "99.5234375")),  # HR-109: 7 = 3/4 of a 32nd (was 7/8): not blind
    ("rtc_h-0011", "micro.rates.bond_yield", {"coupon": "0.04", "frequency": 2, "periods": 4, "price": "100"},
     {"yield": 0.04}),
    ("rtc_h-0012", "micro.rates.bond_yield", {"coupon": "0.04", "frequency": 2, "periods": 2,
                                              "price": "99.036287923854848305"}, {"yield": 0.05}),
    ("rtc_h-0005", "micro.rates.format_32nds", {"resolution": 64, "value": "101.296875"}, {"text": "101-09+"}),
    ("rtc_h-0006", "micro.rates.format_32nds", {"resolution": 128, "value": "101.3"}, "E_DOMAIN"),
    ("rtc_h-0007", "micro.rates.tick_value", {"face": "100000", "tick": "0.015625"}, {"tick_value": "15.625"}),
    ("rtc_h-0008", "micro.rates.bond_price", {"coupon": "0.04", "frequency": 2, "periods": 2, "yield": "0.05"},
     {"price": "99.036287924"}),
    ("rtc_h-0009", "micro.rates.bond_price", {"coupon": "0.04", "frequency": 2, "periods": 4, "yield": "0.04"},
     {"price": "100"}),
    ("rtc_h-0010", "micro.rates.bill_price", {"days": 91, "discount": "0.05"}, {"price": "98.736111111"}),
]
ZN = {"symbol": "ZN"}
FUT_ROWS = [
    ("fut_h-0001", "exec.sim.fut.to_ticks", {"contract": ZN, "price": "110-16+"}, {"label": RT, "ticks": 7073}),
    ("fut_h-0002", "exec.sim.fut.to_text", {"contract": ZN, "ticks": 7073}, {"label": RT, "text": "110-16+"}),
    ("fut_h-0003", "exec.sim.fut.to_ticks", {"contract": ZN, "price": "110-162"}, "E_DOMAIN"),
    ("fut_h-0004", "exec.sim.fut.pnl", {"buy_price": "110-16", "contract": ZN, "fee_per_contract": "0", "qty": 3,
                                        "sell_price": "110-17+"}, {"fees": "0", "label": RT, "pnl": "140.625"}),
    ("fut_h-0005", "exec.sim.fut.pnl", {"buy_price": "110-16", "contract": ZN, "fee_per_contract": "1.00", "qty": 3,
                                        "sell_price": "110-17+"}, {"fees": "6", "label": RT, "pnl": "134.625"}),
    ("fut_h-0006", "exec.sim.fut.variation", {"contract": {"symbol": "ZB"}, "price": "120-00", "qty": 1, "settlements":
                                              ["119-31"], "side": "BUY"}, {"label": RT, "variation_margin": ["-31.25"]}),
]

# Hand error cases beyond the tables (HR-66 order: E_SCHEMA, E_INPUT, E_DOMAIN, E_LIMIT).
ERRORS = {
    "auc_h": [
        ("limit off the tick grid", "exec.sim.auction.uncross", auc([o("b1", "BUY", "10.005", 1)]), "E_DOMAIN"),
        ("duplicate id", "exec.sim.auction.uncross", auc([o("x", "BUY", "10.00", 1), o("x", "SELL", "10.00", 1)]),
         "E_INPUT"),
        ("schema before input: qty as a string", "exec.sim.auction.uncross",
         auc([o("x", "BUY", "10.00", "1"), o("x", "SELL", "10.00", 1)]), "E_SCHEMA"),
    ],
    "eqc_h": [
        ("non-positive price", *rp("0", "BUY"), "E_DOMAIN"),
        ("half-penny tier before the compliance date", *rp("10", "BUY", tick_tier="HALF_PENNY", as_of="2024-01-02"),
         "E_INPUT"),
    ],
    "fxc_h": [("unknown currency", "micro.fx.pip_value", {"notional": "1", "pair": "EURXXX"}, "E_INPUT")],
    "fxv_h": [("u outside [0, 1)", "exec.sim.fx.request", req(u="1"), "E_DOMAIN"),
              ("bid above ask (input before domain)", "exec.sim.fx.request",
               dict(req(u="1"), quote={"ask": "1.0850", "bid": "1.0852", "quote_mid": "1.0851"}), "E_INPUT")],
    "rtc_h": [("32nds above 31", "micro.rates.parse_32nds", {"text": "99-32"}, "E_DOMAIN"),
              ("malformed text", "micro.rates.parse_32nds", {"text": "99.16"}, "E_SCHEMA"),
              ("third digit 3 is not a CME quarter (HR-109)", "micro.rates.parse_32nds", {"text": "99-163"}, "E_SCHEMA"),
              ("price not positive", "micro.rates.bond_yield",
               {"coupon": "0.04", "frequency": 2, "periods": 2, "price": "0"}, "E_DOMAIN"),
              ("resolution not allowed", "micro.rates.format_32nds", {"resolution": 100, "value": "99"}, "E_DOMAIN")],
    "fut_h": [("decimal price off the grid", "exec.sim.fut.to_ticks", {"contract": ZN, "price": "110.01"}, "E_DOMAIN"),
              ("empty settlements", "exec.sim.fut.variation",
               {"contract": ZN, "price": "110-00", "qty": 0, "settlements": [], "side": "BUY"}, "E_INPUT")],
}

# HR-116 integer limits: integer inputs within +-(2^53 - 1), request_index within 0..2^32 - 1, seed
# within 0..2^53 - 1; outside is E_LIMIT in all four languages. Cases at both sides of each boundary.
# request_index = 2^32 - 1 itself is not a golden: the stream is 2^32 - 1 jumps (rng.md), too slow to compute.
I53 = 2**53 - 1
FUT_VAR = {"contract": ZN, "price": "110-00", "settlements": ["110-01"], "side": "BUY"}
for _d, _i, _s in [("HR-116: request_index -1", -1, 20261118), ("HR-116: request_index 2^32", 2**32, 20261118),
                   ("HR-116: seed -1", 0, -1), ("HR-116: seed 2^53", 0, I53 + 1)]:
    _inp = {k: v for k, v in req(after="1.0852").items() if k != "u"}
    _inp.update(p_random_reject="0.5", request_index=_i, seed=_s)
    ERRORS["fxv_h"].append((_d, "exec.sim.fx.request", _inp, "E_LIMIT"))
ERRORS["fut_h"] += [("HR-116: qty 2^53", "exec.sim.fut.variation", dict(FUT_VAR, qty=I53 + 1), "E_LIMIT"),
                    ("HR-116: qty -2^53", "exec.sim.fut.variation", dict(FUT_VAR, qty=-(I53 + 1)), "E_LIMIT")]
# In-range sides (ok rows, appended after the error cases so no case id moves).
BOUNDARY_OK = {"fxv_h": [rng_row("", 0, seed=I53)[1:], rng_row("", 0, seed=0)[1:]]}

LIT = "simulated venue; not a real exchange"


def ev(oid, trader, side, typ, price, qty, **kw):
    e = {"id": oid, "op": "NEW", "qty": qty, "side": side, "trader": trader, "type": typ}
    if price is not None:
        e["price"] = price
    e.update(kw)
    return e


def cons(sub, filled="0", cancelled="0", rejected="0"):
    return {"cancelled": cancelled, "filled": filled, "rejected": rejected, "resting": "0", "submitted": sub}


SES_IN = {"tick_size": "0.01", "lot_size": "1", "session": {"ref_price": "10.00"},
          "fee_schedule": {"auction_fee": "0", "maker_rebate": "0", "taker_fee": "0"},
          "events": [ev("B1", "T1", "BUY", "LIMIT", "10.02", "100"), ev("S1", "T2", "SELL", "LIMIT", "10.00", "60"),
                     ev("S2", "T2", "SELL", "LIMIT", "10.01", "80"), ev("I1", "T3", "BUY", "IOC", "10.05", "10"),
                     {"op": "PHASE", "phase": "CONTINUOUS"}, ev("B2", "T3", "BUY", "LIMIT", "10.01", "40"),
                     {"op": "PHASE", "phase": "PRE_CLOSE"}, ev("B3", "T1", "BUY", "LIMIT", "10.00", "50"),
                     ev("B4", "T1", "BUY", "MARKET", None, "30", on_close=True),
                     ev("S3", "T2", "SELL", "LIMIT", "9.99", "20", on_close=True), {"op": "PHASE", "phase": "CLOSED"}]}
# Hand: open call book B1 100@10.02 | S1 60@10.00, S2 80@10.01. V: 10.00 60 (I +40), 10.01 100 (I -40),
# 10.02 100 (I -40); min |I| ties, all negative: lowest, 10.01. B1 100; S1 60, S2 40; S2 40 rests and
# B2 takes it in CONTINUOUS. I1 (IOC) and B3 (no on_close in PRE_CLOSE) are rejected PHASE. Close book:
# B4 MARKET 30 | S3 20@9.99: one candidate, V 20, I +10; B4's 10 left is cancelled (HR-96).
SES_OUT = {
    "auctions": [
        {"fills": [{"id": "B1", "price": "10.01", "qty": "100", "side": "B"},
                   {"id": "S1", "price": "10.01", "qty": "60", "side": "S"},
                   {"id": "S2", "price": "10.01", "qty": "40", "side": "S"}],
         "imbalance": "-40", "phase": "OPEN", "price": "10.01", "volume": "100"},
        {"fills": [{"id": "B4", "price": "9.99", "qty": "20", "side": "B"},
                   {"id": "S3", "price": "9.99", "qty": "20", "side": "S"}],
         "imbalance": "10", "phase": "CLOSE", "price": "9.99", "volume": "20"}],
    "book": {"asks": [], "bids": []}, "cancelled": [{"id": "B4", "qty": "10"}],
    "conservation": {"B1": cons("100", "100"), "B2": cons("40", "40"), "B3": cons("50", rejected="50"),
                     "B4": cons("30", "20", "10"), "I1": cons("10", rejected="10"), "S1": cons("60", "60"),
                     "S2": cons("80", "80"), "S3": cons("20", "20")},
    "fees": {"T1": "0", "T2": "0", "T3": "0"},
    "fills": [{"maker_id": "S2", "price": "10.01", "qty": "40", "seq": 1, "taker_id": "B2"}],
    "label": LIT, "mbp": {"asks": [], "bids": []}, "phase": "CLOSED",
    "rejects": [{"id": "I1", "reason": "PHASE"}, {"id": "B3", "reason": "PHASE"}],
}
SES_ROWS = [
    ("ses_h-0001", "exec.sim.lit.run", SES_IN, SES_OUT),
    ("ses_h-0002", "exec.sim.lit.run", dict(SES_IN, events=SES_IN["events"][:4] + [{"op": "PHASE", "phase": "PRE_CLOSE"}]),
     "E_INPUT"),
]
SOR_LIT = json.loads((common.ROOT / "datasets/golden/stage_h/sor_h.json").read_text(encoding="utf-8"))["cases"][0]
assert SOR_LIT["case_id"] == "sor_h-0001"


def classed(inp, order, venue):
    out = dict(inp, asset_class=order)
    out["venues"] = [dict(v, asset_class=venue) for v in inp["venues"]]
    return out


ACLS_ROWS = [
    ("acls_h-0001", "exec.sor.allocate", classed(SOR_LIT["inputs"], "FX", "FX"), SOR_LIT["expected"]["outputs"]),
    ("acls_h-0002", "exec.sor.allocate", classed(SOR_LIT["inputs"], "EQUITY", "RATES"), "E_INPUT"),
    ("acls_h-0003", "exec.sor.allocate", classed(SOR_LIT["inputs"], "EQUITY", "BONDS"), "E_SCHEMA"),
    ("acls_h-0004", "exec.sim.dark.run", {"config": {"asset_class": "FX", "lot_size": "1", "p_firm": "1", "seed": 1,
                                                      "tick_size": "0.01"}, "events": []}, "E_INPUT"),
    ("acls_h-0005", "exec.sor.allocate",
     dict(classed(SOR_LIT["inputs"], "RATES", "RATES"),
          venues=[dict(SOR_LIT["inputs"]["venues"][0], asset_class="RATES"),
                  {"as": "0.1", "asset_class": "RATES", "kind": "DARK", "r": "0", "tail": ["0.5", "0"]}]), "E_INPUT"),
]
ADDED.update({c: "session phases in exec.sim.lit.run" for c, *_ in SES_ROWS})
ADDED.update({"acls_h-0001": "asset_class on SOR (HR-93); outputs as sor_h-0001",
              "acls_h-0002": "asset_class mismatch (HR-93)", "acls_h-0003": "asset_class schema",
              "acls_h-0004": "FX dark pool is E_INPUT (HR-113)", "acls_h-0005": "RATES dark venue in SOR is E_INPUT (HR-113)"})
ERRORS["ses_h"] = [("PHASE without a session is not an event", "exec.sim.lit.run",
                    {k: v for k, v in SES_IN.items() if k != "session"}, "E_SCHEMA")]
ERRORS["acls_h"] = []

SUITES = [("auc_h", AUC, [(c, "exec.sim.auction.uncross", i, e) for c, i, e in AUC_ROWS]), ("eqc_h", CONV, EQC_ROWS),
          ("fxc_h", CONV, FXC_ROWS), ("fxv_h", FXV, FXV_ROWS), ("rtc_h", CONV, RTC_ROWS), ("fut_h", FUT, FUT_ROWS),
          ("ses_h", AUC, SES_ROWS), ("acls_h", CONV, ACLS_ROWS)]


def _first_number(v, path=()):
    if isinstance(v, dict):
        for k in sorted(v):
            p = _first_number(v[k], path + (k,))
            if p is not None:
                return p
    elif isinstance(v, list):
        for i, x in enumerate(v):
            p = _first_number(x, path + (i,))
            if p is not None:
                return p
    elif isinstance(v, str) and path and path[-1] not in ("id", "pair", "side", "text", "symbol") and "-" not in v[1:]:
        try:
            if Decimal(v).is_finite():
                return path
        except ArithmeticError:
            return None
    return None


def build():
    suites = []
    for name, spec, rows in SUITES:
        s = Suite(name, spec, G)
        for cid, op, inp, exp in rows:
            assert cid.startswith(name + "-")
            err = exp if isinstance(exp, str) else None
            if err is None:
                assert name == "acls_h" or ("label" in exp) == (name in VENUE_SUITES or "exec." in op), cid  # A4, HR-94 as ruled
            desc = f"{cid} from the spec table" + (f"; not blind: {NOT_BLIND[cid]}" if cid in NOT_BLIND else "")
            if cid in RATES2:
                desc = f"{cid}: blind in rates packet 2 (HR-114), was hand-only"
            elif cid in ADDED:
                desc = f"{cid} hand: {ADDED[cid]} (source check 2026-11-18); not blind"
            if name == "auc_h" and cid not in ("auc_h-0001", "auc_h-0002", "auc_h-0009"):
                desc += "; fills, residual and cancelled hand-derived (the table states price, volume, imbalance)"
            cls = "root_finding" if op == "micro.rates.bond_yield" else "date_and_convention"
            if err:
                s.add(op, inp, error=err, cls=cls, verified=verified(cid),
                      tags=["stage_h", "multiasset"], description=desc)
            else:
                s.add(op, inp, exp, cls=cls, verified=verified(cid),
                      tags=["stage_h", "multiasset"], description=desc)
            s.cases[-1]["case_id"] = cid
        first = len(rows) + 1
        for k, (desc, op, inp, code) in enumerate(ERRORS[name]):
            s.add(op, inp, error=code, cls="date_and_convention", verified=["hand"], tags=["stage_h", "error"],
                  description=f"hand: {desc}")
            s.cases[-1]["case_id"] = f"{name}-{first + k:04d}"
        first += len(ERRORS[name])
        for k, (op, inp, exp) in enumerate(BOUNDARY_OK.get(name, [])):
            s.add(op, inp, exp, cls="date_and_convention", verified=["hand"], tags=["stage_h", "hr116"],
                  description=f"hand: HR-116 in-range boundary (seed {inp['seed']}, request_index {inp['request_index']})")
            s.cases[-1]["case_id"] = f"{name}-{first + k:04d}"
        suites.append(s)
    suites.append(e1_suite(suites))
    return suites


def e1_suite(suites):
    """HR-12 / F-2a: a NaN decimal string at the first decimal input of each operation is E_SCHEMA."""
    e = Suite("e1_h4", CONV, G)
    seen = set()
    for su in suites:
        for c in su.cases:
            op = c["operation"]
            if op in seen or c["expected"]["status"] != "ok":
                continue
            path = _first_number(c["inputs"])
            if path is None:
                continue
            seen.add(op)
            inp = json.loads(json.dumps(c["inputs"]))
            node = inp
            for k in path[:-1]:
                node = node[k]
            node[path[-1]] = "NaN"
            e.add(op, inp, error="E_SCHEMA", cls="date_and_convention", verified=["hand"],
                  tags=["stage_h", "e1", "non-finite-input"],
                  description=f"HR-12: NaN decimal string at {'/'.join(map(str, path))} is E_SCHEMA (from {c['case_id']})")
    # Operations with no plain decimal input (dates, 32nds text, integer ticks): "NaN" at the named field.
    for su in suites:
        for c in su.cases:
            op = c["operation"]
            if op in seen or c["expected"]["status"] != "ok" or op not in NO_DECIMAL:
                continue
            seen.add(op)
            inp = dict(json.loads(json.dumps(c["inputs"])), **{NO_DECIMAL[op]: "NaN"})
            e.add(op, inp, error="E_SCHEMA", cls="date_and_convention", verified=["hand"],
                  tags=["stage_h", "e1", "non-finite-input"],
                  description=f"HR-12: NaN at {NO_DECIMAL[op]} (no decimal input) is E_SCHEMA (from {c['case_id']})")
    return e


NO_DECIMAL = {"micro.eq.settle_date": "trade_date", "micro.fx.spot_date": "trade_date",
              "micro.rates.parse_32nds": "text", "exec.sim.fut.to_ticks": "price",
              "exec.sim.fut.to_text": "ticks", "exec.sim.fut.variation": "price"}


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_h"
    for s in build():
        s.write()
    common.GOLDEN = keep


if __name__ == "__main__":
    main()
