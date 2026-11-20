// Stage K, K-5 (KR-280 to KR-288, confirmed 2026-11-20): snapshot semantics on the shared scenario
// datasets/scenarios/k5_snapshot.json, and the race test that ThreadSanitizer runs. Latency-aware analytics on
// simulated data; nothing here is timed.
//
//   qf_snapshot_race moves                     K-5 acceptance: 1,000 shared moves inside the intraday bound
//   qf_snapshot_race unit                      scenario values, exactness on 1,000 publishes, checksum, faults 4
//   qf_snapshot_race race R [P] [none|relaxed|skip]   1 writer, R readers, P publishes (default QF_SNAPSHOT_PUBLISHES
//                                                     or the scenario's publishes_default)
// Exit 0 when every check holds. Under a planted fault (KR-288) the run is expected to be reported by ThreadSanitizer.
#include <atomic>
#include <bit>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include "quantforge/core/json.hpp"
#include "quantforge/core/live_snapshot.hpp"

namespace qs = quantforge::live;
namespace sk = quantforge::stage_k;

namespace {

int failures = 0;

void expect(bool ok, const char* what) {
    if (!ok) {
        ++failures;
        std::fprintf(stderr, "FAIL: %s\n", what);
    }
}

struct Scenario {
    std::vector<sk::ZeroPosition> book;
    qs::HedgeInstrument hedge{};
    quantforge::json::Value root;
};

Scenario load() {
    std::ifstream in(std::string(QF_REPO_DIR) + "/datasets/scenarios/k5_snapshot.json", std::ios::binary);
    std::stringstream ss;
    ss << in.rdbuf();
    Scenario s;
    s.root = quantforge::json::parse(ss.str()).value;
    for (const auto& p : s.root.find("book")->items)
        s.book.push_back({p.find("notional")->number, p.find("maturity")->number, p.find("yield")->number});
    const auto* h = s.root.find("hedge");
    s.hedge = {h->find("maturity")->number, h->find("yield")->number};
    return s;
}

bool close(double a, double b, double tol) { return std::fabs(a - b) <= tol * std::fabs(b); }

bool same_bits(const qs::HedgeSnapshot& a, const qs::HedgeSnapshot& b) {
    return a.words() == b.words() && a.check == b.check;
}

int unit(const Scenario& sc) {
    const double tol = sc.root.find("tolerance_relative")->number;
    for (const auto& row : sc.root.find("expected")->items) {
        const auto k = static_cast<std::uint64_t>(row.find("version")->number);
        const auto s = qs::build(k, k, sc.book, sc.hedge, qs::scenario_shift(k));
        expect(s.intact(), "built snapshot is intact");
        expect(s.shift == row.find("shift")->number, "shift rule matches the scenario");
        expect(close(s.estimate_pnl, row.find("estimate_pnl")->number, tol), "estimate_pnl at 1e-9");
        expect(close(s.bound, row.find("bound")->number, tol), "bound at 1e-9");
        expect(close(s.book_delta, row.find("book_delta")->number, tol), "book_delta at 1e-9");
        expect(close(s.hedge_unit_delta, row.find("hedge_unit_delta")->number, tol), "hedge_unit_delta at 1e-9");
        expect(close(s.hedge_notional, row.find("hedge_notional")->number, tol), "hedge_notional at 1e-9");
        const double residual = s.book_delta + s.hedge_notional * s.hedge_unit_delta;
        expect(std::fabs(residual) <= 1e-9 * std::fabs(s.book_delta), "hedge neutralises the delta");
    }
    // Checksum pinned values (KR-287).
    const std::uint64_t one[] = {0}, three[] = {1, 2, 3};
    expect(qs::checksum(nullptr, 0) == qs::check_seed, "checksum of no words is the seed");
    expect(qs::checksum(one, 1) == 0xF6E599AEF89D022Full, "checksum [0]");
    expect(qs::checksum(three, 3) == 0x8517CC75DE438E52ull, "checksum [1,2,3]");
    // Exactness (KR-284) on 1,000 publishes through a one-reader cell.
    const auto n = static_cast<std::uint64_t>(sc.root.find("exactness_publishes")->number);
    qs::SnapshotCell<qs::HedgeSnapshot> cell(1, qs::build(0, 0, sc.book, sc.hedge, 0.0));
    for (std::uint64_t k = 1; k <= n; ++k) {
        const double h = qs::scenario_shift(k);
        cell.publish(qs::build(k, k, sc.book, sc.hedge, h));
        const auto g = cell.acquire(0);
        const auto risk = sk::delta_gamma_bound(sc.book, h);
        const double d = qs::book_delta(sc.book, h), u = qs::hedge_unit_delta(sc.hedge, h);
        const bool ok = g->version == k && std::bit_cast<std::uint64_t>(g->estimate_pnl) == std::bit_cast<std::uint64_t>(risk.estimate_pnl) &&
                        std::bit_cast<std::uint64_t>(g->bound) == std::bit_cast<std::uint64_t>(risk.bound) &&
                        std::bit_cast<std::uint64_t>(g->book_delta) == std::bit_cast<std::uint64_t>(d) &&
                        std::bit_cast<std::uint64_t>(g->hedge_unit_delta) == std::bit_cast<std::uint64_t>(u) &&
                        std::bit_cast<std::uint64_t>(g->hedge_notional) == std::bit_cast<std::uint64_t>(-d / u);
        if (!ok) {
            expect(false, "exactness: snapshot equals the direct call bit for bit");
            break;
        }
    }
    // Planted fault 4: one field changed after the checksum; the reader check must fail.
    auto bad = qs::build(5, 5, sc.book, sc.hedge, qs::scenario_shift(5));
    bad.bound = std::nextafter(bad.bound, std::numeric_limits<double>::infinity());
    expect(!bad.intact(), "a corrupted field fails the reader check");
    // Pool rules: R + 2 slots, R in 1..64.
    expect(cell.pool_size() == 3, "pool is R + 2");
    bool threw = false;
    try {
        qs::SnapshotCell<qs::HedgeSnapshot> zero(0, qs::HedgeSnapshot{});
    } catch (const std::invalid_argument&) {
        threw = true;
    }
    expect(threw, "zero readers refused");
    threw = false;
    try {
        (void)cell.acquire(1);
    } catch (const std::out_of_range&) {
        threw = true;
    }
    expect(threw, "reader index out of range refused");
    // A reader that holds a guard keeps its slot through many publishes (the hazard is respected).
    {
        qs::SnapshotCell<qs::HedgeSnapshot> c2(2, qs::build(0, 0, sc.book, sc.hedge, 0.0));
        const auto held = c2.acquire(0);
        const auto before = held->words();
        for (std::uint64_t k = 1; k <= 50; ++k) c2.publish(qs::build(k, k, sc.book, sc.hedge, qs::scenario_shift(k)));
        expect(held->words() == before && held->version == 0 && held->intact(), "held snapshot unchanged");
        expect(c2.acquire(1)->version == 50, "a new reader sees the last version");
    }
    std::printf("unit: %d failure(s)\n", failures);
    return failures == 0 ? 0 : 1;
}

struct alignas(64) ReaderStats {
    std::uint64_t reads = 0, torn = 0, non_monotone = 0, mismatched = 0, last = 0;
};

int race(const Scenario& sc, std::size_t readers, std::uint64_t publishes, qs::Fault fault) {
    const auto initial = qs::build(0, 0, sc.book, sc.hedge, 0.0);
    qs::SnapshotCell<qs::HedgeSnapshot> cell(readers, initial, fault);
    std::vector<ReaderStats> stats(readers);
    std::atomic<std::size_t> ready{0};
    std::vector<std::thread> threads;
    for (std::size_t i = 0; i < readers; ++i) {
        threads.emplace_back([&, i] {
            ReaderStats& st = stats[i];
            ready.fetch_add(1);
            for (;;) {
                const auto g = cell.acquire(i);
                ++st.reads;
                if (!g->intact()) ++st.torn;
                if (g->version < st.last) ++st.non_monotone;
                if (g->version > st.last) st.last = g->version;
                if (st.reads % 64 == 0 && !same_bits(*g, qs::build(g->version, g->as_of, sc.book, sc.hedge, g->shift)))
                    ++st.mismatched;
                if (g->version >= publishes) break;
            }
        });
    }
    while (ready.load() < readers) std::this_thread::yield();
    for (std::uint64_t k = 1; k <= publishes; ++k) cell.publish(qs::build(k, k, sc.book, sc.hedge, qs::scenario_shift(k)));
    for (auto& t : threads) t.join();
    std::uint64_t reads = 0, torn = 0, nonmono = 0, mism = 0, last_min = publishes;
    for (const auto& st : stats) {
        reads += st.reads;
        torn += st.torn;
        nonmono += st.non_monotone;
        mism += st.mismatched;
        if (st.last < last_min) last_min = st.last;
    }
    std::printf("race: readers=%zu publishes=%llu reads=%llu torn=%llu non_monotone=%llu mismatched=%llu final_seen=%s "
                "(latency-aware analytics on simulated data; not timed)\n",
                readers, static_cast<unsigned long long>(publishes), static_cast<unsigned long long>(reads),
                static_cast<unsigned long long>(torn), static_cast<unsigned long long>(nonmono),
                static_cast<unsigned long long>(mism), last_min == publishes ? "yes" : "no");
    return (torn == 0 && nonmono == 0 && mism == 0 && last_min == publishes) ? 0 : 1;
}

// K-5 acceptance on the shared moves file (datasets/scenarios/k5a_intraday_moves.json, the same 50-position book and
// 1,000 moves in every build): |estimate - full revaluation| <= bound on every move.
int moves() {
    std::ifstream in(std::string(QF_REPO_DIR) + "/datasets/scenarios/k5a_intraday_moves.json", std::ios::binary);
    std::stringstream ss;
    ss << in.rdbuf();
    const auto root = quantforge::json::parse(ss.str()).value;
    std::vector<sk::ZeroPosition> book;
    for (const auto& p : root.find("book")->items) book.push_back({p.items[0].number, p.items[1].number, p.items[2].number});
    expect(book.size() == 50, "50 positions");
    const auto& hs = root.find("moves")->items;
    expect(hs.size() == 1000, "1,000 moves");
    double worst = 0.0;
    int violations = 0;
    for (const auto& hv : hs) {
        const double h = hv.number;
        const auto r = sk::delta_gamma_bound(book, h);
        const double err = std::fabs(r.estimate_pnl - sk::zero_revalue(book, h));
        if (!(err <= r.bound)) ++violations;
        if (err / r.bound > worst) worst = err / r.bound;
    }
    expect(violations == 0, "every move inside its bound");
    std::printf("k5a moves: %zu moves, %d violations, worst |error| / bound = %.6g\n", hs.size(), violations, worst);
    return failures == 0 ? 0 : 1;
}

}  // namespace

int main(int argc, char** argv) {
    const Scenario sc = load();
    const std::string mode = argc > 1 ? argv[1] : "unit";
    if (mode == "unit") return unit(sc);
    if (mode == "moves") return moves();
    if (mode == "race" && argc > 2) {
        const auto readers = static_cast<std::size_t>(std::strtoull(argv[2], nullptr, 10));
        auto publishes = static_cast<std::uint64_t>(sc.root.find("race")->find("publishes_default")->number);
        if (const char* env = std::getenv("QF_SNAPSHOT_PUBLISHES")) publishes = std::strtoull(env, nullptr, 10);
        if (argc > 3) publishes = std::strtoull(argv[3], nullptr, 10);
        qs::Fault fault = qs::Fault::None;
        if (argc > 4) {
            const std::string f = argv[4];
            if (f == "relaxed") fault = qs::Fault::RelaxedPublish;
            else if (f == "skip") fault = qs::Fault::SkipHazardScan;
        }
        return race(sc, readers, publishes, fault);
    }
    std::fprintf(stderr, "usage: qf_snapshot_race unit | moves | race R [P] [none|relaxed|skip]\n");
    return 2;
}
