//! H-9 low-latency MBP book (`specifications/09-microstructure/low-latency-book.md`, rulings HR-18 to HR-24).
//!
//! The same operation as `micro.book.rebuild` (`order_book.rs`), built for speed and mirroring the C++ port
//! (`cpp26/include/quantforge/core/fast_book.hpp`): prices are integer ticks and quantities integer lots
//! (HR-20); every buffer is sized at construction and `apply` and the queries never allocate. The one stated
//! exception: a single message carrying more levels than a side's spare capacity (about 7 x depth) grows the
//! buffer, counted in `grows`.
//!
//! Each side is a sorted array of (key, qty) with the best level at the high end (key = price for bids, -price
//! for asks). Truncation moves one index (O(1)); inserts and deletes near the touch shift only the levels
//! between the price and the touch (O(L) expected, HR-19); a lookup scans the 8 levels next to the touch and
//! otherwise binary-searches. `qty_at` is O(log N): a sorted array keeps the book in a few cache lines and
//! needs no hash table (the spec allows O(log N) with the reason stated).

/// A price level in fixed point: price in ticks, quantity in lots.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
#[repr(C)]
pub struct Level {
    pub px: i64,
    pub qty: i64,
}

/// Message kinds; the values match the C++ `MsgType` so both read the same workload file.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
#[repr(u8)]
pub enum MsgType {
    #[default]
    Snapshot = 0,
    Update = 1,
    Gap = 2,
    Trade = 3,
}

pub const FLAG_CHECKSUM: u8 = 1;
pub const FLAG_RESUBSCRIBE: u8 = 2;

/// One pre-decoded message (16 bytes, the C++ layout). Its levels are `levels[first..first + n_bids + n_asks]`,
/// bids first. `reserved` is free for the caller (the harness stores the op kind there).
#[derive(Clone, Copy, Debug, Default)]
#[repr(C)]
pub struct Msg {
    pub kind: MsgType,
    pub flags: u8,
    pub n_bids: u16,
    pub n_asks: u16,
    pub reserved: u16,
    pub checksum: u32,
    pub first: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum EventKind {
    ChecksumFail,
    Crossed,
    Locked,
    Gap,
    UpdateBeforeSnapshot,
}

impl EventKind {
    pub fn name(self) -> &'static str {
        match self {
            EventKind::ChecksumFail => "CHECKSUM_FAIL",
            EventKind::Crossed => "CROSSED",
            EventKind::Locked => "LOCKED",
            EventKind::Gap => "GAP",
            EventKind::UpdateBeforeSnapshot => "UPDATE_BEFORE_SNAPSHOT",
        }
    }
}

/// The counters of `order-book.md` (checkpoint counters stay with the caller) plus `trades`.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Stats {
    pub messages: i64,
    pub snapshots: i64,
    pub updates: i64,
    pub level_changes: i64,
    pub deletes_of_absent_level: i64,
    pub truncated_levels: i64,
    pub checksum_checked: i64,
    pub checksum_failed: i64,
    pub crossed: i64,
    pub locked: i64,
    pub gaps: i64,
    pub resyncs: i64,
    pub trades: i64,
}

const fn crc_table() -> [u32; 256] {
    let mut t = [0u32; 256];
    let mut n = 0;
    while n < 256 {
        let mut c = n as u32;
        let mut k = 0;
        while k < 8 {
            c = if c & 1 == 1 {
                0xEDB8_8320 ^ (c >> 1)
            } else {
                c >> 1
            };
            k += 1;
        }
        t[n] = c;
        n += 1;
    }
    t
}
static CRC: [u32; 256] = crc_table();

/// IEEE 802.3 CRC32 (zlib.crc32).
pub fn crc32(bytes: &[u8]) -> u32 {
    let mut c = 0xFFFF_FFFFu32;
    for &b in bytes {
        c = CRC[((c ^ u32::from(b)) & 0xFF) as usize] ^ (c >> 8);
    }
    c ^ 0xFFFF_FFFF
}

fn put_digits(out: &mut [u8], v: i64) -> usize {
    let mut tmp = [0u8; 20];
    let mut n = 0;
    let mut u = v as u64;
    loop {
        tmp[n] = b'0' + (u % 10) as u8;
        n += 1;
        u /= 10;
        if u == 0 {
            break;
        }
    }
    for k in 0..n {
        out[k] = tmp[n - 1 - k];
    }
    n
}

#[derive(Clone, Copy, Default)]
struct Entry {
    key: i64,
    qty: i64,
}

/// One side of the book.
pub struct Side {
    buf: Vec<Entry>,
    lo: usize,
    hi: usize,
    bid: bool,
    grows: i64,
    far: std::cell::Cell<i64>,
}

