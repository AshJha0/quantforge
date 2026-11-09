#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <cmath>

#include "quantforge/core/credit.hpp"
#include "quantforge/core/equity_carry.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/inflation.hpp"
#include "quantforge/core/multicurve.hpp"

using namespace quantforge;
using Catch::Approx;

namespace {
Date d(const char* s) { return *parse_date(s); }
std::string code_of(auto&& f) {
    try { f(); } catch (const Error& e) { return e.code(); }
    return "none";
}
const Date as_of = d("2026-11-06");
Curve flat(double r) {
    std::vector<Pillar> p;
    for (int y = 1; y <= 12; ++y) {
        const Date x = add_months(as_of, 12 * y);
        p.push_back({x, std::exp(-r * days_between(as_of, x) / 365.0)});
    }
    return Curve(as_of, CurveInterpolation::LogLinearDf, p);
}
}  // namespace

TEST_CASE("cross-currency legs, bootstrap and NDF") {
    const auto s = xccy_schedule(d("2026-11-10"), 12);
    REQUIRE(s.size() == 5);
    const Curve c = flat(0.03);
    CHECK(xccy_leg(s, 1.0, c, c, 0.0) == Approx(0.0).margin(1e-15));  // flat leg on one curve is worth 0
    CHECK(code_of([] { xccy_schedule(d("2026-11-11"), 12); }) == "E_INPUT");  // US holiday
    CHECK(code_of([] { xccy_schedule(d("2026-11-10"), 4); }) == "E_INPUT");
    // Zero spreads on the projection curve itself give that curve back.
    const auto b = xccy_bootstrap(c, d("2026-11-10"), {{12, 0.0}, {24, 0.0}, {60, 0.0}}, CurveInterpolation::LogLinearDf);
    CHECK(b.max_repricing_error < 1e-13);
    for (const Pillar& p : b.curve.pillars()) CHECK(p.discount_factor == Approx(c.discount(p.date)).epsilon(1e-12));
    CHECK(code_of([&] { xccy_bootstrap(c, d("2026-11-10"), {{24, 0.0}, {12, 0.0}}, CurveInterpolation::LogLinearDf); }) == "E_INPUT");

    const Curve off = flat(0.06);
    const Date pay = d("2027-05-10");
    const auto n = ndf_price(c, off, 88.0, d("2027-05-06"), pay, 90.0, 1e6, 1.0, std::nullopt);
    CHECK(n.forward == Approx(88.0 * c.discount(pay) / off.discount(pay)).epsilon(1e-15));
    CHECK(n.pv == Approx(1e6 * (1 - 90.0 / n.forward) * c.discount(pay)).epsilon(1e-14));
    CHECK(ndf_price(c, off, 88.0, d("2027-05-06"), pay, 90.0, 1e6, 1.0, 90.0).pv == 0.0);
    CHECK(code_of([&] { ndf_price(c, off, 88, pay, d("2027-05-06"), 90, 1, 1, std::nullopt); }) == "E_DATE_ORDER");
    CHECK(code_of([&] { ndf_price(c, off, 88, as_of, pay, 90, 1, 1, std::nullopt); }) == "E_INPUT");
    CHECK(code_of([&] { ndf_price(c, off, 0, d("2027-05-06"), pay, 90, 1, 1, std::nullopt); }) == "E_DOMAIN");
}

TEST_CASE("ISDA CDS: bootstrap reprices, price identities, checks") {
    const Curve p = flat(0.035);
    CHECK(cds_maturity(as_of, {5, 'Y'}) == d("2031-12-20"));
    CHECK(cds_maturity(d("2026-03-19"), {1, 'Y'}) == d("2026-12-20"));
    const std::vector<CdsQuote> q{{{1, 'Y'}, 0.006}, {{5, 'Y'}, 0.012}};
    const HazardCurve h = cds_bootstrap(as_of, p, 0.4, q);
    REQUIRE(h.dates.size() == 2);
    CHECK(h.dates[1] == d("2031-12-20"));
    for (std::size_t j = 0; j < q.size(); ++j) {
        const auto r = cds_price(as_of, p, h, 0.4, h.dates[j], 0.01, 1e7, CdsSide::Buy, CdsPayout::Standard);
        CHECK(r.par_spread == Approx(q[j].spread).margin(1e-13));
    }
    const auto buy = cds_price(as_of, p, h, 0.4, h.dates[1], 0.01, 1e7, CdsSide::Buy, CdsPayout::Standard);
    const auto sell = cds_price(as_of, p, h, 0.4, h.dates[1], 0.01, 1e7, CdsSide::Sell, CdsPayout::Standard);
    CHECK(buy.pv == -sell.pv);
    CHECK(buy.accrued == Approx(0.01 * 47 / 360.0).epsilon(1e-15));  // 2026-09-21 to 2026-11-07 + 1
    const auto dig = cds_price(as_of, p, h, 0.4, h.dates[1], 0.01, 1e7, CdsSide::Buy, CdsPayout::Digital);
    CHECK(dig.protection_leg == Approx(buy.protection_leg / 0.6).epsilon(1e-14));
    CHECK(code_of([&] { cds_bootstrap(as_of, p, 1.0, q); }) == "E_DOMAIN");
    CHECK(code_of([&] { cds_bootstrap(as_of, p, 0.4, {q[1], q[0]}); }) == "E_INPUT");
    CHECK(code_of([&] { cds_bootstrap(as_of, p, 0.4, {{{1, 'Y'}, 0.0}}); }) == "E_DOMAIN");
    const Curve p2(d("2026-12-21"), CurveInterpolation::LogLinearDf, {{d("2030-01-01"), 0.9}});
    CHECK(code_of([&] { cds_bootstrap(d("2026-12-21"), p2, 0.4, q); }) == "E_INPUT");  // adjusted coupon date
    CHECK(code_of([&] { HazardCurve{as_of, {d("2027-01-01")}, {0.0}}.check(); }) == "E_DOMAIN");
}

