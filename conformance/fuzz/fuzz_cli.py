#!/usr/bin/env python3
"""Black-box fuzzer for the quantforge CLI. Standard library only. Holds no financial logic.

It mutates golden case inputs and raw bytes, sends them to one implementation in batch mode, and
checks the rules in specifications/cli-contract.md: one result per line, the result shape, a known
error code, and a clean exit. A failing batch is replayed one input at a time with `run`, so each
finding names the exact input. Findings are written to --out as JSON Lines.

Usage: fuzz_cli.py --impl NAME [--seconds N] [--seed N] [--chunk N] [--timeout S] [--out FILE]
Exit status: 0 no findings, 1 findings, 2 bad usage.
"""
import argparse
import copy
import json
import math
import random
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "conformance" / "runner"))
from runner import load_impls, resolve_command  # noqa: E402

CODES = {
    "E_PARSE", "E_LIMIT", "E_CURRENCY_MISMATCH", "E_SCHEMA", "E_UNSUPPORTED_OPERATION", "E_INPUT", "E_DATE_ORDER", "E_DATE_RANGE",
    "E_DOMAIN", "E_NOT_BRACKETED", "E_NO_CONVERGENCE", "E_ZERO_DERIVATIVE", "E_SINGULAR",
    "E_NOT_POSITIVE_DEFINITE", "E_OUT_OF_RANGE", "E_NONEXISTENT_LOCAL_TIME",
    "E_AMBIGUOUS_LOCAL_TIME", "E_NON_FINITE",
}
ODD_VALUES = [
    None, True, False, 0, -1, 1, 2, 0.0, -0.0, 0.5, 1e-308, 5e-324, 1e308, -1e308, 2**31, 2**53,
    -(2**53), "", "x", "NaN", "2024-02-30", "0000-01-01", "9999-12-31", "é", [], [0], {},
    [[1.0]], {"a": 1},
]
RAW = [
    b"", b"{", b"[", b"null", b"0", b'""', b"[]", b"{}", b"\xff\xfe", b'{"a":1,"a":2}', b"1e400",
    b"[" * 2000, b'{"a":' * 2000, b"NaN", b"\xef\xbb\xbf{}", b'"\\ud800"',
]


def load_seeds():
    seeds = []
    for path in sorted((ROOT / "datasets" / "golden").rglob("*.json")):
        for c in json.loads(path.read_text(encoding="utf-8"))["cases"]:
            seeds.append({"schema_version": "1.0", "case_id": c["case_id"],
                          "operation": c["operation"], "inputs": c["inputs"]})
    return seeds


def slots(value, out):
    """Collects (container, key) for every place in a JSON value."""
    items = value.items() if isinstance(value, dict) else enumerate(value)
    for k, v in items:
        out.append((value, k))
        if isinstance(v, (dict, list)):
            slots(v, out)
    return out


def mutate_case(rng, seeds):
    case = copy.deepcopy(rng.choice(seeds))
    for _ in range(rng.choice((1, 1, 1, 2, 3))):
        places = slots(case["inputs"], [])
        kind = rng.randrange(6)
        if kind == 5:  # envelope damage
            key = rng.choice(list(case))
            if rng.random() < 0.5:
                del case[key]
            else:
                case[key] = rng.choice(ODD_VALUES)
            break
        if not places:
            continue
        box, key = rng.choice(places)
        old = box[key]
        if kind == 0:
            box[key] = copy.deepcopy(rng.choice(ODD_VALUES))
        elif kind == 1 and isinstance(box, dict):
            del box[key]
        elif kind == 2 and isinstance(old, (int, float)) and not isinstance(old, bool):
            scaled = old * rng.choice((-1, 2, 10, 1e6, 1e-6, 1e300))
            box[key] = scaled if math.isfinite(scaled) else 1e308
        elif kind == 3 and isinstance(old, list):
            box[key] = rng.choice(([], old[:1], old[::-1], old + old))
        elif kind == 4 and isinstance(old, str) and old:
            at = rng.randrange(len(old))
            box[key] = old[:at] + rng.choice("0-9:TZé") + old[at + 1:]
    return json.dumps(case, ensure_ascii=False, allow_nan=False).encode("utf-8")


def mutate_bytes(rng, seeds):
    if rng.random() < 0.3:
        return rng.choice(RAW)
    data = bytearray(json.dumps(rng.choice(seeds)).encode("utf-8"))
    for _ in range(rng.randint(1, 4)):
        at = rng.randrange(len(data))
        choice = rng.randrange(3)
        if choice == 0:
            data[at] = rng.choice(b'{}[]",:0e-.\\\xff')
        elif choice == 1:
            del data[at:at + rng.randint(1, 8)]
        else:
            del data[at:]
        if not data:
            return b""
    return bytes(data)