impl Side {
    fn new(bid: bool, cap: usize) -> Side {
        Side {
            buf: vec![Entry::default(); cap],
            lo: cap / 2,
            hi: cap / 2,
            bid,
            grows: 0,
            far: std::cell::Cell::new(0),
        }
    }
    fn clear(&mut self) {
        self.lo = self.buf.len() / 2;
        self.hi = self.lo;
    }
    pub fn len(&self) -> usize {
        self.hi - self.lo
    }
    pub fn is_empty(&self) -> bool {
        self.hi == self.lo
    }
    fn key(&self, px: i64) -> i64 {
        if self.bid { px } else { -px }
    }
    fn level(&self, e: Entry) -> Level {
        Level {
            px: if self.bid { e.key } else { -e.key },
            qty: e.qty,
        }
    }
    pub fn best(&self) -> Option<Level> {
        (!self.is_empty()).then(|| self.level(self.buf[self.hi - 1]))
    }
    pub fn qty_at(&self, px: i64) -> i64 {
        let key = self.key(px);
        let pos = self.lower_bound(key);
        if pos < self.hi && self.buf[pos].key == key {
            self.buf[pos].qty
        } else {
            0
        }
    }
    pub fn top(&self, out: &mut [Level]) -> usize {
        let m = out.len().min(self.len());
        for (k, slot) in out.iter_mut().take(m).enumerate() {
            *slot = self.level(self.buf[self.hi - 1 - k]);
        }
        m
    }
    fn lower_bound(&self, key: i64) -> usize {
        let b = &self.buf;
        let mut j = self.hi;
        let stop = self.hi - 8.min(self.hi - self.lo);
        while j > stop && b[j - 1].key >= key {
            j -= 1;
        }
        if j == self.lo || b[j - 1].key < key {
            return j;
        }
        self.far.set(self.far.get() + 1);
        let (mut a, mut z) = (self.lo, j - 1);
        while a < z {
            let mid = a + (z - a) / 2;
            if b[mid].key < key {
                a = mid + 1;
            } else {
                z = mid;
            }
        }
        a
    }
    fn recenter(&mut self, pos: usize) -> usize {
        let n = self.len();
        if n + 2 > self.buf.len() {
            self.grows += 1;
            let mut bigger = vec![Entry::default(); self.buf.len() * 2];
            let nlo = (bigger.len() - n) / 2;
            bigger[nlo..nlo + n].copy_from_slice(&self.buf[self.lo..self.hi]);
            self.buf = bigger;
            let p = pos - self.lo + nlo;
            self.lo = nlo;
            self.hi = nlo + n;
            return p;
        }
        let nlo = (self.buf.len() - n) / 2;
        self.buf.copy_within(self.lo..self.hi, nlo);
        let p = pos - self.lo + nlo;
        self.lo = nlo;
        self.hi = nlo + n;
        p
    }
    fn set(&mut self, px: i64, qty: i64) {
        let key = self.key(px);
        let mut pos = self.lower_bound(key);
        if pos < self.hi && self.buf[pos].key == key {
            self.buf[pos].qty = qty;
            return;
        }
        if self.lo == 0 || self.hi == self.buf.len() {
            pos = self.recenter(pos);
        }
        if self.hi - pos <= pos - self.lo {
            self.buf.copy_within(pos..self.hi, pos + 1);
            self.hi += 1;
        } else {
            self.buf.copy_within(self.lo..pos, self.lo - 1);
            self.lo -= 1;
            pos -= 1;
        }
        self.buf[pos] = Entry { key, qty };
    }
    fn erase(&mut self, px: i64) -> bool {
        let key = self.key(px);
        let pos = self.lower_bound(key);
        if pos >= self.hi || self.buf[pos].key != key {
            return false;
        }
        if self.hi - pos - 1 <= pos - self.lo {
            self.buf.copy_within(pos + 1..self.hi, pos);
            self.hi -= 1;
        } else {
            self.buf.copy_within(self.lo..pos, self.lo + 1);
            self.lo += 1;
        }
        true
    }
    fn truncate(&mut self, depth: usize) -> i64 {
        let n = self.len();
        if n <= depth {
            return 0;
        }
        self.lo += n - depth;
        (n - depth) as i64
    }
}

pub const MAX_EVENTS: usize = 10_000;

/// The book. `new` allocates; `apply` and the queries do not.
pub struct Book {
    depth: usize,
    bids: Side,
    asks: Side,
    st: Stats,
    live: bool,
    pending_resync: bool,
    seq: i64,
    omitted: i64,
    events: Vec<(i64, EventKind)>,
}

