//! Stage K, K-5 (PROPOSED spec `12-platform/lock-free-snapshots.md` 0.2.0, rulings KR-280 to KR-288):
//! versioned immutable snapshots published by one writer to many readers through single-writer hazard
//! pointers over a fixed pool (KR-280), and the real-time hedge a snapshot carries (KR-283).
//! Latency-aware analytics on simulated data.
//!
//! Standard library only (`std::sync::atomic`, `UnsafeCell`); no third-party crate (KR-281).
//! Progress (KR-282): the writer is wait-free (one scan of R hazards); a reader is lock-free, not
//! wait-free. No heap allocation after construction. No latency is claimed: no timing run exists.

use std::cell::UnsafeCell;
use std::sync::atomic::{AtomicU32, Ordering};

use crate::error::Result;
use crate::research_w3::fsum;
use crate::stage_k::{self, ZeroPosition};

/// Test-only planted faults (KR-288). Production code uses `Fault::None`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Fault {
    None,
    /// `current` stored and loaded relaxed: `ThreadSanitizer` must report a race on slot contents.
    RelaxedPublish,
    /// The writer reuses the next slot without scanning hazards: `ThreadSanitizer` must report.
    SkipHazardScan,
}

/// At most 64 registered readers (KR-280).
pub const MAX_READERS: usize = 64;
const NONE_SLOT: u32 = u32::MAX;

#[repr(align(64))]
struct Slot<T>(UnsafeCell<T>);

#[repr(align(64))]
struct Hazard(AtomicU32);

/// Single writer, R readers (1..=64), pool of R + 2 slots of a `Copy` value (KR-280).
pub struct SnapshotCell<T: Copy> {
    slots: Box<[Slot<T>]>,
    hazards: Box<[Hazard]>,
    current: AtomicU32,
    fault: Fault,
}

// SAFETY: a slot is written only by the single writer (`publish` takes `&self` but the type's
// contract, stated on `publish`, is one writer), and only when no reader has announced it in its
// hazard (the hazard-pointer protocol of KR-280); readers only read a slot after validating it.
// The values are `Copy` and `Send`.
unsafe impl<T: Copy + Send> Sync for SnapshotCell<T> {}

/// A held snapshot; the hazard is released when it is dropped.
pub struct Guard<'a, T: Copy> {
    hazard: &'a Hazard,
    value: &'a T,
}

impl<T: Copy> std::ops::Deref for Guard<'_, T> {
    type Target = T;
    fn deref(&self) -> &T {
        self.value
    }
}

impl<T: Copy> Drop for Guard<'_, T> {
    fn drop(&mut self) {
        self.hazard.0.store(NONE_SLOT, Ordering::Release);
    }
}

impl<T: Copy> SnapshotCell<T> {
    /// A cell for `readers` readers (1 to 64) holding `initial`.
    pub fn new(readers: usize, initial: T) -> Option<Self> {
        Self::with_fault(readers, initial, Fault::None)
    }

    /// Test-only: a cell with a planted fault (KR-288). `None` when `readers` is outside 1..=64.
    pub fn with_fault(readers: usize, initial: T, fault: Fault) -> Option<Self> {
        if !(1..=MAX_READERS).contains(&readers) {
            return None;
        }
        let slots = (0..readers + 2)
            .map(|_| Slot(UnsafeCell::new(initial)))
            .collect();
        let hazards = (0..readers).map(|_| Hazard(AtomicU32::new(NONE_SLOT))).collect();
        Some(Self {
            slots,
            hazards,
            current: AtomicU32::new(0),
            fault,
        })
    }

    pub fn readers(&self) -> usize {
        self.hazards.len()
    }

    pub fn pool_size(&self) -> usize {
        self.slots.len()
    }

    fn orders(&self) -> (Ordering, Ordering) {
        if self.fault == Fault::RelaxedPublish {
            (Ordering::Relaxed, Ordering::Relaxed)
        } else {
            (Ordering::Acquire, Ordering::SeqCst)
        }
    }

