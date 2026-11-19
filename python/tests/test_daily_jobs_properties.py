"""State-machine properties of the two daily writers (audit KA-C9, rulings KR-203 and KR-210).

Each writer is driven through 10,000 randomly generated sequences of runs: on time, stale input, failed
fetch, a download that is not the file, a failed fit, a date the source never publishes, missed runs, reruns
at the same instant, two runs on one day, a run after an outage of many days, a clock that goes backwards, and
a prereg holdout window over a date. After every run the test asserts that

- the ledger only grew (append-only) and the verifier accepts it, with the library calendar;
- no business day was silently skipped: every business day from the first to the last date has a row, in
  order, and at most the last one is unsettled;
- nothing was back-filled: the ledger starts at the day due when it was started, no row is written before its
  day is due, and no fit is written after its late window;
- every settled outcome is true of the simulated world (an `ok` day was published, a `not_published` gap was
  skipped by the source, and so on);
- the run did not refuse, except when the clock went backwards, and a refusal leaves the next run unharmed.

The generator is the standard library's `random.Random` with a fixed seed per sequence, so a failure names the
sequence number and replays exactly. The curve fit and the bond prices are replaced by a constant stand-in
(the schedule logic does not read them); the calendar is the library's `USGS`, read once through the CLI
contract. The paper ledger runs its real day builder through the CLI contract. No market data is in this file:
every yield is invented from the date."""

import copy
import datetime as dt
import hashlib
import importlib.util
import json
import os
import random
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from quantforge_core.cli.main import run_case

ROOT = Path(__file__).resolve().parents[2]
SEQUENCES = 10_000  # the count the audit response states; do not lower it


def _load(name: str, path: Path) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(ROOT / "tools" / "curve_daily"))
sys.path.insert(0, str(ROOT / "tools" / "paper_daily"))
curve = _load("curve_core", ROOT / "tools" / "curve_daily" / "curve_core.py")
paper = _load("paper_core", ROOT / "tools" / "paper_daily" / "paper_core.py")
fl = _load("forward_log_for_paper", ROOT / "tools" / "forward-log" / "forward_log.py")
UTC = dt.UTC
FIRST, LAST = (
    dt.date(2027, 10, 1),
    dt.date(2029, 12, 31),
)  # the starts span a year end and market holidays
OPEN: dict[dt.date, bool] = {}


def _calendar() -> dict[dt.date, bool]:
    """Every date of the test span from the library calendar, once."""
    if not OPEN:
        d = FIRST
        while d <= LAST:
            r = run_case(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "case_id": "c",
                        "operation": "core.calendar.is_business_day",
                        "inputs": {"calendar": "USGS", "date": d.isoformat()},
                    }
                )
            )
            OPEN[d] = bool(r["outputs"]["is_business_day"])
            d += dt.timedelta(days=1)
    return OPEN


def business_days() -> list[dt.date]:
    cal = _calendar()
    return [d for d in sorted(cal) if cal[d]]


# ------------------------------------------------------------------ the curve writer


def curve_config() -> dict[str, Any]:
    """The real configuration with a small fit: three tenors, one tau, two probes. The schedule rules (due time,
    cut-off, late window, calendar) are the real ones; only the size of a row is cut down."""
    cfg: dict[str, Any] = copy.deepcopy(curve.load_config())
    cfg["tenors"] = cfg["tenors"][:3]
    cfg["fit"]["tau_grid"] = ["2"]
    cfg["fit"]["probe_years"] = ["1", "2"]
    return cfg


CCFG = curve_config()
BAD_CELL = "-250"


