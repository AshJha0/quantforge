#!/usr/bin/env python3
"""Tutorial 12 through any language's CLI: American puts, a barrier call, Heston and local-vol calls.

  python examples/tutorial_exotics.py rust/target/release/quantforge
  python examples/tutorial_exotics.py java -jar java25/target/quantforge-cli.jar

Standard library only. It sends the cases of docs/getting-started/tutorial-12-exotics.md to
`quantforge batch` and prints the same lines as the Python section of the tutorial.
"""
import json
import math
import shutil
import subprocess
import sys

S, K, T, R, Q, VOL = 100.0, 100.0, 1.0, 0.05, 0.02, 0.25
COMMON = {"spot": S, "strike": K, "expiry_years": T, "rate": R, "dividend_yield": Q, "vol": VOL}
BS = {"model": "BLACK_SCHOLES", "strike": K, "expiry_years": T, "spot": S, "rate": R, "yield": Q}
BARRIER = {**COMMON, "option_type": "CALL", "barrier": 90.0, "rebate": 0.0, "barrier_type": "DOWN_OUT"}
HESTON = {"v0": 0.0625, "kappa": 1.5, "theta": 0.0625, "xi": 0.5, "rho": -0.7}
SURFACE = [{"expiry_years": 1.0, "svi": {"a": 0.035, "b": 0.11, "rho": -0.35, "m": 0.03, "sigma": 0.25}}]


def case(case_id, operation, inputs):
    return {"schema_version": "1.0", "case_id": case_id, "operation": operation, "inputs": inputs}


def batch(cli, cases):
    text = "".join(json.dumps(c) + "\n" for c in cases)
    p = subprocess.run(cli, input=text, capture_output=True, text=True, check=True)
    results = [json.loads(line) for line in p.stdout.splitlines() if line.strip()]
    for r in results:
        if r["status"] != "ok":
            raise SystemExit(f"{r['case_id']}: {r['error']}")
    return [r["outputs"] for r in results]


def main(cli):
    cli = [shutil.which(cli[0]) or cli[0], *cli[1:], "batch"]  # finds quantforge.exe on Windows
    k = math.log(K / (S * math.exp((R - Q) * T)))  # forward log-moneyness of the strike
    put = {**COMMON, "option_type": "PUT"}
    euro, baw, crr, fd, call, cont, daily, weekly, hes, lv = batch(cli, [
        case("t12-euro", "vol.option.price", {**BS, "option_type": "PUT", "vol": VOL}),
        case("t12-baw", "exotic.american.baw", put),
        case("t12-crr", "exotic.american.crr", {**put, "steps": 200}),
        case("t12-fd", "exotic.american.fd",
             {**put, "exercise": "AMERICAN", "grid": {"nx": 201, "nt": 200, "width": 5.0}}),
        case("t12-call", "vol.option.price", {**BS, "option_type": "CALL", "vol": VOL}),
        case("t12-cont", "exotic.barrier.price", BARRIER),
        case("t12-daily", "exotic.barrier.price",
             {**BARRIER, "monitoring": "DISCRETE", "monitoring_per_year": 252}),
        case("t12-weekly", "exotic.barrier.price",
             {**BARRIER, "monitoring": "DISCRETE", "monitoring_per_year": 52}),
        case("t12-heston", "vol.heston.price",
             {"spot": S, "strikes": [K], "expiry_years": T, "rate": R, "dividend_yield": Q,
              "heston": HESTON, "option_type": "CALL"}),
        case("t12-dupire", "vol.local.dupire",
             {"slices": SURFACE, "points": [{"expiry_years": T, "log_moneyness": k}]}),
    ])
    iv = lv["implied_vol"][0]
    [lv_call] = batch(cli, [case("t12-lvcall", "vol.option.price", {**BS, "option_type": "CALL", "vol": iv})])
    print(f"European put (BS)   {euro['price']:.6f}")
    print(f"American put BAW    {baw['price']:.6f}")
    print(f"American put CRR200 {crr['american']:.6f}")
    print(f"American put FD     {fd['price']:.6f}")
    print(f"Vanilla call (BS)   {call['price']:.6f}")
    print(f"Down-out continuous {cont['price']:.6f}")
    print(f"Down-out daily      {daily['price']:.6f}")
    print(f"Down-out weekly     {weekly['price']:.6f}")
    print(f"Heston call         {hes['prices'][0]:.6f}")
    print(f"Surface vol {iv:.6f} local vol {lv['local_vol'][0]:.6f}")
    print(f"Local-vol call      {lv_call['price']:.6f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
