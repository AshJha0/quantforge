"""R3 study data: download once, log provenance, split in-sample from holdout at load (amendment 4 C10).

Every file is fetched once into `research/r3/data/` (git-ignored) and logged in `research/r3/data_log.csv`
(name, window, source URL, UTC retrieval time, SHA-256 of the raw bytes). A file whose bytes no longer match
its log line is refused.

The split is by file: each file belongs to the in-sample or the holdout window of its study (Treasury files by
calendar year, NY Fed files by date range). `load_in_sample` parses in-sample files only and drops any row dated
after the in-sample end. Holdout files are downloaded and hashed but never parsed except by `load_holdout`,
which first calls `r3_runner.holdout_guard` (freeze commit plus a committed `holdout_runs.csv` line).
"""
from __future__ import annotations

import csv
import hashlib
import io
import sys
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3_runner

DATA = Path(__file__).resolve().parent / "r3" / "data"
LOG = Path(__file__).resolve().parent / "r3" / "data_log.csv"
LOG_FIELDS = ["name", "window", "url", "utc_retrieved", "sha256"]
TSY = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
       "{y}/all?type={t}&field_tdr_date_value={y}&page&_format=csv")
NYFED = "https://markets.newyorkfed.org/api/rates/secured/{r}/search.csv?startDate={a}&endDate={b}"
NOMINAL, REAL, BILL = "daily_treasury_yield_curve", "daily_treasury_real_yield_curve", "daily_treasury_bill_rates"
Series = dict[date, dict[str, float]]
Fetch = Callable[[str], bytes]


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    window: str  # "in" or "holdout"
    kind: str  # "treasury" or "nyfed"
    key: str  # series key in the loaded dict


def _years(study: str, t: str, first: int, last_in: int, last: int = 2026) -> list[Source]:
    # One file per study and year: the same Treasury year can be in-sample for one study and holdout for another.
    return [Source(f"{study}_{t}_{y}.csv", TSY.format(y=y, t=t), "in" if y <= last_in else "holdout",
                   "treasury", t) for y in range(first, last + 1)]


def _nyfed(rate: str) -> list[Source]:
    # Ranges by calendar boundary; rows are filtered to each window at parse.
    return [Source(f"R3-02_nyfed_{rate}_in.csv", NYFED.format(r=rate, a="2018-04-02", b="2022-12-31"), "in",
                   "nyfed", rate.upper()),
            Source(f"R3-02_nyfed_{rate}_holdout.csv", NYFED.format(r=rate, a="2023-01-01", b="2026-12-31"),
                   "holdout", "nyfed", rate.upper())]


SOURCES: dict[str, list[Source]] = {
    "R3-01": _years("R3-01", NOMINAL, 1990, 2012),
    "R3-02": _years("R3-02", BILL, 2018, 2022) + _nyfed("sofr") + _nyfed("tgcr") + _nyfed("bgcr"),
    "R3-03": _years("R3-03", NOMINAL, 2003, 2015) + _years("R3-03", REAL, 2003, 2015),
}
# Columns each study may see. R3-03's in-sample years 2013-2015 are R3-01 holdout years: R3-03 never parses the
# 2Y column, so the R3-01 fly cannot be formed from what R3-03 loads.
COLUMNS: dict[tuple[str, str], tuple[str, ...]] = {
    ("R3-01", NOMINAL): ("2 YR", "5 YR", "10 YR"),
    ("R3-02", BILL): ("13 WEEKS COUPON EQUIVALENT",),
    ("R3-03", NOMINAL): ("5 YR", "10 YR"),
    ("R3-03", REAL): ("5 YR", "10 YR"),
}


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "research-client"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data: bytes = r.read()
    return data


def read_log(log: Path = LOG) -> dict[str, dict[str, str]]:
    if not log.exists():
        return {}
    with log.open(newline="", encoding="utf-8") as f:
        return {row["name"]: row for row in csv.DictReader(f)}


