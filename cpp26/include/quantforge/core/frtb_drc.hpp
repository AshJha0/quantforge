#pragma once
// Stage K wave 2, K-8a: FRTB standardised approach default risk charge (DRC) and residual risk add-on (RRAO)
// (06-risk/frtb-drc-rrao.md, rulings KR-50 to KR-55, KR-67 to KR-69, KR-300 to KR-304, KR-327). A port of
// python/quantforge_core/frtb_drc.py. The parameters come from specifications/tables/stage_k/mar22_drc.json and
// mar23_rrao.json, embedded at build time (#embed, KR-50).
//
// Error order (KR-67 = HR-122): E_SCHEMA in the input layer; E_LIMIT; the finite rule; structural E_INPUT (every
// position checked before any domain rule); E_DOMAIN.
#include <map>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace quantforge::frtb_drc {

inline constexpr const char* label = "regulatory formula on caller inputs; not a regulatory return";  // KR-69
inline constexpr const char* rw_source =
    "securitisation risk weights supplied by the caller (CRE40-CRE44 not implemented)";  // KR-55

/// The parameters of mar22_drc.json and mar23_rrao.json, parsed once (KR-50).
struct Params {
    std::vector<std::string> buckets;     // MAR22.22, output order (KR-302)
    std::vector<std::string> seniorities;  // MAR22.12 order
    std::vector<std::string> ratings;      // MAR22.24 Table 2 order
    std::map<std::string, double> lgd;          // MAR22.12
    std::map<std::string, double> risk_weight;  // MAR22.24 Table 2
    double capital_horizon, maturity_floor, cash_equity_short, ctp_cross_factor;
    std::map<std::string, double> rrao_weight;  // MAR23.8(2)
};
const Params& params();

/// KR-53 offsetting rank: a short of rank r offsets longs of rank r or above. Not in the tables (as in Python).
int rank(const std::string& seniority);
inline constexpr double rw_cap = 12.5;  // frtb-drc-rrao.md Errors: a caller rw above 1250% is E_DOMAIN
inline constexpr long long max_positions = 100000;  // KR-67

/// A non-securitisation position (KR-51); `notional` and `market_value` are signed, long > 0.
struct Position {
    std::string id, obligor, bucket, seniority;
    double notional = 0.0, market_value = 0.0, maturity_years = 0.0;
    bool cash_equity = false, lgd_applies = true;
};

/// A securitisation (non-CTP) position: JTD is the market value (MAR22.27); `rw` from the caller (KR-55).
struct SecPosition {
    std::string id, bucket, pool, tranche;
    double market_value = 0.0, maturity_years = 0.0, rw = 0.0;
};

/// A correlation trading position: netting key (index, series, tranche), bucket = index (MAR22.39).
struct CtpPosition {
    std::string id, index, series, tranche;
    double market_value = 0.0, maturity_years = 0.0, rw = 0.0;
};

struct Instrument {
    std::string id;
    double gross_notional = 0.0;
    std::string kind;
    bool listed_or_clearable = false, back_to_back = false;
};

struct PositionRow {
    std::string id;
    std::optional<double> gross_jtd;  // non-securitisation only
    double weight, scaled_jtd;
};

struct ObligorRow {
    std::string obligor;
    double net_long, net_short, rw;
};

struct BucketRow {
    std::string bucket;
    std::optional<double> hbr;  // not reported for CTP buckets
    double wtd_long, wtd_short, drc;
};

struct NonsecResult {
    std::vector<PositionRow> positions;
    std::vector<ObligorRow> obligors;
    std::vector<BucketRow> buckets;
    double drc;
};

struct SecResult {
    std::vector<PositionRow> positions;
    std::vector<BucketRow> buckets;
    double drc;
};

struct CtpResult {
    bool by_position;  // false: bucket_drc mode, only `drc` is reported
    std::vector<PositionRow> positions;
    std::optional<double> hbr_ctp;
    std::vector<BucketRow> buckets;
    double drc;
};

struct RraoRow {
    std::string id;
    double weight;
    bool excluded;
    double addon;
};

struct RraoResult {
    std::vector<RraoRow> instruments;
    double rrao;
};

/// MAR22.15, MAR22.18, KR-52: 1 at one year or more, else the maturity floored at 0.25.
double maturity_weight(double maturity_years);
/// MAR22.11, MAR22.12: LGD x notional + P&L, floored at 0 for a long and capped at 0 for a short.
double gross_jtd(const Position& p);
/// KR-53 greedy offsetting within one obligor over (rank, scaled JTD) pairs in input order (longs > 0, shorts < 0).
/// Returns (net long >= 0, net short <= 0).
std::pair<double, double> offset(const std::vector<std::pair<int, double>>& longs,
                                 const std::vector<std::pair<int, double>>& shorts);
/// MAR22.45: max(sum_b (max(DRC_b, 0) + 0.5 min(DRC_b, 0)), 0).
double ctp_total(const std::vector<double>& bucket_drc);

NonsecResult drc_nonsec(const std::vector<Position>& positions, const std::map<std::string, std::string>& ratings);
SecResult drc_sec_nonctp(const std::vector<SecPosition>& positions);
/// Exactly one of `positions` and `bucket_drc` (index-level DRC_b).
CtpResult drc_ctp(const std::optional<std::vector<CtpPosition>>& positions,
                  const std::optional<std::vector<double>>& bucket_drc);
RraoResult rrao(const std::vector<Instrument>& instruments);

}  // namespace quantforge::frtb_drc
