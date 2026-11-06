#include "test_functions.hpp"

#include <cmath>
#include <numbers>
#include <string>

#include "quantforge/core/error.hpp"
#include "quantforge/core/stats.hpp"

namespace quantforge::cli {
namespace {

double bs_d1(double x) { return (std::log(1.0) + (0.01 + x * x / 2.0) * 1.0) / (x * std::sqrt(1.0)); }

double bs_vol_atm(double x) {
    const double d1 = bs_d1(x), d2 = d1 - x * std::sqrt(1.0);
    return 100.0 * normal_cdf(d1) - 100.0 * std::exp(-0.01 * 1.0) * normal_cdf(d2) - 10.0;
}

double bs_vega(double x) { return 100.0 * normal_pdf(bs_d1(x)) * std::sqrt(1.0); }

[[noreturn]] void unknown(std::string_view name) {
    throw Error("E_SCHEMA", "unknown function " + std::string(name), "function");
}

}  // namespace

RootFunction root_function(std::string_view n) {
    if (n == "cubic_wallis") return {[](double x) { return x * x * x - 2.0 * x - 5.0; }, [](double x) { return 3.0 * x * x - 2.0; }};
    if (n == "cos_minus_x") return {[](double x) { return std::cos(x) - x; }, [](double x) { return -std::sin(x) - 1.0; }};
    if (n == "exp_minus_two") return {[](double x) { return std::exp(x) - 2.0; }, [](double x) { return std::exp(x); }};
    if (n == "triple_root") return {[](double x) { return (x - 1.0) * (x - 1.0) * (x - 1.0); }, [](double x) { return 3.0 * (x - 1.0) * (x - 1.0); }};
    if (n == "square") return {[](double x) { return x * x; }, [](double x) { return 2.0 * x; }};
    if (n == "no_real_root") return {[](double x) { return x * x + 1.0; }, [](double x) { return 2.0 * x; }};
    if (n == "steep_atan")
        return {[](double x) { return std::atan(1000.0 * (x - 0.3)); },
                [](double x) { return 1000.0 / (1.0 + 1e6 * (x - 0.3) * (x - 0.3)); }};
    if (n == "bs_vol_atm") return {bs_vol_atm, bs_vega};
    unknown(n);
}

Fn plain_function(std::string_view n) {
    if (n == "exp") return [](double x) { return std::exp(x); };
    if (n == "sin") return [](double x) { return std::sin(x); };
    if (n == "runge") return [](double x) { return 1.0 / (1.0 + 25.0 * x * x); };
    if (n == "sqrt") return [](double x) { return std::sqrt(x); };
    if (n == "inv_sqrt") return [](double x) { return 1.0 / std::sqrt(x); };
    if (n == "normal_pdf") return [](double x) { return std::exp(-x * x / 2.0) / std::sqrt(2.0 * std::numbers::pi); };
    if (n == "oscillatory") return [](double x) { return std::cos(50.0 * x) * std::exp(-x); };
    if (n == "poly5") return [](double x) { return std::pow(x, 5.0) - 3.0 * x * x + 1.0; };
    unknown(n);
}

}  // namespace quantforge::cli
