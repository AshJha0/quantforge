"""Golden cases for rulings.md and asof-store.md."""
import hashlib
from datetime import datetime, timezone

import numpy as np
from scipy.interpolate import PchipInterpolator

from gen_data import canon
from gen_numerics import monotone_convex
from gen_stats_engines import pde_replay
from qf_oracle.common import Suite, note
from qf_oracle.rng import Xo

G = "oracle/python/gen_rulings_store.py"
E = "date_and_convention"


def rulings():
    s = Suite("rulings", "specifications/01-core/rulings.md", G)

    def err(op, inp, code, rule):
        s.add(op, inp, error=code, tags=["invalid", rule], cls=E)

    dc, cp = "core.daycount.year_fraction", "core.compounding.discount_factor"
    err("core.integrate.trapezoid", {"function": "exp", "a": 0.0, "b": 1.0, "n": 4.0}, "E_SCHEMA", "G1")
    s.add("core.integrate.trapezoid", {"function": "poly5", "a": 0, "b": 1, "n": 1}, {"value": -0.0 + 0.5 * (1 + -1)}, verified=["hand"], cls="quadrature", tags=["G1"],
          description="reals may be written as integers; (f(0) + f(1)) / 2 = (1 + (-1)) / 2")
    s.add(dc, {"convention": "ACT_360", "start": "2024-01-01", "end": "2024-01-31", "unused": 1}, {"year_fraction": 30 / 360}, verified=["hand"], tags=["G2"])
    s.add("core.root.brent", {"function": "exp_minus_two", "a": 0.0, "b": 2.0, "x_tol": None}, {"root": 0.6931471805599453}, verified=["hand"], cls="root_finding", tags=["G3"])
    err("core.root.brent", {"function": "exp_minus_two", "a": None, "b": 2.0}, "E_SCHEMA", "G3")
    now, t0 = "2026-11-06T16:00:00Z", "2026-11-06T15:59:00Z"
    err("core.data.check_quotes", {"as_of": now, "stale_after_seconds": 60, "quotes": [{"instrument_id": "A", "event_time": t0, "ask": 1.0, "quote_status": "FIRM"}]}, "E_SCHEMA", "G4")
    err("core.diff.central", {"function": "exp", "x": 1.0, "h": 1e-4, "order": 3}, "E_SCHEMA", "G5")
    s.add(cp, {"rate": 0.05, "t": 2.0, "compounding": "SIMPLE", "frequency": 5}, {"discount_factor": 1 / 1.1}, verified=["hand"], tags=["G6"])
    err("core.ts.returns", {"prices": [1.0], "kind": "LOG"}, "E_INPUT", "G10")
    err("core.ts.ewma_variance", {"returns": [], "lambda": 0.9}, "E_INPUT", "G10")
    err("core.stats.quantile", {"x": [], "p": [0.5]}, "E_INPUT", "G10")
    a = Xo(seed=7)
    s.add("core.rng.next_u64", {"seed": "007", "stream": 0, "count": 1}, {"values": [str(a.next())]}, cls="bit_exact", verified=["pure-integer-replay"], tags=["G11"])
    err("core.rng.next_u64", {"seed": "18446744073709551616", "stream": 0, "count": 1}, "E_SCHEMA", "G11")
    err(dc, {"convention": "BUS_252", "calendar": "GBLO", "start": "1999-01-04", "end": "1999-01-04"}, "E_DATE_RANGE", "D1")
    err("core.calendar.business_days_between", {"calendar": "GBLO", "start": "2024-01-02", "end": "1999-01-04"}, "E_DATE_RANGE", "D2")
    err(cp, {"rate": -3.0, "t": 0.0, "compounding": "PERIODIC", "frequency": 2}, "E_DOMAIN", "C1")
    err("core.root.newton", {"function": "cubic_wallis", "x0": 2.0, "a": 1.0}, "E_SCHEMA", "R1")
    err("core.root.newton", {"function": "cubic_wallis", "x0": 2.0, "a": 3.0, "b": 2.0}, "E_INPUT", "R2")
    s.add("core.root.newton", {"function": "square", "x0": 0.0, "a": 0.0, "b": 1.0}, {"root": 0.0}, cls="root_finding", verified=["hand"], tags=["R3"])
    err("core.integrate.adaptive_simpson", {"function": "exp", "a": 0.0, "b": 1.0, "max_depth": 0}, "E_INPUT", "I1")
    err("core.integrate.gauss_kronrod", {"function": "exp", "a": 0.0, "b": 1.0, "max_intervals": 0}, "E_INPUT", "I1")
    err("core.integrate.adaptive_simpson", {"function": "inv_sqrt", "a": 0.0, "b": 1.0}, "E_NON_FINITE", "I2")
    err("core.linalg.solve", {"a": [[0.0, 0.0], [0.0, 0.0]], "b": [1.0, 1.0]}, "E_SINGULAR", "L1")
    s.add("core.linalg.eigen_symmetric", {"a": [[1e6, 1.0], [1.0000001, 1e6]]}, {"values": [999999.0, 1000001.0]}, cls="interpolation", verified=["hand"], tags=["L2"],
          limit={"absolute": 1e-3, "relative": 0.0, "reason": "asymmetry of 1e-7 is inside the rule; which triangle is read is free"})
    err("core.linalg.cholesky", {"a": [[1.0, 2.0], [2.001, 9.0]]}, "E_INPUT", "L2")
    err("core.interp.evaluate", {"method": "tension", "tension": -1.0, "x": [0.0, 1.0, 2.0], "y": [0.0, 1.0, 0.0], "at": [0.5]}, "E_DOMAIN", "P1")
    x, y = [0.0, 1.0, 2.0, 3.0], [1.0, 1.0, 2.0, 4.0]
    at = [0.0, 0.5, 1.5, 2.5, 3.0]
    pc = PchipInterpolator(np.array(x), y)
    assert pc(0.0, 1) == 0
    s.add("core.interp.evaluate", {"method": "monotone_pchip", "x": x, "y": y, "at": at}, {"values": [float(pc(v)) for v in at], "derivatives": [float(pc(v, 1)) for v in at]},
          cls="interpolation", verified=["scipy-1.18.1"], tags=["P2"])
    err("core.interp.monotone_convex", {"t": [1.0, 2.0], "r": [0.05, 0.01], "at": [3.0], "positive": True}, "E_OUT_OF_RANGE", "P3")
    t, r = [1.0, 2.0, 3.0], [0.02, 0.02, 0.0233]
    q = [1.5, 2.0, 2.5, 3.0]
    fw, zr = monotone_convex(t, r, q, False)
    s.add("core.interp.monotone_convex", {"t": t, "r": r, "at": q, "positive": False}, {"forwards": fw, "zero_rates": zr}, cls="interpolation", verified=["mpmath-50", "repricing"], tags=["P4"])
    s.add("core.stats.covariance", {"x": [0.1, 0.1, 0.1], "y": [1.0, 2.0, 4.0]}, {"covariance": 0.0, "correlation": None}, cls="statistics", verified=["hand"], tags=["S1"])
    s.add("core.stats.ols", {"x": [1.0, 2.0, 3.0], "y": [5.0, 5.0, 5.0]}, {"alpha": 5.0, "beta": 0.0, "r_squared": None, "se_alpha": 0.0, "se_beta": 0.0}, cls="statistics", verified=["hand"], tags=["S2"])
    err("core.ts.ar1", {"x": [2.0, 2.0, 2.0, 2.0]}, "E_SINGULAR", "S3")
    s.add("core.time.to_instant", {"zone": "Asia/Tokyo", "local": "2007-01-01T00:00:00"}, {"instant": "2006-12-31T15:00:00Z"}, cls=E, verified=["hand"], tags=["T1"])
    inp = {"option": "CALL", "spot": 100.0, "strike": 100.0, "r": 0.05, "q": 0.02, "sigma": 0.2, "t": 1.0, "space_steps": 200, "time_steps": 100, "rannacher_steps": 0}
    p, d, g = pde_replay(inp)
    s.add("core.pde.bs_european", inp, {"price": p, "delta": d, "gamma": g}, cls="numerical_scheme", verified=["independent-replay"], tags=["E1"])
    err("core.rng.next_u64", {"seed": "1", "stream": 0, "count": 1, "skip": -1}, "E_SCHEMA", "N1")
    err("core.sobol.points", {"dimensions": 1, "count": 1, "skip": -1}, "E_INPUT", "N1")
    err("core.mc.gbm_european", {"option": "CALL", "spot": 100.0, "strike": 100.0, "r": 0.0, "q": 0.0, "sigma": 0.2, "t": 1.0, "paths": 10, "seed": "1", "stream": 1024, "method": "PLAIN"}, "E_SCHEMA", "M1")
    bad = {"instrument_id": "A", "event_time": "2026-11-06T16:00:01Z", "bid": 1.0, "ask": 1.1, "quote_status": "FIRM"}
    err("core.data.check_quotes", {"as_of": now, "stale_after_seconds": 60, "outlier_min_history": 2, "quotes": []}, "E_INPUT", "Q1")
    err("core.data.check_quotes", {"as_of": now, "stale_after_seconds": 60, "quotes": [bad]}, "E_INPUT", "Q1")
    s.write()


