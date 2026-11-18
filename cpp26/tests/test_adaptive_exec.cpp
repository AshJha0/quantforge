// Stage H wave 2 execution (rulings HR-59 to HR-67): acceptance tests 1 to 4 of 10-execution/adaptive-algos.md and
// 1, 2 of 10-execution/tca-pretrade.md, seed 20261118, plus the CLI wiring. The goldens alg_h and tcx_h run in
// test_golden_replay.cpp. The simulated-book test rests each planted book on the C++ lit engine (exec.sim.lit.run).
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "dispatch.hpp"
#include "quantforge/core/adaptive_exec.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/rng.hpp"

namespace ex = quantforge::execution;
namespace json = quantforge::json;
using Vec = std::vector<double>;

namespace {
constexpr std::uint64_t seed = 20261118;

// u in [a, b) from the top 53 bits, i in [a, b] by unsigned modulo (as the Python and Java tests draw).
struct U {
    quantforge::Xoshiro256 g;
    explicit U(std::uint64_t s) : g(s, 0) {}
    double u(double a, double b) { return a + (b - a) * ((double)(g.next() >> 11) * 0x1p-53); }
    long long i(long long a, long long b) { return a + (long long)(g.next() % (std::uint64_t)(b - a + 1)); }
    ex::Side side() { return (g.next() & 1) != 0 ? ex::Side::Buy : ex::Side::Sell; }
};

bool rel(double got, double want) { return std::fabs(got - want) <= 1e-12 * std::max(1.0, std::fabs(want)); }
double sum(const Vec& x) {
    double s = 0;
    for (const double v : x) s += v;
    return s;
}

template <class F>
std::string code_of(F f) {
    try {
        f();
    } catch (const quantforge::Error& e) {
        return e.code();
    }
    return "none";
}

std::string run(const std::string& op, const std::string& inputs) {
    return quantforge::cli::run_case(R"({"schema_version":"1.0","case_id":"t","operation":")" + op +
                                     R"(","inputs":)" + inputs + "}")
        .json;
}

std::string price_text(long long ticks) {
    const std::string s = std::to_string(ticks);
    return s.substr(0, s.size() - 2) + "." + s.substr(s.size() - 2);
}

std::string exact(double v) {  // a dyadic child quantity, printed in full
    return json::format_real(v);
}

// Rests the planted book on the lit engine, sends the child as an IOC at L; returns {qty, notional}, checks L.
std::pair<double, double> lit_fills(ex::Side side, const std::vector<std::pair<long long, long long>>& book,
                                    long long limit, double child) {
    const bool buy = side == ex::Side::Buy;
    std::string ev = "[";
    for (std::size_t k = 0; k < book.size(); ++k) {
        if (k) ev += ",";
        ev += R"({"op":"NEW","id":"M)" + std::to_string(k) + R"(","trader":"MM","side":")" +
              (buy ? "SELL" : "BUY") + R"(","type":"LIMIT","price":")" + price_text(book[k].first) +
              R"(","qty":")" + std::to_string(book[k].second) + "\"}";
    }
    if (child > 0)
        ev += R"(,{"op":"NEW","id":"C","trader":"US","side":")" + std::string(buy ? "BUY" : "SELL") +
              R"(","type":"IOC","price":")" + price_text(limit) + R"(","qty":")" + exact(child) + "\"}";
    ev += "]";
    const std::string res = run("exec.sim.lit.run", R"({"tick_size":"0.01","lot_size":"0.125","events":)" + ev +
                                                        R"(,"fee_schedule":{"taker_fee":"0","maker_rebate":"0"}})");
    const json::Parsed doc = json::parse(res);
    const json::Value* outs = doc.value.find("outputs");
    REQUIRE(outs);
    double q = 0, notional = 0;
    const double lim = (double)limit / 100.0;
    for (const json::Value& f : outs->find("fills")->items) {
        if (f.find("taker_id")->text != "C") continue;
        const double fq = std::stod(f.find("qty")->text), fp = std::stod(f.find("price")->text);
        CHECK((buy ? fp <= lim : fp >= lim));  // no fill outside L
        q += fq;
        notional += fq * fp;
    }
    return {q, notional};
}
}  // namespace

