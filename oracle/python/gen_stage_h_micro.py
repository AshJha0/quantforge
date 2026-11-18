"""Stage H wave 2 microstructure goldens: estimators with planted truth (mest_h, H-4b) and venue analytics (venue_h,
H-16).

Specs: specifications/09-microstructure/micro-estimators.md and specifications/10-execution/venue-analytics.md,
"Golden cases". The Expected cells there are prose, so each case is transcribed below: the inputs in the JSON names the
specs fix ("Operation inputs and outputs", "Input and output names"), and the expected values exactly as the table
prints them (TABLE). Every value is then recomputed here with mpmath at 50 digits from the inputs and must agree with
the table to 1e-12 relative (1e-15 absolute at 0); the golden carries the mpmath value rounded once to binary64. No
value is taken from an implementation. Blind record: program/STAGE_H_BLIND_MICRO.md (venue_h-0006 post-blind,
venue_h-0008 hand only; mest_h-0006 and venue_h-0008 re-derived by hand under HR-75a). After the spec rows, one E1 case per operation (ruling F-2: NaN input, E_DOMAIN).

    cd oracle/python && uv run python -W ignore gen_stage_h_micro.py
"""
import json

import mpmath as mp

from qf_oracle import common
from qf_oracle.common import Suite, note

G = "oracle/python/gen_stage_h_micro.py"
FOLDER = "stage_h"
SPEC_M = "specifications/09-microstructure/micro-estimators.md"
SPEC_V = "specifications/10-execution/venue-analytics.md"
REC = "program/STAGE_H_BLIND_MICRO.md"
MATCH = f"blind-rederivation (DR-H2, {REC}): MATCH"
SHAPE = f"blind-rederivation (DR-H2, {REC}): SHAPE-ONLY, values identical"
MP = "mpmath 50 digits"
TOL = {"absolute": 1e-15, "relative": 1e-12}  # both specs: 1e-12 relative, an expected 0 to 1e-15 absolute
mp.mp.dps = 50
M = mp.mpf


def fz(x):
    """Round once to binary64; a residual below 1e-40 of an exact fit (HR-74) is written as 0."""
    return 0.0 if abs(x) < M("1e-40") else common.f(x)


def close(a, table):
    t = M(table)
    assert abs(a - t) <= (M("1e-15") if t == 0 else M("1e-12") * abs(t)), (a, table)


# ------------------------------------------------------------------ exact references (mpmath)

def ols_origin(x, y):
    x, y = [M(str(v)) for v in x], [M(str(v)) for v in y]
    sxx = mp.fsum(a * a for a in x)
    b = mp.fsum(a * c for a, c in zip(x, y)) / sxx
    ssr = mp.fsum((c - b * a) ** 2 for a, c in zip(x, y))
    return b, mp.sqrt(ssr / (len(x) - 1) / sxx)


def ols_slope(t, y):
    t = [M(str(v)) for v in t]
    n = len(t)
    tm, ym = mp.fsum(t) / n, mp.fsum(y) / n
    stt = mp.fsum((a - tm) ** 2 for a in t)
    sl = mp.fsum((a - tm) * (c - ym) for a, c in zip(t, y)) / stt
    ic = ym - sl * tm
    ssr = mp.fsum((c - ic - sl * a) ** 2 for a, c in zip(t, y))
    return sl, mp.sqrt(ssr / (n - 2) / stt)


def welch(p, a):
    p, a = [M(str(v)) for v in p], [M(str(v)) for v in a]

    def mv(v):
        m = mp.fsum(v) / len(v)
        return m, mp.fsum((c - m) ** 2 for c in v) / (len(v) - 1)
    mp_, vp = mv(p)
    ma, va = mv(a)
    return ma - mp_, mp.sqrt(va / len(a) + vp / len(p))


