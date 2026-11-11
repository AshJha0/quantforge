"""Stage I wave 5: outside-checked value cases for the I-2 floor (program/STAGE_I_HANDOVER.md, "WAVE 5 READY"; ruling I-55).

New suites `<suite>5_i` of existing operations; the earlier suites and generators are untouched, so they stay byte-
reproducible. Inputs are drawn from seeded generators (seed per suite below). A draw is rejected only for reasons fixed
before any outside check runs: it breaks a domain rule, an I-3 decision falls within the factor-1e3 margin (the reference
asserts it), or the QP is infeasible. A draw is never rejected because the outside check disagrees: every accepted draw is
written, and the register counts only those where the library agrees within the case tolerance (I-2).

Goldens come from the same reference functions as waves 1 and 2 (50-digit mpmath); outside libraries are named per case:
QuantLib 1.44 (AnalyticEuropeanEngine, AnalyticEuropeanMargrabeEngine, BlackCalculator), numpy 2.5, scipy 1.18.

    cd oracle/python && uv run python -W ignore gen_stage_i_w5.py
"""
import json
import random
from pathlib import Path

import numpy as np

import gen_stage_i_w1 as W
import gen_stage_i_w2 as W2
import gen_stage_i_w4b as B
from qf_oracle import common
from qf_oracle.common import Suite, note

G = "oracle/python/gen_stage_i_w5.py"
HERE = Path(__file__).resolve().parent
RF = "root_finding"
SEEDS = {"hedgegreeks5_i": 202611115, "hedgecorr5_i": 202611116, "hedgemv5_i": 202611117, "hedgeeff5_i": 202611118, "hedgeqp5_i": 202611119}
COUNTS = {"hedgegreeks5_i": 50, "hedgecorr5_i": 35, "hedgemv5_i": 30, "hedgeeff5_i": 20, "hedgeqp5_i": 30}
REJECT = {}


def r4(x):
    return round(x, 4)


def accept(name, fn):
    """Draw until fn returns a case; a draw that raises QfErr or AssertionError (domain, margin, feasibility) is rejected."""
    while True:
        try:
            return fn()
        except (W.QfErr, AssertionError, ZeroDivisionError):
            REJECT[name] = REJECT.get(name, 0) + 1


def greeks(rnd):
    s = Suite("hedgegreeks5_i", "specifications/08-hedging/hedge-solvers.md", G)
    n_out = 0
    for i in range(COUNTS[s.name]):
        def draw():
            S = r4(rnd.uniform(50, 200))
            mk = dict(spot=S, rate=r4(rnd.uniform(-0.01, 0.06)), dividend_yield=r4(rnd.uniform(0.0, 0.04)), volatility=r4(rnd.uniform(0.1, 0.6)))
            opt = lambda: {"instrument": rnd.choice(["CALL", "PUT"]), "strike": r4(S * rnd.uniform(0.7, 1.3)), "expiry_years": rnd.randint(30, 730) / 365}  # noqa: E731
            port = [dict(opt(), quantity=r4(rnd.choice([-1, 1]) * rnd.uniform(10, 1000))) for _ in range(rnd.randint(1, 4))]
            tg = rnd.sample(["DELTA", "GAMMA", "VEGA"], rnd.randint(1, 3))
            hed = [{"instrument": "UNDERLYING"} if t == "DELTA" else opt() for t in tg]
            inp = dict(mk, portfolio=port, hedges=hed, targets=tg)
            return inp, W.gr_ref(inp)
        inp, out = accept(s.name, draw)
        scale = max(abs(v) for v in out["greeks_before"].values())
        lim = {"absolute": 1e-10 * max(1.0, scale), "relative": 1e-10, "reason": "targeted Greeks after hedging are zero up to rounding of the before value"}
        qg = [W.ql_greeks(inp, h) for h in inp["hedges"]]
        Gq = np.array([[g[t] for g in qg] for t in inp["targets"]])
        bq = {t: sum(p["quantity"] * W.ql_greeks(inp, p)[t] for p in inp["portfolio"]) for t in W.GREEKS}
        qq = np.linalg.solve(Gq, -np.array([bq[t] for t in inp["targets"]]))
        ok = all(abs(a - b) <= 1e-10 + 1e-10 * abs(b) for a, b in zip(qq, out["quantities"])) and \
            all(abs(bq[t] - out["greeks_before"][t.lower()]) <= lim["absolute"] + 1e-10 * abs(bq[t]) for t in W.GREEKS)
        n_out += ok
        s.add(W.GR, inp, out, cls=RF, limit=lim, verified=["mpmath-50"] + (["quantlib-1.44-analytic-european", "numpy-2.5-solve"] if ok else []),
              tags=["hedge", "greeks", "wave5"], description=f"seeded draw {i + 1} ({'+'.join(inp['targets'])})")
    return s, n_out, "QuantLib 1.44 AnalyticEuropeanEngine Greeks and numpy solve, as hedgegreeks_i"