TEST_CASE("arrival: slices sum to X, decrease for kappa > 0, and kappa = 0 is TWAP") {
    U r(seed);
    for (int t = 0; t < 1000; ++t) {
        const long long n = r.i(1, 60);
        const double k = r.u(0, 2), x = (double)r.i(1, 1'000'000'000);
        const Vec c = ex::algo_arrival(x, n, k, ex::Mode::Continuous);
        CHECK(rel(sum(c), x));
        for (std::size_t j = 1; j < c.size(); ++j) CHECK(c[j - 1] > c[j]);
        const Vec u = ex::algo_arrival(x, n, k, ex::Mode::Units);
        CHECK(sum(u) == x);
        for (std::size_t j = 0; j < u.size(); ++j) CHECK(std::fabs(u[j] - c[j]) < 1 + 1e-9 * x);  // HR-67
    }
    for (int t = 0; t < 1000; ++t) {
        const long long n = r.i(1, 500);
        const double x = (double)r.i(1, 1'000'000'000);
        CHECK(ex::algo_arrival(x, n, 0, ex::Mode::Units) == ex::twap(x, n, ex::Mode::Units));
        CHECK(ex::algo_arrival(x, n, 0, ex::Mode::Continuous) == ex::twap(x, n, ex::Mode::Continuous));
    }
    CHECK(code_of([] { ex::algo_arrival(1000, 0, -1, ex::Mode::Continuous); }) == "E_INPUT");  // HR-66
    CHECK(code_of([] { ex::algo_arrival(10.5, 2, 0.5, ex::Mode::Units); }) == "E_INPUT");
    CHECK(code_of([] { ex::algo_arrival(1000, 2, -1, ex::Mode::Continuous); }) == "E_DOMAIN");
    CHECK(ex::largest_remainder(3, {1.6, 1.2, 0.2}) == Vec{2, 1, 0});
    CHECK(ex::largest_remainder(2, {1.0, 1.0, 0.25}) == Vec{1, 1, 0});
    CHECK(ex::largest_remainder(2, {1.0, 1.0, 1.0}) == Vec{1, 1, 0});  // floors above x: back from the latest
}

TEST_CASE("close: auction plus slices sum to X") {
    U r(seed + 2);
    for (int t = 0; t < 1000; ++t) {
        Vec w((std::size_t)r.i(1, 30));
        for (double& v : w) v = r.u(0, 5);
        const double x = (double)r.i(1, 10'000'000), v = r.u(0, 1e7), p = r.u(0, 1);
        const ex::Close c = ex::algo_close(x, v, p, w, ex::Mode::Continuous);
        CHECK(rel(c.auction_quantity + sum(c.slices), x));
        const ex::Close u = ex::algo_close(x, v, p, w, ex::Mode::Units);
        CHECK(u.auction_quantity + sum(u.slices) == x);
        CHECK(u.auction_quantity == std::floor(u.auction_quantity));
    }
    const ex::Close all = ex::algo_close(100, 1000, 0.5, {0, 0}, ex::Mode::Units);
    CHECK(all.auction_quantity == 100);
    CHECK(all.slices == Vec{0, 0});
    CHECK(code_of([] { ex::algo_close(100, 1000, 0.01, {0, 0}, ex::Mode::Units); }) == "E_DOMAIN");
    CHECK(code_of([] { ex::algo_close(100, -1, 2, {}, ex::Mode::Units); }) == "E_INPUT");  // HR-66
    CHECK(code_of([] { ex::algo_close(100, -1, 0.5, {1}, ex::Mode::Units); }) == "E_DOMAIN");
    CHECK(code_of([] { ex::algo_close(100, 1, 0.5, {-1}, ex::Mode::Units); }) == "E_DOMAIN");
}

TEST_CASE("basket: legs sum to their quantity, cash imbalance linear in CONTINUOUS") {
    U r(seed + 3);
    for (int t = 0; t < 1000; ++t) {
        const long long n = r.i(1, 40);
        std::vector<ex::Leg> legs((std::size_t)r.i(1, 8));
        for (ex::Leg& g : legs) {
            g.side = r.side();
            g.quantity = (double)r.i(1, 1'000'000);
            g.price = r.u(1, 1000);
        }
        const ex::Basket c = ex::algo_basket(legs, n, ex::Mode::Continuous);
        for (std::size_t k = 0; k < legs.size(); ++k) CHECK(rel(sum(c.slices[k]), legs[k].quantity));
        const double last = c.cash_imbalance.back();
        for (long long j = 0; j < n; ++j)
            CHECK(std::fabs(c.cash_imbalance[(std::size_t)j] - (double)(j + 1) / (double)n * last) <=
                  1e-12 * c.gross_notional);
        const ex::Basket u = ex::algo_basket(legs, n, ex::Mode::Units);
        for (std::size_t k = 0; k < legs.size(); ++k) CHECK(sum(u.slices[k]) == legs[k].quantity);
    }
    const std::vector<ex::Leg> zero = {{ex::Side::Buy, 300, 10}, {ex::Side::Buy, 200, 20}, {ex::Side::Sell, 700, 10}};
    for (const double ci : ex::algo_basket(zero, 7, ex::Mode::Continuous).cash_imbalance) CHECK(std::fabs(ci) <= 1e-9);
    CHECK(code_of([] { ex::algo_basket({}, 0, ex::Mode::Units); }) == "E_INPUT");
    CHECK(code_of([] { ex::algo_basket({{ex::Side::Buy, 1.5, -1}}, 2, ex::Mode::Units); }) == "E_INPUT");
    CHECK(code_of([] { ex::algo_basket({{ex::Side::Buy, 1, -1}}, 2, ex::Mode::Units); }) == "E_DOMAIN");
}

TEST_CASE("pair: slices sum, cash-imbalance bounds, HEDGED quantity_b = h X_A") {
    U r(seed + 4);
    for (int t = 0; t < 1000; ++t) {
        const long long n = r.i(1, 40);
        const double qa = (double)r.i(1, 1'000'000), pa = r.u(1, 1000), pb = r.u(1, 1000);
        const ex::Side sa = r.side(), sb = sa == ex::Side::Buy ? ex::Side::Sell : ex::Side::Buy;
        const ex::Pair c =
            ex::algo_pair(sa, qa, pa, sb, pb, ex::PairMode::CashBalanced, std::nullopt, n, ex::Mode::Continuous);
        CHECK(rel(sum(c.slices_a), qa));
        CHECK(rel(sum(c.slices_b), c.quantity_b));
        for (const double x : c.cash_imbalance) CHECK(std::fabs(x) <= 1e-12 * qa * pa);
        const ex::Pair u =
            ex::algo_pair(sa, qa, pa, sb, pb, ex::PairMode::CashBalanced, std::nullopt, n, ex::Mode::Units);
        CHECK(sum(u.slices_a) == qa);
        CHECK(sum(u.slices_b) == u.quantity_b);
        CHECK(u.quantity_b == std::floor(pa / pb * qa + 0.5));
        for (const double x : u.cash_imbalance) CHECK(std::fabs(x) <= pb / 2 * (1 + 1e-12));
        const double h = r.u(0.01, 5);
        const ex::Pair hd = ex::algo_pair(sa, qa, pa, r.side(), pb, ex::PairMode::Hedged, h, n, ex::Mode::Continuous);
        CHECK(rel(hd.quantity_b, h * qa));
    }
    const auto pair = [](ex::Side sb, double pa, std::optional<double> h, ex::PairMode m) {
        return code_of([&] { ex::algo_pair(ex::Side::Buy, 100, pa, sb, 10, m, h, 2, ex::Mode::Units); });
    };
    CHECK(pair(ex::Side::Buy, -1, std::nullopt, ex::PairMode::CashBalanced) == "E_INPUT");  // HR-66
    CHECK(pair(ex::Side::Sell, 10, std::nullopt, ex::PairMode::Hedged) == "E_INPUT");
    CHECK(pair(ex::Side::Sell, -1, 1.0, ex::PairMode::Hedged) == "E_DOMAIN");
    CHECK(pair(ex::Side::Sell, 10, 0.0, ex::PairMode::Hedged) == "E_DOMAIN");
}

TEST_CASE("liquidity seek: simulated-book method test on the lit engine (200 planted books)") {
    U r(seed);
    for (int t = 0; t < 200; ++t) {
        const ex::Side side = r.side();
        const bool buy = side == ex::Side::Buy;
        const auto kb = (std::size_t)r.i(1, 5);
        const double x = (double)r.i(1, 20'000);
        const double alpha = (double)r.i(1, 8) / 8.0;  // dyadic: alpha A and the remainders are exact
        const long long limit = r.i(9'000, 11'000);
        std::vector<std::vector<std::pair<long long, long long>>> planted(kb);
        std::vector<ex::Book> books(kb);
        for (std::size_t b = 0; b < kb; ++b) {
            const long long nl = r.i(5, 20);
            long long tick = buy ? limit - r.i(0, 40) : limit + r.i(0, 40);
            std::vector<long long> ticks;
            for (long long l = 0; l < nl; ++l) {
                ticks.push_back(tick);
                tick += (buy ? 1 : -1) * r.i(1, 5);
            }
            for (const long long tk : ticks) {
                planted[b].push_back({tk, r.i(1, 2'000)});
                books[b].push_back({(double)tk / 100.0, (double)planted[b].back().second});
            }
        }
        const double lim = (double)limit / 100.0;
        const ex::Seek res = ex::algo_liquidity_seek(side, x, lim, alpha, books);
        double remaining = x;
        for (std::size_t b = 0; b < kb; ++b) {
            double depth = 0;
            long long known = 0;
            for (std::size_t l = 0; l < books[b].size(); ++l) {
                if (buy ? books[b][l][0] <= lim : books[b][l][0] >= lim) depth += books[b][l][1];
                if (buy ? planted[b][l].first <= limit : planted[b][l].first >= limit) known += planted[b][l].second;
            }
            CHECK((double)known == depth);  // known depth inside L
            const double want = std::min(remaining, alpha * depth);
            const double c = res.slices[b];
            CHECK(rel(c, want));
            const auto [q, notional] = lit_fills(side, planted[b], limit, c);
            CHECK(rel(q, want));  // recovered fills equal min(R, alpha A_i)
            const auto& avg = res.avg_prices[b];
            if (c > 0) {
                REQUIRE(avg.has_value());
                CHECK(rel(*avg, notional / q));
                const double best = books[b][0][0];
                const double lo = buy ? best : lim, hi = buy ? lim : best;
                CHECK(lo - 1e-12 <= *avg);
                CHECK(*avg <= hi + 1e-12);
            } else {
                CHECK_FALSE(avg.has_value());
            }
            remaining -= c;
        }
        CHECK(rel(res.filled + res.residual, x));
    }
    const std::vector<ex::Book> bad_order = {{{100.5, 300}, {100.0, 300}}};
    CHECK(code_of([&] { ex::algo_liquidity_seek(ex::Side::Buy, 10, -1, 0, bad_order); }) == "E_INPUT");  // HR-66
    CHECK(code_of([&] { ex::algo_liquidity_seek(ex::Side::Sell, 10, 101, 0, bad_order); }) == "E_DOMAIN");
    CHECK(code_of([] { ex::algo_liquidity_seek(ex::Side::Buy, 10, 101, 1, {{{-1, 3}}}); }) == "E_DOMAIN");
    CHECK(code_of([] { ex::algo_liquidity_seek(ex::Side::Buy, 10, 101, 1, {}); }) == "E_INPUT");
    const ex::Seek none = ex::algo_liquidity_seek(ex::Side::Buy, 10, 99, 1, {{{100, 5}}});
    CHECK_FALSE(none.avg_fill_price.has_value());
    CHECK(none.residual == 10);
}

TEST_CASE("attribution: delay + impact + spread is the executed shortfall and the total matches tca.shortfall") {
    U r(seed);
    for (int t = 0; t < 1000; ++t) {
        const ex::Side side = r.side();
        const double s = side == ex::Side::Buy ? 1 : -1;
        const double pd = r.u(1, 1000), m0 = r.u(1, 1000), pc = r.u(1, 1000);
        std::vector<ex::AttrFill> fills((std::size_t)r.i(1, 50));
        std::vector<ex::Fill> plain;
        double filled = 0;
        for (ex::AttrFill& f : fills) {
            f.quantity = r.u(1, 1000);
            f.price = r.u(1, 1000);
            f.mid = r.u(1, 1000);
            plain.push_back({f.quantity, f.price});
            filled += f.quantity;
        }
        const double x = filled * r.u(1, 2), fees = r.u(0, 100);
        const ex::Attribution a = ex::tca_attribution(side, pd, m0, pc, x, fills, fees);
        const double bound = 1e-10 * std::max(1.0, std::fabs(a.total));
        double direct = 0;
        for (const ex::AttrFill& f : fills) direct += f.quantity * (f.price - pd);
        CHECK(std::fabs(a.delay + a.impact + a.spread - s * direct) <= bound);
        const ex::Shortfall sf = ex::shortfall(side, pd, m0, pc, x, plain, fees, std::nullopt);
        CHECK(std::fabs(a.total - sf.total) <= bound);
        CHECK(std::fabs(a.execution - sf.execution) <= bound);
    }
    const auto attr = [](double x, double q, double pd) {
        return code_of([&] { ex::tca_attribution(ex::Side::Buy, pd, 1, 1, x, {{q, 1, 1}}, 0); });
    };
    CHECK(attr(0, 1, -1) == "E_INPUT");
    CHECK(attr(1, 0, -1) == "E_INPUT");
    CHECK(attr(1, 2, -1) == "E_INPUT");  // HR-66: over-fill before any price check
    CHECK(attr(1, 1, -1) == "E_DOMAIN");
    const ex::Attribution sell = ex::tca_attribution(ex::Side::Sell, 100, 100, 100, 10, {{10, 100, 100}}, 0);
    CHECK_FALSE(std::signbit(sell.delay));  // + 0.0: no negative zero
    CHECK_FALSE(std::signbit(sell.spread));
}

TEST_CASE("pre-trade: impact monotone in X and p, timing risk non-increasing in p") {
    U r(seed + 5);
    for (int t = 0; t < 1000; ++t) {
        const double adv = r.u(1e5, 1e8), sig = r.u(0.001, 0.1);
        const ex::PretradeParams k{r.u(1, 1000), r.u(0, 2), r.u(0.1, 2), r.u(0, 2), r.u(0, 1)};
        const double xa = r.u(1, 1e6), xb = r.u(1, 1e6), pa = r.u(0.01, 0.99), pb = r.u(0.01, 0.99);
        const double x1 = std::min(xa, xb), x2 = std::max(xa, xb), p1 = std::min(pa, pb), p2 = std::max(pa, pb);
        const auto lo = ex::tca_pretrade(x1, adv, sig, p1, 1, k, std::nullopt);
        const auto bx = ex::tca_pretrade(x2, adv, sig, p1, 1, k, std::nullopt);
        const auto hi = ex::tca_pretrade(x1, adv, sig, p2, 1, k, std::nullopt);
        CHECK(lo.impact_bps <= bx.impact_bps * (1 + 1e-14));
        CHECK(lo.impact_bps <= hi.impact_bps * (1 + 1e-14));
        CHECK(lo.timing_risk_bps >= hi.timing_risk_bps * (1 - 1e-14));
        CHECK_FALSE(lo.expected_cost.has_value());
    }
    const ex::PretradeParams k{700, 1, 1, 0.5, 1};
    const auto pre = [&](double x, double sigma, double p, ex::PretradeParams q, std::optional<double> price) {
        return code_of([&] { ex::tca_pretrade(x, 1e6, sigma, p, 0, q, price); });
    };
    CHECK(pre(0, -1, 1, k, std::nullopt) == "E_INPUT");  // HR-66
    CHECK(pre(1, -1, 0.5, k, std::nullopt) == "E_DOMAIN");
    CHECK(pre(1, 0.02, 1, k, std::nullopt) == "E_DOMAIN");
    CHECK(pre(1, 0.02, 0.5, {0, 1, 1, 0.5, 1}, std::nullopt) == "E_DOMAIN");
    CHECK(pre(1, 0.02, 0.5, k, -1.0) == "E_DOMAIN");
    CHECK(pre(1, 0, 0.5, {700, 1, 0, 0.5, 1}, std::nullopt) == "E_DOMAIN");
    const auto priced = ex::tca_pretrade(1e5, 1e6, 0.02, 0.04, 2, k, 50.0);
    REQUIRE(priced.expected_cost.has_value());
    CHECK(rel(*priced.expected_cost, priced.expected_cost_bps * 1e5 * 50 / 1e4));
}

TEST_CASE("wave 2 execution CLI: integer UNITS output, nulls, optional price, limits, schema, non-finite") {
    const auto has = [](const std::string& s, const std::string& what) { return s.find(what) != std::string::npos; };
    CHECK(has(run("exec.algo.arrival", R"({"quantity":10,"n_buckets":3,"urgency":0.5,"mode":"UNITS"})"),
              R"("slices":[)"));
    CHECK(has(run("exec.algo.arrival", R"({"quantity":10,"n_buckets":3,"urgency":0.5,"mode":"UNITS"})"), "[5,3,2]"));
    CHECK(has(run("exec.algo.arrival", R"({"quantity":10,"n_buckets":100001,"urgency":0.5})"), "E_LIMIT"));
    CHECK(has(run("exec.algo.pair", R"({"leg_a":{"side":"BUY","quantity":10,"price":1},"leg_b":{"side":"SELL","price":1},"pair_mode":"CASH_BALANCED","n_buckets":100001})"),
              "E_LIMIT"));
    CHECK(has(run("exec.algo.basket", R"({"legs":[{"side":"BUY","quantity":10,"price":1}],"n_buckets":100001})"),
              "E_LIMIT"));
    CHECK(has(run("exec.algo.basket", R"({"legs":[{"side":"BUY","quantity":10,"price":1}],"n_buckets":2,"mode":"UNITS"})"),
              R"("slices":[[5,5]])"));
    CHECK(has(run("exec.algo.basket", R"({"legs":[1],"n_buckets":2})"), "E_SCHEMA"));
    CHECK(has(run("exec.algo.liquidity_seek", R"({"side":"BUY","quantity":10,"limit_price":99,"take_fraction":1,"books":[[[100,5]]]})"),
              R"("avg_fill_price":null)"));
    CHECK(has(run("exec.algo.liquidity_seek", R"({"side":"BUY","quantity":10,"limit_price":99,"take_fraction":1,"books":[[[100]]]})"),
              "E_SCHEMA"));
    CHECK(has(run("exec.algo.liquidity_seek", R"({"side":"BUY","quantity":10,"limit_price":99,"take_fraction":1,"books":[5]})"),
              "E_SCHEMA"));
    CHECK(has(run("exec.algo.liquidity_seek", R"({"side":"BUY","quantity":10,"limit_price":99,"take_fraction":1,"books":5})"),
              "E_SCHEMA"));
    CHECK(has(run("exec.algo.close", R"({"quantity":10,"close_volume":4,"auction_participation":0.5,"profile":[1,1],"mode":"UNITS"})"),
              R"("auction_quantity":2)"));
    CHECK(has(run("exec.algo.pair", R"({"leg_a":5,"leg_b":{"side":"SELL","price":1},"pair_mode":"HEDGED","n_buckets":2})"),
              "E_SCHEMA"));
    const std::string pre =
        R"({"quantity":100000,"adv":1000000,"daily_vol":0.02,"participation":0.04,"half_spread_bps":2,"params":{"a1":700,"a2":1,"a3":1,"a4":0.5,"b1":1})";
    CHECK_FALSE(has(run("exec.tca.pretrade", pre + "}"), "expected_cost\":"));
    CHECK(has(run("exec.tca.pretrade", pre + R"(,"price":50})"), R"("timing_risk":)"));
    CHECK(has(run("exec.tca.pretrade", R"({"quantity":1,"adv":1,"daily_vol":1,"participation":0.5,"half_spread_bps":0,"params":[1]})"),
              "E_SCHEMA"));
    CHECK(has(run("exec.tca.pretrade", R"({"quantity":1e999,"adv":1,"daily_vol":1,"participation":0.5,"half_spread_bps":0,"params":{"a1":1,"a2":1,"a3":1,"a4":1,"b1":1}})"),
              R"("error")"));
    const std::string attr =
        R"({"side":"SELL","decision_price":100,"arrival_mid":100,"end_price":100,"order_quantity":10,"fills":)";
    CHECK(has(run("exec.tca.attribution", attr + R"([{"quantity":5,"price":100,"mid":100}]})"), R"("fees":0)"));
    CHECK(has(run("exec.tca.attribution", attr + R"([5]})"), "E_SCHEMA"));
    CHECK(has(run("exec.tca.attribution", attr + R"(5})"), "E_SCHEMA"));
}
