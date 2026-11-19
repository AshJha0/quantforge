#pragma once
// H-9 low-latency MBP book (specifications/09-microstructure/low-latency-book.md, rulings HR-18 to HR-24).
// The same operation as micro.book.rebuild (order-book.md), built for speed: prices are integer ticks and
// quantities integer lots at the pair's precision (HR-20), every buffer is sized at construction, and the
// per-message path (apply) and the queries never allocate. The one exception is stated: a single message that
// carries more levels than the side's spare capacity (about 7 x depth) grows the buffer; the bench counts it.
//
// Layout. Each side is a sorted array of (key, qty) with the best level at the high end, key = price for bids
// and -price for asks, so "better" is always "larger key". Truncation drops levels from the low end by moving
// one index (O(1)); inserts and deletes near the touch shift only the few levels between the price and the
// touch (O(L) expected, HR-19); a lookup first scans the 8 levels next to the touch and otherwise binary-searches
// (O(log N)). qty_at is O(1): a direct-mapped index on the price grid (slot = price mod 1024 ticks) holds one
// present price per slot with its quantity and the count of present prices mapping there; a query reads the slot
// and only when two present prices more than 1,024 ticks apart share it falls back to the sorted search (counted).
// The book keeps its top of book in a cache refreshed at the end of every apply, so best_bid/best_ask are one load.
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <vector>

namespace quantforge::lowlat {

/// A price level in fixed point: price in ticks, quantity in lots (10^-qty_decimals).
struct Level {
    std::int64_t px;
    std::int64_t qty;
};

enum class MsgType : std::uint8_t { Snapshot = 0, Update = 1, Gap = 2, Trade = 3 };

inline constexpr std::uint8_t flag_checksum = 1;     // `checksum` is present
inline constexpr std::uint8_t flag_resubscribe = 2;  // snapshot marked as a resubscribe (order-book.md step 5)

/// One pre-decoded message, fixed size (16 bytes). Its levels are levels[first, first + n_bids + n_asks) of
/// the stream's flat level array, bids first. A trade carries one level (price, size) and changes nothing.
struct Msg {
    MsgType type;
    std::uint8_t flags;
    std::uint16_t n_bids;
    std::uint16_t n_asks;
    std::uint16_t reserved;
    std::uint32_t checksum;
    std::uint32_t first;
};
static_assert(sizeof(Msg) == 16);
static_assert(sizeof(Level) == 16);

enum class EventKind : std::uint8_t { ChecksumFail, Crossed, Locked, Gap, UpdateBeforeSnapshot };

struct Event {
    std::int64_t i;
    EventKind kind;
};

/// The counters of order-book.md (checkpoint counters are always 0 here: form A checkpoints are compared by
/// the caller outside the timed region), plus `trades`, which micro.book.rebuild does not see.
struct Stats {
    std::int64_t messages = 0, snapshots = 0, updates = 0, level_changes = 0, deletes_of_absent_level = 0,
                 truncated_levels = 0, checksum_checked = 0, checksum_failed = 0, crossed = 0, locked = 0,
                 gaps = 0, resyncs = 0, trades = 0;
};

/// IEEE 802.3 CRC32 (zlib.crc32), table-driven.
namespace detail {
constexpr std::array<std::uint32_t, 256> crc_table() {
    std::array<std::uint32_t, 256> t{};
    for (std::uint32_t n = 0; n < 256; ++n) {
        std::uint32_t c = n;
        for (int k = 0; k < 8; ++k) c = (c & 1U) ? 0xEDB88320U ^ (c >> 1) : c >> 1;
        t[n] = c;
    }
    return t;
}
inline constexpr std::array<std::uint32_t, 256> crc = crc_table();

// Decimal digits of v > 0 with no leading zeros ([KR-CRC] component of a fixed-point value); "0" for 0.
inline std::size_t put_digits(char* out, std::int64_t v) {
    char tmp[20];
    std::size_t n = 0;
    auto u = static_cast<std::uint64_t>(v);
    do {
        tmp[n++] = static_cast<char>('0' + u % 10);
        u /= 10;
    } while (u != 0);
    for (std::size_t k = 0; k < n; ++k) out[k] = tmp[n - 1 - k];
    return n;
}
}  // namespace detail

inline std::uint32_t crc32(const char* p, std::size_t n) {
    std::uint32_t c = 0xFFFFFFFFU;
    for (std::size_t k = 0; k < n; ++k) c = detail::crc[(c ^ static_cast<unsigned char>(p[k])) & 0xFFU] ^ (c >> 8);
    return c ^ 0xFFFFFFFFU;
}

/// One side of the book. See the layout note at the top of the file.
class Side {
public:
    struct Entry {
        std::int64_t key;
        std::int64_t qty;
    };

