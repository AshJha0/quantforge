#pragma once
// Black-Scholes, Black-76, Bachelier and their Greeks: 05-volatility/black-models.md, 06-risk/vol-greeks.md.
#include "quantforge/core/models.hpp"

namespace quantforge {

enum class VolModel { BlackScholes, Black76, Bachelier };

struct OptionInput {
    VolModel model;
    OptionType type;
    double strike, expiry_years;
    double spot = 0, rate = 0, yield = 0;              // BLACK_SCHOLES
    double forward = 0, discount_factor = 0, shift = 0;  // the others

    double phi() const { return type == OptionType::Call ? 1.0 : -1.0; }
    /// Unshifted forward.
    /// unchecked: caller guarantees finite inputs
    double model_forward() const;
    /// unchecked: caller guarantees finite inputs
    double model_discount() const;
};

/// D phi (F N(phi d1) - K N(phi d2)), with the intrinsic at T = 0 or v = 0.
/// Raw kernels, called inside solvers and calibrations.
/// unchecked: caller guarantees finite inputs
double black_price(double f, double k, double vol, double t, double d, double phi);
/// unchecked: caller guarantees finite inputs
double bachelier_price(double f, double k, double vol, double t, double d, double phi);

/// E_DOMAIN unless every double field is finite (F-2).
void require_finite(const OptionInput& in);
/// The checks both vol.option.price and vol.option.implied share.
void check_option(const OptionInput& in);
double option_price(const OptionInput& in, double vol);
/// Checks vol itself, then the rest, in the order of the spec.
double checked_option_price(const OptionInput& in, double vol);
double implied_vol(const OptionInput& in, double price);
/// implied_vol without the finite check, for internal callers whose price may come out of a grid.
/// unchecked: caller guarantees finite inputs
double implied_vol_unchecked(const OptionInput& in, double price);

struct Greeks {
    double price, delta, gamma, vega, theta, rho, vanna, volga;
};
Greeks option_greeks(const OptionInput& in, double vol);

struct BumpGreeks {
    double delta, gamma, vega, volga, vanna;
};
BumpGreeks bump_greeks(const OptionInput& in, double vol);

}  // namespace quantforge
