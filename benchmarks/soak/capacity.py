#!/usr/bin/env python3
"""K-6 capacity measurements (KR-219): throughput, latency, batch size and input-size ceilings per build.
Standard library only. Holds no financial logic.

Plain idea: there are no targets. Each figure is measured, every answer that has a golden is checked against it, and
the figure is written down with the host and the commit. A row whose answers are wrong reports `WRONG_RESULT`
instead of a number, so a fast wrong build is never listed as fast.

Rows (frozen before the first counted run; see specifications/12-platform/soak-eod-capacity.md section 2):
  mix/<name>      one pass of a fixed golden mix through one `quantforge batch --timings` process per `--procs`;
                  cases per second over the wall time (start-up included), p50/p99 of the per-case
                  `diagnostics.elapsed_ns`, peak memory. Mixes: golden (every golden case), cheap (core.daycount,
                  core.calendar, core.compounding), medium (rates.ois, vol.option, risk.curve), heavy (rates.lmm,
                  xva.exposure, hedge.qp, vol.slv). Every answer is judged against its golden.
  batch/<n>       the cheap mix repeated to n lines (10,000; 100,000; 1,000,000): wall time, cases per second, peak
                  memory, so the effect of batch size on memory is visible. Answers are judged.
  ceiling/<op>/<size>  one large case after a small warm-up case in a fresh process: wall time and the extra memory
                  the case needed (peak during the case minus the idle reading before it). Sizes are 10 %, 50 % and
                  100 % of the documented limit (specifications/01-core/limits.md: 200 quotes for
                  curve.bootstrap.par_annual, 100,000 positions for risk.intraday.delta_gamma_bound); status must be
                  ok. limit + 1 must return E_LIMIT.
A row passes when it completes with every judged answer correct (or, for limit + 1, the error E_LIMIT). The file is
the raw measurement; docs/capacity.md is written from it.

Planted fault (rule 1): `--plant-wrong` changes one expected output of the heavy mix after loading; that row must
report WRONG_RESULT.

Usage: capacity.py --impl NAME [--procs 1,2,4] [--batch-sizes 10000,100000,1000000] [--plant-wrong] [--out FILE]
Exit status: 0 every row passed; 1 a row failed (or, with --plant-wrong, the planted row did not fail); 2 bad usage.
"""

import argparse
import datetime
import json
import os
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import soak
from soak import ROOT, judge, load_policy, procstat

MIXES = {
    "golden": None,
    "cheap": ("core.daycount.", "core.calendar.", "core.compounding."),
    "medium": ("rates.ois.", "vol.option.", "risk.curve."),
    "heavy": ("rates.lmm.", "xva.exposure.", "hedge.qp.", "vol.slv."),
}
CEILINGS = {"curve.bootstrap.par_annual": ("quotes", 200), "risk.intraday.delta_gamma_bound": ("positions", 100_000)}


def big_input(op, n):
    if op == "curve.bootstrap.par_annual":
        return {"quotes": [round(0.03 + 0.0001 * min(i, 50), 6) for i in range(n)]}
    return {
        "positions": [
            {"notional": 1_000_000.0 + i, "maturity": 1.0 + (i % 30), "yield": 0.03 + 0.0001 * (i % 40)}
            for i in range(n)
        ],
        "shift": 0.01,
    }


class Proc:
    """One batch process with a memory poller."""

    def __init__(self, impl, work, timings=True):
        argv, env, pidfile, _ = soak.command(impl, work)
        argv = [a for a in argv if not a.startswith("-Xlog:gc")]
        if timings:
            argv = argv + ["--timings"]
        if pidfile and pidfile.exists():
            pidfile.unlink()
        self.p = soak.start(argv, env)
        self.pid = soak.worker_pid(self.p, pidfile)
        self.peak_judged = self.peak_rss = 0
        self.polling = threading.Event()
        self.poller = threading.Thread(target=self._poll, daemon=True)
        self.poller.start()

    def _poll(self):
        while not self.polling.is_set():
            s = procstat.sample(self.pid)
            if s is None:
                return
            self.peak_judged = max(self.peak_judged, s[procstat.judged_key()])
            self.peak_rss = max(self.peak_rss, s["rss_bytes"])
            time.sleep(0.02)

    def idle_reading(self):
        s = procstat.sample(self.pid)
        return s[procstat.judged_key()] if s else 0

    def ask(self, lines):
        """Sends lines and returns the parsed answers (a writer thread keeps the pipes from filling)."""

        def write():
            for line in lines:
                self.p.stdin.write(line)
            self.p.stdin.flush()

        t = threading.Thread(target=write, daemon=True)
        t.start()
        out = [json.loads(self.p.stdout.readline()) for _ in lines]
        t.join()
        return out

    def close(self):
        self.p.stdin.close()
        code = self.p.wait(timeout=600)
        self.polling.set()
        return code


