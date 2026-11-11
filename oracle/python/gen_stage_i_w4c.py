"""Stage I wave 4c: instrument selection, the best hedge with at most K instruments
(specifications/08-hedging/instrument-selection.md, rulings I-33 on).

Every golden, error codes included, is the output of `sel_ref`: every subset of at most K instruments is solved by the
wave 1 reference (`qp_core`, 50 digits) and the best objective wins, with the I-34 tie rule. The generator asserts that the
runner-up is either an exact tie or more than 1e-9 relative worse, so the choice cannot flip between builds.

Outside: the same enumeration with every subset solved by scipy 1.18 (`linalg.lstsq` without bounds, `lsq_linear` BVLS
with bounds); a case counts if the library's best subset is the same and every output agrees within root_finding.

    cd oracle/python && uv run python -W ignore gen_stage_i_w4c.py
"""
import itertools
import json
from fractions import Fraction as Fr
from pathlib import Path

import mpmath as mp
import numpy as np
import scipy.optimize as so

import gen_stage_i_w1 as W
from gen_stage_i_w1 import fail, decide, run_error, sym_eig, M, RF, EX
from qf_oracle import common
from qf_oracle.common import Suite, note

mp.mp.dps = 50
G = "oracle/python/gen_stage_i_w4c.py"
SPEC = "specifications/08-hedging/instrument-selection.md"
HERE = Path(__file__).resolve().parent
SEL = "hedge.select.solve"
MUT = []


def sub(inp, S):
    q = {"a": [[row[j] for j in S] for row in inp["a"]], "b": inp["b"], "weights": inp["weights"]}
    if "ridge" in inp:
        q["ridge"] = inp["ridge"]
    for k in ("lower", "upper"):
        if k in inp:
            q[k] = [inp[k][j] for j in S]
    return q


def sel_ref(inp, solver=None):
    n = len(inp["a"][0]) if inp["a"] else 0
    if n > 20:
        fail("E_LIMIT")
    W.finite_rule(inp)
    base = {k: v for k, v in inp.items() if k != "max_instruments"}
    m, n, E, f, lo, up, pol = W.qp_validate(base)  # wave 1 checks 1 to 3 (shapes, MIN_NORM, domain)
    K = inp["max_instruments"]
    if not 1 <= K <= n:
        fail("E_INPUT", "max_instruments outside 1..n")
    if any(k in inp for k in ("eq_matrix", "eq_rhs", "singular")):
        fail("E_INPUT", "no equalities or singular policy in selection")
    if any((l is not None and l > 0) or (u is not None and u < 0) for l, u in zip(lo, up)):
        fail("E_DOMAIN", "a bound excludes zero, so an unselected instrument is infeasible")
    # full problem must be regular (I-33): every subset is then regular too
    A, w = M(inp["a"]), [mp.mpf(x) for x in inp["weights"]]
    H = mp.matrix(n, n)
    for i in range(m):
        for p in range(n):
            for q in range(n):
                H[p, q] += A[i, p] * w[i] * A[i, q]
    for p in range(n):
        H[p, p] += mp.mpf(inp.get("ridge", 0.0))
    ev, _ = sym_eig(H)
    if decide(min(ev), max(abs(e) for e in ev), "selection Hessian"):
        fail("E_SINGULAR", "full problem singular")
    solver = solver or (lambda q: W.qp_core(q))
    res = []
    for k in range(1, K + 1):
        for S in itertools.combinations(range(n), k):
            x, r, obj, _ = solver(sub(inp, S))
            res.append((obj, k, S, x, r))
    best = min(o for o, *_ in res)
    tied = [t for t in res if abs(t[0] - best) <= mp.mpf("1e-12") * max(abs(best), mp.mpf("1e-300"))]
    win = min(tied, key=lambda t: (t[1], t[2]))
    return win, tied, res


def sel_out(win, n):
    obj, k, S, x, r = win
    xf = [0.0] * n
    for j, v in zip(S, x):
        xf[j] = float(v)
    return {"selected": list(S), "x": xf, "residual": [float(v) for v in r], "objective": float(obj)}


def sel_api(inp):
    win, tied, res = sel_ref(inp)
    return sel_out(win, len(inp["a"][0]))


def scipy_solver(q):
    A, b, w = np.array(q["a"]), np.array(q["b"]), np.array(q["weights"])
    n = A.shape[1]
    sw = np.sqrt(w)
    At, bt = A * sw[:, None], b * sw
    if q.get("ridge"):
        At = np.vstack([At, np.sqrt(q["ridge"]) * np.eye(n)])
        bt = np.concatenate([bt, np.zeros(n)])
    lo, up = q.get("lower") or [None] * n, q.get("upper") or [None] * n
    lb = np.array([-np.inf if v is None else v for v in lo])
    ub = np.array([np.inf if v is None else v for v in up])
    if np.all(np.isinf(lb)) and np.all(np.isinf(ub)):
        x = np.linalg.lstsq(At, -bt, rcond=None)[0]
    else:
        x = so.lsq_linear(At, -bt, bounds=(lb, ub), method="bvls", tol=1e-15, lsq_solver="exact").x
    r = A @ x + b
    return x, r, float(np.sum(w * r * r) + q.get("ridge", 0.0) * x @ x), None


