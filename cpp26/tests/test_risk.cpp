#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <algorithm>
#include <cstdio>

#include "quantforge/core/error.hpp"
#include "quantforge/core/risk.hpp"

using namespace quantforge;
using Catch::Approx;

namespace {
Date d(const char* s) { return *parse_date(s); }
std::string code_of(auto&& f) {
    try { f(); } catch (const Error& e) { return e.code(); }
    return "none";
}
// Function-local statics: namespace-scope globals here ran before the
// convention table was initialised (static-init order, SIGSEGV on Linux).
const Date& as_of_date() { static const Date v = d("2026-11-06"); return v; }
const RateConvention& sofr_conv() { static const RateConvention& c = *rate_convention("SOFR"); return c; }
std::vector<OisQuote> quotes() {
    return {{{1, 'M'}, 0.0386}, {{6, 'M'}, 0.0377}, {{1, 'Y'}, 0.0365}, {{2, 'Y'}, 0.035}, {{5, 'Y'}, 0.035}, {{10, 'Y'}, 0.0375}};
}
// A 5Y receiver of fixed: it loses value when rates rise.
OisTrade receiver() { return {&sofr_conv(), Tenor{5, 'Y'}, 0.035, 1e7, FixedSide::Receive}; }
CurvePricer pv_of(const OisTrade& t) {
    return [t](const Curve& c) { return ois_price(t, c).valuation.pv; };
}
}  // namespace

TEST_CASE("triangular weights sum to 1 and are 1 at their own key") {
    const std::vector<double> k{0.5, 1.0, 3.0, 10.0};
    for (const double t : {0.0, 0.25, 0.5, 0.75, 1.0, 2.0, 3.0, 7.0, 10.0, 30.0}) {
        double sum = 0.0;
        for (std::size_t i = 0; i < k.size(); ++i) sum += triangular_weight(k, i, t);
        CHECK(sum == Approx(1.0).epsilon(1e-15));
    }
    for (std::size_t i = 0; i < k.size(); ++i) CHECK(triangular_weight(k, i, k[i]) == 1.0);
    CHECK(triangular_weight(k, 1, 2.0) == Approx(0.5));
    CHECK(triangular_weight(k, 3, 0.1) == 0.0);
}

TEST_CASE("key-rate buckets sum to the parallel zero DV01") {
    const Curve c = ois_bootstrap(sofr_conv(), as_of_date(), quotes(), CurveInterpolation::LogLinearDf, SolveMethod::Sequential).curve;
    const auto pv = pv_of(receiver());
    for (const KeyRateMode mode : {KeyRateMode::Triangular, KeyRateMode::Pillar}) {
        const std::vector<Date> keys = mode == KeyRateMode::Pillar ? std::vector<Date>{}
                                                                     : std::vector<Date>{d("2027-11-06"), d("2029-11-06"), d("2031-11-06")};
        const KeyRateRisk r = key_rate_risk(c, mode, keys, pv, 1.0, BumpScheme::Central);
        double sum = 0.0;
        for (const double x : r.buckets) sum += x;
        CHECK(r.zero_dv01 < 0.0);  // a receiver loses when rates rise
        CHECK(sum == Approx(r.zero_dv01).epsilon(1e-6));
    }
    // FORWARD differs from CENTRAL only at second order.
    const auto f = key_rate_risk(c, KeyRateMode::Pillar, {}, pv, 1.0, BumpScheme::Forward);
    const auto m = key_rate_risk(c, KeyRateMode::Pillar, {}, pv, 1.0, BumpScheme::Central);
    CHECK(f.zero_dv01 == Approx(m.zero_dv01).epsilon(1e-3));
    CHECK(f.zero_dv01 != m.zero_dv01);
}

TEST_CASE("par risk equals key-rate risk through the Jacobian") {
    const auto q = quotes();
    const auto pv = pv_of(receiver());
    const ParRisk par = par_risk(sofr_conv(), as_of_date(), q, CurveInterpolation::LogLinearDf, pv, 1.0, BumpScheme::Central);
    const ZeroJacobian j = zero_jacobian(sofr_conv(), as_of_date(), q, CurveInterpolation::LogLinearDf, 1.0);
    const Curve c = ois_bootstrap(sofr_conv(), as_of_date(), q, CurveInterpolation::LogLinearDf, SolveMethod::Sequential).curve;
    const KeyRateRisk kr = key_rate_risk(c, KeyRateMode::Pillar, {}, pv, 1.0, BumpScheme::Central);
    REQUIRE(j.jacobian.size() == q.size());
    double sum = 0.0;
    for (std::size_t col = 0; col < q.size(); ++col) {
        double chain = 0.0;
        for (std::size_t row = 0; row < q.size(); ++row) {
            if (row < col) CHECK(j.jacobian[row][col] == 0.0);
            chain += kr.buckets[row] * j.jacobian[row][col];
        }
        CHECK(std::fabs(par.buckets[col] - chain) < 1e-3 * std::fabs(par.par_dv01));
        sum += par.buckets[col];
    }
    CHECK(sum == Approx(par.par_dv01).epsilon(1e-4));
    CHECK(par.value == Approx(pv(c)).epsilon(1e-15));
}

