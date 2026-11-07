#!/usr/bin/env python3
"""Measures the batch targets in benchmarks/targets.md (T1 to T5). Standard library only, no financial logic.

  python benchmarks/batch_targets.py --impl rust [--config FILE] [--t3-trades N] [--repeats 5] [--out FILE]

Run it on the machine whose figure you want: Windows for Java and Python, WSL for C++ and Rust (fresh native
executables are blocked by Windows Application Control on the reference laptop). It sends `quantforge --batch`
and times from outside the process, as cli_throughput.py does.

T1 single curve bootstrap p99: 10,000 rates.ois.bootstrap cases, 13 SOFR quotes 1W..30Y jittered by a seeded
   +-5 bp; per-case latency is the gap between consecutive result lines (the contract flushes each line), after
   the first 1,000 lines. Start-up is excluded, as targets.md says.
T2 10,000-swap PV wall time: one bootstrap, then 10,000 rates.ois.pv cases from sample_book.py.
T3 key-rate risk wall time: risk.ois.dv01 per trade. --t3-trades below 10,000 measures a subset and
   reports the scaled figure, labelled as scaled, because a slow language would otherwise take hours.
T4 start-up: median of 20 runs of `quantforge version`.
T5 peak RSS during T2: Linux only, from /proc via os.wait4; "not measured" elsewhere.
One core: on Linux the child is pinned with os.sched_setaffinity; on Windows it is not pinned (stated in the result).
"""
import argparse
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "conformance" / "runner"))
sys.path.insert(0, str(ROOT / "tools" / "workflows"))
from runner import resolve_command  # noqa: E402
from sample_book import book, digest  # noqa: E402

TENORS = ["1W", "1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y"]
BASE = [0.0400, 0.0401, 0.0405, 0.0410, 0.0415, 0.0420, 0.0425, 0.0430, 0.0440, 0.0450, 0.0465, 0.0475, 0.0470]
AS_OF = "2026-11-06"
LINUX = sys.platform.startswith("linux")


def case(i, op, inputs):
    return {"schema_version": "1.0", "case_id": str(i), "operation": op, "inputs": inputs}


def quotes(rng=None):
    return [{"tenor": t, "rate": round(r + (rng.uniform(-5e-4, 5e-4) if rng else 0.0), 8)} for t, r in zip(TENORS, BASE)]


def pin():
    if LINUX:
        os.sched_setaffinity(0, {sorted(os.sched_getaffinity(0))[0]})


