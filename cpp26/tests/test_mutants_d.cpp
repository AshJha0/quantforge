// Boundary, error-path and branch tests aimed at mutants that the goldens left alive
// (bonds, credit, equity_d, rates_d). Each check names the condition it pins.
#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <cmath>

#include "quantforge/core/bonds.hpp"
#include "quantforge/core/credit.hpp"
#include "quantforge/core/equity_d.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/rates_d.hpp"

using namespace quantforge;
using Catch::Approx;

namespace {
Date d(const char* s) { return *parse_date(s); }
std::string code_of(auto&& f) {
    try { f(); } catch (const Error& e) { return e.code(); }
    return "none";
}
Curve flat_at(Date as_of, double r) {
    std::vector<Pillar> p;
    for (int y = 1; y <= 12; ++y) {
        const Date x = add_months(as_of, 12 * y);
        p.push_back({x, std::exp(-r * days_between(as_of, x) / 365.0)});
    }
    return Curve(as_of, CurveInterpolation::LogLinearDf, p);
}
const Date as_of = d("2026-11-06");
}  // namespace

TEST_CASE("bonds: boundaries and futures basis arithmetic") {
    // Settlement on the curve's as_of is allowed for an FRN (only strictly before is out of range).
    const Curve c = flat_at(as_of, 0.04);
    CHECK(code_of([&] { frn_price({d("2029-11-06"), 4, 0.04, 0.0, 0.0}, as_of, c, c); }) == "none");
    CHECK(code_of([&] { frn_price({d("2029-11-06"), 4, 0.04, 0.0, 0.0}, d("2026-11-05"), c, c); }) == "E_OUT_OF_RANGE");

    // Invoice = F * CF + accrued at delivery; at r = implied repo the net basis is zero.
    const Date s = d("2026-11-09"), dl = d("2026-12-01");
    const std::vector<BasisBond> bonds{{{d("2033-11-15"), 0.0425, 2}, 100.6, 0.904}, {{d("2034-02-15"), 0.04, 2}, 99.06, 0.887}};
    const auto b = futures_basis(104.4, s, dl, 0.0385, bonds);
    for (std::size_t i = 0; i < bonds.size(); ++i) {
        CHECK(b.bonds[i].invoice == Approx(104.4 * bonds[i].conversion_factor + accrued(bonds[i].bond, dl)).epsilon(1e-15));
        const auto at = futures_basis(104.4, s, dl, b.bonds[i].implied_repo, bonds);
        CHECK(at.bonds[i].net_basis == Approx(0.0).margin(1e-12));
    }
    // A higher repo rate raises the forward, so the net basis rises.
    CHECK(futures_basis(104.4, s, dl, 0.05, bonds).bonds[0].net_basis > b.bonds[0].net_basis);

    // Exactly 3 positive weights is enough for the Nelson-Siegel fit.
    std::vector<NsBond> ns;
    for (int y = 2; y <= 8; y += 2) ns.push_back({{add_months(d("2026-11-15"), 12 * y), 0.04, 2}, 100.0 - y});
    CHECK(code_of([&] { bond_nelson_siegel(s, 2.0, ns, std::vector<double>{1, 1, 1, 0}); }) == "none");
    CHECK(code_of([&] { bond_nelson_siegel(s, 2.0, ns, std::vector<double>{1, 1, 0, 0}); }) == "E_INPUT");

    // Yield above the coupon frequency still round-trips.
    const Bond annual{d("2031-11-15"), 0.05, 1};
    const double y = 1.5;
    CHECK(yield_from_price(annual, s, price_from_yield(annual, s, y).clean) == Approx(y).margin(1e-13));
}

TEST_CASE("credit: schedule start on a weekend IMM date and curve dates") {
    // 2021-03-20 is a Saturday IMM date: the accrual starts on it, so the accrued is at most one day (not a quarter).
    const Date t = d("2021-03-20");
    const Curve p = flat_at(t, 0.01);
    const HazardCurve h{t, {d("2026-03-20")}, {0.95}};
    const auto r = cds_price(t, p, h, 0.4, d("2026-06-20"), 0.01, 1e7, CdsSide::Buy, CdsPayout::Standard);
    CHECK(std::fabs(r.accrued) <= 0.01 * 1.0000001 / 360.0);
    // Either curve on another date is an input error, even when the other matches.
    const Curve p2 = flat_at(d("2021-03-19"), 0.01);
    CHECK(code_of([&] { cds_price(t, p2, h, 0.4, d("2026-06-20"), 0.01, 1, CdsSide::Buy, CdsPayout::Standard); }) == "E_INPUT");
    const HazardCurve h2{d("2021-03-19"), {d("2026-03-20")}, {0.95}};
    CHECK(code_of([&] { cds_price(t, p, h2, 0.4, d("2026-06-20"), 0.01, 1, CdsSide::Buy, CdsPayout::Standard); }) == "E_INPUT");
}

TEST_CASE("equity_d: boundaries") {
    const Curve f = flat_at(as_of, 0.04);
    const Date t = d("2027-11-06");
    const EquityCarry c{f, 0.0, 0.0};
    // A dividend going ex on as_of is already out of the spot.
    CHECK(c.forward(100.0, {{as_of, 5.0}}, t) == c.forward(100.0, {}, t));
    CHECK(c.forward(100.0, {{t, 5.0}}, t) < c.forward(100.0, {}, t));  // ex on expiry counts
    CHECK(code_of([&] { implied_dividends(0.0, f, 0.0, {{t, 100.0}}); }) == "E_DOMAIN");
    // Periods include their end date; a one-day period is valid.
    const std::vector<Constituent> cs{{"A", 100, 10, {{d("2027-01-04"), 1.0}, {d("2027-07-01"), 0.5}}}};
    const auto r = index_dividends(10.0, cs, {{d("2027-01-04"), d("2027-07-01")}, {d("2027-07-01"), d("2027-07-01")}}, {0, 0});
    CHECK(r.period_points[0] == 15.0);
    CHECK(r.period_points[1] == 5.0);
    CHECK(code_of([] { corporate_action(CorporateAction::Rights, 10, 1, 1, 0, 6); }) == "E_DOMAIN");
}

TEST_CASE("rates_d: boundaries") {
    const Curve c = flat_at(as_of, 0.03);
    CHECK(code_of([&] { xccy_bootstrap(c, d("2026-11-10"), {{12, 0.0}, {12, 0.0}}, CurveInterpolation::LogLinearDf); }) == "E_INPUT");
    // start_years = 0 is allowed.
    const auto z = futures_convexity(96.0, 0.0, 0.5, 0.01, 0.0);
    CHECK(z.convexity == Approx(-std::expm1(-0.01 * 0.01 / 2 * 0.0) * (0.04 + 2)).margin(1e-18));
    CHECK(z.futures_rate == Approx(0.04).epsilon(1e-15));
    const Curve off = flat_at(as_of, 0.06);
    CHECK(code_of([&] { ndf_price(c, off, 88, d("2027-05-06"), d("2027-05-10"), 0.0, 1, 1, std::nullopt); }) == "E_DOMAIN");
}
