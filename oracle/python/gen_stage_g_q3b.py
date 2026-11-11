"""Stage G wave 3d, Q3b: AAD ladder of the Hull-White Bermudan swaption on the G-18 reference scheme (ruling G-9).

Goldens: the price and its full ladder (every curve discount factor, `mean_reversion`, `sigma`) by Richardson-extrapolated
central differences of the binary64 scheme (`gen_stage_g_berm.price`), relative bumps h = 1e-4 and 5e-5, exactly the Q3a
reference rule. A second Richardson pair (5e-5, 2.5e-5) must agree with the first within 1e-9 relative, else the case is
dropped (a bump crossed an exercise-boundary node). No outside library differentiates this scheme: not counted (G-18).

    cd oracle/python && uv run python -W ignore gen_stage_g_q3b.py
"""
import copy
import json

from qf_oracle import common
from qf_oracle.common import Suite, note
from gen_stage_g_berm import price

G = "oracle/python/gen_stage_g_q3b.py"
OP = "rates.shortrate.bermudan_ladder"


def paths(inp):
    n = len(inp["curve"]["discount_factors"])
    return [("curve", i) for i in range(n)] + [("mean_reversion", None), ("sigma", None)]


def get(inp, p):
    k, i = p
    return inp["curve"]["discount_factors"][i] if k == "curve" else inp[k]


def bumped(inp, p, f):
    q = copy.deepcopy(inp)
    k, i = p
    if k == "curve":
        q["curve"]["discount_factors"][i] *= f
    else:
        q[k] *= f
    return q


def rich(inp, p, h):
    x = get(inp, p)
    D = lambda hh: (price(bumped(inp, p, 1 + hh)) - price(bumped(inp, p, 1 - hh))) / (2 * hh * x)  # noqa: E731
    return (4 * D(h / 2) - D(h)) / 3


def ladder(inp):
    out, worst = [], 0.0
    for p in paths(inp):
        r1, r2 = rich(inp, p, 1e-4), rich(inp, p, 5e-5)
        worst = max(worst, abs(r1 - r2) / max(abs(r1), 1e-6 * inp["notional"]))
        out.append(r1)
    return out, worst


def main():
    base = json.loads((common.GOLDEN.parent / "stage_g" / "bermudan_g.json").read_text(encoding="utf-8"))["cases"]
    picks = [c for c in base if c["expected"]["status"] == "ok"][:4]
    s = Suite("aadladder_g", "specifications/06-risk/aad-core.md", G)
    for c in picks:
        inp = dict(c["inputs"], grid=dict(c["inputs"]["grid"], nx=101, steps_per_year=50))
        lad, worst = ladder(inp)
        note(f"  {c['case_id']}: Richardson pair agreement {worst:.2e}")
        if worst > 1e-9:
            note("   dropped: bump crossed an exercise node")
            continue
        n = len(inp["curve"]["discount_factors"])
        out = {"price": price(inp), "d_price_d_discount_factors": lad[:n], "d_price_d_mean_reversion": lad[n], "d_price_d_sigma": lad[n + 1]}
        s.add(OP, inp, out, cls="aad_sensitivity", verified=["reference-scheme-float64", "richardson-two-pairs"],
              tags=["aad", "bermudan", "q3b", "synthetic"],
              limit={"absolute": 1e-10, "relative": 1e-8, "reason": "Q3a rule per unit notional (G-9); price at 1e-9 relative"},
              description=f"ladder of {c['case_id']} on nx=101, 50 steps a year")
    e = dict(picks[0]["inputs"], grid=dict(picks[0]["inputs"]["grid"], nx=101, steps_per_year=50))
    s.add(OP, dict(e, sigma=0.0), error="E_DOMAIN", cls="date_and_convention", tags=["invalid", "aad", "synthetic"], description="sigma = 0")
    s.add(OP, dict(e, exercise_times=[]), error="E_INPUT", cls="date_and_convention", tags=["invalid", "aad", "synthetic"], description="no exercise dates")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_g"
    s.write()
    common.GOLDEN = keep


if __name__ == "__main__":
    main()