def run_batch(cmd, cwd, cases, stamps=False):
    """Returns (wall seconds, line arrival times or None, peak RSS KiB or None, results)."""
    text = "".join(json.dumps(c, separators=(",", ":")) + "\n" for c in cases).encode()
    t0 = time.perf_counter()
    p = subprocess.Popen(cmd + ["--batch"], cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         preexec_fn=pin if LINUX else None)
    feeder = threading.Thread(target=lambda: (p.stdin.write(text), p.stdin.close()))
    feeder.start()
    arrivals, out = [], []
    for line in p.stdout:
        if stamps:
            arrivals.append(time.perf_counter())
        out.append(line)
    feeder.join()
    rss = None
    if LINUX:
        _, status, usage = os.wait4(p.pid, 0)
        code = os.waitstatus_to_exitcode(status)
        rss = usage.ru_maxrss
    else:
        code = p.wait()
    wall = time.perf_counter() - t0
    if code != 0 or len(out) != len(cases):
        raise SystemExit(f"batch failed: exit {code}, {len(out)} lines for {len(cases)} cases")
    rows = [json.loads(x) for x in out]
    bad = [r for r in rows if r.get("status") != "ok"]
    if bad:
        raise SystemExit(f"{len(bad)} cases not ok, first: {bad[0]}")
    return wall, arrivals if stamps else None, rss, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", required=True)
    ap.add_argument("--config", default=str(ROOT / "conformance/runner/implementations.json"))
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--t1-cases", type=int, default=10000)
    ap.add_argument("--t3-trades", type=int, default=10000)
    ap.add_argument("--out")
    a = ap.parse_args()
    cmd, cwd = resolve_command(json.loads(Path(a.config).read_text(encoding="utf-8"))[a.impl])
    rng = random.Random(20261107)
    t1_cases = [case(i, "rates.ois.bootstrap", {"convention": "SOFR", "as_of": AS_OF, "quotes": quotes(rng),
                                                "interpolation": "LOG_LINEAR_DF", "method": "SEQUENTIAL"}) for i in range(a.t1_cases)]
    trades = book(10000)
    res = {"impl": a.impl, "command": cmd, "machine": {"platform": platform.platform(), "processor": platform.processor() or platform.machine(),
                                                         "cpus": os.cpu_count(), "pinned_one_core": LINUX},
           "date": time.strftime("%Y-%m-%d"), "book_sha256": digest(trades), "repeats": a.repeats}
    try:
        res["commit"] = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        res["commit"] = "unknown"

    # T4 start-up
    times = []
    for _ in range(20):
        t0 = time.perf_counter()
        subprocess.run(cmd + ["version"], cwd=cwd, capture_output=True, check=True)
        times.append(time.perf_counter() - t0)
    res["T4_startup_s"] = statistics.median(times)
    print(f"T4 start-up median {res['T4_startup_s']:.3f} s", flush=True)

    # T1 bootstrap p99 per case inside a warm batch
    run_batch(cmd, cwd, t1_cases[:1000])  # warm-up, unmeasured
    p99s = []
    for _ in range(a.repeats):
        _, arr, _, _ = run_batch(cmd, cwd, t1_cases, stamps=True)
        gaps = sorted(b - x for x, b in zip(arr[1000:], arr[1001:]))
        p99s.append(gaps[int(0.99 * (len(gaps) - 1))])
    res["T1_bootstrap_p99_ms"] = statistics.median(p99s) * 1e3
    print(f"T1 bootstrap p99 {res['T1_bootstrap_p99_ms']:.3f} ms", flush=True)

    # Curve for T2
    _, _, _, rows = run_batch(cmd, cwd, [t1_cases[0] | {"inputs": t1_cases[0]["inputs"] | {"quotes": quotes()}}])
    curve = {"as_of": AS_OF, "interpolation": "LOG_LINEAR_DF", "pillars": rows[0]["outputs"]["pillars"]}

    def trade(x):
        return {"convention": "SOFR", "tenor": x["tenor"], "fixed_rate": round(0.044 + x["offset"], 6), "notional": x["notional"], "side": x["side"]}

    t2_cases = [case(i, "rates.ois.pv", {"curve": curve, "trade": trade(x)}) for i, x in enumerate(trades)]
    walls, rsss = [], []
    run_batch(cmd, cwd, t2_cases[:500])
    for _ in range(a.repeats):
        w, _, rss, _ = run_batch(cmd, cwd, t2_cases)
        walls.append(w)
        rsss.append(rss)
    res["T2_pv_10000_s"] = statistics.median(walls)
    res["T5_peak_rss_mib"] = max(rsss) / 1024 if all(rsss) else None
    print(f"T2 10,000 PV {res['T2_pv_10000_s']:.2f} s; T5 peak RSS {res['T5_peak_rss_mib']}", flush=True)

    # T3 key-rate risk (scaled if a subset)
    n = min(a.t3_trades, len(trades))
    t3_cases = [case(i, "risk.ois.dv01", {"as_of": AS_OF, "quotes": quotes(), "interpolation": "LOG_LINEAR_DF", "trade": trade(x)})
                for i, x in enumerate(trades[:n])]
    walls = []
    for _ in range(1 if n >= 2000 else a.repeats):  # one run of a long workload; repeats on a short one
        w, _, _, _ = run_batch(cmd, cwd, t3_cases)
        walls.append(w)
    w = statistics.median(walls)
    res["T3_keyrate_trades_measured"] = n
    # Scale only the per-trade part: start-up (T4) is paid once whatever the batch size.
    res["T3_keyrate_10000_s"] = w if n >= 10000 else res["T4_startup_s"] + (w - res["T4_startup_s"]) * 10000 / n
    res["T3_scaled"] = n < 10000
    print(f"T3 key-rate {n} trades {w:.1f} s -> 10,000: {res['T3_keyrate_10000_s']:.1f} s{' (scaled)' if n < 10000 else ''}", flush=True)
    text = json.dumps(res, indent=1)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
