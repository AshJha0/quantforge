#!/usr/bin/env python3
"""Tutorial 13 through any language's CLI: fit GARCH(1,1), forecast vol, build a VIX-style index.

  python examples/tutorial_vol_indices.py rust/target/release/quantforge
  python examples/tutorial_vol_indices.py java -jar java25/target/quantforge-cli.jar

Standard library only. It sends the cases of docs/getting-started/tutorial-13-vol-indices.md to
`quantforge batch` and prints the same lines as the Python section of the tutorial. Inputs are
synthetic and come from golden cases garch_e-0028, garch_f-0009 and vix_e-0007, and from
examples/vol_forward_term_e.json.
"""
import json
import math
import shutil
import subprocess
import sys


def golden(path, case_id):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    cases = data["cases"] if isinstance(data, dict) else data
    return next(c["inputs"] for c in cases if c["case_id"] == case_id)


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
    r250 = golden("datasets/golden/stage_e_b/garch_e.json", "garch_e-0028")["returns"]
    r2000 = golden("datasets/golden/stage_f/garch_f.json", "garch_f-0009")["returns"]
    vix = golden("datasets/golden/stage_e_b/vix_e.json", "vix_e-0007")
    with open("examples/vol_forward_term_e.json", encoding="utf-8") as f:
        term = json.load(f)["inputs"]

    fit, est = batch(cli, [
        case("t13-fit", "vol.garch.fit", {"returns": r250, "initial_variance": "SAMPLE"}),
        case("t13-est", "vol.garch.estimate", {"returns": r2000, "initial_variance": "SAMPLE",
                                               "distribution": "NORMAL", "demean": False})])
    weights = {k: est[k] for k in ("omega", "alpha", "beta")}
    [ll] = batch(cli, [case("t13-ll", "vol.garch.loglik",
                            {"returns": r2000, "initial_variance": "SAMPLE", **weights})])
    nxt = ll["next_variance"]
    fc, near, index, fwd = batch(cli, [
        case("t13-fc", "vol.garch.forecast", {**weights, "next_variance": nxt, "horizon": 21,
                                              "periods_per_year": 252.0}),
        case("t13-near", "vol.vix.term_variance", vix["near"]),
        case("t13-index", "vol.vix.index", vix),
        case("t13-fwd", "vol.forward.vol", term)])
    se = est["std_errors"]

    print(f"fit loglik, 250 returns  {fit['loglik']:.4f}")
    print(f"omega {est['omega']:.4e}  SE {se['omega']:.3e}")
    print(f"alpha {est['alpha']:.6f}  SE {se['alpha']:.6f}")
    print(f"beta  {est['beta']:.6f}  SE {se['beta']:.6f}")
    print(f"persistence {est['persistence']:.6f}")
    print(f"next-day vol, annualised {math.sqrt(nxt * 252):.4f}")
    print(f"21-day forecast vol      {fc['annualized_vol']:.4f}")
    print(f"long-run vol             {math.sqrt(fc['long_run_variance'] * 252):.4f}")
    print(f"near forward {near['forward']:.4f}  K0 {near['k0']:.1f}")
    print(f"near variance {index['near_variance']:.6f}  next variance {index['next_variance']:.6f}")
    print(f"VIX-style index {index['index']:.4f}")
    print("forward vols " + " ".join(f"{v:.4f}" for v in fwd["forward_vols"]))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
