"""Stage F wave 3: F5 book (trade and position lifecycle with fixings, expiry, default and roll; end-of-day marks with
data fallback and independent price verification) and use case 4 (factor attribution).

Lifecycle goldens are replayed in exact rational arithmetic (fractions); attribution at 40 digits (mpmath). Each suite
stops if its tolerance would let a named wrong convention through (`caught`).

    cd oracle/python && uv run python -W ignore gen_stage_f_w3.py
"""
import math
from datetime import date, timedelta
from fractions import Fraction as Fr

import mpmath as mp
import numpy as np

from qf_oracle import common
from qf_oracle.common import Suite, note
from qf_oracle.rng import Xo, ppnd16

mp.mp.dps = 40
G = "oracle/python/gen_stage_f_w3.py"
E, A, IP = "date_and_convention", "simple_analytic", "interpolation"
MUTANTS = []
SEED = 20261109
f = float


def write(s):
    keep = common.GOLDEN
    for c in s.cases:
        if "synthetic" not in c["tags"]:
            c["tags"].append("synthetic")
    common.GOLDEN = keep.parent / "stage_f"
    s.write()
    common.GOLDEN = keep


def caught(suite, name, g, tol):
    assert g > tol, f"{suite}: mutant '{name}' is not caught: gap {g:.3e}, tolerance {tol:.3e}"
    MUTANTS.append((suite, name, g))


# ===================================================================================== lifecycle
class Err(Exception):
    pass


def apply_events(positions, events, method="AVERAGE"):
    pos = {p["instrument"]: [Fr(p["quantity"]), Fr(p["average_cost"])] for p in positions}
    realized, fix, closed, last = {}, {}, set(), None

    def trade(ins, dq, px):
        if dq == 0:
            raise Err("E_DOMAIN")
        q, avg = pos.get(ins, [Fr(0), Fr(0)])
        if q == 0 or (q > 0) == (dq > 0):
            nq = q + dq
            avg = (q * avg + dq * px) / nq if method == "AVERAGE" else avg
            pos[ins] = [nq, avg]
            return
        sgn = 1 if q > 0 else -1
        cl = min(abs(dq), abs(q))
        realized[ins] = realized.get(ins, Fr(0)) + sgn * cl * (px - avg)
        nq = q + dq
        if nq == 0:
            del pos[ins]
        elif (nq > 0) == (q > 0):
            pos[ins] = [nq, avg]
        else:
            pos[ins] = [nq, px]
        realized.setdefault(ins, Fr(0))

    for ev in events:
        d = date.fromisoformat(ev["date"])
        if last and d < last:
            raise Err("E_INPUT")
        last = d
        t = ev["type"]
        if t == "TRADE":
            if ev["instrument"] in closed:
                raise Err("E_INPUT")
            trade(ev["instrument"], Fr(ev["quantity"]), Fr(ev["price"]))
        elif t == "FIXING":
            k = (ev["index"], ev["date"])
            if k in fix:
                raise Err("E_INPUT")
            fix[k] = ev["value"]
        elif t in ("EXPIRY", "DEFAULT"):
            ins = ev["instrument"]
            if ins not in pos:
                raise Err("E_INPUT")
            px = Fr(ev["settlement_price"] if t == "EXPIRY" else ev["recovery_price"])
            trade(ins, -pos[ins][0], px)
            closed.add(ins)
        elif t == "ROLL":
            a, b = ev["from"], ev["to"]
            if a not in pos or b in closed:
                raise Err("E_INPUT")
            q = pos[a][0]
            trade(a, -q, Fr(ev["from_price"]))
            closed.add(a)
            trade(b, q, Fr(ev["to_price"]))
        else:
            raise Err("E_SCHEMA")
    return {"positions": [{"instrument": k, "quantity": f(v[0]), "average_cost": f(v[1])} for k, v in sorted(pos.items())],
            "realized_pnl": [{"instrument": k, "pnl": f(v)} for k, v in sorted(realized.items())],
            "total_realized": f(sum(realized.values(), Fr(0))),
            "fixings": [{"index": k[0], "date": k[1], "value": v} for k, v in sorted(fix.items())]}


