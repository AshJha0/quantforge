#include <cmath>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/models.hpp"
#include "quantforge/core/rng.hpp"
#include "quantforge/core/sobol.hpp"

namespace quantforge {
namespace {

using Vec = std::vector<double>;

struct Path {
    const McInputs& in;
    double log_spot, drift, vol, discount;

    double terminal(const Vec& z, double sign) const {
        double s = log_spot;
        for (const double v : z) s += drift + vol * (sign * v);
        return std::exp(s);
    }
    double payoff(double s_t) const {
        const double p = in.option == OptionType::Call ? s_t - in.strike : in.strike - s_t;
        return discount * std::max(p, 0.0);
    }
};

double mean_of(const Vec& v) {
    double s = 0.0;
    for (const double x : v) s += x;
    return s / double(v.size());
}

McResult mean_and_error(const Vec& y) {
    const double n = double(y.size()), m = mean_of(y);
    double s = 0.0;
    for (const double v : y) s += (v - m) * (v - m);
    return {m, std::sqrt(s / (n - 1.0)) / std::sqrt(n)};
}

}  // namespace

McResult mc_gbm_european(const McInputs& in) {
    if (in.spot <= 0.0 || in.strike <= 0.0 || in.sigma <= 0.0 || in.t <= 0.0)
        throw Error("E_DOMAIN", "spot, strike, sigma and t must be positive");
    if (in.paths < 2) throw Error("E_INPUT", "paths must be at least 2", "paths");
    if (in.steps < 1) throw Error("E_INPUT", "steps must be at least 1", "steps");
    if (in.method == McMethod::Sobol && in.steps > 64) throw Error("E_INPUT", "SOBOL allows at most 64 steps", "steps");

    const double dt = in.t / double(in.steps);
    const Path path{in, std::log(in.spot), (in.r - in.q - in.sigma * in.sigma / 2.0) * dt, in.sigma * std::sqrt(dt),
                    std::exp(-in.r * in.t)};
    const auto n = std::size_t(in.paths);
    Vec z(std::size_t(in.steps)), y(n);

    if (in.method == McMethod::Sobol) {
        Sobol sobol(int(in.steps));
        for (std::size_t i = 0; i < n; ++i) {
            sobol.next(z.data());
            for (double& v : z) v = ppnd16(v);
            y[i] = path.payoff(path.terminal(z, 1.0));
        }
        return mean_and_error(y);
    }

    Xoshiro256 rng(in.seed, in.stream);
    Vec control(in.method == McMethod::ControlVariate ? n : 0);
    for (std::size_t i = 0; i < n; ++i) {
        for (double& v : z) v = rng.next_normal();
        const double s_t = path.terminal(z, 1.0);
        if (in.method == McMethod::Antithetic) {
            y[i] = (path.payoff(s_t) + path.payoff(path.terminal(z, -1.0))) / 2.0;
        } else {
            y[i] = path.payoff(s_t);
            if (in.method == McMethod::ControlVariate) control[i] = path.discount * s_t;
        }
    }
    if (in.method == McMethod::ControlVariate) {
        const double mp = mean_of(y), mc = mean_of(control);
        double cov = 0.0, var = 0.0;
        for (std::size_t i = 0; i < n; ++i) {
            cov += (y[i] - mp) * (control[i] - mc);
            var += (control[i] - mc) * (control[i] - mc);
        }
        const double beta = cov / var, known = in.spot * std::exp(-in.q * in.t);
        for (std::size_t i = 0; i < n; ++i) y[i] -= beta * (control[i] - known);
    }
    return mean_and_error(y);
}

}  // namespace quantforge
