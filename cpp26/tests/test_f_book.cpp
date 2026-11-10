// Stage F book unit tests. No namespace-scope static objects.
#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include "quantforge/core/book.hpp"
#include "quantforge/core/error.hpp"

using namespace quantforge;
using Catch::Approx;

namespace {

Date day(unsigned d) { return make_date(2026, 11, d); }

BookEvent trade(unsigned d, const char* instrument, double q, double p) {
    BookEvent e;
    e.date = day(d);
    e.instrument = instrument;
    e.quantity = q;
    e.price = p;
    return e;
}

std::string code_of(auto&& f) {
    try {
        f();
    } catch (const Error& e) {
        return e.code();
    }
    return "ok";
}

}  // namespace

TEST_CASE("weighted average cost: add then partial reduce", "[f5]") {
    const BookResult r = apply_lifecycle({}, {trade(2, "A", 100, 99.5), trade(3, "A", 50, 100.25), trade(4, "A", -120, 100.5)});
    REQUIRE(r.positions.size() == 1);
    CHECK(r.positions[0].quantity == 30.0);
    CHECK(r.positions[0].average_cost == Approx(99.75));
    CHECK(r.total_realized == Approx(90.0));
}

TEST_CASE("limit cases: close to zero removes, reversal opens at the trade price", "[f5]") {
    const BookResult closed = apply_lifecycle({{"A", 200, 180}}, {trade(5, "A", -200, 190.5)});
    CHECK(closed.positions.empty());
    CHECK(closed.realized.size() == 1);
    CHECK(closed.total_realized == Approx(2100.0));
    const BookResult flip = apply_lifecycle({}, {trade(2, "S", -10, 95.8), trade(3, "S", 15, 95.7)});
    REQUIRE(flip.positions.size() == 1);
    CHECK(flip.positions[0].quantity == 5.0);
    CHECK(flip.positions[0].average_cost == 95.7);
    CHECK(flip.total_realized == Approx(1.0));
}

TEST_CASE("expiry, default and roll", "[f5]") {
    BookEvent roll;
    roll.date = day(10);
    roll.type = BookEventType::Roll;
    roll.instrument = "Z6";
    roll.to = "H7";
    roll.price = 95.82;
    roll.to_price = 96.01;
    const BookResult r = apply_lifecycle({{"Z6", -20, 95.9}}, {roll});
    REQUIRE(r.positions.size() == 1);
    CHECK(r.positions[0].instrument == "H7");
    CHECK(r.positions[0].quantity == -20.0);
    CHECK(r.total_realized == Approx(1.6));
    BookEvent expiry = roll;
    expiry.type = BookEventType::Expiry;
    expiry.instrument = "Z6";
    CHECK(code_of([&] { apply_lifecycle({}, {expiry}); }) == "E_INPUT");
    CHECK(code_of([&] { apply_lifecycle({{"Z6", 1, 1}}, {expiry, trade(11, "Z6", 1, 1)}); }) == "E_INPUT");
    CHECK(code_of([&] { apply_lifecycle({}, {trade(3, "A", 1, 1), trade(2, "A", 1, 1)}); }) == "E_INPUT");
    CHECK(code_of([&] { apply_lifecycle({}, {trade(3, "A", 0, 1)}); }) == "E_DOMAIN");
}

TEST_CASE("marks: primary, fallback, stale, missing and IPV", "[f5]") {
    const std::vector<MarkSource> sources = {
        {"A", {{"X", day(10), 99.75}, {"S", day(7), 6012.5}}},
        {"B", {{"Y", day(10), 131.2}, {"X", day(10), 99.8}, {"S", day(9), 6020.0}, {"I", day(1), 88.0}}}};
    const auto m = resolve_marks(day(10), {"X", "Y", "S", "I"}, sources, 3, {{"X", 99.7}, {"Y", 130.0}}, 0.005);
    CHECK(m[0].status == MarkStatus::Primary);
    CHECK(m[1].status == MarkStatus::Fallback);
    CHECK(m[1].ipv_breach);
    CHECK(m[2].status == MarkStatus::Stale);
    CHECK(*m[2].age_days == 1);
    CHECK(m[3].status == MarkStatus::Missing);
    CHECK(!m[3].price);
    const auto wide = resolve_marks(day(10), {"I"}, sources, 9, {}, 0.005);
    CHECK(wide[0].status == MarkStatus::Stale);
    CHECK(code_of([&] { resolve_marks(day(10), {"X"}, sources, -1, {}, 0.005); }) == "E_DOMAIN");
    CHECK(code_of([&] { resolve_marks(day(10), {"X"}, {sources[0], sources[0]}, 1, {}, 0.005); }) == "E_INPUT");
    CHECK(code_of([&] { resolve_marks(day(10), {"X"}, sources, 1, {{"X", 0.0}}, 0.005); }) == "E_DOMAIN");
}

TEST_CASE("factor attribution: exact fit and the attribution identity", "[f5]") {
    const std::vector<double> f1 = {0.01, -0.02, 0.03, 0.0, 0.015, -0.01};
    const std::vector<double> e = {0.001, -0.001, 0.0005, -0.0002, 0.0, -0.0003};
    Matrix f;
    std::vector<double> y;
    for (std::size_t i = 0; i < f1.size(); ++i) {
        f.push_back({f1[i]});
        y.push_back(0.002 + 0.8 * f1[i] + e[i]);
    }
    const FactorAttribution r = factor_attribution(y, f, 1);
    CHECK(r.alpha + r.contributions[0] == Approx(r.mean_return).margin(1e-15));
    CHECK(r.betas[0] == Approx(0.8).margin(0.1));
    CHECK(r.r_squared > 0.9);
    CHECK(code_of([&] { factor_attribution({0.01, 0.02}, {{0.01}, {0.02}}, 1); }) == "E_INPUT");
    CHECK(code_of([&] { factor_attribution(y, f, 2); }) == "E_INPUT");
    Matrix twin;
    for (const double v : f1) twin.push_back({v, 2 * v});
    CHECK(code_of([&] { factor_attribution(y, twin, 2); }) == "E_DOMAIN");
}
