#pragma once
// Stage K wave 1b, K-8d: SA-CCR exposure at default of a derivatives netting set (06-risk/sa-ccr.md, rulings KR-30
// to KR-39). A port of python/quantforge_core/saccr.py. The supervisory parameters come from
// specifications/06-risk/sa-ccr-parameters.json, embedded at build time (#embed).
#include <array>
#include <cstddef>
#include <optional>
#include <string>
#include <vector>

namespace quantforge::saccr {

/// The asset classes and treatments, in output order (CRE52.26, CRE52.46, CRE52.47).
inline constexpr std::array<const char*, 5> classes = {"IR", "FX", "CREDIT", "EQUITY", "COMMODITY"};
inline constexpr std::array<const char*, 3> treatments = {"NORMAL", "BASIS", "VOLATILITY"};

/// One CRE52.72 Table 2 row; subclass "" for IR and FX.
struct Row {
    std::string asset_class, subclass;
    double factor = 0.0;
    std::optional<double> correlation;
    double option_volatility = 0.0;
    std::optional<std::string> hedging_set;
};

struct Params {
    double alpha, floor;
    long long year_days, min_days;
    double sd_rate, rho12, rho23, rho13, bucket1_below, bucket2_up_to, margined_mf_scale;
    long long mpor_daily, mpor_non_daily_base, mpor_large, mpor_large_trades_above, mpor_dispute_multiplier;
    std::array<double, 3> scale;
    double cdo_numerator, cdo_slope;
    std::vector<Row> table2;
};

/// The parsed parameter file, built once.
const Params& params();

/// One trade. Enum-valued fields hold the contract's strings, checked by the input layer (E_SCHEMA, KR-39).
struct Trade {
    std::string id, asset_class;
    double notional = 0.0, market_value = 0.0, maturity = 0.0;
    std::string kind = "LINEAR", position = "LONG", treatment = "NORMAL";
    std::optional<double> start, end;
    std::optional<std::string> hedging_set, entity, subclass, option_type;
    std::optional<double> underlying_price, strike, exercise;
    double shift = 0.0;
    std::optional<double> attachment, detachment;
};

struct Margin {
    double threshold = 0.0, mta = 0.0, nica = 0.0;
    long long remargin_days = 1;
    std::optional<long long> mpor_days;
    bool illiquid = false, disputes = false;
};

struct TradeRow {
    std::string id;
    std::optional<double> supervisory_duration;
    double adjusted_notional, maturity_factor, delta, effective_notional, supervisory_factor;
};

struct HedgingSet {
    std::string asset_class, treatment, key;
    double addon;
};

struct Result {
    double ead, rc, pfe, multiplier, addon_aggregate;
    std::array<double, 5> addon;  // in classes order
    double v, c;
    bool margined;
    std::optional<long long> mpor_days;
    std::optional<double> ead_unmargined;
    bool capped;
    std::vector<HedgingSet> hedging_sets;
    std::vector<TradeRow> trades;
};

/// EAD of one netting set (CRE52.1); no margin means unmargined. Order: the finite rule, structure (E_INPUT), then
/// domain (E_DOMAIN), as HR-122.
Result ead(const std::vector<Trade>& trades, double collateral, const std::optional<Margin>& margin, bool ir_offset);

/// CRE52.34, floored at ten business days.
double supervisory_duration(double start, double end);
/// CRE52.50 and CRE52.51 floors in business days (KR-35).
long long mpor_floor(const Margin& m, std::size_t trade_count);
/// CRE52.39 to CRE52.41; the trade must have passed the structural checks.
double supervisory_delta(const Trade& t);
/// CRE52.23 with the KR-36 edges: exactly 1 when V - C >= 0 (no exponential), the floor for a zero add-on.
double multiplier(double v_minus_c, double addon);
/// CRE52.57 step 3 on the end date; 1 and 5 years fall in bucket 2 (KR-32).
int bucket(double end);

}  // namespace quantforge::saccr