TEST_CASE("risk checks") {
    CHECK(code_of([] { check_bump(0.0); }) == "E_DOMAIN");
    CHECK(code_of([] { check_bump(100.5); }) == "E_DOMAIN");
    CHECK(code_of([] { check_bump(100.0); }) == "none");
    const Curve c(as_of_date(), CurveInterpolation::LogLinearDf, {{d("2030-11-06"), 0.85}});
    CHECK(code_of([&] { check_key_dates(c, {}); }) == "E_INPUT");
    CHECK(code_of([&] { check_key_dates(c, {as_of_date()}); }) == "E_INPUT");
    CHECK(code_of([&] { check_key_dates(c, {d("2028-01-01"), d("2027-01-01")}); }) == "E_INPUT");
    CHECK(code_of([&] { check_key_dates(c, {d("2027-01-01"), d("2028-01-01")}); }) == "none");
}

TEST_CASE("P&L explain: small moves are explained, large ones leave second-order P&L") {
    const auto q0 = quotes();
    const auto shifted = [&](double bp_move) {
        auto q = q0;
        for (auto& x : q) x.rate += bp_move * 1e-4;
        return q;
    };
    const auto pv = pv_of(receiver());
    const PnlExplain small = pnl_explain(sofr_conv(), as_of_date(), q0, shifted(1.0), CurveInterpolation::LogLinearDf, pv, 1.0, 1e7);
    double dv01 = 0.0;
    for (const double b : small.par_buckets) dv01 += b;
    CHECK(small.explained);
    CHECK(small.full_pnl == Approx(small.value_end - small.value_start).epsilon(1e-15));
    CHECK(small.risk_pnl == Approx(dv01).epsilon(1e-12));  // a 1 bp parallel move
    CHECK(small.unexplained == Approx(small.full_pnl - small.risk_pnl).margin(1e-9));
    CHECK(small.gross_risk_pnl >= std::fabs(small.risk_pnl));
    CHECK(small.threshold == Approx(0.05 * std::max(std::fabs(small.full_pnl), small.gross_risk_pnl) + 1e-8 * 1e7));
    // No move at all: only the numerical floor remains, and risk and revaluation agree.
    const PnlExplain still = pnl_explain(sofr_conv(), as_of_date(), q0, q0, CurveInterpolation::LogLinearDf, pv, 1.0, 1e7);
    CHECK(still.gross_risk_pnl == 0.0);
    CHECK(still.threshold == Approx(0.1));
    CHECK(still.explained);
    // Convexity grows with the square of the move, so the relative gap grows with it.
    const PnlExplain big = pnl_explain(sofr_conv(), as_of_date(), q0, shifted(150.0), CurveInterpolation::LogLinearDf, pv, 1.0, 1e7);
    CHECK(std::fabs(big.unexplained / big.full_pnl) > std::fabs(small.unexplained / small.full_pnl));
    auto other = q0;
    other.back().tenor = Tenor{12, 'Y'};
    CHECK(code_of([&] { pnl_explain(sofr_conv(), as_of_date(), q0, other, CurveInterpolation::LogLinearDf, pv, 1.0, 1e7); }) == "E_INPUT");
    CHECK(code_of([&] { pnl_explain(sofr_conv(), as_of_date(), q0, {q0.begin(), q0.end() - 1}, CurveInterpolation::LogLinearDf, pv, 1.0, 1e7); }) == "E_INPUT");
}

namespace {
double zr(const Curve& c, Date x) { return -std::log(c.discount(x)) / c.time(x); }
}  // namespace

// R6 finding 3 (review 2026-11-12): under a non-local interpolation a pillar's zero rate moves with later quotes, so
// the Jacobian above the diagonal is not zero. Hidden reproducer, run with "[r6-repro]"; it fails while the mask stands.
TEST_CASE("R6 finding 3 reproducer: Jacobian upper triangle against a central difference", "[.][r6-repro]") {
    const auto q = quotes();
    const ZeroJacobian j = zero_jacobian(sofr_conv(), as_of_date(), q, CurveInterpolation::MonotoneConvex, 1.0);
    double worst = 0.0;
    for (std::size_t col = 0; col < q.size(); ++col) {
        auto up = q, dn = q;
        up[col].rate += 1e-4;
        dn[col].rate -= 1e-4;
        const Curve cu = ois_bootstrap(sofr_conv(), as_of_date(), up, CurveInterpolation::MonotoneConvex, SolveMethod::Sequential).curve;
        const Curve cd = ois_bootstrap(sofr_conv(), as_of_date(), dn, CurveInterpolation::MonotoneConvex, SolveMethod::Sequential).curve;
        for (std::size_t row = 0; row < col; ++row) {
            const double fd = (zr(cu, j.pillar_dates[row]) - zr(cd, j.pillar_dates[row])) / 2e-4;
            INFO("row " << row << " col " << col << " jacobian " << j.jacobian[row][col] << " central " << fd);
            worst = std::max(worst, std::fabs(fd));
            CHECK(std::fabs(j.jacobian[row][col] - fd) <= 1e-8);
        }
    }
    std::printf("R6 finding 3: largest upper-triangle central difference %.3e bp per bp\n", worst);
}
