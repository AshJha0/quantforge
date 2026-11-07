#pragma once
// Equity spot, dividends and forward: 02-curves/equity-forward.md.
#include <optional>
#include <vector>

#include "quantforge/core/rates.hpp"

namespace quantforge {

struct Dividend {
    Date ex_date;
    double amount;
};
struct TimedDividend {
    double time_years, amount;
};
struct EquityForward {
    double forward, discount_factor, carry_factor, pv_dividends;
};
/// `borrow` may be null for B = 1. The caller has already checked spot, which comes before the curves' own checks.
EquityForward equity_forward(double spot, Date as_of, Date expiry, const Curve& funding, const Curve* borrow,
                             const std::vector<Dividend>& dividends);
double equity_forward_flat(double spot, double rate, double borrow, double expiry_years,
                           const std::vector<TimedDividend>& dividends);

struct ParityQuote {
    double strike, call_bid, call_ask, put_bid, put_ask;
};
struct ParityForward {
    double forward, discount_factor, max_residual;
    std::vector<double> outside_spread;
};
ParityForward parity_forward(const std::vector<ParityQuote>& quotes, std::optional<double> discount_factor);

}  // namespace quantforge
