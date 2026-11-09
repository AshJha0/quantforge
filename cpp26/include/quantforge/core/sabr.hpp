#pragma once
// SABR: Hagan formula, density check, calibration, arbitrage-free recipe: 05-volatility/sabr.md.
#include <optional>
#include <string_view>
#include <vector>

namespace quantforge {

struct SabrParameters {
    double alpha, beta, rho, nu;
};

/// The common checks, in order. `f` and `strikes` are shifted.
/// E_DOMAIN unless alpha, beta, rho and nu are finite (F-2).
void require_finite(const SabrParameters& p, std::string_view field);
void check_sabr(double t, const SabrParameters& p, double f, const std::vector<double>& strikes);
/// Lognormal vol on the shifted forward f and strike x.
/// unchecked: caller guarantees finite inputs
double hagan_vol(double f, double x, double t, const SabrParameters& p);

struct SabrDensity {
    std::vector<double> density;
    double min_density;
    bool negative;
};
SabrDensity sabr_density(double f, const std::vector<double>& strikes, double t, const SabrParameters& p, double h);

struct SabrFit {
    double alpha, rho, nu, rmse;
};
SabrFit sabr_calibrate(double f, double t, double beta, const std::vector<double>& strikes, const std::vector<double>& vols,
                       const std::optional<std::vector<double>>& weights);

struct ArbFreeGrid {
    long long cells, cells_below, steps;
};
struct ArbFreeResult {
    std::vector<double> call_prices;
    std::vector<std::optional<double>> vols;
    double mass, mean, absorbed, min_density;
};
/// `f0` and `strikes` are on the shifted axis.
ArbFreeResult sabr_arbfree(double f0, const std::vector<double>& strikes, double t, const SabrParameters& p, const ArbFreeGrid& grid);

}  // namespace quantforge