def corr(rnd):
    s = Suite("hedgecorr5_i", "specifications/08-hedging/credit-and-correlation-hedges.md", G)
    n_out = 0
    pick = {"CORRELATION": None, "VEGA_1": "CALL_1", "VEGA_2": "PUT_2", "DELTA_1": "UNDERLYING_1", "DELTA_2": "UNDERLYING_2"}
    for i in range(COUNTS[s.name]):
        def draw():
            mk = dict(spot1=r4(rnd.uniform(50, 150)), spot2=r4(rnd.uniform(50, 150)), rate=r4(rnd.uniform(0.0, 0.05)), yield1=r4(rnd.uniform(0, 0.03)),
                      yield2=r4(rnd.uniform(0, 0.03)), vol1=r4(rnd.uniform(0.1, 0.5)), vol2=r4(rnd.uniform(0.1, 0.5)), correlation=r4(rnd.uniform(-0.9, 0.95)))
            X = lambda: {"instrument": "EXCHANGE", "quantity1": 1.0, "quantity2": float(rnd.choice([1, 1, 2])), "expiry_years": rnd.randint(30, 730) / 365}  # noqa: E731

            def inst(kind):
                if kind is None:
                    return X()
                if kind.startswith("UNDER"):
                    return {"instrument": kind}
                k = kind[-1]
                return {"instrument": kind, "strike": r4(mk[f"spot{k}"] * rnd.uniform(0.8, 1.2)), "expiry_years": rnd.randint(30, 730) / 365}
            book = [dict(X(), quantity=r4(rnd.choice([-1, 1]) * rnd.uniform(50, 1000))) for _ in range(rnd.randint(1, 3))]
            tg = ["CORRELATION"] + rnd.sample(["VEGA_1", "VEGA_2", "DELTA_1", "DELTA_2"], rnd.randint(0, 4))
            inp = dict(mk, book=book, hedges=[inst(pick[t]) for t in tg], targets=tg)
            return inp, W2.corr_ref(inp)
        inp, out = accept(s.name, draw)
        scale = max(abs(v) for v in out["greeks_before"].values())
        lim = {"absolute": 1e-10 * max(1.0, scale), "relative": 1e-10, "reason": "targeted Greeks after hedging are zero up to rounding of the before value"}
        qg = [W2.ql_margrabe(inp, h) for h in inp["hedges"]]
        Gq = np.array([[g[t] for g in qg] for t in inp["targets"]])
        bq = {t: sum(p["quantity"] * W2.ql_margrabe(inp, p)[t] for p in inp["book"]) for t in W2.CG}
        qq = np.linalg.solve(Gq, -np.array([bq[t] for t in inp["targets"]]))
        ok = all(abs(a - b) <= 1e-10 * max(1, abs(b)) for a, b in zip(qq, out["quantities"])) and \
            all(abs(bq[t] - out["greeks_before"][W2.OUTK[t]]) <= lim["absolute"] + 1e-10 * abs(bq[t]) for t in W2.CG)
        n_out += ok
        s.add(W2.CO, inp, out, cls=RF, limit=lim, verified=["mpmath-50"] + (["quantlib-1.44-margrabe", "numpy-2.5-solve"] if ok else []),
              tags=["hedge", "correlation", "wave5"], description=f"seeded draw {i + 1} ({'+'.join(inp['targets'])})")
    return s, n_out, "QuantLib 1.44 Margrabe engine, BlackCalculator.vega and AnalyticEuropeanEngine, numpy solve, as hedgecorr_i"


