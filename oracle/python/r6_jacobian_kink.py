"""R6-1.3 follow-up: does the 1 bp Jacobian gap under SOFR MONOTONE_CONVEX and HYBRID shrink with the bump?
Central and one-sided quotients of the worst entries at 1, 0.5, 0.1, 0.01 bp. Writes oracle/R6_JACOBIAN_KINK.json.

    cd oracle/python && uv run python -W ignore r6_jacobian_kink.py
"""
import json
from pathlib import Path

import gen_r6_w1 as W
import gen_stage_f_q1 as Q1

W._estr()
out = []
for kind, kw, ij in (("MONOTONE_CONVEX", {}, (10, 9)), ("HYBRID", {"step_end_idx": 2}, None)):
    i, j = ij or (0, 0)
    q = Q1.QUOTES["SOFR"]
    z0 = W.zeros_at("SOFR", kind, q, kw)[1]
    if kind == "HYBRID":  # worst entry from the cached 1 bp and 0.5 bp Jacobians
        c = json.loads((Path(__file__).parent / ".r6_jac_cache" / "SOFR_HYBRID.json").read_text())
        R = [[(4 * b - a) / 3 for a, b in zip(ra, rb)] for ra, rb in zip(c["J"], c["Jh"])]
        i, j = max(((r, k) for r in range(len(R)) for k in range(len(R))), key=lambda t: abs(c["J"][t[0]][t[1]] - R[t[0]][t[1]]))
    rows = []
    for hbp in (1.0, 0.5, 0.1, 0.01):
        h = hbp * 1e-4
        up = W.zeros_at("SOFR", kind, [(t, r + (h if k == j else 0.0)) for k, (t, r) in enumerate(q)], kw)[1][i]
        dn = W.zeros_at("SOFR", kind, [(t, r - (h if k == j else 0.0)) for k, (t, r) in enumerate(q)], kw)[1][i]
        rows.append({"bump_bp": hbp, "central": (up - dn) / (2 * h), "forward": (up - z0[i]) / h, "backward": (z0[i] - dn) / h})
        print(kind, (i, j), rows[-1], flush=True)
    out.append({"interpolation": kind, "entry": [i, j], "rows": rows})
(Path(__file__).resolve().parent.parent / "R6_JACOBIAN_KINK.json").write_text(json.dumps(out, indent=1) + chr(10), encoding="utf-8", newline=chr(10))