def shape_error(line):
    """Returns why a result line breaks the contract, or None."""
    try:
        res = json.loads(line.decode("utf-8"), parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
    except ValueError as e:
        return f"not JSON: {e}"
    if not isinstance(res, dict):
        return "result is not an object"
    if not isinstance(res.get("schema_version"), str):
        return "schema_version missing"
    if not isinstance(res.get("case_id"), str) or not res["case_id"]:
        return "case_id missing"
    extra = set(res) - {"schema_version", "case_id", "status", "outputs", "diagnostics", "error", "provenance"}
    if extra:
        return f"extra keys {sorted(extra)}"
    if res.get("status") == "ok":
        if not isinstance(res.get("outputs"), dict) or "error" in res:
            return "ok result needs outputs and no error"
    elif res.get("status") == "error":
        err = res.get("error")
        if "outputs" in res or not isinstance(err, dict):
            return "error result needs error and no outputs"
        if err.get("code") not in CODES:
            return f"unknown error code {err.get('code')!r}"
        if not isinstance(err.get("message"), str) or set(err) - {"code", "message", "field"}:
            return "bad error object"
    else:
        return f"bad status {res.get('status')!r}"
    return None


def call(argv, cwd, data, timeout):
    try:
        p = subprocess.run(argv, cwd=cwd, input=data, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, b"", b""
    return p.returncode, p.stdout, p.stderr


def check_run(base, cwd, data, timeout):
    """Runs one input with `run`. Returns a finding message, or None."""
    code, out, err = call(base + ["run"], cwd, data, timeout)
    if code is None:
        return f"timeout after {timeout}s"
    tail = err.decode("utf-8", "replace")[-300:]
    if code not in (0, 2):
        return f"exit code {code}: {tail}"
    lines = out.splitlines()
    if len(lines) != 1:
        return f"{len(lines)} result lines"
    bad = shape_error(lines[0])
    if bad:
        return bad
    status = json.loads(lines[0])["status"]
    if (status == "ok") != (code == 0):
        return f"status {status} with exit code {code}"
    return None


def batch_ok(base, cwd, inputs, timeout):
    code, out, _ = call(base + ["batch"], cwd, b"\n".join(inputs) + b"\n", timeout)
    lines = out.splitlines()
    return code == 0 and len(lines) == len(inputs) and not any(shape_error(x) for x in lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", required=True)
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--chunk", type=int, default=200)
    ap.add_argument("--timeout", type=float, default=20, help="seconds for one input with run")
    ap.add_argument("--config", default=str(ROOT / "conformance" / "runner" / "implementations.json"))
    ap.add_argument("--out", default=str(ROOT / "conformance" / "reports" / "fuzz"))
    ap.add_argument("--max-findings", type=int, default=25)
    a = ap.parse_args()
    impls = load_impls(a.config)
    if a.impl not in impls:
        print(f"unknown implementation {a.impl}", file=sys.stderr)
        return 2
    base, cwd = resolve_command(impls[a.impl])
    rng = random.Random(a.seed)
    seeds = load_seeds()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    findings, sent, replayed = [], 0, 0
    end = time.monotonic() + a.seconds
    with (out / f"{a.impl}.jsonl").open("w", encoding="utf-8") as log:
        while time.monotonic() < end and len(findings) < a.max_findings:
            inputs = [(mutate_case if rng.random() < 0.8 else mutate_bytes)(rng, seeds) for _ in range(a.chunk)]
            # A newline inside an input would split it into two batch lines.
            inputs = [x.replace(b"\n", b" ").replace(b"\r", b" ") for x in inputs]
            sent += len(inputs)
            if batch_ok(base, cwd, inputs, a.timeout * 5):
                continue
            for data in inputs:
                if time.monotonic() > end + a.timeout * 10 or len(findings) >= a.max_findings:
                    break
                replayed += 1
                msg = check_run(base, cwd, data, a.timeout)
                if msg:
                    row = {"impl": a.impl, "seed": a.seed, "problem": msg, "input": data.decode("utf-8", "backslashreplace")}
                    findings.append(row)
                    log.write(json.dumps(row) + "\n")
                    log.flush()
                    print(f"FINDING {msg[:160]}\n  input: {row['input'][:300]}")
    print(f"{a.impl}: sent {sent}, replayed {replayed}, findings {len(findings)}, seed {a.seed}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