def fetch(src: Source, fetcher: Fetch = http_get, data: Path = DATA, log: Path = LOG) -> str:
    """Download once and log; afterwards verify. Returns the SHA-256. Never parses the bytes."""
    path, logged = data / src.name, read_log(log).get(src.name)
    if logged is not None:
        if logged["url"] != src.url or logged["window"] != src.window:
            raise ValueError(f"{src.name}: log line names another source")
        if not path.exists():
            raise FileNotFoundError(f"{src.name}: logged but missing; restore the logged bytes")
        verify(src.name, data, log)
        return logged["sha256"]
    raw = fetcher(src.url)
    sha = hashlib.sha256(raw).hexdigest()
    data.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    new = not log.exists()
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow({"name": src.name, "window": src.window, "url": src.url,
                    "utc_retrieved": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "sha256": sha})
    return sha


def verify(name: str, data: Path = DATA, log: Path = LOG) -> bytes:
    raw = (data / name).read_bytes()
    want = read_log(log)[name]["sha256"]
    if hashlib.sha256(raw).hexdigest() != want:
        raise ValueError(f"{name}: SHA-256 differs from its log line; refused")
    return raw


def parse_treasury(raw: bytes) -> Series:
    out: Series = {}
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        m, d, y = (int(x) for x in row.pop("Date").split("/"))
        out[date(y, m, d)] = {k.strip().upper(): float(v) for k, v in row.items() if v not in ("", None)}
    return out


def parse_nyfed(raw: bytes) -> Series:
    out: Series = {}
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        v = row.get("Rate (%)", "")
        if v:
            y, m, d = (int(x) for x in row["Effective Date"].split("-")) if "-" in row["Effective Date"] \
                else _mdy(row["Effective Date"])
            out[date(y, m, d)] = {row["Rate Type"].strip().upper(): float(v)}
    return out


def _mdy(s: str) -> tuple[int, int, int]:
    m, d, y = (int(x) for x in s.split("/"))
    return y, m, d


def _merge(dst: dict[str, Series], key: str, s: Series, lo: date, hi: date) -> None:
    tgt = dst.setdefault(key, {})
    for d, v in s.items():
        if lo <= d <= hi:
            tgt.setdefault(d, {}).update(v)


def _load(study: str, window: str, lo: date, hi: date, data: Path, log: Path) -> dict[str, Series]:
    out: dict[str, Series] = {}
    for src in SOURCES[study]:
        if src.window != window:
            continue
        raw = verify(src.name, data, log)
        if src.kind == "treasury":
            keep = COLUMNS[(study, src.key)]
            s = {d: {k: v for k, v in row.items() if k in keep} for d, row in parse_treasury(raw).items()}
        else:
            s = parse_nyfed(raw)
        _merge(out, src.key, s, lo, hi)
    return out


def load_in_sample(study: str, data: Path = DATA, log: Path = LOG) -> dict[str, Series]:
    """In-sample files only, rows dated on or before the in-sample end. Keys: Treasury file type or NY Fed rate."""
    return _load(study, "in", date(1900, 1, 1), r3_runner.IN_SAMPLE_END[study], data, log)


def load_holdout(study: str, freeze_commit: str, data: Path = DATA, log: Path = LOG,
                 git: Callable[..., str] = r3_runner._git) -> dict[str, Series]:
    """Holdout files, rows inside the holdout window. Refused unless the runner's guard passes."""
    hi = r3_runner.HOLDOUT[study][1]
    r3_runner.holdout_guard(r3_runner.GuardInputs(study, hi, freeze_commit, r3_runner.script_sha256()), git=git)
    after_in = date.fromordinal(r3_runner.IN_SAMPLE_END[study].toordinal() + 1)
    return _load(study, "holdout", after_in, hi, data, log)


def fetch_all(fetcher: Fetch = http_get) -> dict[str, str]:
    return {s.name: fetch(s, fetcher) for srcs in SOURCES.values() for s in srcs}


if __name__ == "__main__":
    for n, h in fetch_all().items():
        print(n, h)
