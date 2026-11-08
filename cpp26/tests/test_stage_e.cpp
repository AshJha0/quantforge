// Stage E unit tests built on identities, so they need no golden values.
#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <numbers>
#include <string>

#include "quantforge/core/credit_e.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/stats.hpp"

using namespace quantforge;
using Catch::Approx;

namespace {
Date d(const char* s) { return *parse_date(s); }
std::string code_of(auto&& f) {
    try { f(); } catch (const Error& e) { return e.code(); }
    return "none";
}
}  // namespace

TEST_CASE("bivariate normal: reflection identity in every correlation branch") {
    for (const double rho : {-0.99, -0.95, -0.5, 0.0, 0.2, 0.8, 0.95, 0.99})
        for (const double a : {-1.5, 0.3})
            for (const double b : {-0.7, 1.1}) {
                // P(X<=a, Y<=b; rho) + P(X<=a, Y<=-b; -rho) = Phi(a)
                const double sum = bivariate_normal_cdf(a, b, rho) + bivariate_normal_cdf(a, -b, -rho);
                CHECK(sum == Approx(normal_cdf(a)).margin(1e-14));
            }
    CHECK(bivariate_normal_cdf(0.4, -0.2, 0.0) == Approx(normal_cdf(0.4) * normal_cdf(-0.2)).margin(1e-15));
    CHECK(bivariate_normal_cdf(0.0, 0.0, 0.5) == Approx(0.25 + std::asin(0.5) / (2 * std::numbers::pi)).margin(1e-15));
}

TEST_CASE("Student t: Cauchy at one degree of freedom, inverse, bivariate reflection") {
    for (const double x : {-3.0, -0.5, 0.0, 2.0})
        CHECK(student_t_cdf(x, 1.0) == Approx(0.5 + std::atan(x) / std::numbers::pi).margin(1e-14));
    CHECK(student_t_inverse(student_t_cdf(-1.3, 4.5), 4.5) == Approx(-1.3).margin(1e-12));
    for (const double rho : {-0.6, 0.0, 0.7}) {
        const double sum = bivariate_t_cdf(-1.0, 0.5, rho, 5.0) + bivariate_t_cdf(-1.0, -0.5, -rho, 5.0);
        CHECK(sum == Approx(student_t_cdf(-1.0, 5.0)).margin(1e-11));
    }
    // At rho = 0 the t copula is not independence: (0, 0) gives exactly 1/4 + asin(0)/(2 pi) = 1/4 by symmetry.
    CHECK(bivariate_t_cdf(0.0, 0.0, 0.0, 3.0) == Approx(0.25).margin(1e-12));
}

TEST_CASE("copula, LHP and CDS option checks and identities") {
    const JointDefault g = copula_joint_default(CopulaKind::Gaussian, {0.02, 0.03}, 0.0, std::nullopt);
    CHECK(g.joint == Approx(0.0006).margin(1e-15));
    CHECK(code_of([] { copula_joint_default(CopulaKind::StudentT, {0.02, 0.03}, 0.3, std::nullopt); }) == "E_INPUT");
    CHECK(code_of([] { copula_joint_default(CopulaKind::Gaussian, {0.02}, 0.3, std::nullopt); }) == "E_INPUT");
    CHECK(code_of([] { copula_joint_default(CopulaKind::Gaussian, {0.0, 0.5}, 0.3, std::nullopt); }) == "E_DOMAIN");
    CHECK(code_of([] { copula_joint_default(CopulaKind::Gaussian, {0.1, 0.5}, 1.0, std::nullopt); }) == "E_DOMAIN");
    CHECK(code_of([] { copula_joint_default(CopulaKind::StudentT, {0.1, 0.5}, 0.3, 0.0); }) == "E_DOMAIN");

    // Tranches of a partition, weighted by width, add up to the pool loss (1 - R) p.
    double total = 0.0;
    const double pts[] = {0.0, 0.03, 0.07, 0.1, 0.15, 0.3, 1.0};
    for (int i = 0; i + 1 < 7; ++i) total += (pts[i + 1] - pts[i]) * lhp_tranche_loss(0.05, 0.3, 0.4, pts[i], pts[i + 1]);
    CHECK(total == Approx(0.6 * 0.05).margin(1e-15));
    CHECK(code_of([] { lhp_tranche_loss(0.05, 0.3, 0.4, 0.1, 0.1); }) == "E_INPUT");
    CHECK(code_of([] { lhp_tranche_loss(0.05, 1.0, 0.4, 0.0, 0.1); }) == "E_DOMAIN");
    CHECK(code_of([] { lhp_tranche_loss(0.05, 0.3, 1.0, 0.0, 0.1); }) == "E_DOMAIN");
    CHECK(code_of([] { lhp_loss_cdf(0.05, 0.3, 0.4, {}); }) == "E_INPUT");
    CHECK(code_of([] { lhp_loss_cdf(0.05, 0.3, 0.4, {0.7}); }) == "E_DOMAIN");
    const std::vector<double> cdf = lhp_loss_cdf(0.05, 0.3, 0.4, {0.01, 0.1, 0.5});
    CHECK(cdf[0] < cdf[1]);
    CHECK(cdf[1] < cdf[2]);

    CdsOptionInputs c{d("2026-11-06"), d("2027-03-20"), d("2032-03-20"), 0.035, 0.02, 0.4, true, 0.012, 1e7, true};
    for (const bool payer : {true, false}) {
        c.payer = payer;
        const double premium = cds_option_price(c, 0.5).price;
        CHECK(cds_option_implied_vol(c, premium) == Approx(0.5).margin(1e-10));
    }
    c.knock_out = false;
    c.payer = true;
    const CdsOptionPrice with = cds_option_price(c, 0.5);
    c.knock_out = true;
    CHECK(with.price == Approx(cds_option_price(c, 0.5).price + with.front_end_protection).margin(1e-6));
    CHECK(code_of([&] { cds_option_price(c, -0.1); }) == "E_DOMAIN");
    CHECK(code_of([&] { cds_option_implied_vol(c, 1e9); }) == "E_DOMAIN");
    CdsOptionInputs bad = c;
    bad.maturity = bad.expiry;
    CHECK(code_of([&] { cds_option_price(bad, 0.5); }) == "E_INPUT");
    bad = c;
    bad.recovery = 1.0;
    CHECK(code_of([&] { cds_option_price(bad, 0.5); }) == "E_DOMAIN");
    bad = c;
    bad.hazard_rate = -0.01;
    CHECK(code_of([&] { cds_option_price(bad, 0.5); }) == "E_DOMAIN");
    bad = c;
    bad.strike = 0.0;
    CHECK(code_of([&] { cds_option_price(bad, 0.5); }) == "E_DOMAIN");
    bad = c;
    bad.knock_out = false;
    CHECK(code_of([&] { cds_option_implied_vol(bad, 1.0); }) == "E_INPUT");
}
