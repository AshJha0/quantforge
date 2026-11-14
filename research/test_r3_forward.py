"""Tests of the R3 forward-log writer (amendment 6) and the rule-5 signal check, on synthetic data only."""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from typing import Any, ClassVar

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import holdout_scan as hs
import r3_data as d
import r3_forward as w
import r3_runner as r

RUNS = {st: {"study": st, "utc_date": "2026-11-14", "script": "research/r3_runner.py",
             "script_sha256": w.sha(w.HERE / "r3_runner.py"), "commit": "faadaa4"} for st in w.STUDIES}
FIT: dict[str, Any] = {"lambda": 0, "month_mean_bp": {str(m): (m - 6.5) / 10 for m in range(1, 13)}}
SHAS = {"writer": "w" * 64, "runner": "r" * 64}


def bdays(start: date, n: int) -> list[date]:
    out: list[date] = []
    x = start
    while len(out) < n:
        if x.weekday() < 5:
            out.append(x)
        x += timedelta(days=1)
    return out


def write_log(path: Path, rows: list[tuple[str, str, dict[str, Any]]]) -> list[w.Entry]:
    for i, (sid, et, pay) in enumerate(rows):
        w.fl.append(path, sid, et, pay, knowledge_time=f"2026-11-{10 + i // 100:02d}T00:00:00Z")
    entries: list[w.Entry] = w.fl.read(path)
    return entries


def study(st: str) -> dict[str, Any]:
    return {"kind": "study_position", "position": None, "signal": None, "status": "no position", "inputs": {}}


