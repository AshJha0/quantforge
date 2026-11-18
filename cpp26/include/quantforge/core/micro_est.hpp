#pragma once
// Stage H H-4b microstructure estimators with planted truth (specifications/09-microstructure/micro-estimators.md)
// and H-16 venue analytics (specifications/10-execution/venue-analytics.md); rulings HR-70 to HR-75 as amended
// (HR-66). Ports of the Python build's micro_est.py and venue_analytics.py, matching the Java build: sums are
// correctly rounded (math.fsum); venue sums are exact on the decimals the inputs print as, with one correctly
// rounded division per output. Error order: structural E_INPUT, then E_DOMAIN, then value-dependent E_INPUT. The
// CLI raises a non-finite input (F-2) before any of these.
#include <map>
#include <string>
#include <string_view>
#include <vector>

namespace quantforge::micro_est {

struct Estimate {
    double value, se;
};

struct Order {
    double lifetime;
    bool cancelled;  // else filled
};

struct Sample {
    std::vector<double> x, y;
};

/// Code-point order on UTF-8 strings (Python's str order): byte order.
struct CodePointLess {
    bool operator()(std::string_view a, std::string_view b) const;
};

struct RegimeImpact {
    std::vector<std::pair<std::string, Estimate>> regimes;  // code-point order
    double ratio;
};

/// OLS through the origin: beta = sum xy / sum x^2, SE = sqrt(SSR / (n - 1) / sum x^2).
Estimate ols_origin(const std::vector<double>& x, const std::vector<double>& y, const std::string& field);
Estimate arrival_rate(long long count, double window);
Estimate cancel_rate(const std::vector<Order>& orders);
/// points are (t, S).
Estimate resilience(double s_inf, const std::vector<std::pair<double, double>>& points);
/// levels are (k, depth).
Estimate liquidity_decay(const std::vector<std::pair<double, double>>& levels);
Estimate adverse_selection(const std::vector<double>& x, const std::vector<double>& y);
RegimeImpact regime_impact(const std::map<std::string, Sample, CodePointLess>& regimes);
Estimate passive_vs_aggressive(const std::vector<double>& passive, const std::vector<double>& aggressive);

namespace venue {

struct Fill {
    std::string venue;
    bool buy;
    double quantity, price, t;
};

struct Order {
    std::string venue;
    double sent, filled;
};

struct Markout {
    std::string venue;
    double h, markout, markout_bps, toxicity;
};

struct Result {
    std::vector<std::pair<std::string, double>> fill_rates;  // code-point order
    std::vector<Markout> markouts;
};

/// mids rows are (t, mid). The mid at u is the last mid stamped at or before u (HR-72).
Result analytics(const std::vector<std::pair<double, double>>& mids, const std::vector<Fill>& fills,
                 const std::vector<Order>& orders, const std::vector<double>& horizons);

/// Exposed for the unit tests: (a * 10^ea) / (b * 10^eb) for decimal strings of the integer mantissas, correctly
/// rounded to binary64, and the shortest round-trip decimal of a double as text.
double exact_ratio(const std::string& a, const std::string& b);

}  // namespace venue

}  // namespace quantforge::micro_est
