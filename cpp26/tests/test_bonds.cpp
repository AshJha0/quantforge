#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <cmath>

#include "quantforge/core/bonds.hpp"
#include "quantforge/core/error.hpp"

using namespace quantforge;
using Catch::Approx;

namespace {
Date d(const char* s) { return *parse_date(s); }
std::string code_of(auto&& f) {
    try { f(); } catch (const Error& e) { return e.code(); }
    return "none";
}
const Bond b5{d("2029-11-15"), 0.0425, 2};
Curve flat(double r) {
    const Date as_of = d("2026-11-06");
    std::vector<Pillar> p;
    for (int y = 1; y <= 10; ++y) {
        const Date x = add_months(as_of, 12 * y);
        p.push_back({x, std::exp(-r * days_between(as_of, x) / 365.0)});
    }
    return Curve(as_of, CurveInterpolation::LogLinearDf, p);
}
}  // namespace

TEST_CASE("bond coupon dates and accrued") {
    const auto p = bond_period(b5, d("2026-11-09"));
    CHECK(p.prev == d("2026-05-15"));
    CHECK(p.next == d("2026-11-15"));
    CHECK(p.flows.size() == 7);
    CHECK(accrued(b5, d("2026-11-15")) == 0.0);
    const Bond eom{d("2031-02-28"), 0.0375, 2};
    CHECK(bond_period(eom, d("2026-11-09")).prev == d("2026-08-31"));
    CHECK(code_of([] { bond_period(b5, d("2029-11-15")); }) == "E_DATE_ORDER");
}

TEST_CASE("price and yield are inverse; par on a coupon date") {
    const auto p = price_from_yield(b5, d("2026-11-15"), 0.0425);
    CHECK(p.clean == Approx(100.0).margin(1e-11));
    CHECK(p.modified_duration == Approx(p.macaulay_duration / (1 + 0.0425 / 2)).epsilon(1e-15));
    const auto q = price_from_yield(b5, d("2026-11-09"), 0.041);
    CHECK(yield_from_price(b5, d("2026-11-09"), q.clean) == Approx(0.041).margin(1e-13));
    // Duration matches a finite difference.
    const double h = 1e-6, up = price_from_yield(b5, d("2026-11-09"), 0.041 + h).dirty,
                 dn = price_from_yield(b5, d("2026-11-09"), 0.041 - h).dirty;
    CHECK(-(up - dn) / (2 * h) / q.dirty == Approx(q.modified_duration).epsilon(1e-8));
    CHECK(code_of([] { price_from_yield(b5, d("2026-11-09"), -2.0); }) == "E_DOMAIN");
    CHECK(code_of([] { yield_from_price(b5, d("2026-11-09"), -1.0); }) == "E_DOMAIN");
}

TEST_CASE("curve price, z-spread and asset swap") {
    const Curve c = flat(0.04);
    const double dirty = curve_dirty(b5, d("2026-11-09"), c, 0.0);
    const double acc = accrued(b5, d("2026-11-09"));
    const double clean_z = curve_dirty(b5, d("2026-11-09"), c, 0.0035) - acc;
    CHECK(z_spread(b5, d("2026-11-09"), c, clean_z) == Approx(0.0035).margin(1e-12));
    CHECK(z_spread(b5, d("2026-11-09"), c, dirty - acc) == Approx(0.0).margin(1e-12));
    const auto a = asset_swap(b5, d("2026-11-09"), c, dirty);
    CHECK(a.spread == Approx(0.0).margin(1e-15));
    CHECK(a.annuity > 2.8);
    CHECK(code_of([&] { curve_dirty(b5, d("2026-11-05"), c, 0.0); }) == "E_OUT_OF_RANGE");
}

TEST_CASE("FRN par identity") {
    const Curve c = flat(0.04);
    const Date s = d("2026-11-16");
    const Date e = add_months(s, 3);
    const double fwd = (c.discount(s) / c.discount(e) - 1.0) / (days_between(s, e) / 360.0);
    const auto p = frn_price({d("2029-11-16"), 4, fwd, 0.0, 0.0}, s, c, c);
    CHECK(p.dirty == Approx(100.0).margin(1e-11));
    CHECK(p.accrued == 0.0);
    CHECK(frn_price({d("2029-11-16"), 4, fwd, 0.001, 0.0}, s, c, c).dirty > 100.0);
}

TEST_CASE("repo forward and implied rate") {
    const auto f = repo_forward(b5, d("2026-11-09"), d("2026-12-09"), 100.4, 0.0385, std::nullopt);
    CHECK(!f.special_spread);
    CHECK(f.interest == Approx(f.dirty * 0.0385 * 30 / 360).epsilon(1e-15));
    CHECK(repo_implied_rate(b5, d("2026-11-09"), d("2026-12-09"), 100.4, f.forward_clean) == Approx(0.0385).margin(1e-14));
    const auto g = repo_forward(b5, d("2026-11-09"), d("2026-12-09"), 100.4, 0.0385, 0.04);
    CHECK(*g.special_spread == Approx(0.0015).margin(1e-16));
    // A coupon inside the term is paid out and reinvested.
    const auto h = repo_forward(b5, d("2026-11-09"), d("2027-01-09"), 100.4, 0.0385, std::nullopt);
    CHECK(h.forward_dirty < h.dirty);
    CHECK(code_of([] { repo_forward(b5, d("2026-12-09"), d("2026-11-09"), 100, 0.03, std::nullopt); }) == "E_DATE_ORDER");
    CHECK(code_of([] { repo_forward(b5, d("2026-12-09"), d("2029-11-15"), 100, 0.03, std::nullopt); }) == "E_INPUT");
}