def rec(seq, sid, ev, kn, val, **kw):
    return {"sequence": seq, "series_id": sid, "event_time": ev, "knowledge_time": kn, "value": val, **kw}


def zform(t):
    return datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def row(r):
    return {"series_id": r["series_id"], "event_time": zform(r["event_time"]), "knowledge_time": zform(r["knowledge_time"]), "sequence": r["sequence"], "value": r["value"]}


def snap(rows, as_of):
    c = canon({"as_of": zform(as_of), "rows": rows})
    return c, "sha256:" + hashlib.sha256(c.encode()).hexdigest()


def chain(records):
    h, out = "0" * 64, []
    for r in records:
        h = hashlib.sha256((h + canon(r)).encode()).hexdigest()
        out.append(h)
    return h, out


D1, D2 = "2026-11-02T16:00:00Z", "2026-11-03T16:00:00Z"
K1, K2, K3, K4 = "2026-11-02T16:05:00Z", "2026-11-03T16:05:00Z", "2026-11-04T09:00:00Z", "2026-11-05T09:00:00Z"
LOG = [rec(1, "SONIA", D1, K1, 3.73), rec(2, "EURUSD", D1, K1, 1.08), rec(3, "SONIA", D2, K2, 3.74),
       rec(4, "SONIA", D1, K3, 3.72),                      # correction, learned later
       rec(5, "EURUSD", D1, K3, None, deleted=True),      # withdrawn
       rec(6, "EURUSD", D1, K4, 1.09),                    # restored
       rec(7, "SONIA", "2026-11-01T16:00:00Z", K4, None)]  # late, and known to be missing


