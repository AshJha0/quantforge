"""Daily paper ledger (specifications/12-platform/paper-ledger-daily.md, acceptance P1 to P10; plan 14.8 K-1,
K-2, 12.7 Q8k). A 30-business-day offline run on synthetic par yields through the CLI operations, and a planted
fault for every check (plan 14.10 rule 1: a gate counts as built only when a run shows it failing).

The yields are invented by a hash of the date; no market data is in this file. Dates are after every prereg
holdout window, and the one test that needs a date inside a window builds it at run time."""

import copy
import datetime as dt
import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable, Iterable
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from quantforge_core import paper
from quantforge_core.cli.main import run_case

ROOT = Path(__file__).resolve().parents[2]
Runner = Callable[[list[dict[str, Any]]], dict[str, Any]]


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


core = _load("paper_core", ROOT / "tools" / "paper_daily" / "paper_core.py")
fl = _load("forward_log_for_paper", ROOT / "tools" / "forward-log" / "forward_log.py")
verify_cli = _load("paper_daily_verify", ROOT / "tools" / "paper_daily" / "verify_ledger.py")
CFG: dict[str, Any] = core.load_config()
FIELDS = [k["field"] for k in CFG["knots"]]
BASE = {"3 Mo": 430, "2 Yr": 480, "5 Yr": 490, "10 Yr": 510, "30 Yr": 540}  # basis points, invented
START = dt.date(2027, 1, 4)
NO_WINDOWS: dict[str, tuple[str, str]] = {}


