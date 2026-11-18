// Unit tests for shortrate.cpp boundaries and branches the goldens leave open (mutation kill round 2026-11-18).
// Every expected value is derived independently in the comment next to it (closed form by hand, or a 40-50
// digit mpmath / scipy computation of the textbook formula); none is copied from the program's output.
// No namespace-scope static objects (static-init order has broken ASan before).
#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <limits>
#include <string>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/shortrate.hpp"

using namespace quantforge;
namespace sr = quantforge::shortrate;
using Catch::Approx;

namespace {
std::string code_of(auto&& run) {
    try {
        run();
    } catch (const Error& e) {
        return e.code();
    }
    return "ok";
}
sr::Curve flat_curve(double r) {
    std::vector<double> t, d;
    for (int i = 1; i <= 10; ++i) {
        t.push_back(i);
        d.push_back(std::exp(-r * i));
    }
    return sr::Curve::from(t, d);
}
bool close_rel(double got, double want, double tol) { return std::fabs(got - want) <= tol * std::fabs(want); }
}  // namespace

TEST_CASE("sru curve: interpolation, flat-forward extrapolation and the forward past the last knot", "[shortrate][sru]") {
    // Knots (0, 0), (1, -0.02), (5, -0.2). Last segment forward f = (-0.02 - -0.2) / 4 = 0.045.
    const auto c = sr::Curve::from({1.0, 5.0}, {std::exp(-0.02), std::exp(-0.2)});
    CHECK(c.ln_p(0.0) == 0.0);
    CHECK(c.ln_p(3.0) == Approx(-0.11).margin(1e-15));  // -0.02 + (2/4)(-0.18)
    CHECK(c.ln_p(5.0) == Approx(-0.2).margin(1e-15));
    CHECK(c.ln_p(7.0) == Approx(-0.29).margin(1e-15));  // -0.2 - 0.045 * 2
    CHECK(c.df(7.0) == Approx(std::exp(-0.29)).epsilon(1e-14));
    CHECK(c.fwd(0.5) == Approx(0.02).margin(1e-15));
    CHECK(c.fwd(1.0) == Approx(0.045).margin(1e-15));  // a knot belongs to the segment on its right
    // At and past the last knot the forward is the last segment's (index clamped to n - 1, never past the end).
    CHECK(c.fwd(5.0) == Approx(0.045).margin(1e-15));
    CHECK(c.fwd(9.0) == Approx(0.045).margin(1e-15));
}

TEST_CASE("sru b factors on both sides of the series switch", "[shortrate][sru]") {
    CHECK(sr::b_factor(0.5, 2.0) == Approx((1 - std::exp(-1.0)) / 0.5).epsilon(1e-15));
    // (B - tau)/a^2 from 40-digit mpmath of (-(expm1(-a tau))/a - tau)/a^2.
    CHECK(close_rel(sr::b_minus_tau_over_a2(0.001, 5.0), -12479.192682313352304, 1e-13));  // x = 0.005, series
    CHECK(close_rel(sr::b_minus_tau_over_a2(0.002, 4.99), -6204.3679817904701317, 1e-13));  // x = 0.00998
    CHECK(close_rel(sr::b_minus_tau_over_a2(0.3, 5.0), -26.782598524015920966, 1e-13));  // closed form
}

TEST_CASE("sru Vasicek and CIR zero-coupon bonds match the closed forms", "[shortrate][sru]") {
    sr::Params v;
    v.model = sr::Model::Vasicek;
    v.a = 0.3, v.b = 0.05, v.sigma = 0.02, v.r0 = 0.03;
    // P = A e^{-B r}, ln A = (B - tau)(a^2 b - s^2/2)/a^2 - s^2 B^2/(4a); mpmath 40 digits.
    CHECK(close_rel(sr::bond0(v, 5.0), 0.82276271098355574112, 1e-14));
    v.a = 0.001;  // small a: the series branch of (B - tau)/a^2
    CHECK(close_rel(sr::bond0(v, 5.0), 0.86766687050069553771, 1e-13));
    sr::Params c;
    c.model = sr::Model::Cir;
    c.a = 0.5, c.b = 0.04, c.sigma = 0.1, c.r0 = 0.03;
    // CIR (1985) A = [2g e^{(a+g)tau/2} / ((g+a)(e^{g tau}-1) + 2g)]^{2ab/s^2}, B = 2(e^{g tau}-1)/(...).
    CHECK(close_rel(sr::bond0(c, 3.0), 0.90131039870992760564, 1e-14));
}