def venue_ref(inp):
    times = [M(str(m["t"])) for m in inp["mids"]]
    vals = [M(str(m["mid"])) for m in inp["mids"]]

    def mid(u):
        k = max(i for i, t in enumerate(times) if t <= u)
        return vals[k]
    marks = []
    for v in sorted({f["venue"] for f in inp["fills"]}):
        mine = [f for f in inp["fills"] if f["venue"] == v]
        sq = mp.fsum(M(str(f["quantity"])) for f in mine)
        sqp = mp.fsum(M(str(f["quantity"])) * M(str(f["price"])) for f in mine)
        for h in inp["horizons"]:
            num, tox = M(0), M(0)
            for f in mine:
                s = 1 if f["side"] == "BUY" else -1
                mv = s * (mid(M(str(f["t"])) + M(str(h))) - M(str(f["price"])))
                num += M(str(f["quantity"])) * mv
                tox += M(str(f["quantity"])) if mv < 0 else 0
            marks.append({"venue": v, "h": h, "markout": num / sq, "markout_bps": 10000 * num / sqp, "toxicity": tox / sq})
    rates = {}
    for v in sorted({o["venue"] for o in inp["orders"]}):
        rates[v] = (mp.fsum(M(str(o["filled"])) for o in inp["orders"] if o["venue"] == v)
                    / mp.fsum(M(str(o["sent"])) for o in inp["orders"] if o["venue"] == v))
    return rates, marks


# ------------------------------------------------------------------ mest_h

def pts(rows, a, b):
    return [{a: float(u), b: float(w)} for u, w in rows]


MEST = [  # case, operation, inputs, table values (field: printed value) or error code, verified_by
    ("mest_h-0001", "micro.est.arrival_rate", {"count": 12, "window": 4.0}, {"lambda": "3", "se": "0.866025403784439"}),
    ("mest_h-0002", "micro.est.arrival_rate", {"count": 12, "window": 0.0}, "E_DOMAIN"),
    ("mest_h-0003", "micro.est.cancel_rate",
     {"orders": [{"lifetime": 2.0, "outcome": "CANCEL"}, {"lifetime": 3.0, "outcome": "FILL"},
                 {"lifetime": 5.0, "outcome": "CANCEL"}]}, {"theta": "0.2", "se": "0.141421356237310"}),
    ("mest_h-0004", "micro.est.cancel_rate", {"orders": [{"lifetime": 3.0, "outcome": "FILL"}]}, "E_INPUT"),
    ("mest_h-0005", "micro.est.resilience", {"s_inf": 1.0, "points": pts([(0, 5), (1, 3), (2, 2)], "t", "s")},
     {"kappa": "0.693147180559945", "se": "0"}),
    ("mest_h-0006", "micro.est.resilience", {"s_inf": 1.0, "points": pts([(0, 5), (1, 0.5)], "t", "s")}, "E_INPUT"),
    ("mest_h-0007", "micro.est.liquidity_decay",
     {"levels": pts([(0, 800), (1, 400), (2, 200), (3, 100)], "k", "depth")}, {"alpha": "0.693147180559945", "se": "0"}),
    ("mest_h-0008", "micro.est.adverse_selection", {"x": [1.0, -1.0, 2.0], "y": [0.02, -0.01, 0.05]},
     {"lambda_as": "0.0216666666666667", "se": "0.00390867979985286"}),
    ("mest_h-0009", "micro.est.regime_impact",
     {"regimes": {"calm": {"x": [1.0, 2.0], "y": [0.01, 0.02]},
                  "stressed": {"x": [1.0, -1.0, 1.0], "y": [0.05, -0.03, 0.04]}}},
     {"calm": ("0.01", "0"), "stressed": ("0.04", "0.00577350269189626"), "ratio": "4"}),
    ("mest_h-0010", "micro.est.passive_vs_aggressive", {"passive": [-1.0, -0.5, 0.0], "aggressive": [1.0, 1.5, 2.0]},
     {"delta": "2", "se": "0.408248290463863"}),
    ("mest_h-0011", "micro.est.passive_vs_aggressive", {"passive": [-1.0], "aggressive": [1.0, 2.0]}, "E_INPUT"),
]


