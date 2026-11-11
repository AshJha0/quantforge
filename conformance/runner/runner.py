#!/usr/bin/env python3
"""Neutral conformance runner. Standard library only. Holds no financial logic.

It sends each golden case to an implementation's CLI in batch mode, then compares the JSON that
comes back with the expected values, using the classes in conformance/tolerances/policy.yaml.

Usage: runner.py --impl NAME [--suite GLOB] [--report DIR] [--golden DIR] [--config FILE]
Exit status: 0 all pass, 1 any failure or crash, 2 bad usage or bad golden file.
A case the build does not support counts as not implemented: reported, and not a pass.
"""
import argparse
import datetime
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONTRACT = "1.11.0"  # ruling I-51 (stage I); every build reports this value


def load_policy(path):
    """Reads the small two-level subset of YAML the policy file uses, so the runner needs no packages."""
    classes, current = {}, None
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip() or line.strip() == "classes:":
            continue
        indent = len(line) - len(line.lstrip())
        key, _, val = line.strip().partition(":")
        val = val.strip().strip('"')
        if indent == 2:
            current = classes.setdefault(key, {})
        elif indent == 4 and current is not None:
            if val in ("true", "false"):
                current[key] = val == "true"
            else:
                try:
                    current[key] = float(val)
                except ValueError:
                    current[key] = val
    return classes


def load_impls(path):
    """implementations.json: {"name": {"command": [...], "cwd": optional}}."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve_command(cfg, root=ROOT, windows=None):
    """Returns (argv, cwd). cwd is relative to the repo root, not the caller's directory.

    Windows cannot start a relative path without its suffix, and resolves it against the parent's
    directory, so a command holding a path separator becomes an absolute path to the real file.
    A bare name such as "java" is left for the PATH search. Unresolved commands are returned as given.
    """
    windows = os.name == "nt" if windows is None else windows
    cwd = Path(root) / cfg.get("cwd", ".")
    argv = list(cfg["command"])
    exe = argv[0]
    if "/" in exe or "\\" in exe:
        base = cwd / exe
        for suffix in ("", ".exe", ".cmd", ".bat") if windows else ("",):
            cand = base.with_name(base.name + suffix)
            if cand.is_file():
                argv[0] = str(cand.resolve())
                break
    else:
        argv[0] = shutil.which(exe) or exe
    return argv, str(cwd)


def same_number(a, e, absolute, relative):
    return abs(a - e) <= absolute + relative * max(abs(a), abs(e))


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def compare(actual, expected, cls, limit, path):
    """Returns a list of mismatch strings. Recurses through arrays and objects. null only equals null."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected object"]
        if set(actual) != set(expected):
            return [f"{path}: keys differ, missing {sorted(set(expected) - set(actual))}, extra {sorted(set(actual) - set(expected))}"]
        return [m for k in expected for m in compare(actual[k], expected[k], cls, limit, f"{path}.{k}")]
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return [f"{path}: expected array of {len(expected)}"]
        return [m for i, (a, e) in enumerate(zip(actual, expected)) for m in compare(a, e, cls, limit, f"{path}[{i}]")]
    if expected is None or isinstance(expected, (bool, str)):
        return [] if actual == expected and type(actual) is type(expected) else [f"{path}: {actual!r} != {expected!r}"]
    if not is_num(actual) or not math.isfinite(actual):
        return [f"{path}: {actual!r} is not a finite number"]
    if cls.get("exact"):
        return [] if actual == expected else [f"{path}: {actual!r} != {expected!r} (exact)"]
    ab = limit.get("absolute", cls.get("absolute")) if limit else cls.get("absolute")
    re_ = limit.get("relative", cls.get("relative", 0.0)) if limit else cls.get("relative")
    if ab is None or re_ is None:
        raise ValueError(f"class has no numeric tolerance at {path}")
    if same_number(actual, expected, ab, re_):
        return []
    return [f"{path}: {actual!r} vs {expected!r}, error {abs(actual - expected):.3e}, limit abs {ab:g} rel {re_:g}"]


