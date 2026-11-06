"""Golden cases for limits.md, and for the store and skip rulings in rulings.md."""
import hashlib
import json
from datetime import date
from fractions import Fraction as Fr

import mpmath as mp

from gen_data import canon
from gen_random import mc_replay
from gen_rulings_store import LOG, K1, K2, K4, chain, rec, row, snap
from gen_stats_engines import cos_replay, pde_replay
from qf_oracle.common import Suite, f, note
from qf_oracle.dates import is_business
from qf_oracle.rng import Sobol, Xo, bs

G = "oracle/python/gen_limits.py"
L = "E_LIMIT"
E = "date_and_convention"


def limits():
    s = Suite("limits", "specifications/01-core/limits.md", G)
    s.compact = True  # holds arrays at their size limits

    def over(op, inp):
        s.add(op, inp, error=L, cls=E, tags=["limit", "above"])

    def at(op, inp, out, cls, ver, **kw):
        s.add(op, inp, out, cls=cls, verified=ver, tags=["limit", "at"], **kw)

    rnd = {"absolute": 1e-8, "reason": "rounding over 10^7 additions; the rule's own error is far below this"}
    for op, v in (("core.integrate.trapezoid", 1 / 6), ("core.integrate.simpson", 1 / 6)):
        at(op, {"function": "poly5", "a": 0.0, "b": 1.0, "n": 10000000}, {"value": v}, "quadrature", ["analytic"], limit=rnd)
        over(op, {"function": "poly5", "a": 0.0, "b": 1.0, "n": 10000002})
    over("core.integrate.simpson", {"function": "poly5", "a": 0.0, "b": 1.0, "n": 9007199254740992})
    over("core.integrate.simpson", {"function": "poly5", "a": 0.0, "b": 1.0, "n": 10000001})
    lim = {"absolute": 1e-9, "reason": "tol is 1e-10"}
    e1 = f(mp.e - 1)
    at("core.integrate.adaptive_simpson", {"function": "exp", "a": 0.0, "b": 1.0, "tol": 1e-10, "max_depth": 60}, {"value": e1}, "quadrature", ["analytic"], limit=lim)
    over("core.integrate.adaptive_simpson", {"function": "exp", "a": 0.0, "b": 1.0, "max_depth": 61})
    at("core.integrate.gauss_kronrod", {"function": "exp", "a": 0.0, "b": 1.0, "tol": 1e-10, "max_intervals": 10000}, {"value": e1}, "quadrature", ["analytic"], limit=lim)
    over("core.integrate.gauss_kronrod", {"function": "exp", "a": 0.0, "b": 1.0, "max_intervals": 10001})
    s.add("core.integrate.adaptive_simpson", {"function": "oscillatory", "a": 0.0, "b": 2.0, "tol": 1e-6, "max_depth": 1}, error="E_NO_CONVERGENCE", cls=E, tags=["limit"],
          description="the Simpson difference at depth 1 is about 0.1, far above tol and rounding, so no build can accept it")
    root = f(mp.findroot(lambda x: mp.cos(x) - x, 0.7))
    for op in ("bisection", "brent"):
        at(f"core.root.{op}", {"function": "cos_minus_x", "a": 0.0, "b": 1.0, "max_iter": 100000}, {"root": root}, "root_finding", ["mpmath-50"])
        over(f"core.root.{op}", {"function": "cos_minus_x", "a": 0.0, "b": 1.0, "max_iter": 100001})
    at("core.root.newton", {"function": "cos_minus_x", "x0": 0.5, "max_iter": 100000}, {"root": root}, "root_finding", ["mpmath-50"])
    over("core.root.newton", {"function": "cos_minus_x", "x0": 0.5, "max_iter": 100001})
    x = Xo(seed=1)
    at("core.rng.next_u64", {"seed": "1", "stream": 0, "count": 100000}, {"values": [str(x.next()) for _ in range(100000)]}, "bit_exact", ["pure-integer-replay"])
    over("core.rng.next_u64", {"seed": "1", "stream": 0, "count": 100001})
    over("core.rng.uniforms", {"seed": "1", "stream": 0, "count": 100001})
    over("core.rng.normals", {"seed": "1", "stream": 0, "count": 100001})
    over("core.rng.set_state_next_u64", {"state": ["1", "2", "3", "4"], "count": 100001})
    x = Xo(seed=1)
    for _ in range(10000000):
        x.next()
    at("core.rng.next_u64", {"seed": "1", "stream": 0, "count": 2, "skip": 10000000}, {"values": [str(x.next()), str(x.next())]}, "bit_exact", ["pure-integer-replay"])
    over("core.rng.next_u64", {"seed": "1", "stream": 0, "count": 1, "skip": 10000001})
    o = Sobol(4)
    at("core.sobol.points", {"dimensions": 4, "count": 25000}, {"points": [o.next() for _ in range(25000)]}, "bit_exact", ["own-bit-code"])
    over("core.sobol.points", {"dimensions": 4, "count": 25001})
    o = Sobol(2)
    for _ in range(10000000):
        o.next()
    at("core.sobol.points", {"dimensions": 2, "count": 1, "skip": 10000000}, {"points": [o.next()]}, "bit_exact", ["own-bit-code"])
    over("core.sobol.points", {"dimensions": 2, "count": 1, "skip": 10000001})
    b = {"option": "CALL", "spot": 100.0, "strike": 100.0, "r": 0.05, "q": 0.02, "sigma": 0.2, "t": 1.0, "seed": "20261106", "method": "PLAIN"}
    inp = {**b, "paths": 1000000, "steps": 1}
    p, se = mc_replay(inp)
    note(f"limits: mc at limit, price {p:.5f}, stderr {se:.5f}")
    at("core.mc.gbm_european", inp, {"price": p, "stderr": se}, "common_rng", ["independent-replay", "analytic-mpmath-50"],
       extra_checks=[{"output": "price", "expected": f(bs("CALL", 100, 100, .05, .02, .2, 1)[0]), "method": "confidence_interval", "stderr_output": "stderr", "z": 4.0}])
    over("core.mc.gbm_european", {**b, "paths": 1000001, "steps": 1})
    over("core.mc.gbm_european", {**b, "paths": 500001, "steps": 2})
    pb = {"option": "CALL", "spot": 100.0, "strike": 100.0, "r": 0.05, "q": 0.02, "sigma": 0.2, "t": 1.0}
    inp = {**pb, "space_steps": 2000, "time_steps": 5000}
    pr, d, g = pde_replay(inp)
    at("core.pde.bs_european", inp, {"price": pr, "delta": d, "gamma": g}, "numerical_scheme", ["independent-replay"])
    over("core.pde.bs_european", {**pb, "space_steps": 2002, "time_steps": 5000})
    cb = {"option": "CALL", "spot": 100.0, "strike": 100.0, "r": 0.05, "q": 0.02, "t": 1.0, "model": {"name": "BLACK_SCHOLES", "sigma": 0.2}, "truncation": 10.0}
    v512, v1024 = cos_replay({**cb, "terms": 512}), cos_replay({**cb, "terms": 1024})
    assert abs(v512 - v1024) < mp.mpf(10) ** -30  # later terms vanish, so 100000 terms give the same value
    at("core.cos.european", {**cb, "terms": 100000}, {"price": f(v1024)}, "fourier", ["mpmath-50-replay"])
    over("core.cos.european", {**cb, "terms": 100001})
    d0 = date(2000, 1, 4)
    s.add("core.calendar.add_business_days", {"calendar": "GBLO", "date": str(d0), "days": 30000}, error="E_DATE_RANGE", cls=E, tags=["limit", "at"], description="legal size; the walk leaves 2099")
    over("core.calendar.add_business_days", {"calendar": "GBLO", "date": str(d0), "days": 30001})
    over("core.calendar.add_business_days", {"calendar": "GBLO", "date": str(d0), "days": -30001})
    s.add("core.calendar.add_tenor", {"calendar": "GBLO", "date": "2024-01-02", "tenor": "9999Y", "convention": "FOLLOWING", "end_of_month": False}, error="E_DATE_RANGE", cls=E)
    assert is_business("GBLO", d0)
    n = 100000
    xs = [1.0, 2.0] * (n // 2)
    at("core.stats.summary", {"x": xs}, {"count": n, "mean": 1.5, "variance": float(Fr(n // 4 * 1, 1) * 1 / (n - 1)), "stdev": f(mp.sqrt(mp.mpf(n) / 4 / (n - 1))), "skewness": 0.0, "excess_kurtosis": -2.0, "min": 1.0, "max": 2.0},
       "statistics", ["exact-rational"], output_classes={"count": E})
    over("core.stats.summary", {"x": xs + [1.0]})
    w = [1.0] * 1001
    at("core.ts.rolling", {"x": w, "window": 1000, "statistic": "MEAN"}, {"values": [None] * 999 + [1.0, 1.0]}, "statistics", ["hand"])
    over("core.ts.rolling", {"x": w + [1.0], "window": 1001, "statistic": "MEAN"})
    over("core.ts.rolling", {"x": [1.0, 2.0], "window": 1001, "statistic": "MEAN"})
    alt = [(-1.0) ** i for i in range(1002)]  # mean 0, so acf_k = (+-)(n - k)/n exactly
    m = len(alt)
    acf = [float(Fr((-1) ** k * (m - k), m)) for k in range(1, 1001)]
    at("core.ts.autocorrelation", {"x": alt, "max_lag": 1000}, {"acf": acf}, "statistics", ["exact-rational"])
    over("core.ts.autocorrelation", {"x": alt, "max_lag": 1001})
    over("core.ts.ljung_box", {"x": alt, "max_lag": 1001})
    I = [[1.0 if i == j else 0.0 for j in range(200)] for i in range(200)]
    at("core.linalg.solve", {"a": I, "b": [2.0] * 200}, {"x": [2.0] * 200}, "interpolation", ["hand"])
    big = [[1.0 if i == j else 0.0 for j in range(201)] for i in range(201)]
    over("core.linalg.solve", {"a": big, "b": [2.0] * 201})
    over("core.linalg.cholesky", {"a": big})
    over("core.linalg.eigen_symmetric", {"a": big})
    fill = 1048576 - len('{"a":""}')
    t = '{"a":"' + "x" * fill + '"}'
    c = canon({"a": "x" * fill})
    at("core.snapshot.hash", {"document_text": t}, {"canonical": c, "snapshot_id": "sha256:" + hashlib.sha256(c.encode()).hexdigest()}, E, ["oracle-canon"])
    over("core.snapshot.hash", {"document_text": t[:-2] + 'x"}'})
    deep = "[" * 63 + "1" + "]" * 63
    c = "{" + canon("a") + ":" + "[" * 63 + canon(1) + "]" * 63 + "}"
    at("core.snapshot.hash", {"document_text": '{"a":' + deep + "}"}, {"canonical": c, "snapshot_id": "sha256:" + hashlib.sha256(c.encode()).hexdigest()}, E, ["oracle-canon"])
    over("core.snapshot.hash", {"document_text": '{"a":[' + deep + "]}"})
    v = 1
    for _ in range(64):
        v = [v]
    h = [rec(1, "A", K1, K1, v)]
    at("core.store.chain", {"records": h}, {"head": chain(h)[0], "hashes": chain(h)[1]}, E, ["oracle-canon"])
    over("core.store.chain", {"records": [rec(1, "A", K1, K1, [v])]})
    cps = [K1] * 1000
    one = [rec(1, "A", K1, K1, 1.0)]
    sid = snap([row(one[0])], K1)[1]
    at("core.store.replay", {"records": one, "checkpoints": cps}, {"snapshots": [{"as_of": K1, "row_count": 1, "snapshot_id": sid}] * 1000, "head": chain(one)[0]}, E, ["oracle-canon"])
    over("core.store.replay", {"records": one, "checkpoints": cps + [K1]})
    s.add("core.integrate.simpson", {"function": "not_registered", "a": 0.0, "b": 1.0, "n": 10000002}, error="E_SCHEMA", cls=E, tags=["limit"], description="E_SCHEMA comes before E_LIMIT")
    s.add("core.integrate.simpson", {"function": "poly5", "a": 1.0, "b": 0.0, "n": 10000002}, error=L, cls=E, tags=["limit"], description="E_LIMIT comes before rule checks")
    s.write()


def limit_order():
    s = Suite("limit_order", "specifications/01-core/limits.md", G)
    s.compact = True
    h = "core.snapshot.hash"

    def err(op, inp, code, rule):
        s.add(op, inp, error=code, cls=E, tags=["limit", rule])

    deep = "[" * 65
    err(h, {"document_text": "x" * 1048577}, L, "B1")
    err(h, {"document_text": "\u00e9" * 524289}, L, "B1")
    err(h, {"document_text": '{"a":' + deep}, L, "B2")
    err(h, {"document_text": "{x " + deep}, L, "B2")
    err(h, {"document_text": '{"a":1e400,"b":' + deep + "1" + "]" * 65 + "}"}, L, "B2")
    err(h, {"document_text": '{"a":1,"a":2,"b":' + deep + "1" + "]" * 65 + "}"}, L, "B2")
    for t in ('{"a":"' + deep + '"}', '{"a":"\\"' + deep + '"}'):
        c = canon(json.loads(t))
        s.add(h, {"document_text": t}, {"canonical": c, "snapshot_id": "sha256:" + hashlib.sha256(c.encode()).hexdigest()}, cls=E, verified=["oracle-canon"], tags=["limit", "B2"],
              description="brackets inside a string do not count")
    err(h, {"document_text": '{"a":1'}, "E_PARSE", "B2")
    big = [0] * 100001
    dc = "core.daycount.year_fraction"
    err(dc, {"convention": "ACT_360", "start": "2024-01-01", "end": "2024-01-02", "unused": big}, L, "B3")
    err(dc, {"convention": "ACT_ACT_ICMA", "start": "2024-01-01", "end": "2024-01-02", "unused": big}, "E_SCHEMA", "B3")
    err(dc, {"convention": "ACT_365L", "start": "2024-01-01", "end": "2024-01-02", "frequency": 5, "unused": big}, "E_SCHEMA", "B3")
    err("core.sobol.points", {"dimensions": 65, "count": 100000}, L, "B3")
    v = 1
    for _ in range(65):
        v = [v]
    err("core.store.chain", {"records": [{**rec(1, "A", K1, K1, 1.0), "note": v}]}, L, "B4")
    err("core.store.chain", {"records": [rec(1, "A", "0001-01-01T00:00:00+01:00", K1, 1.0)]}, "E_DATE_RANGE", "B5")
    s.write()


def store_rulings():
    s = Suite("store_rulings", "specifications/01-core/rulings.md", G)
    q = "core.store.query_as_of"

    def err(op, inp, code, rule):
        s.add(op, inp, error=code, cls=E, tags=["invalid", rule])

    err(q, {"records": [rec(0, "A", K1, K1, 1.0)], "as_of": K1}, "E_SCHEMA", "A1")
    err(q, {"records": [rec(1, "", K1, K1, 1.0)], "as_of": K1}, "E_SCHEMA", "A1")
    back = [LOG[1], LOG[0]]
    err(q, {"records": back, "as_of": "not-an-instant"}, "E_SCHEMA", "A2")
    err(q, {"records": back, "as_of": K1, "event_from": K2, "event_to": K1}, "E_INPUT", "A2")
    extra = [{**rec(1, "A", K1, K1, 1.0), "note": "kept", "snapshot_id": "sha256:kept"}]
    h, hs = chain(extra)
    s.add("core.store.chain", {"records": extra}, {"head": h, "hashes": hs}, cls=E, verified=["oracle-canon"], tags=["A3"])
    s.add(q, {"records": extra, "as_of": K1}, {"rows": [row(extra[0])]}, cls=E, verified=["hand"], tags=["A3"], description="unknown keys stay out of rows")
    offs = [rec(1, "A", "2026-11-02T17:00:00+01:00", "2026-11-02T12:05:00-04:00", 1.0)]
    h, hs = chain(offs)
    s.add("core.store.chain", {"records": offs}, {"head": h, "hashes": hs}, cls=E, verified=["oracle-canon"], tags=["A3"], description="instants stay as given in the chain")
    err(q, {"records": [rec(1, "A", "0001-01-01T00:00:00+01:00", K1, 1.0)], "as_of": K1}, "E_DATE_RANGE", "A5")
    err(q, {"records": [], "as_of": "9999-12-31T23:00:00-02:00"}, "E_DATE_RANGE", "A5")
    views = [row(LOG[1]), row(LOG[0])]
    s.add("core.store.replay", {"records": LOG, "checkpoints": [K1]}, {"snapshots": [{"as_of": K1, "row_count": 2, "snapshot_id": snap(views, K1)[1]}], "head": chain(LOG)[0]}, cls=E, verified=["oracle-canon"], tags=["A6"],
          description="head covers the whole log, past the last checkpoint")
    s.add("core.store.replay", {"records": LOG, "checkpoints": []}, {"snapshots": [], "head": chain(LOG)[0]}, cls=E, verified=["hand"], tags=["A6"])
    assert K4
    s.write()


def surrogates():
    """Ruling A4. A lone surrogate can only travel as a JSON escape, so this suite is written in ASCII."""
    s = Suite("store_a4", "specifications/01-core/rulings.md", G)
    s.ascii_only = True
    bad = "x\ud800y"
    q = "core.store.query_as_of"
    for op, inp in ((q, {"records": [rec(1, "A", K1, K1, bad)], "as_of": K1}), (q, {"records": [rec(1, bad, K1, K1, 1.0)], "as_of": K1}), (q, {"records": [rec(1, "A", K1, K1, {"k": [bad]})], "as_of": K1}),
                    (q, {"records": [{**rec(1, "A", K1, K1, 1.0), "note": bad}], "as_of": K1}), ("core.store.chain", {"records": [rec(1, "A", K1, K1, bad)]})):
        s.add(op, inp, error="E_SCHEMA", cls=E, tags=["invalid", "A4"])
    good = [rec(1, "A", K1, K1, "\U0001f600")]  # a proper pair must still pass
    s.add("core.store.chain", {"records": good}, {"head": chain(good)[0], "hashes": chain(good)[1]}, cls=E, verified=["oracle-canon"], tags=["A4"])
    s.write()


def main():
    limits()
    surrogates()
    limit_order()
    store_rulings()


if __name__ == "__main__":
    main()
