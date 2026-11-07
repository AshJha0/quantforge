#pragma once
// Stage B rates. The parts of 04-pricing/pricing-framework.md stay apart:
//   instrument      OisTrade, SwapTrade, FraTrade: terms only
//   product model   ois_periods, swap_legs: terms to dated periods
//   market data     Curve
//   pricing model   ois_price, swap_price, fra_price
//   valuation       Valuation
// Everything is a pure function of its inputs.
#include <functional>
#include <optional>
#include <string>
#include <vector>

#include "quantforge/core/calendar.hpp"
#include "quantforge/core/dates.hpp"
#include "quantforge/core/daycount.hpp"

namespace quantforge {

// ---- conventions ----

struct RateConvention {
    std::string id, currency;
    Calendar calendar;
    int spot_lag, payment_lag, fixed_months;
    DayCount fixed_day_count;
    int months;  // term index tenor; 0 for overnight
    double denominator;  // floating day-count denominator: 360 or 365
};

/// SONIA, SOFR or USD-TERM-3M; nullptr otherwise.
const RateConvention* rate_convention(std::string_view id);

// ---- schedules ----

struct Period {
    Date start, end, payment;
};

std::vector<Period> generate_schedule(Date start, Date end, long long frequency_months, Calendar c, bool end_of_month,
                                      long long payment_lag);

// ---- curves ----

enum class CurveInterpolation { LogLinearDf, LinearZero };

/// A curve jump (curve-framework.md): multiplies discount factors for dates strictly after `date`.
struct Jump {
    Date date;
    double factor;
};
/// E_INPUT unless dates strictly increase after as_of; E_DOMAIN on a factor <= 0.
void check_jumps(Date as_of, const std::vector<Jump>& jumps);
/// Product of the factors dated strictly before d.
double jump_product(const std::vector<Jump>& jumps, Date d);

struct Pillar {
    Date date;
    double discount_factor;
};

class Curve {
public:
    /// An empty curve, holding only the implied node at as_of.
    Curve(Date as_of, CurveInterpolation interpolation);
    /// Checks pillars: E_INPUT on order, E_DOMAIN on a factor <= 0.
    Curve(Date as_of, CurveInterpolation interpolation, const std::vector<Pillar>& pillars,
          const std::vector<Jump>& jumps = {});
    /// Checks jumps; call before any push. Stored values are then ln(D/J).
    void set_jumps(const std::vector<Jump>& jumps);

    Date as_of() const { return as_of_; }
    CurveInterpolation interpolation() const { return interpolation_; }
    double time(Date d) const { return double(days_between(as_of_, d)) / 365.0; }
    /// Throws E_OUT_OF_RANGE before as_of.
    double discount(Date d) const;

    std::size_t size() const { return dates_.size(); }
    void push(Date d, double log_df);
    void set_log_df(std::size_t pillar, double log_df) { log_df_[pillar + 1] = log_df; }
    double log_df(std::size_t pillar) const { return log_df_[pillar + 1]; }
    std::vector<Pillar> pillars() const;

private:
    Date as_of_;
    CurveInterpolation interpolation_;
    std::vector<Date> dates_;
    std::vector<double> t_, log_df_;  // index 0 is the node at as_of; ln of the jump-free curve
    std::vector<Jump> jumps_;
    double plain_discount(double t) const;
};

double simple_forward(const Curve& c, Date start, Date end, DayCount day_count);

// ---- curve solves ----

enum class SolveMethod { Sequential, Global };

struct SolvedCurve {
    Curve curve;
    double max_repricing_error;
};

using ModelRate = std::function<double(std::size_t, const Curve&)>;

/// Finds pillars at `dates` so that model(j, curve) = targets[j]. Each model(j) may read only dates
/// up to pillar j. Throws E_NO_CONVERGENCE unless every error is below 1e-13.
SolvedCurve solve_curve(Date as_of, CurveInterpolation interpolation, const std::vector<Date>& dates,
                        const std::vector<double>& targets, const ModelRate& model, SolveMethod method,
                        const std::vector<Jump>& jumps = {});

// ---- OIS ----

struct OisQuote {
    Tenor tenor;
    double rate;
};

std::vector<Period> ois_periods(const RateConvention& c, Date as_of, Tenor tenor);

struct Legs {
    double annuity, floating;
    double par() const { return floating / annuity; }
};
Legs ois_legs(const RateConvention& c, const std::vector<Period>& periods, const Curve& curve);
Legs ois_legs(const RateConvention& c, const std::vector<Period>& periods, const std::function<double(Date)>& discount);

SolvedCurve ois_bootstrap(const RateConvention& c, Date as_of, const std::vector<OisQuote>& quotes,
                          CurveInterpolation interpolation, SolveMethod method, const std::vector<Jump>& jumps = {});

/// rates and days must be checked by this call: E_INPUT.
double ois_compound(const std::vector<double>& rates, const std::vector<long long>& days, double denominator);

enum class FixedSide { Pay, Receive };

struct OisTrade {
    const RateConvention* convention;
    Tenor tenor;
    double fixed_rate, notional;
    FixedSide side;
};

struct Valuation {
    double pv;
    std::string currency, model;
    std::optional<std::string> data_version;
    std::string conventions;
    Date as_of;
};

struct OisPrice {
    Valuation valuation;
    double par_rate, annuity;
};
OisPrice ois_price(const OisTrade& trade, const Curve& curve, std::optional<std::string> snapshot_id = {});

// ---- projection ----

enum class ProjectionQuoteType { Deposit, Fra, Swap };

struct ProjectionQuote {
    ProjectionQuoteType type;
    long long months;  // deposit and swap length, or the FRA's start_months
    double rate;
};

Curve projection_bootstrap(const Curve& discount, const RateConvention& index, Date as_of,
                           const std::vector<ProjectionQuote>& quotes, CurveInterpolation interpolation,
                           double* max_repricing_error = nullptr);

struct SwapTrade {
    const RateConvention* index;
    long long tenor_months;
    double fixed_rate, notional;
    FixedSide side;
};

struct SwapPrice {
    Valuation valuation;
    double par_rate;
};
SwapPrice swap_price(const SwapTrade& trade, const Curve& discount, const Curve& projection,
                     std::optional<std::string> snapshot_id = {});

struct FraTrade {
    const RateConvention* index;
    Date start;
    double fixed_rate, notional;
    FixedSide side;
};

struct FraPrice {
    Valuation valuation;
    double forward_rate;
};
FraPrice fra_price(const FraTrade& trade, const Curve& discount, const Curve& projection,
                   std::optional<std::string> snapshot_id = {});

double basis_spread(const Curve& discount, const Curve& projection, const RateConvention& index, long long tenor_months);

// ---- sensitivities ----

struct RateRisk {
    double dv01;
    std::vector<double> key_rate;
};

/// Rebuilt curves for each bump, reusable across trades on the same quotes.
struct BumpedCurves {
    std::vector<Curve> up, down;  // per quote
    std::optional<Curve> all_up, all_down;
};
BumpedCurves bumped_curves(const RateConvention& c, Date as_of, const std::vector<OisQuote>& quotes,
                           CurveInterpolation interpolation);
RateRisk rate_risk(const OisTrade& trade, const BumpedCurves& curves);

struct CashflowRisk {
    double pv, duration, convexity;
};
struct Cashflow {
    double t, amount;
};
CashflowRisk cashflow_risk(const std::vector<Cashflow>& cashflows, double yield);

}  // namespace quantforge
