"""Stage J integration lane: the active-set rank cut of `hedge.qp.solve` is taken after Jacobi scaling.

Spec: specifications/08-hedging/hedge-solvers.md; ruling specifications/stage-j-rulings.md J-I.1 (applies R6-6.2).

Python's primal active-set step dropped a reduced direction whose squared singular value was at or below 1e-12
times the largest eigenvalue of H, in the caller's units. A 1e-7 exposure against a unit one fell below that cut,
so with any bound present the instrument was treated as absent (x = [0, 0], objective 1, true optimum 0). Java,
C++ and Rust (dual active set on a positive definite, or pre-scaled, Hessian) already returned the true optimum.

Independent oracle: exact rational arithmetic (fractions) on the binary64 inputs. Every pattern of the KKT
conditions is enumerated (each instrument at its lower bound, at its upper bound, at the kink 0, or free on one
side of it); the stationarity system of each pattern is solved exactly and the pattern is kept only when every
primal and subgradient condition holds. H is positive definite and the cost convex, so the KKT point is the unique
minimiser; the generator asserts that every surviving pattern gives the same x. Hand check for case 1:
(1e-7 x1 + 1)^2 + x2^2 with x2 = 0 is zero at x1 = -1e7.

    cd oracle/python && uv run python -W ignore gen_stage_j_qpcut.py
"""
import itertools
from fractions import Fraction as Fr

from qf_oracle import common
from qf_oracle.common import Suite, note

G = "oracle/python/gen_stage_j_qpcut.py"
FOLDER = "stage_j"
SPEC = "specifications/08-hedging/hedge-solvers.md"
OP = "hedge.qp.solve"
LIMIT = {"absolute": 1e-10, "relative": 1e-9,
         "reason": "J-I.1 / R6-6.2: positions near 1e7 against unit ones; relative, as r6/hedgescale_r6"}


def solve(m, v):
    """Exact Gauss-Jordan; None when singular."""
    n = len(v)
    a = [row[:] + [v[i]] for i, row in enumerate(m)]
    for c in range(n):
        p = next((r for r in range(c, n) if a[r][c] != 0), None)
        if p is None:
            return None
        a[c], a[p] = a[p], a[c]
        for r in range(n):
            if r != c and a[r][c] != 0:
                f = a[r][c] / a[c][c]
                a[r] = [x - f * y for x, y in zip(a[r], a[c])]
    return [a[i][n] / a[i][i] for i in range(n)]


