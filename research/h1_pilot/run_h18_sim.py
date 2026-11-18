"""H-18 minimum (owner decision 2026-11-18): run the Avellaneda-Stoikov quoting code
(micro.mm.as_quotes, stage-h commit 5202d98f, unchanged) on SIMULATED data only. No recorded data
is read. The H18-01 prereg is an UNSIGNED DRAFT; nothing here is a result of that study.

Simulation as in [AS08] section 3.3: mid is arithmetic Brownian motion, s0 = 100, T = 1,
sigma = 2, dt = 0.005, k = 1.5, A = 140; a quote at distance delta from mid is filled in a step
with probability A exp(-k delta) dt. The inventory strategy (as_quotes) is compared with the
symmetric strategy that uses the same spread centred on the mid. Seed 20261118, 1,000 paths.

    flock ~/qf-wsl.lock python3 -I research/h1_pilot/run_h18_sim.py OUT_JSON
"""

import json
import math
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "python"))
sys.path.insert(0, HERE)
import stage_h_execution_5202d98f as ex  # noqa: E402

S0, T, SIGMA, DT, K, A, PATHS, SEED = 100.0, 1.0, 2.0, 0.005, 1.5, 140.0, 1000, 20261118


def path(rng, gamma, symmetric):
    s, x, q, t = S0, 0.0, 0, 0.0
    for _ in range(int(round(T / DT))):
        o = ex.as_quotes(s, q, gamma, SIGMA, T - t, K)
        bid, ask = o["bid"], o["ask"]
        if symmetric:
            bid, ask = s - o["spread"] / 2, s + o["spread"] / 2
        if rng.random() < A * math.exp(-K * (s - bid)) * DT:
            q, x = q + 1, x - bid
        if rng.random() < A * math.exp(-K * (ask - s)) * DT:
            q, x = q - 1, x + ask
        s += SIGMA * math.sqrt(DT) * (1 if rng.random() < 0.5 else -1)  # binomial step, [AS08]
        t += DT
    return x + q * s, q


def main(out):
    res = {"label": "simulated data only; no recorded data; H18-01 prereg is an unsigned draft",
           "params": {"s0": S0, "T": T, "sigma": SIGMA, "dt": DT, "k": K, "A": A,
                      "paths": PATHS, "seed": SEED}, "runs": {}}
    for gamma in (0.01, 0.1, 1.0):
        for name, sym in (("inventory", False), ("symmetric", True)):
            rng = random.Random(SEED)
            pl, qs = zip(*(path(rng, gamma, sym) for _ in range(PATHS)))
            res["runs"][f"gamma={gamma} {name}"] = {
                "spread_at_half_horizon": ex.as_quotes(S0, 0, gamma, SIGMA, T / 2, K)["spread"],
                "profit_mean": statistics.fmean(pl), "profit_std": statistics.stdev(pl),
                "final_q_mean": statistics.fmean(qs), "final_q_std": statistics.stdev(qs)}
    with open(out, "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)


if __name__ == "__main__":
    main(sys.argv[1])
