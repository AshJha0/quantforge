"""R6-2 step 1: map the BGK error against exact-date Monte Carlo on a grid, before the envelope is ruled.

Writes oracle/R6_BARRIER_GRID.json: per case the BGK price (the v0.8.0 golden formula, gen_stage_g_w1.r9_price), the MC
price and standard error (qf_oracle.mc_barrier, 1,000,000 antithetic paths, seed 20261112), the relative error, the
number of dates n and the distance x = |ln(S/H)| / (v sqrt(dt)) in monitoring standard deviations.

    cd oracle/python && uv run python -W ignore r6_barrier_envelope.py   (about an hour; run detached with a log)
"""
import json
import math
import sys
from pathlib import Path

from qf_oracle import mc_barrier as M
import gen_stage_g_w1 as W

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "R6_BARRIER_GRID.json"


def grid():
    base = dict(spot=100.0, strike=100.0, expiry_years=1.0, rate=0.05, dividend_yield=0.02, rebate=0.0, monitoring="DISCRETE")
    for vol in (0.25, 0.4):
        for bt, Hs in (("DOWN_OUT", (80.0, 90.0, 95.0)), ("UP_OUT", (110.0, 120.0, 130.0))):
            for ot in ("CALL", "PUT"):
                for H in Hs:
                    for m in (252, 52, 12, 4):
                        yield dict(base, vol=vol, barrier_type=bt, option_type=ot, barrier=H, monitoring_per_year=m)


def main(pairs=500_000):
    rows = json.loads(OUT.read_text()) if OUT.exists() else []
    seen = {json.dumps(r["inputs"], sort_keys=True) for r in rows}
    for inp in grid():
        key = json.dumps(inp, sort_keys=True)
        if key in seen:
            continue
        n = M.n_dates(inp["monitoring_per_year"], inp["expiry_years"])
        dt = inp["expiry_years"] / n
        bgk = W.r9_price(inp)
        mc, se, paths = M.price(inp, pairs)
        rows.append({"inputs": inp, "n": n, "x": abs(math.log(inp["spot"] / inp["barrier"])) / (inp["vol"] * math.sqrt(dt)),
                     "bgk": bgk, "mc": mc, "se": se, "paths": paths, "rel_err": (bgk - mc) / mc if mc else None, "z": (bgk - mc) / se if se else None})
        OUT.write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8", newline="\n")
        r = rows[-1]
        print(f"{inp['barrier_type']} {inp['option_type']} H={inp['barrier']} m={inp['monitoring_per_year']} vol={inp['vol']}: "
              f"BGK {bgk:.5f} MC {mc:.5f} +- {se:.5f} rel {r['rel_err']:+.2%} x {r['x']:.2f}", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 500_000)
