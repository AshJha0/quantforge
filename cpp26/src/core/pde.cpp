#include <cmath>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/models.hpp"

namespace quantforge {
namespace {

using Vec = std::vector<double>;

struct Grid {
    const PdeInputs& in;
    std::size_t J;
    double h, lower, centre, upper;  // operator coefficients l, c, u
    Vec x;

    double left(double tau) const {
        if (in.option == OptionType::Call) return 0.0;
        return in.strike * std::exp(-in.r * tau) - std::exp(x.front()) * std::exp(-in.q * tau);
    }
    double right(double tau) const {
        if (in.option == OptionType::Put) return 0.0;
        return std::exp(x.back()) * std::exp(-in.q * tau) - in.strike * std::exp(-in.r * tau);
    }

    // One theta step from tau to tau + s, in place.
    void step(Vec& v, double tau, double s, double theta) const {
        const double a = theta * s, b = (1.0 - theta) * s;
        const double new_left = left(tau + s), new_right = right(tau + s);
        v.front() = left(tau);
        v.back() = right(tau);
        Vec diag(J - 1), rhs(J - 1);
        for (std::size_t j = 1; j < J; ++j)
            rhs[j - 1] = v[j] + b * (lower * v[j - 1] + centre * v[j] + upper * v[j + 1]);
        rhs.front() += a * lower * new_left;
        rhs.back() += a * upper * new_right;
        const double sub = -a * lower, sup = -a * upper, mid = 1.0 - a * centre;
        diag[0] = mid;
        for (std::size_t i = 1; i < J - 1; ++i) {
            const double w = sub / diag[i - 1];
            diag[i] = mid - w * sup;
            rhs[i] -= w * rhs[i - 1];
        }
        v[J - 1] = rhs[J - 2] / diag[J - 2];
        for (std::size_t i = J - 2; i-- > 0;) v[i + 1] = (rhs[i] - sup * v[i + 2]) / diag[i];
        v.front() = new_left;
        v.back() = new_right;
    }
};

double cell_average(const PdeInputs& in, double x, double h) {
    const double k = std::log(in.strike), lo = x - h / 2.0, hi = x + h / 2.0;
    if (in.option == OptionType::Call) {
        if (hi <= k) return 0.0;
        const double l = std::max(lo, k);
        return (std::exp(hi) - std::exp(l) - in.strike * (hi - l)) / h;
    }
    if (lo >= k) return 0.0;
    const double u = std::min(hi, k);
    return (in.strike * (u - lo) - std::exp(u) + std::exp(lo)) / h;
}

}  // namespace

PdeResult pde_bs_european(const PdeInputs& in) {
    if (in.spot <= 0.0 || in.strike <= 0.0 || in.sigma <= 0.0 || in.t <= 0.0 || in.width <= 0.0)
        throw Error("E_DOMAIN", "spot, strike, sigma, t and width must be positive");
    if (in.space_steps % 2 != 0 || in.space_steps < 20) throw Error("E_INPUT", "space_steps must be even and at least 20", "space_steps");
    if (in.time_steps < 2) throw Error("E_INPUT", "time_steps must be at least 2", "time_steps");
    if (in.rannacher_steps < 0 || in.rannacher_steps >= in.time_steps)
        throw Error("E_INPUT", "rannacher_steps must be 0 to time_steps - 1", "rannacher_steps");

    const auto J = std::size_t(in.space_steps);
    const double h = 2.0 * in.width * in.sigma * std::sqrt(in.t) / double(J);
    const double dt = in.t / double(in.time_steps);
    const double a = in.sigma * in.sigma / 2.0, b = in.r - in.q - a;
    Grid g{in, J, h, a / (h * h) - b / (2.0 * h), -2.0 * a / (h * h) - in.r, a / (h * h) + b / (2.0 * h), Vec(J + 1)};
    const double centre_x = std::log(in.spot);
    Vec v(J + 1);
    for (std::size_t j = 0; j <= J; ++j) {
        g.x[j] = centre_x + (double(j) - double(J / 2)) * h;
        v[j] = cell_average(in, g.x[j], h);
    }
    long long done = 0;
    for (; done < in.rannacher_steps; ++done) {
        const double tau = double(done) * dt;
        g.step(v, tau, dt / 2.0, 1.0);
        g.step(v, tau + dt / 2.0, dt / 2.0, 1.0);
    }
    for (; done < in.time_steps; ++done) g.step(v, double(done) * dt, dt, 0.5);

    const std::size_t m = J / 2;
    const double vx = (v[m + 1] - v[m - 1]) / (2.0 * h);
    const double vxx = (v[m + 1] - 2.0 * v[m] + v[m - 1]) / (h * h);
    return {v[m], vx / in.spot, (vxx - vx) / (in.spot * in.spot), h};
}

}  // namespace quantforge
