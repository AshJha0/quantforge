"""Stage K follow-up to PT-6 (2026-11-22): AAD gradients of `xva.sens.aad` on `xva.adjustments.value` at tiny and
zero hazard. Writes datasets/golden/stage_k/aadtiny_k.json.

Plain idea: PT-6 (KR-350) moved the G-41 bucket default probability to the cancellation-free form
`S(t_(i-1)) (1 - e^(-h dt_i))` and pinned the values at h = 1e-9 and h = 0 (suite g41tiny_k), but added no gradient
goldens there. At h = 1e-9 most gradient entries are of order h, so an adjoint that still forms
`S(t_(i-1)) - S(t_i)` would lose about 9 of 16 digits in them. These cases pin the gradients.

Oracle: the KR-265 rule of gen_stage_k_aadadj.py, reused unchanged: the G-41 forward at 50 digits on the exact
binary64 inputs, every input bumped centrally by d = 1e-12 max(1, |x|) and d / 2 and Richardson-combined, and the
hand-derived closed-form adjoint evaluated at 50 digits must agree with the bump to 1e-30 of max(1, |entry|) before
anything is written. At h = 1e-9 the bump d = 1e-12 is 1e-3 of h; the functions are entire in h, so the truncation
is still of order d^4 (no singularity near h = 0) and the 50-digit forward has no cancellation to speak of.
As a third check the hazard-rate entries are also differentiated with mpmath's own `mp.diff` at 50 digits.

The tolerance below was committed before any expected value was computed (commit "aadtiny: tolerance first").

    cd oracle/python && uv run python gen_stage_k_aadtiny.py
"""
import json

import mpmath as mp

import gen_stage_k_aadadj as A
from qf_oracle import common
from qf_oracle.common import Suite, note

G = "oracle/python/gen_stage_k_aadtiny.py"
SPEC = A.SPEC
OP = A.OP
# Committed before the values. KR-265's limit is 1e-12 absolute + 1e-10 relative; at h = 1e-9 many entries are of
# order 1e-10 to 1e-7, where a 1e-12 absolute floor would hide a loss of 3 to 6 digits. So the relative part stays
# 1e-10 (a derivative exact to rounding, as KR-265) and the absolute floor drops to 1e-20, below every nonzero entry
# by many orders; at h = 0 the entries that are exactly 0 (bucket probability exactly 0) must come out 0 to 1e-20.
LIMIT = {"absolute": 1e-20, "relative": 1e-10,
         "reason": "KR-265 relative 1e-10 kept; absolute floor 1e-20 because entries at h = 1e-9 are of order h "
                   "(KR-350 follow-up, tolerance committed before the values)"}
TAGS = ("stage_k", "xva", "aad", "sensitivities", "tiny-hazard", "synthetic")
VERIFIED = ("mpmath-50", A.ORACLE, A.ADJOINT, "mpmath-50 mp.diff on the hazard-rate entries")

BASE = {"times": [0.5, 1.0, 1.5, 2.0], "discount_factors": [0.985, 0.97, 0.955, 0.94],
        "ee": [120.0, 150.0, 130.0, 80.0], "ene": [-60.0, -90.0, -100.0, -70.0]}
EXTRA = {"im": [50.0, 55.0, 60.0, 40.0], "im_spread": 0.005, "capital": [30.0, 32.0, 28.0, 20.0], "hurdle_rate": 0.1}
# (description, h_c, h_b, exclude_dva_overlap, lend_spread, with im and capital)
CASES = [
    ("both names h = 1e-9: full gradient of cva, dva, fca, fba, fva", 1e-9, 1e-9, False, 0.012, False),
    ("counterparty h = 1e-9, own h = 0.02, overlap excluded (0.02 - 0.012 > 0, linear branch), im and capital",
     1e-9, 0.02, True, 0.02, True),
    ("counterparty h = 0, own h = 1e-9, overlap excluded (0.012 - 6e-10 > 0, linear branch)", 0.0, 1e-9, True,
     0.012, False),
    ("counterparty h = 0.02, own h = 0: dva 0, own-hazard entries the analytic ones at 0", 0.02, 0.0, False, 0.012,
     False),
    ("both names h = 0, overlap excluded, im and capital: cva = dva = 0", 0.0, 0.0, True, 0.012, True),
]


def inputs(hc, hb, excl, sl, extra):
    x = {**json.loads(json.dumps(BASE)), "counterparty": {"hazard_rate": hc, "recovery": 0.4},
         "own": {"hazard_rate": hb, "recovery": 0.4},
         "funding": {"borrow_spread": 0.008, "lend_spread": sl, "exclude_dva_overlap": excl}}
    if extra:
        x.update(json.loads(json.dumps(EXTRA)))
    return x


def diff_check(inp, out):
    """Third check: d/dh of each output by mp.diff (flat hazard, both buckets moved together)."""
    p, branch = A.params(inp), A.active_branch(inp)
    n = len(p["t"])
    for key, f in (("counterparty.hazard_rate", "hc"), ("own.hazard_rate", "hb")):
        h0 = p[f][0]
        for o in out["gradient"]:
            g = mp.diff(lambda h: A.forward({**p, f: [h] * n}, branch)[o], h0)
            ref = out["gradient"][o][key]
            assert abs(g - mp.mpf(ref)) <= mp.mpf("1e-15") * max(mp.mpf("1e-300"), abs(g)) + mp.mpf("1e-40"), \
                (o, key, g, ref)


def build():
    s = Suite("aadtiny_k", SPEC, G)
    first = None
    for desc, hc, hb, excl, sl, extra in CASES:
        inp = inputs(hc, hb, excl, sl, extra)
        out = A.gradient(inp)
        diff_check(inp, out)
        s.add(OP, A.req(inp), out, cls="aad_sensitivity", verified=VERIFIED, tags=TAGS, limit=LIMIT,
              description=f"KR-350 follow-up: {desc}")
        first = first or out
    return s, first


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_k"
    s, o1 = build()
    s.write()
    common.GOLDEN = keep
    g = o1["gradient"]["cva"]
    note(f"aadtiny_k-0001 cva {o1['cva']!r}; d cva / d h_c {g['counterparty.hazard_rate']!r}; "
         f"d cva / d ee[0] {g['ee'][0]!r}")


if __name__ == "__main__":
    main()