def mest_ref(op, inp):
    if op == "micro.est.arrival_rate":
        lam = M(inp["count"]) / M(str(inp["window"]))
        return {"lambda": lam, "se": mp.sqrt(lam / M(str(inp["window"])))}
    if op == "micro.est.cancel_rate":
        c = sum(o["outcome"] == "CANCEL" for o in inp["orders"])
        th = M(c) / mp.fsum(M(str(o["lifetime"])) for o in inp["orders"])
        return {"theta": th, "se": th / mp.sqrt(c)}
    if op == "micro.est.resilience":
        sl, se = ols_slope([p["t"] for p in inp["points"]],
                           [mp.log(M(str(p["s"])) - M(str(inp["s_inf"]))) for p in inp["points"]])
        return {"kappa": -sl, "se": se}
    if op == "micro.est.liquidity_decay":
        sl, se = ols_slope([p["k"] for p in inp["levels"]], [mp.log(M(str(p["depth"]))) for p in inp["levels"]])
        return {"alpha": -sl, "se": se}
    if op == "micro.est.adverse_selection":
        b, se = ols_origin(inp["x"], inp["y"])
        return {"lambda_as": b, "se": se}
    if op == "micro.est.regime_impact":
        r = {k: dict(zip(("lambda_as", "se"), ols_origin(v["x"], v["y"]))) for k, v in sorted(inp["regimes"].items())}
        return {"regimes": r, "ratio": r["stressed"]["lambda_as"] / r["calm"]["lambda_as"]}
    d, se = welch(inp["passive"], inp["aggressive"])
    return {"delta": d, "se": se}


def mest_suite():
    s = Suite("mest_h", SPEC_M, G)
    for cid, op, inp, exp in MEST:
        verified = (["hand"] if cid == "mest_h-0006"  # HR-75a re-derivation; the blind MATCH was under HR-75
                    else ["hand", SHAPE] if cid in ("mest_h-0008", "mest_h-0009") else ["hand", MATCH])
        if isinstance(exp, str):
            s.add(op, inp, error=exp, cls="simple_analytic", verified=verified, tags=["stage_h", "microstructure", "error"],
                  description=f"{cid} from the spec table")
        else:
            ref = mest_ref(op, inp)
            if op == "micro.est.regime_impact":
                for lab in ("calm", "stressed"):
                    close(ref["regimes"][lab]["lambda_as"], exp[lab][0])
                    close(ref["regimes"][lab]["se"], exp[lab][1])
                close(ref["ratio"], exp["ratio"])
                out = {"regimes": {k: {f: fz(x) for f, x in v.items()} for k, v in ref["regimes"].items()},
                       "ratio": fz(ref["ratio"])}
            else:
                assert set(ref) == set(exp), cid
                for k in exp:
                    close(ref[k], exp[k])
                out = {k: fz(v) for k, v in ref.items()}
            s.add(op, inp, out, cls="simple_analytic", verified=verified + [MP], limit=TOL,
                  tags=["stage_h", "microstructure"], description=f"{cid} from the spec table")
        assert s.cases[-1]["case_id"] == cid
    return s


# ------------------------------------------------------------------ venue_h

def base(h, orders=None, extra=None):
    return {
        "mids": [{"t": 0.0, "mid": 100.00}, {"t": 1.0, "mid": 100.02}, {"t": 5.0, "mid": 100.05}, {"t": 10.0, "mid": 99.98}],
        "fills": [{"venue": "A", "side": "BUY", "quantity": 100.0, "price": 100.01, "t": 0.0},
                  {"venue": "A", "side": "SELL", "quantity": 200.0, "price": 100.03, "t": 1.0},
                  {"venue": "B", "side": "BUY", "quantity": 300.0, "price": 100.00, "t": 1.0}] + (extra or []),
        "orders": orders or [{"venue": "A", "sent": 500.0, "filled": 300.0}, {"venue": "B", "sent": 300.0, "filled": 300.0}],
        "horizons": h,
    }


