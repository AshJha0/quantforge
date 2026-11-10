"""Q4 open item: per joint system, IFT Jacobian against whole-system bump-and-rebuild; prints the four worst entries.

    cd oracle/python && uv run python -u -W ignore diag_q4_jacobian.py   (about 10 minutes; the full system runs last)
"""
import numpy as np
import gen_stage_f_q4 as G
for desc, inp in G.systems()[::-1]:
    s = G.System(inp)
    x, err = s.solve()
    J, Jx = s.jacobian()
    ref = G.bump_jacobian(inp, 1e-4, x, Jx)
    dev = np.abs(J - ref) - (1e-9 + 1e-6 * np.abs(ref))
    idx = np.dstack(np.unravel_index(np.argsort(-dev.ravel())[:4], dev.shape))[0]
    print(desc[:30], "max dev", dev.max(), flush=True)
    for r, c in idx:
        print("   ", s.labels[r], s.ins[c]["id"], J[r, c], ref[r, c], flush=True)
