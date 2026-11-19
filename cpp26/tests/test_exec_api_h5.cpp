// H-5 typed layer (specifications/10-execution/library-interfaces.md section 2.5): bit-equal to the kernels,
// invariants at construction with the stated code, enum parse at the edge.
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <cstring>
#include <limits>
#include <random>
#include <string>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/exec_api.hpp"

namespace api = quantforge::exec_api;
namespace ex = quantforge::execution;
using Vec = std::vector<double>;

namespace {
template <class F>
std::string code_of(F f) {
    try {
        f();
    } catch (const quantforge::Error& e) {
        return e.code();
    }
    return "none";
}

bool same(double a, double b) { return std::memcmp(&a, &b, sizeof a) == 0; }
bool same(const Vec& a, const Vec& b) {
    if (a.size() != b.size()) return false;
    for (std::size_t i = 0; i < a.size(); ++i)
        if (!same(a[i], b[i])) return false;
    return true;
}
constexpr double k_nan = std::numeric_limits<double>::quiet_NaN();
constexpr double k_inf = std::numeric_limits<double>::infinity();
}  // namespace

TEST_CASE("H-5 C++ typed calls are bit-equal to the kernels", "[h5][exec_api]") {
    std::mt19937_64 rng(20261118);
    std::uniform_real_distribution<double> u(0.0, 1.0);
    for (int t = 0; t < 200; ++t) {
        const double x = std::floor(1 + u(rng) * 1e6);
        const long long n = 1 + (long long)(u(rng) * 50);
        const auto mode = t % 2 ? api::FillMode::Units : api::FillMode::Continuous;
        CHECK(same(api::twap(x, n, mode).slices(), ex::twap(x, n, mode)));
        Vec prof(n);
        for (double& w : prof) w = 0.1 + u(rng);
        CHECK(same(api::vwap(x, prof, mode).slices(), ex::vwap(x, prof, mode)));
        const double part = 0.05 + 0.5 * u(rng);
        Vec mv(n);
        for (double& v : mv) v = std::floor(1 + u(rng) * 1e5);
        const auto ps = api::pov(x, part, mv, mode);
        const auto pk = ex::pov(x, part, mv, mode);
        CHECK(same(ps.slices(), pk.slices));
        CHECK(same(ps.filled(), pk.filled));
        CHECK(same(ps.residual(), pk.residual));

        const api::AcParams p(x, 1 + 9 * u(rng), n, u(rng), 0.1 * u(rng), 1e-5 + 1e-5 * u(rng), 1e-8 * u(rng));
        const double lam = 1e-6 * u(rng);
        const auto at = api::ac_trajectory(p, lam);
        const auto ak = ex::ac_trajectory(p.kernel(), lam);
        CHECK(same(at.holdings(), ak.holdings));
        CHECK(same(at.trades(), ak.trades));
        CHECK(same(at.kappa(), ak.kappa));
        CHECK(same(at.expected_cost(), ak.expected_cost));
        CHECK(same(at.variance(), ak.variance));
        CHECK(same(at.objective(), ak.objective));
        const Vec lams{0, lam, 2 * lam};
        const auto af = api::ac_frontier(p, lams);
        const auto fk = ex::ac_frontier(p.kernel(), lams);
        CHECK(same(af.risk_aversions(), fk.risk_aversions));
        CHECK(same(af.expected_costs(), fk.expected_cost));
        CHECK(same(af.variances(), fk.variance));
        CHECK(af.expected_costs().size() == af.variances().size());

        const double q = 1e5 * u(rng), v = 1e6 + 1e7 * u(rng), s = 0.05 * u(rng), y = u(rng);
        CHECK(same(api::impact_sqrt(q, v, s, y), ex::impact_sqrt(q, v, s, y)));
        const auto ow = api::ow_optimal(x, 1 + u(rng), 0.5 + u(rng));
        CHECK(ow.initial_block() == ow.final_block());

        std::vector<api::Fill> fills;
        std::vector<ex::Fill> kf;
        for (int i = 0; i < 20; ++i) {
            const double fq = 1 + std::floor(u(rng) * 100), fp = 99 + 2 * u(rng);
            fills.emplace_back(fq, fp);
            kf.push_back({fq, fp});
        }
        const auto side = t % 3 ? api::Side::Buy : api::Side::Sell;
        const std::optional<double> bm = t % 2 ? std::optional<double>(100.1) : std::nullopt;
        const auto sa = api::shortfall(side, 100, 100.2, 100.5, 5000, fills, 3.5, bm);
        const auto sk = ex::shortfall(side, 100, 100.2, 100.5, 5000, kf, 3.5, bm);
        CHECK(same(sa.delay(), sk.delay));
        CHECK(same(sa.execution(), sk.execution));
        CHECK(same(sa.opportunity(), sk.opportunity));
        CHECK(same(sa.total(), sk.total));
        CHECK(same(sa.total_bps(), sk.total_bps));
        CHECK(sa.vwap_slippage().has_value() == sk.vwap_slippage.has_value());
        if (bm) CHECK(same(*sa.vwap_slippage(), *sk.vwap_slippage));

        const double inv = std::floor(20 * u(rng)) - 10, g = 0.01 + u(rng), sg = 3 * u(rng), tl = u(rng),
                     k = 0.1 + 2 * u(rng);
        const auto qa = api::as_quotes(100, inv, g, sg, tl, k);
        const auto qk = ex::as_quotes(100, inv, g, sg, tl, k);
        CHECK(same(qa.reservation(), qk.reservation));
        CHECK(same(qa.spread(), qk.spread));
        CHECK(same(qa.bid(), qk.bid));
        CHECK(same(qa.ask(), qk.ask));
    }
    const auto ow = api::ow_optimal(1e6, 1, 2);
    const auto owk = ex::ow_optimal(1e6, 1, 2);
    CHECK(same(ow.initial_block(), owk.initial_block));
    CHECK(same(ow.rate(), owk.rate));
    CHECK(same(ow.final_block(), owk.final_block));
}

