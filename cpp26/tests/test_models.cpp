#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <cmath>

#include "quantforge/core/error.hpp"
#include "quantforge/core/models.hpp"

using namespace quantforge;

namespace {
// Black-Scholes values for the numeric targets, from oracle/REPORT.md.
constexpr double call_true = 9.227005508154049;
}

TEST_CASE("PDE meets its numeric target and order") {
    PdeInputs in{OptionType::Call, 100, 100, 0.05, 0.02, 0.2, 1, 400, 200};
    const double e1 = std::fabs(pde_bs_european(in).price - call_true);
    CHECK(e1 < 1e-3);
    in.space_steps = 800;
    in.time_steps = 400;
    const double ratio = e1 / std::fabs(pde_bs_european(in).price - call_true);
    CHECK(ratio > 3.0);
    CHECK(ratio < 5.0);
}

TEST_CASE("Monte Carlo variance reduction and Sobol") {
    McInputs in{OptionType::Call, 100, 100, 0.05, 0.02, 0.2, 1, 100000, 1, 20261106, 0, McMethod::Plain};
    const McResult plain = mc_gbm_european(in);
    CHECK(std::fabs(plain.price - call_true) <= 4 * plain.standard_error);
    CHECK(plain.standard_error == Catch::Approx(0.045).margin(0.003));
    in.method = McMethod::Antithetic;
    CHECK(mc_gbm_european(in).standard_error < plain.standard_error);
    in.method = McMethod::ControlVariate;
    CHECK(mc_gbm_european(in).standard_error < plain.standard_error);
    in.method = McMethod::Sobol;
    in.paths = 65536;
    CHECK(std::fabs(mc_gbm_european(in).price - call_true) < 0.01);
}

TEST_CASE("COS numeric targets") {
    CosInputs in{OptionType::Call, 100, 100, 0.05, 0.02, 1, {CosModelName::BlackScholes, 0.2}, 256, 10};
    CHECK(std::fabs(cos_european(in).price - call_true) < 1e-10);
    // Near-zero vol-of-vol approaches Black-Scholes at the same variance.
    in.model = {CosModelName::Heston, 1e-3, 0.04, 1.5, 0.04, -0.7};
    in.terms = 512;
    in.truncation = 16;
    CHECK(std::fabs(cos_european(in).price - call_true) < 1e-3);
    in.model.rho = 1.0;
    CHECK_THROWS_AS(cos_european(in), Error);
}
