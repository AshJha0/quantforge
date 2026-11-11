"""Stage I wave 4e: transaction costs in the dynamic delta-hedge backtest (specifications/08-hedging/
dynamic-hedge-and-effectiveness.md, section "Costs in the backtest (wave 4e)"; rulings I-39 on).

`bt_ref` extends the wave 4b reference with optional `half_spread` and `impact` (the wave 4a cost model, per share
traded). Without them it must return exactly the wave 4b result: every `hedgebt_i` golden is re-derived and compared
(ruling I-13 pattern). The new suite is `hedgebtcost_i`; every golden and error code comes from `bt_ref`.

Outside: as wave 4b, QuantLib 1.44 `AnalyticEuropeanEngine` value and delta on each date, then the spec's cash-account
arithmetic with the costs.

    cd oracle/python && uv run python -W ignore gen_stage_i_w4e.py
"""
import json
from pathlib import Path

import mpmath as mp

import gen_stage_i_w1 as W
import gen_stage_i_w4b as B
from gen_stage_i_w1 import fail, finite_rule, run_error, RF
from qf_oracle import common
from qf_oracle.common import Suite, note

mp.mp.dps = 50
G = "oracle/python/gen_stage_i_w4e.py"
SPEC = "specifications/08-hedging/dynamic-hedge-and-effectiveness.md"
HERE = Path(__file__).resolve().parent
BT = "hedge.backtest.delta"
MUT = []


def bt_ref(inp, val=None):
    if "half_spread" not in inp and "impact" not in inp:
        return B.bt_ref(inp, val)
    ts, ss = inp["times"], inp["spots"]
    if len(ts) > 100000:
        fail("E_LIMIT")
    finite_rule(inp)
    o = inp["option"]
    T = o["expiry_years"]
    if len(ts) != len(ss) or len(ts) < 4 or ts[0] != 0 or any(b <= a for a, b in zip(ts, ts[1:])) or ts[-1] > T:
        fail("E_INPUT", "path")
    if any(s <= 0 for s in ss) or o["strike"] <= 0 or T <= 0 or inp["hedge_volatility"] <= 0:
        fail("E_DOMAIN", "spot, strike, expiry or volatility")
    hs, eta = inp.get("half_spread", 0.0), inp.get("impact", 0.0)
    if hs < 0 or eta < 0:
        fail("E_DOMAIN", "negative cost parameter")
    hs, eta = mp.mpf(hs), mp.mpf(eta)
    val = val or (lambda S, tau: B.bs(o["type"], S, o["strike"], tau, inp["rate"], inp["dividend_yield"], inp["hedge_volatility"]))
    N = mp.mpf(inp["quantity"])
    r, q = mp.mpf(inp["rate"]), mp.mpf(inp["dividend_yield"])
    m = len(ts)
    V, D = [], []
    for t, S in zip(ts, ss):
        v_, d_ = val(S, mp.mpf(T) - mp.mpf(t))
        V.append(mp.mpf(v_))
        D.append(None if d_ is None else mp.mpf(d_))
    h = [-N * D[i] for i in range(m - 1)]

    def cost(dq):
        return hs * abs(dq) + eta * dq * dq
    paid = cost(h[0])  # the initial share purchase is a trade (I-39)
    cash = -N * V[0] - h[0] * mp.mpf(ss[0]) - paid
    pi = [-paid]
    for i in range(m - 1):
        dt = mp.mpf(ts[i + 1]) - mp.mpf(ts[i])
        cash = cash * mp.exp(r * dt) + h[i] * mp.mpf(ss[i]) * (mp.exp(q * dt) - 1)
        pi.append(N * V[i + 1] + h[i] * mp.mpf(ss[i + 1]) + cash)
        if i + 1 < m - 1:
            c = cost(h[i + 1] - h[i])
            paid += c
            cash -= (h[i + 1] - h[i]) * mp.mpf(ss[i + 1]) + c
    # a rebalance cost at t_{i+1} is paid after Pi_{i+1} is recorded, so it falls in the next step's change (I-39)
    item = [N * (V[i + 1] - V[i]) for i in range(m - 1)]
    hedge = [(pi[i + 1] - pi[i]) - item[i] for i in range(m - 1)]
    st = B.stats(item, hedge)
    return {"option_values": [float(v) for v in V], "shares": [float(v) for v in h], "portfolio_values": [float(v) for v in pi],
            "final_pnl": float(pi[-1]), "trading_cost": float(paid), **{k: float(v) for k, v in st.items()}}


