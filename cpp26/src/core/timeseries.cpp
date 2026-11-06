#include "quantforge/core/timeseries.hpp"

#include <cmath>

#include "quantforge/core/error.hpp"
#include "quantforge/core/stats.hpp"

namespace quantforge {
namespace {

void check_lag(const std::vector<double>& x, long long max_lag) {
    if (max_lag < 1 || max_lag >= std::ssize(x)) throw Error("E_INPUT", "max_lag must be at least 1 and below n", "max_lag");
}

// Week number from a Monday; 1970-01-01 was a Thursday.
long long bucket(Date d, ResampleFrequency f) {
    if (f == ResampleFrequency::Month) return year_of(d) * 12LL + month_of(d);
    const long long n = d.time_since_epoch().count() + 3;
    return n >= 0 ? n / 7 : -((6 - n) / 7);
}

}  // namespace

std::vector<double> returns(const std::vector<double>& p, ReturnKind kind) {
    if (p.size() < 2) throw Error("E_INPUT", "at least 2 prices are needed", "prices");
    for (const double v : p)
        if (v <= 0.0) throw Error("E_DOMAIN", "prices must be positive", "prices");
    std::vector<double> r;
    r.reserve(p.size() - 1);
    for (std::size_t i = 1; i < p.size(); ++i)
        r.push_back(kind == ReturnKind::Simple ? p[i] / p[i - 1] - 1.0 : std::log(p[i] / p[i - 1]));
    return r;
}

std::vector<MaybeReal> rolling(const std::vector<double>& x, long long window, RollingStatistic statistic) {
    if (window < 2 || window > std::ssize(x)) throw Error("E_INPUT", "window must be 2 to n", "window");
    const auto w = std::size_t(window);
    std::vector<MaybeReal> out(x.size());
    for (std::size_t end = w - 1; end < x.size(); ++end) {
        double m = 0.0;
        for (std::size_t i = end + 1 - w; i <= end; ++i) m += x[i];
        m /= double(w);
        if (statistic == RollingStatistic::Mean) {
            out[end] = m;
            continue;
        }
        double s = 0.0;
        for (std::size_t i = end + 1 - w; i <= end; ++i) s += (x[i] - m) * (x[i] - m);
        out[end] = std::sqrt(s / double(w - 1));
    }
    return out;
}

std::vector<double> ewma_variance(const std::vector<double>& r, double lambda) {
    if (r.empty()) throw Error("E_INPUT", "at least 1 return is needed", "returns");
    if (lambda <= 0.0 || lambda >= 1.0) throw Error("E_DOMAIN", "lambda must lie in (0, 1)", "lambda");
    std::vector<double> v(r.size());
    v[0] = r[0] * r[0];
    for (std::size_t t = 1; t < r.size(); ++t) v[t] = lambda * v[t - 1] + (1.0 - lambda) * r[t] * r[t];
    return v;
}

std::vector<double> autocorrelation(const std::vector<double>& x, long long max_lag) {
    check_lag(x, max_lag);
    double m = 0.0;
    for (const double v : x) m += v;
    m /= double(x.size());
    double denominator = 0.0;
    for (const double v : x) denominator += (v - m) * (v - m);
    if (denominator == 0.0) throw Error("E_DOMAIN", "x has zero variance", "x");
    std::vector<double> acf;
    for (std::size_t k = 1; k <= std::size_t(max_lag); ++k) {
        double s = 0.0;
        for (std::size_t t = k; t < x.size(); ++t) s += (x[t] - m) * (x[t - k] - m);
        acf.push_back(s / denominator);
    }
    return acf;
}

double ljung_box(const std::vector<double>& x, long long max_lag) {
    const auto acf = autocorrelation(x, max_lag);
    const double n = double(x.size());
    double s = 0.0;
    for (std::size_t k = 1; k <= acf.size(); ++k) s += acf[k - 1] * acf[k - 1] / (n - double(k));
    return n * (n + 2.0) * s;
}

Ar1 ar1(const std::vector<double>& x) {
    if (x.size() < 4) throw Error("E_INPUT", "at least 4 values are needed", "x");
    const std::vector<double> lagged(x.begin(), x.end() - 1), current(x.begin() + 1, x.end());
    double mx = 0.0, my = 0.0;
    for (std::size_t i = 0; i < lagged.size(); ++i) {
        mx += lagged[i];
        my += current[i];
    }
    mx /= double(lagged.size());
    my /= double(lagged.size());
    double sxx = 0.0, sxy = 0.0;
    for (std::size_t i = 0; i < lagged.size(); ++i) {
        sxx += (lagged[i] - mx) * (lagged[i] - mx);
        sxy += (lagged[i] - mx) * (current[i] - my);
    }
    if (sxx == 0.0) throw Error("E_SINGULAR", "x has zero variance", "x");
    const double phi = sxy / sxx, constant = my - phi * mx;
    double sse = 0.0;
    for (std::size_t i = 0; i < lagged.size(); ++i) {
        const double e = current[i] - constant - phi * lagged[i];
        sse += e * e;
    }
    return {constant, phi, std::sqrt(sse / double(x.size() - 3))};
}

Resampled resample_last(const std::vector<Date>& dates, const std::vector<MaybeReal>& values, ResampleFrequency f) {
    if (dates.size() != values.size()) throw Error("E_INPUT", "dates and values differ in length");
    for (std::size_t i = 1; i < dates.size(); ++i)
        if (!(dates[i - 1] < dates[i])) throw Error("E_INPUT", "dates must be strictly increasing", "dates");
    Resampled out;
    bool open = false;
    long long current = 0;
    for (std::size_t i = 0; i < dates.size(); ++i) {
        if (!values[i]) continue;
        const long long b = bucket(dates[i], f);
        if (open && b == current) {
            out.dates.back() = dates[i];
            out.values.back() = *values[i];
        } else {
            out.dates.push_back(dates[i]);
            out.values.push_back(*values[i]);
            open = true;
            current = b;
        }
    }
    return out;
}

std::vector<MaybeReal> forward_fill(const std::vector<MaybeReal>& values, long long limit) {
    if (limit < 1) throw Error("E_INPUT", "limit must be at least 1", "limit");
    std::vector<MaybeReal> out = values;
    long long last = -1;
    for (long long i = 0; i < std::ssize(values); ++i) {
        const auto u = std::size_t(i);
        if (values[u]) last = i;
        else if (last >= 0 && i - last <= limit) out[u] = values[std::size_t(last)];
    }
    return out;
}

}  // namespace quantforge