class Series(unittest.TestCase):
    def test_r301_matches_runner_on_long_synthetic_history(self) -> None:
        days = bdays(date(2020, 1, 1), 620)
        rng = np.random.default_rng(1)
        y = np.cumsum(rng.normal(0, 0.03, (620, 3)), axis=0) + np.array([2.0, 2.5, 3.0])
        state = {"us-treasury-par-yields": {f"{x}|{c}": float(y[i, j]) for i, x in enumerate(days)
                                            for j, c in enumerate(("2 Yr", "5 Yr", "10 Yr"))}}
        sig, pos, status, as_of = w.r301_signal(w.to_series(state, days[-1]), 500, 1.5)
        fly = (2 * y[:, 1] - y[:, 0] - y[:, 2]) * 100
        z = r.zscore(fly, 500)
        self.assertEqual(status, "computed")
        self.assertAlmostEqual(sig or 0.0, float(z[-1]), places=9)
        self.assertEqual(pos, float(r.hysteresis(z, 1.5)[-1]))
        self.assertEqual(as_of, days[-1].isoformat())
        # a date cut-off drops later observations (C1)
        short = w.r301_signal(w.to_series(state, days[100]), 500, 1.5)
        self.assertEqual(short[:3], (None, None, "insufficient recorded history: 101 of 500 business days"))

    def test_r302_positions_agree_with_runner_months(self) -> None:
        days = bdays(date(2019, 1, 1), 420)
        rng = np.random.default_rng(2)
        bill = 2 + np.cumsum(rng.normal(0, 0.02, 420))
        fund = bill - 0.1 + rng.normal(0, 0.05, 420)
        state = {"us-treasury-bill-rates": {f"{x}|13 WEEKS COUPON EQUIVALENT": float(bill[i]) for i, x in enumerate(days)}}
        for src in ("nyfed-sofr", "nyfed-tgcr", "nyfed-bgcr"):
            state[src] = {f"{x}|percentRate": float(fund[i]) for i, x in enumerate(days)}
        ex, ret = r.bill_month_returns(days, bill / 100, fund / 100, 60, 1.0, cost_mult=0.0)
        starts = r.month_starts(days)
        checked = 0
        for j, x in enumerate(ex):
            e = starts[[days[i] for i in starts].index(x) - 1]
            sig = w.r302_signal(w.to_series(state, days[e]), 60, 1.0, "SOFR")
            self.assertEqual(sig[2], "computed")
            self.assertEqual(sig[1] == 0.0, ret[j] == 0.0)
            checked += 1
        self.assertGreater(checked, 5)
        none = w.r302_signal(w.to_series(state, days[10]), 60, 1.0, "SOFR")
        self.assertEqual(none[:2], (None, None))
        self.assertIn("of 60 spread values", none[2])
        self.assertEqual(w.r302_signal(w.to_series({}, days[10]), 60, 1.0, "SOFR")[2],
                         "insufficient recorded history: 0 of 60 spread values")

    def test_r303_month_means_and_signal(self) -> None:
        ends = [date(2003 + i // 12, i % 12 + 1, 28) for i in range(36)]
        b = np.arange(36, dtype=float) ** 1.5
        m = w.r303_month_means(ends, b, date(2004, 12, 31))
        dd = np.diff(b)
        self.assertAlmostEqual(m[3], float(np.mean([dd[1], dd[13]])))  # March changes ending in 2003 and 2004
        self.assertEqual(w.r303_signal(FIT, date(2026, 11, 9)), (0.45, 1.0, "computed", None))
        self.assertEqual(w.r303_signal(FIT, date(2026, 2, 2))[1], -1.0)
        self.assertEqual(w.r303_signal({"lambda": 0, "month_mean_bp": {}}, date(2026, 2, 2))[:2], (0.0, 0.0))

    def test_to_series_maps_fields_and_skips_monthly_keys(self) -> None:
        st = {"us-treasury-par-yields": {"2026-11-10|5 Yr": 4.0, "2026-11-10|30 Yr": 4.5},
              "nyfed-sofr": {"2026-11-10|percentRate": 3.9, "2026-11-10|volumeInBillions": 2000.0},
              "bls-cpi-u-nsa": {"2026-10|CUUR0000SA0": 300.0}}
        s = w.to_series(st, date(2026, 11, 10))
        self.assertEqual(s[d.NOMINAL], {date(2026, 11, 10): {"5 YR": 4.0}})
        self.assertEqual(s["SOFR"], {date(2026, 11, 10): {"SOFR": 3.9}})


class Rows(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def log(self, bad_state: bool = False) -> list[w.Entry]:
        obs = {"2026-11-10|2 Yr": 3.5}
        rows: list[tuple[str, str, dict[str, Any]]] = [
            ("recorder/us-treasury-par-yields", "2026-11-10T21:00:00Z",
             {"observations": obs, "state_sha256": "0" * 64 if bad_state else w.state_hash(obs)})]
        for day in ("2026-11-12", "2026-11-13", "2026-11-14", "2026-11-17"):
            rows += [(f"study/{st}", f"{day}T21:00:00Z", study(st)) for st in w.STUDIES]
        return write_log(self.tmp / "fwd.jsonl", rows)

    def test_backfill_marks_rows_before_j2_and_daily_skips_them(self) -> None:
        entries = self.log()
        rows = w.build(entries, RUNS, "backfill", set(), FIT, "f" * 64, "c" * 40, SHAS)
        self.assertEqual(len(rows), 12)
        back = [p for _, et, p in rows if et < "2026-11-14"]
        self.assertTrue(all(p["backfilled"] and p["backfill_commit"] == "c" * 40 for p in back))
        self.assertTrue(all(not p["backfilled"] and "backfill_commit" not in p for _, et, p in rows if et >= "2026-11-14"))
        r301 = [p for sid, _, p in rows if sid == "study/R3-01"]
        self.assertTrue(all(p["signal"] is None and p["signal_status"].startswith("insufficient") for p in r301))
        r303 = [p for sid, _, p in rows if sid == "study/R3-03"]
        self.assertTrue(all(p["signal"] == 0.45 and p["fit_sha256"] == "f" * 64 for p in r303))
        self.assertEqual(r301[0]["inputs"], {"us-treasury-par-yields": w.state_hash({"2026-11-10|2 Yr": 3.5})})
        self.assertTrue(all(set(p) & {"pnl", "return", "sharpe"} == set() for _, _, p in rows))
        daily = w.build(entries, RUNS, "daily", set(), FIT, "f" * 64, "c" * 40, SHAS)
        self.assertEqual(len(daily), 6)
        done = {p["fills"] for _, _, p in rows}
        self.assertEqual(w.build(entries, RUNS, "daily", done, FIT, "f" * 64, "c" * 40, SHAS), [])

    def test_state_mismatch_stops(self) -> None:
        with self.assertRaises(w.Refused):
            w.build(self.log(bad_state=True), RUNS, "backfill", set(), FIT, "f" * 64, "c", SHAS)

    def test_append_all_and_existing(self) -> None:
        entries = self.log()
        rows = w.build(entries, RUNS, "backfill", set(), FIT, "f" * 64, "c", SHAS)
        out = self.tmp / "sig.jsonl"
        self.assertEqual(w.existing(out), (set(), False))
        w.append_all(out, rows, "2026-11-14T15:00:00Z")
        fills, back = w.existing(out)
        self.assertEqual(len(fills), 12)
        self.assertTrue(back)
        dup = self.tmp / "dup.jsonl"
        w.append_all(dup, rows[:1] + rows[:1], "2026-11-14T15:00:00Z")
        with self.assertRaises(w.Refused):
            w.existing(dup)

    def test_check_pins(self) -> None:
        amend = (w.HERE / "preregs" / "R3-01-amendment-6.md").read_text(encoding="utf-8")
        w.check_pins(RUNS, amend)
        with self.assertRaises(w.Refused):
            w.check_pins({**RUNS, "R3-02": {**RUNS["R3-02"], "script_sha256": "0" * 64}}, amend)
        with self.assertRaises(w.Refused):
            w.check_pins(RUNS, amend.replace(w.sha(w.HERE / "r3_data.py"), "0" * 64))
        with self.assertRaises(w.Refused):
            w.check_pins({k: v for k, v in RUNS.items() if k != "R3-03"}, amend)


def entry(et: str, kt: str, pay: dict[str, Any], commit: str = "good") -> dict[str, Any]:
    return {"record": {"series_id": "study/R3-03", "event_time": et, "knowledge_time": kt,
                       "value": {"commit": commit, "payload": pay}}}


class SignalCheck(unittest.TestCase):
    runs: ClassVar[dict[str, str]] = {"R3-03": "2026-11-14"}

    @staticmethod
    def show(commit: str) -> str | None:
        return "study,utc_date\nR3-03,2026-11-14\n" if commit == "good" else None

    def check(self, *es: dict[str, Any], runs: dict[str, str] | None = None) -> list[str]:
        return [b[1][0] for b in hs.signal_check(list(es), runs if runs is not None else self.runs, show=self.show)]

    def test_rules(self) -> None:
        ok_back = {"signal": 1.0, "position": 1.0, "backfilled": True, "backfill_commit": "good"}
        self.assertEqual(self.check(entry("2026-11-12T21:00:00Z", "2026-11-14T15:00:00Z", ok_back)), [])
        self.assertEqual(self.check(entry("2026-11-12T21:00:00Z", "2026-11-14T15:00:00Z", {"signal": None, "position": None})), [])
        self.assertEqual(self.check(entry("2026-11-12T21:00:00Z", "2026-11-14T15:00:00Z", ok_back), runs={}), ["a"])
        self.assertEqual(self.check(entry("2026-11-12T21:00:00Z", "2026-11-13T15:00:00Z", ok_back)), ["b"])
        self.assertEqual(self.check(entry("2026-11-12T21:00:00Z", "2026-11-14T15:00:00Z", {"signal": 1.0})), ["c"])
        self.assertEqual(self.check(entry("2026-11-17T21:00:00Z", "2026-11-17T22:00:00Z", {"position": 0.0}, "gone")), ["d"])
        self.assertEqual(self.check(entry("2026-11-17T21:00:00Z", "2026-11-17T22:00:00Z", {"signal": 0.2})), [])


if __name__ == "__main__":
    unittest.main()
