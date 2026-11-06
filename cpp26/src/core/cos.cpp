#include <cmath>
#include <complex>
#include <numbers>

#include "quantforge/core/error.hpp"
#include "quantforge/core/models.hpp"

namespace quantforge {
namespace {

using Complex = std::complex<double>;
constexpr Complex I{0.0, 1.0};

Complex phi_black_scholes(double u, const CosInputs& in) {
    const double s2 = in.model.sigma * in.model.sigma;
    return std::exp(I * (u * (in.r - in.q - s2 / 2.0) * in.t) - s2 * u * u * in.t / 2.0);
}

Complex phi_heston(double u, const CosInputs& in) {
    if (u == 0.0) return 1.0;
    const CosModel& m = in.model;
    const double s2 = m.sigma * m.sigma, t = in.t;
    const Complex beta = m.kappa - m.rho * m.sigma * I * u;
    const Complex d = std::sqrt(beta * beta + s2 * (I * u + u * u));
    const Complex g = (beta - d) / (beta + d);
    const Complex e = std::exp(-d * t);
    const Complex one_minus = 1.0 - g * e;
    return std::exp(I * (u * (in.r - in.q) * t) +
                    (m.kappa * m.theta / s2) * ((beta - d) * t - 2.0 * std::log(one_minus / (1.0 - g))) +
                    (m.v0 / s2) * (beta - d) * (1.0 - e) / one_minus);
}

}  // namespace

CosResult cos_european(const CosInputs& in) {
    const CosModel& m = in.model;
    const bool heston = m.name == CosModelName::Heston;
    if (in.spot <= 0.0 || in.strike <= 0.0 || in.t <= 0.0 || in.truncation <= 0.0 || m.sigma <= 0.0)
        throw Error("E_DOMAIN", "spot, strike, t, truncation and sigma must be positive");
    if (heston && (m.v0 <= 0.0 || m.kappa <= 0.0 || m.theta <= 0.0))
        throw Error("E_DOMAIN", "v0, kappa and theta must be positive");
    if (heston && std::fabs(m.rho) >= 1.0) throw Error("E_DOMAIN", "|rho| must be below 1", "rho");
    if (in.terms < 2) throw Error("E_INPUT", "terms must be at least 2", "terms");

    const double w = heston ? (m.theta + (m.v0 - m.theta) * (1.0 - std::exp(-m.kappa * in.t)) / (m.kappa * in.t)) * in.t
                            : m.sigma * m.sigma * in.t;
    const double x = std::log(in.spot / in.strike);
    const double c1 = x + (in.r - in.q) * in.t - w / 2.0;
    const double a = c1 - in.truncation * std::sqrt(w), b = c1 + in.truncation * std::sqrt(w);
    if (a >= 0.0 || b <= 0.0) throw Error("E_INPUT", "the range does not hold the strike");

    double sum = 0.0;
    for (long long k = 0; k < in.terms; ++k) {
        const double u = double(k) * std::numbers::pi / (b - a);
        const double angle = u * (0.0 - a);
        const double chi = (std::cos(angle) + u * std::sin(angle) - std::exp(a)) / (1.0 + u * u);
        const double psi = k == 0 ? -a : std::sin(angle) / u;
        const double v = 2.0 / (b - a) * in.strike * (psi - chi);
        const Complex phi = heston ? phi_heston(u, in) : phi_black_scholes(u, in);
        const double term = (phi * std::exp(I * (u * (x - a)))).real() * v;
        sum += k == 0 ? term / 2.0 : term;
    }
    const double put = std::exp(-in.r * in.t) * sum;
    const double price = in.option == OptionType::Put
                             ? put
                             : put + in.spot * std::exp(-in.q * in.t) - in.strike * std::exp(-in.r * in.t);
    return {price, a, b};
}

}  // namespace quantforge
