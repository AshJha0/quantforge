#!/usr/bin/env python3
"""List every forward-log row and tracked file that carries an observation inside an R3 study's holdout window.

Finding 1 of the 2026-11-12 review, reproduced by script (R6-19). Holdout windows are read from the prereg files;
study inputs from tools/recorder/studies.json.

What counts as an observation:
- forward log: an entry in a row's `observations` whose date key (YYYY-MM-DD or YYYY-MM) falls inside the holdout
  window of a study that lists the row's source as an input;
- tracked file (.json, .jsonl, .csv, .md, .html): a date inside a study's window in a file that also names one of
  that study's real sources (MARKERS below). Synthetic test dates in files that name no real study source are not
  observations of study data and are not reported.

  python research/holdout_scan.py [--log FILE | --log-ref origin/forward-log] [--files]

Prints one line per hit: <location>\t<study>\t<count>\t<first date>\t<last date>. research/test_preregs.py fails on
any hit not listed in research/preregs/DEVIATION-2026-11-12.md.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREREGS = {"R3-01": "R3-01-treasury-fly.md", "R3-02": "R3-02-bill-repo-spread.md", "R3-03": "R3-03-breakeven-seasonality.md"}
# Words that tie a tracked file to a study's real input data.
MARKERS = {
    "R3-01": r"home\.treasury\.gov|daily_treasury_yield_curve|us-treasury-par-yields|Treasury par",
    "R3-02": r"newyorkfed|nyfed-|\bSOFR\b|\bTGCR\b|\bBGCR\b|daily_treasury_bill_rates|us-treasury-bill-rates",
    "R3-03": r"home\.treasury\.gov|us-treasury-par-yields|us-treasury-real-yields|daily_treasury_real|bls\.gov|bls-cpi|CUUR0000SA0",
}
DATE = re.compile(r"(?<![\d-])(\d{4}-\d{2}(?:-\d{2})?)(?![\d-])")
SKIP = ("research/preregs/", "program/", "CHANGELOG.md", "ROADMAP.md")  # prose about the studies, not data


def windows():
    out = {}
    for sid, name in PREREGS.items():
        t = (ROOT / "research" / "preregs" / name).read_text(encoding="utf-8")
        m = re.search(r"Holdout: (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})", t)
        out[sid] = (m.group(1), m.group(2))
    return out


def inside(d, w):
    lo, hi = w
    if len(d) == 7:  # a month overlaps the window
        return lo[:7] <= d <= hi[:7]
    return lo <= d <= hi


def study_inputs():
    st = json.loads((ROOT / "tools" / "recorder" / "studies.json").read_text(encoding="utf-8"))["studies"]
    return {s["id"]: set(s["inputs"]) for s in st}


def scan_log(lines, w=None, inputs=None):
    w, inputs = w or windows(), inputs or study_inputs()
    hits = []
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        r = json.loads(line)["record"]
        sid = r["series_id"]
        if not sid.startswith("recorder/"):
            continue
        v = r["value"]
        obs = (v.get("payload", v) or {}).get("observations") or {}
        src = sid.split("/", 1)[1]
        for study, ins in inputs.items():
            if src not in ins:
                continue
            ds = sorted(k.split("|")[0] for k in obs if inside(k.split("|")[0], w[study]))
            if ds:
                hits.append((f"forward-log:actions/log.jsonl#row{n}:{src}", study, len(ds), ds[0], ds[-1]))
    return hits


def scan_text(path, text, w=None):
    w = w or windows()
    hits = []
    for study, mk in MARKERS.items():
        if not re.search(mk, text):
            continue
        ds = sorted(d for d in DATE.findall(text) if inside(d, w[study]))
        if ds:
            hits.append((path, study, len(ds), ds[0], ds[-1]))
    return hits


def tracked(ref=None):
    """Tracked data files of the working tree, or of a git ref (for the forward-log branch)."""
    if ref:
        names = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
        get = lambda n: subprocess.run(["git", "show", f"{ref}:{n}"], cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8", "replace")
        prefix = ref.split("/")[-1] + ":"
    else:
        names = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
        get = lambda n: (ROOT / n).read_text(encoding="utf-8", errors="replace")
        prefix = ""
    for n in names:
        if n.endswith((".json", ".jsonl", ".csv", ".md", ".html")) and not n.startswith(SKIP) and n != "actions/log.jsonl":
            if ref or (ROOT / n).exists():
                yield prefix + n, get(n)


def scan_all(log_ref="origin/forward-log"):
    w = windows()
    hits = []
    for p, t in tracked():
        hits += scan_text(p, t, w)
    have = subprocess.run(["git", "rev-parse", "--verify", "-q", log_ref], cwd=ROOT, capture_output=True).returncode == 0
    if have:
        log = subprocess.run(["git", "show", f"{log_ref}:actions/log.jsonl"], cwd=ROOT, capture_output=True, check=True).stdout.decode()
        hits += scan_log(log.splitlines(), w)
        for p, t in tracked(log_ref):
            hits += scan_text(p, t, w)
    return hits, have


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", help="scan this log file only")
    ap.add_argument("--log-ref", default="origin/forward-log")
    a = ap.parse_args()
    if a.log:
        hits = scan_log(Path(a.log).read_text(encoding="utf-8").splitlines())
    else:
        hits, have = scan_all(a.log_ref)
        if not have:
            print(f"note: {a.log_ref} not found; forward log not scanned", file=sys.stderr)
    for h in hits:
        print("\t".join(map(str, h)))


if __name__ == "__main__":
    main()
