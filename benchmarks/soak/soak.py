#!/usr/bin/env python3
"""K-6 soak driver (KR-217): one long-lived `quantforge batch` process fed the golden set in a loop. Standard
library only. Holds no financial logic.

Plain idea: start one batch process, keep feeding it every golden case in index order, over and over, for two
hours, and watch three things: its memory, whether every answer is the same as the first time, and whether it keeps
working. Every 10 s one CSV row is written; at the end a summary JSON and the frozen verdict from analyse.py.

  * Workload: every case of datasets/golden (files sorted, cases as listed), repeated; at most `--window` cases in
    flight, so the pipes never fill and the process is never idle.
  * Answers: the first answer to each case is judged against its golden with the conformance runner's `judge`
    (a failure counts as GOLDEN); every later answer must be byte-identical to the first (else DRIFT).
  * Samples: every 10 s the driver stops sending, waits until every case in flight has been answered (the process
    is then idle, holding only what it keeps between requests), takes the judged memory reading (procstat.py),
    then resumes. Java instead, every 30 s at the idle point, gets `jcmd <pid> GC.run` and then
    `jcmd <pid> GC.heap_info`, and the heap used after that full collection is the judged reading (KiB precision;
    the `-Xlog:gc` file is kept as evidence). Each row also has the instant RSS, private bytes, peak, handles,
    threads, cases done, errors and drift.
  * Priority: below normal on Windows (`BELOW_NORMAL_PRIORITY_CLASS`), `nice 10` on Linux, for the child and this
    driver, so a laptop shared with other work is disturbed as little as possible.

Usage: soak.py --impl python|java|cpp|rust [--minutes 120] [--out-dir DIR] [--tag TAG] [--plant-leak]
               [--progress FILE] [--host LABEL]
Exit status: 0 PASS (or planted leak caught); 1 MISS; 2 bad usage or could not start.
"""

import argparse
import collections
import csv
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "conformance" / "runner"))
sys.path.insert(0, str(HERE))
import analyse
import procstat
from runner import judge, load_policy

LAPTOP = "local laptop, not the acceptance machine"
FIELDS = [
    "t_s",
    "utc",
    "judged_bytes",
    "rss_bytes",
    "private_bytes",
    "peak_bytes",
    "heap_after_gc_bytes",
    "handles",
    "threads",
    "cases_total",
    "cases_window",
    "cases_per_s",
    "passes",
    "drift_total",
    "errors_total",
    "alive",
]
_USED = re.compile(r"heap\s+total[^\n]*?used (\d+)K")


