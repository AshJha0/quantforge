"""Daily curve run (specifications/12-platform/daily-curve-run.md, rulings KR-90 onwards; plan item K-11).

An offline 30-business-day run on synthetic par yields through the CLI operations, and a planted fault for every
check (plan 14.10 rule 1: a gate counts as built only when a run shows it failing on a planted fault).

The yields are invented from a hash of the date; no market data is in this file. Every date is after the prereg
holdout windows; the tests that need a date inside a window inject their own window at run time."""

import copy
import datetime as dt
import hashlib
import importlib.util
import json
import math
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import daily_jobs_support as support
import pytest

from quantforge_core.cli.main import run_case

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


TOOLS = ROOT / "tools" / "curve_daily"
sys.path.insert(0, str(TOOLS))
core = _load("curve_core", TOOLS / "curve_core.py")
run_day = _load("run_day", TOOLS / "run_day.py")
verify_chain = _load("verify_chain", TOOLS / "verify_chain.py")
site_page = _load("curve_daily_site_page", TOOLS / "site_page.py")
CFG: dict[str, Any] = core.load_config()
FIELDS = [t["field"] for t in CFG["tenors"]]
START = dt.date(2027, 1, 4)
NO_WINDOWS: dict[str, tuple[str, str]] = {}
Fetch = Callable[[str], bytes]