impl Book {
    pub fn new(depth: usize) -> Book {
        let cap = 8 * depth + 64;
        Book {
            depth,
            bids: Side::new(true, cap),
            asks: Side::new(false, cap),
            st: Stats::default(),
            live: false,
            pending_resync: false,
            seq: 0,
            omitted: 0,
            events: Vec::with_capacity(MAX_EVENTS),
        }
    }

    fn event(&mut self, i: i64, k: EventKind) {
        if self.events.len() < MAX_EVENTS {
            self.events.push((i, k));
        } else {
            self.omitted += 1;
        }
    }

    fn update_side(side: &mut Side, st: &mut Stats, lv: &[Level]) {
        for l in lv {
            st.level_changes += 1;
            if l.qty == 0 {
                if !side.erase(l.px) {
                    st.deletes_of_absent_level += 1;
                }
            } else {
                side.set(l.px, l.qty);
            }
        }
    }

    pub fn apply(&mut self, m: &Msg, levels: &[Level]) {
        match m.kind {
            MsgType::Trade => {
                self.st.trades += 1;
                return;
            }
            MsgType::Gap => {
                self.st.gaps += 1;
                self.bids.clear();
                self.asks.clear();
                self.live = false;
                let i = self.seq;
                self.seq += 1;
                self.event(i, EventKind::Gap);
                return;
            }
            _ => {}
        }
        let i = self.seq;
        self.seq += 1;
        self.st.messages += 1;
        let f = m.first as usize;
        let nb = usize::from(m.n_bids);
        let lb = &levels[f..f + nb];
        let la = &levels[f + nb..f + nb + usize::from(m.n_asks)];
        if m.kind == MsgType::Snapshot {
            self.st.snapshots += 1;
            if m.flags & FLAG_RESUBSCRIBE != 0 && self.pending_resync {
                self.st.resyncs += 1;
            }
            self.pending_resync = false;
            self.bids.clear();
            self.asks.clear();
            for l in lb.iter().filter(|l| l.qty != 0) {
                self.bids.set(l.px, l.qty);
            }
            for l in la.iter().filter(|l| l.qty != 0) {
                self.asks.set(l.px, l.qty);
            }
            self.live = true;
        } else {
            self.st.updates += 1;
            if !self.live {
                self.event(i, EventKind::UpdateBeforeSnapshot);
                return;
            }
            Book::update_side(&mut self.bids, &mut self.st, lb);
            Book::update_side(&mut self.asks, &mut self.st, la);
        }
        self.st.truncated_levels += self.bids.truncate(self.depth) + self.asks.truncate(self.depth);
        if m.flags & FLAG_CHECKSUM != 0 {
            self.st.checksum_checked += 1;
            if self.checksum() != m.checksum {
                self.st.checksum_failed += 1;
                self.pending_resync = true;
                self.event(i, EventKind::ChecksumFail);
            }
        }
        if let (Some(b), Some(a)) = (self.bids.best(), self.asks.best()) {
            if a.px < b.px {
                self.st.crossed += 1;
                self.event(i, EventKind::Crossed);
            } else if a.px == b.px {
                self.st.locked += 1;
                self.event(i, EventKind::Locked);
            }
        }
    }

    pub fn best_bid(&self) -> Option<Level> {
        self.bids.best()
    }
    pub fn best_ask(&self) -> Option<Level> {
        self.asks.best()
    }
    pub fn qty_at(&self, bid: bool, px: i64) -> i64 {
        if bid {
            self.bids.qty_at(px)
        } else {
            self.asks.qty_at(px)
        }
    }
    /// The best `out.len()` levels of one side into `out`; returns how many were written.
    pub fn top(&self, bid: bool, out: &mut [Level]) -> usize {
        if bid {
            self.bids.top(out)
        } else {
            self.asks.top(out)
        }
    }

    /// [KR-CRC] CRC32 of the top 10 asks then the top 10 bids; no allocation.
    pub fn checksum(&self) -> u32 {
        let mut s = [0u8; 800];
        let mut n = 0;
        let mut lv = [Level::default(); 10];
        for bid in [false, true] {
            let m = self.top(bid, &mut lv);
            for l in &lv[..m] {
                n += put_digits(&mut s[n..], l.px);
                n += put_digits(&mut s[n..], l.qty);
            }
        }
        crc32(&s[..n])
    }

    pub fn stats(&self) -> &Stats {
        &self.st
    }
    pub fn events(&self) -> &[(i64, EventKind)] {
        &self.events
    }
    pub fn events_omitted(&self) -> i64 {
        self.omitted
    }
    pub fn depth(&self) -> usize {
        self.depth
    }
    pub fn grows(&self) -> i64 {
        self.bids.grows + self.asks.grows
    }
    pub fn far_lookups(&self) -> i64 {
        self.bids.far.get() + self.asks.far.get()
    }
}
