"""Stage H wave 2 execution goldens: adaptive algos (alg_h, H-14) and TCA pre-trade / attribution (tcx_h, H-17).

Specs: specifications/10-execution/adaptive-algos.md and tca-pretrade.md, rulings HR-59..65
(stage-h-rulings-w2-exec.md). Expected values are the spec lane's hand derivations (exact rational
arithmetic; square roots to 20 digits) written into the tables below; no value is taken from an
implementation. Each ok-case is re-checked below with exact Fractions (attribution identity, arrival
holdings, pair rounding) before writing. Blind record: program/STAGE_H_BLIND_EXEC.md (36/36 MATCH or
SHAPE-ONLY, 0 VALUE MISMATCH).

    cd oracle/python && uv run python -W ignore gen_stage_h_w2_exec.py
"""
import json, sys
R = sys.argv[1] if len(sys.argv) > 1 else str(__import__("pathlib").Path(__file__).resolve().parents[2])
LN2 = 0.69314718055994531
E = lambda c: {"status": "error", "error_code": c}
def ok(**k): return {"status": "ok", "outputs": k}
A, C, L, P, B = "exec.algo.arrival", "exec.algo.close", "exec.algo.liquidity_seek", "exec.algo.pair", "exec.algo.basket"
def leg(side, q=None, p=None):
    d = {"side": side}
    if q is not None: d["quantity"] = q
    d["price"] = p
    return d