OVERFILL = [{"venue": "A", "sent": 500.0, "filled": 600.0}, {"venue": "B", "sent": 300.0, "filled": 300.0}]
VENUE = [  # case, inputs, table (venue: (markout, markout_bps, toxicity)) or fill rates or error code, verified_by
    ("venue_h-0001", base([5.0]), {"A": ("0", "0", "0.666666666666667"), "B": ("0.05", "5", "0")}, ["hand", SHAPE]),
    ("venue_h-0002", base([10.0]), {"A": ("0.0233333333333333", "2.33278901589629", "0.333333333333333"),
                                    "B": ("-0.02", "-2", "1")}, ["hand", SHAPE]),
    ("venue_h-0003", base([0.0]), {"A": ("0.00333333333333333", "0.333255573699470", "0.333333333333333"),
                                   "B": ("0.02", "2", "0")}, ["hand", SHAPE]),
    ("venue_h-0004", base([]), {"fill_rates": {"A": "0.6", "B": "1"}}, ["hand", SHAPE]),
    ("venue_h-0005", base([5.0], OVERFILL), "E_INPUT", ["hand", MATCH]),
    ("venue_h-0006", base([0.0], extra=[{"venue": "B", "side": "BUY", "quantity": 10.0, "price": 100.0, "t": -1.0}]),
     "E_INPUT", ["hand", "post-blind 2026-11-18 (h = 0 added after the blind lane): not blind-checked"]),
    ("venue_h-0007", base([-1.0]), "E_DOMAIN", ["hand", MATCH]),
    ("venue_h-0008", base([-1.0], OVERFILL), "E_INPUT", ["hand"]),  # HR-75a; was E_DOMAIN under HR-75
]


def venue_suite():
    s = Suite("venue_h", SPEC_V, G)
    for cid, inp, exp, verified in VENUE:
        if isinstance(exp, str):
            s.add("exec.venue.analytics", inp, error=exp, cls="simple_analytic", verified=verified,
                  tags=["stage_h", "execution", "error"], description=f"{cid} from the spec table")
        else:
            rates, marks = venue_ref(inp)
            if "fill_rates" in exp:
                for v, t in exp["fill_rates"].items():
                    close(rates[v], t)
                assert set(rates) == set(exp["fill_rates"]) and not marks
            else:
                assert [m["venue"] for m in marks] == sorted(exp), cid
                for m in marks:
                    for k, t in zip(("markout", "markout_bps", "toxicity"), exp[m["venue"]]):
                        close(m[k], t)
                close(rates["A"], "0.6")
                close(rates["B"], "1")
            out = {"fill_rates": {v: fz(x) for v, x in rates.items()},
                   "markouts": [{k: (fz(x) if k in ("markout", "markout_bps", "toxicity") else x)
                                 for k, x in m.items()} for m in marks]}
            s.add("exec.venue.analytics", inp, out, cls="simple_analytic", verified=verified + [MP], limit=TOL,
                  tags=["stage_h", "execution", "simulated"], description=f"{cid} from the spec table")
        assert s.cases[-1]["case_id"] == cid
    return s


def e1(s):
    """F-2: one NaN Real input per operation, from its first value case; E_DOMAIN before any other check."""
    seen = set()
    for c in list(s.cases):
        op = c["operation"]
        if op in seen or c["expected"]["status"] != "ok":
            continue
        seen.add(op)
        inp = json.loads(json.dumps(c["inputs"]))
        node, key = _first_real(inp)
        node[key] = "NaN"
        s.add(op, inp, error="E_DOMAIN", cls="simple_analytic", verified=["hand"],
              tags=["stage_h", "e1", "non-finite-input"], description=f"F-2: NaN input (from {c['case_id']})")
    assert seen == {c["operation"] for c in s.cases}


def _first_real(v):
    items = sorted(v.items()) if isinstance(v, dict) else enumerate(v)
    for k, x in items:
        if isinstance(x, float):
            return v, k
        if isinstance(x, (dict, list)):
            r = _first_real(x)
            if r:
                return r
    return None


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    for s in (mest_suite(), venue_suite()):
        e1(s)
        s.write()
    common.GOLDEN = keep


if __name__ == "__main__":
    main()