def exact_zero(check, outputs):
    """Stage F (rulings F-25, F-26, F-30): structural zeros. `output` is a dotted path to a matrix (a list of rows);
    every [row, column] in `positions` must be exactly 0.0 or -0.0, not merely within tolerance."""
    m = outputs
    for k in check["output"].split("."):
        m = m.get(k) if isinstance(m, dict) else None
    if not isinstance(m, list):
        return [f"extra check: {check['output']} missing"]
    bad = []
    for i, j in check["positions"]:
        try:
            v = m[i][j]
        except (IndexError, TypeError):
            return [f"extra check {check['output']}: position [{i}, {j}] missing"]
        if not (is_num(v) and v == 0.0):
            bad.append(f"[{i}, {j}] = {v!r}")
    return [] if not bad else [f"extra check {check['output']}: not exactly zero at {len(bad)} structural positions, e.g. {bad[:3]}"]


def extra_check(check, outputs):
    if check["method"] == "exact_zero":
        return exact_zero(check, outputs)
    a = outputs.get(check["output"])
    if not is_num(a):
        return [f"extra check: {check['output']} missing"]
    e = check["expected"]
    if check["method"] == "absolute":
        lim = check["limit"]
    elif check["method"] == "confidence_interval":
        se = outputs.get(check["stderr_output"])
        if not is_num(se) or se <= 0:
            return ["extra check: stderr missing or not positive"]
        lim = check["z"] * se
    else:
        raise ValueError(check["method"])
    return [] if abs(a - e) <= lim else [f"extra check {check['output']}: {a!r} vs {e!r}, limit {lim:g}"]


def judge(case, res, classes, peers=None):
    """Returns (status, messages). status: pass, fail, not_implemented.

    Stage F (rule F-3): expected status "any" passes on any well-formed result; "same_as" passes when the
    result matches the peer case's result (same status and code, or outputs within this case's tolerance)."""
    exp = case["expected"]
    if not isinstance(res, dict):
        return "fail", ["no result object"]
    if res.get("case_id") != case["case_id"]:
        return "fail", [f"case_id mismatch: {res.get('case_id')!r}"]
    if res.get("status") == "error" and (res.get("error") or {}).get("code") == "E_UNSUPPORTED_OPERATION":
        return "not_implemented", []
    if exp["status"] == "any":
        return ("pass", []) if res.get("status") in ("ok", "error") else ("fail", [f"bad status {res.get('status')!r}"])
    if exp["status"] == "same_as":
        peer = (peers or {}).get(exp["case_id"])
        if not isinstance(peer, dict) or peer.get("status") not in ("ok", "error"):
            return "fail", [f"peer {exp['case_id']} has no well-formed result"]
        if peer.get("status") == "error" and (peer.get("error") or {}).get("code") == "E_UNSUPPORTED_OPERATION":
            return "not_implemented", []
        if peer["status"] == "error":
            exp = {"status": "error", "error_code": (peer.get("error") or {}).get("code")}
        else:
            exp = {"status": "ok", "outputs": peer.get("outputs") or {}}
    if exp["status"] == "error":
        if res.get("status") != "error":
            return "fail", [f"expected {exp['error_code']}, got status {res.get('status')!r}"]
        code = (res.get("error") or {}).get("code")
        return ("pass", []) if code == exp["error_code"] else ("fail", [f"error code {code!r} != {exp['error_code']!r}"])
    if res.get("status") != "ok":
        return "fail", [f"unexpected error {res.get('error')!r}"]
    outs = res.get("outputs")
    if not isinstance(outs, dict):
        return "fail", ["outputs missing"]
    if set(outs) != set(exp["outputs"]):
        return "fail", [f"output keys differ: {sorted(outs)} vs {sorted(exp['outputs'])}"]
    msgs = []
    base = classes[case["tolerance_class"]]
    per = case.get("output_classes", {})
    for k, e in exp["outputs"].items():
        c = classes[per[k]] if k in per else base
        msgs += compare(outs[k], e, c, None if k in per else case.get("tolerance_limit"), k)
    for chk in case.get("extra_checks", []):
        msgs += extra_check(chk, outs)
    return ("pass", []) if not msgs else ("fail", msgs)


