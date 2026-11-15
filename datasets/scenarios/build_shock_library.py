#!/usr/bin/env python3
"""Build the historical shock library (G18, rulings J-W3-6 and J-W3-7) from stored Treasury par yield files.

    python datasets/scenarios/build_shock_library.py --fetch   # download raw files once, record provenance
    python datasets/scenarios/build_shock_library.py           # verify hashes, build us_treasury_shocks.json, check H.15

Raw files: raw/ust_<year>.csv (home.treasury.gov daily par yield curve, public domain) and raw/fred_<series>.csv
(FRED, Federal Reserve H.15 constant maturities, no account). raw/provenance.csv records URL, UTC retrieval time and
SHA-256 of every file. The build refuses a raw file whose hash differs from its provenance row.
"""
import argparse
import csv
import hashlib
import io
import json
import sys
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
PROV = RAW / "provenance.csv"
OUT = HERE / "us_treasury_shocks.json"
UST = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
       "{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv")
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}&cosd=2008-09-01&coed=2022-10-31"
YEARS = (2008, 2013, 2020, 2021, 2022)
TENORS = (("1 Mo", 1 / 12, "DGS1MO"), ("3 Mo", 0.25, "DGS3MO"), ("6 Mo", 0.5, "DGS6MO"), ("1 Yr", 1.0, "DGS1"),
          ("2 Yr", 2.0, "DGS2"), ("3 Yr", 3.0, "DGS3"), ("5 Yr", 5.0, "DGS5"), ("7 Yr", 7.0, "DGS7"),
          ("10 Yr", 10.0, "DGS10"), ("20 Yr", 20.0, "DGS20"), ("30 Yr", 30.0, "DGS30"))
# Fixed in specifications/stage-j-rulings-w3.md J-W3-6 before any file was downloaded.
SCENARIOS = (("gfc_2008", "2008-09-12", "2008-12-31", "Lehman's last trading day to year end"),
             ("taper_2013", "2013-05-01", "2013-09-05", "taper tantrum"),
             ("covid_2020", "2020-02-19", "2020-03-09", "Covid rally"),
             ("hikes_2022", "2021-12-31", "2022-10-21", "2022 hiking cycle"))
H15_TOL = 0.005  # percentage points, half the published rounding unit (J-W3-7)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def get(url: str) -> bytes:
    # curl, not urllib: FRED times out urllib requests from this client (seen 2026-11-15); curl's defaults work.
    r = subprocess.run(["curl", "-s", "-f", "-m", "90", url], capture_output=True, check=True)
    return r.stdout


def sources() -> list[tuple[str, str]]:
    return [(f"ust_{y}.csv", UST.format(y=y)) for y in YEARS] + [(f"fred_{s}.csv", FRED.format(s=s)) for _, _, s in TENORS]


def fetch() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, url in sources():
        b = get(url)
        (RAW / name).write_bytes(b)
        rows.append({"name": name, "url": url, "utc_retrieved": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "sha256": sha(b)})
        print(name, len(b), "bytes")
    with PROV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["name", "url", "utc_retrieved", "sha256"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def verified(name: str) -> bytes:
    prov = {r["name"]: r for r in csv.DictReader(PROV.open(encoding="utf-8"))}
    b = (RAW / name).read_bytes()
    if sha(b) != prov[name]["sha256"]:
        raise SystemExit(f"{name}: hash differs from provenance.csv")
    return b


def treasury() -> dict[date, dict[str, float]]:
    """All stored Treasury rows: date -> {column label: percent}; blank cells are absent (J-W3-5)."""
    out: dict[date, dict[str, float]] = {}
    for y in YEARS:
        for row in csv.DictReader(io.StringIO(verified(f"ust_{y}.csv").decode("utf-8-sig"))):
            m, d, yy = (int(x) for x in row.pop("Date").split("/"))
            out[date(yy, m, d)] = {k.strip(): float(v) for k, v in row.items() if v not in ("", None)}
    return out


def fred(series: str) -> dict[date, float]:
    out: dict[date, float] = {}
    for row in csv.DictReader(io.StringIO(verified(f"fred_{series}.csv").decode("utf-8-sig"))):
        v = row[series]
        if v not in ("", "."):
            out[date.fromisoformat(row["observation_date"])] = float(v)
    return out


def build() -> dict:
    ust = treasury()
    h15 = {s: fred(s) for _, _, s in TENORS}
    prov = {r["name"]: r["sha256"] for r in csv.DictReader(PROV.open(encoding="utf-8"))}
    lib, worst = [], 0.0
    for name, a, b, what in SCENARIOS:
        da, db = date.fromisoformat(a), date.fromisoformat(b)
        if da not in ust or db not in ust:
            raise SystemExit(f"{name}: a named date has no Treasury row; J-W3-3 says use the previous row and say so")
        kept = [(lab, t, s) for lab, t, s in TENORS if lab in ust[da] and lab in ust[db]]
        dropped = [lab for lab, _, _ in TENORS if lab not in {k[0] for k in kept}]
        start = [ust[da][lab] for lab, _, _ in kept]
        end = [ust[db][lab] for lab, _, _ in kept]
        h15_check = []
        for (lab, _, s), y0, y1 in zip(kept, start, end, strict=True):
            for d, y in ((da, y0), (db, y1)):
                ref = h15[s].get(d)
                gap = None if ref is None else abs(ref - y)
                if gap is not None:
                    worst = max(worst, gap)
                h15_check.append({"tenor": lab, "date": d.isoformat(), "treasury": y, "h15": ref,
                                  "pass": gap is not None and gap <= H15_TOL})
        lib.append({"name": name, "description": what, "start_date": a, "end_date": b,
                    "tenor_labels": [lab for lab, _, _ in kept], "tenors": [t for _, t, _ in kept],
                    "dropped_tenors": dropped, "start_yields": start, "end_yields": end,
                    "shift_bp": [100 * (y1 - y0) for y0, y1 in zip(start, end, strict=True)],
                    "raw_files": {f"ust_{y}.csv": prov[f"ust_{y}.csv"] for y in sorted({da.year, db.year})},
                    "h15_check": h15_check, "h15_pass": all(c["pass"] for c in h15_check)})
    return {"schema_version": "1.0", "built_by": "datasets/scenarios/build_shock_library.py",
            "units": {"yields": "percent", "shift_bp": "basis points", "tenors": "years"},
            "source": "U.S. Department of the Treasury, Daily Treasury Par Yield Curve Rates (public domain)",
            "outside_check": f"Federal Reserve H.15 via FRED, tolerance {H15_TOL} percentage points (J-W3-7)",
            "h15_worst_gap": worst, "scenarios": lib}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    if ap.parse_args().fetch:
        fetch()
    doc = build()
    OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    for s in doc["scenarios"]:
        sb = dict(zip(s["tenor_labels"], s["shift_bp"], strict=True))
        print(f"{s['name']}: 2Y {sb.get('2 Yr', float('nan')):+.0f} bp, 10Y {sb.get('10 Yr', float('nan')):+.0f} bp, "
              f"H.15 {'pass' if s['h15_pass'] else 'FAIL'}, dropped {s['dropped_tenors']}")
    print(f"H.15 worst gap {doc['h15_worst_gap']:.4f} pp")
    return 0 if all(s["h15_pass"] for s in doc["scenarios"]) else 1


if __name__ == "__main__":
    sys.exit(main())
