"""Stage I wave 4b: dynamic delta-hedge backtest and hedge effectiveness
(specifications/08-hedging/dynamic-hedge-and-effectiveness.md, rulings I-29 on).

Every golden, error codes included, is the output of `bt_ref` or `eff_ref` (50-digit mpmath). Paths are input data, made
here from a fixed formula and a seeded generator; they are recorded in the goldens.

Outside: QuantLib 1.44 `AnalyticEuropeanEngine` NPV and delta at each rebalance date (evaluation date moved day by day,
exercise date fixed), then the spec's cash-account arithmetic on those values; numpy 2.5 `polyfit` and `var` for the
effectiveness statistics. A case counts only if every output agrees within the case tolerance.

    cd oracle/python && uv run python -W ignore gen_stage_i_w4b.py
"""
import json
import math
import random
from pathlib import Path

import mpmath as mp
import numpy as np
import QuantLib as ql

import gen_stage_i_w1 as W
from gen_stage_i_w1 import fail, finite_rule, run_error, RF
from qf_oracle import common
from qf_oracle.common import Suite, note

mp.mp.dps = 50
G = "oracle/python/gen_stage_i_w4b.py"
SPEC = "specifications/08-hedging/dynamic-hedge-and-effectiveness.md"
HERE = Path(__file__).resolve().parent
BT, EF = "hedge.backtest.delta", "hedge.effectiveness"
MUT = []


def bs(typ, S, K, tau, r, q, v):
    """(value, delta) at time to expiry tau; tau = 0 gives the payoff and a delta of None (never used)."""
    S, K, r, q, v = map(mp.mpf, (S, K, r, q, v))
    if tau == 0:
        return (max(S - K, 0) if typ == "CALL" else max(K - S, 0)), None
    tau = mp.mpf(tau)
    d1 = (mp.log(S / K) + (r - q + v * v / 2) * tau) / (v * mp.sqrt(tau))
    d2 = d1 - v * mp.sqrt(tau)
    dq, dr = mp.exp(-q * tau), mp.exp(-r * tau)
    if typ == "CALL":
        return S * dq * mp.ncdf(d1) - K * dr * mp.ncdf(d2), dq * mp.ncdf(d1)
    return K * dr * mp.ncdf(-d2) - S * dq * mp.ncdf(-d1), -dq * mp.ncdf(-d1)


def stats(x, y):
    """Effectiveness statistics of hedged-item changes x and hedge changes y (I-31)."""
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    vx = sum((a - mx) ** 2 for a in x) / (n - 1)
    vy = sum((b - my) ** 2 for b in y) / (n - 1)
    cxy = sum((a - mx) * (b - my) for a, b in zip(x, y)) / (n - 1)
    z = [a + b for a, b in zip(x, y)]
    mz = sum(z) / n
    vz = sum((c - mz) ** 2 for c in z) / (n - 1)
    sx = sum(x)
    if sx == 0 or vx == 0 or vy == 0:
        fail("E_DOMAIN", "hedged item unchanged, or a series without variance")
    return {"dollar_offset": -sum(y) / sx, "regression_slope": cxy / vx, "regression_r2": cxy * cxy / (vx * vy),
            "variance_reduction": 1 - vz / vx}


def eff_ref(inp):
    x, y = inp["item_changes"], inp["hedge_changes"]
    if len(x) > 100000:
        fail("E_LIMIT")
    finite_rule(inp)
    if len(x) != len(y) or len(x) < 3:
        fail("E_INPUT", "series of unequal length or fewer than 3")
    return {k: float(v) for k, v in stats([mp.mpf(a) for a in x], [mp.mpf(b) for b in y]).items()}