def runner(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """The CLI contract in process: one case document in, one result out."""
    out: dict[str, Any] = core.outputs(
        json.loads(json.dumps(run_case(json.dumps(c)))) for c in cases
    )
    return out


def business_days(n: int) -> list[dt.date]:
    cal = core.Calendar(runner, CFG["calendar"])
    days = [START] if cal.is_open(START) else []
    while len(days) < n:
        days.append(cal.next_open(days[-1]))
    return days


def synthetic_yields(days: Iterable[dt.date]) -> dict[str, dict[str, float]]:
    """A hash-driven walk of at most 7 bp a day per point: deterministic and plainly not market data."""
    level = dict(BASE)
    out = {}
    for d in days:
        for f in FIELDS:
            h = hashlib.sha256(f"{d.isoformat()}|{f}".encode()).digest()
            level[f] = max(50, level[f] + h[0] % 15 - 7)
        out[d.isoformat()] = {f: level[f] / 100 for f in FIELDS}
    return out


def forward_log(yields: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    """Rows in the recorder's own format and chain, one per day, as record.py writes them."""
    head, rows = fl.ZERO, []
    for n, (date, y) in enumerate(yields.items(), 1):
        t = f"{date}T22:10:00Z"
        rec = {
            "event_time": t,
            "knowledge_time": t,
            "sequence": n,
            "series_id": CFG["source_series"],
            "value": {
                "payload": {
                    "kind": "recording",
                    "observations": {f"{date}|{f}": v for f, v in y.items()},
                }
            },
        }
        head = fl.link(head, rec)
        rows.append({"record": rec, "hash": head})
    return rows


def evening(d: dt.date) -> dt.datetime:
    return dt.datetime.combine(d, dt.time(23, 45), dt.UTC)


def run_days(
    days: list[dt.date],
    log: list[dict[str, Any]],
    cfg: dict[str, Any] = CFG,
    run: Runner = runner,
    skip_runs: tuple[dt.date, ...] = (),
) -> str:
    text = ""
    for d in days:
        if d in skip_runs:
            continue
        seen = [e for e in log if e["record"]["knowledge_time"] <= core.stamp(evening(d))]
        text, _, _ = core.run(cfg, run, text, seen, evening(d), "testcommit", "python", NO_WINDOWS)
    return text


@pytest.fixture(scope="module")
def days30() -> list[dt.date]:
    return business_days(30)


@pytest.fixture(scope="module")
def ledger30(days30: list[dt.date]) -> str:
    return run_days(days30, forward_log(synthetic_yields(days30)))


def rows_of(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = core.parse(text)
    return out


def rechain(rows: list[dict[str, Any]]) -> str:
    """What someone who can push would do after an edit: renumber and recompute every hash."""
    prev = core.GENESIS
    out = []
    for n, r in enumerate(rows):
        r = {**r, "seq": n, "prev": prev}
        r["hash"] = core.row_hash(r)
        prev = r["hash"]
        out.append(core.line(r))
    return "".join(x + "\n" for x in out)


def check(text: str, cfg: dict[str, Any] = CFG, cli: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = core.verify(text, cfg, runner if cli else None, NO_WINDOWS)
    return out


# ---------------------------------------------------------------- the 30-day run (P1 to P6)


def test_thirty_business_days_verify_and_replay(ledger30: str, days30: list[dt.date]) -> None:
    v = check(ledger30)
    assert v["ok"], v
    assert v["recorded_trading_days"] == 30 and v["late_days"] == 0 and v["gaps"] == 0
    assert v["records"] == 31 and v["recomputed"] and v["calendar_checked"]
    rows = rows_of(ledger30)
    assert [r["body"]["date"] for r in rows[1:]] == [d.isoformat() for d in days30]
    assert dt.date(2027, 1, 18) not in days30  # a federal holiday inside the span: no row
    assert all(r["label"] == "paper marks on a fitted curve; not tradable" for r in rows)
    assert all(r["format"] == "qf-paper-ledger/1" for r in rows)
    # the ledger alone, with no CLI and no calendar, replays every day as well
    assert check(ledger30, cli=False)["ok"]


def test_every_day_explains_and_reconciles(ledger30: str) -> None:
    moved = 0
    for r in rows_of(ledger30)[1:]:
        b, e = r["body"], r["body"]["explain"]
        terms = sum(Decimal(e[k]) for k in ("carry", "roll_down", "curve_move", "fills_costs"))
        assert Decimal(b["pnl"]) == terms and e["unexplained"] == "0", b["date"]
        assert Decimal(b["nav_close"]) - Decimal(b["nav_open"]) == Decimal(b["pnl"])
        held = sum(Decimal(x) for x in b["positions_close"].values())
        assert Decimal(b["cash_close"]) + 100 * held == Decimal(b["nav_close"]), b["date"]
        moved += e["curve_move"] != "0" and e["roll_down"] != "0" and e["carry"] != "0"
    assert moved >= 25  # the terms are live numbers, not zeros that sum trivially


def test_every_order_carries_tca_and_fills_come_from_the_simulator(ledger30: str) -> None:
    orders = [o for r in rows_of(ledger30)[1:] for o in r["body"]["orders"]]
    assert len(orders) >= 25 and {o["side"] for o in orders} == {"BUY", "SELL"}
    assert {o["symbol"] for o in orders} == {i["symbol"] for i in CFG["instruments"]}
    assert any(o["status"] == "PARTIALLY_FILLED" for o in orders)
    assert any(o["status"] == "FILLED" for o in orders)
    for o in orders:
        assert (
            o["fill_source"] == "simulated" and o["tca_pretrade"]["label"] == "placeholder weights"
        )
        t = o["tca"]
        parts = sum(Decimal(t[k]) for k in ("delay", "impact", "spread", "opportunity", "fees"))
        assert abs(parts - Decimal(t["total"])) <= Decimal("1e-10") * max(
            Decimal(1), abs(Decimal(t["total"]))
        )
        assert Decimal(o["tca_pretrade"]["expected_cost_bps"]) > 0
        # every fill is a level of the recorded synthetic book, on the right side
        side = "asks" if o["side"] == "BUY" else "bids"
        assert [[f["price"], f["quantity"]] for f in o["fills"][:-1]] == o["book"][side][
            : len(o["fills"]) - 1
        ]
        assert o["seed"] == core.seed_for(
            o["order_id"][:10], _prev_hash(ledger30, o["order_id"]), o["symbol"]
        )


def _prev_hash(text: str, order_id: str) -> str:
    for r in rows_of(text)[1:]:
        if any(o["order_id"] == order_id for o in r["body"]["orders"]):
            return str(r["prev"])
    raise AssertionError(order_id)


def test_same_inputs_give_a_byte_identical_ledger(ledger30: str, days30: list[dt.date]) -> None:
    again = run_days(days30[:6], forward_log(synthetic_yields(days30)))
    assert again == "".join(x + "\n" for x in ledger30.splitlines()[:7])


def test_row_bytes_follow_the_paper_trading_canonical_rule(ledger30: str) -> None:
    for r in rows_of(ledger30)[:3]:
        assert core.canonical(r) == paper.canonical(r)  # HR-45, the library's own function
        assert r["hash"] == hashlib.sha256(paper.canonical(r)).hexdigest()


# ---------------------------------------------------------------- planted faults (P7)


def _edit(text: str, seq: int, change: Callable[[dict[str, Any]], None]) -> str:
    rows = copy.deepcopy(rows_of(text))
    change(rows[seq]["body"])
    return rechain(rows)


def _set(path: str, value: str) -> Callable[[dict[str, Any]], None]:
    def change(b: dict[str, Any]) -> None:
        node: Any = b
        keys = path.split("/")
        for k in keys[:-1]:
            node = node[int(k)] if isinstance(node, list) else node[k]
        node[keys[-1]] = value

    return change


def test_a_tampered_row_breaks_the_chain(ledger30: str) -> None:
    lines = ledger30.splitlines()
    assert '"nav_close":"' in lines[12]
    lines[12] = lines[12].replace('"timing":"on_time"', '"timing":"on-time"')
    v = check("".join(x + "\n" for x in lines))
    assert (v["ok"], v["first_bad_seq"], v["reason"]) == (False, 12, "HASH")
    # a removed row without re-hashing, and a row with a repeated key
    assert check("".join(x + "\n" for x in lines[:5] + lines[6:]))["reason"] == "SEQ"
    dup = ledger30.splitlines()
    dup[3] = dup[3][:-1] + ',"seq":3}'
    assert check("".join(x + "\n" for x in dup))["reason"] == "PARSE"


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        ("explain/curve_move", "1.5", "EXPLAIN"),
        ("explain/carry", "0", "EXPLAIN"),
        ("explain/unexplained", "0.01", "EXPLAIN"),
        ("pnl", "12345", "NAV"),
        ("nav_close", "10000001", "NAV"),
        ("cash_close", "1", "CASH"),
        ("positions_close/UST-CM-2Y", "100", "POSITION"),
        ("instruments/UST-CM-5Y/position_open", "700", "POSITION"),
        ("instruments/UST-CM-10Y/accrued", "0.5", "EXPLAIN"),
        ("cumulative/recorded_trading_days", "20", "COUNT"),
        ("date", "2027-01-18", "DATE"),
    ],
)
def test_a_rehashed_edit_fails_the_exact_replay(
    ledger30: str, path: str, value: str, reason: str
) -> None:
    v = check(_edit(ledger30, 9, _set(path, value)), cli=path == "date")
    assert (v["ok"], v["first_bad_seq"], v["reason"]) == (False, 9, reason), v


def test_an_explain_that_does_not_sum_is_caught_even_when_every_term_is_rewritten(
    ledger30: str,
) -> None:
    def change(
        b: dict[str, Any],
    ) -> None:  # move one dollar from the curve term to nowhere, consistently
        b["explain"]["curve_move"] = core.plain(Decimal(b["explain"]["curve_move"]) - 1)
        b["explain"]["total"] = core.plain(Decimal(b["explain"]["total"]) - 1)
        b["explain"]["unexplained"] = "1"

    v = check(_edit(ledger30, 9, change), cli=False)
    assert (v["first_bad_seq"], v["reason"]) == (9, "EXPLAIN")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (
            "instruments/UST-CM-10Y/y_close",
            "9.5",
        ),  # a mark input that the exact replay does not read
        ("par_yields/3 Mo", "1.11"),
        ("orders/0/tca/spread", "0"),
        ("orders/0/tca_pretrade/expected_cost_bps", "0.01"),
        ("orders/0/seed", "00" * 32),
        ("orders/0/rule_step", "7"),
    ],
)
def test_a_rehashed_edit_of_a_derived_field_fails_the_rebuild(
    ledger30: str, path: str, value: str
) -> None:
    text = _edit(ledger30, 9, _set(path, value))
    v = check(text)
    assert (v["ok"], v["first_bad_seq"], v["reason"]) == (False, 9, "RECOMPUTE"), v