def suite():
    s = Suite("hedgeselect_i", SPEC, G)
    KR = [[0.45, 0.10, 0.02, 0.00, 0.30], [0.30, 0.85, 0.15, 0.05, 0.40], [0.05, 0.70, 0.60, 0.20, 0.45],
          [0.00, 0.20, 1.10, 0.70, 0.35], [0.00, 0.02, 0.55, 1.20, 0.20]]
    bKR = [-12.0, -25.0, -31.0, -18.0, -7.5]
    w5 = [1.0] * 5
    base = dict(a=KR, b=bKR, weights=w5)
    cases = [
        ("best single bond for a key-rate book", dict(base, max_instruments=1)),
        ("best two of five", dict(base, max_instruments=2)),
        ("best three of five", dict(base, max_instruments=3)),
        ("all five allowed: the full least-squares hedge", dict(base, max_instruments=5)),
        ("two of five, long-only", dict(base, max_instruments=2, lower=[0.0] * 5)),
        ("two of five with a ridge", dict(base, max_instruments=2, ridge=0.5)),
        ("weights on the long key rates change the choice (bond 2, not bond 4)", dict(base, max_instruments=1, weights=[0.01, 0.01, 0.01, 10.0, 10.0])),
        ("exact tie: the lower index wins", dict(a=[[1.0, 0.0], [0.0, 1.0]], b=[-1.0, -1.0], weights=[1.0, 1.0], max_instruments=1)),
        ("greedy selection misses the best pair: the best single instrument is not in it", dict(a=[[1.0, 1.0, 0.0], [1.0, 0.0, 1.0], [1.0, 0.0, 0.0]], b=[-1.0, -1.0, 0.0], weights=[1.0, 1.0, 1.0], max_instruments=2)),
        ("fewer instruments win a tie with more", dict(a=[[1.0, 0.0], [0.0, 1.0]], b=[-2.0, 0.0], weights=[1.0, 1.0], max_instruments=2)),
    ]
    n_out = 0
    for desc, inp in cases:
        win, tied, res = sel_ref(inp)
        out = sel_out(win, len(inp["a"][0]))
        if "tie" in desc:
            assert len(tied) > 1, desc
            assert all(t[0] == win[0] for t in tied), "tie must be exact"
        else:
            assert len(tied) == 1, desc
            rest = sorted(o for o, *_ in res if o != win[0])
            assert not rest or (rest[0] - win[0]) > mp.mpf("1e-9") * max(abs(win[0]), 1), f"{desc}: near tie"
        lib_win, _, _ = sel_ref(inp, scipy_solver)
        lo = sel_out(lib_win, len(inp["a"][0]))
        ok = lo["selected"] == out["selected"] and all(abs(p - q) <= 1e-10 + 1e-10 * abs(q) for p, q in zip(lo["x"] + lo["residual"] + [lo["objective"]], out["x"] + out["residual"] + [out["objective"]]))
        n_out += ok
        if not ok:
            note(f"  hedgeselect not counted: {desc}")
        s.add(SEL, inp, out, cls=RF, output_classes={"selected": EX}, verified=["mpmath-50-subset-enumeration"] + (["scipy-1.18-lstsq-bvls-per-subset"] if ok else []),
              tags=["hedge", "selection"], description=f"{desc} ({len(res)} subsets)")
    # mutant: greedy forward selection (best single instrument, then the best partner) misses the best pair
    gc = cases[8][1]
    g1 = sel_api(dict(gc, max_instruments=1))["selected"][0]
    best2 = s.cases[8]["expected"]["outputs"]
    greedy = min(W.qp_core(sub(gc, tuple(sorted((g1, j)))))[2] for j in range(3) if j != g1)
    assert g1 not in best2["selected"]
    caught_gap = float(greedy) - best2["objective"]
    assert caught_gap > 1e-9
    MUT.append(("greedy forward selection", caught_gap))
    e = dict(base, max_instruments=2)
    errs = [
        (dict(e, max_instruments=0), "E_INPUT", "max_instruments 0"),
        (dict(e, max_instruments=6), "E_INPUT", "max_instruments above n"),
        (dict(e, eq_matrix=[[1.0] * 5], eq_rhs=[0.0]), "E_INPUT", "equalities not allowed in selection"),
        (dict(e, lower=[0.5, None, None, None, None]), "E_DOMAIN", "a lower bound above zero"),
        (dict(e, weights=[1.0, 1.0, -1.0, 1.0, 1.0]), "E_DOMAIN", "negative weight"),
        (dict(a=[[1.0, 1.0, 0.0], [0.5, 0.5, 1.0]], b=[-2.0, -1.0], weights=[1.0, 1.0], max_instruments=1), "E_SINGULAR", "duplicate instruments"),
        (dict(a=[[1.0] * 21], b=[-1.0], weights=[1.0], max_instruments=1), "E_LIMIT", "21 instruments (limit 20)"),
    ]
    for inp, code, desc in errs:
        run_error(s, SEL, sel_api, inp, code, desc, ["hedge", "selection"])
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
    reg[s.name] = {"counted": n_out, "total": len(s.cases), "rule": "the same subset enumeration with every subset solved by scipy 1.18 (lstsq, or lsq_linear BVLS with bounds); same selected set and every output within root_finding"}
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
