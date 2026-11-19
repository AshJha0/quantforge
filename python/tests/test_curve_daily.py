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
    ledger.write_text(text, encoding="utf-8")
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
    ledger.write_text(text, encoding="utf-8")
    res = verify_chain.anchor(str(ledger), str(tmp_path / "anchors"), cfg=CFG)
    assert res["ok"]
    assert verify_chain.verify(str(ledger), str(tmp_path / "anchors"), runner, CFG, NO_WINDOWS)[
        "ok"
    ]
    rows = rows_of(text)
    rows[3]["body"]["fit"]["tau"] = "9"
    ledger.write_text(
        rechain(rows), encoding="utf-8"
    )  # every hash recomputed: the chain alone passes
    assert core.verify(ledger.read_text(encoding="utf-8"), CFG, None, NO_WINDOWS)["ok"]
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
    dup = copy.deepcopy(next(r for r in rows if r["kind"] == "DAY"))
    rows.append(dup)
    assert check(rechain(rows))["reason"] in ("ORDER", "DUP")


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
    rows[1]["ts"] = f"{days[0].isoformat()}T15:00:00Z"
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