def minvar(rnd):
    s = Suite("hedgemv5_i", "specifications/08-hedging/hedge-solvers.md", G)
    n_out = 0
    for i in range(COUNTS[s.name]):
        series = i % 2 == 1

        def draw():
            k = rnd.randint(1, 3)
            if not series:
                L = [[r4(rnd.gauss(0, 0.1)) for _ in range(k + 2)] for _ in range(k + 1)]
                C = [[sum(a * b for a, b in zip(L[p], L[q])) + (1e-4 if p == q else 0.0) for q in range(k + 1)] for p in range(k + 1)]
                inp = dict(covariance=C)
            else:
                T = rnd.randint(k + 8, 60)
                f = [[rnd.gauss(0, 0.01) for _ in range(T)] for _ in range(k)]
                ex = [r4(sum(rnd.uniform(0.3, 1.2) * f[j][t] for j in range(k)) + rnd.gauss(0, 0.004)) for t in range(T)]
                inp = dict(exposure_changes=ex, hedge_changes=[[r4(v) for v in row] for row in f])
            return inp, W.mv_ref(inp)
        inp, out = accept(s.name, draw)
        if "covariance" in inp:
            Cn = np.array(inp["covariance"])
            hl, lib = -np.linalg.solve(Cn[1:, 1:], Cn[1:, 0]), "numpy-2.5-solve"
        else:
            Xh = np.column_stack([np.ones(len(inp["exposure_changes"]))] + [np.array(h) for h in inp["hedge_changes"]])
            hl, lib = -np.linalg.lstsq(Xh, np.array(inp["exposure_changes"]), rcond=None)[0][1:], "numpy-2.5-lstsq-ols"
        ok = all(abs(p - q) <= 1e-10 + 1e-10 * abs(q) for p, q in zip(hl, out["hedge"]))
        n_out += ok
        s.add(W.MV, inp, out, cls=RF, verified=["mpmath-50"] + ([lib] if ok else []), tags=["hedge", "minvar", "wave5"],
              description=f"seeded draw {i + 1} ({'series' if series else 'covariance'})")
    return s, n_out, "numpy 2.5 solve (covariance) or lstsq OLS with intercept (series); hedge within root_finding, as hedgemv_i"


def eff(rnd):
    s = Suite("hedgeeff5_i", "specifications/08-hedging/dynamic-hedge-and-effectiveness.md", G)
    n_out = 0
    for i in range(COUNTS[s.name]):
        def draw():
            n = rnd.randint(5, 40)
            beta = rnd.uniform(0.5, 1.5)
            x = [round(rnd.gauss(0, 1000), 2) for _ in range(n)]
            y = [round(-beta * a + rnd.gauss(0, rnd.uniform(10, 600)), 2) for a in x]
            inp = dict(item_changes=x, hedge_changes=y)
            return inp, B.eff_ref(inp)
        inp, out = accept(s.name, draw)
        xa, ya = np.array(inp["item_changes"]), np.array(inp["hedge_changes"])
        lib = {"dollar_offset": -ya.sum() / xa.sum(), "regression_slope": np.polyfit(xa, ya, 1)[0], "regression_r2": np.corrcoef(xa, ya)[0, 1] ** 2,
               "variance_reduction": 1 - np.var(xa + ya, ddof=1) / np.var(xa, ddof=1)}
        ok = all(abs(lib[k] - out[k]) <= 1e-10 + 1e-10 * abs(out[k]) for k in out)
        n_out += ok
        s.add(B.EF, inp, out, cls=RF, verified=["mpmath-50"] + (["numpy-2.5-polyfit-corrcoef-var"] if ok else []), tags=["hedge", "effectiveness", "wave5"],
              description=f"seeded draw {i + 1} (n = {len(inp['item_changes'])})")
    return s, n_out, "numpy 2.5 polyfit, corrcoef, var(ddof=1), as hedgeeff_i"


