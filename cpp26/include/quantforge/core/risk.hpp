#pragma once
// Par and key-rate risk by bump and revalue (06-risk/par-and-key-rate.md). Every result is money per bp.
#include <functional>
#include <vector>

#include "quantforge/core/rates.hpp"

namespace quantforge {

enum class BumpScheme { Central, Forward };
enum class KeyRateMode { Triangular, Pillar };

/// Values a product on a curve.
using CurvePricer = std::function<double(const Curve&)>;

/// E_DOMAIN unless 0 < bump_bp <= 100.
void check_bump(double bump_bp);

struct ParRisk {
    double value, par_dv01;
    std::vector<double> buckets;
};
/// Bumps the OIS quotes and rebuilds the curve with a sequential solve.
ParRisk par_risk(const RateConvention& c, Date as_of, const std::vector<OisQuote>& quotes,
                 CurveInterpolation interpolation, const CurvePricer& price, double bump_bp, BumpScheme scheme);

struct KeyRateRisk {
    double value, zero_dv01;
    std::vector<double> buckets;
};
/// E_INPUT unless key_dates (TRIANGULAR only) strictly increase after as_of, at least one.
void check_key_dates(const Curve& curve, const std::vector<Date>& key_dates);
KeyRateRisk key_rate_risk(const Curve& curve, KeyRateMode mode, const std::vector<Date>& key_dates,
                          const CurvePricer& price, double bump_bp, BumpScheme scheme);
/// The triangular weight of key i at curve time t (key times strictly increasing).
double triangular_weight(const std::vector<double>& key_times, std::size_t i, double t);

struct PnlExplain {
    double value_start, value_end, full_pnl, risk_pnl, gross_risk_pnl, unexplained, threshold;
    std::vector<double> par_buckets;
    bool explained;
};
/// E_INPUT unless both quote sets have the same tenors in the same order. `notional` sets the numerical floor.
PnlExplain pnl_explain(const RateConvention& c, Date as_of, const std::vector<OisQuote>& start,
                       const std::vector<OisQuote>& end, CurveInterpolation interpolation, const CurvePricer& price,
                       double bump_bp, double notional);

struct ZeroJacobian {
    std::vector<Date> pillar_dates;
    std::vector<double> zero_rates;
    std::vector<std::vector<double>> jacobian;  // rows: pillars, columns: quotes
};
ZeroJacobian zero_jacobian(const RateConvention& c, Date as_of, const std::vector<OisQuote>& quotes,
                           CurveInterpolation interpolation, double bump_bp);

}  // namespace quantforge
