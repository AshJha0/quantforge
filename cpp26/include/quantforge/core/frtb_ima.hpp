#pragma once
// Stage K wave 2, K-8f: FRTB internal models approach pieces: PLA test, liquidity horizons, ES with the
// liquidity-horizon cascade, stressed ES, IMCC, NMRF stress scenario aggregation (SES), the risk factor eligibility
// test (RFET) and the capital aggregation (06-risk/frtb-ima.md, rulings KR-50, KR-56 to KR-61, KR-67 to KR-69,
// KR-305 to KR-310). A port of python/quantforge_core/frtb_ima.py. Parameters come from
// specifications/tables/stage_k/mar31_rfet.json, mar32_pla.json and mar33_ima.json, embedded at build time (#embed).
#include <array>
#include <map>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "quantforge/core/dates.hpp"

namespace quantforge::frtb_ima {

inline constexpr const char* label = "regulatory formula on caller inputs; not a regulatory return";  // KR-69
inline constexpr long long max_pnl = 1000000;  // KR-67: P&L points per list
inline constexpr long long max_list = 100000;  // KR-67: everything else
inline constexpr long long pla_min_n = 3;      // KR-56

/// The parameters of the three tables, parsed once (KR-50).
struct Params {
    double pla_green_spearman, pla_red_spearman;
    long long pla_green_ks_percent, pla_red_ks_percent;  // whole percentages: green needs 100 d < 9 n
    long long pla_window;
    double es_confidence;
    long long base_horizon;
    std::array<long long, 5> horizons;                 // MAR33.4 Table 1
    std::vector<std::pair<std::string, long long>> lh_table;  // MAR33.12 Table 2, table order
    std::vector<std::string> specified_fx_pairs;       // footnote 309
    double imcc_rho, ses_rho;
    std::vector<double> multiplier;  // MAR32.9 Table 1, by exceptions 0..9
    double multiplier_red;           // 10 or more (KR-61)
    long long rfet_min_days, rfet_window_days, rfet_min_per_window, rfet_alt_min_days, rfet_lookback_months;
    std::map<std::string, std::vector<double>> rfet_lower;  // MAR31.16 Table 1 lower bounds per row
    double rfet_d_upper;
};
const Params& params();

inline constexpr double surcharge_factor = 0.5;  // MAR33.45 formula text
inline constexpr std::array<const char*, 5> imcc_classes = {"IR", "EQ", "FX", "COM", "CS"};  // output order

// ---- PLA ----
/// Twice the average ranks (ties share the mean of their positions), so every value is an integer.
std::vector<long long> doubled_ranks(const std::vector<double>& x);
double spearman(const std::vector<double>& hpl, const std::vector<double>& rtpl);
long long ks_count(const std::vector<double>& hpl, const std::vector<double>& rtpl);
/// Q_KS(x) = 2 sum_{k>=1} (-1)^(k-1) exp(-2 k^2 x^2), with the theta series below 1 (KR-305).
double kolmogorov_q(double x);

struct Pla {
    long long n;
    double spearman, ks;
    long long ks_count;
    std::string zone;
    double ks_pvalue_asymptotic;
    bool regulatory_window;
};
Pla pla(const std::vector<double>& hpl, const std::vector<double>& rtpl);
double pla_ks_pvalue(double ks, long long n);

// ---- liquidity horizons ----
bool fx_pair_specified(const std::string& pair);
struct Lh {
    long long n, table_n;
    std::string rule;
};
Lh liquidity_horizon(const std::optional<std::string>& category, const std::optional<std::string>& fx_pair,
                     const std::optional<std::vector<std::pair<double, long long>>>& constituents,
                     std::optional<double> maturity_days);

// ---- ES, stressed ES, IMCC, SES ----
double normal_es_factor();
double es_cascade(const std::vector<double>& es_by_horizon);
struct EsLh {
    std::string mode;
    std::vector<double> es_by_horizon;
    double es;
};
EsLh es_lh(const std::optional<std::vector<double>>& es_t, const std::optional<std::vector<double>>& sigma,
           const std::optional<std::vector<std::vector<double>>>& pnl);

struct Triple {
    double es_rs, es_fc, es_rc;
};
struct Stressed {
    double ratio;
    bool ratio_floored;
    double es;
};
Stressed es_stressed(const Triple& t);

struct Imcc {
    double imcc_c;
    bool portfolio_floored;
    std::vector<std::pair<std::string, double>> classes;  // IR, EQ, FX, COM, CS order
    std::vector<std::string> classes_floored;
    double imcc;
};
Imcc imcc(const Triple& portfolio, const std::map<std::string, Triple>& classes);

struct Ses {
    double idio_credit, idio_equity, other, ses;
};
Ses ses(const std::vector<double>& idio_credit, const std::vector<double>& idio_equity, const std::vector<double>& other);

// ---- capital ----
double multiplier(long long exceptions);
struct CapitalInput {
    double imcc_prev, ses_prev, imcc_avg, ses_avg;
    long long exceptions;
    double drc;
    std::vector<std::pair<std::string, double>> desks;  // (zone GREEN or AMBER, sa)
    double c_u, sa_all, qualitative_addon = 0.0;
};
struct Capital {
    double m_c, c_a, ima_ga, sa_ga, k, surcharge, acr_total;
};
Capital capital(const CapitalInput& in);

// ---- RFET ----
/// Calendar months back, the day clamped to the end of the target month (KR-59).
Date months_back(Date d, int months);
struct Rfet {
    Date window_start;
    long long distinct_days;
    std::optional<long long> min_window_count;
    std::optional<Date> first_failing_window_start;
    std::optional<long long> first_failing_window_count;
    bool crit1, crit2, pass;
};
Rfet rfet(Date as_of, const std::vector<Date>& observations);

struct RfetBucket {
    long long bucket;
    double lower;
    std::optional<double> upper;
};
RfetBucket rfet_bucket(const std::string& row, std::optional<double> t, std::optional<double> delta);

}  // namespace quantforge::frtb_ima