TEST_CASE("equity carry, implied borrow and financing, TRS") {
    const Curve f = flat(0.04);
    const Date t = d("2027-11-06");
    const EquityCarry plain{f, 0.0, 0.0};
    CHECK(plain.forward(100.0, {}, t) == Approx(100.0 / f.discount(t)).epsilon(1e-15));
    const std::vector<CashDividend> divs{{d("2027-03-19"), 2.0}, {d("2026-01-01"), 50.0}};
    const double fwd = EquityCarry{f, 0.003, 0.0}.forward(100.0, divs, t);
    CHECK(implied_borrow(100.0, f, divs, t, fwd) == Approx(0.003).margin(1e-14));
    CHECK(code_of([&] { implied_borrow(100.0, f, divs, t, 1e6); }) == "E_NOT_BRACKETED");
    const auto basis = equity_futures_basis(100.0, f, 0.003, 0.001, divs, t, fwd);
    CHECK(basis.implied_financing_spread == Approx(0.0).margin(1e-14));
    CHECK(basis.basis == Approx(fwd - basis.fair_price).epsilon(1e-15));
    CHECK(code_of([&] { equity_futures_basis(100.0, f, 0, 0, divs, as_of, 100); }) == "E_DATE_ORDER");
    const auto imp = implied_dividends(100.0, f, 0.0, {{t, plain.forward(100.0, {}, t)}});
    CHECK(imp.pv_dividends[0] == Approx(0.0).margin(1e-12));
    CHECK(code_of([&] { implied_dividends(100.0, f, 0.0, {{t, 0.0}}); }) == "E_DOMAIN");
    CHECK(code_of([&] { implied_dividends(100.0, f, 0.0, {{t, 1.0}, {t, 1.0}}); }) == "E_INPUT");

    const TrsTrade trade{d("2026-09-18"), t, 95.0, 10.0, 0.0045, 1.0};
    const auto r = trs_price(100.0, f, 0.0, {}, trade, 0.04);
    CHECK(r.funding_leg == Approx(10 * 95 * 0.0445 * days_between(trade.start, t) / 360.0 * f.discount(t)).epsilon(1e-14));
    CHECK(r.pv == r.equity_leg - r.funding_leg);
    CHECK(code_of([&] { trs_price(100.0, f, 0.0, {}, trade, std::nullopt); }) == "E_INPUT");
}

TEST_CASE("index dividends, rebalance and corporate actions") {
    const std::vector<Constituent> cs{{"A", 100, 10, {{d("2027-01-04"), 1.0}}}, {"B", 50, 20, {{d("2027-01-04"), 2.0}, {d("2027-07-01"), 1.0}}}};
    const auto r = index_dividends(10.0, cs, {{d("2027-01-04"), d("2027-06-30")}}, {25.0});
    CHECK(r.level == 200.0);
    REQUIRE(r.ex_dates.size() == 2);
    CHECK(r.points[0] == 20.0);
    CHECK(r.period_points[0] == 20.0);  // start included, July excluded
    CHECK(r.basis[0] == 5.0);
    CHECK(code_of([&] { index_dividends(0.0, cs, {}, {}); }) == "E_DOMAIN");
    CHECK(code_of([&] { index_dividends(1.0, cs, {{d("2027-02-01"), d("2027-01-01")}}, {0}); }) == "E_DATE_ORDER");
    CHECK(code_of([&] { index_dividends(1.0, cs, {}, {1.0}); }) == "E_INPUT");
    const auto rb = index_rebalance(10.0, cs, {{"A", 200, 10, {}}});
    CHECK(rb.new_divisor == Approx(10.0).epsilon(1e-15));
    CHECK(rb.weights[0] == 1.0);
    CHECK(code_of([&] { index_rebalance(10.0, {cs[0], cs[0]}, cs); }) == "E_INPUT");
    auto a = corporate_action(CorporateAction::Split, 90, 100, 60, 3, 0);
    CHECK(a.ex_price == Approx(30).epsilon(1e-15));
    CHECK(a.adjusted_shares == Approx(300).epsilon(1e-15));
    a = corporate_action(CorporateAction::Rights, 10, 100, 10, 1, 6);
    CHECK(a.ex_price == Approx(8).epsilon(1e-15));
    a = corporate_action(CorporateAction::SpecialDividend, 10, 100, 10, 2, 0);
    CHECK(a.factor == Approx(0.8).epsilon(1e-15));
    CHECK(code_of([] { corporate_action(CorporateAction::SpecialDividend, 10, 1, 1, 10, 0); }) == "E_DOMAIN");
    CHECK(code_of([] { corporate_action(CorporateAction::Rights, 10, 1, 1, 1, 0); }) == "E_DOMAIN");
    CHECK(code_of([] { corporate_action(CorporateAction::ReverseSplit, 10, 1, 1, 0, 0); }) == "E_DOMAIN");
}

