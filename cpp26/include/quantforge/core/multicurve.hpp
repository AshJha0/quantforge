#pragma once
// Multi-curve rates: dated overnight compounding, IBOR fallbacks, meeting-date step curves,
// futures convexity, CSA discounting, OIS index basis, joint bootstrap and the two curve fits.
#include <optional>
#include <string_view>
#include <vector>

#include "quantforge/core/rates.hpp"

namespace quantforge {

enum class ShiftMethod { None, Lookback, ObservationShift, Lockout };

struct Fixing {
    Date date;
    double rate;
};

struct DatedCompound {
    double compounded_rate, accrual, interest;
};
/// overnight-compounding.md. E_INPUT unless `c` is overnight.
DatedCompound compound_dated(const RateConvention& c, Date start, Date end, ShiftMethod method, long long shift_days,
                             const std::vector<Fixing>& fixings);

struct FallbackRate {
    double compounded_rate, spread_adjustment, fallback_rate;
};
/// E_SCHEMA for an IBOR outside the ISDA table.
FallbackRate fallback_rate(std::string_view ibor, Date start, Date end, const std::vector<Fixing>& fixings);

struct Step {
    Date date;
    double rate;
};

struct StepCurve {
    Date as_of;
    double base_rate;
    std::vector<Step> steps;
    std::vector<Jump> jumps;

    /// Finite base_rate, step rates and jump factors (E_DOMAIN), then step dates (E_INPUT), then jumps.
    void check() const;
    /// E_OUT_OF_RANGE before as_of. Call check() first.
    /// unchecked: caller guarantees finite inputs
    double discount(Date d) const;
    /// unchecked: caller guarantees finite inputs
    double forward(Date d) const;
};

struct StepFit {
    double base_rate;
    std::vector<double> step_rates;
    double max_repricing_error;
};
StepFit fit_steps(const RateConvention& c, Date as_of, const std::vector<Date>& step_dates,
                  const std::vector<OisQuote>& quotes, const std::vector<Jump>& jumps);

struct Convexity {
    double futures_rate, convexity, forward_rate;
};
Convexity futures_convexity(double price, double start_years, double end_years, double sigma, double mean_reversion);

struct FxForwardPoint {
    Date date;
    double forward;
};
struct CsaFx {
    double spot;
    std::vector<FxForwardPoint> forwards;
};
std::vector<double> csa_discount(const Curve& curve, double spread, const std::optional<CsaFx>& fx,
                                 const std::vector<Date>& dates);

double ois_index_spread(const RateConvention& c, Tenor tenor, const Curve& discount, const Curve& a, const Curve& b);

struct JointCurves {
    Curve discount, projection;
    double max_repricing_error;
};
JointCurves joint_bootstrap(const RateConvention& c, const RateConvention& index, Date as_of,
                            const std::vector<OisQuote>& ois_quotes, const std::vector<ProjectionQuote>& term_quotes,
                            CurveInterpolation interpolation, SolveMethod method);

struct SmoothFit {
    std::vector<double> forwards, fitted;
    double objective;
};
/// Empty `weights` means all 1.
SmoothFit smooth_fit(const std::vector<double>& knots, const std::vector<double>& maturities,
                     const std::vector<double>& zero_rates, double lambda, const std::optional<std::vector<double>>& weights);

struct RobustFit {
    std::vector<double> betas, residuals;
    std::vector<std::size_t> outliers;
    double objective;
};
RobustFit robust_fit(const std::vector<double>& maturities, const std::vector<double>& zero_rates, double tau, double delta);

}  // namespace quantforge

// ---- D3: cross-currency (02-curves/cross-currency.md); domestic USD SOFR, foreign EUR ESTR ----
namespace quantforge {

/// Quarterly dates start + 3k months, MODIFIED_FOLLOWING on the joint calendar; [start, e_1, ..., e_n].
std::vector<Date> xccy_schedule(Date start, long long months);
/// L = N [ sum ((P(s)/P(e) - 1) + m alpha) D(e) + D(T) - D(start) ].
double xccy_leg(const std::vector<Date>& dates, double notional, const Curve& projection, const Curve& discount, double spread);

struct XccyQuote {
    long long months;
    double spread;
};
SolvedCurve xccy_bootstrap(const Curve& foreign_projection, Date start, const std::vector<XccyQuote>& quotes,
                           CurveInterpolation interpolation);

struct NdfPrice {
    double pv, forward;
};
/// sign +1 for BUY.
NdfPrice ndf_price(const Curve& usd, const Curve& offshore, double spot, Date fixing_date, Date payment_date, double strike,
                   double usd_notional, double sign, std::optional<double> fixing);

}  // namespace quantforge