TEST_CASE("sru incomplete gamma and noncentral chi-square against scipy", "[shortrate][sru]") {
    // scipy.special.gammainc / gammaincc; x < s + 1 takes the series, x >= s + 1 the continued fraction.
    CHECK(close_rel(sr::gamma_p(2.5, 1.0), 0.15085496391539038, 1e-13));
    CHECK(close_rel(sr::gamma_pq(2.5, 1.0, true), 0.8491450360846096, 1e-13));
    CHECK(close_rel(sr::gamma_pq(2.5, 5.0, false), 0.9247647538534878, 1e-13));
    CHECK(close_rel(sr::gamma_pq(2.5, 5.0, true), 0.07523524614651217, 1e-12));
    CHECK(sr::gamma_pq(2.5, 0.0, false) == 0.0);
    CHECK(sr::gamma_pq(2.5, -1.0, true) == 1.0);
    // scipy.stats.ncx2.
    CHECK(close_rel(sr::ncx2_cdf(3.0, 4.0, 2.5), 0.21170522565569064, 1e-12));
    CHECK(close_rel(sr::ncx2_sf(10.0, 4.0, 2.5), 0.18174876591172662, 1e-12));
    CHECK(close_rel(sr::ncx2_cdf(30.0, 6.0, 40.0), 0.10135090477838675, 1e-12));
    CHECK(sr::ncx2_cdf(0.0, 4.0, 2.5) == 0.0);
    CHECK(sr::ncx2_sf(-1.0, 4.0, 2.5) == 1.0);
    CHECK(code_of([] { sr::ncx2_cdf(std::numeric_limits<double>::infinity(), 4.0, 2.5); }) == "E_NON_FINITE");
}

TEST_CASE("sru Chernoff decision on both sides of f = -750", "[shortrate][sru]") {
    // f = (k/2) ln u - x (1 - 1/u)/2 + lambda (u - 1)/2, u = 2x / (k + sqrt(k^2 + 4 lambda x)); values by a separate
    // Python evaluation of that formula. x = 2, k = 4: lambda 1606 gives f = -754.05 (settled, lower tail, u = 0.034),
    // lambda 1580 gives f = -741.49 (not settled). Each term moves f by more than 4 across the line.
    const auto lo = sr::ncx2_chernoff(2.0, 4.0, 1606.0);
    REQUIRE(lo.has_value());
    CHECK(*lo == 0.0);
    CHECK_FALSE(sr::ncx2_chernoff(2.0, 4.0, 1580.0).has_value());
    // Upper tail: x = 6000, k = 4, lambda = 1000: u = 2.447, f = -1048.7, so the CDF is 1 and the survival 0.
    const auto hi = sr::ncx2_chernoff(6000.0, 4.0, 1000.0);
    REQUIRE(hi.has_value());
    CHECK(*hi == 1.0);
    CHECK(sr::ncx2_cdf(2.0, 4.0, 1606.0) == 0.0);
    CHECK(sr::ncx2_sf(2.0, 4.0, 1606.0) == 1.0);
    CHECK(sr::ncx2_cdf(6000.0, 4.0, 1000.0) == 1.0);
    CHECK(sr::ncx2_sf(6000.0, 4.0, 1000.0) == 0.0);
}