def reference(inp):
    a = [[Fr(x) for x in row] for row in inp["a"]]
    b = [Fr(x) for x in inp["b"]]
    w = [Fr(x) for x in inp["weights"]]
    n = len(a[0])
    hs = [Fr(x) for x in inp.get("half_spreads", [0.0] * n)]
    lo = [None if x is None else Fr(x) for x in inp.get("lower", [None] * n)]
    hi = [None if x is None else Fr(x) for x in inp.get("upper", [None] * n)]
    h = [[2 * sum(w[i] * a[i][j] * a[i][k] for i in range(len(b))) for k in range(n)] for j in range(n)]
    g = [2 * sum(w[i] * a[i][j] * b[i] for i in range(len(b))) for j in range(n)]
    found = []
    for pat in itertools.product("LUZPN", repeat=n):
        x, ok, free = [None] * n, True, []
        for j, s in enumerate(pat):
            if s == "L":
                ok &= lo[j] is not None
                x[j] = lo[j]
            elif s == "U":
                ok &= hi[j] is not None
                x[j] = hi[j]
            elif s == "Z":
                ok &= hs[j] > 0
                x[j] = Fr(0)
            elif s == "N":
                ok &= hs[j] > 0  # a smooth instrument is free once, as "P"
                free.append(j)
            else:
                free.append(j)
        if not ok:
            continue
        sign = {j: (-1 if pat[j] == "N" else 1 if hs[j] > 0 else 0) for j in free}
        fixed = [j for j in range(n) if j not in free]
        if free:
            m = [[h[j][k] for k in free] for j in free]
            v = [-(g[j] + sum(h[j][k] * x[k] for k in fixed) + hs[j] * sign[j]) for j in free]
            y = solve(m, v)
            if y is None:
                continue
            for j, val in zip(free, y):
                x[j] = val
        grad = [g[j] + sum(h[j][k] * x[k] for k in range(n)) for j in range(n)]

        for j in range(n):
            ok &= (lo[j] is None or x[j] >= lo[j]) and (hi[j] is None or x[j] <= hi[j])
            if not ok:
                break
            s = pat[j]
            if s in "PN" and hs[j] > 0:
                ok &= (x[j] >= 0) if s == "P" else (x[j] <= 0)
            elif s in "LU" and not (lo[j] is not None and hi[j] is not None and lo[j] == hi[j]):
                up = grad[j] + (hs[j] if x[j] >= 0 else -hs[j])    # right derivative
                down = grad[j] + (hs[j] if x[j] > 0 else -hs[j])   # left derivative
                ok &= up >= 0 if s == "L" else down <= 0
            elif s == "Z":
                ok &= abs(grad[j]) <= hs[j]
        if ok:
            found.append(x)
    assert found, "no KKT point"
    assert all(f == found[0] for f in found), "KKT point not unique"
    x = found[0]
    r = [sum(a[i][j] * x[j] for j in range(n)) + b[i] for i in range(len(b))]
    risk = sum(w[i] * r[i] * r[i] for i in range(len(b)))
    cost = sum(hs[j] * abs(x[j]) for j in range(n))
    out = {"x": [float(v) for v in x], "residual": [float(v) for v in r], "objective": float(risk + cost), "rank": n}
    if "half_spreads" in inp:
        out["risk"], out["cost"] = float(risk), float(cost)
    return out


CASES = [
    (("a = diag(1e-7, 1), x2 fixed at 0 by its bounds: x1 = -1e7, objective 0. The unscaled active-set cut "
      "(1e-12 of the largest eigenvalue of H) dropped x1 and gave [0, 0], objective 1 (J-I.1, R6-6.2)"),
     {"a": [[1e-7, 0.0], [0.0, 1.0]], "b": [1.0, 0.0], "weights": [1.0, 1.0],
      "lower": [None, 0.0], "upper": [None, 0.0]}),
    ("as case 1 with a half spread on x2: the costed (orthant) active set had the same unscaled cut (J-I.1)",
     {"a": [[1e-7, 0.0], [0.0, 1.0]], "b": [1.0, 0.0], "weights": [1.0, 1.0],
      "lower": [None, 0.0], "upper": [None, 0.0], "half_spreads": [0.0, 0.1]}),
    ("half spread 1e-9 on the small column: the kink stops x1 at -9.95e6 (residual 0.005); x2 at the kink (J-I.1)",
     {"a": [[1e-7, 0.0], [0.0, 1.0]], "b": [1.0, 0.0], "weights": [1.0, 1.0],
      "lower": [None, -1.0], "upper": [None, 1.0], "half_spreads": [1e-9, 0.1]}),
    ("box on both instruments, none active at the optimum x = [-1e7, -0.5] (J-I.1)",
     {"a": [[1e-7, 0.0], [0.0, 1.0]], "b": [1.0, 0.5], "weights": [1.0, 1.0],
      "lower": [-2e7, -1.0], "upper": [None, 1.0]}),
]


def build():
    s = Suite("hedgecut_j", SPEC, G)
    for desc, inp in CASES:
        s.add(OP, inp, outputs=reference(inp), cls="root_finding", verified=("fractions KKT enumeration",),
              tags=("stage_j", "hedge", "qp", "scaling", "synthetic"), output_classes={"rank": "date_and_convention"},
              limit=LIMIT, description=desc)
    return [s]


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    for s in build():
        s.write()
    common.GOLDEN = keep
    note("stage J qp cut: 4 value-checked cases")


if __name__ == "__main__":
    main()
