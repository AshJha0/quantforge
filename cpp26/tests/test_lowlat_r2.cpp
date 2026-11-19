// H-9 workload R2 and row L7 harness helpers (cpp26/bench/lowlat_r2.hpp; low-latency-book.md items 2a and 2b,
// low-latency-targets.md (g) and (h)). Hand-built messages only, no recorded rows.
//  1. Truncation to depth 100 is inside Book::apply: a raw update that adds a 101st level drops the worst one, and
//     the top-10 checksum is that of the truncated book.
//  2. The L7 sample is the apply time divided by the levels, rounded up.
//  3. The form A pass: venue checksums counted and failed; a row passes at any message of its millisecond range;
//     a row that differs only below level 10 and one that differs in the top 10 are counted apart.
//  4. The checkpoint file round-trips.
#include <catch2/catch_test_macros.hpp>

#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <vector>

#include "../bench/lowlat_r2.hpp"
#include "quantforge/core/fast_book.hpp"

namespace ll = quantforge::lowlat;
namespace r2 = quantforge::lowlat::r2;

namespace {

// A full 100-level book: bids 1000 down to 901, asks 1001 up to 1100, quantity = 1 + distance from the touch.
std::vector<ll::Level> full_book() {
    std::vector<ll::Level> lv;
    for (int k = 0; k < 100; ++k) lv.push_back({1000 - k, 1 + k});
    for (int k = 0; k < 100; ++k) lv.push_back({1001 + k, 1 + k});
    return lv;
}

ll::Msg msg(ll::MsgType t, std::uint16_t nb, std::uint16_t na, std::uint32_t first, std::uint32_t cs = 0,
            std::uint8_t flags = 0) {
    return ll::Msg{t, flags, nb, na, 2, cs, first};
}

}  // namespace

TEST_CASE("R2: truncation to 100 levels happens inside apply", "[lowlat][r2]") {
    std::vector<ll::Level> lv = full_book();
    ll::Book b(100);
    b.apply(msg(ll::MsgType::Snapshot, 100, 100, 0), lv.data());
    REQUIRE(b.stats().truncated_levels == 0);
    // A raw update inserting a better bid: 101 bids, the worst falls off. Same book on a 10-tick grid, so that a
    // price between the touch levels exists.
    std::vector<ll::Level> better = {{10005, 7}};
    ll::Book c(100);
    std::vector<ll::Level> ticks;
    for (int k = 0; k < 100; ++k) ticks.push_back({10000 - 10 * k, 1 + k});
    for (int k = 0; k < 100; ++k) ticks.push_back({10010 + 10 * k, 1 + k});
    c.apply(msg(ll::MsgType::Snapshot, 100, 100, 0), ticks.data());
    c.apply(msg(ll::MsgType::Update, 1, 0, 0), better.data());
    CHECK(c.stats().truncated_levels == 1);
    std::vector<ll::Level> top(100);
    REQUIRE(c.top(true, 100, top.data()) == 100);
    CHECK(top[0].px == 10005);
    CHECK(top[99].px == 10000 - 10 * 98);  // 9020: the old worst (9010) was dropped
    CHECK(c.qty_at(true, 9010) == 0);
    // An update beyond depth on the far side is inserted and truncated in the same apply: the book is unchanged.
    const std::uint32_t before = c.checksum();
    std::vector<ll::Level> deep = {{5000, 3}};
    c.apply(msg(ll::MsgType::Update, 1, 0, 0), deep.data());
    CHECK(c.stats().truncated_levels == 2);
    CHECK(c.checksum() == before);
    CHECK(c.qty_at(true, 5000) == 0);
    // The checksum after the truncating update equals that of a book built directly in the truncated state.
    std::vector<ll::Level> direct = {{10005, 7}};
    for (int k = 0; k < 99; ++k) direct.push_back({10000 - 10 * k, 1 + k});
    for (int k = 0; k < 100; ++k) direct.push_back({10010 + 10 * k, 1 + k});
    ll::Book d(100);
    d.apply(msg(ll::MsgType::Snapshot, 100, 100, 0), direct.data());
    CHECK(d.checksum() == c.checksum());
    CHECK(c.grows() == 0);
}

TEST_CASE("L7: per-level sample is apply time over levels, rounded up", "[lowlat][r2]") {
    CHECK(r2::per_level_ns(100, 1) == 100);
    CHECK(r2::per_level_ns(101, 2) == 51);
    CHECK(r2::per_level_ns(100, 3) == 34);
    CHECK(r2::per_level_ns(99, 3) == 33);
    CHECK(r2::per_level_ns(0, 5) == 0);
    CHECK(r2::per_level_ns(1, 200) == 1);
}

