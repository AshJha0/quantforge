#pragma once
// Stage F (F5): the trade and position lifecycle with weighted average cost, end-of-day marks with source
// fallback and price verification (07-portfolio/book-lifecycle.md, ruling F-34), and use case 4, factor
// attribution (04-pricing/use-cases.md).
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "quantforge/core/dates.hpp"
#include "quantforge/core/linalg.hpp"

namespace quantforge {

struct BookPosition {
    std::string instrument;
    double quantity = 0.0;
    double average_cost = 0.0;
};

enum class BookEventType { Trade, Fixing, Expiry, Default, Roll };

/// One lifecycle event. TRADE: instrument, quantity, price. FIXING: instrument holds the index, price the
/// value. EXPIRY and DEFAULT: instrument, price (settlement or recovery). ROLL: instrument (from), to,
/// price (from_price), to_price.
struct BookEvent {
    Date date{};
    BookEventType type = BookEventType::Trade;
    std::string instrument;
    std::string to;
    double quantity = 0.0;
    double price = 0.0;
    double to_price = 0.0;
};

struct BookFixing {
    std::string index;
    Date date{};
    double value = 0.0;
};

struct BookResult {
    std::vector<BookPosition> positions;                    // instrument order
    std::vector<std::pair<std::string, double>> realized;  // instrument order
    double total_realized = 0.0;
    std::vector<BookFixing> fixings;  // index, then date
};

/// E_INPUT on events out of date order, a duplicate fixing, a duplicate opening instrument, an
/// EXPIRY/DEFAULT/ROLL on an instrument not held, or a TRADE/ROLL into a closed instrument; E_DOMAIN on a
/// zero trade quantity or a non-finite number.
BookResult apply_lifecycle(const std::vector<BookPosition>& positions, const std::vector<BookEvent>& events);

struct MarkQuote {
    std::string instrument;
    Date date{};
    double price = 0.0;
};

struct MarkSource {
    std::string name;
    std::vector<MarkQuote> quotes;
};

enum class MarkStatus { Primary, Fallback, Stale, Missing };

struct Mark {
    std::string instrument;
    std::optional<double> price;
    std::optional<std::string> source;
    MarkStatus status = MarkStatus::Missing;
    std::optional<int> age_days;
    std::optional<double> ipv_diff;
    bool ipv_breach = false;
};

/// E_INPUT on duplicate source names; E_DOMAIN on max_age_days < 0, an IPV price <= 0 or a non-finite number.
std::vector<Mark> resolve_marks(Date as_of, const std::vector<std::string>& instruments,
                                const std::vector<MarkSource>& sources, long long max_age_days,
                                const std::vector<std::pair<std::string, double>>& ipv, double ipv_threshold);

struct FactorAttribution {
    double alpha = 0.0;
    std::vector<double> betas;
    double r_squared = 0.0;
    std::vector<double> contributions;
    double mean_return = 0.0;
    double residual_vol = 0.0;
    std::vector<double> beta_se;
};

/// OLS with an intercept. factor_returns is T rows of K. E_INPUT when names and columns differ, a row has
/// the wrong length or T < K + 2; E_DOMAIN when the factors are collinear or a number is non-finite.
FactorAttribution factor_attribution(const std::vector<double>& portfolio_returns, const Matrix& factor_returns,
                                     std::size_t factor_names);

}  // namespace quantforge