def run_batch(command, cwd, cases, timeout):
    lines = [json.dumps({"schema_version": "1.0", "case_id": c["case_id"], "operation": c["operation"], "inputs": c["inputs"]},
                        ensure_ascii=True) for c in cases]  # escapes carry a lone surrogate, which UTF-8 cannot
    start = time.monotonic()
    try:
        p = subprocess.run(command, cwd=cwd, input=("\n".join(lines) + "\n").encode("utf-8"), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f"timeout after {timeout}s", time.monotonic() - start
    except OSError as e:
        return None, f"could not start: {e}", time.monotonic() - start
    took = time.monotonic() - start
    if p.returncode != 0:
        return None, f"exit code {p.returncode}: {p.stderr.decode('utf-8', 'replace')[-300:]}", took
    out = p.stdout.decode("utf-8", "strict").splitlines()
    if len(out) != len(cases):
        return None, f"{len(out)} result lines for {len(cases)} cases", took
    results = []
    for line in out:
        try:
            results.append(json.loads(line, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c))))
        except ValueError:
            results.append(None)
    return results, None, took


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", required=True)
    ap.add_argument("--suite", default="*")
    ap.add_argument("--golden", default=str(ROOT / "datasets" / "golden"))
    ap.add_argument("--config", default=str(HERE / "implementations.json"))
    ap.add_argument("--policy", default=str(ROOT / "conformance" / "tolerances" / "policy.yaml"))
    ap.add_argument("--report", default=str(ROOT / "conformance" / "reports"))
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--max-show", type=int, default=20)
    a = ap.parse_args()
    impls = load_impls(a.config)
    if a.impl not in impls:
        print(f"unknown implementation {a.impl}; known: {sorted(impls)}", file=sys.stderr)
        return 2
    cfg = impls[a.impl]
    classes = load_policy(a.policy)
    files = sorted(p for p in Path(a.golden).rglob(f"{a.suite}.json"))
    if not files:
        print("no golden files matched", file=sys.stderr)
        return 2
    base, cwd = resolve_command(cfg)
    version = {}
    try:
        v = subprocess.run(base + ["version"], cwd=cwd, capture_output=True, timeout=60)
        version = json.loads(v.stdout)
        if version.get("contract_version") != CONTRACT:
            print(f"contract version {version.get('contract_version')!r} is not {CONTRACT}", file=sys.stderr)
            return 1
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        print(f"version command failed: {e}", file=sys.stderr)
        return 1
    report = {"implementation": a.impl, "version": version, "contract_version": CONTRACT,
              "run_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "suites": []}
    bad = False
    for path in files:
        doc = json.loads(path.read_text(encoding="utf-8"))
        cases = doc["cases"]
        for c in cases:
            if c["tolerance_class"] not in classes:
                print(f"{c['case_id']}: unknown class {c['tolerance_class']}", file=sys.stderr)
                return 2
        results, err, took = run_batch(base + ["batch"], cwd, cases, a.timeout)
        row = {"suite": doc["suite"], "spec_version": doc["spec_version"], "cases": len(cases), "seconds": round(took, 3),
               "pass": 0, "fail": 0, "not_implemented": 0, "crash": err, "failures": []}
        if err:
            bad = True
            print(f"{doc['suite']:<14} CRASH {err}")
        else:
            peers = {c["case_id"]: r for c, r in zip(cases, results)}
            for c, r in zip(cases, results):
                st, msgs = judge(c, r, classes, peers)
                row[st] += 1
                if st == "fail":
                    bad = True
                    row["failures"].append({"case_id": c["case_id"], "messages": msgs[:5]})
            print(f"{doc['suite']:<14} pass {row['pass']:>5}  fail {row['fail']:>5}  not implemented {row['not_implemented']:>5}  ({took:.1f}s)")
            for fl in row["failures"][:a.max_show]:
                print(f"   {fl['case_id']}: {fl['messages'][0]}")
        report["suites"].append(row)
    tot = {k: sum(s[k] for s in report["suites"]) for k in ("cases", "pass", "fail", "not_implemented")}
    report["totals"] = tot
    print(f"TOTAL {tot}")
    out = Path(a.report)
    out.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9_-]", "_", a.impl)
    (out / f"{name}.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return 1 if bad or tot["not_implemented"] else 0


if __name__ == "__main__":
    sys.exit(main())
