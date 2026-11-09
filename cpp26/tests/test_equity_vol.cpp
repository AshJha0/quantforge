#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <cmath>

#include "quantforge/core/black.hpp"
#include "quantforge/core/equity.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/sabr.hpp"
#include "quantforge/core/smile.hpp"
#include "quantforge/core/surface.hpp"

using namespace quantforge;
using Catch::Approx;
using Vec = std::vector<double>;

namespace {
std::string code_of(auto&& f) {
    try { f(); } catch (const Error& e) { return e.code(); }
    return "none";
}
OptionInput black76(OptionType type, double f, double k, double t) {
    OptionInput o{VolModel::Black76, type, k, t};
    o.forward = f;
    o.discount_factor = 0.97;
    return o;
}
}  // namespace

TEST_CASE("dividends carry on C, not D") {
    REQUIRE(equity_forward_flat(100, 0.04, 0.05, 1, {{0.5, 2}}) == Approx(97.0149584).epsilon(1e-9));
    REQUIRE(code_of([] { equity_forward_flat(1, 0, 0, 1, {{0.5, 2}}); }) == "E_DOMAIN");
}

TEST_CASE("parity recovers a known forward and discount") {
    std::vector<ParityQuote> q;
    for (const double k : {90.0, 100.0, 110.0}) {
        const double y = 0.95 * (103 - k);
        q.push_back({k, 20 + y, 20 + y, 20, 20});
    }
    const ParityForward p = parity_forward(q, std::nullopt);
    REQUIRE(p.forward == Approx(103));
    REQUIRE(p.discount_factor == Approx(0.95));
    REQUIRE(code_of([&] { parity_forward({q[0]}, std::nullopt); }) == "E_INPUT");
}

TEST_CASE("implied vol inverts price and rejects bounds") {
    const OptionInput o = black76(OptionType::Put, 100, 90, 1.5);
    REQUIRE(implied_vol(o, option_price(o, 0.31)) == Approx(0.31).epsilon(1e-10));
    REQUIRE(code_of([&] { implied_vol(o, 0.97 * 90); }) == "E_DOMAIN");
}

TEST_CASE("analytic Greeks agree with bumps") {
    const OptionInput o = black76(OptionType::Call, 100, 105, 1);
    const Greeks g = option_greeks(o, 0.25);
    const BumpGreeks b = bump_greeks(o, 0.25);
    REQUIRE(g.delta == Approx(b.delta).epsilon(1e-4));
    REQUIRE(g.vega == Approx(b.vega).epsilon(1e-4));
    REQUIRE(g.vanna == Approx(b.vanna).epsilon(1e-3));
}

TEST_CASE("delta to strike and back") {
    const double k = delta_to_strike(100, 0.2, 0.5, OptionType::Put, -0.25, 1);
    REQUIRE(delta_from_strike(100, 0.2, 0.5, OptionType::Put, k, 1) == Approx(-0.25).epsilon(1e-11));
    REQUIRE(normal_inverse(0.975) == Approx(1.959963984540054).epsilon(1e-12));
}

TEST_CASE("SVI fit recovers its own parameters") {
    const Svi truth{0.03, 0.12, -0.35, 0.02, 0.15};
    Vec k, w;
    for (int i = -4; i <= 4; ++i) {
        k.push_back(0.15 * i);
        w.push_back(truth.w(k.back()));
    }
    const SviFit fit = svi_calibrate(k, w, std::nullopt);
    REQUIRE(fit.rmse < 1e-9);
    REQUIRE(fit.svi.rho == Approx(truth.rho).epsilon(1e-5));
}

TEST_CASE("surface holds flat vol beyond its grid and finds a calendar breach") {
    const Surface s{{1, 2}, {-0.1, 0.1}, {{0.3, 0.3}, {0.2, 0.2}}};
    REQUIRE(std::sqrt(surface_total_variance(s, 0.5, 5) / 0.5) == Approx(0.3));
    const SurfaceCheck c = surface_check(s);
    REQUIRE(c.calendar.size() == 2);
    REQUIRE(c.calendar[0].expiry_index == 1);
}

TEST_CASE("arbitrage-free SABR conserves mass and mean") {
    const SabrParameters p{0.3, 0.5, -0.2, 0.4};
    const ArbFreeResult r = sabr_arbfree(1.0, {0.8, 1.0, 1.2}, 1.0, p, {800, 200, 200});
    REQUIRE(r.mass == Approx(1.0).epsilon(1e-10));
    REQUIRE(r.mean == Approx(1.0).epsilon(1e-9));
    REQUIRE(r.min_density >= 0);
    REQUIRE(r.vols[1]);
    REQUIRE(*r.vols[1] == Approx(hagan_vol(1, 1, 1, p)).margin(7e-3));
}