def golden_cases():
    """All golden cases in file order, each with its suite name, plus the request line sent for it."""
    out = []
    for path in sorted((ROOT / "datasets" / "golden").rglob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or "cases" not in doc:
            continue
        for c in doc["cases"]:
            line = json.dumps(
                {"schema_version": "1.0", "case_id": c["case_id"], "operation": c["operation"], "inputs": c["inputs"]},
                ensure_ascii=True,
            )
            out.append((doc.get("suite", path.stem), c, (line + "\n").encode("utf-8")))
    return out


def java_home():
    home = os.environ.get("JAVA_HOME")
    if not home and sys.platform == "win32":
        home = r"C:\Program Files\Eclipse Adoptium\jdk-25.0.5.8-hotspot"
    return Path(home) if home else None


def command(impl, work):
    """(argv, env, pidfile or None, gc log or None). The argv starts the process that does the work, not a wrapper."""
    env = dict(os.environ, PYTHONUTF8="1")
    if impl == "python":
        venv = ROOT / "python" / ".venv"
        py = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        pidfile = work / "python.pid"
        env["QF_SOAK_PIDFILE"] = str(pidfile)
        return [str(py), str(HERE / "py_entry.py"), "batch"], env, pidfile, None
    if impl == "java":
        jh = java_home()
        java = str(jh / "bin" / "java") if jh else "java"
        gclog = work / "java-gc.log"
        return (
            [
                java,
                f"-Xlog:gc:file={gclog.as_posix()}",
                "-jar",
                str(ROOT / "java25/target/quantforge-cli.jar"),
                "batch",
            ],
            env,
            None,
            gclog,
        )
    exe = {"cpp": ROOT / "cpp26/build/quantforge", "rust": ROOT / "rust/target/release/quantforge"}[impl]
    if sys.platform == "win32":
        exe = exe.with_suffix(".exe")
    return [str(exe), "batch"], env, None, None


def start(argv, env, low_priority=True):
    kw = {}
    if low_priority and sys.platform == "win32":
        kw["creationflags"] = subprocess.BELOW_NORMAL_PRIORITY_CLASS
    elif low_priority:
        argv = ["nice", "-n", "10", *argv]
    return subprocess.Popen(
        argv, cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw
    )


def own_low_priority():
    if sys.platform == "win32":
        import ctypes

        k = ctypes.windll.kernel32
        k.SetPriorityClass(k.GetCurrentProcess(), 0x4000)  # BELOW_NORMAL_PRIORITY_CLASS
    else:
        try:
            os.nice(10)
        except OSError:
            pass


def worker_pid(proc, pidfile, timeout=60.0):
    """The pid of the process doing the work: the Python entry point's own pid, else the child itself (`nice`
    execs the program in place, so its pid is the program's)."""
    if pidfile is None:
        return proc.pid
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            return int(pidfile.read_text(encoding="ascii"))
        except (OSError, ValueError):
            time.sleep(0.1)
    raise RuntimeError("the Python entry point did not write its pid")


def heap_after_full_gc(jcmd, pid):
    """Bytes of Java heap in use right after a requested full collection, or None."""
    try:
        subprocess.run([jcmd, str(pid), "GC.run"], capture_output=True, timeout=120, check=True)
        info = subprocess.run(
            [jcmd, str(pid), "GC.heap_info"], capture_output=True, text=True, timeout=120, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = _USED.search(info)
    return int(m.group(1)) * 1024 if m else None


class Soak:
    def __init__(self, impl, cases, classes, window):
        self.impl, self.cases, self.classes, self.window = impl, cases, classes, window
        self.first = [None] * len(cases)  # sha256 of the first answer per case
        self.same_as_ids = {c["expected"].get("case_id") for _, c, _ in cases if c["expected"]["status"] == "same_as"}
        self.peer = {}  # (suite, case_id) -> first parsed answer, only for cases some same_as case points at
        self.deferred = []  # same_as cases judged after the first pass
        self.done = self.drift = self.errors = self.golden_failures = self.stderr_bytes = 0
        self.drift_examples, self.golden_examples = [], []
        self.pending = collections.deque()
        self.slots = threading.Semaphore(window)
        self.stop = threading.Event()
        self.paused = threading.Event()
        self.lock = threading.Lock()

    def writer(self, stdin):
        i = 0
        try:
            while not self.stop.is_set():
                if self.paused.is_set():
                    time.sleep(0.005)
                    continue
                if not self.slots.acquire(timeout=1.0):
                    continue
                k = i % len(self.cases)
                with self.lock:
                    self.pending.append(k)
                stdin.write(self.cases[k][2])
                stdin.flush()
                i += 1
        except OSError:
            pass
        finally:
            try:
                stdin.close()
            except OSError:
                pass

    def reader(self, stdout):
        for raw in stdout:
            with self.lock:
                k = self.pending.popleft() if self.pending else None
            self.slots.release()
            if k is None:
                self.errors += 1
                continue
            suite, case, _ = self.cases[k]
            digest = hashlib.sha256(raw).digest()
            if self.first[k] is None:
                self.first[k] = digest
                self.check_first(suite, case, raw)
            elif digest != self.first[k]:
                self.drift += 1
                if len(self.drift_examples) < 10:
                    self.drift_examples.append({"case_id": case["case_id"], "pass": self.done // len(self.cases) + 1})
            self.done += 1
            if self.done == len(self.cases):
                for s, c, res in self.deferred:
                    self.judge_one(s, c, res)

    def check_first(self, suite, case, raw):
        try:
            res = json.loads(raw, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
        except ValueError:
            self.errors += 1
            return
        if case["case_id"] in self.same_as_ids:
            self.peer[(suite, case["case_id"])] = res
        if case["expected"]["status"] == "same_as":
            self.deferred.append((suite, case, res))
        else:
            self.judge_one(suite, case, res)

    def judge_one(self, suite, case, res):
        peers = {cid: r for (s, cid), r in self.peer.items() if s == suite}
        status, msgs = judge(case, res, self.classes, peers)
        if status == "fail":
            self.golden_failures += 1
            if len(self.golden_examples) < 10:
                self.golden_examples.append({"case_id": case["case_id"], "why": "; ".join(msgs)[:200]})

    def quiesce(self, timeout=600.0):
        """Stops sending and waits until every case in flight is answered. True when idle."""
        self.paused.set()
        time.sleep(0.01)  # let a write already past the pause check land in `pending`
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.lock:
                if not self.pending:
                    return True
            time.sleep(0.002)
        return False

    def drain_stderr(self, stderr):
        for chunk in iter(lambda: stderr.read(4096), b""):
            self.stderr_bytes += len(chunk)


def commit():
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", required=True, choices=["python", "java", "cpp", "rust"])
    ap.add_argument("--minutes", type=float, default=130.0)
    ap.add_argument("--interval", type=float, default=10.0)
    ap.add_argument("--window", type=int, default=32)
    ap.add_argument("--out-dir", default=str(ROOT / "benchmarks" / "results" / "k6"))
    ap.add_argument("--tag", default=datetime.date.today().isoformat())
    ap.add_argument("--plant-leak", action="store_true")
    ap.add_argument("--leak-every", type=int, default=100, help="planted leak: 1 KiB kept per this many cases")
    ap.add_argument("--progress")
    ap.add_argument("--host", default=os.environ.get("QF_HOST_LABEL", LAPTOP))
    ap.add_argument("--normal-priority", action="store_true")
    a = ap.parse_args(argv)
    if a.plant_leak and a.impl != "python":
        print("--plant-leak is built into the Python entry point only", file=sys.stderr)
        return 2
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"soak-{a.impl}-{a.tag}"
    if a.plant_leak:
        stem += "-planted-leak" if a.leak_every == 100 else f"-planted-leak-every-{a.leak_every}"
    work = out / f".{stem}-work"
    work.mkdir(exist_ok=True)
    if not a.normal_priority:
        own_low_priority()
    cases = golden_cases()
    s = Soak(a.impl, cases, load_policy(ROOT / "conformance" / "tolerances" / "policy.yaml"), a.window)
    argv_, env, pidfile, gclog = command(a.impl, work)
    if a.plant_leak:
        env["QF_SOAK_LEAK"] = "1"
        env["QF_SOAK_LEAK_EVERY"] = str(a.leak_every)
    if pidfile and pidfile.exists():
        pidfile.unlink()
    if gclog and gclog.exists():
        gclog.unlink()
    started = datetime.datetime.now(datetime.UTC)
    try:
        proc = start(argv_, env, not a.normal_priority)
        pid = worker_pid(proc, pidfile)
    except (OSError, RuntimeError) as e:
        print(f"could not start: {e}", file=sys.stderr)
        return 2
    threads = [
        threading.Thread(target=s.writer, args=(proc.stdin,), daemon=True),
        threading.Thread(target=s.reader, args=(proc.stdout,), daemon=True),
        threading.Thread(target=s.drain_stderr, args=(proc.stderr,), daemon=True),
    ]
    for t in threads:
        t.start()
    jcmd = str(java_home() / "bin" / "jcmd") if a.impl == "java" and java_home() else "jcmd"
    t0 = time.monotonic()
    end = t0 + a.minutes * 60
    csv_path = out / f"{stem}.csv"
    died, last_done, next_gc, quiesce_fail = False, 0, t0 + 30, 0
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        tick = t0
        while True:
            tick += a.interval
            while time.monotonic() < tick and not died:
                died = proc.poll() is not None
                time.sleep(max(0.0, min(1.0, tick - time.monotonic())))
            judged, heap = None, None
            if not died:
                idle = s.quiesce()
                quiesce_fail += not idle
                snap = procstat.sample(pid) or {}
                if idle and a.impl == "java" and time.monotonic() >= next_gc:
                    heap = judged = heap_after_full_gc(jcmd, pid)
                    next_gc += 30
                elif idle and a.impl != "java" and snap:
                    judged = snap[procstat.judged_key()]
                s.paused.clear()
            else:
                snap = {}
            done = s.done
            row = {
                "t_s": round(time.monotonic() - t0, 1),
                "utc": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
                "judged_bytes": judged,
                "heap_after_gc_bytes": heap,
                "cases_total": done,
                "cases_window": done - last_done,
                "cases_per_s": round((done - last_done) / a.interval, 1),
                "passes": done // len(cases),
                "drift_total": s.drift,
                "errors_total": s.errors,
                "alive": 0 if died or not snap else 1,
            }
            for k in ("rss_bytes", "private_bytes", "peak_bytes", "handles", "threads"):
                row[k] = snap.get(k, "")
            w.writerow(row)
            f.flush()
            last_done = done
            if a.progress:
                Path(a.progress).write_text(
                    json.dumps(
                        {
                            "stem": stem,
                            "t_s": row["t_s"],
                            "of_s": a.minutes * 60,
                            "cases": done,
                            "drift": s.drift,
                            "errors": s.errors,
                            "golden_failures": s.golden_failures,
                            "alive": row["alive"],
                            "utc": row["utc"],
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
            if died or time.monotonic() >= end:
                break
    s.stop.set()
    try:
        code = proc.wait(timeout=600)
    except subprocess.TimeoutExpired:
        proc.kill()
        code = "killed after 600 s"
    for t in threads:
        t.join(timeout=30)
    summary = {
        "implementation": a.impl,
        "host": a.host,
        "commit": commit(),
        "started_utc": started.isoformat(),
        "finished_utc": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "minutes": a.minutes,
        "planted_leak": a.plant_leak,
        "leak_every": a.leak_every if a.plant_leak else None,
        "judged_key": procstat.judged_key(),
        "argv_tail": argv_[1:],
        "golden_cases": len(cases),
        "cases": s.done,
        "passes": s.done // len(cases),
        "drift": s.drift,
        "drift_examples": s.drift_examples,
        "golden_failures": s.golden_failures,
        "golden_examples": s.golden_examples,
        "errors": s.errors,
        "stderr_bytes": s.stderr_bytes,
        "exit_code": code,
        "died": died,
        "quiesce_timeouts": quiesce_fail,
        "platform": sys.platform,
        "csv": csv_path.name,
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
    }
    sum_path = out / f"{stem}.summary.json"
    sum_path.write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    verdict = analyse.analyse(rows, summary, planted=a.plant_leak)
    (out / f"{stem}.verdict.json").write_text(json.dumps(verdict, indent=1) + "\n", encoding="utf-8")
    print(
        f"{stem}: {verdict['verdict']} slope {verdict['slope_mib_per_h']} MiB/h CI {verdict['slope_ci95_mib_per_h']} "
        f"range {verdict['range_fraction_of_median']} cases {s.done} reasons {verdict['reasons']}"
    )
    return 0 if verdict["verdict"] in ("PASS", "LEAK CAUGHT") else 1


if __name__ == "__main__":
    sys.exit(main())
