"""K-5 snapshot semantics (PROPOSED, KR-280 to KR-288) on the shared scenario
datasets/scenarios/k5_snapshot.json. The Python build is a correctness reference, not lock-free: these
tests check the semantics (whole snapshots, monotone versions, final version seen, exactness), not
progress. Latency-aware analytics on simulated data."""

import json
import math
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from quantforge_core import live_snapshot as sn
from quantforge_core import stage_k as sk

ROOT = Path(__file__).resolve().parents[2]
SCEN = json.loads(
    (ROOT / "datasets" / "scenarios" / "k5_snapshot.json").read_text(encoding="utf-8")
)
BOOK = [sk.ZeroPosition(p["notional"], p["maturity"], p["yield"]) for p in SCEN["book"]]
HEDGE = sn.HedgeInstrument(SCEN["hedge"]["maturity"], SCEN["hedge"]["yield"])
FIELDS = ["shift", "estimate_pnl", "bound", "book_delta", "hedge_unit_delta", "hedge_notional"]


def test_scenario_file_is_current() -> None:
    import subprocess
    import sys

    script = ROOT / "datasets" / "scenarios" / "build_k5_snapshot.py"
    assert subprocess.run([sys.executable, str(script), "--check"], check=False).returncode == 0


@pytest.mark.parametrize("row", SCEN["expected"], ids=lambda r: f"v{r['version']}")
def test_expected_values(row: dict[str, float]) -> None:
    k = int(row["version"])
    s = sn.build(k, k, BOOK, HEDGE, sn.scenario_shift(k))
    tol = SCEN["tolerance_relative"]
    for f in FIELDS:
        assert math.isclose(getattr(s, f), row[f], rel_tol=tol, abs_tol=0.0), f
    assert s.intact()


def test_hedge_neutralises_delta() -> None:
    # The recommended hedge sets the book's parallel delta to zero (up to rounding): the reason it exists.
    for k in (1, 7, 401, 999):
        s = sn.build(k, k, BOOK, HEDGE, sn.scenario_shift(k))
        residual = s.book_delta + s.hedge_notional * s.hedge_unit_delta
        assert abs(residual) <= 1e-9 * abs(s.book_delta)


def test_exactness_1000_publishes() -> None:
    # KR-284: every number read through the cell is bit-identical to the direct library call.
    cell = sn.SnapshotCell(sn.build(0, 0, BOOK, HEDGE, 0.0))
    for k in range(1, SCEN["exactness_publishes"] + 1):
        h = sn.scenario_shift(k)
        cell.publish(sn.build(k, k, BOOK, HEDGE, h))
        s = cell.read()
        risk = sk.delta_gamma_bound(BOOK, h)
        d, u = sn.book_delta(BOOK, h), sn.hedge_unit_delta(HEDGE, h)
        direct = [h, risk["estimate_pnl"], risk["bound"], d, u, -d / u]
        assert [sn.f64_bits(getattr(s, f)) for f in FIELDS] == [sn.f64_bits(x) for x in direct]
        assert s.version == k


def test_checksum_detects_a_corrupted_field() -> None:
    # Planted fault 4 (KR-288): the reader check must fail on a snapshot with one field changed.
    s = sn.build(5, 5, BOOK, HEDGE, sn.scenario_shift(5))
    assert s.intact()
    for f in FIELDS:
        bad = replace(s, **{f: math.nextafter(getattr(s, f), math.inf)})  # type: ignore[arg-type]
        assert not bad.intact(), f
    assert not replace(s, version=6).intact()
    assert not replace(s, as_of=4).intact()


def test_checksum_reference_value() -> None:
    # Pins the KR-287 mixing function so the other builds can check theirs against the same numbers.
    assert sn.checksum([]) == 0x9E3779B97F4A7C15
    assert sn.checksum([0]) == 0xF6E599AEF89D022F
    assert sn.checksum([1, 2, 3]) == 0x8517CC75DE438E52


def test_publish_rejects_a_non_increasing_version() -> None:
    cell = sn.SnapshotCell(sn.build(3, 3, BOOK, HEDGE, 0.0))
    with pytest.raises(ValueError, match="strictly increase"):
        cell.publish(sn.build(3, 3, BOOK, HEDGE, 0.0))


def test_second_concurrent_writer_is_refused() -> None:
    cell = sn.SnapshotCell(sn.build(0, 0, BOOK, HEDGE, 0.0))
    assert cell._writer.acquire()  # simulate a writer inside publish
    try:
        with pytest.raises(RuntimeError, match="one writer"):
            cell.publish(sn.build(1, 1, BOOK, HEDGE, 0.0))
    finally:
        cell._writer.release()


@pytest.mark.parametrize("readers", [1, 4])
def test_race_scenario(readers: int) -> None:
    publishes = 2000  # Python is the reference; the long runs are the native and JVM builds
    reports = sn.run_race(BOOK, HEDGE, publishes, readers, verify_every=16)
    for r in reports:
        assert r.torn == 0
        assert r.non_monotone == 0
        assert r.mismatched == 0
        assert r.last_version == publishes
        assert r.reads >= 1


def test_race_checker_catches_an_in_place_writer() -> None:
    # Planted fault 3 in Python form: a cell whose writer hands out a snapshot with a wrong checksum. The
    # scenario's reader check must count it as torn (proves the checker runs inside run_race).
    class Faulty(sn.SnapshotCell):
        def publish(self, snap: sn.Snapshot) -> None:
            super().publish(replace(snap, bound=snap.bound * 2))

    reports = sn.run_race(BOOK, HEDGE, 50, 1, verify_every=1, cell_factory=Faulty)
    assert reports[0].torn > 0
    assert reports[0].mismatched > 0


def test_readers_see_only_whole_snapshots_under_thread_switching() -> None:
    # Forces frequent thread switches so the reader interleaves with the writer at many points.
    import sys

    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        reports = sn.run_race(BOOK, HEDGE, 300, 2, verify_every=1)
    finally:
        sys.setswitchinterval(old)
    assert all(r.torn == 0 and r.mismatched == 0 and r.last_version == 300 for r in reports)
    assert threading.active_count() >= 1
