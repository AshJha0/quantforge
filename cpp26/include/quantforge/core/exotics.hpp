#pragma once
// Stage E, E5: exotic options (04-pricing/exotics.md). Rulings E-A19 to E-A23.
#include <vector>

#include "quantforge/core/linalg.hpp"
#include "quantforge/core/models.hpp"

namespace quantforge {

/// Common inputs; strike is unused by the lookback.
struct ExoticMarket {
    double spot, strike, expiry_years, rate, dividend_yield, vol;
    OptionType type;
};

/// Generalised Black-Scholes with cost of carry b.
double gbs(OptionType type, double s, double k, double t, double r, double b, double v);

enum class DigitalPayoff { CashOrNothing, AssetOrNothing };
double digital_price(const ExoticMarket& m, DigitalPayoff payoff, double cash);

enum class BarrierType { DownIn, DownOut, UpIn, UpOut };
double barrier_price(const ExoticMarket& m, double barrier, double rebate, BarrierType type);

double asian_geometric(const ExoticMarket& m, bool continuous, const std::vector<double>& fixing_years);
double lookback_floating(const ExoticMarket& m, double running_extreme);

struct QuantoInputs {
    double spot, strike, expiry_years, domestic_rate, foreign_rate, dividend_yield, vol, fx_vol, correlation;
    OptionType type;
};
double quanto_price(const QuantoInputs& q);
double chooser_price(const ExoticMarket& m, double choose_years);
double kirk_spread(double f1, double f2, double strike, double t, double rate, double v1, double v2, double rho);

struct BasketPrice {
    double price, basket_forward, basket_vol;
};
BasketPrice basket_moment(const std::vector<double>& forwards, const std::vector<double>& weights,
                          const std::vector<double>& vols, const Matrix& correlation, double strike, double t, double rate,
                          OptionType type);

struct AmericanTree {
    double american, european, early_exercise_premium;
};
AmericanTree american_crr(const ExoticMarket& m, long long steps);
double american_baw(const ExoticMarket& m);

struct FdGrid {
    long long nx, nt;
    double width;
};
struct FdResult {
    double price, delta, gamma;
};
FdResult american_fd(const ExoticMarket& m, bool american, const FdGrid& g);

}  // namespace quantforge