def test_a_missing_day_is_caught_after_rehashing(ledger30: str) -> None:
    rows = rows_of(ledger30)
    v = check(rechain(rows[:14] + rows[15:]))
    assert (v["ok"], v["first_bad_seq"], v["reason"]) == (False, 14, "MISSING_DAY"), v
    assert rows[14]["body"]["date"] in v["detail"]
    # without the calendar the same cut still fails: the next day does not continue from the state before it
    assert check(rechain(rows[:14] + rows[15:]), cli=False)["ok"] is False


def test_a_wrong_label_or_changed_configuration_fails(ledger30: str) -> None:
    rows = copy.deepcopy(rows_of(ledger30))
    rows[4]["label"] = "crypto venue; simulated"
    assert check(rechain(rows))["reason"] == "LABEL"
    rows = copy.deepcopy(rows_of(ledger30))
    rows[0]["body"]["config"]["target_dv01_usd"] = "5000"
    assert check(rechain(rows))["reason"] == "CONFIG"
    looser = copy.deepcopy(CFG)
    looser["unexplained_threshold"] = "100"
    assert (
        check(ledger30, looser)["reason"] == "CONFIG"
    )  # the file may not drift from the genesis row


# ---------------------------------------------------------------- pre-trade limit breach (P8)


def test_a_limit_breach_is_rejected_and_nothing_fills(days30: list[dt.date]) -> None:
    tight = copy.deepcopy(CFG)
    tight["limits"]["max_order_qty"] = "100"
    tight["limits"]["max_notional"] = "5000"
    text = run_days(days30[:3], forward_log(synthetic_yields(days30[:3])), tight)
    rows = rows_of(text)
    for r in rows[1:]:
        (o,) = r["body"]["orders"]
        assert o["status"] == "REJECTED" and o["pretrade"] == {
            "accepted": "false",
            "reasons": ["MAX_QTY", "MAX_NOTIONAL"],
        }
        assert o["fills"] == [] and o["filled"] == "0" and o["cancelled"] == "0"
        assert set(r["body"]["positions_close"].values()) == {"0"}
    assert rows[-1]["body"]["explain"]["fills_costs"] == "0"
    assert check(text, tight)["ok"]

    def fill_it(b: dict[str, Any]) -> None:
        b["orders"][0]["fills"] = [{"quantity": "100", "price": "100.0078125", "fee": "0"}]
        b["orders"][0]["filled"] = "100"

    v = check(_edit(text, 2, fill_it), tight, cli=False)
    assert (v["first_bad_seq"], v["reason"]) == (2, "ORDER")


