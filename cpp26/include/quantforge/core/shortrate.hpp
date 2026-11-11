#pragma once
// Stage G: short-rate models (04-pricing/short-rate-models.md, rulings G-1 to G-21), Monte Carlo Greeks
// (06-risk/mc-greeks.md, G-10, G-15) and closed-form swap exposure (06-risk/xva-exposure.md, G-16).
// Inputs are validated by the CLI; these kernels assume finite, in-domain arguments unless a function says it throws.
#include <cstdint>
#include <optional>
#include <utility>
#include <vector>

namespace quantforge::shortrate {

enum class Model { Vasicek, Cir, HullWhite };

/// Log-linear discount curve with (0, 1) as its first node, flat forward beyond the last pillar.
struct Curve {
    std::vector<double> t, lnp;  // nodes, (0, 0) first
    static Curve from(const std::vector<double>& times, const std::vector<double>& dfs);
    double ln_p(double x) const;
    double df(double x) const;
    /// Right-hand instantaneous forward (ruling G-3).
    double fwd(double x) const;
};

struct Params {
    Model model = Model::HullWhite;
    double a = 0.0, sigma = 0.0, b = 0.0;  // b: long-term mean (Vasicek, CIR)
    double r0 = 0.0;                         // short rate at 0 (Vasicek, CIR)
    Curve curve;                             // Hull-White only
};

/// B = (1 - e^{-a tau}) / a, by expm1.
double b_factor(double a, double tau);
/// (B - tau) / a^2, with a series when a tau < 1e-2 (ruling G-2).
double b_minus_tau_over_a2(double a, double tau);
/// {ln A, B} with P(t, T) = A exp(-B r).
std::pair<double, double> ln_a_b(const Params& p, double t, double T);
/// P(t, T) given r(t) = r.
double bond(const Params& p, double t, double T, double r);
/// P(0, T): the curve (Hull-White) or the model at r0.
double bond0(const Params& p, double T);
/// Option at T on the bond to S, strike K per unit face.
double bond_option(const Params& p, double T, double S, double K, bool call);

double gamma_p(double s, double x);
double gamma_pq(double s, double x, bool upper);
double ncx2_tail(double x, double k, double lambda, bool upper);
double ncx2_sf(double x, double k, double lambda);
double ncx2_cdf(double x, double k, double lambda);

/// Per unit notional. Throws E_DOMAIN for CIR with no non-negative critical rate (ruling G-20).
struct Swaption {
    double price, forward_swap_rate, annuity;
};
Swaption swaption(const Params& p, double expiry, const std::vector<double>& payment_times, double fixed_rate, bool payer);
/// d price / d sigma for Hull-White or Vasicek (the critical-rate terms cancel), per unit notional.
double swaption_vega(const Params& p, double expiry, const std::vector<double>& payment_times, double fixed_rate, bool payer);

struct CapFloor {
    double price;
    std::vector<double> caplets;
};
/// Per unit notional.
CapFloor capfloor(const Params& p, const std::vector<double>& period_times, double strike, bool cap);

struct CalSwaption {
    double expiry;
    std::vector<double> payment_times;
    double fixed_rate;
    bool payer;
    double target;
};
struct Calibration {
    double sigma;
    std::vector<double> fitted;
    double rmse;
};
/// Hull-White sigma by least squares on [1e-4, 1] (ruling G-17); throws E_NO_CONVERGENCE at an end.
Calibration hw_calibrate(const Curve& curve, double a, const std::vector<CalSwaption>& strip);

struct Grid {
    long long nx, steps_per_year;
    double width;
};
/// Pinned scheme of ruling G-18, per unit notional.
double bermudan_swaption(const Params& p, const std::vector<double>& payment_times, double fixed_rate, bool payer,
                         const std::vector<double>& exercise_times, const Grid& g);
/// Q3b ladder (G-9, G-35): price and its reverse-mode derivatives with respect to the curve pillar discount factors
/// `P` (the curve's input values, in order), the mean reversion and sigma, per unit notional.
struct Ladder {
    double price;
    std::vector<double> d_discount_factors;
    double d_mean_reversion, d_sigma;
};
Ladder bermudan_ladder(const Params& p, const std::vector<double>& P, const std::vector<double>& payment_times,
                       double fixed_rate, bool payer, const std::vector<double>& exercise_times, const Grid& g);
/// Callable bond on the G-18 scheme (ruling G-21), per unit notional.
double callable_bond(const Params& p, const std::vector<double>& payment_times, double coupon,
                     const std::vector<double>& call_times, double call_price, const Grid& g);

struct G2 {
    double a, sigma, b, eta, rho;
    Curve curve;
};
double g2_bond(const G2& m, double t, double T, double x, double y);
double g2_bond_option(const G2& m, double T, double S, double K, bool call);

struct Exposure {
    std::vector<double> discounted_ee;
    std::optional<double> cva;
};
/// Per unit notional. exposure_times must be reset dates (checked by the caller).
Exposure swap_ee_hw(const Params& p, double start, const std::vector<double>& payment_times, double fixed_rate, bool pay,
                    const std::vector<double>& exposure_times, std::optional<std::pair<double, double>> hazard_recovery);

/// Wave 4c (G-42): exposure of a swap netting set at common reset dates, exact one-factor (LGM) integration.
struct SwapTrade {
    double notional, fixed_rate, start;
    bool pay;
    std::vector<double> payment_times;
};
struct PortfolioExposure {
    std::vector<double> discounted_ee, discounted_ene;
    std::vector<std::vector<double>> pfe;  // per quantile, per time
    double epe = 0.0, cva = 0.0;
};
PortfolioExposure portfolio_exposure_hw(const Params& p, const std::vector<SwapTrade>& trades, const std::vector<double>& times,
                                        const std::vector<double>& quantiles, double hazard, double recovery);
/// P(f(t) > y) for the deflated set value f at an exposure time t (the PFE property test: at y = PFE_q it is 1 - q).
double portfolio_prob_above_hw(const Params& p, const std::vector<SwapTrade>& trades, double t, double y);

}  // namespace quantforge::shortrate

namespace quantforge::mcgreeks {

enum class Payoff { Call, Put, DigitalCall };
enum class Method { Pathwise, LikelihoodRatio, Bump };
struct Inputs {
    double spot, strike, expiry_years, rate, dividend_yield, vol;
    Payoff payoff;
    Method method;
    long long paths;
    std::uint64_t seed;
    int stream = 0;
    double smoothing_width = 0.0, bump_relative = 0.0;
};
struct Result {
    double price, price_se, delta, delta_se, vega, vega_se;
};
Result greeks(const Inputs& in);
/// Per-path delta terms (for the variance tests of G-10 and G-10b).
std::vector<double> delta_terms(const Inputs& in);

}  // namespace quantforge::mcgreeks
