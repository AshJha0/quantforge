// Unit tests aimed at the stage I hedging mutants the goldens left alive (PR #35 mutation gate): each check pins
// one boundary of a comparison exactly, so flipping < and <= changes the answer. The exact-boundary inputs were
// found by search in IEEE double arithmetic and are noted where they are used.
// No namespace-scope static objects (static-init order has broken ASan before): fixtures are built by functions.
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <optional>
#include <string>
#include <vector>

#include "quantforge/core/credit.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/hedging.hpp"

using namespace quantforge;
namespace hg = quantforge::hedging;

namespace {

struct Caught {
    std::string code = "ok", field, message;
};

Caught catch_error(auto&& run) {
    Caught c;
    try {
        run();
    } catch (const Error& e) {
        c.code = e.code();
        c.field = e.field();
        c.message = e.what();
    }
    return c;
}

Curve flat_discount(Date as_of, double r) {
    std::vector<Pillar> p;
    for (int y = 1; y <= 12; ++y) {
        const Date x = add_months(as_of, 12 * y);
        p.push_back({x, std::exp(-r * days_between(as_of, x) / 365.0)});
    }
    return Curve(as_of, CurveInterpolation::LogLinearDf, p);
}

hg::TwoAssetMarket two_asset_market() { return {100.0, 95.0, 0.03, 0.01, 0.02, 0.25, 0.3, 0.4}; }
hg::TwoAssetPosition exchange_option(double q1, double q2) { return {hg::TwoAssetKind::Exchange, q1, q2, 0.0, 1.0, 1.0}; }

}  // namespace

TEST_CASE("hedge credit: a hazard bumped to exactly 0 is allowed; below 0 is E_DOMAIN (R6-11.9)", "[mutants]") {
    const Date as_of = make_date(2026, 11, 6);
    // 2605 days and this survival give -ln(Q) / t == 1e-4 exactly, the bump size at recovery 0, so the downward
    // bump leaves a hazard of exactly 0.
    const HazardCurve exact{as_of, {make_date(2033, 12, 24)}, {0.9992865559921522}};
    REQUIRE(-std::log(exact.survival[0]) / (2605.0 / 365.0) == 1e-4);
    const Curve disc = flat_discount(as_of, 0.03);
    const Caught at_zero = catch_error(
        [&] { (void)hg::unit_credit_risk(as_of, disc, exact, 0.0, make_date(2031, 12, 20), 0.01); });
    CHECK(at_zero.code == "ok");
    const hg::CreditRisk r = hg::unit_credit_risk(as_of, disc, exact, 0.0, make_date(2031, 12, 20), 0.01);
    REQUIRE(r.buckets.size() == 1);
    CHECK(r.cs01 > 0.0);
    CHECK(r.buckets[0] == r.cs01);  // one section: the bucket bump is the parallel bump
    CHECK(r.jtd == 1.0 - r.pv);
    // A slightly higher survival makes the bumped hazard negative.
    const HazardCurve below{as_of, {make_date(2033, 12, 24)}, {0.99929}};
    const Caught neg = catch_error([&] { (void)hg::unit_credit_risk(as_of, disc, below, 0.0, make_date(2031, 12, 20), 0.01); });
    CHECK(neg.code == "E_DOMAIN");
    CHECK(neg.field == "hazard");
}

TEST_CASE("hedge correlation: exchange quantities of exactly 0 are E_DOMAIN in book and hedges", "[mutants]") {
    const hg::TwoAssetMarket m = two_asset_market();
    const hg::TwoAssetPosition good = exchange_option(1.0, 1.0);
    for (const auto& bad : {exchange_option(0.0, 1.0), exchange_option(1.0, 0.0), exchange_option(-1.0, 1.0)}) {
        const Caught b = catch_error([&] { hg::correlation_hedge(m, {bad}, {good}, {hg::TwoAssetTarget::Delta1}); });
        CHECK(b.code == "E_DOMAIN");
        CHECK(b.field == "book");
        const Caught h = catch_error([&] { hg::correlation_hedge(m, {good}, {bad}, {hg::TwoAssetTarget::Delta1}); });
        CHECK(h.code == "E_DOMAIN");
        CHECK(h.field == "hedges");
    }
    // A tiny positive quantity passes the check.
    CHECK(catch_error([&] { hg::correlation_hedge(m, {exchange_option(1e-300, 1.0)}, {good}, {hg::TwoAssetTarget::Delta1}); })
              .code != "E_DOMAIN");
}

