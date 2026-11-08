#pragma once
// Stage E, E2: Heston, Bates, Merton, SLV leverage (05-volatility/heston-family.md). Rulings E-A12 to E-A14.
#include <complex>
#include <vector>

#include "quantforge/core/arb_surface.hpp"

namespace quantforge {

struct HestonParams {
    double v0, kappa, theta, xi, rho;
};
void check_heston(const HestonParams& h);

struct Jumps {
    double intensity, mean_log_jump, log_jump_vol;
};
void check_jumps(const Jumps& j);

/// Characteristic function of ln(S_T/F) at complex u, little-trap form [Alb07].
std::complex<double> heston_cf(double t, const HestonParams& h, std::complex<double> u);

struct EquityOption {
    double spot, expiry_years, rate, dividend_yield;
    OptionType type;
    std::vector<double> strikes;
};
std::vector<double> heston_price(const EquityOption& o, const HestonParams& h);
std::vector<double> bates_price(const EquityOption& o, const HestonParams& h, const Jumps& j);
std::vector<double> merton_price(const EquityOption& o, double vol, const Jumps& j);

struct SlvGrid {
    long long nx, nv, nt;
    double x_min, x_max, v_max;
};
struct SlvLeverage {
    std::vector<double> x, leverage;
    double mass;
};
SlvLeverage slv_leverage(double spot, double t, double rate, double q, const HestonParams& h,
                         const std::vector<SviSlice>& slices, const SlvGrid& g);

}  // namespace quantforge
