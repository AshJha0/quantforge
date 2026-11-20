#!/usr/bin/env python3
"""Site stub for the daily curve run: one Markdown section from the latest-fit summary (KR-106).

  site_page.py [--data tools/curve_daily/site/latest.json] [--out FILE]

The data file is the `summary.json` that run_day.py and verify_chain.py write on branch curve-daily; the copy in
this folder is a placeholder until the first scheduled run. No existing site page calls this yet: the hook for
tools/build_site.py or tools/build_gallery.py is `render(json.load(...))`, which returns Markdown. Every number
printed keeps its labels: the curve label, the timing (on time or late), and "consistency check, not proof".
Every page also states the one recorded result from before the scheduled runs (MISS_NOTE): the dry run for
2026-11-13 was outside the 15 bp tolerance, a recorded miss of the consistency check.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "site" / "latest.json"
# Measured 2026-11-19 on the local laptop (dry run, nothing pushed); 12-platform/daily-curve-run.md, worked example.
MISS_NOTE = ("Recorded miss: on the one real day tried before the scheduled runs (2026-11-13, dry run of 2026-11-19), "
             "the comparison with the Federal Reserve's fitted curve was outside the 15 bp RMSE tolerance fixed "
             "beforehand (RMSE 17.36 bp, largest 25.71 bp at 22 years). The fit weights were changed once after one "
             "real day had been seen; the tolerance and the method were not changed afterwards. This is a "
             "consistency check, not proof, and a row outside the tolerance is recorded as outside, never dropped.")


def render(s):
    out = ["## Daily curve run", "",
           f"Label: {s.get('label', '')}.", "", MISS_NOTE, ""]
    latest = s.get("latest")
    if not s.get("ok") or latest is None:
        out += ["No verified daily fit yet. The run is scheduled from v0.10.1 (2026-11-20); the workflow "
                "`.github/workflows/curve-daily.yml` has three cron slots; rows would live on branch `curve-daily` "
                "(`ledger/curves.jsonl`).", ""]
        return "\n".join(out)
    c = latest["consistency"]
    out += [
        f"Latest settled fit: {latest['date']} ({latest['timing'].replace('_', ' ')}), Nelson-Siegel tau "
        f"{latest['tau']} years, RMSE {float(latest['rmse_bp']):.2f} bp and largest error "
        f"{float(latest['max_abs_bp']):.2f} bp against the Treasury par yields it was fitted to.", "",
        "| Years | " + " | ".join(str(int(k)) for k in ("01", "02", "05", "10", "20", "30")) + " |",
        "|---|" + "---:|" * 6,
        "| Zero rate, % (continuous) | " + " | ".join(f"{float(latest['zeros_pct'][k]):.3f}"
                                                  for k in ("01", "02", "05", "10", "20", "30")) + " |", "",
    ]
    if c["status"] == "pending":
        out.append("Comparison with the Federal Reserve's fitted curve: pending (the Fed posts weekly).")
    elif "rmse_bp" in c:
        out.append(f"Comparison with the Federal Reserve's fitted curve ({c['label']}): {c['status']} the stated "
                   f"tolerance, RMSE {float(c['rmse_bp']):.2f} bp, largest {float(c['max_abs_bp']):.2f} bp.")
    else:
        out.append(f"Comparison with the Federal Reserve's fitted curve: {c['status']}.")
    out += ["", f"Chain head `{s['head'][:16]}`, {s['records']} rows. Sources: US Department of the Treasury; Board of "
            "Governors of the Federal Reserve System.", ""]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    text = render(json.loads(Path(a.data).read_text(encoding="utf-8")))
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
