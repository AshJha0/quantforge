"""R6-27: the Bermudan ladder (aadladder_g) at several grids. Central differences of the oracle's scheme price
(gen_stage_g_berm.price): absolute bump 1e-6 on each discount factor, relative 1e-4 on mean_reversion and sigma.
Writes oracle/R6_LADDER_GRIDS.json (price and every entry per case and grid, run time per grid).

    cd oracle/python && uv run python -W ignore r6_ladder_grids.py
"""
import copy
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from gen_stage_g_berm import price

HERE = Path(__file__).resolve().parent
GRIDS = [(101, 50), (201, 100), (301, 150), (401, 200), (801, 400)]


def ladder(args):
    inp, nx, spy = args
    q = copy.deepcopy(inp)
    q["grid"] = dict(inp["grid"], nx=nx, steps_per_year=spy)
    t0 = time.time()
    p0 = price(q)
    t_price = time.time() - t0
    out = []
    for i in range(len(q["curve"]["discount_factors"])):
        u, d = copy.deepcopy(q), copy.deepcopy(q)
        u["curve"]["discount_factors"][i] += 1e-6
        d["curve"]["discount_factors"][i] -= 1e-6
        out.append((price(u) - price(d)) / 2e-6)
    for k in ("mean_reversion", "sigma"):
        h = 1e-4 * q[k]
        u, d = dict(q, **{k: q[k] + h}), dict(q, **{k: q[k] - h})
        out.append((price(u) - price(d)) / (2 * h))
    return {"nx": nx, "steps_per_year": spy, "price": p0, "ladder": out, "seconds_per_price": t_price}


def main():
    cases = [c for c in json.loads((HERE.parents[1] / "datasets/golden/stage_g/aadladder_g.json").read_text(encoding="utf-8"))["cases"] if c["expected"]["status"] == "ok"]
    jobs = [(c["inputs"], nx, s) for c in cases for nx, s in GRIDS]
    with ProcessPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(ladder, jobs))
    doc = {"ruling": "R6-27", "entries": "d_price_d_discount_factors[0..m-1], d_price_d_mean_reversion, d_price_d_sigma", "cases": []}
    for k, c in enumerate(cases):
        doc["cases"].append({"case_id": c["case_id"], "grids": res[k * len(GRIDS):(k + 1) * len(GRIDS)]})
    (HERE.parent / "R6_LADDER_GRIDS.json").write_text(json.dumps(doc, indent=1) + chr(10), encoding="utf-8", newline=chr(10))


if __name__ == "__main__":
    main()
