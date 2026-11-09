#pragma once
#include <cstddef>
#include <optional>
#include <vector>

namespace quantforge {

/// Mean and deviations, shifted by the first value first, so that a large mean loses nothing.
struct Centred {
    double mean;
    std::vector<double> d;
};
/// Internal helper over checked data; unchecked: caller guarantees finite inputs.
Centred centre(const std::vector<double>& x);
/// The zero-variance test: exact, so rounding cannot hide it.
/// unchecked: caller guarantees finite inputs
bool all_equal(const std::vector<double>& x);

/// Raw kernels, defined at the infinities; unchecked: caller guarantees finite inputs.
double normal_pdf(double x);
double normal_cdf(double x);

struct Summary {
    std::size_t count;
    double mean, variance, stdev;
    std::optional<double> skewness, excess_kurtosis;
    double min, max;
};
Summary summary(const std::vector<double>& x);

std::vector<double> quantiles(std::vector<double> x, const std::vector<double>& p);

struct Covariance {
    double covariance;
    std::optional<double> correlation;
};
Covariance covariance(const std::vector<double>& x, const std::vector<double>& y);

struct Ols {
    double alpha, beta;
    std::optional<double> r_squared;
    double se_alpha, se_beta;
};
Ols ols(const std::vector<double>& x, const std::vector<double>& y);

}  // namespace quantforge