def bt_ref(inp, val=None):
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
    val = val or (lambda S, tau: bs(o["type"], S, o["strike"], tau, inp["rate"], inp["dividend_yield"], inp["hedge_volatility"]))
    N = mp.mpf(inp["quantity"])
    r, q = mp.mpf(inp["rate"]), mp.mpf(inp["dividend_yield"])
    m = len(ts)
    V, D = [], []
    for t, S in zip(ts, ss):
        tau = mp.mpf(T) - mp.mpf(t)
        v_, d_ = val(S, tau)
        V.append(mp.mpf(v_))
        D.append(None if d_ is None else mp.mpf(d_))
    h = [-N * D[i] for i in range(m - 1)]  # shares held over [t_i, t_{i+1}]
    cash = -N * V[0] - h[0] * mp.mpf(ss[0])
    pi = [mp.mpf(0)]
    for i in range(m - 1):
        dt = mp.mpf(ts[i + 1]) - mp.mpf(ts[i])
        cash = cash * mp.exp(r * dt) + h[i] * mp.mpf(ss[i]) * (mp.exp(q * dt) - 1)  # interest, then dividends on the shares held
        pi.append(N * V[i + 1] + h[i] * mp.mpf(ss[i + 1]) + cash)
        if i + 1 < m - 1:
            cash -= (h[i + 1] - h[i]) * mp.mpf(ss[i + 1])  # self-financing rebalance
    item = [N * (V[i + 1] - V[i]) for i in range(m - 1)]
    hedge = [(pi[i + 1] - pi[i]) - item[i] for i in range(m - 1)]
    st = stats(item, hedge)
    return {"option_values": [float(v) for v in V], "shares": [float(v) for v in h], "portfolio_values": [float(v) for v in pi],
            "final_pnl": float(pi[-1]), **{k: float(v) for k, v in st.items()}}


def ql_val(inp):
    o = inp["option"]
    dc, d0 = ql.Actual365Fixed(), ql.Date(11, 11, 2026)
    Td = round(o["expiry_years"] * 365)
    assert abs(Td - o["expiry_years"] * 365) < 1e-9

    def f(S, tau):
        tau = float(tau)
        days = round(tau * 365)
        assert abs(days - tau * 365) < 1e-6
        if days == 0:
            return (max(S - o["strike"], 0.0) if o["type"] == "CALL" else max(o["strike"] - S, 0.0)), None
        today = d0 + (Td - days)
        ql.Settings.instance().evaluationDate = today
        proc = ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(S)), ql.YieldTermStructureHandle(ql.FlatForward(today, inp["dividend_yield"], dc, ql.Continuous)),
                                            ql.YieldTermStructureHandle(ql.FlatForward(today, inp["rate"], dc, ql.Continuous)),
                                            ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, ql.NullCalendar(), inp["hedge_volatility"], dc)))
        op = ql.EuropeanOption(ql.PlainVanillaPayoff(ql.Option.Call if o["type"] == "CALL" else ql.Option.Put, o["strike"]), ql.EuropeanExercise(d0 + Td))
        op.setPricingEngine(ql.AnalyticEuropeanEngine(proc))
        return op.NPV(), op.delta()
    return f


def close_all(a, b, absl, rel):
    if isinstance(b, list):
        return all(close_all(x, y, absl, rel) for x, y in zip(a, b))
    return abs(a - b) <= absl + rel * abs(b)


def path(seed, n, days_step, S0, vol, drift=0.0):
    rnd = random.Random(seed)
    ts, ss = [0.0], [S0]
    for i in range(n):
        dt = days_step / 365
        ss.append(round(ss[-1] * math.exp((drift - vol * vol / 2) * dt + vol * math.sqrt(dt) * rnd.gauss(0, 1)), 4))
        ts.append((i + 1) * days_step / 365)
    return ts, ss


