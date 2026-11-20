"""Stage K, K-5: versioned immutable snapshots and the real-time hedge they carry (spec
`specifications/12-platform/lock-free-snapshots.md` 1.0.0, rulings KR-280 to KR-288, confirmed 2026-11-20).

Latency-aware analytics on simulated data. **This Python build is a correctness reference only: it is
not lock-free.** A publish takes a `threading.Lock` (one writer is the rule, the lock only makes a
second writer fail loudly instead of silently), and a read is one attribute load of a reference to a
frozen object. That gives the same semantics as the lock-free builds (whole snapshots only, versions
monotone per reader) on CPython with or without the GIL, because a reference load or store is atomic
there, but it says nothing about progress or latency. The race tests that count for K-5 are the C++
(ThreadSanitizer), Rust (ThreadSanitizer, CI only) and Java (jcstress) ones.

What a snapshot holds (KR-283): the version, the logical event number, the cumulative parallel shift of
the simulated market, and five numbers the writer computes once per publish from library operations:
`risk.intraday.delta_gamma_bound` of the book at that shift (estimate and bound), the book's parallel
delta at the shifted yields, the delta of one unit of the hedge zero, and the hedge notional that
neutralises the book's delta. A 64-bit checksum over all fields (KR-287) lets every reader detect a
torn snapshot. No orders and no venue: the hedge is a recommendation, a number.
"""

import math
import struct
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from . import stage_k as sk
from .finite import guard

LABEL = sk.LABEL
MASK = (1 << 64) - 1
CHECK_SEED = 0x9E3779B97F4A7C15
CHECK_MUL = 0x94D049BB133111EB


def f64_bits(x: float) -> int:
    """The IEEE 754 binary64 bit pattern of `x` as an unsigned 64-bit integer."""
    return int.from_bytes(struct.pack("<d", x), "little")


def checksum(words: Sequence[int]) -> int:
    """KR-287: `c = SEED; for w: c = rotl64(c xor w, 27) * MUL mod 2^64`."""
    c = CHECK_SEED
    for w in words:
        x = (c ^ w) & MASK
        c = ((((x << 27) | (x >> 37)) & MASK) * CHECK_MUL) & MASK
    return c


@dataclass(frozen=True)
class Snapshot:
    """One immutable snapshot (KR-280). Fields are never changed after construction."""

    version: int
    as_of: int
    shift: float
    estimate_pnl: float
    bound: float
    book_delta: float
    hedge_unit_delta: float
    hedge_notional: float
    check: int

    def words(self) -> list[int]:
        return [
            self.version & MASK,
            self.as_of & MASK,
            f64_bits(self.shift),
            f64_bits(self.estimate_pnl),
            f64_bits(self.bound),
            f64_bits(self.book_delta),
            f64_bits(self.hedge_unit_delta),
            f64_bits(self.hedge_notional),
        ]

    def intact(self) -> bool:
        """True when the stored checksum matches the fields: the reader's torn-read test."""
        return checksum(self.words()) == self.check


@dataclass(frozen=True)
class HedgeInstrument:
    """The zero-coupon hedge instrument: one unit pays 1 at `maturity`, priced at `yield_`."""

    maturity: float
    yield_: float


def book_delta(positions: Sequence[sk.ZeroPosition], shift: float) -> float:
    """KR-283: the parallel delta of the book at the shifted yields,
    `fsum(-T * (N * exp(-(y + h) * T)))`, in that order."""
    return math.fsum(
        -p.maturity * (p.notional * math.exp(-(p.yield_ + shift) * p.maturity)) for p in positions
    )


def hedge_unit_delta(hedge: HedgeInstrument, shift: float) -> float:
    """KR-283: `-T_H * exp(-(y_H + h) * T_H)`, the delta of one unit of the hedge zero."""
    return -hedge.maturity * math.exp(-(hedge.yield_ + shift) * hedge.maturity)


def build(
    version: int,
    as_of: int,
    positions: Sequence[sk.ZeroPosition],
    hedge: HedgeInstrument,
    shift: float,
) -> Snapshot:
    """The writer's per-publish computation (KR-283). Every number is the direct library call; the
    snapshot stores results and does no arithmetic of its own (KR-284)."""
    risk = sk.delta_gamma_bound(positions, shift)
    d = book_delta(positions, shift)
    u = hedge_unit_delta(hedge, shift)
    q = -d / u
    fields = (version, as_of, shift, risk["estimate_pnl"], risk["bound"], d, u, q)
    probe = Snapshot(*fields, check=0)
    return Snapshot(*fields, check=checksum(probe.words()))


def scenario_shift(k: int) -> float:
    """KR-287: the shift of version `k`: `((k * 7919) mod 401 - 200) * 5e-5` (0 for version 0)."""
    return 0.0 if k == 0 else float((k * 7919) % 401 - 200) * 5e-5


class SnapshotCell:
    """Single writer, many readers. Correctness reference only; not lock-free (see the module text)."""

    def __init__(self, initial: Snapshot) -> None:
        self._current = initial
        self._writer = threading.Lock()

    def publish(self, snap: Snapshot) -> None:
        if not self._writer.acquire(blocking=False):
            raise RuntimeError(
                "SnapshotCell has one writer (KR-280); a second concurrent publish was refused"
            )
        try:
            if snap.version <= self._current.version:
                raise ValueError("versions must strictly increase (KR-280)")
            self._current = snap
        finally:
            self._writer.release()

    def read(self) -> Snapshot:
        return self._current


@dataclass
class ReaderReport:
    reads: int = 0
    torn: int = 0
    non_monotone: int = 0
    last_version: int = -1
    mismatched: int = 0


def run_race(
    positions: Sequence[sk.ZeroPosition],
    hedge: HedgeInstrument,
    publishes: int,
    readers: int,
    verify_every: int = 64,
    cell_factory: Callable[[Snapshot], SnapshotCell] = SnapshotCell,
) -> list[ReaderReport]:
    """The shared race scenario (KR-287): one writer publishes versions 1..`publishes`; each reader reads
    until it has seen the final version, checking the checksum on every read, monotone versions, and every
    `verify_every`-th read against a fresh direct computation (KR-284)."""
    cell = cell_factory(build(0, 0, positions, hedge, 0.0))
    reports = [ReaderReport() for _ in range(readers)]
    start = threading.Barrier(readers + 1)

    def reader(r: ReaderReport) -> None:
        start.wait()
        while True:
            s = cell.read()
            r.reads += 1
            if not s.intact():
                r.torn += 1
            if s.version < r.last_version:
                r.non_monotone += 1
            r.last_version = max(r.last_version, s.version)
            if r.reads % verify_every == 0 and s != build(
                s.version, s.as_of, positions, hedge, s.shift
            ):
                r.mismatched += 1
            if s.version >= publishes:
                return

    threads = [threading.Thread(target=reader, args=(r,)) for r in reports]
    for t in threads:
        t.start()
    start.wait()
    for k in range(1, publishes + 1):
        cell.publish(build(k, k, positions, hedge, scenario_shift(k)))
    for t in threads:
        t.join()
    return reports


# E1: every public function rejects NaN and infinity at its inputs first (tests/test_finite.py). The guard's
# re-entry flag is thread-local, so the reader threads of run_race are checked independently.
guard(globals())
