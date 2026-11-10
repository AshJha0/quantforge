#include "quantforge/core/sabr.hpp"

#include <algorithm>
#include <cmath>

#include "quantforge/core/black.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/finite.hpp"
#include "quantforge/core/smile.hpp"

namespace quantforge {
namespace {

using Vec = std::vector<double>;

[[noreturn]] void domain(const char* why) { throw Error("E_DOMAIN", why); }

}  // namespace

void require_finite(const SabrParameters& p, std::string_view field) {
    for (const double x : {p.alpha, p.beta, p.rho, p.nu}) require_finite(x, field);
}

void check_sabr(double t, const SabrParameters& p, double f, const Vec& strikes) {
    require_finite(t, "expiry_years");
    require_finite(p, "sabr");
    require_finite(f, "forward");
    require_finite(strikes, "strikes");
    if (t <= 0) domain("expiry_years is not above 0");
    if (p.alpha <= 0) domain("alpha is not above 0");
    if (p.beta < 0 || p.beta > 1) domain("beta is outside [0, 1]");
    if (std::fabs(p.rho) >= 1) domain("|rho| is not below 1");
    if (p.nu < 0) domain("nu is below 0");
    if (f <= 0) domain("shifted forward is not above 0");
    for (const double x : strikes)
        if (x <= 0) domain("shifted strike is not above 0");
}

double hagan_vol(double f, double x, double t, const SabrParameters& p) {
    const double one = 1 - p.beta, a = std::pow(f * x, one), root = std::sqrt(a), l = std::log(f / x);
    const double c = one * one * l * l;
    const double z = (p.nu / p.alpha) * root * l;
    double m;
    if (std::fabs(z) < 1e-7) {
        m = 1 - p.rho * z / 2 - (3 * p.rho * p.rho - 2) * z * z / 12;
    } else {
        m = z / std::log((std::sqrt(1 - 2 * p.rho * z + z * z) + z - p.rho) / (1 - p.rho));
    }
    const double den = root * (1 + c / 24 + c * c / 1920);
    const double h = 1 + t * (one * one * p.alpha * p.alpha / (24 * a) + p.rho * p.beta * p.nu * p.alpha / (4 * root) +
                              (2 - 3 * p.rho * p.rho) * p.nu * p.nu / 24);
    return p.alpha * m * h / den;
}

SabrDensity sabr_density(double f, const Vec& strikes, double t, const SabrParameters& p, double h) {
    require_finite(f, "forward");
    require_finite(strikes, "strikes");
    require_finite(t, "expiry_years");
    require_finite(p, "sabr");
    require_finite(h, "h");
    const auto call = [&](double x) { return black_price(f, x, hagan_vol(f, x, t, p), t, 1.0, 1.0); };
    SabrDensity out{{}, INFINITY, false};
    for (const double x : strikes) {
        out.density.push_back((call(x + h) - 2 * call(x) + call(x - h)) / (h * h));
        out.min_density = std::min(out.min_density, out.density.back());
    }
    out.negative = out.min_density < -1e-9;
    return out;
}

SabrFit sabr_calibrate(double f, double t, double beta, const Vec& strikes, const Vec& vols, const std::optional<Vec>& weights) {
    require_finite(f, "forward");
    require_finite(t, "expiry_years");
    require_finite(beta, "beta");
    require_finite(strikes, "strikes");
    require_finite(vols, "vols");
    require_finite(weights, "weights");
    const std::size_t n = strikes.size();
    if (n < 3 || vols.size() != n || (weights && weights->size() != n)) throw Error("E_INPUT", "too few strikes, or lengths differ");
    for (std::size_t i = 1; i < n; ++i)
        if (!(strikes[i - 1] < strikes[i])) throw Error("E_INPUT", "strikes not strictly increasing");
    for (const double v : vols)
        if (v <= 0) domain("vol is not above 0");
    if (weights)
        for (const double w : *weights)
            if (w <= 0) domain("weight is not above 0");
    const auto weight = [&](std::size_t i) { return weights ? (*weights)[i] : 1.0; };
    const auto unpack = [&](const Vec& p) { return SabrParameters{std::exp(p[0]), beta, std::tanh(p[1]), std::exp(p[2])}; };
    const Residuals residuals = [&](const Vec& p) {
        const SabrParameters s = unpack(p);
        Vec r(n);
        for (std::size_t i = 0; i < n; ++i) r[i] = std::sqrt(weight(i)) * (hagan_vol(f, strikes[i], t, s) - vols[i]);
        return r;
    };
    // The vol nearest the money sets the scale of alpha.
    std::size_t near = 0;
    for (std::size_t i = 0; i < n; ++i)
        if (std::fabs(strikes[i] - f) < std::fabs(strikes[near] - f)) near = i;
    const double alpha0 = vols[near] * std::pow(f, 1 - beta);
    std::vector<Vec> starts;
    for (const double scale : {0.7, 1.0, 1.4})
        for (const double rho : {-0.7, -0.3, 0.0, 0.3, 0.7})
            for (const double nu : {0.05, 0.2, 0.5, 1.0, 2.0}) starts.push_back({std::log(scale * alpha0), std::atanh(rho), std::log(nu)});
    const Vec p = best_fit(residuals, starts);
    const SabrParameters s = unpack(p);
    const Vec r = residuals(p);
    double total = 0.0, sum_weight = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        total += r[i] * r[i];
        sum_weight += weight(i);
    }
    return {s.alpha, s.rho, s.nu, std::sqrt(total / sum_weight)};
}