def suite():
    # I-13 pattern: the wave 4b goldens are reproduced exactly with the cost inputs absent
    w4b = json.loads((HERE.parents[1] / "datasets" / "golden" / W.FOLDER / "hedgebt_i.json").read_text(encoding="utf-8"))
    for c in w4b["cases"]:
        try:
            got = {"status": "ok", "outputs": bt_ref(c["inputs"])}
        except W.QfErr as e:
            got = {"status": "error", "error_code": e.code}
        assert got == c["expected"], c["case_id"]
    s = Suite("hedgebtcost_i", SPEC, G)
    call = {"type": "CALL", "strike": 100.0, "expiry_years": 63 / 365}
    base = dict(rate=0.03, dividend_yield=0.01, hedge_volatility=0.20, quantity=-100.0)
    t1, s1 = B.path(20261111, 63, 1, 100.0, 0.20)
    t3, s3 = B.path(20261113, 9, 7, 100.0, 0.20)
    cases = [
        ("daily rebalancing, 2 cent half-spread", dict(base, option=call, times=t1, spots=s1, half_spread=0.02)),
        ("weekly rebalancing, 2 cent half-spread: fewer trades, less cost", dict(base, option=call, times=t3, spots=s3, half_spread=0.02)),
        ("daily rebalancing with spread and impact", dict(base, option=call, times=t1, spots=s1, half_spread=0.02, impact=0.001)),
        ("zero cost parameters equal the cost-free replay plus a zero trading_cost", dict(base, option=call, times=t3, spots=s3, half_spread=0.0, impact=0.0)),
        ("impact only", dict(base, option=call, times=t3, spots=s3, impact=0.002)),
    ]
    n_out = 0
    for desc, inp in cases:
        out = bt_ref(inp)
        qo = bt_ref(inp, B.ql_val(inp))
        lim = {"absolute": 1e-9, "relative": 1e-9, "reason": "a running cash account over up to 63 steps; option values up to 1e3 per position"}
        ok = all(B.close_all(qo[k], out[k], lim["absolute"], lim["relative"]) for k in out)
        n_out += ok
        if not ok:
            note(f"  hedgebtcost not counted: {desc}")
        s.add(BT, inp, out, cls=RF, limit=lim, verified=["mpmath-50", "wave-4b-reproduced"] + (["quantlib-1.44-analytic-european-daily"] if ok else []),
              tags=["hedge", "backtest", "cost"], description=desc)
    o = [c["expected"]["outputs"] for c in s.cases]
    free = B.bt_ref(cases[3][1])
    assert o[3]["trading_cost"] == 0.0 and all(o[3][k] == free[k] for k in free)
    assert o[1]["trading_cost"] < o[0]["trading_cost"], "weekly trades less than daily"
    free1 = B.bt_ref({k: v for k, v in cases[0][1].items() if k != "half_spread"})
    gap = free1["final_pnl"] - o[0]["final_pnl"]
    assert gap > 0, "costs lower the final P&L"
    MUT.append(("costs ignored", gap))
    e = dict(base, option=call, times=t3, spots=s3, half_spread=0.02)
    errs = [(dict(e, half_spread=-0.01), "E_DOMAIN", "negative half-spread"), (dict(e, impact=-1.0), "E_DOMAIN", "negative impact"),
            (dict(e, times=t3[:3], spots=s3[:3]), "E_INPUT", "three points (at least 4)")]
    for inp, code, desc in errs:
        run_error(s, BT, bt_ref, inp, code, desc, ["hedge", "backtest", "cost"])
    return s, n_out


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / W.FOLDER
    s, n_out = suite()
    for c in s.cases:
        c["tags"].append("synthetic")
    s.write()
    common.GOLDEN = keep
    reg_p = HERE.parent / "outside_register_i.json"
    reg = json.loads(reg_p.read_text(encoding="utf-8"))
    reg[s.name] = {"counted": n_out, "total": len(s.cases), "rule": "as hedgebt_i: QuantLib 1.44 AnalyticEuropeanEngine value and delta on each date, then the spec's cash-account arithmetic with costs; every output within the case limit"}
    suites = {k: v for k, v in reg.items() if not k.startswith("_")}
    cnt, tot = sum(v["counted"] for v in suites.values()), sum(v["total"] for v in suites.values())
    reg["_stage"] = {"counted": cnt, "total": tot, "share": round(cnt / tot, 4), "floor": 0.60,
                     "note": "Stage I so far, error cases in the denominator (ruling I-2); the floor applies at release"}
    reg_p.write_text(json.dumps(reg, indent=1) + "\n", encoding="utf-8", newline="\n")
    note(f"{s.name}: {len(s.cases)} cases, outside {n_out}; stage I outside so far: {cnt} of {tot} = {100 * cnt / tot:.1f}%")
    for m_, g in MUT:
        note(f"  mutant caught: {m_} (gap {g:.3e})")


if __name__ == "__main__":
    main()
