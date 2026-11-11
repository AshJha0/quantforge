#pragma once
// Stage I wave 1, hedge solvers (specifications/08-hedging/hedge-solvers.md; rulings I-1 to I-14).
// Every rank or singularity decision compares with 1e-12 times the largest value of the stated matrix (I-3).
#include <optional>
#include <vector>

#include "quantforge/core/linalg.hpp"

namespace quantforge::hedging {

using Vec = std::vector<double>;
using Bound = std::optional<double>;

/// The one relative threshold of ruling I-3.
inline constexpr double singular_threshold = 1e-12;

/// Symmetric eigen-decomposition by cyclic Jacobi. values ascending; vectors[i][k] is entry i of the
/// unit eigenvector of values[k]. unchecked: caller guarantees a finite symmetric square matrix.
struct Eigen {
    Vec values;
    Matrix vectors;
};
Eigen jacobi_eigen(Matrix s);

enum class Singular { Error, MinNorm };

/// hedge.qp.solve: minimise sum_i w_i (A x + b)_i^2 + ridge |x|^2 subject to E x = e and the bounds.
struct QpProblem {
    Matrix a;
    Vec b, weights;
    double ridge = 0.0;
    std::optional<Matrix> eq_matrix;
    std::optional<Vec> eq_rhs;
    std::optional<std::vector<Bound>> lower, upper;
    Singular singular = Singular::Error;
};
struct QpResult {
    Vec x, residual;
    double objective = 0.0;
    long long rank = 0;
};
/// Checks in the spec's order: E_INPUT, E_DOMAIN, E_SINGULAR, E_INFEASIBLE.
QpResult solve_qp(const QpProblem& p);

/// hedge.integer.solve: the same objective over x = lot_sizes * n, n integer within optional lot bounds.
struct IntegerProblem {
    Matrix a;
    Vec b, weights;
    double ridge = 0.0;
    Vec lot_sizes;
    std::optional<std::vector<std::optional<long long>>> lower_lots, upper_lots;
};
struct IntegerResult {
    std::vector<long long> lots;
    Vec x, residual;
    double objective = 0.0, continuous_objective = 0.0, rounding_cost = 0.0;
};
IntegerResult solve_integer(const IntegerProblem& p);

/// hedge.minvar.ratio. Index 0 of the covariance is the position, 1..k one unit of each hedge.
struct MinVarResult {
    Vec hedge;
    double variance_before = 0.0, variance_after = 0.0, effectiveness = 0.0;
};
MinVarResult min_variance(const Matrix& covariance);
/// Sample covariance (divisor T - 1) of the exposure and hedge series, index 0 the exposure.
/// E_INPUT for k < 1, unequal lengths or T < k + 2.
Matrix sample_covariance(const Vec& exposure, const Matrix& hedge_series);

enum class Instrument { Call, Put, Underlying };
struct Position {
    Instrument instrument = Instrument::Underlying;
    std::optional<double> strike, expiry_years;
    double quantity = 0.0;
};
struct Market {
    double spot = 0.0, rate = 0.0, dividend_yield = 0.0, volatility = 0.0;
};
struct Greeks {
    double delta = 0.0, gamma = 0.0, vega = 0.0;
};
enum class Greek { Delta, Gamma, Vega };
/// Per-unit Black-Scholes-Merton Greeks; vega per unit of volatility (I-9). unchecked: caller validates.
Greeks unit_greeks(const Market& m, const Position& p);
struct GreekHedge {
    Vec quantities;
    Greeks before, after;
};
GreekHedge neutralise(const Market& m, const std::vector<Position>& book, const std::vector<Position>& hedges,
                      const std::vector<Greek>& targets);

enum class Rounding { Nearest, None };
struct BetaHedge {
    double contracts = 0.0, contracts_held = 0.0, beta_after = 0.0;
};
BetaHedge beta_futures(double value, double beta, double target_beta, double futures_price, double multiplier,
                       Rounding rounding);

struct ResidualReport {
    Vec residual;
    double variance_before = 0.0, variance_after = 0.0, volatility_after = 0.0, effectiveness = 0.0;
    Vec contributions;
};
ResidualReport residual_report(const Matrix& a, const Vec& b, const Vec& x, const Matrix& covariance);

}  // namespace quantforge::hedging