TEST_CASE("hedge correlation: a spread volatility of exactly 0 is E_DOMAIN on correlation; vanillas skip it", "[mutants]") {
    hg::TwoAssetMarket flat = two_asset_market();
    flat.vol1 = flat.vol2 = 0.25;
    flat.correlation = 1.0;  // 0.0625 + 0.0625 - 2 * 0.0625 == 0 exactly
    const hg::TwoAssetPosition ex = exchange_option(1.0, 1.0);
    const Caught e = catch_error([&] { hg::correlation_hedge(flat, {ex}, {ex}, {hg::TwoAssetTarget::Delta1}); });
    CHECK(e.code == "E_DOMAIN");
    CHECK(e.field == "correlation");
    CHECK(e.message == "correlation: the spread volatility is 0");
    // Without an exchange option the zero spread volatility does not matter.
    const hg::TwoAssetPosition u1{hg::TwoAssetKind::Underlying1, 0.0, 0.0, 0.0, 0.0, 2.0};
    const hg::CorrelationHedge h = hg::correlation_hedge(flat, {u1}, {u1}, {hg::TwoAssetTarget::Delta1});
    REQUIRE(h.quantities.size() == 1);
    CHECK(h.quantities[0] == -2.0);
    CHECK(h.after[0] == 0.0);
}

TEST_CASE("hedge effectiveness: item changes summing to exactly 0 are E_DOMAIN (I-31, I-43)", "[mutants]") {
    const Caught z = catch_error([] { (void)hg::effectiveness({1.0, -1.0, 0.0}, {1.0, 2.0, 4.0}); });
    CHECK(z.code == "E_DOMAIN");
    CHECK(z.field == "item_changes");
    CHECK(z.message == "item_changes: sum to zero (I-31, I-43)");
    CHECK(catch_error([] { (void)hg::effectiveness({1.0, -1.0, 0.5}, {1.0, 2.0, 4.0}); }).code == "ok");
    CHECK(catch_error([] { (void)hg::effectiveness({1.0, 2.0}, {1.0, 2.0, 4.0}); }).code == "E_INPUT");
}

TEST_CASE("option hedge lots: half_spread 0 is allowed and costs nothing; negative is E_DOMAIN", "[mutants]") {
    const hg::Market m{100.0, 0.0, 0.0, 0.2};
    const std::vector<hg::Position> book{{hg::Instrument::Underlying, std::nullopt, std::nullopt, -237.0}};
    const hg::Position u{hg::Instrument::Underlying, std::nullopt, std::nullopt, 0.0};
    const hg::LotHedgeResult r = hg::option_hedge_lots(m, book, {{u, 100.0, 0.0}}, {hg::Greek::Delta}, 10);
    REQUIRE(r.lots.size() == 1);
    CHECK(r.lots[0] == 2);
    CHECK(r.hedge_cost == 0.0);
    CHECK(r.after.delta == -37.0);
    const Caught neg = catch_error([&] { hg::option_hedge_lots(m, book, {{u, 100.0, -0.01}}, {hg::Greek::Delta}, 10); });
    CHECK(neg.code == "E_DOMAIN");
    CHECK(neg.field == "hedges");
    CHECK(neg.message == "hedges: half_spread must be at least 0");
    CHECK(catch_error([&] { hg::option_hedge_lots(m, book, {{u, 0.0, 0.0}}, {hg::Greek::Delta}, 10); }).code == "E_DOMAIN");
    CHECK(catch_error([&] { hg::option_hedge_lots(m, book, {{u, 100.0, 0.0}}, {hg::Greek::Delta}, 0); }).field == "max_lots");
}

TEST_CASE("minimum variance: a hedged variance of exactly -1e-12 S_00 reads as 0 (I-44 boundary)", "[mutants]") {
    // S_00 - S_he^2 / S_hh == -1e-12 * S_00 exactly in doubles for this pair (S_hh = 1).
    const double s00 = 0.9094947017729282, she = 0.9536743164067268;
    REQUIRE(s00 - she * she == -1e-12 * s00);
    const hg::MinVarResult r = hg::min_variance({{s00, she}, {she, 1.0}});
    CHECK(r.variance_after == 0.0);
    CHECK(r.effectiveness == 1.0);
    CHECK(r.variance_before == s00);
    REQUIRE(r.hedge.size() == 1);
    CHECK(r.hedge[0] == -she);
    // One step further below is an error.
    const double further = std::nextafter(she, 2.0);
    CHECK(catch_error([&] { hg::min_variance({{s00, further}, {further, 1.0}}); }).code == "E_NOT_POSITIVE_DEFINITE");
}
