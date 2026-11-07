"""R1 rulings R1-3 (conversion factor) and R1-4 (CDS discount interpolation). Suite stage_d/rulings_r1.

Conversion factors are rounded to 4 decimals; the generator stops if a raw value lies within 1e-6 of a rounding boundary,
so pow rounding in another language cannot move a result.
"""
import json
import math
from datetime import date

from qf_oracle.common import ROOT, note
import gen_stage_d as D
from gen_stage_d import E, S, write

G = "oracle/python/gen_r1_rulings.py"
WHOLE = {"TWO_YEAR", "THREE_YEAR", "FIVE_YEAR"}


def cf(b, delivery_month, contract):
    deliv = date.fromisoformat(delivery_month + "-01")
    mat = date.fromisoformat(b["maturity"])
    months = (mat.year - deliv.year) * 12 + mat.month - deliv.month
    n, z = divmod(months, 12)
    if (contract or "TEN_YEAR") not in WHOLE:
        z = z // 3 * 3
    c = math.floor(b["coupon"] * 800 + 0.5) / 800
    v = z if z < 7 else z - 6
    a = 1 / 1.03 ** (v / 6)
    bb = c / 2 * (6 - v) / 6
    C = 1 / 1.03 ** (2 * n) if z < 7 else 1 / 1.03 ** (2 * n + 1)
    raw = a * (c / 2 + c / .06 * (1 - C) + C) - bb
    frac = raw * 1e4 - math.floor(raw * 1e4)
    assert abs(frac - .5) > 1e-2, ("near a rounding boundary", b, contract, raw)
    return round(raw, 4)


def main():
    s = S("rulings_r1", "r1-rulings.md")
    s.generator = G
    op = "bond.futures.conversion_factor"
    rows = [
        ({"maturity": "2031-10-31", "coupon": .04125, "frequency": 2}, "2026-12", "FIVE_YEAR", "whole months, z = 10"),
        ({"maturity": "2031-11-30", "coupon": .0400, "frequency": 2}, "2026-12", "FIVE_YEAR", "whole months, z = 11"),
        ({"maturity": "2028-11-30", "coupon": .03875, "frequency": 2}, "2026-12", "TWO_YEAR", "whole months, z = 11"),
        ({"maturity": "2029-11-15", "coupon": .0350, "frequency": 2}, "2026-12", "THREE_YEAR", "whole months, z = 11"),
        ({"maturity": "2031-10-31", "coupon": .04125, "frequency": 2}, "2026-12", "TEN_YEAR", "same bond as the first, z rounded down to 9"),
        ({"maturity": "2033-11-15", "coupon": .0425, "frequency": 2}, "2026-12", None, "null means TEN_YEAR (stage D value)"),
        ({"maturity": "2055-05-15", "coupon": .0475, "frequency": 2}, "2026-12", "ULTRA_BOND", "z rounded down to a multiple of 3"),
        ({"maturity": "2033-11-15", "coupon": .04210, "frequency": 2}, "2026-12", "TEN_YEAR", "coupon 4.21% rounds to 4.25%"),
        ({"maturity": "2033-11-15", "coupon": .04180, "frequency": 2}, "2026-12", "TEN_YEAR", "coupon 4.18% rounds to 4.125%"),
    ]
    for b, dm, k, why in rows:
        s.add(op, {"bond": b, "delivery_month": dm, "notional_coupon": .06, "contract": k}, {"conversion_factor": cf(b, dm, k)}, cls=E,
              verified=["cme-formula", "hand"], tags=["ruling", "R1-3", "bond-futures"], description=why)
    s.add(op, {"bond": rows[0][0], "delivery_month": "2026-12", "notional_coupon": .06, "contract": "SEVEN_YEAR"}, error="E_SCHEMA", cls=E,
          tags=["ruling", "R1-3", "invalid"], description="contract not listed")
    # R1-4: a non-LOG_LINEAR_DF discount curve is E_INPUT in every credit operation, before other rule checks.
    cr = json.loads((ROOT / "datasets" / "golden" / "stage_d" / "credit_d.json").read_text(encoding="utf-8"))["cases"]
    done = set()
    for c in cr:
        if c["expected"]["status"] != "ok" or c["operation"] in done:
            continue
        done.add(c["operation"])
        inp = json.loads(json.dumps(c["inputs"]))
        inp["discount"]["interpolation"] = "LINEAR_ZERO"
        s.add(c["operation"], inp, error="E_INPUT", cls=E, tags=["ruling", "R1-4", "invalid"], description=f"LINEAR_ZERO discount curve (from {c['case_id']})")
        if c["operation"] == "credit.cds.price":
            bad = json.loads(json.dumps(inp))
            bad["recovery"] = 1.5
            s.add(c["operation"], bad, error="E_INPUT", cls=E, tags=["ruling", "R1-4", "invalid", "order"],
                  description="interpolation is checked before recovery (which alone would be E_DOMAIN)")
    assert done == {"credit.cds.price", "credit.cds.bootstrap", "credit.index.intrinsic", "credit.curve.composite"}, done
    write(s)
    note(f"rulings_r1: {len(s.cases)} cases (R1-3 conversion factor, R1-4 CDS discount interpolation)")


if __name__ == "__main__":
    main()