TEST_CASE("H-5 C++ invariants raise the stated code at construction", "[h5][exec_api]") {
    // AcParams: almgren-chriss.md order (HR-2, HR-5) and F-2 finiteness.
    CHECK(code_of([] { api::AcParams(1e6, 5, 0, 0.95, 0.0625, 2.5e-6, 2.5e-7); }) == "E_INPUT");
    CHECK(code_of([] { api::AcParams(0, 5, 5, 0.95, 0.0625, 2.5e-6, 2.5e-7); }) == "E_INPUT");
    CHECK(code_of([] { api::AcParams(1e6, 0, 5, 0.95, 0.0625, 2.5e-6, 2.5e-7); }) == "E_DOMAIN");
    CHECK(code_of([] { api::AcParams(1e6, 5, 5, -1, 0.0625, 2.5e-6, 2.5e-7); }) == "E_DOMAIN");
    CHECK(code_of([] { api::AcParams(1e6, 5, 5, 0.95, -1, 2.5e-6, 2.5e-7); }) == "E_DOMAIN");
    CHECK(code_of([] { api::AcParams(1e6, 5, 5, 0.95, 0.0625, 2.5e-6, -1); }) == "E_DOMAIN");
    CHECK(code_of([] { api::AcParams(1e6, 5, 5, 0.95, 0.0625, 1e-7, 2.5e-7); }) == "E_DOMAIN");  // eta_tilde <= 0
    CHECK(code_of([] { api::AcParams(k_nan, 5, 5, 0.95, 0.0625, 2.5e-6, 2.5e-7); }) == "E_DOMAIN");
    CHECK(code_of([] { api::AcParams(1e6, k_inf, 5, 0.95, 0.0625, 2.5e-6, 2.5e-7); }) == "E_DOMAIN");
    CHECK(code_of([] { api::AcParams(1e6, 5, 5, 0.95, 0.0625, 2.5e-6, 2.5e-7); }) == "none");
    // Fill
    CHECK(code_of([] { api::Fill(0, 100); }) == "E_INPUT");
    CHECK(code_of([] { api::Fill(-1, 100); }) == "E_INPUT");
    CHECK(code_of([] { api::Fill(1, 0); }) == "E_DOMAIN");
    CHECK(code_of([] { api::Fill(1, k_nan); }) == "E_DOMAIN");
    CHECK(code_of([] { api::Fill(k_inf, 1); }) == "E_DOMAIN");
    // Quotes: bid <= ask
    CHECK(code_of([] { api::Quotes(100, -1, 101, 99); }) == "E_DOMAIN");
    CHECK(code_of([] { api::Quotes(100, 0, 100, 100); }) == "none");
    // Non-finite inputs never reach the maths.
    CHECK(code_of([] { api::twap(k_nan, 5, api::FillMode::Units); }) == "E_DOMAIN");
    CHECK(code_of([] { api::vwap(10, {1, k_inf}, api::FillMode::Units); }) == "E_DOMAIN");
    CHECK(code_of([] { api::as_quotes(100, 0, 0.1, k_nan, 1, 1); }) == "E_DOMAIN");
    CHECK(code_of([] { api::shortfall(api::Side::Buy, 100, 100, 100, 10, {}, 0, k_inf); }) == "E_DOMAIN");
    // Kernel checks still apply.
    CHECK(code_of([] { api::twap(10.5, 5, api::FillMode::Units); }) == "E_INPUT");
    CHECK(code_of([] { api::shortfall(api::Side::Buy, 100, 100, 100, 1, {api::Fill(2, 100)}, 0); }) == "E_INPUT");
}

TEST_CASE("H-5 C++ enums parse at the edge and round-trip their JSON spelling", "[h5][exec_api]") {
    for (const char* s : {"BUY", "SELL"}) CHECK(std::string(api::to_string(api::parse_side(s))) == s);
    for (const char* s : {"UNITS", "CONTINUOUS"}) CHECK(std::string(api::to_string(api::parse_fill_mode(s))) == s);
    for (const char* s : {"buy", "Buy", "", "SHORT", "BUY "}) CHECK(code_of([s] { api::parse_side(s); }) == "E_SCHEMA");
    for (const char* s : {"units", "", "LOTS"}) CHECK(code_of([s] { api::parse_fill_mode(s); }) == "E_SCHEMA");
}
