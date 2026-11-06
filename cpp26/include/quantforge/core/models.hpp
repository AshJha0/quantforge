#pragma once
// The three European option engines of stage A: PDE, Monte Carlo and COS.
#include <cstdint>

namespace quantforge {

enum class OptionType { Call, Put };

struct PdeInputs {
    OptionType option;
    double spot, strike, r, q, sigma, t;
    long long space_steps, time_steps;
    double width = 6.0;
    long long rannacher_steps = 2;
};
struct PdeResult {
    double price, delta, gamma, grid_h;
};
PdeResult pde_bs_european(const PdeInputs& in);

enum class McMethod { Plain, Antithetic, ControlVariate, Sobol };
struct McInputs {
    OptionType option;
    double spot, strike, r, q, sigma, t;
    long long paths;
    long long steps = 1;
    std::uint64_t seed;
    int stream = 0;
    McMethod method;
};
struct McResult {
    double price, standard_error;
};
McResult mc_gbm_european(const McInputs& in);

enum class CosModelName { BlackScholes, Heston };
struct CosModel {
    CosModelName name;
    double sigma = 0.0;
    double v0 = 0.0, kappa = 0.0, theta = 0.0, rho = 0.0;  // Heston only
};
struct CosInputs {
    OptionType option;
    double spot, strike, r, q, t;
    CosModel model;
    long long terms;
    double truncation;
};
struct CosResult {
    double price, a, b;
};
CosResult cos_european(const CosInputs& in);

}  // namespace quantforge
