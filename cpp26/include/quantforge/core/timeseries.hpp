#pragma once
#include <optional>
#include <vector>

#include "quantforge/core/dates.hpp"

namespace quantforge {

using MaybeReal = std::optional<double>;

enum class ReturnKind { Simple, Log };
enum class RollingStatistic { Mean, Stdev };
enum class ResampleFrequency { Week, Month };

std::vector<double> returns(const std::vector<double>& prices, ReturnKind kind);
std::vector<MaybeReal> rolling(const std::vector<double>& x, long long window, RollingStatistic statistic);
std::vector<double> ewma_variance(const std::vector<double>& r, double lambda);
std::vector<double> autocorrelation(const std::vector<double>& x, long long max_lag);
double ljung_box(const std::vector<double>& x, long long max_lag);

struct Ar1 {
    double constant, phi, sigma;
};
Ar1 ar1(const std::vector<double>& x);

struct Resampled {
    std::vector<Date> dates;
    std::vector<double> values;
};
Resampled resample_last(const std::vector<Date>& dates, const std::vector<MaybeReal>& values, ResampleFrequency f);
std::vector<MaybeReal> forward_fill(const std::vector<MaybeReal>& values, long long limit);

}  // namespace quantforge