    static constexpr std::size_t slots = 1024;  // direct index on the tick grid; a power of two
    static constexpr std::int64_t no_px = std::numeric_limits<std::int64_t>::min();

    void init(bool bid, std::size_t cap) {
        bid_ = bid;
        buf_.assign(cap, Entry{0, 0});
        index_.assign(slots, Slot{no_px, 0});
        counts_.assign(slots, 0);
        lo_ = hi_ = buf_.size() / 2;
    }
    void clear() {
        for (std::size_t k = lo_; k < hi_; ++k) unindex(to_px(buf_[k].key));
        lo_ = hi_ = buf_.size() / 2;
    }
    std::size_t size() const { return hi_ - lo_; }
    bool empty() const { return hi_ == lo_; }
    std::size_t capacity() const { return buf_.size(); }
    std::int64_t grows() const { return grows_; }
    std::int64_t far_lookups() const { return far_; }
    std::int64_t index_fallbacks() const { return index_fallbacks_; }

    /// Best price and quantity; false when the side is empty (the empty marker, not an error).
    bool best(Level& out) const {
        if (empty()) return false;
        out = to_level(buf_[hi_ - 1]);
        return true;
    }

    std::int64_t qty_at(std::int64_t px) const {
        const std::size_t i = slot(px);
        if (counts_[i] == 0) return 0;
        const Slot& s = index_[i];
        if (s.px == px) return s.qty;
        ++index_fallbacks_;
        const std::int64_t key = to_key(px);
        const std::size_t pos = lower_bound(key);
        return (pos < hi_ && buf_[pos].key == key) ? buf_[pos].qty : 0;
    }

    /// The best n levels into out[0..n); returns how many were written.
    std::size_t top(std::size_t n, Level* out) const {
        const std::size_t m = std::min(n, size());
        for (std::size_t k = 0; k < m; ++k) out[k] = to_level(buf_[hi_ - 1 - k]);
        return m;
    }

    /// Replace (or insert) the quantity at px.
    void set(std::int64_t px, std::int64_t qty) {
        const std::int64_t key = to_key(px);
        std::size_t pos = lower_bound(key);
        if (pos < hi_ && buf_[pos].key == key) {
            buf_[pos].qty = qty;
            Slot& s = index_[slot(px)];
            if (s.px == px) s.qty = qty;
            return;
        }
        {
            const std::size_t i = slot(px);
            Slot& s = index_[i];
            if (counts_[i]++ == 0 || s.px == no_px) s.px = px, s.qty = qty;
        }
        if (lo_ == 0 || hi_ == buf_.size()) pos = recenter(pos);
        Entry* b = buf_.data();
        if (hi_ - pos <= pos - lo_) {  // shift the touch side up by one
            std::memmove(b + pos + 1, b + pos, (hi_ - pos) * sizeof(Entry));
            ++hi_;
        } else {  // shift the deep side down by one
            std::memmove(b + lo_ - 1, b + lo_, (pos - lo_) * sizeof(Entry));
            --lo_;
            --pos;
        }
        b[pos] = Entry{key, qty};
    }

    /// Remove px; false when it was absent.
    bool erase(std::int64_t px) {
        const std::int64_t key = to_key(px);
        const std::size_t pos = lower_bound(key);
        if (pos >= hi_ || buf_[pos].key != key) return false;
        unindex(px);
        Entry* b = buf_.data();
        if (hi_ - pos - 1 <= pos - lo_) {
            std::memmove(b + pos, b + pos + 1, (hi_ - pos - 1) * sizeof(Entry));
            --hi_;
        } else {
            std::memmove(b + lo_ + 1, b + lo_, (pos - lo_) * sizeof(Entry));
            ++lo_;
        }
        return true;
    }