alg = [
 (A, dict(quantity=1000, n_buckets=4, urgency=0.0, mode="CONTINUOUS"), ok(slices=[250,250,250,250])),
 (A, dict(quantity=1000, n_buckets=2, urgency=LN2, mode="CONTINUOUS"), ok(slices=[600,400])),
 (A, dict(quantity=1001, n_buckets=2, urgency=LN2, mode="UNITS"), ok(slices=[601,400])),
 (A, dict(quantity=2100, n_buckets=3, urgency=LN2, mode="CONTINUOUS"), ok(slices=[1100,600,400])),
 (A, dict(quantity=1000, n_buckets=4, urgency=-0.1, mode="CONTINUOUS"), E("E_DOMAIN")),
 (A, dict(quantity=1000, n_buckets=0, urgency=0.5, mode="CONTINUOUS"), E("E_INPUT")),
 (C, dict(quantity=10000, close_volume=50000, auction_participation=0.1, profile=[1,1,2,4], mode="CONTINUOUS"), ok(auction_quantity=5000, slices=[625,625,1250,2500])),
 (C, dict(quantity=3000, close_volume=50000, auction_participation=0.1, profile=[1,1,2,4], mode="CONTINUOUS"), ok(auction_quantity=3000, slices=[0,0,0,0])),
 (C, dict(quantity=10002, close_volume=50000, auction_participation=0.1, profile=[1,1,1], mode="UNITS"), ok(auction_quantity=5000, slices=[1668,1667,1667])),
 (C, dict(quantity=1000, close_volume=50000, auction_participation=1.5, profile=[1], mode="CONTINUOUS"), E("E_DOMAIN")),
 (C, dict(quantity=10000, close_volume=50000, auction_participation=0.1, profile=[0,0], mode="CONTINUOUS"), E("E_DOMAIN")),
 (L, dict(side="BUY", quantity=1000, limit_price=100.2, take_fraction=0.5, books=[[[100.0,400],[100.1,400],[100.3,1000]],[[100.1,600],[100.2,600]]]), ok(slices=[400,600], avg_prices=[100.0,100.1], filled=1000, residual=0, notional=100060, avg_fill_price=100.06)),
 (L, dict(side="BUY", quantity=1000, limit_price=100.0, take_fraction=1.0, books=[[[100.0,300],[100.5,1000]],[[101.0,500]]]), ok(slices=[300,0], avg_prices=[100.0,None], filled=300, residual=700, notional=30000, avg_fill_price=100.0)),
 (L, dict(side="SELL", quantity=500, limit_price=99.9, take_fraction=0.5, books=[[[100.0,200],[99.9,200],[99.8,1000]],[[99.95,1000]]]), ok(slices=[200,300], avg_prices=[100.0,99.95], filled=500, residual=0, notional=49985, avg_fill_price=99.97)),
 (L, dict(side="BUY", quantity=1000, limit_price=101.0, take_fraction=1.0, books=[[[100.0,300],[100.5,300],[101.0,1000]]]), ok(slices=[1000], avg_prices=[100.55], filled=1000, residual=0, notional=100550, avg_fill_price=100.55)),
 (L, dict(side="BUY", quantity=1000, limit_price=101.0, take_fraction=0.0, books=[[[100.0,300]]]), E("E_DOMAIN")),
 (L, dict(side="BUY", quantity=1000, limit_price=101.0, take_fraction=1.0, books=[[[100.5,300],[100.0,300]]]), E("E_INPUT")),
 (P, dict(leg_a=leg("BUY",1000,50.0), leg_b=leg("SELL",p=25.0), pair_mode="CASH_BALANCED", n_buckets=4, mode="CONTINUOUS"), ok(slices_a=[250]*4, slices_b=[500]*4, quantity_b=2000, cash_imbalance=[0,0,0,0])),
 (P, dict(leg_a=leg("BUY",1000,30.0), leg_b=leg("SELL",p=70.0), pair_mode="CASH_BALANCED", n_buckets=3, mode="UNITS"), ok(slices_a=[334,333,333], slices_b=[143,143,143], quantity_b=429, cash_imbalance=[10,-10,-30])),
 (P, dict(leg_a=leg("BUY",1000,100.0), leg_b=leg("SELL",p=50.0), pair_mode="HEDGED", hedge_ratio=0.8, n_buckets=2, mode="CONTINUOUS"), ok(slices_a=[500,500], slices_b=[400,400], quantity_b=800, cash_imbalance=[30000,60000])),
 (P, dict(leg_a=leg("BUY",1000,50.0), leg_b=leg("BUY",p=25.0), pair_mode="CASH_BALANCED", n_buckets=2, mode="CONTINUOUS"), E("E_INPUT")),
 (P, dict(leg_a=leg("BUY",1000,50.0), leg_b=leg("SELL",p=25.0), pair_mode="HEDGED", hedge_ratio=0.0, n_buckets=2, mode="CONTINUOUS"), E("E_DOMAIN")),
 (B, dict(legs=[leg("BUY",300,10.0), leg("BUY",200,20.0), leg("SELL",700,10.0)], n_buckets=2, mode="CONTINUOUS"), ok(slices=[[150,150],[100,100],[350,350]], cash_imbalance=[0,0], gross_notional=14000)),
 (B, dict(legs=[leg("BUY",3,10.0), leg("SELL",1,30.0)], n_buckets=2, mode="UNITS"), ok(slices=[[2,1],[1,0]], cash_imbalance=[-10,0], gross_notional=60)),
 (B, dict(legs=[], n_buckets=2, mode="CONTINUOUS"), E("E_INPUT")),
]
T, X = "exec.tca.pretrade", "exec.tca.attribution"
p1 = dict(a1=700.0, a2=0.5, a3=1.0, a4=0.5, b1=0.9)
p2 = dict(a1=700.0, a2=1.0, a3=1.0, a4=0.5, b1=1.0)
base2 = dict(quantity=100000, adv=1000000, daily_vol=0.02, participation=0.04, half_spread_bps=0.0, params=p2)
def m(d, **k):
    d = json.loads(json.dumps(d)); d.update(k); return d