def runner(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The CLI contract in process: one case document in, one result out."""
    return {c["case_id"]: json.loads(json.dumps(run_case(json.dumps(c)))) for c in cases}


CAL = core.Calendar(runner, CFG["calendar"])


def business_days(n: int, start: dt.date = START) -> list[dt.date]:
    days = [start] if CAL.is_open(start) else []
    while len(days) < n:
        days.append(CAL.next_open(days[-1] if days else start))
    return days


def _u(d: dt.date, salt: str) -> float:
    """A number in [-1, 1) from a hash of the date: invented, repeatable."""
    h = hashlib.sha256(f"{d.isoformat()}|{salt}".encode()).digest()
    return int.from_bytes(h[:4], "big") / 2**31 - 1


def _ns(params: tuple[float, float, float, float], years: float) -> float:
    b0, b1, b2, tau = params
    x = years / tau
    e = -math.expm1(-x) / x
    return b0 + b1 * e + b2 * (e - math.exp(-x))


def params(d: dt.date) -> tuple[float, float, float, float]:
    return (
        4.3 + 0.2 * _u(d, "b0"),
        -0.7 + 0.2 * _u(d, "b1"),
        0.8 + 0.4 * _u(d, "b2"),
        2.0 + 0.5 * _u(d, "tau"),
    )


def treasury_csv(
    days: list[dt.date],
    blank: dict[dt.date, str] | None = None,
    override: dict[dt.date, str] | None = None,
) -> bytes:
    """Newest first, MM/DD/YYYY, two decimals, as the Treasury file is laid out. Synthetic values."""
    rows = ["Date," + ",".join(FIELDS)]
    for d in sorted(days, reverse=True):
        vals = []
        for t in CFG["tenors"]:
            v = f"{_ns(params(d), int(t['months']) / 12):.2f}"
            if blank and blank.get(d) == t["field"]:
                v = ""
            if override and d in override:
                v = override[d]
            vals.append(v)
        rows.append(f"{d.month:02d}/{d.day:02d}/{d.year}," + ",".join(vals))
    return ("\n".join(rows) + "\n").encode()


def gsw_csv(days: list[dt.date], shift_bp: float = 0.0) -> bytes:
    """Notes, then a `Date,` header, then SVENY01..SVENY30 in percent, four decimals. Synthetic values."""
    head = [
        "Synthetic stand-in for feds200628.csv (test data only)",
        "",
        "Date," + ",".join(f"SVENY{n:02d}" for n in range(1, 31)),
    ]
    body = [
        d.isoformat()
        + ","
        + ",".join(f"{_ns(params(d), n) + shift_bp / 100:.4f}" for n in range(1, 31))
        for d in days
    ]
    return ("\n".join(head + body) + "\n").encode()


def fetcher(treasury: bytes | None, gsw: bytes | None) -> Fetch:
    def go(url: str) -> bytes:
        data = gsw if url == CFG["gsw"]["url"] else treasury
        if data is None:
            raise OSError("planted fetch failure")
        return data

    return go


def evening(d: dt.date) -> dt.datetime:
    return dt.datetime.combine(d, dt.time(23, 45), dt.UTC)


def step(
    text: str, now: dt.datetime, fetch: Fetch, windows: dict[str, tuple[str, str]] | None = None
) -> tuple[str, list[dict[str, Any]], list[str]]:
    out: tuple[str, list[dict[str, Any]], list[str]] = core.run(
        CFG,
        runner,
        text,
        now,
        fetch,
        "test",
        "1.16.0",
        "python",
        NO_WINDOWS if windows is None else windows,
    )
    return out


def check(text: str, windows: dict[str, tuple[str, str]] | None = None) -> dict[str, Any]:
    v: dict[str, Any] = core.verify(text, CFG, runner, NO_WINDOWS if windows is None else windows)
    return v


def rechain(rows: list[dict[str, Any]]) -> str:
    """Rebuild seq, prev and hash so only the planted rule fault remains (a forger with no anchor)."""
    prev = core.GENESIS
    out = []
    moved: dict[str, str] = {}
    for i, r in enumerate(rows):
        old = r.get("hash", "")
        r = {k: v for k, v in r.items() if k != "hash"}
        r["seq"], r["prev"] = i, prev
        if (
            r["kind"] == "CONSISTENCY"
        ):  # a forger also re-points each consistency row at the new hash
            r["body"] = {
                **r["body"],
                "day_row": moved.get(r["body"]["day_row"], r["body"]["day_row"]),
            }
        r["hash"] = core.row_hash(r)
        moved[old] = r["hash"]
        prev = r["hash"]
        out.append(core.line(r))
    return "".join(x + "\n" for x in out)


def rows_of(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = core.parse(text)
    return out


@pytest.fixture(scope="module")
def month() -> tuple[str, list[dt.date]]:
    """30 business days, one evening run each; the Fed file runs five business days behind."""
    days = business_days(30)
    text = ""
    for i, d in enumerate(days):
        text, new, _ = step(
            text, evening(d), fetcher(treasury_csv(days[: i + 1]), gsw_csv(days[: max(0, i - 4)]))
        )
        assert new, d
    return text, days


# ------------------------------------------------------------------ the 30-day run


def test_thirty_business_days_offline(month: tuple[str, list[dt.date]]) -> None:
    text, days = month
    v = check(text)
    assert v["ok"], v
    assert v["calendar_checked"]
    rows = rows_of(text)
    day_rows = [r for r in rows if r["kind"] == "DAY"]
    assert [r["body"]["date"] for r in day_rows] == [d.isoformat() for d in days]
    assert all(r["body"]["status"] == "ok" and r["body"]["timing"] == "on_time" for r in day_rows)
    cons = [r for r in rows if r["kind"] == "CONSISTENCY"]
    assert len(cons) == 25  # the last five wait for the Fed
    assert all(c["body"]["status"] in ("within", "outside") for c in cons)
    assert all(c["body"]["label"] == "consistency check, not proof" for c in cons)
    for r in day_rows:
        fit = r["body"]["fit"]
        assert fit["taus_ok"] == "40" and len(fit["zeros_pct"]) == 30
        assert float(fit["rmse_bp"]) < 10  # synthetic NS inputs rounded to 0.01%: a few bp at most
        assert r["body"]["run"]["contract_version"] == "1.16.0"
    assert v["counts"]["ok"] == 30 and v["counts"]["gap"] == 0


def test_rerun_same_evening_adds_nothing(month: tuple[str, list[dt.date]]) -> None:
    text, days = month
    out, new, _ = step(
        text,
        evening(days[-1]) + dt.timedelta(minutes=5),
        fetcher(treasury_csv(days), gsw_csv(days[:-5])),
    )
    assert new == [] and out == text


def test_consistency_fills_in_when_the_fed_posts(month: tuple[str, list[dt.date]]) -> None:
    text, days = month
    nxt = CAL.next_open(days[-1])
    out, new, _ = step(text, evening(nxt), fetcher(treasury_csv([*days, nxt]), gsw_csv(days)))
    kinds = [r["kind"] for r in new]
    assert kinds == [
        "DAY",
        "CONSISTENCY",
        "CONSISTENCY",
        "CONSISTENCY",
        "CONSISTENCY",
        "CONSISTENCY",
    ]
    assert check(out)["ok"]


def test_fit_is_deterministic_and_rebuilds(
    month: tuple[str, list[dt.date]], tmp_path: Path
) -> None:
    text, days = month
    ledger = tmp_path / "curves.jsonl"
    ledger.write_bytes(text.encode("ascii"))
    f = tmp_path / "t.csv"
    f.write_bytes(treasury_csv(days))
    res = verify_chain.rebuild(str(ledger), days[-1].isoformat(), str(f), runner, CFG)
    assert res["ok"], res
    f.write_bytes(treasury_csv(days[:-1]))
    assert (
        verify_chain.rebuild(str(ledger), days[-1].isoformat(), str(f), runner, CFG)["reason"]
        == "INPUT_HASH"
    )


def test_consistency_tolerance_flags_a_shifted_fed_curve() -> None:
    days = business_days(2)
    text, _, _ = step(
        "", evening(days[0]), fetcher(treasury_csv(days[:1]), gsw_csv(days[:1], shift_bp=60))
    )
    cons = [r for r in rows_of(text) if r["kind"] == "CONSISTENCY"]
    assert cons[0]["body"]["status"] == "outside"
    assert check(text)["ok"]


# ------------------------------------------------------------------ planted faults: chain


def test_tampered_row_fails(month: tuple[str, list[dt.date]]) -> None:
    text, _ = month
    rows = rows_of(text)
    rows[5]["body"]["fit"]["tau"] = "9"
    lines = [core.line(r) for r in rows]
    assert check("\n".join(lines) + "\n")["reason"] == "HASH"
    rows[5]["hash"] = core.row_hash(
        rows[5]
    )  # recomputed, but the next row still links to the old hash
    lines = [core.line(r) for r in rows]
    v = check("\n".join(lines) + "\n")
    assert (v["reason"], v["first_bad_seq"]) == ("LINK", 6)


def test_anchor_catches_a_rewritten_chain(month: tuple[str, list[dt.date]], tmp_path: Path) -> None:
    text, _ = month
    ledger = tmp_path / "curves.jsonl"
    ledger.write_bytes(text.encode("ascii"))
    res = verify_chain.anchor(str(ledger), str(tmp_path / "anchors"), cfg=CFG)
    assert res["ok"]
    assert verify_chain.verify(str(ledger), str(tmp_path / "anchors"), runner, CFG, NO_WINDOWS)[
        "ok"
    ]
    rows = rows_of(text)
    rows[3]["body"]["fit"]["tau"] = "9"
    ledger.write_bytes(
        rechain(rows).encode("ascii")
    )  # every hash recomputed: the chain alone passes
    assert core.verify(core.read_ledger(ledger), CFG, None, NO_WINDOWS)["ok"]
    assert (
        verify_chain.verify(str(ledger), str(tmp_path / "anchors"), runner, CFG, NO_WINDOWS)[
            "reason"
        ]
        == "ANCHOR"
    )


def test_config_change_fails(month: tuple[str, list[dt.date]]) -> None:
    text, _ = month
    cfg = copy.deepcopy(CFG)
    cfg["consistency_tolerance_bp"]["rmse"] = "50"
    assert core.verify(text, cfg, runner, NO_WINDOWS)["reason"] == "CONFIG"


# ------------------------------------------------------------------ planted faults: days


def test_missing_day_fails(month: tuple[str, list[dt.date]]) -> None:
    text, days = month
    gone = days[10].isoformat()
    rows = [r for r in rows_of(text) if r["body"].get("date") != gone]
    v = check(rechain(rows))
    assert v["reason"] == "MISSING" and gone in v["detail"]


def test_second_settled_row_for_a_day_fails(month: tuple[str, list[dt.date]]) -> None:
    text, _ = month
    rows = rows_of(text)
    last = [r for r in rows if r["kind"] == "DAY"][-1]
    assert check(rechain([*rows, {**copy.deepcopy(last), "ts": rows[-1]["ts"]}]))["reason"] == "DUP"
    first = copy.deepcopy(next(r for r in rows if r["kind"] == "DAY"))
    assert check(rechain([*rows, {**first, "ts": rows[-1]["ts"]}]))["reason"] == "ORDER"
    assert (
        check(rechain([*rows, first]))["reason"] == "TS"
    )  # with its own, older time: refused sooner


def test_missed_days_are_late_then_gaps() -> None:
    days = business_days(12)
    text, _, _ = step("", evening(days[0]), fetcher(treasury_csv(days[:1]), None))
    # no run for days[1]..days[10]; a run on days[11] fits the last five (late) and gaps the older ones
    out, new, _ = step(text, evening(days[11]), fetcher(treasury_csv(days), None))
    v = check(out)
    assert v["ok"], v
    kinds = {
        r["body"]["date"]: (r["kind"], r["body"].get("timing"))
        for r in new
        if r["kind"] in ("DAY", "GAP")
    }
    assert kinds[days[11].isoformat()] == ("DAY", "on_time")
    assert kinds[days[10].isoformat()] == ("DAY", "late")
    assert kinds[days[1].isoformat()] == ("GAP", None)
    assert v["counts"]["gap"] >= 1 and v["counts"]["late"] >= 1


def test_wrong_timing_label_fails() -> None:
    days = business_days(3)
    text, _, _ = step("", evening(days[0]), fetcher(treasury_csv(days[:1]), None))
    out, _, _ = step(text, evening(days[2]), fetcher(treasury_csv(days), None))
    rows = rows_of(out)
    late = next(r for r in rows if r["body"].get("timing") == "late")
    late["body"]["timing"] = "on_time"
    assert check(rechain(rows))["reason"] == "TIMING"


def test_row_written_before_due_fails() -> None:
    days = business_days(1)
    text, _, _ = step("", evening(days[0]), fetcher(treasury_csv(days), None))
    rows = rows_of(text)
    rows[0]["ts"] = rows[1]["ts"] = f"{days[0].isoformat()}T15:00:00Z"
    assert check(rechain(rows))["reason"] == "EARLY"


# ------------------------------------------------------------------ planted faults: holdout windows


def test_holdout_date_is_blocked_and_checked() -> None:
    days = business_days(2)
    window = {"T-01": (days[1].isoformat(), days[1].isoformat())}
    text, _, _ = step("", evening(days[0]), fetcher(treasury_csv(days[:1]), None), window)
    out, new, _ = step(text, evening(days[1]), fetcher(treasury_csv(days), None), window)
    assert new[0]["body"]["status"] == "holdout_blocked" and "input" not in new[0]["body"]
    assert check(out, window)["ok"]
    # an ok fit dated inside a window fails, whatever else is right
    good, _, _ = step(text, evening(days[1]), fetcher(treasury_csv(days), None))
    v = check(good, window)
    assert v["reason"] == "HOLDOUT" and "T-01" in v["detail"]


def test_holdout_windows_come_from_the_preregs() -> None:
    w = core.holdout_windows()
    assert w and all(lo <= hi for lo, hi in w.values())
    inside = min(lo for lo, _ in w.values())
    assert core.holdout_hit(inside, w)


# ------------------------------------------------------------------ planted faults: fits and inputs


def test_failed_fit_is_recorded_with_its_code() -> None:
    days = business_days(2)
    text, new, _ = step(
        "", evening(days[0]), fetcher(treasury_csv(days[:1], blank={days[0]: "7 Yr"}), None)
    )
    assert new[1]["body"]["status"] == "fit_failed"
    assert new[1]["body"]["error"]["code"] == "E_MISSING_TENOR"
    out, new, _ = step(
        text, evening(days[1]), fetcher(treasury_csv(days, override={days[1]: "-250"}), None)
    )
    assert (
        new[0]["body"]["status"] == "fit_failed" and new[0]["body"]["error"]["code"] == "E_DOMAIN"
    )
    assert check(out)["ok"]  # failed days are settled rows, not gaps and not dropped
    rows = rows_of(out)
    del rows[-1]["body"]["error"]
    assert check(rechain(rows))["reason"] == "FAILCODE"


def test_stale_input_is_recorded_then_retried() -> None:
    days = business_days(2)
    text, _, _ = step("", evening(days[0]), fetcher(treasury_csv(days[:1]), None))
    stale, new, _ = step(text, evening(days[1]), fetcher(treasury_csv(days[:1]), None))
    assert new[0]["body"]["status"] == "stale_input"
    assert new[0]["body"]["input"]["latest_date"] == days[0].isoformat()
    assert check(stale)["ok"]
    morning = dt.datetime.combine(CAL.next_open(days[1]), dt.time(14, 15), dt.UTC)
    out, new, _ = step(stale, morning, fetcher(treasury_csv(days), None))
    assert (new[0]["body"]["status"], new[0]["body"]["timing"]) == ("ok", "on_time")
    assert check(out)["ok"]
    rows = rows_of(out)
    rows[-1]["body"]["input"]["row_date"] = days[
        0
    ].isoformat()  # yesterday's row presented as today's
    assert check(rechain(rows))["reason"] == "STALE"


def test_fetch_failure_is_recorded() -> None:
    days = business_days(1)
    text, new, _ = step("", evening(days[0]), fetcher(None, None))
    assert new[1]["body"]["status"] == "fetch_failed"
    assert check(text)["ok"]


def test_doctored_diagnostics_fail(month: tuple[str, list[dt.date]]) -> None:
    text, _ = month
    rows = rows_of(text)
    r = next(r for r in rows if r["kind"] == "DAY")
    r["body"]["fit"]["rmse_bp"] = "0.1"
    assert check(rechain(rows))["reason"] == "DIAG"
    rows = rows_of(text)
    c = next(r for r in rows if r["kind"] == "CONSISTENCY")
    c["body"]["status"] = "outside" if c["body"]["status"] == "within" else "within"
    assert check(rechain(rows))["reason"] == "VERDICT"
    rows = rows_of(text)
    c = next(r for r in rows if r["kind"] == "CONSISTENCY")
    c["body"]["label"] = "validated"
    assert check(rechain(rows))["reason"] == "LABEL"


def test_unpublished_fed_date_becomes_unavailable_after_the_wait() -> None:
    days = business_days(1)
    text, _, _ = step("", evening(days[0]), fetcher(treasury_csv(days), gsw_csv([])))
    assert not [r for r in rows_of(text) if r["kind"] == "CONSISTENCY"]
    later = evening(days[0]) + dt.timedelta(days=40)
    nxt = business_days(1, later.date())[0]
    out, new, _ = step(text, evening(nxt), fetcher(treasury_csv(days), gsw_csv([])))
    cons = [r for r in new if r["kind"] == "CONSISTENCY"]
    assert cons and cons[0]["body"]["status"] == "unavailable"
    assert check(out)["ok"]


def test_refuses_to_extend_a_broken_ledger(month: tuple[str, list[dt.date]]) -> None:
    text, days = month
    broken = text.replace('"tau":"', '"tau":"1', 1)
    with pytest.raises(core.CurveError):
        step(broken, evening(CAL.next_open(days[-1])), fetcher(treasury_csv(days), None))


# ------------------------------------------------------------------ scripts and site stub


def test_run_day_dry_run_and_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    days = business_days(1)
    t, g = tmp_path / "t.csv", tmp_path / "g.csv"
    t.write_bytes(treasury_csv(days))
    g.write_bytes(gsw_csv(days))
    monkeypatch.setattr(run_day, "cli_runner", lambda impl: runner)
    monkeypatch.setattr(run_day, "contract_version", lambda impl: "1.16.0")
    monkeypatch.setattr(core, "holdout_windows", lambda: NO_WINDOWS)
    ledger = tmp_path / "ledger" / "curves.jsonl"
    args = [
        "--ledger",
        str(ledger),
        "--treasury-file",
        str(t),
        "--gsw-file",
        str(g),
        "--now",
        f"{days[0].isoformat()}T23:45:00Z",
    ]
    assert run_day.main([*args, "--dry-run"]) == 0
    assert not ledger.exists()
    assert '"rows_added": 3' in capsys.readouterr().out
    summary = tmp_path / "summary.json"
    assert run_day.main([*args, "--summary", str(summary)]) == 0
    s = json.loads(summary.read_text(encoding="utf-8"))
    assert s["ok"] and s["latest"]["date"] == days[0].isoformat()
    page = site_page.render(s)
    assert "consistency check, not proof" in page and "on time" in page
    assert "No verified daily fit yet" in site_page.render(
        json.loads((TOOLS / "site" / "latest.json").read_text())
    )


def test_problem_rows_make_the_run_red() -> None:
    days = business_days(1)
    _, new, _ = step("", evening(days[0]), fetcher(None, None))
    assert run_day.problems(new) == 2
    _, new, _ = step("", evening(days[0]), fetcher(treasury_csv(days), None))
    assert run_day.problems(new) == 0


@pytest.mark.parametrize(("second", "timing"), [(59, "on_time"), (60, "late")])
def test_cutoff_boundary_second(second: int, timing: str) -> None:
    """KR-111 (aligned with paper KR-82): on time strictly before 19:30:00 UTC on the next business day."""
    days = business_days(2)
    when = dt.datetime.combine(days[1], dt.time(19, 29), dt.UTC) + dt.timedelta(seconds=second)
    out, new, _ = step("", when, fetcher(treasury_csv(days[:1]), None))
    day = next(r for r in new if r["kind"] == "DAY")
    assert day["body"]["date"] == days[0].isoformat() and day["body"]["timing"] == timing
    assert check(out)["ok"]


# ------------------------------------------------------------------ audit KA-C9, KA-C10, KA-C14 (KR-203 on)


def test_unsettled_date_followed_by_a_later_date_does_not_stop_the_chain() -> None:
    """Audit KA-C9 (2026-11-19), reproduced as a failing test in commit bb9bce54 before the fix. Day 1 fits;
    day 2 is not in the file on three consecutive runs; day 3 is. Every run after that must leave a ledger that
    verifies, and day 2 must end as a recorded gap."""
    days = business_days(12)
    without_day2 = [days[0], *days[2:]]
    text, _, _ = step("", evening(days[0]), fetcher(treasury_csv(days[:1]), None))
    text, _, _ = step(text, evening(days[1]), fetcher(treasury_csv(days[:1]), None))
    morning = dt.datetime.combine(days[2], dt.time(14, 15), dt.UTC)
    text, _, _ = step(text, morning, fetcher(treasury_csv(days[:1]), None))
    for i in range(2, 12):
        text, new, _ = step(text, evening(days[i]), fetcher(treasury_csv(without_day2[:i]), None))
        v = check(text)
        assert v["ok"] and new, (days[i], v)
    rows = rows_of(text)
    gaps = {r["body"]["date"]: r["body"]["cause"] for r in rows if r["kind"] == "GAP"}
    assert gaps == {days[1].isoformat(): "not_published"}
    ok = [r["body"]["date"] for r in rows if r["kind"] == "DAY" and r["body"]["status"] == "ok"]
    assert ok == [d.isoformat() for d in without_day2]


def test_a_date_the_source_never_publishes_is_closed_with_the_evidence() -> None:
    """KR-203: when the file holds a later date and not this one, the date is closed as a `not_published` gap
    that names the file; the later date is fitted in the same run, in order."""
    days = business_days(3)
    text, _, _ = step("", evening(days[0]), fetcher(treasury_csv(days[:1]), None))
    text, new, _ = step(text, evening(days[1]), fetcher(treasury_csv(days[:1]), None))
    assert [r["body"]["status"] for r in new] == ["stale_input"]
    later = fetcher(treasury_csv([days[0], days[2]]), None)
    # KR-255: the first run that sees the file past the date records it (stale_input, with that file) ...
    text, new, _ = step(text, evening(days[2]), later)
    assert [
        (r["kind"], r["body"].get("status"), r["body"]["input"]["latest_date"]) for r in new
    ] == [("DAY", "stale_input", days[2].isoformat())]
    assert check(text)["ok"]
    # ... and a later run that sees it again closes it
    out, new, _ = step(text, evening(days[2]) + dt.timedelta(minutes=30), later)
    assert [(r["kind"], r["body"]["date"]) for r in new] == [
        ("GAP", days[1].isoformat()),
        ("DAY", days[2].isoformat()),
    ]
    gap = new[0]["body"]
    assert gap["cause"] == "not_published" and gap["input"]["latest_date"] == days[2].isoformat()
    assert new[1]["body"]["status"] == "ok" and check(out)["ok"]
    # planted: the gap's evidence removed, or pointing at a file that had not moved past the date
    rows = rows_of(out)
    g = next(r for r in rows if r["kind"] == "GAP")
    g["body"]["input"]["latest_date"] = days[0].isoformat()
    assert check(rechain(rows))["reason"] == "GAPRULE"
    rows = rows_of(out)
    next(r for r in rows if r["kind"] == "GAP")["body"]["cause"] = "because"
    assert check(rechain(rows))["reason"] == "GAPRULE"
    rows = rows_of(out)
    next(r for r in rows if r["kind"] == "GAP")["body"]["cause"] = (
        "late_window"  # declared inside the window
    )
    assert check(rechain(rows))["reason"] == "GAPRULE"


def test_a_row_for_a_later_date_while_one_is_unsettled_fails() -> None:
    """KR-203 planted fault: the audited writer's own output (KA-C9). A stale row for day 2, then a row for
    day 3, is refused with ORDER, whatever the row for day 3 says."""
    days = business_days(3)
    text, _, _ = step("", evening(days[0]), fetcher(treasury_csv(days[:1]), None))
    text, _, _ = step(text, evening(days[1]), fetcher(treasury_csv(days[:1]), None))
    good, _, _ = step(text, evening(days[2]), fetcher(treasury_csv(days), None))
    rows = rows_of(good)
    assert [r["body"]["date"] for r in rows[1:]] == [
        days[0].isoformat(),
        *[days[1].isoformat()] * 2,
        days[2].isoformat(),
    ]
    del rows[3]  # the settling row of day 2: day 3 now follows an unsettled day 2
    v = check(rechain(rows))
    assert v["reason"] == "ORDER" and "unsettled" in v["detail"]


def test_a_download_that_is_not_the_file_is_retried_not_settled() -> None:
    """KA-C10, KR-204: an error page served as HTTP 200 is `fetch_failed` (retried); the next run with the real
    file fits the day. A bad cell in a present row stays a settled `fit_failed`."""
    days = business_days(2)
    page = b"<!DOCTYPE html>\n<html><body>maintenance</body></html>\n"
    text, new, _ = step("", evening(days[0]), fetcher(page, None))
    b = new[1]["body"]
    assert (
        b["status"] == "fetch_failed"
        and b["error"]["code"] == "E_NOT_THE_FILE"
        and "sha256" in b["input"]
    )
    assert check(text)["ok"] and run_day.problems(new) == 2
    morning = dt.datetime.combine(days[1], dt.time(4, 15), dt.UTC)
    out, new, _ = step(text, morning, fetcher(treasury_csv(days[:1]), None))
    assert [(r["body"]["status"], r["body"]["timing"]) for r in new] == [("ok", "on_time")]
    assert check(out)["ok"]
    for junk in (
        b"",
        b"\xff\xfe\x00",
        b"Date,1 Mo\nnot a date,4.1\n",
        b"Date,1 Mo\n02/30/2027,4.1\n",
    ):
        _, new, _ = step("", evening(days[0]), fetcher(junk, None))
        assert new[1]["body"]["status"] == "fetch_failed", junk
    # planted: a fetch_failed row given a fit, and a stale row whose file does hold the date
    rows = rows_of(text)
    rows[1]["body"]["fit"] = {}
    assert check(rechain(rows))["reason"] == "FAILCODE"
    stale, _, _ = step("", evening(days[1]), fetcher(treasury_csv(days[:1]), None))
    rows = rows_of(stale)
    rows[1]["body"]["input"]["latest_date"] = days[1].isoformat()
    assert check(rechain(rows))["reason"] == "STALE"


def test_a_clock_before_the_last_row_is_refused_and_harms_nothing() -> None:
    days = business_days(2)
    text, _, _ = step("", evening(days[0]), fetcher(treasury_csv(days[:1]), None))
    with pytest.raises(core.CurveError, match="clock"):
        step(
            text, evening(days[0]) - dt.timedelta(minutes=1), fetcher(treasury_csv(days[:1]), None)
        )
    out, new, _ = step(text, evening(days[1]), fetcher(treasury_csv(days), None))
    assert new and check(out)["ok"]
    rows = rows_of(out)
    rows[-1]["ts"] = (
        rows[0]["ts"][:11] + "00:00:00Z"
    )  # planted: a row timed before the row above it
    assert check(rechain(rows))["reason"] == "TS"


def test_the_start_cannot_be_back_dated_or_detached_from_genesis() -> None:
    """START: the first dated row is a DAY row of the run that wrote GENESIS, for the latest day due then."""
    days = business_days(3)
    text, _, _ = step("", evening(days[2]), fetcher(treasury_csv(days), None))
    rows = rows_of(text)
    assert rows[1]["body"]["date"] == days[2].isoformat()
    rows[1]["body"]["date"] = days[0].isoformat()  # an older day presented as the start
    rows[1]["body"]["input"]["row_date"] = days[0].isoformat()
    rows[1]["body"]["timing"] = "late"
    assert check(rechain(rows))["reason"] == "START"
    rows = rows_of(text)
    rows[1]["ts"] = core.stamp(evening(days[2]) + dt.timedelta(hours=1))
    assert check(rechain(rows))["reason"] == "START"


def test_a_non_finite_fit_is_a_recorded_failure_not_a_refusal() -> None:
    """A refusal would repeat on every later run for the same input; `E_NONFINITE` settles the day."""
    days = business_days(1)

    def broken(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        out = runner(cases)
        for r in out.values():
            if "betas" in r.get("outputs", {}):
                r["outputs"]["betas"][0] = math.inf
        return out

    text, new, _ = core.run(
        CFG,
        broken,
        "",
        evening(days[0]),
        fetcher(treasury_csv(days), None),
        "t",
        "1.16.0",
        "python",
        NO_WINDOWS,
    )
    assert (
        new[1]["body"]["status"] == "fit_failed"
        and new[1]["body"]["error"]["code"] == "E_NONFINITE"
    )
    assert check(text)["ok"]


def test_the_year_end_gap_is_found_in_the_next_years_file() -> None:
    """A business day at the end of a year that the source skips is closed from the next year's file."""
    year_end = [
        d
        for d in (dt.date(2027, 12, 20) + dt.timedelta(days=i) for i in range(12))
        if CAL.is_open(d)
    ]
    d0, d1 = year_end[-2], year_end[-1]
    d2 = CAL.next_open(d1)
    assert d1.year == 2027 and d2.year == 2028
    files = {2027: treasury_csv([d0]), 2028: treasury_csv([d2])}

    def by_year(url: str) -> bytes:
        if url == CFG["gsw"]["url"]:
            raise OSError("no Fed file in this test")
        return files[2027 if "/2027/" in url else 2028]

    text, _, _ = step("", evening(d0), by_year)
    text, new, _ = step(
        text,
        evening(d1),
        lambda u: (
            files[2027]
            if "/2027/" in u
            else b"Date," + b",".join(f.encode() for f in FIELDS) + b"\n"
        ),
    )
    assert [r["body"]["status"] for r in new] == ["stale_input"]
    text, new, _ = step(text, evening(d2), by_year)  # KR-255: first sighting of the 2028 file
    assert [(r["body"]["status"], r["body"]["input"]["latest_date"]) for r in new] == [
        ("stale_input", d2.isoformat())
    ]
    out, new, _ = step(text, evening(d2) + dt.timedelta(minutes=30), by_year)
    assert [(r["kind"], r["body"]["date"]) for r in new] == [
        ("GAP", d1.isoformat()),
        ("DAY", d2.isoformat()),
    ]
    assert (
        new[0]["body"]["input"]["latest_date"] == d2.isoformat()
        and "/2028/" in new[0]["body"]["input"]["url"]
    )
    assert check(out)["ok"]


def test_the_ledger_file_has_one_serialisation(month: tuple[str, list[dt.date]]) -> None:
    """KR-208: LF line ends, sorted keys, no spaces, a final line feed. Any other bytes fail, though the row
    hashes are unchanged."""
    text, _ = month
    assert check(text)["ok"]
    assert check(text.replace("\n", "\r\n"))["reason"] == "BYTES"
    assert check(text[:-1])["reason"] == "BYTES"
    lines = text.split("\n")
    lines[2] = json.dumps(json.loads(lines[2]))  # same row, default separators and key order
    assert check("\n".join(lines))["reason"] == "BYTES"
    assert check(text + "\n")["reason"] in ("BYTES", "PARSE")


def test_rebuild_allows_last_bit_noise_and_nothing_more(
    month: tuple[str, list[dt.date]], tmp_path: Path
) -> None:
    """KA-C14, KR-207: a refit on another platform may differ in the last bits; the rebuild compares numbers
    within 1e-6 relative to max(1, value) and everything else exactly."""
    text, days = month
    f = tmp_path / "t.csv"
    f.write_bytes(treasury_csv(days))
    date = days[-1].isoformat()

    def with_fit(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        rows = rows_of(text)
        change(
            next(r for r in rows if r["kind"] == "DAY" and r["body"]["date"] == date)["body"]["fit"]
        )
        ledger = tmp_path / "c.jsonl"
        ledger.write_bytes(rechain(rows).encode("ascii"))
        out: dict[str, Any] = verify_chain.rebuild(str(ledger), date, str(f), runner, CFG)
        return out

    same = with_fit(lambda fit: None)
    assert same["ok"] and same["exact"] is True

    def nudge(fit: dict[str, Any]) -> None:
        fit["betas"][0] = core.fstr(float(fit["betas"][0]) * (1 + 1e-12))

    near = with_fit(nudge)
    assert near["ok"] and near["exact"] is False

    def move(fit: dict[str, Any]) -> None:
        fit["betas"][0] = core.fstr(float(fit["betas"][0]) + 1e-4)

    assert with_fit(move)["reason"] == "REFIT_DIFFERS"

    def other_tau(fit: dict[str, Any]) -> None:
        fit["tau"] = "9.75" if fit["tau"] != "9.75" else "9.5"

    assert with_fit(other_tau) == {"ok": False, "reason": "REFIT_DIFFERS", "detail": ".tau"}


def test_a_run_that_adds_no_row_adds_no_anchor(
    month: tuple[str, list[dt.date]], tmp_path: Path
) -> None:
    """KR-205: `anchor --if-uncovered` writes nothing when the head already has an anchor, and writes one when
    it has not (a failed stamp is made good by the next run)."""
    text, _ = month
    ledger = tmp_path / "curves.jsonl"
    ledger.write_bytes(text.encode("ascii"))
    a = tmp_path / "anchors"
    first = verify_chain.anchor(
        str(ledger), str(a), cfg=CFG, if_uncovered=True, when="20270216T050000Z"
    )
    assert first["covered"] is False and first["anchor"] == "20270216T050000Z.json"
    again = verify_chain.anchor(
        str(ledger), str(a), cfg=CFG, if_uncovered=True, when="20270216T090000Z"
    )
    assert again["covered"] is True and again["anchor"] is None
    assert sorted(p.name for p in a.iterdir()) == ["20270216T050000Z.json"]
    clash = verify_chain.anchor(str(ledger), str(a), cfg=CFG, when="20270216T050000Z")
    assert clash["ok"] is False and "never overwritten" in clash["detail"]


def test_the_on_time_label_is_checked_against_bitcoin_block_times(
    month: tuple[str, list[dt.date]], tmp_path: Path
) -> None:
    """KR-201: with block headers, every row labelled on time is either proven (an anchor over it has a block
    time, plus the margin, before the cut-off) or listed as not proven. A back-dated chain stamped in one
    sitting proves nothing."""
    text, days = month
    ledger = tmp_path / "curves.jsonl"
    ledger.write_bytes(text.encode("ascii"))
    rows = rows_of(text)
    a = tmp_path / "anchors"
    headers: dict[str, str] = {}
    # an honest anchor a few minutes after each of the first three days' rows
    for n, d in enumerate(days[:3]):
        upto = "".join(core.line(r) + "\n" for r in rows if r["ts"] <= core.stamp(evening(d)))
        part = tmp_path / "part.jsonl"
        part.write_bytes(upto.encode("ascii"))
        name = evening(d).strftime("%Y%m%dT%H%M%SZ")
        assert verify_chain.anchor(str(part), str(a), cfg=CFG, when=name)["ok"]
        support.stamp(a / f"{name}.json", 900000 + n, int(evening(d).timestamp()) + 1200, headers)
    # and one anchor over everything, stamped long after: the remaining 27 days rest on it alone
    assert verify_chain.anchor(str(ledger), str(a), cfg=CFG, when="20270401T000000Z")["ok"]
    late = int(dt.datetime(2027, 4, 1, tzinfo=dt.UTC).timestamp())
    support.stamp(a / "20270401T000000Z.json", 905000, late, headers)
    v = verify_chain.verify(
        str(ledger), str(a), runner, CFG, NO_WINDOWS, headers, support.EASY_TARGET
    )
    assert v["ok"], v
    t = v["anchored_timing"]
    assert t["proven_on_time"] == 3 and len(t["labelled_on_time_without_proof"]) == 27
    assert days[3].isoformat() in t["labelled_on_time_without_proof"]
    # the production floor refuses the home-made headers outright
    v = verify_chain.verify(str(ledger), str(a), runner, CFG, NO_WINDOWS, headers)
    assert v["reason"] == "EVIDENCE" and "floor" in v["detail"]
    # a header that does not hold the proof's Merkle root is an error, not a miss
    headers["900000"] = headers["900001"]
    v = verify_chain.verify(
        str(ledger), str(a), runner, CFG, NO_WINDOWS, headers, support.EASY_TARGET
    )
    assert v["reason"] == "EVIDENCE" and "Merkle root" in v["detail"]


def test_a_next_year_file_without_a_later_date_is_no_evidence() -> None:
    """A year-end date is closed as `not_published` only by a file that really holds a later date. If the next
    year's URL serves older rows, the date stays `stale_input` (a gap with no later date would fail `GAPRULE`
    and be refused on every run)."""
    year_end = [
        d
        for d in (dt.date(2027, 12, 20) + dt.timedelta(days=i) for i in range(12))
        if CAL.is_open(d)
    ]
    d0, d1 = year_end[-2], year_end[-1]
    d2 = CAL.next_open(d1)
    old = treasury_csv([d0])
    text, _, _ = step("", evening(d0), fetcher(old, None))
    out, new, _ = step(text, evening(d2), fetcher(old, None))  # both years' URLs serve the old file
    assert [(r["kind"], r["body"]["date"], r["body"].get("status")) for r in new] == [
        ("DAY", d1.isoformat(), "stale_input")
    ]
    assert check(out)["ok"]


def test_first_run_with_the_date_missing_and_a_later_date_present_verifies() -> None:
    """KF-8 / KR-254: first run 10 minutes before the next day's due time, the file holding D+1 and not D. The
    writer used to write GENESIS then a not_published GAP, which its own verifier refused (START). The first
    dated row is now a DAY stale_input row naming that file, and the ledger verifies."""
    d = dt.date(2027, 12, 6)
    d1 = CAL.next_open(d)
    now = dt.datetime.combine(d1, dt.time(22, 50), dt.UTC)
    out, new, _ = step("", now, fetcher(treasury_csv([d1]), None))
    assert [(r["kind"], r["body"].get("status")) for r in new] == [
        ("GENESIS", None),
        ("DAY", "stale_input"),
    ]
    assert check(out)["ok"]


def test_a_not_published_gap_needs_an_earlier_run_that_saw_it() -> None:
    """KR-255 (KF-9): one download is not enough to close a date for good. A GAP not_published must follow a
    stale_input row of the same date, written by an earlier run, whose file already held a later date."""
    days = business_days(3)
    text, _, _ = step("", evening(days[0]), fetcher(treasury_csv(days[:1]), None))
    text, _, _ = step(text, evening(days[1]), fetcher(treasury_csv(days[:1]), None))
    later = fetcher(treasury_csv([days[0], days[2]]), None)
    text, _, _ = step(text, evening(days[2]), later)
    out, _, _ = step(text, evening(days[2]) + dt.timedelta(minutes=30), later)
    assert check(out)["ok"]
    rows = rows_of(out)
    # planted: the first sighting's file did not hold a later date
    sight = next(
        r
        for r in rows
        if r["kind"] == "DAY"
        and r["body"]["status"] == "stale_input"
        and r["body"]["input"]["latest_date"] > r["body"]["date"]
    )
    sight["body"]["input"]["latest_date"] = days[0].isoformat()
    assert check(rechain(rows))["reason"] == "GAPRULE"
    # planted: the gap written by the same run as the sighting
    rows = rows_of(out)
    gi = next(i for i, r in enumerate(rows) if r["kind"] == "GAP")
    for r in rows[gi:]:
        r["ts"] = rows[gi - 1]["ts"]
    assert check(rechain(rows))["reason"] == "GAPRULE"


def test_a_sub_second_clock_cannot_write_a_gap_the_verifier_refuses() -> None:
    """KF-14: the ledger stamps whole seconds. A sighting written at 23:45:00.200 and a rerun at 23:45:00.700
    are the same instant to the verifier, so the rerun must not close the date as a gap (the verifier would
    refuse it, GAPRULE); `core.run` compares at whole seconds."""
    days = business_days(3)
    text, _, _ = step("", evening(days[0]), fetcher(treasury_csv(days[:1]), None))
    text, _, _ = step(text, evening(days[1]), fetcher(treasury_csv(days[:1]), None))
    later = fetcher(treasury_csv([days[0], days[2]]), None)
    first = evening(days[2]).replace(microsecond=200_000)
    text, _, _ = step(text, first, later)
    out, new, _ = step(text, first.replace(microsecond=700_000), later)
    assert check(out)["ok"], check(out)
    assert not any(r["kind"] == "GAP" for r in new)