def curve_runner(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Calendar from the library (cached); pricing and fit replaced by constants. A coupon of -2.5 (the planted
    bad cell) fails the price operation with E_DOMAIN, as the library does."""
    cal = _calendar()
    out: dict[str, dict[str, Any]] = {}
    for c in cases:
        op, i = c["operation"], c["inputs"]
        if op == "core.calendar.is_business_day":
            d = dt.date.fromisoformat(i["date"])
            o: dict[str, Any] = {"is_business_day": cal[d]}
        elif op == "bond.price.from_yield":
            if i["yield"] < 0:
                out[c["case_id"]] = {
                    "status": "error",
                    "error": {"code": "E_DOMAIN", "message": "yield"},
                }
                continue
            o = {"dirty": 100.0, "accrued": 0.0, "clean": 100.0, "modified_duration": 2.0}
        elif op == "bond.fit.nelson_siegel":
            o = {"betas": [0.04, -0.01, 0.01], "residuals": [0.0] * len(i["bonds"])}
        elif op == "bond.yield.from_price":
            o = {"yield": i["bond"]["coupon"]}
        else:
            raise AssertionError(op)
        out[c["case_id"]] = {"status": "ok", "outputs": o}
    return out


CCAL = curve.Calendar(curve_runner, CCFG["calendar"])


class CurveWorld:
    """What the source would serve at any instant: each business day is published at some time, or never, or
    with an unreadable cell."""

    def __init__(self, rng: random.Random, days: list[dt.date]):
        self.days = days
        self.published: dict[dt.date, dt.datetime | None] = {}
        self.bad: set[dt.date] = set()
        for d in days:
            x = rng.random()
            base = dt.datetime.combine(d, dt.time(22, 0), UTC)
            if x < 0.07:
                self.published[d] = None  # the source never publishes this business day
            elif x < 0.30:
                self.published[d] = base + dt.timedelta(
                    hours=rng.choice([3, 9, 20, 30, 50, 100, 200])
                )
            else:
                self.published[d] = base
            if rng.random() < 0.06:
                self.bad.add(d)

    def has(self, d: dt.date, now: dt.datetime) -> bool:
        p = self.published.get(d)
        return p is not None and p <= now

    def csv(self, year: int, now: dt.datetime) -> bytes:
        rows = ["Date," + ",".join(t["field"] for t in CCFG["tenors"])]
        for d in sorted(self.days, reverse=True):
            if d.year == year and self.has(d, now):
                cell = BAD_CELL if d in self.bad else "4.25"
                rows.append(
                    f"{d.month:02d}/{d.day:02d}/{d.year}," + ",".join([cell] * len(CCFG["tenors"]))
                )
        return ("\n".join(rows) + "\n").encode()

    def later_published(self, d: dt.date, now: dt.datetime) -> bool:
        return any(x > d and self.has(x, now) for x in self.days)


def gsw_bytes(days: list[dt.date], upto: dt.date) -> bytes:
    head = ["test stand-in", "Date,SVENY01,SVENY02"]
    return (
        "\n".join(head + [f"{d.isoformat()},4.0000,4.1000" for d in days if d <= upto]) + "\n"
    ).encode()


def curve_sequence(seed: int) -> None:
    rng = random.Random(seed)
    days = business_days()
    start = rng.randrange(20, 130)
    span = days[start : start + 45]
    world = CurveWorld(rng, span)
    windows: dict[str, tuple[str, str]] = {}
    if rng.random() < 0.15:
        w = span[rng.randrange(2, 12)]
        windows = {
            "T-PLANTED": (w.isoformat(), (w + dt.timedelta(days=rng.choice([0, 1, 4]))).isoformat())
        }
    now = dt.datetime.combine(span[1], dt.time(rng.choice([0, 4, 15, 23]), rng.randrange(60)), UTC)
    text = ""
    year_of = re.compile(r"/(\d{4})/all")
    for _step in range(rng.randrange(5, 11)):
        mode = rng.choices(["ok", "fail", "html", "empty"], [0.8, 0.1, 0.07, 0.03])[0]
        back = bool(text) and rng.random() < 0.04
        when = now - dt.timedelta(hours=rng.choice([1, 30])) if back else now

        def fetch(url: str, mode: str = mode, when: dt.datetime = when) -> bytes:
            if url == CCFG["gsw"]["url"]:
                if rng.random() < 0.5:
                    raise OSError("planted")
                return gsw_bytes(span, (when - dt.timedelta(days=rng.choice([0, 3, 9]))).date())
            if mode == "fail":
                raise OSError("planted fetch failure")
            if mode == "html":
                return b"<!DOCTYPE html>\n<html><body>maintenance</body></html>\n"
            if mode == "empty":
                return b""
            m = year_of.search(url)
            assert m is not None
            return world.csv(int(m[1]), when)

        try:
            out, new, _ = curve.run(
                CCFG, curve_runner, text, when, fetch, "c", "1.17.0", "python", windows
            )
        except curve.CurveError as e:
            assert back and "clock" in str(e), (seed, _step, str(e))
            out, new = text, []
        else:
            assert not back or when >= curve.instant(curve.parse(text)[-1]["ts"]), (seed, _step)
        assert out.startswith(text), (seed, _step, "append-only")
        if out:
            v = curve.verify(out, CCFG, curve_runner, windows)
            assert v["ok"], (seed, _step, v)
            curve_invariants(seed, _step, out, when if not back else None, mode, world, windows)
        text = out
        now += dt.timedelta(
            minutes=rng.choice(
                [0, 0, 5, 40, 180, 400, 540, 900, 1440, 1500, 2900, 4400, 10000, 21000, 36000]
            )
        )


def curve_invariants(
    seed: int,
    step: int,
    text: str,
    now: dt.datetime | None,
    mode: str,
    world: CurveWorld,
    windows: dict[str, tuple[str, str]],
) -> None:
    rows = curve.parse(text)
    dated = [r for r in rows if r["kind"] in ("DAY", "GAP")]
    where = (seed, step)
    assert rows[0]["kind"] == "GENESIS" and dated, where
    g = curve.instant(rows[0]["ts"])
    first = curve.day(dated[0]["body"]["date"])
    assert first == curve.latest_due(g, CCAL, CCFG), (
        where,
        "the start is the latest day due, never earlier",
    )
    settled: dict[dt.date, dict[str, Any]] = {}
    seen: list[dt.date] = []
    for r in dated:
        d, b, t = curve.day(r["body"]["date"]), r["body"], curve.instant(r["ts"])
        assert t >= curve.due_instant(d, CCFG), (where, "written before due")
        assert d not in settled, (where, "a row after its date was settled")
        if seen and d != seen[-1]:
            assert seen[-1] in settled, (where, "moved on from an unsettled date")
            assert d == CCAL.next_open(seen[-1]), (where, "a business day was skipped")
        if not seen or d != seen[-1]:
            seen.append(d)
        hit = curve.holdout_hit(d.isoformat(), windows)
        status = b.get("status", "gap")
        if hit:
            assert status == "holdout_blocked" and "input" not in b, where
            settled[d] = r
            continue
        if r["kind"] == "GAP":
            if b["cause"] == "late_window":
                assert t > curve.late_limit(d, CCAL, CCFG), where
            else:
                assert b["cause"] == "not_published", where
                assert not world.has(d, t) and world.later_published(d, t), (
                    where,
                    "a gap the source did publish",
                )
            settled[d] = r
        elif status == "ok":
            assert world.has(d, t) and d not in world.bad, (
                where,
                "an ok fit of a day not published",
            )
            assert t <= curve.late_limit(d, CCAL, CCFG), (
                where,
                "a fit written after its late window",
            )
            assert b["input"]["row_date"] == d.isoformat(), where
            settled[d] = r
        elif status == "fit_failed":
            assert world.has(d, t) and d in world.bad and b["error"]["code"] == "E_DOMAIN", where
            settled[d] = r
        else:
            assert status in ("stale_input", "fetch_failed"), where
            assert t <= curve.late_limit(d, CCAL, CCFG), where
            if status == "stale_input":
                assert not world.has(d, t) and not world.later_published(d, t), (
                    where,
                    "stale but published",
                )
    assert all(d in settled for d in seen[:-1]), where
    if now is None:
        return
    # This run left nothing undone that it could do: every day due at `now` is settled, or the first unsettled
    # one has a row written by this run that says why it stopped there.
    target = curve.latest_due(now, CCAL, CCFG)
    todo = [d for d in [first, *CCAL.open_between(first, target)] if d not in settled]
    if todo:
        last = dated[-1]
        assert curve.day(last["body"]["date"]) == todo[0] and last["ts"] == curve.stamp(now), (
            where,
            "silent stop",
        )
        assert last["body"]["status"] in ("stale_input", "fetch_failed"), where
        if mode == "ok":
            assert last["body"]["status"] == "stale_input", (
                where,
                "a good file left a publishable day undone",
            )


def test_the_property_test_sees_the_ka_c9_fault(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan 14.10 rule 1: the property test is shown failing on the fault it was written for. The writer of
    the audited commit went on to later dates after an unsettled one; restoring that one behaviour here (a run
    that does not stop at a stale date) must make the sequences fail."""
    real = curve.run

    def audited(cfg: Any, runner: Any, text: str, now: Any, fetch: Any, *a: Any) -> Any:
        out, new, notes = real(cfg, runner, text, now, fetch, *a)
        dated = [r for r in new if r["kind"] == "DAY"]
        if dated and dated[-1]["body"]["status"] == "stale_input":
            nxt = CCAL.next_open(curve.day(dated[-1]["body"]["date"]))
            if (
                curve.due_instant(nxt, cfg) <= now
            ):  # the old writer wrote a row for the next date as well
                body = {**dated[-1]["body"], "date": nxt.isoformat()}
                rows = curve.parse(out)
                extra = curve.make_row(
                    len(rows), curve.stamp(now), "DAY", cfg, body, rows[-1]["hash"]
                )
                out, new = out + curve.line(extra) + "\n", [*new, extra]
        return out, new, notes

    monkeypatch.setattr(curve, "run", audited)
    failures = 0
    for seed in range(300):
        try:
            curve_sequence(seed)
        except AssertionError:
            failures += 1
    assert failures > 0


# ------------------------------------------------------------------ the paper writer

PCFG: dict[str, Any] = paper.load_config()
PFIELDS = [k["field"] for k in PCFG["knots"]]
MEMO: dict[str, Any] = {}


def paper_runner(bad_date: str | None = None) -> Any:
    """The CLI contract in process, with results remembered by case content. `bad_date` plants a day whose row
    cannot be built: every bond price for that settlement date fails."""
    cal = _calendar()

    def go(cases: list[dict[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for c in cases:
            op, i = c["operation"], c["inputs"]
            if op == "core.calendar.is_business_day":
                out[c["case_id"]] = {"is_business_day": cal[dt.date.fromisoformat(i["date"])]}
                continue
            if (
                bad_date is not None
                and op == "bond.price.from_yield"
                and i["settlement"] == bad_date
            ):
                raise paper.PaperError(f"CLI case {c['case_id']} failed: planted")
            key = json.dumps([op, i], sort_keys=True)
            if key not in MEMO:
                r = json.loads(json.dumps(run_case(json.dumps(c))))
                assert r["status"] == "ok", r
                MEMO[key] = r["outputs"]
            out[c["case_id"]] = copy.deepcopy(MEMO[key])
        return out

    return go


PCAL = paper.Calendar(paper_runner(), PCFG["calendar"])


def paper_yields(d: dt.date) -> dict[str, float]:
    """Invented from the date alone: a level per field plus 0 to 39 bp."""
    base = {"3 Mo": 430, "2 Yr": 480, "5 Yr": 490, "10 Yr": 510, "30 Yr": 540}
    h = hashlib.sha256(d.isoformat().encode()).digest()
    return {f: (base[f] + h[n] % 40) / 100 for n, f in enumerate(PFIELDS)}


class PaperWorld:
    """When the recorder wrote each business day's curve: usually a few hours after the day, sometimes after
    the day's cut-off, sometimes never."""

    def __init__(self, rng: random.Random, days: list[dt.date]):
        self.days = days
        self.recorded: dict[dt.date, dt.datetime | None] = {}
        for d in days:
            x = rng.random()
            base = dt.datetime.combine(d, dt.time(23, 30), UTC)
            if x < 0.07:
                self.recorded[d] = None
            elif x < 0.25:
                self.recorded[d] = base + dt.timedelta(hours=rng.choice([9, 22, 30, 50, 100, 200]))
            else:
                self.recorded[d] = base + dt.timedelta(
                    minutes=rng.randrange(200, 345)
                )  # measured 3.4 to 5.7 h
        head, rows = fl.ZERO, []
        order = sorted((t, d) for d, t in self.recorded.items() if t is not None)
        for n, (t, d) in enumerate(order, 1):
            ts = paper.stamp(t)
            rec = {
                "event_time": ts,
                "knowledge_time": ts,
                "sequence": n,
                "series_id": PCFG["source_series"],
                "value": {
                    "payload": {
                        "kind": "recording",
                        "observations": {
                            f"{d.isoformat()}|{f}": v for f, v in paper_yields(d).items()
                        },
                    }
                },
            }
            head = fl.link(head, rec)
            rows.append({"record": rec, "hash": head})
        self.log = rows

    def seen(self, now: dt.datetime) -> list[dict[str, Any]]:
        s = paper.stamp(now)
        return [e for e in self.log if e["record"]["knowledge_time"] <= s]

    def has(self, d: dt.date, now: dt.datetime) -> bool:
        t = self.recorded.get(d)
        return t is not None and t <= now


def paper_sequence(seed: int) -> None:
    rng = random.Random(seed)
    days = business_days()
    start = rng.randrange(20, 130)
    span = days[start : start + 45]
    world = PaperWorld(rng, span)
    windows: dict[str, tuple[str, str]] = {}
    if rng.random() < 0.15:
        w = span[rng.randrange(2, 10)]
        windows = {
            "T-PLANTED": (w.isoformat(), (w + dt.timedelta(days=rng.choice([0, 1, 4]))).isoformat())
        }
    bad = span[rng.randrange(2, 10)].isoformat() if rng.random() < 0.15 else None
    runner = paper_runner(bad)
    now = dt.datetime.combine(span[1], dt.time(rng.choice([0, 4, 15, 23]), rng.randrange(60)), UTC)
    text = ""
    for step in range(rng.randrange(4, 9)):
        back = bool(text) and rng.random() < 0.04
        when = now - dt.timedelta(hours=rng.choice([1, 30])) if back else now
        where = (seed, step)
        when_ok: dt.datetime | None = when
        try:
            out, new, notes = paper.run(
                PCFG, runner, text, world.seen(when), when, "c", "python", windows
            )
        except paper.PaperError as e:
            assert back and "clock" in str(e), (where, str(e))
            out, new, notes = text, [], []
            when_ok = None
        assert out.startswith(text), (where, "append-only")
        if out:
            v = paper.verify(out, PCFG, None, windows, PCAL)
            assert v["ok"], (where, v)
            paper_invariants(where, out, when_ok, notes, world, windows, bad)
        else:
            assert new == [], where
        text = out
        now += dt.timedelta(
            minutes=rng.choice(
                [0, 0, 5, 40, 180, 400, 540, 900, 1440, 1500, 2900, 4400, 10000, 21000]
            )
        )
    if (
        text and seed % 100 == 0
    ):  # the full check as well, with the rebuild through the CLI, on a sample
        v = paper.verify(text, PCFG, paper_runner(), windows, PCAL)
        assert v["ok"], (seed, v)


def paper_invariants(
    where: tuple[int, int],
    text: str,
    now: dt.datetime | None,
    notes: list[str],
    world: PaperWorld,
    windows: dict[str, tuple[str, str]],
    bad: str | None,
) -> None:
    rows = paper.parse(text)
    assert rows[0]["kind"] == "GENESIS" and len(rows) > 1, where
    g = paper.instant(rows[0]["ts"])
    first = paper.day(rows[1]["body"]["date"])
    # the start: a day whose curve was recorded and still on time when the ledger was started; never earlier
    assert rows[1]["kind"] == "DAY" and rows[1]["ts"] == rows[0]["ts"], where
    assert world.has(first, g) and g < PCAL.cutoff(first, PCFG), (where, "back-filled start")
    prev: dt.date | None = None
    for r in rows[1:]:
        d, b, t = paper.day(r["body"]["date"]), r["body"], paper.instant(r["ts"])
        if prev is not None:
            assert d == PCAL.next_open(prev), (where, "a business day was skipped or repeated")
        prev = d
        cut = PCAL.cutoff(d, PCFG)
        hit = paper.holdout_hit(d.isoformat(), windows)
        if r["kind"] == "GAP":
            if b["cause"] == "holdout":
                assert hit and b["studies"] == hit, where
            elif b["cause"] == "no_curve":
                assert not hit and t >= cut and not world.has(d, t), (
                    where,
                    "a gap for a recorded day",
                )
            else:
                assert b["cause"] == "build_refused" and d.isoformat() == bad and t >= cut, where
            continue
        assert not hit and d.isoformat() != bad, where
        assert world.has(d, t), (where, "a day row before its curve was recorded")
        assert b["timing"] == ("on_time" if t < cut else "late"), where
        assert b["par_yields"] == {f: paper.fstr(v) for f, v in paper_yields(d).items()}, where
        if b["timing"] == "late":
            assert b["orders"] == [], (where, "an order on a late day")
    if now is None or rows[0]["ts"] == paper.stamp(now):
        return  # the clock went backwards, or this run started the ledger (one day only; the next run goes on)
    # This run left nothing undone: the first business day without a row is not yet recorded and still before
    # its cut-off, or it is the planted day that cannot be built and still before its cut-off (and the run said so).
    assert prev is not None
    nxt = PCAL.next_open(prev)
    if nxt <= now.date():
        early = now < PCAL.cutoff(nxt, PCFG)
        if (
            nxt.isoformat() == bad
            and world.has(nxt, now)
            and not paper.holdout_hit(nxt.isoformat(), windows)
        ):
            assert early and any(n.startswith("PROBLEM:") for n in notes), (
                where,
                "silent stop at a bad day",
            )
        else:
            assert early and not world.has(nxt, now), (where, "silent stop")
            assert not paper.holdout_hit(nxt.isoformat(), windows), where


# ------------------------------------------------------------------ 10,000 sequences each, over the cores


def _block(job: tuple[str, int, int]) -> list[str]:
    kind, lo, hi = job
    fn = curve_sequence if kind == "curve" else paper_sequence
    out: list[str] = []
    for seed in range(lo, hi):
        try:
            fn(seed)
        except AssertionError as e:
            out.append(f"{kind} sequence {seed}: {e}")
            if len(out) >= 3:
                break
    return out


def run_sequences(kind: str) -> tuple[int, list[str]]:
    """All SEQUENCES seeds of one writer, in blocks over the machine's cores (serially if no pool can start).
    Returns (sequences run, failures)."""
    size = 250
    jobs = [(kind, lo, min(lo + size, SEQUENCES)) for lo in range(0, SEQUENCES, size)]
    try:
        with ProcessPoolExecutor(max_workers=min(os.cpu_count() or 1, 8)) as pool:
            results = list(pool.map(_block, jobs))
    except OSError, BrokenProcessPool:
        results = [_block(j) for j in jobs]
    return sum(hi - lo for _, lo, hi in jobs), [f for r in results for f in r]


def test_curve_writer_ten_thousand_sequences() -> None:
    ran, failures = run_sequences("curve")
    assert ran == SEQUENCES == 10_000 and not failures, failures[:3]


def test_paper_writer_ten_thousand_sequences() -> None:
    ran, failures = run_sequences("paper")
    assert ran == SEQUENCES == 10_000 and not failures, failures[:3]


def test_the_paper_property_test_sees_a_writer_that_skips_a_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plan 14.10 rule 1 for the paper sequences: a writer that drops the gap row of an unrecorded day (it goes
    straight on to the next recorded day) must make the sequences fail."""
    real = paper.make_row

    def skipping(
        seq: int, ts: str, kind: str, label: str, body: dict[str, Any], prev: str
    ) -> dict[str, Any]:
        if kind == "GAP" and body.get("cause") == "no_curve":
            body = {**body, "date": PCAL.next_open(paper.day(body["date"])).isoformat()}
        out: dict[str, Any] = real(seq, ts, kind, label, body, prev)
        return out

    monkeypatch.setattr(paper, "make_row", skipping)
    failures = 0
    for seed in range(40):
        try:
            paper_sequence(seed)
        except AssertionError, paper.PaperError:
            failures += 1
    assert failures > 0
