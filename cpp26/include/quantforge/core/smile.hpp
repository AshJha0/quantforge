#pragma once
// Delta conventions, SVI, SSVI: 05-volatility/smile-and-surface.md.
#include <functional>
#include <optional>
#include <vector>

#include "quantforge/core/linalg.hpp"
#include "quantforge/core/models.hpp"

namespace quantforge {

double normal_inverse(double p);

/// `scale` is s in the spec: 1 for FORWARD, the given scale for SPOT.
double delta_to_strike(double forward, double vol, double t, OptionType type, double delta, double scale);
double delta_from_strike(double forward, double vol, double t, OptionType type, double strike, double scale);

/// Levenberg-Marquardt on residuals from each start; returns the best point. r(p) may return non-finite values to refuse p.
using Residuals = std::function<std::vector<double>(const std::vector<double>&)>;
std::vector<double> best_fit(const Residuals& r, const std::vector<std::vector<double>>& starts);

struct Svi {
    double a, b, rho, m, sigma;
    double w(double k) const;
    double g(double k) const;
};
void check_svi(const Svi& s);

struct SviFit {
    Svi svi;
    double rmse;
};
SviFit svi_calibrate(const std::vector<double>& k, const std::vector<double>& w, const std::optional<std::vector<double>>& weights);

struct Ssvi {
    double rho, eta, gamma;
    double phi(double theta) const;
    double w(double k, double theta) const;
};
void check_ssvi(const Ssvi& s, const std::vector<double>& thetas);
bool ssvi_butterfly_free(const Ssvi& s, const std::vector<double>& thetas);
bool ssvi_calendar_free(const Ssvi& s, const std::vector<double>& thetas);

struct SsviFit {
    Ssvi ssvi;
    double rmse;
};
SsviFit ssvi_calibrate(const std::vector<double>& thetas, const std::vector<double>& k, const Matrix& w);

}  // namespace quantforge