def bt_suite():
    s = Suite("hedgebt_i", SPEC, G)
    call = {"type": "CALL", "strike": 100.0, "expiry_years": 63 / 365}
    put = {"type": "PUT", "strike": 95.0, "expiry_years": 63 / 365}
    base = dict(rate=0.03, dividend_yield=0.01, hedge_volatility=0.20, quantity=-100.0)
    t1, s1 = path(20261111, 63, 1, 100.0, 0.20)
    t2, s2 = path(20261112, 21, 3, 100.0, 0.35)
    t3, s3 = path(20261113, 9, 7, 100.0, 0.20)
    t4, s4 = path(20261114, 30, 1, 100.0, 0.10, drift=0.5)
    cases = [
        ("short call, daily rebalancing to expiry", dict(base, option=call, times=t1, spots=s1)),
        ("short call, realised vol 35% against hedge vol 20% (every 3 days)", dict(base, option=call, times=t2, spots=s2)),
        ("short call, weekly rebalancing", dict(base, option=call, times=t3, spots=s3)),
        ("long put, daily, stopped 33 days before expiry", dict(base, option=put, quantity=50.0, times=t4, spots=s4)),
        ("short put, daily to expiry", dict(base, option=put, times=t1, spots=s1)),
        ("zero rates and dividends", dict(base, rate=0.0, dividend_yield=0.0, option=call, times=t3, spots=s3)),
        ("hedge volatility above the realised", dict(base, hedge_volatility=0.30, option=call, times=t1, spots=s1)),
    ]
    n_out = 0
    for desc, inp in cases:
        out = bt_ref(inp)
        q = bt_ref(inp, ql_val(inp))
        lim = {"absolute": 1e-9, "relative": 1e-9, "reason": "a running cash account over up to 63 steps; option values up to 1e3 per position"}
        ok = all(close_all(q[k], out[k], lim["absolute"], lim["relative"]) for k in out)
        n_out += ok
        if not ok:
            note(f"  hedgebt not counted: {desc}")
        s.add(BT, inp, out, cls=RF, limit=lim, verified=["mpmath-50"] + (["quantlib-1.44-analytic-european-daily"] if ok else []), tags=["hedge", "backtest"], description=desc)
    o = {c["description"]: c["expected"]["outputs"] for c in s.cases}
    d = o["short call, daily rebalancing to expiry"]
    w = o["short call, weekly rebalancing"]
    note(f"  daily: offset {d['dollar_offset']:.4f}, R2 {d['regression_r2']:.4f}; weekly: offset {w['dollar_offset']:.4f}, R2 {w['regression_r2']:.4f}")
    assert d["regression_r2"] > 0.8, "a daily delta hedge must track the option"
    # mutant: dividends on the shares left out of the cash account
    inp = cases[0][1]

    def no_div(i):
        return bt_ref(dict(i, dividend_yield=0.0), lambda S, tau: bs("CALL", S, 100.0, tau, i["rate"], i["dividend_yield"], i["hedge_volatility"]))
    gap = abs(no_div(inp)["final_pnl"] - d["final_pnl"])
    assert gap > 1e-6
    MUT.append(("dividends on the hedge shares left out", gap))
    e = dict(base, option=call, times=t3, spots=s3)
    errs = [
        (dict(e, times=[0.01] + t3[1:]), "E_INPUT", "path not starting at 0"),
        (dict(e, times=t3[:3] + [t3[2]] + t3[4:]), "E_INPUT", "times not increasing"),
        (dict(e, spots=s3[:-1]), "E_INPUT", "spots shorter than times"),
        (dict(e, times=t3[:3], spots=s3[:3]), "E_INPUT", "three points (at least 4)"),
        (dict(e, option=dict(call, expiry_years=56 / 365)), "E_INPUT", "path beyond expiry"),
        (dict(e, spots=[100.0, 0.0] + s3[2:]), "E_DOMAIN", "zero spot"),
        (dict(e, hedge_volatility=0.0), "E_DOMAIN", "zero hedge volatility"),
        (dict(e, quantity=0.0), "E_DOMAIN", "zero quantity: the hedged item never changes"),
    ]
    for inp, code, desc in errs:
        run_error(s, BT, bt_ref, inp, code, desc, ["hedge", "backtest"])
    return s, n_out, "QuantLib 1.44 AnalyticEuropeanEngine NPV and delta on each date (evaluation date moved, exercise fixed), then the spec's cash-account arithmetic; every output within the case limit"