TEST_CASE("R2: form A pass counts checksums and checkpoint classes", "[lowlat][r2]") {
    // Stream: 0 snapshot (bids 100..89, asks 101..112, qty 5), 1 update bid 100 -> 6, 2 trade, 3 update bid 89 -> 9
    // (level 12, below the top 10), 4 update bid 100 -> 7.
    std::vector<ll::Level> lv;
    for (int k = 0; k < 12; ++k) lv.push_back({100 - k, 5});
    for (int k = 0; k < 12; ++k) lv.push_back({101 + k, 5});
    const std::uint32_t u1 = std::uint32_t(lv.size());
    lv.push_back({100, 6});
    const std::uint32_t tr = std::uint32_t(lv.size());
    lv.push_back({101, 1});
    const std::uint32_t u3 = std::uint32_t(lv.size());
    lv.push_back({89, 9});
    const std::uint32_t u4 = std::uint32_t(lv.size());
    lv.push_back({100, 7});
    std::vector<ll::Msg> msgs = {msg(ll::MsgType::Snapshot, 12, 12, 0), msg(ll::MsgType::Update, 1, 0, u1),
                                 msg(ll::MsgType::Trade, 1, 0, tr), msg(ll::MsgType::Update, 1, 0, u3),
                                 msg(ll::MsgType::Update, 1, 0, u4)};
    msgs[2].reserved = 4;
    // Venue checksums: the right value on messages 0, 1, 4; a wrong one on message 3; none flagged on the trade.
    {
        ll::Book ref(100);
        for (std::size_t i = 0; i < msgs.size(); ++i) {
            ref.apply(msgs[i], lv.data());
            if (msgs[i].type == ll::MsgType::Trade) continue;
            msgs[i].flags = r2::flag_venue_checksum;
            msgs[i].checksum = i == 3 ? ref.checksum() ^ 1U : ref.checksum();
        }
    }
    // The book after each message, as rows.
    auto row = [&](std::size_t after_msg, r2::Checkpoints& cps, std::uint32_t lo, std::uint32_t hi, int tweak) {
        ll::Book b(100);
        for (std::size_t i = 0; i <= after_msg; ++i) b.apply(msgs[i], lv.data());
        std::vector<ll::Level> bids(100), asks(100);
        const std::size_t nb = b.top(true, 100, bids.data()), na = b.top(false, 100, asks.data());
        if (tweak == 1) bids[11].qty += 1;  // level 12: below the top 10
        if (tweak == 2) asks[0].qty += 1;   // the touch
        r2::Checkpoint c{lo, std::uint16_t(nb), std::uint16_t(na), std::uint32_t(cps.levels.size()), hi};
        cps.levels.insert(cps.levels.end(), bids.begin(), bids.begin() + long(nb));
        cps.levels.insert(cps.levels.end(), asks.begin(), asks.begin() + long(na));
        cps.rows.push_back(c);
    };
    r2::Checkpoints cps;
    row(0, cps, 0, 0, 0);  // exact at lo == hi
    row(1, cps, 0, 2, 0);  // state after message 1: not at lo (0), not at hi (2 = after the trade, same as 1)
    row(4, cps, 3, 4, 0);  // matches at hi only
    row(3, cps, 3, 3, 1);  // differs below level 10
    row(4, cps, 4, 4, 2);  // differs in the top 10
    const r2::Counts c = r2::verify_form_a(msgs, lv, cps, 100);
    CHECK(c.checksum_checked == 4);
    CHECK(c.checksum_failed == 1);
    CHECK(c.checkpoint_checked == 5);
    CHECK(c.checkpoint_failed_below10 == 1);
    CHECK(c.checkpoint_failed_top10 == 1);
    CHECK(c.rows_with_tie == 2);
    CHECK(c.matched_at_lo == 1);
    CHECK(c.matched_at_hi == 3);  // rows 0, 1 (the trade leaves the book as after message 1) and 2
    CHECK(c.matched_only_inside_tie == 0);
    // compare(): 0, 1, 2 directly.
    ll::Book b(100);
    b.apply(msgs[0], lv.data());
    std::vector<ll::Level> bids(100), asks(100), scratch(100);
    const std::size_t nb = b.top(true, 100, bids.data()), na = b.top(false, 100, asks.data());
    CHECK(r2::compare(b, bids.data(), nb, asks.data(), na, scratch.data()) == 0);
    bids[11].px -= 1;
    CHECK(r2::compare(b, bids.data(), nb, asks.data(), na, scratch.data()) == 1);
    asks[3].qty = 99;
    CHECK(r2::compare(b, bids.data(), nb, asks.data(), na, scratch.data()) == 2);
    // A row with fewer levels than the book compares only the row's levels (micro.book.rebuild's rule).
    CHECK(r2::compare(b, bids.data(), 5, asks.data(), 2, scratch.data()) == 0);
}

TEST_CASE("R2: checkpoint file round trip", "[lowlat][r2]") {
    const auto path = std::filesystem::temp_directory_path() / "qf_lowlat_r2_cps.bin";
    {
        FILE* f = std::fopen(path.string().c_str(), "wb");
        REQUIRE(f != nullptr);
        const std::uint64_t n[2] = {1, 3};
        const r2::Checkpoint c{4, 2, 1, 0, 7};
        const ll::Level lv[3] = {{100, 1}, {99, 2}, {101, 3}};
        std::fwrite("QFH9C001", 1, 8, f);
        std::fwrite(n, 8, 2, f);
        std::fwrite(&c, sizeof c, 1, f);
        std::fwrite(lv, sizeof(ll::Level), 3, f);
        std::fclose(f);
    }
    r2::Checkpoints cps;
    REQUIRE(r2::read_checkpoints(path.string().c_str(), cps));
    REQUIRE(cps.rows.size() == 1);
    CHECK(cps.rows[0].lo == 4);
    CHECK(cps.rows[0].hi == 7);
    CHECK(cps.rows[0].n_bids == 2);
    CHECK(cps.levels[2].px == 101);
    std::filesystem::remove(path);
    CHECK_FALSE(r2::read_checkpoints(path.string().c_str(), cps));
}