    /// Drop the worst levels beyond depth; returns how many.
    std::int64_t truncate(std::size_t depth) {
        const std::size_t n = size();
        if (n <= depth) return 0;
        for (std::size_t k = lo_; k < lo_ + (n - depth); ++k) unindex(to_px(buf_[k].key));
        lo_ += n - depth;
        return static_cast<std::int64_t>(n - depth);
    }

private:
    struct Slot {
        std::int64_t px;  // one present price mapping here (no_px when that one left and others remain)
        std::int64_t qty;
    };
    static std::size_t slot(std::int64_t px) { return static_cast<std::size_t>(px) & (slots - 1); }
    void unindex(std::int64_t px) {
        const std::size_t i = slot(px);
        Slot& s = index_[i];
        if (--counts_[i] == 0 || s.px == px) s.px = no_px;
    }
    std::int64_t to_key(std::int64_t px) const { return bid_ ? px : -px; }
    std::int64_t to_px(std::int64_t key) const { return bid_ ? key : -key; }
    Level to_level(const Entry& e) const { return Level{bid_ ? e.key : -e.key, e.qty}; }

    // First index in [lo, hi) whose key >= key. Scans the 8 levels next to the touch first (HR-19).
    std::size_t lower_bound(std::int64_t key) const {
        const Entry* b = buf_.data();
        std::size_t j = hi_;
        const std::size_t stop = hi_ - std::min<std::size_t>(8, hi_ - lo_);
        while (j > stop && b[j - 1].key >= key) --j;
        if (j == lo_ || b[j - 1].key < key) return j;
        ++far_;
        std::size_t a = lo_, z = j - 1;  // answer in [a, z]; b[z].key >= key
        while (a < z) {
            const std::size_t mid = a + (z - a) / 2;
            if (b[mid].key < key) a = mid + 1;
            else z = mid;
        }
        return a;
    }

    // Move the levels to the middle of the buffer (growing it if it is full); returns pos's new index.
    std::size_t recenter(std::size_t pos) {
        const std::size_t n = size();
        if (n + 2 > buf_.size()) {
            ++grows_;  // the stated allocating path: one message with more levels than the spare capacity
            std::vector<Entry> bigger(buf_.size() * 2, Entry{0, 0});
            const std::size_t nlo = (bigger.size() - n) / 2;
            std::memcpy(bigger.data() + nlo, buf_.data() + lo_, n * sizeof(Entry));
            buf_.swap(bigger);
            pos = pos - lo_ + nlo;
            lo_ = nlo;
            hi_ = nlo + n;
            return pos;
        }
        const std::size_t nlo = (buf_.size() - n) / 2;
        std::memmove(buf_.data() + nlo, buf_.data() + lo_, n * sizeof(Entry));
        pos = pos - lo_ + nlo;
        lo_ = nlo;
        hi_ = nlo + n;
        return pos;
    }

    std::vector<Entry> buf_;
    std::vector<Slot> index_;
    std::vector<std::uint32_t> counts_;  // present prices per slot, apart so an absent query reads 4 KB
    mutable std::int64_t index_fallbacks_ = 0;
    std::size_t lo_ = 0, hi_ = 0;
    bool bid_ = true;
    std::int64_t grows_ = 0;
    mutable std::int64_t far_ = 0;
};

/// The book. Construct once (this allocates); apply() and the queries do not allocate afterwards.
class Book {
public:
    static constexpr std::size_t max_events = 10'000;

    explicit Book(std::size_t depth) : depth_(depth) {
        const std::size_t cap = 8 * depth + 64;
        bids_.init(true, cap);
        asks_.init(false, cap);
        events_.reserve(max_events);
    }

    void apply(const Msg& m, const Level* levels) {
        apply_book(m, levels);
        has_bid_ = bids_.best(bid_);
        has_ask_ = asks_.best(ask_);
    }

