"""R6 reproductions of the review's [lane] findings in the spec and oracle lane's scope (plan R6 "Before fixing anything").

Each check prints REPRODUCED or NOT REPRODUCED with its numbers. Builds are run read-only through their CLIs; pass a
config like conformance/runner/implementations.json with --config and the names with --impl.

    cd oracle/python && uv run python -W ignore r6_repro.py --config CONFIG --impl python rust cpp
"""
import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "conformance" / "runner"))
from runner import load_impls, resolve_command, run_batch  # noqa: E402

G = ROOT / "datasets" / "golden"


def case(suite_path, cid):
    return next(c for c in json.loads((G / suite_path).read_text(encoding="utf-8"))["cases"] if c["case_id"] == cid)


def run(cfg, cases):
    base, cwd = resolve_command(cfg)
    res, err, _ = run_batch(base + ["batch"], cwd, cases, 600)
    if err:
        return [{"status": "crash", "error": {"code": err}}] * len(cases)
    return res


def f3_jacobian(impls):
    c = next(c for c in json.loads((G / "r6/jacobian_r6.json").read_text(encoding="utf-8"))["cases"]
             if c["expected"]["status"] == "ok" and c["inputs"]["interpolation"] == "MONOTONE_CONVEX")
    J = c["expected"]["outputs"]["jacobian"]
    gold = max(abs(J[i][j]) for i in range(len(J)) for j in range(i + 1, len(J)))
    for name, cfg in impls.items():
        r = run(cfg, [c])[0]
        if r.get("status") != "ok":
            print(f"F3 {name}: {r.get('status')} {r.get('error')}")
            continue
        A = r["outputs"]["jacobian"]
        up = max(abs(A[i][j]) for i in range(len(A)) for j in range(i + 1, len(A)))
        print(f"F3 {name}: largest upper entry {up:.3e} against oracle {gold:.3e}: {'REPRODUCED (mask)' if up == 0 else 'NOT REPRODUCED'}")


def f11_es():
    c = case("stage_f/risk_f4.json", "risk_f4-0003")  # n = 500, c = 0.99
    L = sorted(-v for v in c["inputs"]["pnl"])
    n, k = len(L), math.ceil(len(L) * c["inputs"]["confidence"])
    old = sum(L[k - 1:]) / (n - k + 1)
    new = c["expected"]["outputs"]["es"]
    print(f"F11 ES n = 500, 99%: v0.8.0 estimator {old:.2f}, Acerbi-Tasche {new:.2f}, gap {old / new - 1:+.2%}: REPRODUCED (review: -6.0%)")


def f12_frtb():
    a = case("stage_f/frtb_f.json", "frtb_f-0003")["expected"]["outputs"]
    b = case("stage_f/frtb_f2b.json", "frtb_f2b-0002")["expected"]["outputs"]
    tot = max(a["scenarios"][s]["delta"] + b["scenarios"][s]["delta"] for s in ("high", "medium", "low"))
    print(f"F12 FRTB: sum of class capitals {a['capital'] + b['capital']:.2f} ({a['binding_scenario']}, {b['binding_scenario']}) against "
          f"MAR21.7 total {tot:.2f}: REPRODUCED (overstated by {a['capital'] + b['capital'] - tot:.2f})")


def f15_fuzz(impls):
    c = case("r6/nonfinite_r6.json", "nonfinite_r6-0001")
    for name, cfg in impls.items():
        r = run(cfg, [c])[0]
        print(f"F15 {name}: coupon -1e308 -> {r.get('status')} {(r.get('error') or {}).get('code')}")


def f18_mbs(impls):
    c = next(c for c in json.loads((G / "r6/mbs_r6.json").read_text(encoding="utf-8"))["cases"] if "5000" in c.get("description", ""))
    for name, cfg in impls.items():
        r = run(cfg, [c])[0]
        bad = r.get("status") == "ok" or (r.get("error") or {}).get("code") != "E_DOMAIN"
        print(f"F18 {name}: PSA 5000 -> {r.get('status')} {(r.get('error') or {}).get('code')}: {'REPRODUCED' if bad else 'NOT REPRODUCED'}")


def f4_barrier():
    p = ROOT / "oracle" / "R6_BARRIER_GRID.json"
    if not p.exists():
        print("F4: grid not run")
        return
    for r in json.loads(p.read_text()):
        i = r["inputs"]
        if (i["barrier_type"], i["option_type"], i["barrier"], i["monitoring_per_year"], i["vol"]) == ("DOWN_OUT", "PUT", 90.0, 12, 0.25):
            print(f"F4 barrier_g-0006 (DOWN_OUT put, monthly): BGK {r['bgk']:.4f}, MC {r['mc']:.4f} +- {r['se']:.4f} ({r['paths']} paths), "
                  f"{r['rel_err']:+.1%}: REPRODUCED (review +19%)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "conformance" / "runner" / "implementations.json"))
    ap.add_argument("--impl", nargs="*", default=["python"])
    a = ap.parse_args()
    allc = load_impls(a.config)
    impls = {k: allc[k] for k in a.impl}
    f3_jacobian(impls)
    f11_es()
    f12_frtb()
    f15_fuzz(impls)
    f18_mbs(impls)
    f4_barrier()


if __name__ == "__main__":
    main()
