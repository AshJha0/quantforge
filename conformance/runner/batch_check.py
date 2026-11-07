#!/usr/bin/env python3
"""Checks batch-mode framing (cli-contract.md, Batch mode) against datasets/batch/streams.json.

python conformance/runner/batch_check.py --impl rust

Standard library only, and no financial logic: it compares statuses, codes, case ids and
result equality between `run` and `batch`.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from runner import load_impls, resolve_command  # noqa: E402


def build(segs):
    out = bytearray()
    for s in segs:
        if "text" in s:
            out += s["text"].encode("utf-8")
        elif "hex" in s:
            out += bytes.fromhex(s["hex"])
        else:
            out += s["repeat"].encode("utf-8") * s["count"]
    return bytes(out)


def call(cmd, cwd, data, timeout):
    p = subprocess.run(cmd, cwd=cwd, input=data, capture_output=True, timeout=timeout)
    return p.returncode, p.stdout


def parse_lines(raw):
    if b"\r" in raw:
        raise ValueError("CR in output (BT6)")
    text = raw.decode("utf-8")
    if text.startswith("﻿"):
        raise ValueError("byte order mark in output (BT6)")
    if text and not text.endswith("\n"):
        raise ValueError("output does not end in LF (BT6)")
    lines = text.split("\n")[:-1] if text else []
    if any(not ln for ln in lines):
        raise ValueError("blank output line (BT6)")
    return [json.loads(ln) for ln in lines]


def strip_timing(r):
    """The result without elapsed_ns. An empty or absent diagnostics object counts as the same."""
    r = json.loads(json.dumps(r))
    r.get("diagnostics", {}).pop("elapsed_ns", None)
    if r.get("diagnostics") == {}:
        del r["diagnostics"]
    return r


def check_stream(st, base, cwd, timeout):
    code, out = call(base + st["args"], cwd, build(st["segments"]), timeout)
    if code != st["exit"]:
        return [f"exit {code}, expected {st['exit']}"]
    if st["exit"] == 64:
        return [] if out == b"" else ["stdout not empty on exit 64"]
    try:
        res = parse_lines(out)
    except ValueError as e:
        return [str(e)]
    if len(res) != len(st["expected"]):
        return [f"{len(res)} results, expected {len(st['expected'])}"]
    msgs = []
    for i, (r, e) in enumerate(zip(res, st["expected"])):
        if r.get("status") != e["status"]:
            msgs.append(f"line {i}: status {r.get('status')} vs {e['status']}")
        if r.get("case_id") != e["case_id"]:
            msgs.append(f"line {i}: case_id {r.get('case_id')} vs {e['case_id']}")
        if e["status"] == "error" and (r.get("error") or {}).get("code") != e["code"]:
            msgs.append(f"line {i}: code {(r.get('error') or {}).get('code')} vs {e['code']}")
        t = r.get("diagnostics", {}).get("elapsed_ns")
        if st["timings"]:
            if not (isinstance(t, int) and not isinstance(t, bool) and t >= 0):
                msgs.append(f"line {i}: elapsed_ns missing or not a non-negative integer")
        elif t is not None:
            msgs.append(f"line {i}: elapsed_ns present without --timings")
    return msgs


def sample_cases(every):
    out = []
    for p in sorted((ROOT / "datasets" / "golden").rglob("*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        for c in doc.get("cases", [])[::every]:
            out.append({"schema_version": "1.0", "case_id": c["case_id"], "operation": c["operation"], "inputs": c["inputs"]})
    return out


def lines_of(cases):
    return ("\n".join(json.dumps(c, ensure_ascii=True) for c in cases) + "\n").encode("utf-8")


def check_sample(base, cwd, timeout, every, do_run):
    msgs = []
    cases = sample_cases(every)
    _, out = call(base + ["batch"], cwd, lines_of(cases), timeout)
    fwd = parse_lines(out)
    _, out = call(base + ["batch"], cwd, lines_of(cases[::-1]), timeout)
    rev = parse_lines(out)
    if fwd != rev[::-1]:
        msgs.append("reorder: results differ when the stream is reversed (BT7)")
    _, out = call(base + ["batch", "--timings"], cwd, lines_of(cases), timeout)
    tim = parse_lines(out)
    if [strip_timing(r) for r in tim] != [strip_timing(r) for r in fwd]:
        msgs.append("timings_identity: results differ with --timings")
    if do_run:
        for c, b in zip(cases, fwd):
            _, out = call(base + ["run"], cwd, json.dumps(c, ensure_ascii=True).encode("utf-8"), timeout)
            if json.loads(out) != b:
                msgs.append(f"equivalence: {c['case_id']} differs between run and batch (BT4)")
    return len(cases), msgs


def check_interactive(base, cwd, timeout):
    line = (json.dumps({"schema_version": "1.0", "case_id": "i", "operation": "core.daycount.year_fraction",
                        "inputs": {"convention": "ACT_360", "start": "2024-01-01", "end": "2024-07-01"}}) + "\n").encode()
    p = subprocess.Popen(base + ["batch"], cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    import threading
    got = []
    try:
        for _ in range(3):
            p.stdin.write(line)
            p.stdin.flush()
            t = threading.Thread(target=lambda: got.append(p.stdout.readline()))
            t.start()
            t.join(timeout)
            if t.is_alive():
                return ["interactive: no result within the limit before stdin closed (BT6)"]
    finally:
        p.kill()
    return [] if len(got) == 3 and all(g.endswith(b"\n") for g in got) else ["interactive: bad result lines"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", required=True)
    ap.add_argument("--config", default=str(HERE / "implementations.json"))
    ap.add_argument("--every", type=int, default=40)
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--skip-run", action="store_true", help="skip the per-case run equivalence (slow on the JVM)")
    a = ap.parse_args()
    base, cwd = resolve_command(load_impls(a.config)[a.impl])
    doc = json.loads((ROOT / "datasets" / "batch" / "streams.json").read_text(encoding="utf-8"))
    bad = 0
    for st in doc["streams"]:
        msgs = check_stream(st, base, cwd, a.timeout)
        print(f"{st['id']} {'ok' if not msgs else 'FAIL'}  {st['description']}")
        for m in msgs:
            print(f"   {m}")
        bad += bool(msgs)
    n, msgs = check_sample(base, cwd, a.timeout, a.every, not a.skip_run)
    msgs += check_interactive(base, cwd, 30)
    print(f"sample of {n} golden cases: {'ok' if not msgs else 'FAIL'}")
    for m in msgs[:20]:
        print(f"   {m}")
    bad += bool(msgs)
    print("TOTAL", "pass" if not bad else f"{bad} failing")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