    bool best_bid(Level& out) const {
        out = bid_;
        return has_bid_;
    }
    bool best_ask(Level& out) const {
        out = ask_;
        return has_ask_;
    }

private:
    void apply_book(const Msg& m, const Level* levels) {
        switch (m.type) {
            case MsgType::Trade: ++st_.trades; return;
            case MsgType::Gap:
                ++st_.gaps;
                bids_.clear();
                asks_.clear();
                live_ = false;
                event(seq_++, EventKind::Gap);
                return;
            default: break;
        }
        const std::int64_t i = seq_++;
        ++st_.messages;
        const Level* lb = levels + m.first;
        const Level* la = lb + m.n_bids;
        if (m.type == MsgType::Snapshot) {
            ++st_.snapshots;
            if ((m.flags & flag_resubscribe) && pending_resync_) ++st_.resyncs;
            pending_resync_ = false;
            bids_.clear();
            asks_.clear();
            for (std::uint16_t k = 0; k < m.n_bids; ++k)
                if (lb[k].qty != 0) bids_.set(lb[k].px, lb[k].qty);
            for (std::uint16_t k = 0; k < m.n_asks; ++k)
                if (la[k].qty != 0) asks_.set(la[k].px, la[k].qty);
            live_ = true;
        } else {
            ++st_.updates;
            if (!live_) {
                event(i, EventKind::UpdateBeforeSnapshot);
                return;
            }
            update_side(bids_, lb, m.n_bids);
            update_side(asks_, la, m.n_asks);
        }
        st_.truncated_levels += bids_.truncate(depth_) + asks_.truncate(depth_);
        if (m.flags & flag_checksum) {
            ++st_.checksum_checked;
            if (checksum() != m.checksum) {
                ++st_.checksum_failed;
                pending_resync_ = true;
                event(i, EventKind::ChecksumFail);
            }
        }
        Level b{}, a{};
        if (bids_.best(b) && asks_.best(a)) {
            if (a.px < b.px) {
                ++st_.crossed;
                event(i, EventKind::Crossed);
            } else if (a.px == b.px) {
                ++st_.locked;
                event(i, EventKind::Locked);
            }
        }
    }


public:
    std::int64_t qty_at(bool bid, std::int64_t px) const { return bid ? bids_.qty_at(px) : asks_.qty_at(px); }
    std::size_t top(bool bid, std::size_t n, Level* out) const { return bid ? bids_.top(n, out) : asks_.top(n, out); }

    /// [KR-CRC] CRC32 of the top 10 asks (ascending) then the top 10 bids (descending); no allocation.
    std::uint32_t checksum() const {
        char s[20 * 2 * 20];
        std::size_t n = 0;
        Level lv[10];
        for (const bool bid : {false, true}) {
            const std::size_t m = top(bid, 10, lv);
            for (std::size_t k = 0; k < m; ++k) {
                n += detail::put_digits(s + n, lv[k].px);
                n += detail::put_digits(s + n, lv[k].qty);
            }
        }
        return crc32(s, n);
    }

    const Stats& stats() const { return st_; }
    const std::vector<Event>& events() const { return events_; }
    std::int64_t events_omitted() const { return omitted_; }
    std::size_t depth() const { return depth_; }
    /// Buffer growths (the allocating path) and lookups that left the 8-level touch window, both sides.
    std::int64_t grows() const { return bids_.grows() + asks_.grows(); }
    std::int64_t far_lookups() const { return bids_.far_lookups() + asks_.far_lookups(); }
    /// qty_at calls that met a shared index slot and used the sorted search.
    std::int64_t index_fallbacks() const { return bids_.index_fallbacks() + asks_.index_fallbacks(); }

private:
    void update_side(Side& s, const Level* l, std::uint16_t n) {
        for (std::uint16_t k = 0; k < n; ++k) {
            ++st_.level_changes;
            if (l[k].qty == 0) {
                if (!s.erase(l[k].px)) ++st_.deletes_of_absent_level;
            } else {
                s.set(l[k].px, l[k].qty);
            }
        }
    }
    void event(std::int64_t i, EventKind k) {
        if (events_.size() < max_events) events_.push_back(Event{i, k});
        else ++omitted_;
    }

    std::size_t depth_;
    Side bids_, asks_;
    Stats st_{};
    Level bid_{}, ask_{};
    bool has_bid_ = false, has_ask_ = false;
    bool live_ = false, pending_resync_ = false;
    std::int64_t seq_ = 0, omitted_ = 0;
    std::vector<Event> events_;
};

}  // namespace quantforge::lowlat