def judge_all(cases, answers, classes):
    peers = {}
    for (suite, c, _), r in zip(cases, answers):
        peers.setdefault(suite, {})[c["case_id"]] = r
    bad = []
    for (suite, c, _), r in zip(cases, answers):
        status, msgs = judge(c, r, classes, peers[suite])
        if status == "fail":
            bad.append({"case_id": c["case_id"], "why": "; ".join(msgs)[:160]})
    return bad


def latencies(answers):
    ns = [r.get("diagnostics", {}).get("elapsed_ns") for r in answers if isinstance(r, dict)]
    ns = sorted(x for x in ns if isinstance(x, int))
    if not ns:
        return None, None
    return ns[len(ns) // 2] / 1e3, ns[min(len(ns) - 1, int(0.99 * len(ns)))] / 1e3


def run_mix(impl, work, cases, classes, procs):
    """One pass of `cases` through each of `procs` processes at once."""
    lines = [c[2] for c in cases]
    ps = [Proc(impl, work / f"p{i}") for i in range(procs)]
    results = [None] * procs
    t0 = time.perf_counter()

    def go(i):
        results[i] = ps[i].ask(lines)

    th = [threading.Thread(target=go, args=(i,)) for i in range(procs)]
    for t in th:
        t.start()
    for t in th:
        t.join()
    wall = time.perf_counter() - t0
    codes = [p.close() for p in ps]
    bad = [b for r in results for b in judge_all(cases, r, classes)]
    p50, p99 = latencies([a for r in results for a in r])
    return {
        "cases": len(cases) * procs,
        "processes": procs,
        "wall_s": round(wall, 3),
        "cases_per_s": round(len(cases) * procs / wall, 1),
        "p50_us": p50 and round(p50, 1),
        "p99_us": p99 and round(p99, 1),
        "peak_rss_mib": round(max(p.peak_rss for p in ps) / 2**20, 1),
        "peak_judged_mib": round(max(p.peak_judged for p in ps) / 2**20, 1),
        "exit_codes": codes,
        "wrong": len(bad),
        "wrong_examples": bad[:5],
        "status": "pass" if not bad and not any(codes) else "WRONG_RESULT" if bad else "EXIT",
    }


def run_ceiling(impl, work, op, key, size, limit):
    warm = {
        "curve.bootstrap.par_annual": {"quotes": [0.02, 0.025, 0.03]},
        "risk.intraday.delta_gamma_bound": {
            "positions": [{"notional": 1e6, "maturity": 5.0, "yield": 0.04}],
            "shift": 0.01,
        },
    }[op]
    mk = lambda cid, inputs: (
        json.dumps({"schema_version": "1.0", "case_id": cid, "operation": op, "inputs": inputs}) + "\n"
    ).encode()
    p = Proc(impl, work / "ceil", timings=False)
    p.ask([mk("warm", warm)])
    time.sleep(0.5)
    idle = p.idle_reading()
    p.peak_judged = idle
    line = mk("big", big_input(op, size))
    t0 = time.perf_counter()
    ans = p.ask([line])[0]
    wall = time.perf_counter() - t0
    time.sleep(0.1)
    code = p.close()
    want_error = size > limit
    got = ans.get("status"), (ans.get("error") or {}).get("code")
    ok = got == ("error", "E_LIMIT") if want_error else got[0] == "ok"
    return {
        "operation": op,
        "input": key,
        "size": size,
        "limit": limit,
        "request_bytes": len(line),
        "wall_s": round(wall, 3),
        "extra_memory_mib": round(max(0, p.peak_judged - idle) / 2**20, 2),
        "answer": list(got),
        "exit_code": code,
        "status": "pass" if ok and code == 0 else "FAIL",
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", required=True, choices=["python", "java", "cpp", "rust"])
    ap.add_argument("--procs", default="1")
    ap.add_argument("--batch-sizes", default="10000,100000,1000000")
    ap.add_argument("--plant-wrong", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--host", default=os.environ.get("QF_HOST_LABEL", soak.LAPTOP))
    a = ap.parse_args(argv)
    soak.own_low_priority()
    work = ROOT / "benchmarks" / "results" / "k6" / f".capacity-{a.impl}-work"
    for d in ("p0", "p1", "p2", "p3", "ceil"):
        (work / d).mkdir(parents=True, exist_ok=True)
    classes = load_policy(ROOT / "conformance" / "tolerances" / "policy.yaml")
    allc = soak.golden_cases()
    rows, code = [], 0
    for name, prefixes in MIXES.items():
        cases = allc if prefixes is None else [c for c in allc if c[1]["operation"].startswith(prefixes)]
        if a.plant_wrong:
            if name != "heavy":
                continue
            i = next(
                i
                for i, c in enumerate(cases)
                if c[1]["expected"]["status"] == "ok"
                and any(
                    isinstance(v, (int, float)) and not isinstance(v, bool)
                    for v in c[1]["expected"]["outputs"].values()
                )
            )
            c = json.loads(json.dumps(cases[i][1]))
            k = next(
                k
                for k, v in c["expected"]["outputs"].items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)
            )
            c["expected"]["outputs"][k] = c["expected"]["outputs"][k] * 1.5 + 1.0
            cases = cases[:i] + [(cases[i][0], c, cases[i][2])] + cases[i + 1 :]
        for n in [int(x) for x in a.procs.split(",")]:
            row = {"row": f"mix/{name}", **run_mix(a.impl, work, cases, classes, n)}
            rows.append(row)
            print(
                f"{row['row']:<14} x{n} {row['status']:<12} {row['cases_per_s']:>9} cases/s  p50 {row['p50_us']} us"
                f"  p99 {row['p99_us']} us  peak {row['peak_judged_mib']} MiB",
                flush=True,
            )
    if not a.plant_wrong:
        cheap = [c for c in allc if c[1]["operation"].startswith(MIXES["cheap"])]
        for n in [int(x) for x in a.batch_sizes.split(",") if x]:
            reps = [cheap[i % len(cheap)] for i in range(n)]
            row = {"row": f"batch/{n}", **run_mix(a.impl, work, reps, classes, 1)}
            rows.append(row)
            print(
                f"{row['row']:<14} {row['status']:<12} {row['cases_per_s']:>9} cases/s  wall {row['wall_s']} s"
                f"  peak {row['peak_judged_mib']} MiB",
                flush=True,
            )
        for op, (key, limit) in CEILINGS.items():
            for size in (limit // 10, limit // 2, limit, limit + 1):
                row = {"row": f"ceiling/{op}/{size}", **run_ceiling(a.impl, work, op, key, size, limit)}
                rows.append(row)
                print(
                    f"{row['row']:<52} {row['status']:<5} {row['wall_s']} s  +{row['extra_memory_mib']} MiB "
                    f"{row['answer']}",
                    flush=True,
                )
    failed = [r["row"] for r in rows if r["status"] != "pass"]
    if a.plant_wrong:
        code = 0 if failed == ["mix/heavy"] and rows[-1]["status"] == "WRONG_RESULT" else 1
    else:
        code = 1 if failed else 0
    report = {
        "implementation": a.impl,
        "host": a.host,
        "commit": soak.commit(),
        "platform": sys.platform,
        "logical_cpus": os.cpu_count(),
        "memory_key": procstat.judged_key(),
        "run_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "planted_wrong": a.plant_wrong,
        "rows": rows,
        "failed_rows": failed,
        "verdict": ("WRONG_RESULT CAUGHT" if code == 0 else "WRONG_RESULT MISSED")
        if a.plant_wrong
        else ("PASS" if code == 0 else "MISS"),
    }
    out = Path(
        a.out
        or ROOT
        / "benchmarks"
        / "results"
        / "k6"
        / f"capacity-{a.impl}-{datetime.date.today().isoformat()}{'-planted-wrong' if a.plant_wrong else ''}.json"
    )
    out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"{a.impl}: {report['verdict']} -> {out.name}")
    return code


if __name__ == "__main__":
    sys.exit(main())