TEST_CASE("CPI curve, ZCIS and linkers") {
    const long long b = month_index(d("2026-08-01"));
    CpiCurve c{b, 300.0, {{1, 0.03}, {2, 0.025}}, std::nullopt};
    c.check();
    CHECK(c.cpi(b) == 300.0);
    CHECK(c.cpi(b + 12) == Approx(309.0).epsilon(1e-14));
    CHECK(c.cpi(b + 6) == Approx(std::sqrt(300.0 * 309.0)).epsilon(1e-14));
    CHECK(c.cpi(b + 24) == Approx(300.0 * 1.025 * 1.025).epsilon(1e-14));
    CHECK(code_of([&] { c.cpi(b - 1); }) == "E_OUT_OF_RANGE");
    CpiCurve s = c;
    s.seasonality = std::vector<double>{1.01, 1, 1, 1, 1, 1, 1, 0.99, 1, 1, 1, 1};
    CHECK(s.cpi(b + 12) == Approx(309.0).epsilon(1e-14));  // the factors cancel on pillars
    CHECK(s.cpi(b + 5) == Approx(c.cpi(b + 5) * 1.01 / 0.99).epsilon(1e-14));
    CHECK(code_of([&] { CpiCurve{b, 300, {{1.5, 0.03}}, std::nullopt}.check(); }) == "E_INPUT");
    CHECK(code_of([&] { CpiCurve{b, 300, {{1, -1.0}}, std::nullopt}.check(); }) == "E_DOMAIN");
    CHECK(code_of([&] { CpiCurve{b, 300, {{1, 0.03}}, std::vector<double>(11, 1.0)}.check(); }) == "E_INPUT");
    CHECK(code_of([&] { CpiCurve{b, 300, {{1, 0.03}}, std::vector<double>(12, 0.0)}.check(); }) == "E_DOMAIN");

    const Curve disc = flat(0.04);
    const auto z = zcis_price(c, disc, 2, 0.025 * 1.0, 1e6, 1.0, d("2028-11-10"));
    CHECK(z.pv == Approx(1e6 * (1.025 * 1.025 - std::pow(1.025, 2)) * disc.discount(d("2028-11-10"))).margin(1e-6));

    const std::vector<CpiFixing> fx{{month_index(d("2026-08-01")), 300.0}, {month_index(d("2026-09-01")), 303.0}};
    const Bond bond{d("2029-11-15"), 0.02, 2};
    const auto l = linker_price(bond, d("2026-11-16"), 0.015, 290.0, fx);
    CHECK(l.ref_cpi == Approx(300.0 + 15.0 / 30.0 * 3.0).epsilon(1e-15));
    CHECK(l.nominal_clean == Approx(l.real_clean * l.ref_cpi / 290.0).epsilon(1e-15));
    CHECK(code_of([&] { linker_price(bond, d("2026-12-16"), 0.015, 290.0, fx); }) == "E_INPUT");
    CHECK(linker_price_curve(bond, d("2026-11-16"), 300.0, c, disc) > 0.0);
    CHECK(code_of([&] { linker_price_curve(bond, d("2026-11-16"), 300.0, CpiCurve{b + 12, 300, {{1, 0.03}}, std::nullopt}, disc); }) == "E_OUT_OF_RANGE");
}

TEST_CASE("ruling D52: hazard survival range and maturity") {
    const Curve p = flat(0.035);
    CHECK(code_of([] { HazardCurve{as_of, {d("2027-01-01")}, {1.01}}.check(); }) == "E_DOMAIN");
    HazardCurve{as_of, {d("2027-01-01")}, {1.0}}.check();
    const HazardCurve h{as_of, {d("2031-12-20")}, {0.9}};
    CHECK(code_of([&] { cds_price(as_of, p, h, 0.4, as_of, 0.01, 1, CdsSide::Buy, CdsPayout::Standard); }) == "E_INPUT");
}
