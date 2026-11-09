#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <cmath>

#include "quantforge/core/error.hpp"
#include "quantforge/core/rates_vol.hpp"
#include "quantforge/core/commodity.hpp"
#include "quantforge/core/mbs.hpp"

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
    for (int y = 1; y <= 15; ++y) {
        const Date x = add_months(as_of, 12 * y);
        p.push_back({x, std::exp(-r * days_between(as_of, x) / 365.0)});
    }
    return Curve(as_of, CurveInterpolation::LogLinearDf, p);
}
}  // namespace

TEST_CASE("caps, floors and swaptions") {
    const Curve dc = flat(0.035), pc = flat(0.038);
    const auto cap = cap_price(dc, pc, RateVolModel::Black76, {0.2}, true, 1.0, 3, 24, 0.038, 1e6);
    const auto floor = cap_price(dc, pc, RateVolModel::Black76, {0.2}, true, -1.0, 3, 24, 0.038, 1e6);
    REQUIRE(cap.caplets.size() == 8);
    double sum = 0.0;
    for (const double c : cap.caplets) sum += c;
    CHECK(cap.price == Approx(sum).epsilon(1e-15));
    // Cap - floor = swap of forwards over strike (put-call parity per caplet).
    double parity = 0.0;
    const Date start = adjust(Calendar::Usgs, add_months(add_business_days(Calendar::Usgs, as_of, 2), 3), BusinessDayConvention::ModifiedFollowing);
    for (const Period& p : generate_schedule(start, add_months(start, 24), 3, Calendar::Usgs, false, 0)) {
        const double a = year_fraction(DayCount::Act360, p.start, p.end), f = (pc.discount(p.start) / pc.discount(p.end) - 1) / a;
        parity += 1e6 * a * dc.discount(p.end) * (f - 0.038);
    }
    CHECK(cap.price - floor.price == Approx(parity).margin(1e-8));
    const auto quoted = cap_price(dc, pc, RateVolModel::Black76, std::vector<double>(8, 0.2), false, 1.0, 3, 24, 0.038, 1e6);
    CHECK(quoted.price == Approx(cap.price).epsilon(1e-15));
    CHECK(code_of([&] { cap_price(dc, pc, RateVolModel::Black76, {0.2}, true, 1, 0, 24, 0.038, 1); }) == "E_INPUT");
    CHECK(code_of([&] { cap_price(dc, pc, RateVolModel::Black76, {0.2, 0.2}, false, 1, 3, 24, 0.038, 1); }) == "E_INPUT");
    CHECK(code_of([&] { cap_price(dc, pc, RateVolModel::Black76, {-0.2}, true, 1, 3, 24, 0.038, 1); }) == "E_DOMAIN");
    CHECK(code_of([&] { cap_price(dc, pc, RateVolModel::Black76, {0.2}, true, 1, 3, 24, 0.0, 1); }) == "E_DOMAIN");
    CHECK(cap_price(dc, pc, RateVolModel::Bachelier, {0.008}, true, 1, 3, 24, -0.01, 1).price > 0.0);

    const auto pay = swaption_price(dc, pc, RateVolModel::Black76, 0.2, 1.0, 12, 60, 0.037, 1e6);
    const auto rec = swaption_price(dc, pc, RateVolModel::Black76, 0.2, -1.0, 12, 60, 0.037, 1e6);
    CHECK(pay.price - rec.price == Approx(1e6 * pay.annuity * (pay.forward_rate - 0.037)).margin(1e-8));
    CHECK(code_of([&] { swaption_price(dc, pc, RateVolModel::Black76, 0.2, 1, 0, 60, 0.037, 1); }) == "E_INPUT");
    CHECK(code_of([&] { swaption_price(dc, pc, RateVolModel::Black76, -0.2, 1, 12, 60, 0.037, 1); }) == "E_DOMAIN");
}

