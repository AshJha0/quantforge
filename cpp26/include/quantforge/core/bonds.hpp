#pragma once
// Stage D wave 2, D2: fixed-coupon bonds, FRNs, repo, Treasury futures and a Nelson-Siegel bond fit
// (04-pricing/bonds.md). Face 100, unadjusted coupon dates, regular periods only (ruling D13).
#include <optional>
#include <vector>

#include "quantforge/core/rates.hpp"

namespace quantforge {

struct Bond {
    Date maturity;
    double coupon;
    int frequency;  // 1, 2 or 4
};

/// Coupon dates of `b` stepping back from maturity, ascending, all > `after` plus the one at or before it first.
struct BondPeriod {
    Date prev, next;
    std::vector<Date> flows;  // coupon dates after settlement, ascending; the last is maturity
};
/// E_DATE_ORDER when settlement >= maturity.
BondPeriod bond_period(const Bond& b, Date settlement);
/// Dates stepping back from `maturity` every `months`, same end-of-month rule; ascending, from the last
/// date at or before `from` up to maturity.
std::vector<Date> roll_back(Date maturity, int months, Date from, bool month_end_rule = true);
double coupon_amount(const Bond& b);
double accrued(const Bond& b, Date settlement);

struct YieldPrice {
    double dirty, accrued, clean, modified_duration, macaulay_duration, convexity;
};
YieldPrice price_from_yield(const Bond& b, Date settlement, double yield);
double yield_from_price(const Bond& b, Date settlement, double clean_price);

/// Dirty price on curve with continuous spread z, carried to settlement. E_OUT_OF_RANGE before as_of.
double curve_dirty(const Bond& b, Date settlement, const Curve& curve, double z);
double z_spread(const Bond& b, Date settlement, const Curve& curve, double clean_price);

struct AssetSwap {
    double spread, annuity;
};
AssetSwap asset_swap(const Bond& b, Date settlement, const Curve& curve, double dirty_price);

struct Frn {
    Date maturity;
    int frequency;
    double current_rate, margin, discount_margin;
};
struct FrnPrice {
    double dirty, accrued, clean;
};
FrnPrice frn_price(const Frn& n, Date settlement, const Curve& discount, const Curve& projection);

struct RepoForward {
    double dirty, forward_dirty, forward_clean, interest;
    std::optional<double> special_spread, specialness_value;
};
RepoForward repo_forward(const Bond& b, Date start, Date end, double clean_price, double repo_rate,
                         std::optional<double> gc_rate);
double repo_implied_rate(const Bond& b, Date start, Date end, double clean_price, double forward_clean);

/// delivery = first day of the delivery month.
enum class FuturesContract { TwoYear, ThreeYear, FiveYear, TenYear, UltraTenYear, Bond, UltraBond };
double conversion_factor(const Bond& b, Date delivery, double notional_coupon,
                         FuturesContract contract = FuturesContract::TenYear);

struct BasisBond {
    Bond bond;
    double clean_price, conversion_factor;
};
struct BasisRow {
    double invoice, gross_basis, net_basis, implied_repo;
};
struct Basis {
    std::vector<BasisRow> bonds;
    std::size_t ctd;
};
Basis futures_basis(double futures_price, Date settlement, Date delivery, double repo_rate, const std::vector<BasisBond>& bonds);

struct NsBond {
    Bond bond;
    double dirty_price;
};
struct NsFit {
    std::vector<double> betas, residuals;
};
NsFit bond_nelson_siegel(Date settlement, double tau, const std::vector<NsBond>& bonds,
                         const std::optional<std::vector<double>>& weights);

}  // namespace quantforge