def test_the_kill_switch_rejects(days30: list[dt.date]) -> None:
    off = copy.deepcopy(CFG)
    off["limits"]["kill_switch"] = True
    text = run_days(days30[:1], forward_log(synthetic_yields(days30[:1])), off)
    assert rows_of(text)[1]["body"]["orders"][0]["pretrade"]["reasons"] == ["KILL_SWITCH"]


# ---------------------------------------------------------------- gaps and late runs (P9)


@pytest.fixture(scope="module")
def gappy(days30: list[dt.date]) -> tuple[str, list[dt.date]]:
    """Ten days: the recorder has no curve for day index 3, and the job does not run on day index 6."""
    days = days30[:10]
    y = synthetic_yields(days)
    del y[days[3].isoformat()]
    return run_days(days, forward_log(y), skip_runs=(days[6],)), days


def test_a_missed_curve_is_a_gap_row_and_a_missed_run_is_labelled_late(
    gappy: tuple[str, list[dt.date]],
) -> None:
    text, days = gappy
    v = check(text)
    assert v["ok"], v
    assert (v["gaps"], v["late_days"], v["recorded_trading_days"]) == (1, 1, 8)
    by_date = {r["body"]["date"]: r for r in rows_of(text)[1:]}
    assert list(by_date) == [d.isoformat() for d in days]  # every business day has a row, in order
    gap = by_date[days[3].isoformat()]
    assert gap["kind"] == "GAP" and gap["ts"] > core.stamp(
        core.Calendar(runner, "USGS").cutoff(days[3], CFG)
    )
    after = by_date[days[4].isoformat()]["body"]
    assert (
        after["gaps_since_prev"] == [days[3].isoformat()]
        and after["prev_date"] == days[2].isoformat()
    )
    assert int(after["days"]) == (days[4] - days[2]).days
    late = by_date[days[6].isoformat()]
    assert (
        late["body"]["timing"] == "late"
        and late["body"]["orders"] == []
        and "late run" in late["body"]["no_order"]
    )
    assert (
        late["ts"] == by_date[days[7].isoformat()]["ts"]
    )  # written by the next run, with that run's time
    assert (
        late["body"]["cumulative"]["recorded_trading_days"]
        == by_date[days[5].isoformat()]["body"]["cumulative"]["recorded_trading_days"]
    )