def eff_suite():
    s = Suite("hedgeeff_i", SPEC, G)
    rnd = random.Random(20261115)
    x = [round(rnd.gauss(0, 1000), 2) for _ in range(24)]
    y_good = [round(-0.97 * a + rnd.gauss(0, 60), 2) for a in x]
    y_poor = [round(-0.6 * a + rnd.gauss(0, 500), 2) for a in x]
    cases = [
        ("a close hedge (offset near 1, R2 near 1)", dict(item_changes=x, hedge_changes=y_good)),
        ("a poor hedge", dict(item_changes=x, hedge_changes=y_poor)),
        ("perfect hedge: changes cancel", dict(item_changes=[100.0, -50.0, 30.0, -20.0], hedge_changes=[-100.0, 50.0, -30.0, 20.0])),
        ("over-hedge by a quarter", dict(item_changes=[100.0, -50.0, 30.0, -20.0], hedge_changes=[-125.0, 62.5, -37.5, 25.0])),
        ("three observations", dict(item_changes=[10.0, -4.0, 7.0], hedge_changes=[-9.0, 5.0, -6.5])),
    ]
    n_out = 0
    for desc, inp in cases:
        out = eff_ref(inp)
        xa, ya = np.array(inp["item_changes"]), np.array(inp["hedge_changes"])
        slope = np.polyfit(xa, ya, 1)[0]
        r2 = np.corrcoef(xa, ya)[0, 1] ** 2
        vr = 1 - np.var(xa + ya, ddof=1) / np.var(xa, ddof=1)
        lib = {"dollar_offset": -ya.sum() / xa.sum(), "regression_slope": slope, "regression_r2": r2, "variance_reduction": vr}
        ok = all(abs(lib[k] - out[k]) <= 1e-10 + 1e-10 * abs(out[k]) for k in out)
        n_out += ok
        if not ok:
            note(f"  hedgeeff not counted: {desc}")
        s.add(EF, inp, out, cls=RF, verified=["mpmath-50"] + (["numpy-2.5-polyfit-corrcoef-var"] if ok else []), tags=["hedge", "effectiveness"], description=desc)
    o = s.cases[3]["expected"]["outputs"]
    assert abs(o["dollar_offset"] - 1.25) < 1e-15 and abs(o["regression_slope"] + 1.25) < 1e-15
    errs = [
        (dict(item_changes=[1.0, 2.0, 3.0], hedge_changes=[1.0, 2.0]), "E_INPUT", "unequal lengths"),
        (dict(item_changes=[1.0, 2.0], hedge_changes=[-1.0, -2.0]), "E_INPUT", "two observations"),
        (dict(item_changes=[1.0, -1.0, 2.0, -2.0], hedge_changes=[-1.0, 1.0, -2.0, 2.5]), "E_DOMAIN", "hedged item sums to zero"),
        (dict(item_changes=[1.0, 1.0, 1.0], hedge_changes=[-1.0, -0.5, -1.2]), "E_DOMAIN", "hedged item without variance"),
        (dict(item_changes=[1.0, 2.0, 3.0], hedge_changes=[-1.0, -1.0, -1.0]), "E_DOMAIN", "hedge without variance"),
    ]
    for inp, code, desc in errs:
        run_error(s, EF, eff_ref, inp, code, desc, ["hedge", "effectiveness"])
    return s, n_out, "numpy 2.5 polyfit (slope), corrcoef (R2), var ddof=1 (variance reduction) and sums (dollar offset); every output within root_finding"


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / W.FOLDER
    reg_p = HERE.parent / "outside_register_i.json"
    reg = json.loads(reg_p.read_text(encoding="utf-8"))
    for s, n_out, rule in (bt_suite(), eff_suite()):
        for c in s.cases:
            c["tags"].append("synthetic")
        s.write()
        reg[s.name] = {"counted": n_out, "total": len(s.cases), "rule": rule}
        note(f"{s.name}: {len(s.cases)} cases, outside {n_out}")
    common.GOLDEN = keep
    suites = {k: v for k, v in reg.items() if not k.startswith("_")}
    cnt, tot = sum(v["counted"] for v in suites.values()), sum(v["total"] for v in suites.values())
    reg["_stage"] = {"counted": cnt, "total": tot, "share": round(cnt / tot, 4), "floor": 0.60,
                     "note": "Stage I so far, error cases in the denominator (ruling I-2); the floor applies at release"}
    reg_p.write_text(json.dumps(reg, indent=1) + "\n", encoding="utf-8", newline="\n")
    note(f"stage I outside so far: {cnt} of {tot} = {100 * cnt / tot:.1f}%")
    for m_, g in MUT:
        note(f"  mutant caught: {m_} (gap {g:.3e})")


if __name__ == "__main__":
    main()
