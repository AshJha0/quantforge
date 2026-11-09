#pragma once
// Stage E, E6: correlation validation, nearest correlation, implied correlation, dispersion
// (06-risk/correlation.md). Rulings E-B18 to E-B21.
#include <vector>

#include "quantforge/core/linalg.hpp"

namespace quantforge {

struct CorrValidation {
    bool symmetric, unit_diagonal, in_range, psd, valid;
    double min_eigenvalue;
};
CorrValidation corr_validate(const Matrix& m);

struct NearestCorr {
    Matrix matrix;
    double frobenius_distance;
};
NearestCorr corr_nearest(const Matrix& m);

double corr_implied(const std::vector<double>& weights, const std::vector<double>& vols, double index_vol);

struct Dispersion {
    double pnl, implied_correlation, realized_correlation, index_variance_notional;
    std::vector<double> constituent_variance_notionals;
};
Dispersion corr_dispersion(const std::vector<double>& weights, const std::vector<double>& vol_strikes, double index_vol_strike,
                           const std::vector<double>& realized_vols, double index_realized_vol, double vega_notional);

}  // namespace quantforge