def lifecycle(s):
    op = "book.lifecycle.apply"
    T = lambda d, i, q, p: {"date": d, "type": "TRADE", "instrument": i, "quantity": q, "price": p}  # noqa: E731
    hand = [
        ("buy, add, partial sell", [], [T("2026-11-02", "UST10", 100.0, 99.5), T("2026-11-03", "UST10", 50.0, 100.25), T("2026-11-04", "UST10", -120.0, 100.5)]),
        ("short then cover through zero", [], [T("2026-11-02", "SR3Z6", -10.0, 95.80), T("2026-11-03", "SR3Z6", 15.0, 95.70)]),
        ("opening position, close exactly", [{"instrument": "AAPL", "quantity": 200.0, "average_cost": 180.0}], [T("2026-11-05", "AAPL", -200.0, 190.5)]),
        ("fixings are recorded, not traded", [], [{"date": "2026-11-02", "type": "FIXING", "index": "SOFR", "value": 0.0431},
                                                   {"date": "2026-11-02", "type": "FIXING", "index": "ESTR", "value": 0.0193},
                                                   {"date": "2026-11-03", "type": "FIXING", "index": "SOFR", "value": 0.0430}]),
        ("option expiry at settlement", [{"instrument": "SPX-C-6000", "quantity": 5.0, "average_cost": 42.0}],
         [{"date": "2026-12-18", "type": "EXPIRY", "instrument": "SPX-C-6000", "settlement_price": 57.25}]),
        ("default at recovery", [{"instrument": "BOND-X", "quantity": 1000.0, "average_cost": 0.97}],
         [{"date": "2026-11-20", "type": "DEFAULT", "instrument": "BOND-X", "recovery_price": 0.38}]),
        ("futures roll", [{"instrument": "SR3Z6", "quantity": -20.0, "average_cost": 95.9}],
         [{"date": "2026-12-10", "type": "ROLL", "from": "SR3Z6", "to": "SR3H7", "from_price": 95.82, "to_price": 96.01}]),
    ]
    for d, p0, ev in hand:
        out = apply_events(p0, ev)
        s.add(op, {"positions": p0, "events": ev}, out, cls=A, output_classes={"fixings": E}, verified=["exact rational replay"],
              tags=["lifecycle", "stage-f"], description=d)
        if d.startswith("buy, add"):
            caught("lifecycle", "FIFO instead of average cost", abs(100.25 - out["positions"][0]["average_cost"]), 1e-10)
            caught("lifecycle", "realized on the sale price only", abs(120 * 100.5 - out["total_realized"]), 1e-10)
    g = Xo(SEED, stream=7)
    for k in range(10):
        ins = ["A", "B", "C"][: 1 + k % 3]
        ev, d0 = [], date(2026, 11, 2)
        for j in range(20 + 5 * k):
            i = ins[int(g.uniform() * len(ins))]
            q = float(round((g.uniform() - 0.5) * 200)) or 1.0
            px = round(100 + 10 * ppnd16(g.uniform()), 2)
            ev.append(T((d0 + timedelta(days=j // 3)).isoformat(), i, q, px))
        out = apply_events([], ev)
        s.add(op, {"positions": [], "events": ev}, out, cls=A, output_classes={"fixings": E}, verified=["exact rational replay"],
              tags=["lifecycle", "stage-f"], description=f"random sequence {k + 1}: {len(ev)} trades on {len(ins)} instruments")
    bad = [("events out of date order", [], [T("2026-11-03", "A", 1.0, 1.0), T("2026-11-02", "A", 1.0, 1.0)], "E_INPUT"),
           ("trade after expiry", [{"instrument": "O", "quantity": 1.0, "average_cost": 1.0}],
            [{"date": "2026-11-02", "type": "EXPIRY", "instrument": "O", "settlement_price": 2.0}, T("2026-11-03", "O", 1.0, 1.0)], "E_INPUT"),
           ("expiry of an instrument not held", [], [{"date": "2026-11-02", "type": "EXPIRY", "instrument": "O", "settlement_price": 2.0}], "E_INPUT"),
           ("zero quantity", [], [T("2026-11-02", "A", 0.0, 1.0)], "E_DOMAIN"),
           ("duplicate fixing", [], [{"date": "2026-11-02", "type": "FIXING", "index": "SOFR", "value": 0.04}] * 2, "E_INPUT"),
           ("unknown event type", [], [{"date": "2026-11-02", "type": "SPLIT", "instrument": "A"}], "E_SCHEMA")]
    for d, p0, ev, code in bad:
        try:
            apply_events(p0, ev)
            raise AssertionError(d)
        except Err as e:
            assert str(e) == code, (d, e)
        s.add(op, {"positions": p0, "events": ev}, error=code, cls=E, tags=["invalid", "stage-f"], description=d)


# ===================================================================================== marks
def resolve(inp):
    asof = date.fromisoformat(inp["as_of"])
    out = []
    ipv = {x["instrument"]: x["price"] for x in inp.get("ipv", [])}
    for ins in inp["instruments"]:
        mark = None
        for k, src in enumerate(inp["sources"]):
            q = [x for x in src["quotes"] if x["instrument"] == ins and x["date"] == inp["as_of"]]
            if q:
                mark = (q[0]["price"], src["name"], "PRIMARY" if k == 0 else "FALLBACK", 0)
                break
        if mark is None:
            best = None
            for k, src in enumerate(inp["sources"]):
                for x in src["quotes"]:
                    d = date.fromisoformat(x["date"])
                    age = (asof - d).days
                    if x["instrument"] == ins and 0 < age <= inp["max_age_days"] and (best is None or age < best[3]):
                        best = (x["price"], src["name"], "STALE", age)
            mark = best
        row = {"instrument": ins, "price": None, "source": None, "status": "MISSING", "age_days": None, "ipv_diff": None, "ipv_breach": False}
        if mark:
            row.update(price=mark[0], source=mark[1], status=mark[2], age_days=mark[3])
            if ins in ipv:
                dlt = (Fr(mark[0]) - Fr(ipv[ins])) / Fr(ipv[ins])
                row["ipv_diff"] = f(dlt)
                row["ipv_breach"] = abs(dlt) > Fr(inp["ipv_threshold"])
        out.append(row)
    return {"marks": out}


def marks(s):
    op = "book.marks.resolve"
    base = {"as_of": "2026-11-10", "instruments": ["UST10", "BUND10", "SPX", "ILLIQ"], "max_age_days": 3, "ipv_threshold": 0.005,
            "sources": [{"name": "VENDOR_A", "quotes": [{"instrument": "UST10", "date": "2026-11-10", "price": 99.75},
                                                        {"instrument": "SPX", "date": "2026-11-07", "price": 6012.5}]},
                        {"name": "VENDOR_B", "quotes": [{"instrument": "BUND10", "date": "2026-11-10", "price": 131.2},
                                                        {"instrument": "UST10", "date": "2026-11-10", "price": 99.80},
                                                        {"instrument": "SPX", "date": "2026-11-09", "price": 6020.0},
                                                        {"instrument": "ILLIQ", "date": "2026-11-01", "price": 88.0}]}],
            "ipv": [{"instrument": "UST10", "price": 99.70}, {"instrument": "BUND10", "price": 130.0}]}
    variants = [("primary, fallback, stale and missing", base),
                ("stale limit widened: the old quote is used", dict(base, max_age_days=10)),
                ("tighter IPV threshold", dict(base, ipv_threshold=0.0001)),
                ("no IPV prices", {k: v for k, v in base.items() if k != "ipv"} | {"ipv": []}),
                ("one source only", dict(base, sources=base["sources"][:1])),
                ("sources reversed", dict(base, sources=base["sources"][::-1]))]
    for d, inp in variants:
        out = resolve(inp)
        s.add(op, inp, out, cls=A, output_classes={"marks": A}, verified=["hand rule replay"], tags=["marks", "stage-f"], description=d)
    for d, inp, code in (("negative stale limit", dict(base, max_age_days=-1), "E_DOMAIN"), ("duplicate source names", dict(base, sources=base["sources"][:1] * 2), "E_INPUT"),
                         ("IPV price 0", dict(base, ipv=[{"instrument": "UST10", "price": 0.0}]), "E_DOMAIN")):
        s.add(op, inp, error=code, cls=E, tags=["invalid", "stage-f"], description=d)


# ===================================================================================== use case 4
def attribution_ref(r, F):
    T, K = len(r), len(F[0])
    X = mp.matrix([[1] + [mp.mpf(v) for v in row] for row in F])
    y = mp.matrix([mp.mpf(v) for v in r])
    XtX = X.T * X
    inv = mp.inverse(XtX)
    b = inv * (X.T * y)
    res = y - X * b
    ssr = mp.fsum(v * v for v in res)
    ybar = mp.fsum(y) / T
    sst = mp.fsum((v - ybar) ** 2 for v in y)
    s2 = ssr / (T - K - 1)
    fbar = [mp.fsum(mp.mpf(row[k]) for row in F) / T for k in range(K)]
    return {"alpha": f(b[0]), "betas": [f(b[k + 1]) for k in range(K)], "r_squared": f(1 - ssr / sst),
            "contributions": [f(b[k + 1] * fbar[k]) for k in range(K)], "mean_return": f(ybar),
            "residual_vol": f(mp.sqrt(s2)), "beta_se": [f(mp.sqrt(s2 * inv[k + 1, k + 1])) for k in range(K)]}


def usecase4(s):
    op = "usecase.factor_attribution"
    g = Xo(SEED, stream=8)
    names_all = ["MKT", "SMB", "HML", "MOM", "RATES", "CREDIT"]
    for T, K in [(60, 1), (60, 3), (120, 3), (250, 4), (36, 2), (500, 6), (24, 3), (120, 5)] * 3:
        beta = [2 * g.uniform() - 0.5 for _ in range(K)]
        F = [[round(0.01 * ppnd16(g.uniform()) * (2 if k == 0 else 1), 6) for k in range(K)] for _ in range(T)]
        r = [round(0.0005 + sum(b * x for b, x in zip(beta, row)) + 0.004 * ppnd16(g.uniform()), 6) for row in F]
        out = attribution_ref(r, F)
        inp = {"portfolio_returns": r, "factor_returns": F, "factor_names": names_all[:K]}
        s.add(op, inp, out, cls=IP, verified=["mpmath 40-digit normal equations"], tags=["usecase-4", "stage-f"], description=f"T = {T}, {K} factors")
        if T == 60 and K == 3:
            Xn = np.array(F)
            b_noint = np.linalg.lstsq(Xn, np.array(r), rcond=None)[0]
            caught("uc4", "regression without intercept", float(np.max(np.abs(b_noint - out["betas"]))), 1e-8)
            caught("uc4", "residual vol with divisor T", abs(out["residual_vol"] * math.sqrt((T - K - 1) / T) - out["residual_vol"]), 1e-8 * out["residual_vol"])
    for d, inp, code in (("too few observations", {"portfolio_returns": [0.01, 0.02], "factor_returns": [[0.01], [0.02]], "factor_names": ["MKT"]}, "E_INPUT"),
                         ("collinear factors", {"portfolio_returns": [0.01, 0.02, -0.01, 0.0], "factor_returns": [[0.01, 0.02], [0.02, 0.04], [-0.01, -0.02], [0.0, 0.0]],
                                                "factor_names": ["A", "B"]}, "E_DOMAIN"),
                         ("names and columns differ", {"portfolio_returns": [0.01] * 5, "factor_returns": [[0.01]] * 5, "factor_names": ["A", "B"]}, "E_INPUT")):
        s.add(op, inp, error=code, cls=E, tags=["invalid", "stage-f"], description=d)


def main():
    s = Suite("book_f", "specifications/07-portfolio/book-lifecycle.md", G)
    lifecycle(s)
    marks(s)
    write(s)
    u = Suite("uc4_f", "specifications/04-pricing/use-cases.md", G)
    usecase4(u)
    write(u)
    for m in MUTANTS:
        note(f"caught {m[0]}: {m[1]} (gap {m[2]:.3e})")


if __name__ == "__main__":
    main()
