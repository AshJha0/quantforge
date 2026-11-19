// H-9 harness (specifications/09-microstructure/low-latency-book.md "Harness"; targets in low-latency-targets.md).
// Built only with -DQF_LOWLAT_BENCH=ON. No third-party code.
//
//   qf_lowlat_book gen  <file>                 write workload S (core.rng seed 20261117, 10,000,000 messages)
//   qf_lowlat_book run  <file> [runs] [out]    correctness pass, then `runs` (default 5) timed runs; JSON to out
//
// Per message: CLOCK_MONOTONIC read before and after Book::apply, recorded in an HDR-style histogram (3 significant
// digits, 1 ns to 10 s); per op kind and pooled. Replay is unpaced, so there is no coordinated-omission correction.
// Warm-up: the first 1,000,000 messages, unmeasured; then the allocation counter is reset. Every 1,000th measured
// message the six queries are timed the same way. Clock cost: 1,000,000 empty pairs, published, not subtracted.
// Batch timing (1,000 messages per sample, divided) is always recorded; the report says which is the headline.
// Allocation (H-9(b)): malloc/calloc/realloc are interposed on glibc (operator new goes through malloc), so every
// heap allocation in the process is counted; elsewhere operator new is replaced.
#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <map>
#include <new>
#include <string>
#include <vector>

#include "quantforge/core/fast_book.hpp"
#include "quantforge/core/rng.hpp"

namespace ll = quantforge::lowlat;

// ---------------------------------------------------------------- allocation counting
static std::atomic<long long> g_allocs{0};

