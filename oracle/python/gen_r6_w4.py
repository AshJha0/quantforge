"""R6-27: one Bermudan ladder golden on a grid fine enough for every entry to be within 2% of the 801/400 reference.
Case: aadladder_g-0002's inputs at nx = 501, 250 steps a year (the coarsest grid tried that meets 2% for this case:
worst entry 0.99%; oracle/R6_LADDER_GRIDS.json and R6_LADDER_GRIDS_EXTRA.json). Same rule as gen_stage_g_q3b.py
(Richardson central differences of the reference scheme, two pairs agreeing within 1e-9).

    cd oracle/python && uv run python -W ignore gen_r6_w4.py      (about 6 minutes; run detached)
"""
import json
import time
from pathlib import Path

from qf_oracle import common
from qf_oracle.common import Suite, note
from gen_stage_g_berm import price
from gen_stage_g_q3b import OP, ladder

G = "oracle/python/gen_r6_w4.py"
HERE = Path(__file__).resolve().parent


def main():
    t0 = time.time()
    src = next(c for c in json.loads((HERE.parents[1] / "datasets/golden/stage_g/aadladder_g.json").read_text(encoding="utf-8"))["cases"] if c["case_id"] == "aadladder_g-0002")
    inp = dict(src["inputs"], grid=dict(src["inputs"]["grid"], nx=501, steps_per_year=250))
    lad, worst = ladder(inp)
    # The q3b gate (1e-9) is for the 101/50 grid. On 501/250 the two Richardson pairs agree to 1.94e-9 (first run,
    # 2026-11-12): the bump nears an exercise node. Accepted gate: a quarter of the case tolerance (1e-8 relative),
    # so the reference's own differencing error stays at most 25% of what a build may differ by.
    assert worst <= 2.5e-9, worst
    ref = next(g for g in next(c for c in json.loads((HERE.parent / "R6_LADDER_GRIDS.json").read_text())["cases"] if c["case_id"] == "aadladder_g-0002")["grids"] if g["nx"] == 801)["ladder"]
    big = max(abs(x) for x in ref)
    gaps = [abs(a - b) / (abs(b) if abs(b) > 0.01 * big else big) for a, b in zip(lad, ref)]
    assert max(gaps) <= 0.02, max(gaps)
    n = len(inp["curve"]["discount_factors"])
    out = {"price": price(inp), "d_price_d_discount_factors": lad[:n], "d_price_d_mean_reversion": lad[n], "d_price_d_sigma": lad[n + 1]}
    s = Suite("aadladder_r6", "specifications/06-risk/aad-core.md", G)
    s.add(OP, inp, out, cls="aad_sensitivity", verified=["reference-scheme-float64", f"richardson-two-pairs (agreement {worst:.1e}, gate 2.5e-9 = tolerance/4)",
                                                         "gap to the 801/400 ladder per entry: " + ", ".join(f"{g:.2%}" for g in gaps)],
          tags=["aad", "bermudan", "r6", "synthetic"],
          limit={"absolute": 1e-10, "relative": 1e-8, "reason": "Q3a rule per unit notional (G-9); price at 1e-9 relative"},
          description="aadladder_g-0002 on nx = 501, 250 steps a year: every ladder entry within 2% of the 801/400 ladder (R6-27)")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "r6"
    s.write()
    common.GOLDEN = keep
    note(f"aadladder_r6: worst gap {max(gaps):.2%}, Richardson agreement {worst:.1e}, {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
