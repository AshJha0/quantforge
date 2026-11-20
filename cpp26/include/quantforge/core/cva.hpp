#pragma once
// Stage K wave 2b, K-8g: CVA risk capital, BA-CVA reduced and full (MAR50.14 to MAR50.26) and SA-CVA (MAR50.41 to
// MAR50.77). A port of python/quantforge_core/cva.py (specifications/06-risk/cva-capital.md, rulings KR-62 to KR-64
// and KR-311 to KR-318). Every parameter comes from specifications/tables/stage_k/mar50_cva.json, embedded at
// build time (#embed, ruling KR-50).
//
// Error order (KR-67): the input layer raises E_SCHEMA for unlisted enums and factor names; the functions here raise
// every structural E_INPUT of the whole input before any E_DOMAIN.
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace quantforge::cva {

inline constexpr const char* label = "regulatory formula on caller inputs; not a regulatory return";  // KR-69

/// The listed values, in table order (the input layer refuses anything else as E_SCHEMA).
const std::vector<std::string>& sectors();
const std::vector<std::string>& qualities();       // IG, HY_NR (MAR50.16 Table 1 columns)
const std::vector<std::string>& versions();        // REDUCED, FULL
const std::vector<std::string>& relations();       // DIRECT, LEGAL, SECTOR_REGION (KR-64)
const std::vector<std::string>& ccs_tenors();      // MAR50.65(1)
const std::vector<std::string>& ir_delta_factors();  // the specified tenors, inflation, CURVE (KR-311)
const std::vector<std::string>& ir_vega_factors();   // IR_VOL, INFLATION_VOL (KR-311)
/// Every `class.kind` key the input layer reads, CCS.VEGA included (refused later as E_INPUT).
const std::vector<std::string>& class_keys();

/// Python's built-in sum of floats (3.12 and later): Neumaier-compensated, the compensation added at the end.
double py_sum(const std::vector<double>& v);

// --- BA-CVA ---------------------------------------------------------------------------------------------------

struct NettingSet {
    double ead = 0.0, m = 0.0;
    bool imm = false;
};

struct Counterparty {
    std::string id, sector, quality;
    std::vector<NettingSet> netting_sets;
};

struct SingleNameHedge {
    std::string counterparty, relation, sector, quality;
    double m = 0.0, notional = 0.0;
};

struct Constituent {
    std::string sector, quality;
    double weight = 0.0;
};

struct IndexHedge {
    double m = 0.0, notional = 0.0;
    std::vector<Constituent> constituents;
};

struct CounterpartyRow {
    std::string id;
    double scva = 0.0;
    std::optional<double> snh, hma;  // FULL only
    std::vector<double> dfs;         // one per netting set
};

struct BaResult {
    std::string version;
    std::vector<CounterpartyRow> counterparties;
    std::optional<double> ih, k_hedged, k_full;  // FULL only
    double k_reduced = 0.0, capital = 0.0, rwa = 0.0;
};

/// MAR50.15(4), KR-64: 1 for IMM, else -expm1(-0.05 M) / (0.05 M). M must be above 0 (E_DOMAIN).
double discount_factor(double m, bool imm = false);

BaResult ba_cva(const std::vector<Counterparty>& counterparties, const std::string& version,
                const std::vector<SingleNameHedge>& single_name_hedges, const std::vector<IndexHedge>& index_hedges);

// --- SA-CVA ---------------------------------------------------------------------------------------------------

/// A counterparty credit spread factor (KR-63).
struct CreditFactor {
    std::string name, tenor, quality;
    std::optional<std::string> legal_group, index, series;
};

/// One sensitivity: `factor` is the factor name outside CCS, `credit` the CCS factor.
struct Sensitivity {
    std::string bucket, factor;
    std::optional<CreditFactor> credit;
    double s_cva = 0.0, s_hdg = 0.0;
};

struct BucketRow {
    std::string bucket;
    double k_b = 0.0, s_b = 0.0, sum_ws = 0.0;
    bool floored = false;
};

struct ClassResult {
    std::string key;
    std::vector<BucketRow> buckets;
    double k = 0.0;
};

struct SaResult {
    std::vector<ClassResult> classes;  // in the order IR.DELTA, IR.VEGA, FX.DELTA, ... COM.VEGA
    double m_cva = 1.0, total = 0.0, rwa = 0.0;
};

/// `classes` holds (`IR.DELTA` ..., sensitivities) in input order; each key at most once and listed.
SaResult sa_cva(const std::vector<std::pair<std::string, std::vector<Sensitivity>>>& classes,
                const std::string& reporting_currency, double m_cva = 1.0);

}  // namespace quantforge::cva