ArbFreeResult sabr_arbfree(double f0, const Vec& strikes, double t, const SabrParameters& p, const ArbFreeGrid& grid) {
    require_finite(f0, "forward");
    require_finite(strikes, "strikes");
    require_finite(t, "expiry_years");
    require_finite(p, "sabr");
    const std::size_t cells = std::size_t(grid.cells), start = std::size_t(grid.cells_below) - 1;  // 0-based cell of f0
    const double beta = p.beta, one = 1 - beta;
    const double h = f0 / (double(grid.cells_below) - 0.5), u_max = double(grid.cells) * h;
    const double dt = t / double(grid.steps), lambda = dt / (h * h);
    for (const double x : strikes)
        if (x >= u_max) throw Error("E_INPUT", "strike is at or beyond the top of the grid");

    Vec u(cells), half_dsq(cells), g(cells);
    const double f_one = std::pow(f0, one), f_beta = std::pow(f0, beta);
    for (std::size_t j = 0; j < cells; ++j) {
        u[j] = (double(j) + 0.5) * h;
        const double z = (std::pow(u[j], one) - f_one) / one;
        half_dsq[j] = (p.alpha * p.alpha + 2 * p.rho * p.alpha * p.nu * z + p.nu * p.nu * z * z) * std::pow(u[j], 2 * beta) / 2;
        if (beta == 0) g[j] = 0.0;
        else if (j == start) g[j] = beta * std::pow(f0, beta - 1);
        else g[j] = (std::pow(u[j], beta) - f_beta) / (u[j] - f0);
    }

    Vec q(cells, 0.0), m(cells), diag(cells), upper(cells), right(cells);
    q[start] = 1.0 / h;
    double p_left = 0.0, p_right = 0.0;
    const double growth = p.rho * p.nu * p.alpha;
    for (long long n = 1; n <= grid.steps; ++n) {
        const double time = double(n) * dt;
        for (std::size_t j = 0; j < cells; ++j) m[j] = half_dsq[j] * std::exp(growth * g[j] * time);
        // Thomas on: -l m[j-1] q[j-1] + (1 + 2 l m[j]) q[j] - l m[j+1] q[j+1] = old; the ghosts make the ends 3 l m.
        for (std::size_t j = 0; j < cells; ++j) {
            const double centre = 1 + (j == 0 || j + 1 == cells ? 3.0 : 2.0) * lambda * m[j];
            const double lower = j > 0 ? -lambda * m[j - 1] : 0.0;
            const double up = j + 1 < cells ? -lambda * m[j + 1] : 0.0;
            if (j == 0) {
                diag[j] = centre;
                right[j] = q[j];
            } else {
                const double w = lower / diag[j - 1];
                diag[j] = centre - w * upper[j - 1];
                right[j] = q[j] - w * right[j - 1];
            }
            upper[j] = up;
        }
        q[cells - 1] = right[cells - 1] / diag[cells - 1];
        for (std::size_t j = cells - 1; j-- > 0;) q[j] = (right[j] - upper[j] * q[j + 1]) / diag[j];
        p_left += 2 * dt * m[0] * q[0] / h;
        p_right += 2 * dt * m[cells - 1] * q[cells - 1] / h;
    }

    ArbFreeResult out{};
    double mass = 0.0, mean = 0.0;
    out.min_density = INFINITY;
    for (std::size_t j = 0; j < cells; ++j) {
        mass += q[j] * h;
        mean += u[j] * q[j] * h;
        out.min_density = std::min(out.min_density, q[j]);
    }
    out.mass = mass + p_left + p_right;
    out.mean = mean + u_max * p_right;
    out.absorbed = p_left;
    for (const double x : strikes) {
        const std::size_t c = std::min(std::size_t(x / h), cells - 1);
        const double edge = double(c + 1) * h;
        double call = 0.0;
        for (std::size_t j = c + 1; j < cells; ++j) call += (u[j] - x) * q[j] * h;
        call += q[c] * (edge - x) * (edge - x) / 2 + (u_max - x) * p_right;
        out.call_prices.push_back(call);
        if (call <= std::max(f0 - x, 0.0) || call >= f0) {
            out.vols.push_back(std::nullopt);
            continue;
        }
        OptionInput o{VolModel::Black76, OptionType::Call, x, t};
        o.forward = f0;
        o.discount_factor = 1.0;
        out.vols.push_back(implied_vol_unchecked(o, call));
    }
    return out;
}

}  // namespace quantforge
