#pragma once
#include <cstddef>
#include <optional>
#include <vector>

namespace quantforge {

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
    double alpha, beta, r_squared, se_alpha, se_beta;
};
Ols ols(const std::vector<double>& x, const std::vector<double>& y);

}  // namespace quantforge