def test_gap_and_late_rows_cannot_be_relabelled_or_dropped(
    gappy: tuple[str, list[dt.date]],
) -> None:
    text, days = gappy
    rows = rows_of(text)
    at = {r["body"]["date"]: n for n, r in enumerate(rows) if n}
    late = at[days[6].isoformat()]
    v = check(_edit(text, late, _set("timing", "on_time")))
    assert (v["first_bad_seq"], v["reason"]) == (late, "TIMING")
    gap = at[days[3].isoformat()]
    v = check(rechain(rows[:gap] + rows[gap + 1 :]))
    assert (v["first_bad_seq"], v["reason"]) == (gap, "MISSING_DAY")
    v = check(_edit(text, gap + 1, _set("gaps_since_prev", [])))  # type: ignore[arg-type]
    assert v["reason"] == "MISSING_DAY"


def test_nothing_is_written_before_a_curve_is_recorded_and_the_start_is_never_back_filled(
    days30: list[dt.date],
) -> None:
    log = forward_log(synthetic_yields(days30[:5]))
    text, new, notes = core.run(CFG, runner, "", [], evening(days30[0]), "c", "python", NO_WINDOWS)
    assert (text, new) == ("", []) and "nothing written" in notes[0]
    # first run on day index 4: the ledger starts there, with no rows for the four earlier days
    text, new, _ = core.run(CFG, runner, "", log, evening(days30[4]), "c", "python", NO_WINDOWS)
    assert [r["kind"] for r in new] == ["GENESIS", "DAY"] and new[1]["body"]["date"] == days30[
        4
    ].isoformat()
    # a second run the same evening adds nothing
    again, new, _ = core.run(CFG, runner, text, log, evening(days30[4]), "c", "python", NO_WINDOWS)
    assert again == text and new == []


# ---------------------------------------------------------------- holdout windows (plan 14.10 rule 6)


def test_a_date_inside_a_holdout_window_is_refused_and_fails_verify(
    ledger30: str, days30: list[dt.date]
) -> None:
    windows = core.holdout_windows()
    assert windows and check(ledger30)["ok"]
    assert core.verify(ledger30, CFG, None)[
        "ok"
    ]  # the real windows: the synthetic dates are outside all of them
    planted = {"PLANTED": (days30[10].isoformat(), days30[12].isoformat())}
    v = core.verify(ledger30, CFG, None, planted)
    assert (v["ok"], v["first_bad_seq"], v["reason"]) == (False, 11, "HOLDOUT")
    # the writer refuses a real holdout date (built here so that no such date is written in this file)
    inside = dt.date.fromisoformat(max(hi for _, hi in windows.values()))
    while not core.Calendar(runner, "USGS").is_open(inside):
        inside -= dt.timedelta(days=1)
    log = forward_log(synthetic_yields([inside]))
    with pytest.raises(core.PaperError, match="holdout window"):
        core.run(CFG, runner, "", log, evening(inside), "c", "python")


# ---------------------------------------------------------------- the builder refuses an explain that does not sum


def test_the_writer_refuses_a_day_whose_explain_does_not_sum(days30: list[dt.date]) -> None:
    log = forward_log(synthetic_yields(days30[:6]))
    text = run_days(days30[:5], log)

    def off_by_a_cent(cases: list[dict[str, Any]]) -> dict[str, Any]:
        out = runner(cases)
        if "curve|UST-CM-2Y" in out:
            out["curve|UST-CM-2Y"]["market"] = core.plain(
                Decimal(out["curve|UST-CM-2Y"]["market"]) + Decimal("0.01")
            )
        return out

    with pytest.raises(core.PaperError, match="does not replay|unexplained"):
        core.run(CFG, off_by_a_cent, text, log, evening(days30[5]), "c", "python", NO_WINDOWS)
    assert rows_of(
        run_days(days30[5:6], log)
    )  # sanity: the same call without the fault is fine on its own


def test_the_writer_refuses_to_extend_a_ledger_that_does_not_verify(
    ledger30: str, days30: list[dt.date]
) -> None:
    bad = _edit(ledger30, 9, _set("explain/curve_move", "1.5"))
    with pytest.raises(core.PaperError, match="does not verify"):
        core.run(CFG, runner, bad, [], evening(days30[-1]), "c", "python", NO_WINDOWS)


# ---------------------------------------------------------------- anchors (K-2: anchored like the forward log)