#if defined(__GLIBC__) && defined(__linux__)
extern "C" {
void* __libc_malloc(std::size_t);
void* __libc_calloc(std::size_t, std::size_t);
void* __libc_realloc(void*, std::size_t);
void* malloc(std::size_t n) {
    g_allocs.fetch_add(1, std::memory_order_relaxed);
    return __libc_malloc(n);
}
void* calloc(std::size_t a, std::size_t b) {
    g_allocs.fetch_add(1, std::memory_order_relaxed);
    return __libc_calloc(a, b);
}
void* realloc(void* p, std::size_t n) {
    g_allocs.fetch_add(1, std::memory_order_relaxed);
    return __libc_realloc(p, n);
}
}
static const char* const alloc_method = "glibc malloc/calloc/realloc interposition (covers operator new)";
#else
void* operator new(std::size_t n) {
    g_allocs.fetch_add(1, std::memory_order_relaxed);
    if (void* p = std::malloc(n ? n : 1)) return p;
    throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
static const char* const alloc_method = "replaced global operator new";
#endif

namespace {

inline std::uint64_t now_ns() {
    timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return std::uint64_t(ts.tv_sec) * 1'000'000'000ULL + std::uint64_t(ts.tv_nsec);
}

// ---------------------------------------------------------------- HDR-style histogram
// HdrHistogram's bucket rule at 3 significant digits: 2048 sub-buckets, unit 1 ns, highest 10 s.
class Hist {
public:
    Hist() : counts_(index(10'000'000'000ULL) + 1, 0) {}
    void record(std::uint64_t v) {
        if (v > 10'000'000'000ULL) v = 10'000'000'000ULL;
        ++counts_[index(v)];
        ++n_;
        sum_ += v;
        mn_ = std::min(mn_, v);
        mx_ = std::max(mx_, v);
    }
    std::uint64_t count() const { return n_; }
    // HdrHistogram's getValueAtPercentile: the highest value equivalent to the bucket that reaches the rank.
    std::uint64_t pct(double p) const {
        if (n_ == 0) return 0;
        auto rank = std::uint64_t(p / 100.0 * double(n_) + 0.5);
        rank = std::max<std::uint64_t>(rank, 1);
        std::uint64_t acc = 0;
        for (std::size_t i = 0; i < counts_.size(); ++i) {
            acc += counts_[i];
            if (acc >= rank) return std::min(highest(i), mx_);
        }
        return mx_;
    }
    std::string json() const {
        char b[512];
        if (n_ == 0) return "{\"count\":0}";
        std::snprintf(b, sizeof b,
                      "{\"count\":%llu,\"min\":%llu,\"p50\":%llu,\"p90\":%llu,\"p99\":%llu,\"p99_9\":%llu,%s\"max\":%llu,"
                      "\"mean\":%.2f}",
                      (unsigned long long)n_, (unsigned long long)mn_, (unsigned long long)pct(50), (unsigned long long)pct(90),
                      (unsigned long long)pct(99), (unsigned long long)pct(99.9),
                      n_ >= 1'000'000 ? ("\"p99_99\":" + std::to_string(pct(99.99)) + ",").c_str() : "",
                      (unsigned long long)mx_, double(sum_) / double(n_));
        return b;
    }

private:
    static std::size_t index(std::uint64_t v) {
        const int bucket = 64 - std::countl_zero(v | 2047ULL) - 11;
        const std::uint64_t sub = v >> bucket;
        return (std::size_t(bucket) << 10) + std::size_t(sub);  // sub in [0, 2048) for bucket 0, [1024, 2048) after
    }
    static std::uint64_t highest(std::size_t i) {
        const std::size_t bucket = i >> 10 ? (i >> 10) : 0;
        std::size_t b = bucket, sub = i - (bucket << 10);
        if (b > 0 && sub < 1024) {  // belongs to the previous bucket's upper half
            --b;
            sub += 1024;
        }
        return ((std::uint64_t(sub) + 1) << b) - 1;
    }
    std::vector<std::uint64_t> counts_;
    std::uint64_t n_ = 0, sum_ = 0, mn_ = UINT64_MAX, mx_ = 0;
};

// ---------------------------------------------------------------- workload S
enum Kind : std::uint16_t { KSnapshot, KAdd, KModify, KDelete, KTrade, KSweep, KRefill, KTruncTouch, NKinds };
const char* const kind_names[NKinds] = {"snapshot", "add", "modify", "delete", "trade", "sweep", "refill", "truncated_price"};

struct Stream {
    std::vector<ll::Msg> msgs;
    std::vector<ll::Level> levels;
};

constexpr std::uint64_t seed = 20261117ULL;
constexpr std::size_t n_messages = 10'000'000, depth = 100;
// Workload R (2026-11-19): QF_H9_WARMUP overrides the warm-up count (R warms up on its first hour), QF_H9_WORKLOAD the
// label, and QF_H9_DUMP names a file that receives the fast book's full top(100) after every non-trade message of the
// correctness pass, for the independent check against micro.book.rebuild (benchmarks/h9_check_r.py).
std::size_t warmup = 1'000'000;

Stream generate() {
    quantforge::Xoshiro256 r(seed, 0);
    auto u = [&](std::uint64_t m) { return std::int64_t(r.next() % m); };
    auto chance = [&](double p) { return r.next_uniform() < p; };
    Stream st;
    st.msgs.reserve(n_messages);
    std::map<std::int64_t, std::int64_t> side[2];  // [0] bids, [1] asks; price ticks (0.1 grid) -> lots (1e-8)
    std::int64_t last_trunc[2] = {0, 0};
    const std::int64_t mid = 500'000;  // 50,000.0
    auto qty = [&] { return 1 + u(500'000'000); };
    auto emit = [&](ll::MsgType t, Kind k, int s, const std::vector<ll::Level>& lv) {
        ll::Msg m{};
        m.type = t;
        m.reserved = k;
        m.first = std::uint32_t(st.levels.size());
        (s == 0 ? m.n_bids : m.n_asks) = std::uint16_t(lv.size());
        st.levels.insert(st.levels.end(), lv.begin(), lv.end());
        st.msgs.push_back(m);
        if (t == ll::MsgType::Trade) return;
        for (const ll::Level& l : lv) {
            if (l.qty == 0) side[s].erase(l.px);
            else side[s][l.px] = l.qty;
        }
        while (side[0].size() > depth) last_trunc[0] = side[0].begin()->first, side[0].erase(side[0].begin());
        while (side[1].size() > depth) last_trunc[1] = std::prev(side[1].end())->first, side[1].erase(std::prev(side[1].end()));
    };
    auto best = [&](int s) { return s == 0 ? side[0].rbegin()->first : side[1].begin()->first; };
    auto nth = [&](int s, std::int64_t k) {  // k-th best price
        if (s == 0) {
            auto it = side[0].rbegin();
            std::advance(it, k);
            return it->first;
        }
        auto it = side[1].begin();
        std::advance(it, k);
        return it->first;
    };
    {  // message 0: the snapshot
        ll::Msg m{};
        m.type = ll::MsgType::Snapshot;
        m.reserved = KSnapshot;
        m.n_bids = m.n_asks = depth;
        for (std::int64_t k = 1; k <= std::int64_t(depth); ++k) st.levels.push_back({mid - k, qty()}), side[0][mid - k] = st.levels.back().qty;
        for (std::int64_t k = 1; k <= std::int64_t(depth); ++k) st.levels.push_back({mid + k, qty()}), side[1][mid + k] = st.levels.back().qty;
        st.msgs.push_back(m);
    }
    std::vector<ll::Level> refill;
    int refill_side = 0;
    std::vector<ll::Level> lv;
    while (st.msgs.size() < n_messages) {
        const std::size_t k = st.msgs.size();
        const bool burst = (k / 1000) % 2 == 1;  // bursts of 1,000 messages, alternating with quieter blocks
        lv.clear();
        if (!refill.empty()) {
            emit(ll::MsgType::Update, KRefill, refill_side, refill);
            refill.clear();
            continue;
        }
        if (k % 10'000 == 0) {  // deep sweep: remove the best 1-100 levels of one side; refill next message
            const int s = int(u(2));
            const std::int64_t n = std::min<std::int64_t>(1 + u(100), std::int64_t(side[s].size()));
            for (std::int64_t j = 0; j < n; ++j) lv.push_back({nth(s, j), 0});
            for (const ll::Level& l : lv) refill.push_back({l.px, qty()});
            refill_side = s;
            emit(ll::MsgType::Update, KSweep, s, lv);
            continue;
        }
        const int s = int(u(2));
        if (chance(0.01) && last_trunc[s] != 0) {  // a price that has just been truncated
            lv.push_back({last_trunc[s], qty()});
            emit(ll::MsgType::Update, KTruncTouch, s, lv);
            continue;
        }
        const bool near = chance(burst ? 0.5 : 0.1);  // within 3 ticks of the touch
        const std::int64_t sz = std::int64_t(side[s].size());
        const double roll = r.next_uniform();
        if (roll < 0.95 && roll >= 0.80 && sz <= 10) {  // keep both sides populated
            lv.push_back({s == 0 ? best(1) - 1 - u(3) : best(0) + 1 + u(3), qty()});
            emit(ll::MsgType::Update, KAdd, s, lv);
        } else if (roll < 0.60) {
            lv.push_back({nth(s, near ? u(std::min<std::int64_t>(3, sz)) : u(sz)), qty()});
            emit(ll::MsgType::Update, KModify, s, lv);
        } else if (roll < 0.80) {
            const std::int64_t d = near ? u(3) : u(110);
            lv.push_back({s == 0 ? best(1) - 1 - d : best(0) + 1 + d, qty()});
            emit(ll::MsgType::Update, KAdd, s, lv);
        } else if (roll < 0.95) {
            lv.push_back({nth(s, near ? u(std::min<std::int64_t>(3, sz)) : u(sz)), 0});
            emit(ll::MsgType::Update, KDelete, s, lv);
        } else {
            lv.push_back({best(s), 1 + u(100'000'000)});
            emit(ll::MsgType::Trade, KTrade, s, lv);
        }
    }
    return st;
}

bool write_stream(const char* path, const Stream& st) {
    FILE* f = std::fopen(path, "wb");
    if (!f) return false;
    const std::uint64_t n[2] = {st.msgs.size(), st.levels.size()};
    bool ok = std::fwrite("QFH9S001", 1, 8, f) == 8 && std::fwrite(n, 8, 2, f) == 2 &&
              std::fwrite(st.msgs.data(), sizeof(ll::Msg), st.msgs.size(), f) == st.msgs.size() &&
              std::fwrite(st.levels.data(), sizeof(ll::Level), st.levels.size(), f) == st.levels.size();
    return std::fclose(f) == 0 && ok;
}

bool read_stream(const char* path, Stream& st) {
    FILE* f = std::fopen(path, "rb");
    if (!f) return false;
    char magic[8];
    std::uint64_t n[2];
    bool ok = std::fread(magic, 1, 8, f) == 8 && std::memcmp(magic, "QFH9S001", 8) == 0 && std::fread(n, 8, 2, f) == 2;
    if (ok) {
        st.msgs.resize(n[0]);
        st.levels.resize(n[1]);
        ok = std::fread(st.msgs.data(), sizeof(ll::Msg), n[0], f) == n[0] &&
             std::fread(st.levels.data(), sizeof(ll::Level), n[1], f) == n[1];
    }
    std::fclose(f);
    return ok;
}

// ---------------------------------------------------------------- correctness pass (outside timing)
// The stream against a std::map transcription of order-book.md, top(100) compared every 1,000 messages and at the end.
long long verify(const Stream& st) {
    ll::Book b(depth);
    FILE* dump = std::getenv("QF_H9_DUMP") ? std::fopen(std::getenv("QF_H9_DUMP"), "w") : nullptr;
    std::map<std::int64_t, std::int64_t> bids, asks;
    std::vector<ll::Level> t(depth);
    long long mismatches = 0, checks = 0;
    for (std::size_t i = 0; i < st.msgs.size(); ++i) {
        const ll::Msg& m = st.msgs[i];
        b.apply(m, st.levels.data());
        if (m.type != ll::MsgType::Trade) {
            const ll::Level* lb = st.levels.data() + m.first;
            if (m.type == ll::MsgType::Snapshot) bids.clear(), asks.clear();
            for (int k = 0; k < m.n_bids; ++k) lb[k].qty ? void(bids[lb[k].px] = lb[k].qty) : void(bids.erase(lb[k].px));
            for (int k = 0; k < m.n_asks; ++k) {
                const ll::Level& l = lb[m.n_bids + k];
                l.qty ? void(asks[l.px] = l.qty) : void(asks.erase(l.px));
            }
            while (bids.size() > depth) bids.erase(bids.begin());
            while (asks.size() > depth) asks.erase(std::prev(asks.end()));
            if (dump) {
                std::fprintf(dump, "%zu", i);
                for (int side = 1; side >= 0; --side) {
                    const std::size_t n = b.top(side == 1, depth, t.data());
                    std::fprintf(dump, " %c %zu", side ? 'b' : 'a', n);
                    for (std::size_t k = 0; k < n; ++k) std::fprintf(dump, " %lld %lld", (long long)t[k].px, (long long)t[k].qty);
                }
                std::fputc('\n', dump);
            }
        }
        if (i % 1000 == 999 || i + 1 == st.msgs.size()) {
            ++checks;
            std::size_t n = b.top(true, depth, t.data());
            bool same = n == bids.size();
            auto it = bids.rbegin();
            for (std::size_t k = 0; same && k < n; ++k, ++it) same = t[k].px == it->first && t[k].qty == it->second;
            n = b.top(false, depth, t.data());
            same = same && n == asks.size();
            auto ja = asks.begin();
            for (std::size_t k = 0; same && k < n; ++k, ++ja) same = t[k].px == ja->first && t[k].qty == ja->second;
            if (!same) ++mismatches;
        }
    }
    if (dump) std::fclose(dump);
    std::fprintf(stderr, "correctness: %lld checkpoints, %lld mismatches; crossed %lld, grows %lld\n", checks, mismatches,
                 (long long)b.stats().crossed, (long long)b.grows());
    return mismatches;
}

// ---------------------------------------------------------------- one timed run
enum Query { QBestBid, QBestAsk, QQtyPresent, QQtyAbsent, QTop10, QTop100, NQueries };
const char* const query_names[NQueries] = {"best_bid", "best_ask", "qty_at_present", "qty_at_absent", "top10", "top100"};

struct RunResult {
    Hist all, kinds[NKinds], queries[NQueries], qbatch[NQueries], batch;
    long long allocs = 0, batch_allocs = 0, far = 0, grows = 0, fallbacks = 0;
};

volatile std::int64_t g_sink;

// DoNotOptimize-style barrier: the value must be materialised and memory may have changed.
inline void keep(std::int64_t& v) { asm volatile("" : "+r"(v) : : "memory"); }

// Precomputed side choices for the batch loops (filled once from core.rng).
std::array<std::uint8_t, 1024> sides{};

void timed_run(const Stream& st, RunResult& rr, std::uint64_t qseed) {
    quantforge::Xoshiro256 r(qseed, 0);
    for (auto& x : sides) x = std::uint8_t(r.next() & 1);
    std::vector<ll::Level> buf(depth), pres(depth);
    {
        ll::Book b(depth);
        for (std::size_t i = 0; i < warmup; ++i) b.apply(st.msgs[i], st.levels.data());
        const long long far0 = b.far_lookups();
        g_allocs.store(0);
        for (std::size_t i = warmup; i < st.msgs.size(); ++i) {
            const ll::Msg& m = st.msgs[i];
            const std::uint64_t t0 = now_ns();
            b.apply(m, st.levels.data());
            const std::uint64_t dt = now_ns() - t0;
            rr.all.record(dt);
            rr.kinds[m.reserved].record(dt);
            if ((i - warmup) % 1000 == 999) {
                ll::Level q{};
                std::uint64_t a = now_ns();
                b.best_bid(q);
                rr.queries[QBestBid].record(now_ns() - a);
                a = now_ns();
                b.best_ask(q);
                rr.queries[QBestAsk].record(now_ns() - a);
                const bool bid = (r.next() & 1) != 0;
                const std::size_t n = b.top(bid, depth, buf.data());  // untimed: picks the present price
                const std::int64_t present = n ? buf[std::size_t(r.next() % n)].px : 0;
                ll::Level ba{};
                const std::int64_t absent = b.best_ask(ba) ? ba.px + 5 : 1;  // above the best ask: never a bid price
                a = now_ns();
                g_sink = b.qty_at(bid, present);
                rr.queries[QQtyPresent].record(now_ns() - a);
                a = now_ns();
                g_sink = b.qty_at(true, absent);
                rr.queries[QQtyAbsent].record(now_ns() - a);
                a = now_ns();
                g_sink = std::int64_t(b.top(bid, 10, buf.data()));
                rr.queries[QTop10].record(now_ns() - a);
                a = now_ns();
                g_sink = std::int64_t(b.top(bid, 100, buf.data()));
                rr.queries[QTop100].record(now_ns() - a);
                // HR-21 batch timing: each query 1,000 times in a row, total divided by 1,000. To stop the compiler
                // hoisting or eliding the call, every iteration's side and price come from precomputed arrays indexed
                // through the previous result (a dependency chain, so the figure is latency, not throughput), and
                // the accumulator passes an empty asm barrier with a memory clobber each iteration (DoNotOptimize).
                std::int64_t acc = 0;
                const std::size_t np = b.top(bid, depth, pres.data());  // untimed
                const std::size_t npres = np ? np : 1;
                a = now_ns();
                for (std::size_t j = 0; j < 1000; ++j) {
                    acc += b.best_bid(q) ? q.qty + (acc & 1) : 0;
                    keep(acc);
                }
                rr.qbatch[QBestBid].record((now_ns() - a + 500) / 1000);
                a = now_ns();
                for (std::size_t j = 0; j < 1000; ++j) {
                    acc += b.best_ask(q) ? q.qty + (acc & 1) : 0;
                    keep(acc);
                }
                rr.qbatch[QBestAsk].record((now_ns() - a + 500) / 1000);
                a = now_ns();
                for (std::size_t j = 0; j < 1000; ++j) {
                    acc += b.qty_at(bid, pres[(j + std::size_t(acc & 1)) % npres].px);
                    keep(acc);
                }
                rr.qbatch[QQtyPresent].record((now_ns() - a + 500) / 1000);
                a = now_ns();
                for (std::size_t j = 0; j < 1000; ++j) {
                    acc += b.qty_at(true, absent + std::int64_t(j & 511) + (acc & 1));
                    keep(acc);
                }
                rr.qbatch[QQtyAbsent].record((now_ns() - a + 500) / 1000);
                a = now_ns();
                for (std::size_t j = 0; j < 1000; ++j) {
                    acc += std::int64_t(b.top(sides[(j + std::size_t(acc & 1)) & 1023] != 0, 10, buf.data())) + buf[0].qty;
                    keep(acc);
                }
                rr.qbatch[QTop10].record((now_ns() - a + 500) / 1000);
                a = now_ns();
                for (std::size_t j = 0; j < 1000; ++j) {
                    acc += std::int64_t(b.top(sides[(j + std::size_t(acc & 1)) & 1023] != 0, 100, buf.data())) + buf[99].qty;
                    keep(acc);
                }
                rr.qbatch[QTop100].record((now_ns() - a + 500) / 1000);
                g_sink = acc;
            }
        }
        rr.allocs = g_allocs.load();
        rr.far = b.far_lookups() - far0;
        rr.grows = b.grows();
        rr.fallbacks = b.index_fallbacks();
    }
    {  // batch timing: 1,000 messages per sample, divided
        ll::Book b(depth);
        for (std::size_t i = 0; i < warmup; ++i) b.apply(st.msgs[i], st.levels.data());
        g_allocs.store(0);
        for (std::size_t i = warmup; i + 1000 <= st.msgs.size(); i += 1000) {
            const std::uint64_t t0 = now_ns();
            for (std::size_t j = i; j < i + 1000; ++j) b.apply(st.msgs[j], st.levels.data());
            rr.batch.record((now_ns() - t0 + 500) / 1000);
        }
        rr.batch_allocs = g_allocs.load();
    }
}

}  // namespace

int main(int argc, char** argv) {
    if (argc >= 3 && std::strcmp(argv[1], "gen") == 0) {
        const Stream st = generate();
        if (!write_stream(argv[2], st)) return std::perror("write"), 2;
        std::fprintf(stderr, "wrote %zu messages, %zu levels\n", st.msgs.size(), st.levels.size());
        return 0;
    }
    if (argc < 3 || std::strcmp(argv[1], "run") != 0) {
        std::fprintf(stderr, "usage: qf_lowlat_book gen <file> | run <file> [runs] [out.json]\n");
        return 2;
    }
    Stream st;
    if (!read_stream(argv[2], st)) return std::fprintf(stderr, "cannot read %s\n", argv[2]), 2;
    const int runs = argc >= 4 ? std::atoi(argv[3]) : 5;
    if (const char* w = std::getenv("QF_H9_WARMUP")) warmup = std::size_t(std::strtoull(w, nullptr, 10));
    const char* workload = std::getenv("QF_H9_WORKLOAD") ? std::getenv("QF_H9_WORKLOAD") : "S";
    const long long mismatches = verify(st);

    Hist clock;  // 1,000,000 empty pairs
    for (int i = 0; i < 1'000'000; ++i) {
        const std::uint64_t a = now_ns();
        clock.record(now_ns() - a);
    }
    std::string out = "{\"workload\":\"" + std::string(workload) + "\",\"messages\":" + std::to_string(st.msgs.size()) +
                      ",\"warmup\":" + std::to_string(warmup) + ",\"depth\":100,\"alloc_method\":\"" + alloc_method +
                      "\",\"correctness_mismatches\":" + std::to_string(mismatches) + ",\"clock_overhead\":" + clock.json() +
                      ",\"runs\":[";
    for (int k = 0; k < runs; ++k) {
        auto* rr = new RunResult();
        timed_run(st, *rr, seed + 1 + std::uint64_t(k));
        out += (k ? "," : "") + std::string("{\"all\":") + rr->all.json() + ",\"kinds\":{";
        for (int j = 0; j < NKinds; ++j) out += (j ? ",\"" : "\"") + std::string(kind_names[j]) + "\":" + rr->kinds[j].json();
        out += "},\"queries\":{";
        for (int j = 0; j < NQueries; ++j) out += (j ? ",\"" : "\"") + std::string(query_names[j]) + "\":" + rr->queries[j].json();
        out += "},\"queries_batch_per_call\":{";
        for (int j = 0; j < NQueries; ++j) out += (j ? ",\"" : "\"") + std::string(query_names[j]) + "\":" + rr->qbatch[j].json();
        out += "},\"batch_per_message\":" + rr->batch.json() + ",\"allocations_measured\":" + std::to_string(rr->allocs) +
               ",\"allocations_batch\":" + std::to_string(rr->batch_allocs) + ",\"far_lookups\":" + std::to_string(rr->far) +
               ",\"buffer_grows\":" + std::to_string(rr->grows) +
               ",\"qty_at_index_fallbacks\":" + std::to_string(rr->fallbacks) + "}";
        std::fprintf(stderr, "run %d: p50 %llu p99 %llu p99.9 %llu ns, allocs %lld\n", k + 1, (unsigned long long)rr->all.pct(50),
                     (unsigned long long)rr->all.pct(99), (unsigned long long)rr->all.pct(99.9), rr->allocs);
        delete rr;
    }
    out += "]}\n";
    FILE* f = argc >= 5 ? std::fopen(argv[4], "w") : stdout;
    std::fputs(out.c_str(), f);
    if (f != stdout) std::fclose(f);
    return mismatches == 0 ? 0 : 1;
}
