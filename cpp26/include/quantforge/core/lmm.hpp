#pragma once
// Stage G wave 3b: LIBOR market model closed forms (04-pricing/lmm.md, rulings G-22, G-25).
#include <cstdint>
#include <vector>

#include "quantforge/core/shortrate.hpp"

namespace quantforge::lmm {

/// sigma_T(t) = (a + b (T - t)) e^{-c (T - t)} + d (ruling G-22).
struct Abcd {
    double a, b, c, d;
};
double vol_at(const Abcd& v, double T, double t);
/// integral_0^u sigma_Ti(t) sigma_Tj(t) dt, by composite 20-point Gauss-Legendre (exact to rounding for this integrand).
double covariance(const Abcd& v, double Ti, double Tj, double u);
double black(double F, double K, double v, bool call);
/// Simple forward over [s, t]; throws E_DOMAIN when it is not positive.
double forward(const shortrate::Curve& c, double s, double t);

struct CapFloor {
    double price;
    std::vector<double> caplets, forwards, black_vols;
};
/// Per unit notional.
CapFloor capfloor(const shortrate::Curve& c, const Abcd& v, const std::vector<double>& times, double K, bool cap);

struct Swaption {
    double price, swap_rate, annuity, black_vol;
};
/// Rebonato's frozen-weight approximation, per unit notional.
Swaption swaption_rebonato(const shortrate::Curve& c, const Abcd& v, double beta, double T0, const std::vector<double>& pay,
                           double K, bool payer);

/// Simulated LMM caplets (wave 3c, ruling G-26): terminal measure, log-Euler, predictor-corrector drift, sigma at the
/// step midpoint, Cholesky correlation. Grid t_0 = 0 < t_1 < ... < t_N; caplet k on [t_k, t_(k+1)], k = 1..N-1.
struct McCaplets {
    std::vector<double> price, se;
};
McCaplets simulate_caplets(const shortrate::Curve& c, const Abcd& v, double beta, const std::vector<double>& grid, double K,
                           long long paths, long long steps_per_year, std::uint64_t seed);

}  // namespace quantforge::lmm
