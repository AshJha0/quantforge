#pragma once
// Equity carry: dividend, borrow and financing curves; index dividends, rebalancing, corporate actions and
// TRS (02-curves/equity-curves.md, 04-pricing/equity-index.md). Carry C = D exp(b t) exp(-s t) (ruling C2, D22).
#include <optional>
#include <string>
#include <vector>

#include "quantforge/core/rates.hpp"

namespace quantforge {

struct CashDividend {
    Date ex_date;
    double amount;
};

struct EquityCarry {
    const Curve& funding;
    double borrow, spread;
    double carry(Date d) const;
    /// F(T) = [S - sum_{as_of < t_i <= T} div_i C(t_i)] / C(T).
    double forward(double spot, const std::vector<CashDividend>& dividends, Date expiry) const;
};

struct FuturesQuote {
    Date expiry;
    double price;
};
struct ImpliedDividends {
    std::vector<double> pv_dividends, period_pv_dividends, dividend_yields;
};
ImpliedDividends implied_dividends(double spot, const Curve& funding, double borrow, const std::vector<FuturesQuote>& futures);

/// E_NOT_BRACKETED with no solution in [-0.5, 0.5].
double implied_borrow(double spot, const Curve& funding, const std::vector<CashDividend>& dividends, Date expiry, double forward);

struct FuturesBasis {
    double fair_price, basis, implied_financing_spread;
};
FuturesBasis equity_futures_basis(double spot, const Curve& funding, double borrow, double spread,
                                  const std::vector<CashDividend>& dividends, Date expiry, double futures_price);

struct Constituent {
    std::string id;
    double shares, price;
    std::vector<CashDividend> dividends;
};
struct Period2 {
    Date start, end;
};
struct IndexDividends {
    double level;
    std::vector<Date> ex_dates;
    std::vector<double> points, period_points, basis;
};
IndexDividends index_dividends(double divisor, const std::vector<Constituent>& constituents, const std::vector<Period2>& periods,
                               const std::vector<double>& implied_period_points);

struct Rebalance {
    double level, new_divisor;
    std::vector<double> weights;
};
Rebalance index_rebalance(double divisor, const std::vector<Constituent>& old_list, const std::vector<Constituent>& new_list);

enum class CorporateAction { Split, ReverseSplit, Rights, SpecialDividend };
struct ActionResult {
    double factor, ex_price, adjusted_shares, adjusted_strike;
};
/// a = ratio, new_per_old or amount; k = subscription_price (rights only).
ActionResult corporate_action(CorporateAction action, double cum_price, double shares, double strike, double a, double k);

struct TrsTrade {
    Date start, end;
    double initial_price, shares, spread, sign;  // +1 RECEIVE_EQUITY
};
struct TrsPrice {
    double equity_leg, funding_leg, pv;
};
TrsPrice trs_price(double spot, const Curve& funding, double borrow, const std::vector<CashDividend>& dividends,
                   const TrsTrade& trade, std::optional<double> current_rate);

}  // namespace quantforge
