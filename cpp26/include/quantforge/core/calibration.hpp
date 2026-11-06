#pragma once
// Calibration core and hedge solve: 03-calibration/least-squares.md, 08-hedging/stage-b-hedges.md.
#include <optional>
#include <string>
#include <vector>

#include "quantforge/core/linalg.hpp"
#include "quantforge/core/rates.hpp"

namespace quantforge {

enum class FitModel { Linear, Exponential, NelsonSiegel, Rosenbrock };
enum class FitMethod { GaussNewton, LevenbergMarquardt, Bfgs };

struct FitInputs {
    FitModel model;
    std::vector<double> x, y, start;
    FitMethod method;
    std::optional<std::vector<double>> weights;
    double regularisation = 0.0;
    std::optional<std::vector<double>> prior, lower, upper;
    long long max_iter = 1000;
};

struct FitResult {
    std::vector<double> parameters;
    double objective;
    long long iterations;
    std::string status;
    std::vector<double> residuals;
};

FitResult fit(const FitInputs& in);

struct Breach {
    std::size_t index;
    std::string side;
    double distance;
};
std::vector<Breach> check_bid_ask(const std::vector<double>& fitted, const std::vector<double>& bid,
                                  const std::vector<double>& ask);

struct CurveReport {
    Matrix jacobian;
    double condition_number, max_repricing_error;
};
CurveReport curve_report(const RateConvention& c, Date as_of, const std::vector<OisQuote>& quotes,
                         CurveInterpolation interpolation);

struct HedgeResult {
    std::vector<double> x, residual;
    double objective;
};
HedgeResult hedge_solve(const Matrix& a, const std::vector<double>& b, const std::vector<double>& weights,
                        const std::vector<double>& costs, double lambda);
double spread_cost(const std::vector<double>& quantities, const std::vector<double>& half_spreads);

}  // namespace quantforge
