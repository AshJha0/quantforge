#!/usr/bin/env python3
"""A fake implementation for testing the runner. It is not an implementation of anything.

It replays expected values from the golden files, so that the runner can be tested without any
financial code. Modes: replay (all correct), perturb (numbers nudged by --by), wrong_error,
drop_key, extra_key, unsupported, crash, short, nan, bad_contract.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def golden(root):
    idx = {}
    for p in Path(root).rglob("*.json"):
        for c in json.loads(p.read_text(encoding="utf-8"))["cases"]:
            idx[c["case_id"]] = c
    return idx


def nudge(v, by):
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        return v + by * max(1.0, abs(v))
    if isinstance(v, list):
        return [nudge(x, by) for x in v]
    return {k: nudge(x, by) for k, x in v.items()}


def answer(case, idx, mode, by):
    cid = case["case_id"]
    g = idx.get(cid)
    if mode == "unsupported" or g is None:
        return {"schema_version": "1.0", "case_id": cid, "status": "error", "error": {"code": "E_UNSUPPORTED_OPERATION", "message": "stub"}}
    if "expected" in case:
        raise SystemExit("the runner leaked expected values")
    exp = g["expected"]
    if exp["status"] == "same_as":
        r = answer(dict(case, case_id=exp["case_id"]), idx, mode, by)
        return dict(r, case_id=cid)
    if exp["status"] == "any":
        exp = {"status": "error", "error_code": "E_INPUT"}
    if exp["status"] == "error":
        code = "E_WRONG" if mode == "wrong_error" else exp["error_code"]
        return {"schema_version": "1.0", "case_id": cid, "status": "error", "error": {"code": code, "message": "stub"}}
    outs = dict(exp["outputs"])
    if mode == "perturb":
        outs = nudge(outs, by)
    if mode == "drop_key":
        outs.pop(next(iter(outs)))
    if mode == "extra_key":
        outs["surprise"] = 1
    r = {"schema_version": "1.0", "case_id": cid, "status": "ok", "outputs": outs, "diagnostics": {}}
    return r


def main():
    a = sys.argv[1:]
    golden_dir = a[a.index("--golden") + 1] if "--golden" in a else str(ROOT / "datasets" / "golden")
    mode = a[a.index("--mode") + 1] if "--mode" in a else "replay"
    by = float(a[a.index("--by") + 1]) if "--by" in a else 1e-6
    cmd = a[-1]
    if cmd == "version":
        print(json.dumps({"language": "stub", "implementation_version": "0", "toolchain": "python",
                          "contract_version": "0.0.0" if mode == "bad_contract" else "1.0.0"}))
        return 0
    if cmd != "batch":
        return 64
    if mode == "crash":
        print("boom", file=sys.stderr)
        return 70
    idx = golden(golden_dir)
    lines = sys.stdin.buffer.read().decode("utf-8").splitlines()
    if mode == "short":
        lines = lines[:-1]
    out = []
    for line in lines:
        r = answer(json.loads(line), idx, mode, by)
        s = json.dumps(r, ensure_ascii=False)
        out.append(s.replace("0.5", "NaN", 1) if mode == "nan" and '"outputs"' in s else s)
    sys.stdout.buffer.write(("\n".join(out) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