def qp(rnd):
    s = Suite("hedgeqp5_i", "specifications/08-hedging/hedge-solvers.md", G)
    n_out = 0
    for i in range(COUNTS[s.name]):
        kind = ["plain", "ridge", "bounds", "equality"][i % 4]

        def draw():
            m, n = rnd.randint(3, 6), rnd.randint(2, 4)
            inp = dict(a=[[r4(rnd.uniform(-1, 1.5)) for _ in range(n)] for _ in range(m)], b=[r4(rnd.uniform(-3, 3)) for _ in range(m)],
                       weights=[r4(rnd.uniform(0.2, 3.0)) for _ in range(m)])
            if kind == "ridge":
                inp["ridge"] = r4(rnd.uniform(0.01, 2.0))
            if kind == "bounds":
                inp["lower"] = [r4(-rnd.uniform(0.1, 2.0)) if rnd.random() < 0.7 else None for _ in range(n)]
                inp["upper"] = [r4(rnd.uniform(0.1, 2.0)) if rnd.random() < 0.7 else None for _ in range(n)]
            if kind == "equality":
                inp["eq_matrix"] = [[1.0] * n]
                inp["eq_rhs"] = [r4(rnd.uniform(-1, 1))]
            out = W.qp_ref(inp)
            W.kkt_check(inp, out)
            return inp, out
        inp, out = accept(s.name, draw)
        xl, lib = W.qp_outside(inp, out, 1e-10)
        ok = W.agrees(xl, out, inp, 1e-10)
        n_out += ok
        s.add(W.QP, inp, out, cls=RF, output_classes={"rank": W.EX}, verified=["mpmath-50-active-set", "kkt-check"] + ([lib] if ok else []),
              tags=["hedge", "qp", "wave5"], description=f"seeded draw {i + 1} ({kind})")
    return s, n_out, "scipy 1.18 BVLS, lstsq (gelsd) or SLSQP on the same problem, as hedgeqp_i"


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / W.FOLDER
    reg_p = HERE.parent / "outside_register_i.json"
    reg = json.loads(reg_p.read_text(encoding="utf-8"))
    for fn, name in ((greeks, "hedgegreeks5_i"), (corr, "hedgecorr5_i"), (minvar, "hedgemv5_i"), (eff, "hedgeeff5_i"), (qp, "hedgeqp5_i")):
        s, n_out, rule = fn(random.Random(SEEDS[name]))
        for c in s.cases:
            c["tags"].append("synthetic")
        s.write()
        reg[s.name] = {"counted": n_out, "total": len(s.cases), "rule": rule + f"; seeded draws (seed {SEEDS[name]}), {REJECT.get(s.name, 0)} draws rejected before any outside check"}
        note(f"{s.name}: {len(s.cases)} cases, outside {n_out}, rejected draws {REJECT.get(s.name, 0)}")
    common.GOLDEN = keep
    suites = {k: v for k, v in reg.items() if not k.startswith("_")}
    cnt, tot = sum(v["counted"] for v in suites.values()), sum(v["total"] for v in suites.values())
    reg["_stage"] = {"counted": cnt, "total": tot, "share": round(cnt / tot, 4), "floor": 0.60,
                     "note": "Stage I so far, error cases in the denominator (ruling I-2); the floor applies at release"}
    reg_p.write_text(json.dumps(reg, indent=1) + "\n", encoding="utf-8", newline="\n")
    note(f"stage I outside: {cnt} of {tot} = {100 * cnt / tot:.1f}%")


if __name__ == "__main__":
    main()