TEST_CASE("conversion factor and futures basis") {
    CHECK(conversion_factor({d("2033-12-15"), 0.06, 2}, d("2026-12-01"), 0.06) == 1.0);
    CHECK(conversion_factor({d("2033-11-15"), 0.0425, 2}, d("2026-12-01"), 0.06) < 1.0);
    CHECK(code_of([] { conversion_factor({d("2033-11-15"), 0.0425, 2}, d("2026-12-01"), 0.05); }) == "E_INPUT");
    CHECK(code_of([] { conversion_factor({d("2033-11-15"), 0.0425, 1}, d("2026-12-01"), 0.06); }) == "E_INPUT");
    const std::vector<BasisBond> bonds{{{d("2033-11-15"), 0.0425, 2}, 100.6, 0.904}, {{d("2034-02-15"), 0.04, 2}, 99.06, 0.887}};
    const auto basis = futures_basis(104.4, d("2026-11-09"), d("2026-12-01"), 0.0385, bonds);
    CHECK(basis.bonds[0].gross_basis == Approx(100.6 - 104.4 * 0.904).epsilon(1e-15));
    CHECK(basis.ctd == (basis.bonds[1].implied_repo > basis.bonds[0].implied_repo ? 1u : 0u));
    CHECK(code_of([] { futures_basis(100, d("2026-11-09"), d("2026-12-01"), 0.03, {}); }) == "E_INPUT");
}

TEST_CASE("Nelson-Siegel bond fit recovers known betas") {
    const Date s = d("2026-11-09");
    const double tau = 2.5, b[3] = {0.042, -0.006, 0.004};
    std::vector<NsBond> bonds;
    for (int y = 2; y <= 10; y += 2) {
        const Bond bd{add_months(d("2026-11-15"), 12 * y), 0.04, 2};
        const auto p = bond_period(bd, s);
        double dirty = 0.0;
        for (std::size_t k = 0; k < p.flows.size(); ++k) {
            const double t = days_between(s, p.flows[k]) / 365.0, u = t / tau, e = -std::expm1(-u) / u;
            const double z = b[0] + b[1] * e + b[2] * (e - std::exp(-u));
            dirty += (2.0 + (k + 1 == p.flows.size() ? 100.0 : 0.0)) * std::exp(-z * t);
        }
        bonds.push_back({bd, dirty});
    }
    bonds[4].dirty_price += 1.0;  // weight 0: shows its richness only
    const auto fit = bond_nelson_siegel(s, tau, bonds, std::vector<double>{1, 1, 1, 1, 0});
    for (int k = 0; k < 3; ++k) CHECK(fit.betas[k] == Approx(b[k]).margin(1e-10));
    CHECK(fit.residuals[4] == Approx(-1.0).margin(1e-8));
    CHECK(code_of([&] { bond_nelson_siegel(s, tau, bonds, std::vector<double>{1, 1, 0, 0, 0}); }) == "E_INPUT");
    CHECK(code_of([&] { bond_nelson_siegel(s, 0.0, bonds, std::nullopt); }) == "E_DOMAIN");
}

TEST_CASE("conversion factor contracts (ruling R1-3)") {
    const Date dm = d("2026-12-01");
    const Bond b8{d("2031-08-15"), 0.0425, 2};  // n = 4, z = 8 whole months
    // FIVE_YEAR keeps z = 8, so v = z - 6 = 2 and C carries the extra half year.
    const double a = std::pow(1.03, -2.0 / 6.0), c = std::pow(1.03, -9.0);
    const double five = std::nearbyint((a * (0.02125 + (0.0425 / 0.06) * (1 - c) + c) - 0.02125 * 4.0 / 6.0) * 1e4) / 1e4;
    CHECK(conversion_factor(b8, dm, 0.06, FuturesContract::FiveYear) == five);
    // TEN_YEAR rounds z down to 6: v = 6, b = 0, no extra half year.
    const double ten = std::nearbyint((std::pow(1.03, -1.0) * (0.02125 + (0.0425 / 0.06) * (1 - std::pow(1.03, -8.0)) +
                                                               std::pow(1.03, -8.0))) * 1e4) / 1e4;
    CHECK(conversion_factor(b8, dm, 0.06) == ten);
    CHECK(conversion_factor(b8, dm, 0.06, FuturesContract::Bond) == ten);
    // The coupon goes to the 1/8 of 1% grid first, ties up.
    CHECK(conversion_factor({d("2031-08-15"), 0.04240, 2}, dm, 0.06) == ten);
    CHECK(conversion_factor({d("2031-08-15"), 0.044375, 2}, dm, 0.06) ==
          conversion_factor({d("2031-08-15"), 0.045, 2}, dm, 0.06));
}