TEST_CASE("sru CIR critical rate exactly 0 is accepted, below 0 is E_DOMAIN", "[shortrate][sru]") {
    sr::Params c;
    c.model = sr::Model::Cir;
    c.a = 0.5, c.b = 0.04, c.sigma = 0.1, c.r0 = 0.03;
    // One payment at 2, expiry 1: g(0) = (1 + K) P(1, 2; 0) - 1 with P(1, 2; 0) = e^{ln A}. Walk K over adjacent doubles
    // until the product is exactly 1 (the same operations, in the same order, as the pricer's coupon and bond).
    const double lnA = sr::ln_a_b(c, 1.0, 2.0).first;
    const double P0 = std::exp(lnA - sr::ln_a_b(c, 1.0, 2.0).second * 0.0);
    double K = 1.0 / P0 - 1.0;
    bool found = false;
    for (int s = 0; s < 200 && !found; ++s) {
        for (double k : {K, std::nextafter(K, 1.0), std::nextafter(K, 0.0)}) {
            double ci = k * (2.0 - 1.0);
            ci += 1.0;
            if (0.0 + ci * P0 - 1.0 == 0.0) {
                K = k;
                found = true;
                break;
            }
        }
        if (!found) K = std::nextafter(K, 1.0);
    }
    REQUIRE(found);
    // g(0) = 0 is not "no non-negative critical rate" (ruling G-20 throws only for g(0) < 0): r* = 0, a price.
    CHECK(code_of([&] { sr::swaption(c, 1.0, {2.0}, K, true); }) == "ok");
    // A lower fixed rate makes g(0) < 0.
    CHECK(code_of([&] { sr::swaption(c, 1.0, {2.0}, K - 0.01, true); }) == "E_DOMAIN");
}

TEST_CASE("sru Hull-White calibration recovers sigma near the top of the [1e-4, 1] grid", "[shortrate][sru]") {
    // Targets priced at sigma = 0.98; the scan grid reaches 1 exactly (node 400 = 1e-4 * 1e4), so the minimum is
    // interior and the bisection returns 0.98. A grid ending short of 0.98 would put the minimum at an end.
    sr::Params p;
    p.model = sr::Model::HullWhite;
    p.a = 0.1;
    p.curve = flat_curve(0.03);
    p.sigma = 0.98;
    const std::vector<double> pay{2.0, 3.0};
    const double target = sr::swaption(p, 1.0, pay, 0.03, true).price;
    const auto cal = sr::hw_calibrate(p.curve, 0.1, {{1.0, pay, 0.03, true, target}});
    CHECK(cal.sigma == Approx(0.98).epsilon(1e-9));
    CHECK(cal.rmse < 1e-9);
}

TEST_CASE("sru G2++ bond: small-a series against 50-digit closed form, and t = 0 with large mean reversion", "[shortrate][sru]") {
    sr::G2 m{0.01, 0.01, 0.02, 0.008, -0.6, flat_curve(0.03)};
    // mpmath: ln P = -0.03 (T - t) + (V(T-t) - V(T) + V(t))/2 - B_a x - B_b y with the bracket definitions of V.
    CHECK(close_rel(sr::g2_bond(m, 1.0, 3.0, 0.01, -0.005), 0.93221096740151193848, 1e-13));
    // a = b = 9.99, tau = 0.01: a tau = 0.0999 takes the series with a small sum (3.3e-7), so the 1e-17 relative stop
    // matters; mpmath of the bracket definitions, sigma = 10 makes a 1e-7 relative error in V(tau) a 1.6e-12 bond error.
    sr::G2 fast{9.99, 10.0, 9.99, 0.0, 0.0, flat_curve(0.03)};
    CHECK(close_rel(sr::g2_bond(fast, 1.0, 1.01, 0.0, 0.0), 0.99471988543079336655, 2e-14));
    // At t = 0 every V(0) bracket is 0 and V(T - 0) - V(T) = 0, so with x = y = 0 the bond is the curve discount
    // factor exactly; a = b = 5000 makes the tau = 0 series terms (0 times a^(k-3) 2^(k-1)) large but finite up to k = 79.
    sr::G2 big{5000.0, 0.01, 5000.0, 0.01, 0.5, flat_curve(0.03)};
    const double v = sr::g2_bond(big, 0.0, 2.0, 0.0, 0.0);
    CHECK(std::isfinite(v));
    CHECK(v == Approx(std::exp(-0.06)).epsilon(1e-14));
}