def fl(q, p, mid): return dict(quantity=q, price=p, mid=mid)
b6 = dict(side="BUY", decision_price=100.0, arrival_mid=100.1, end_price=101.0, order_quantity=1000, fills=[fl(600,100.2,100.15), fl(200,100.3,100.25)], fees=5.0)
tcx = [
 (T, dict(quantity=40000, adv=1000000, daily_vol=0.02, participation=0.25, half_spread_bps=1.5, params=p1, price=50.0), ok(istar_bps=2.8, impact_bps=1.54, spread_bps=1.5, expected_cost_bps=3.04, duration_days=0.16, timing_risk_bps=46.1880215352, expected_cost=608, timing_risk=9237.60430703)),
 (T, base2, ok(istar_bps=1.4, impact_bps=0.28, spread_bps=0, expected_cost_bps=0.28, duration_days=2.5, timing_risk_bps=182.574185835)),
 (T, m(base2, participation=1.0), E("E_DOMAIN")),
 (T, m(base2, params=dict(p2, b1=1.2)), E("E_DOMAIN")),
 (T, m(base2, quantity=0), E("E_INPUT")),
 (X, b6, ok(delay=80, impact=60, spread=40, execution=100, opportunity=200, fees=5, total=385, total_bps=38.5)),
 (X, dict(side="SELL", decision_price=100.0, arrival_mid=100.0, end_price=99.0, order_quantity=1000, fills=[fl(500,99.9,99.95), fl(500,99.7,99.8)], fees=2.0), ok(delay=0, impact=125, spread=75, execution=200, opportunity=0, fees=2, total=202, total_bps=20.2)),
 (X, dict(side="BUY", decision_price=99.5, arrival_mid=100.0, end_price=100.0, order_quantity=100, fills=[fl(100,100.0,100.05)], fees=0.0), ok(delay=50, impact=5, spread=-5, execution=0, opportunity=0, fees=0, total=50, total_bps=50.2512562814)),
 (X, dict(side="BUY", decision_price=100.0, arrival_mid=100.5, end_price=101.0, order_quantity=100, fills=[], fees=0.0), ok(delay=0, impact=0, spread=0, execution=0, opportunity=100, fees=0, total=100, total_bps=100)),
 (X, m(b6, fills=[fl(600,100.2,100.15), fl(600,100.3,100.25)]), E("E_INPUT")),
 (X, m(b6, fills=[fl(600,100.2,0.0), fl(200,100.3,100.25)]), E("E_DOMAIN")),
]

from fractions import Fraction as F
def _check():
    for op, i, e in tcx:
        if op == X and e["status"] == "ok":
            s = 1 if i["side"] == "BUY" else -1
            fs = [(F(str(f["quantity"])), F(str(f["price"])), F(str(f["mid"]))) for f in i["fills"]]
            Q = sum(q for q, _, _ in fs); pd, m0 = F(str(i["decision_price"])), F(str(i["arrival_mid"]))
            d = s * Q * (m0 - pd); im = s * sum(q * (m - m0) for q, _, m in fs); sp = s * sum(q * (p - m) for q, p, m in fs)
            op_ = s * (F(str(i["order_quantity"])) - Q) * (F(str(i["end_price"])) - pd)
            assert (d, im, sp, op_) == tuple(F(str(e["outputs"][k])) for k in ("delay", "impact", "spread", "opportunity")), i
            assert d + im + sp + op_ + F(str(i["fees"])) == F(str(e["outputs"]["total"]))
    for op, i, e in alg:
        if op == P and e["status"] == "ok":
            o = e["outputs"]; assert sum(o["slices_a"]) == i["leg_a"]["quantity"] and sum(o["slices_b"]) == o["quantity_b"]
_check()
def suite(name, spec, rows):
    cs = []
    for i, (op, inp, exp) in enumerate(rows, 1):
        cid = f"{name}-{i:04d}"
        cs.append(dict(case_id=cid, operation=op, inputs=inp, expected=exp, tolerance_class="simple_analytic",
                       verified_by=["hand"], tags=["stage_h", "wave2", name.split("_")[0]], description=f"{spec} golden {cid}"))
    return dict(schema_version="1.0", suite=name, spec=spec, spec_version="0.1.0", generator="oracle/python/gen_stage_h_w2_exec.py",
                reviewer="none: self-assessment; blind re-derivation pending", cases=cs)
for n, s, r in [("alg_h", "specifications/10-execution/adaptive-algos.md", alg), ("tcx_h", "specifications/10-execution/tca-pretrade.md", tcx)]:
    with open(f"{R}/datasets/golden/stage_h/{n}.json", "w", newline="\n") as fh:
        json.dump(suite(n, s, r), fh, indent=1); fh.write("\n")