def store():
    s = Suite("store", "specifications/01-core/asof-store.md", G)
    q, lt = "core.store.query_as_of", "core.store.latest"
    R = {r["sequence"]: row(r) for r in LOG}

    def view(*seqs):
        return [R[i] for i in seqs]
    # Expected rows are written by hand from the rules, by sequence number.
    hand = [("2026-11-02T16:04:59Z", ()), (K1, (2, 1)), (K2, (2, 1, 3)), (K3, (4, 3)), (K4, (6, 7, 4, 3))]
    for a, seqs in hand:
        s.add(q, {"records": LOG, "as_of": a}, {"rows": view(*seqs)}, cls=E, verified=["hand"])
    s.add(q, {"records": LOG, "as_of": K4, "series_id": "SONIA", "event_from": D1, "event_to": D1}, {"rows": view(4)}, cls=E, verified=["hand"])
    s.add(q, {"records": [], "as_of": K4}, {"rows": []}, cls=E, verified=["hand"], tags=["boundary"])
    s.add(lt, {"records": LOG, "as_of": K2, "series_id": "SONIA"}, {"row": R[3]}, cls=E, verified=["hand"])
    s.add(lt, {"records": LOG, "as_of": K3, "series_id": "EURUSD"}, {"row": None}, cls=E, verified=["hand"])
    off = [rec(1, "A", "2026-11-02T17:00:00+01:00", "2026-11-02T12:05:00-04:00", 1.0)]
    utc = [rec(1, "A", "2026-11-02T16:00:00Z", "2026-11-02T16:05:00Z", 1.0)]
    c0, i0 = snap([row(utc[0])], K1)
    s.add("core.store.snapshot", {"records": off, "as_of": K1}, {"canonical": c0, "snapshot_id": i0}, cls=E, verified=["oracle-canon"], description="offsets do not change the hash")
    s.add("core.store.snapshot", {"records": utc, "as_of": "2026-11-02T17:05:00+01:00"}, {"canonical": c0, "snapshot_id": i0}, cls=E, verified=["oracle-canon"])
    c, i = snap(view(4, 3), K3)
    s.add("core.store.snapshot", {"records": LOG, "as_of": K3}, {"canonical": c, "snapshot_id": i}, cls=E, verified=["oracle-canon"])
    cps = [K1, K2, K3, K3, K4]
    views = [(2, 1), (2, 1, 3), (4, 3), (4, 3), (6, 7, 4, 3)]
    snaps = [{"as_of": a, "row_count": len(v), "snapshot_id": snap(view(*v), a)[1]} for a, v in zip(cps, views)]
    s.add("core.store.replay", {"records": LOG, "checkpoints": cps}, {"snapshots": snaps, "head": chain(LOG)[0]}, cls=E, verified=["oracle-canon"])
    # An append must leave earlier checkpoints alone, while the head moves on.
    more = LOG + [rec(8, "SONIA", D2, "2026-11-06T09:00:00Z", 3.75)]
    s.add("core.store.replay", {"records": more, "checkpoints": cps}, {"snapshots": snaps, "head": chain(more)[0]}, cls=E, verified=["oracle-canon"], description="same snapshots as the case before")
    h, hs = chain(LOG)
    s.add("core.store.chain", {"records": LOG}, {"head": h, "hashes": hs}, cls=E, verified=["oracle-canon"])
    s.add("core.store.chain", {"records": []}, {"head": "0" * 64, "hashes": []}, cls=E, verified=["hand"], tags=["boundary"])
    for inp, op, code in (({"records": [LOG[0], LOG[0]], "as_of": K1}, q, "E_INPUT"), ({"records": [LOG[3], LOG[0]], "as_of": K1}, q, "E_INPUT"),
                          ({"records": [{"sequence": 1}], "as_of": K1}, q, "E_SCHEMA"), ({"records": LOG, "as_of": K1, "event_from": D2, "event_to": D1}, q, "E_DATE_ORDER"),
                          ({"records": LOG, "checkpoints": [K2, K1]}, "core.store.replay", "E_INPUT")):
        s.add(op, inp, error=code, cls=E, tags=["invalid"])
    s.write()
    note("store: expected rows hand-written; hashes from the oracle canonical form, one source by nature")


def main():
    rulings()
    store()


if __name__ == "__main__":
    main()
