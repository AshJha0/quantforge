#pragma once
// Stage E, E1: arbitrage-free SVI surfaces (05-volatility/arb-free-surfaces.md) and local vol, forward vol,
// smile dynamics and vol of vol (05-volatility/local-and-forward-vol.md). Rulings E-A1 to E-A8.
#include <string>
#include <vector>

#include "quantforge/core/black.hpp"
#include "quantforge/core/smile.hpp"

namespace quantforge {

struct SviSlice {
    double expiry_years;
    Svi svi;
};
/// The slices object checks, in the spec's order (E_INPUT, E_DOMAIN, then E_LIMIT above 100 slices).
void check_slices(const std::vector<SviSlice>& slices);
/// The two halves of check_slices, for operations that put every E_INPUT rule first (ruling E-A37).
void check_slices_input(const std::vector<SviSlice>& slices);
void check_slices_domain(const std::vector<SviSlice>& slices);

struct GridViolation {
    std::size_t expiry_index, k_index;
};
struct WingViolation {
    std::size_t expiry_index;
    std::string side, kind;  // LEFT / RIGHT; LEE / CALENDAR
};
struct SviSurfaceCheck {
    std::vector<GridViolation> butterfly, calendar;
    std::vector<WingViolation> wings;
    bool arbitrage_free() const { return butterfly.empty() && calendar.empty() && wings.empty(); }
};
/// Checks slices and grid, then (reject and not arbitrage-free) throws E_ARBITRAGE.
SviSurfaceCheck svi_surface_check(const std::vector<SviSlice>& slices, const std::vector<double>& k, bool reject);

Svi ssvi_to_svi(double rho, double eta, double gamma, double theta);

struct SurfaceFit {
    std::vector<SviSlice> slices;
    std::vector<double> rmse;
    SviSurfaceCheck check;
};
SurfaceFit svi_fit_surface(const std::vector<double>& expiries, const std::vector<double>& k,
                           const std::vector<std::vector<double>>& total_variance, bool reject);

struct LocalVolPoint {
    double expiry_years, log_moneyness;
};
struct LocalVol {
    std::vector<double> total_variance, implied_vol, local_vol;
};
LocalVol local_vol_dupire(const std::vector<SviSlice>& slices, const std::vector<LocalVolPoint>& points);

std::vector<double> forward_vols(const std::vector<double>& expiries, const std::vector<double>& vols);

enum class SmileRule { StickyStrike, StickyDelta };
struct SmileDynamicsInputs {
    Svi svi;
    double expiry_years, spot, spot_shifted, rate, dividend_yield;
    std::vector<double> strikes;
    SmileRule rule;
    OptionType type;
};
struct SmileDynamics {
    std::vector<double> vols_base, vols_shifted, prices_base, prices_shifted, deltas;
};
SmileDynamics smile_dynamics(const SmileDynamicsInputs& in);

enum class VolChange { Log, Absolute };
struct VolOfVol {
    double mean_change, vol_of_vol;
};
VolOfVol vol_of_vol(const std::vector<double>& vols, double periods_per_year, VolChange method);

}  // namespace quantforge