    /// Reader `reader` takes the current snapshot. Each reader index must be used by one thread at a
    /// time and hold at most one guard. `None` for an index out of range.
    pub fn acquire(&self, reader: usize) -> Option<Guard<'_, T>> {
        let hazard = self.hazards.get(reader)?;
        let (load, check) = self.orders();
        loop {
            let s = self.current.load(load);
            hazard.0.store(s, check);
            if self.current.load(check) == s {
                // SAFETY: slot `s` was announced before the validating load saw it current, so the
                // writer will not write it until this hazard is cleared (KR-280).
                let value = unsafe { &*self.slots[s as usize].0.get() };
                return Some(Guard { hazard, value });
            }
        }
    }

    /// The writer publishes the next snapshot. **One writer only** (KR-280); wait-free: one scan of
    /// the hazards.
    pub fn publish(&self, next: T) {
        let cur = self.current.load(Ordering::Relaxed); // only the writer stores it
        let f = if self.fault == Fault::SkipHazardScan {
            (cur as usize + 1) % self.slots.len()
        } else {
            self.free_slot(cur)
        };
        // SAFETY: no reader has slot `f` announced, and a reader that announces it later fails its
        // validation because `current` does not name `f` (KR-280).
        unsafe { *self.slots[f].0.get() = next };
        let store = if self.fault == Fault::RelaxedPublish {
            Ordering::Relaxed
        } else {
            Ordering::SeqCst
        };
        self.current.store(f as u32, store);
    }

    fn free_slot(&self, cur: u32) -> usize {
        let mut held = [false; MAX_READERS + 2];
        held[cur as usize] = true;
        let (_, check) = self.orders();
        for h in &self.hazards {
            let s = h.0.load(check);
            if s != NONE_SLOT {
                held[s as usize] = true;
            }
        }
        (0..self.slots.len())
            .find(|&k| !held[k])
            .expect("R + 2 slots always leave one free (pigeonhole)")
    }
}

// --- the hedge snapshot (KR-283, KR-287) ------------------------------------------------------------

pub const CHECK_SEED: u64 = 0x9E3779B97F4A7C15;
pub const CHECK_MUL: u64 = 0x94D049BB133111EB;

/// KR-287: `c = rotl64(c xor w, 27) * MUL mod 2^64` from `SEED`.
pub fn checksum(words: &[u64]) -> u64 {
    words.iter().fold(CHECK_SEED, |c, &w| {
        (c ^ w).rotate_left(27).wrapping_mul(CHECK_MUL)
    })
}

/// One snapshot (72 bytes): version, logical event number, cumulative parallel shift, the writer's
/// five results and the checksum.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct HedgeSnapshot {
    pub version: u64,
    pub as_of: u64,
    pub shift: f64,
    pub estimate_pnl: f64,
    pub bound: f64,
    pub book_delta: f64,
    pub hedge_unit_delta: f64,
    pub hedge_notional: f64,
    pub check: u64,
}

impl HedgeSnapshot {
    pub fn words(&self) -> [u64; 8] {
        [
            self.version,
            self.as_of,
            self.shift.to_bits(),
            self.estimate_pnl.to_bits(),
            self.bound.to_bits(),
            self.book_delta.to_bits(),
            self.hedge_unit_delta.to_bits(),
            self.hedge_notional.to_bits(),
        ]
    }

    /// The reader's torn-read test.
    pub fn intact(&self) -> bool {
        checksum(&self.words()) == self.check
    }
}

/// The zero-coupon hedge instrument: one unit pays 1 at `maturity`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct HedgeInstrument {
    pub maturity: f64,
    pub yield_: f64,
}

/// `fsum(-T * (N * exp(-(y + h) * T)))`: the book's parallel delta at the shifted yields (KR-283).
pub fn book_delta(positions: &[ZeroPosition], shift: f64) -> f64 {
    fsum(
        positions
            .iter()
            .map(|p| -p.maturity * (p.notional * (-(p.yield_ + shift) * p.maturity).exp())),
    )
}

/// `-T_H * exp(-(y_H + h) * T_H)`: the delta of one unit of the hedge zero (KR-283).
pub fn hedge_unit_delta(hedge: &HedgeInstrument, shift: f64) -> f64 {
    -hedge.maturity * (-(hedge.yield_ + shift) * hedge.maturity).exp()
}

/// The writer's per-publish computation: direct library calls only (KR-283, KR-284).
pub fn build(
    version: u64,
    as_of: u64,
    positions: &[ZeroPosition],
    hedge: &HedgeInstrument,
    shift: f64,
) -> Result<HedgeSnapshot> {
    let risk = stage_k::delta_gamma_bound(positions, shift)?;
    let d = book_delta(positions, shift);
    let u = hedge_unit_delta(hedge, shift);
    let mut s = HedgeSnapshot {
        version,
        as_of,
        shift,
        estimate_pnl: risk.estimate_pnl,
        bound: risk.bound,
        book_delta: d,
        hedge_unit_delta: u,
        hedge_notional: -d / u,
        check: 0,
    };
    s.check = checksum(&s.words());
    Ok(s)
}

/// KR-287: 0 for version 0, else `((k * 7919) mod 401 - 200) * 5e-5`.
pub fn scenario_shift(k: u64) -> f64 {
    if k == 0 {
        0.0
    } else {
        (((k * 7919) % 401) as i64 - 200) as f64 * 5e-5
    }
}
