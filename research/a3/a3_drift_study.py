#!/usr/bin/env python3
"""A3 drift-detector study (prereg research/preregs/A3-drift.md).

The real run (seeds 20261109 and 20261110, 2,000 paths) is refused unless the prereg is signed, its body matches its
recorded hash, this file and python/quantforge_core/drift.py match the hashes in the prereg header, and the output does
not exist. Unit tests call `study(...)` with other seeds and few paths.

    python research/a3/a3_drift_study.py [--dry-run]
"""
import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "python"))
from quantforge_core import drift

PREREG = ROOT / "research" / "preregs" / "A3-drift.md"
OUTPUT = HERE / "a3_output.json"
DRIFT = ROOT / "python" / "quantforge_core" / "drift.py"
MARK = b"<!-- body -->"
BREAK = 500


def se_share(p: float, n: int) -> float:
    return math.sqrt(p * (1 - p) / n)


def delays(paths: np.ndarray, detect: Any) -> tuple[list[float], int]:
    out, false = [], 0
    for x in paths:
        alarms = detect(x.tolist())["alarms"]
        false += sum(a < BREAK for a in alarms)
        after = [a for a in alarms if a >= BREAK]
        out.append(float(after[0] - BREAK) if after else math.inf)
    return out, false


def delay_summary(d: list[float], false: int) -> dict[str, Any]:
    n = len(d)
    s = sorted(d)
    # order-statistic 95% interval for the median (normal approximation to the binomial)
    lo, hi = max(0, int(n / 2 - 1.96 * math.sqrt(n) / 2)), min(n - 1, math.ceil(n / 2 + 1.96 * math.sqrt(n) / 2))
    share = sum(v <= 40 for v in d) / n
    return {"median": statistics.median(d), "median_ci95": [s[lo], s[hi]], "share_within_40": share,
            "share_se": se_share(share, n), "pre_break_alarms": false}


def study(seed_null: int = 20261109, seed_break: int = 20261110, paths: int = 2000) -> dict[str, Any]:
    rng = np.random.default_rng(seed_null)
    null = rng.standard_normal((paths, 1000))
    arl = rng.standard_normal((paths, 5000))
    rng = np.random.default_rng(seed_break)
    mean_break = rng.standard_normal((paths, 1000))
    mean_break[:, BREAK:] += 1.0
    var_break = rng.standard_normal((paths, 1000))
    var_break[:, BREAK:] *= math.sqrt(2.0)

    run = []
    censored = 0
    for x in arl:
        a = drift.cusum(x.tolist(), 0.5, 5.0, reset=False)["alarms"]
        run.append(a[0] + 1 if a else 5000)
        censored += not a
    arl0 = statistics.fmean(run)
    out: dict[str, Any] = {"paths": paths, "cusum": {"arl0": arl0, "arl0_se": statistics.stdev(run) / math.sqrt(paths),
                                                     "arl0_censored": censored}}
    out["cusum"].update(delay_summary(*delays(mean_break, lambda x: drift.cusum(x, 0.5, 5.0))))
    out["page_hinkley"] = delay_summary(*delays(mean_break, lambda x: drift.page_hinkley(x, 0.5, 50.0)))

    def psi_any(x: np.ndarray) -> bool:
        ref = x[:250].tolist()
        return any(drift.psi(ref, x[a:a + 250].tolist())["alarm"] for a in (250, 500, 750))
    fa = sum(psi_any(x) for x in null) / paths
    det = sum(drift.psi(x[:250].tolist(), x[500:750].tolist())["alarm"] for x in var_break) / paths
    out["psi"] = {"false_alarm_share": fa, "false_alarm_se": se_share(fa, paths), "detect_share": det,
                  "detect_se": se_share(det, paths)}
    size = sum(drift.ks(x[:250].tolist(), x[250:500].tolist())["reject"] for x in null) / paths
    power = sum(drift.ks(x[250:500].tolist(), x[500:750].tolist())["reject"] for x in var_break) / paths
    out["ks"] = {"size": size, "size_se": se_share(size, paths), "power": power, "power_se": se_share(power, paths)}
    c, p, s, k = out["cusum"], out["page_hinkley"], out["psi"], out["ks"]
    out["verdicts"] = {
        "cusum": 400 <= c["arl0"] <= 540 and c["median"] <= 15 and c["share_within_40"] >= 0.95,
        "page_hinkley": p["median"] <= 15 and p["share_within_40"] >= 0.95,
        "psi": s["false_alarm_share"] <= 0.02 and s["detect_share"] >= 0.95,
        "ks": 0.035 <= k["size"] <= 0.065 and k["power"] >= 0.95}
    return out


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def guard(prereg: Path = PREREG, output: Path = OUTPUT) -> None:
    if output.exists():
        raise SystemExit(f"refused: {output.name} exists; A3 is run once")
    b = prereg.read_bytes()
    if MARK not in b:
        raise SystemExit("refused: prereg has no body marker")
    head = b[:b.index(MARK)].decode()
    if "Status: **signed**" not in head:
        raise SystemExit("refused: prereg A3 is not signed")
    if hashlib.sha256(b[b.index(MARK) + len(MARK):]).hexdigest() not in head:
        raise SystemExit("refused: prereg A3 body differs from its recorded hash")
    for f in (Path(__file__).resolve(), DRIFT):
        m = re.search(rf"`{re.escape(f.name)}` \(whole file\): `([0-9a-f]{{64}})`", head)
        if not m or m.group(1) != sha(f):
            raise SystemExit(f"refused: {f.name} differs from the hash in prereg A3")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="check the guard, draw nothing")
    a = ap.parse_args()
    guard()
    if a.dry_run:
        print("guard passed; nothing drawn")
        sys.exit(0)
    result = study()
    OUTPUT.write_text(json.dumps(result, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result["verdicts"]))