TEST_CASE("commodity forwards and storage carry") {
    const long long dec = 12LL * 2026 + 11;
    const std::vector<CommodityQuote> q{{dec, 3.4}, {dec + 3, 3.1}};
    auto f = commodity_forwards(q, std::nullopt, {dec, dec + 1, dec + 3});
    CHECK(f[0] == Approx(3.4).epsilon(1e-15));
    CHECK(f[1] == Approx(std::exp(std::log(3.4) + (std::log(3.1) - std::log(3.4)) / 3)).epsilon(1e-15));
    std::vector<double> s(12, 0.0);
    s[11] = 0.05;
    s[0] = 0.04;
    f = commodity_forwards(q, s, {dec, dec + 1, dec + 3});
    CHECK(f[0] == Approx(3.4).epsilon(1e-15));  // quotes reprice
    CHECK(f[2] == Approx(3.1).epsilon(1e-15));
    CHECK(code_of([&] { commodity_forwards(q, std::nullopt, {dec + 4}); }) == "E_OUT_OF_RANGE");
    CHECK(code_of([&] { commodity_forwards({q[1], q[0]}, std::nullopt, {dec}); }) == "E_INPUT");
    CHECK(code_of([&] { commodity_forwards({{dec, 0.0}}, std::nullopt, {dec}); }) == "E_DOMAIN");
    CHECK(code_of([&] { commodity_forwards(q, std::vector<double>(11, 0.0), {dec}); }) == "E_INPUT");

    const Curve c = flat(0.04);
    const auto r = storage_carry(c, {{d("2027-01-06"), 70.0}, {d("2027-07-06"), 75.0}}, 0.01);
    const double dt = days_between(d("2027-01-06"), d("2027-07-06")) / 365.0;
    CHECK(r.convenience_yields[0] == Approx(0.04 + 0.01 - std::log(75.0 / 70.0) / dt).margin(1e-12));
    CHECK(r.arbitrage[0] == (r.carry_values[0] > 0.0));
    CHECK(r.arbitrage[0]);  // contango beyond carry
    CHECK(code_of([&] { storage_carry(c, {{d("2027-01-06"), 70.0}}, 0.0); }) == "E_INPUT");
    CHECK(code_of([&] { storage_carry(c, {{d("2027-01-06"), 70.0}, {d("2027-07-06"), 75.0}}, -0.1); }) == "E_DOMAIN");
}

TEST_CASE("MBS cash flows and price") {
    MbsPool p{1e6, 0.06, 0.06, 12, 0, false, 0.0};
    const auto c = mbs_cashflows(p);
    // No prepayment: level pay.
    const double pay = 1e6 * 0.005 / (1 - std::pow(1.005, -12));
    CHECK(c.scheduled_principal[0] + c.interest[0] == Approx(pay).epsilon(1e-13));
    CHECK(c.prepayment[0] == 0.0);
    double total = 0.0;
    for (std::size_t k = 0; k < 12; ++k) total += c.scheduled_principal[k] + c.prepayment[k];
    CHECK(total == Approx(1e6).epsilon(1e-13));
    // At the WAC yield, no delay and net = WAC, a level-pay pool prices at par.
    CHECK(mbs_price(p, 0.06, 0).price == Approx(100.0).epsilon(1e-13));
    // PSA ramp: 100 PSA reaches 6% CPR at age 30.
    MbsPool psa{1e6, 0.065, 0.06, 360, 29, true, 100.0};
    const auto pc = mbs_cashflows(psa);
    const double smm = 1 - std::pow(1 - 0.06, 1.0 / 12.0);
    CHECK(pc.prepayment[0] == Approx(smm * (pc.balance[0] - pc.scheduled_principal[0])).epsilon(1e-14));
    CHECK(mbs_price(psa, 0.055, 24).price < mbs_price(psa, 0.055, 0).price);
    CHECK(code_of([] { mbs_cashflows({1e6, 0.06, 0.07, 12, 0, false, 0.0}); }) == "E_INPUT");
    CHECK(code_of([] { mbs_cashflows({1e6, 0.06, 0.05, 0, 0, false, 0.0}); }) == "E_INPUT");
    CHECK(code_of([] { mbs_cashflows({1e6, 0.0, 0.05, 12, 0, false, 0.0}); }) == "E_DOMAIN");
    CHECK(code_of([] { mbs_cashflows({1e6, 0.06, 0.05, 12, 0, false, 1.0}); }) == "E_DOMAIN");
    CHECK(code_of([] { mbs_cashflows({1e6, 0.06, 0.05, 12, 0, true, -1.0}); }) == "E_DOMAIN");
    CHECK(code_of([&] { mbs_price(p, 0.06, -1); }) == "E_INPUT");
}
