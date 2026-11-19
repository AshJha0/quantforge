#pragma once
// H-9 workload R2 and row L7 helpers for the bench harness (specifications/09-microstructure/low-latency-book.md
// items 2a and 2b; low-latency-targets.md sections (g) and (h)). Everything here runs outside the timed region,
// except per_level_ns, which turns one measured apply time into the L7 sample after the clock has been read.
//
// Checkpoint file (written by benchmarks/h9/build_r2.py): "QFH9C001", u64 checkpoints, u64 levels; records of 16
// bytes (u32 lo, u16 n_bids, u16 n_asks, u32 first level, u32 hi); then levels (i64 price ticks, i64 lots), bids
// descending then asks ascending. A row is compared with the book after each message index in [lo, hi]: lo is the
// last book message received strictly before the row's millisecond, hi the last one at or before it; the order of
// messages inside one millisecond is not recorded (benchmarks/h9/check_r2.py), so the row passes at any of them.
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

#include "quantforge/core/fast_book.hpp"

namespace quantforge::lowlat::r2 {

inline constexpr std::uint8_t flag_venue_checksum = 4;  // venue checksum carried, checked outside the timed apply

struct Checkpoint {
    std::uint32_t lo;
    std::uint16_t n_bids;
    std::uint16_t n_asks;
    std::uint32_t first;
    std::uint32_t hi;
};
static_assert(sizeof(Checkpoint) == 16);

struct Checkpoints {
    std::vector<Checkpoint> rows;
    std::vector<Level> levels;
};

inline bool read_checkpoints(const char* path, Checkpoints& out) {
    FILE* f = std::fopen(path, "rb");
    if (!f) return false;
    char magic[8];
    std::uint64_t n[2];
    bool ok = std::fread(magic, 1, 8, f) == 8 && std::memcmp(magic, "QFH9C001", 8) == 0 && std::fread(n, 8, 2, f) == 2;
    if (ok) {
        out.rows.resize(n[0]);
        out.levels.resize(n[1]);
        ok = std::fread(out.rows.data(), sizeof(Checkpoint), n[0], f) == n[0] &&
             std::fread(out.levels.data(), sizeof(Level), n[1], f) == n[1];
    }
    std::fclose(f);
    for (const Checkpoint& c : out.rows) ok = ok && c.lo <= c.hi && std::uint64_t(c.first) + c.n_bids + c.n_asks <= n[1];
    return ok;
}

/// L7 sample: apply time divided by the message's levels, rounded up to a whole nanosecond (item 2b). n >= 1.
inline std::uint64_t per_level_ns(std::uint64_t dt, std::uint32_t n) { return (dt + n - 1) / n; }

/// 0: the book equals the row, all its levels a side; 1: the first 10 a side equal, a deeper level differs;
/// 2: the first 10 differ. A side compares our best n levels with the row's n (micro.book.rebuild's checkpoint rule).
inline int compare(const Book& b, const Level* bids, std::size_t nb, const Level* asks, std::size_t na, Level* scratch) {
    int worst = 0;
    for (const bool bid : {true, false}) {
        const Level* want = bid ? bids : asks;
        const std::size_t n = bid ? nb : na;
        const std::size_t got = b.top(bid, n, scratch);
        const std::size_t k10 = std::min<std::size_t>(10, n);
        bool top_ok = got >= k10;
        for (std::size_t k = 0; top_ok && k < k10; ++k) top_ok = scratch[k].px == want[k].px && scratch[k].qty == want[k].qty;
        if (!top_ok) return 2;
        bool all_ok = got == n;
        for (std::size_t k = k10; all_ok && k < n; ++k) all_ok = scratch[k].px == want[k].px && scratch[k].qty == want[k].qty;
        if (!all_ok) worst = 1;
    }
    return worst;
}

/// Form A counts of low-latency-targets.md (g).
struct Counts {
    std::int64_t checksum_checked = 0, checksum_failed = 0, checkpoint_checked = 0, checkpoint_failed_top10 = 0,
                 checkpoint_failed_below10 = 0, matched_at_lo = 0, matched_at_hi = 0, matched_only_inside_tie = 0,
                 rows_with_tie = 0;
};

/// Replays the stream once on a fresh book (outside any timing): the venue checksum after every book message that
/// carries one, and every checkpoint row over its [lo, hi] range.
inline Counts verify_form_a(const std::vector<Msg>& msgs, const std::vector<Level>& levels, const Checkpoints& cps,
                            std::size_t depth) {
    Book b(depth);
    Counts c;
    std::vector<Level> scratch(std::max<std::size_t>(depth, 1024));
    std::vector<int> best(cps.rows.size(), 3);
    std::vector<char> at_lo(cps.rows.size(), 0), at_hi(cps.rows.size(), 0);
    std::size_t next = 0;           // first row whose range has not started
    std::vector<std::size_t> live;  // rows whose range holds the current message
    for (std::size_t i = 0; i < msgs.size(); ++i) {
        const Msg& m = msgs[i];
        b.apply(m, levels.data());
        if (m.type != MsgType::Trade && (m.flags & flag_venue_checksum)) {
            ++c.checksum_checked;
            if (b.checksum() != m.checksum) ++c.checksum_failed;
        }
        while (next < cps.rows.size() && cps.rows[next].lo <= i) live.push_back(next++);
        for (std::size_t k = 0; k < live.size();) {
            const std::size_t j = live[k];
            const Checkpoint& r = cps.rows[j];
            if (i >= r.lo) {
                const Level* lb = cps.levels.data() + r.first;
                const int res = compare(b, lb, r.n_bids, lb + r.n_bids, r.n_asks, scratch.data());
                best[j] = std::min(best[j], res);
                if (res == 0 && i == r.lo) at_lo[j] = 1;
                if (res == 0 && i == r.hi) at_hi[j] = 1;
            }
            if (i >= r.hi) {
                live[k] = live.back();
                live.pop_back();
            } else {
                ++k;
            }
        }
    }
    for (std::size_t j = 0; j < cps.rows.size(); ++j) {
        ++c.checkpoint_checked;
        c.rows_with_tie += cps.rows[j].hi > cps.rows[j].lo;
        if (best[j] == 0) {
            c.matched_at_lo += at_lo[j];
            c.matched_at_hi += at_hi[j];
            c.matched_only_inside_tie += !at_lo[j] && !at_hi[j];
        } else if (best[j] == 1) {
            ++c.checkpoint_failed_below10;
        } else {
            ++c.checkpoint_failed_top10;  // includes a row whose range lies beyond the stream (never compared)
        }
    }
    return c;
}

}  // namespace quantforge::lowlat::r2