def test_anchors_catch_a_rewrite_with_every_hash_recomputed(ledger30: str, tmp_path: Path) -> None:
    early = "".join(x + "\n" for x in ledger30.splitlines()[:11])
    a = core.anchor_make(early, CFG, tmp_path, "2027-01-15T234500Z")
    assert json.loads(a.read_text())["count"] == 11
    core.anchor_make(ledger30, CFG, tmp_path, "2027-02-16T234500Z")
    assert core.anchor_check(ledger30, CFG, tmp_path) == 2
    rows = copy.deepcopy(rows_of(ledger30))
    rows[5]["body"]["run"]["commit"] = (
        "rewritten"  # a field no replay reads: only the anchor can see this
    )
    rewritten = rechain(rows)
    assert check(rewritten, cli=False)["ok"]
    with pytest.raises(core.PaperError, match="rewritten"):
        core.anchor_check(rewritten, CFG, tmp_path)
    with pytest.raises(core.PaperError, match="rows were removed"):
        core.anchor_check(early, CFG, tmp_path)


# ---------------------------------------------------------------- the 20-day gate (K-2)


def test_the_twenty_day_gate(
    ledger30: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    short = tmp_path / "short.jsonl"
    short.write_text(
        "".join(x + "\n" for x in ledger30.splitlines()[:20]), encoding="utf-8", newline="\n"
    )
    full = tmp_path / "full.jsonl"
    full.write_text(ledger30, encoding="utf-8", newline="\n")
    assert (
        verify_cli.main(["verify", "--ledger", str(short), "--no-cli", "--require-days", "20"]) == 1
    )
    out = json.loads(capsys.readouterr().out)
    assert out["reason"] == "DAYS" and "19 recorded trading days" in out["detail"]
    summary = tmp_path / "s.json"
    args = [
        "verify",
        "--ledger",
        str(full),
        "--no-cli",
        "--require-days",
        "20",
        "--summary",
        str(summary),
    ]
    assert verify_cli.main(args) == 0
    assert json.loads(summary.read_text())["recorded_trading_days"] == 30


def test_late_days_and_gaps_do_not_count_towards_the_gate(gappy: tuple[str, list[dt.date]]) -> None:
    text, days = gappy
    assert len(days) == 10 and check(text)["recorded_trading_days"] == 8


# ---------------------------------------------------------------- goldens pl_k (paper-ledger-daily.md)


def test_goldens_pl_k(ledger30: str) -> None:
    rows = rows_of(ledger30)
    assert rows[1]["hash"] == "d7f22a80b63fa8ad612907dd6c8b1d4ba0e67527398887bb7848f5e6e5d191f3"
    assert rows[1]["body"]["pnl"] == "-285.9375"
    assert rows[2]["hash"] == "f887e3d3d0a9ac889d95d5a6e3ee3578b4908286700c5428ea1c7daee2980cb4"
    b = rows[2]["body"]
    assert b["instruments"]["UST-CM-2Y"]["mark"] == "99.938677" and b["pnl"] == "-895.26075"
    assert b["explain"]["carry"] == "1213.9355" and b["explain"]["curve_move"] == "-1993.7275"
    assert rows[-1]["hash"] == "56a3dd05b177badb7e91c5f1033058282773df03d7fc58b5d1676def5258cf28"
    status = [o["status"] for r in rows[1:] for o in r["body"]["orders"]]
    assert (status.count("FILLED"), status.count("PARTIALLY_FILLED")) == (17, 13)


def test_no_code_path_reaches_fedinvest_or_a_network() -> None:
    """P1 and KR-70: the job reads the recorded log only."""
    for name in ("paper_core.py", "run_day.py", "verify_ledger.py"):
        src = (ROOT / "tools" / "paper_daily" / name).read_text(encoding="utf-8")
        for word in ("urllib", "requests", "http.client", "socket", "FedInvest", "treasurydirect"):
            assert word not in src, (name, word)


def test_the_workflow_pins_actions_as_the_recorder_does_and_pushes_only_its_own_branches() -> None:
    wf = (ROOT / ".github" / "workflows" / "paper-ledger.yml").read_text(encoding="utf-8")
    recorder = (ROOT / ".github" / "workflows" / "recorder.yml").read_text(encoding="utf-8")
    uses = [ln.split("uses:")[1].strip() for ln in wf.splitlines() if "uses:" in ln]
    assert uses and all(
        u in recorder and "@" in u and len(u.split("@")[1].split()[0]) == 40 for u in uses
    )
    pushes = [ln.strip() for ln in wf.splitlines() if "git push" in ln]
    assert (
        len(pushes) == 2
        and "push origin paper-ledger" in pushes[0]
        and "paper-ledger-anchors" in pushes[1]
    )
    assert "permissions:" + chr(10) + "  contents: write" + chr(10) + "concurrency:" in wf
    assert "dry_run" in wf and "pull_request" not in wf and "fwd remote remove origin" in wf
