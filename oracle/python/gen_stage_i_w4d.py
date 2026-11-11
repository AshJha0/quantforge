"""Stage I wave 4d: hedge slippage, realised execution cost against the wave 4a cost model
(specifications/08-hedging/hedge-slippage.md, rulings I-36 on).

Every golden, error codes included, is the output of `slip_ref`, in exact rational arithmetic (Fractions) and rounded
once to binary64 at the end. No outside library computes implementation shortfall, so no case counts as outside (I-2);
the self-checks are the identities `shortfall = execution + opportunity` and `slippage = execution - model`.

    cd oracle/python && uv run python -W ignore gen_stage_i_w4d.py
"""
import json
from fractions import Fraction as Fr
from pathlib import Path

import gen_stage_i_w1 as W
from gen_stage_i_w1 import fail, finite_rule, run_error, RF
from qf_oracle import common
from qf_oracle.common import Suite, note

G = "oracle/python/gen_stage_i_w4d.py"
SPEC = "specifications/08-hedging/hedge-slippage.md"
HERE = Path(__file__).resolve().parent
SL = "hedge.slippage.report"


def sgn(x):
    return (x > 0) - (x < 0)


def slip_ref(inp):
    orders = inp["orders"]
    if len(orders) > 10000 or sum(len(o["fills"]) for o in orders) > 1000000:
        fail("E_LIMIT")
    finite_rule(inp)
    if not orders:
        fail("E_INPUT", "no orders")
    for o in orders:
        Q = o["quantity"]
        if Q == 0:
            fail("E_INPUT", "zero order")
        if any(sgn(f["quantity"]) != sgn(Q) for f in o["fills"]):
            fail("E_INPUT", "fill against the order's side, or a zero fill")
        if abs(sum(Fr(f["quantity"]) for f in o["fills"])) > abs(Fr(Q)):
            fail("E_INPUT", "overfilled")
    for o in orders:
        if o["decision_price"] <= 0 or o["final_price"] <= 0 or any(f["price"] <= 0 for f in o["fills"]):
            fail("E_DOMAIN", "price")
        if o["half_spread"] < 0 or o["impact"] < 0:
            fail("E_DOMAIN", "cost model")
    out = []
    tot = {k: Fr(0) for k in ("execution_cost", "opportunity_cost", "shortfall", "model_cost", "slippage")}
    for o in orders:
        d, pf = Fr(o["decision_price"]), Fr(o["final_price"])
        qf = sum((Fr(f["quantity"]) for f in o["fills"]), Fr(0))
        ex = sum((Fr(f["quantity"]) * (Fr(f["price"]) - d) for f in o["fills"]), Fr(0))
        op = (Fr(o["quantity"]) - qf) * (pf - d)
        model = Fr(o["half_spread"]) * abs(qf) + Fr(o["impact"]) * qf * qf
        r = {"filled_quantity": qf, "average_price": (sum((Fr(f["quantity"]) * Fr(f["price"]) for f in o["fills"]), Fr(0)) / qf) if qf else None,
             "execution_cost": ex, "opportunity_cost": op, "shortfall": ex + op, "model_cost": model, "slippage": ex - model}
        for k in tot:
            tot[k] += r[k]
        out.append(r)
    f = lambda v: None if v is None else float(v)  # noqa: E731
    return {"orders": [{k: f(v) for k, v in r.items()} for r in out], "total": {k: float(v) for k, v in tot.items()}}


def suite():
    s = Suite("hedgeslip_i", SPEC, G)
    buy = {"quantity": 1000.0, "decision_price": 100.0, "final_price": 101.5, "half_spread": 0.02, "impact": 0.0001,
           "fills": [{"quantity": 400.0, "price": 100.05}, {"quantity": 600.0, "price": 100.12}]}
    sell = {"quantity": -500.0, "decision_price": 50.0, "final_price": 49.2, "half_spread": 0.01, "impact": 0.0002,
            "fills": [{"quantity": -300.0, "price": 49.97}]}
    cases = [
        ("one buy, fully filled in two fills", dict(orders=[buy])),
        ("one sell, partly filled: opportunity cost on the rest", dict(orders=[sell])),
        ("buy and sell together: totals add", dict(orders=[buy, sell])),
        ("nothing filled: average price null, all opportunity cost", dict(orders=[dict(sell, fills=[])])),
        ("filled better than the decision price: negative cost", dict(orders=[dict(buy, fills=[{"quantity": 1000.0, "price": 99.98}])])),
        ("fills exactly at the model cost: zero slippage", dict(orders=[{"quantity": 100.0, "decision_price": 10.0, "final_price": 10.0, "half_spread": 0.25, "impact": 0.0,
                                                                         "fills": [{"quantity": 100.0, "price": 10.25}]}])),
    ]
    for desc, inp in cases:
        out = slip_ref(inp)
        for r in out["orders"] + [out["total"]]:
            assert abs(r["shortfall"] - r["execution_cost"] - r["opportunity_cost"]) <= 1e-9 * (1 + abs(r["shortfall"]))
            assert abs(r["slippage"] - (r["execution_cost"] - r["model_cost"])) <= 1e-9 * (1 + abs(r["slippage"]))
        s.add(SL, inp, out, cls=RF, verified=["exact-rational"], tags=["hedge", "slippage"], description=desc)
    assert s.cases[3]["expected"]["outputs"]["orders"][0]["average_price"] is None
    assert s.cases[5]["expected"]["outputs"]["total"]["slippage"] == 0.0
    e = dict(orders=[buy])
    errs = [
        (dict(orders=[]), "E_INPUT", "no orders"),
        (dict(orders=[dict(buy, fills=[{"quantity": -10.0, "price": 100.0}])]), "E_INPUT", "a sell fill on a buy order"),
        (dict(orders=[dict(buy, fills=[{"quantity": 1200.0, "price": 100.0}])]), "E_INPUT", "overfilled"),
        (dict(orders=[dict(buy, quantity=0.0, fills=[])]), "E_INPUT", "zero order"),
        (dict(orders=[dict(buy, decision_price=0.0)]), "E_DOMAIN", "zero decision price"),
        (dict(orders=[dict(buy, impact=-0.1)]), "E_DOMAIN", "negative impact"),
    ]
    for inp, code, desc in errs:
        run_error(s, SL, slip_ref, inp, code, desc, ["hedge", "slippage"])
    return s


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / W.FOLDER
    s = suite()
    for c in s.cases:
        c["tags"].append("synthetic")
    s.write()
    common.GOLDEN = keep
    reg_p = HERE.parent / "outside_register_i.json"
    reg = json.loads(reg_p.read_text(encoding="utf-8"))
    reg[s.name] = {"counted": 0, "total": len(s.cases), "rule": "no outside library computes implementation shortfall; exact rational arithmetic, uncounted"}
    suites = {k: v for k, v in reg.items() if not k.startswith("_")}
    cnt, tot = sum(v["counted"] for v in suites.values()), sum(v["total"] for v in suites.values())
    reg["_stage"] = {"counted": cnt, "total": tot, "share": round(cnt / tot, 4), "floor": 0.60,
                     "note": "Stage I so far, error cases in the denominator (ruling I-2); the floor applies at release"}
    reg_p.write_text(json.dumps(reg, indent=1) + "\n", encoding="utf-8", newline="\n")
    note(f"{s.name}: {len(s.cases)} cases, outside 0; stage I outside so far: {cnt} of {tot} = {100 * cnt / tot:.1f}%")


if __name__ == "__main__":
    main()
