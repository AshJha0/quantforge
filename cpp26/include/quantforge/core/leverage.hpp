#pragma once
// Stage K wave 2b, K-8i: leverage ratio (LEV20, LEV30) and large exposures (LEX10, LEX20, LEX30), simplified as the
// spec's Limits section states. A port of python/quantforge_core/leverage.py
// (specifications/06-risk/leverage-large-exposures.md, rulings KR-65, KR-66 and KR-319 to KR-326). Parameters come
// from specifications/tables/stage_k/lev_leverage.json and lex_large_exposures.json, embedded at build time (#embed).
//
// Error order (KR-67): enums are E_SCHEMA in the input layer; here every structural E_INPUT comes before E_DOMAIN.
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace quantforge::leverage {

inline constexpr const char* leverage_label = "simplified leverage ratio (LEV30 subset); not a regulatory return";
inline constexpr const char* large_exposures_label =
    "simplified large exposures (LEX subset); not a regulatory return";

/// The input names of the LEV30.49-30.54 CCF categories (KR-65) and the KR-53 seniorities.
const std::vector<std::string>& ccf_categories();
const std::vector<std::string>& seniorities();

// --- leverage ratio ---

struct DerivativeSet {
    double v = 0.0, pfe = 0.0, cvm_received = 0.0, cvm_provided = 0.0;
};

struct WrittenCreditDerivative {
    double notional = 0.0, fair_value = 0.0, purchased_offset = 0.0;
};

struct Sft {
    double gross_assets = 0.0;
    bool mna = false;
    std::vector<double> exposures, collateral;
};

struct OffBalance {
    double notional = 0.0;
    std::string ccf_category;
};

struct LeverageResult {
    double on_balance = 0.0, derivatives = 0.0, derivative_netting_sets = 0.0, written_credit_derivatives = 0.0;
    double sfts = 0.0, off_balance = 0.0, exposure = 0.0, ratio = 0.0;
    bool meets_minimum = false;
};

/// LEV30.14-30.16: alpha (max(V - CVM received + CVM provided, 0) + PFE).
double derivative_exposure(const DerivativeSet& d);
/// LEV30.31, footnote 384: notional reduced by a negative fair value, then by purchased protection, floored at 0.
double written_cd_effective_notional(const WrittenCreditDerivative& w);
/// LEV30.37: gross assets plus the counterparty measure, netted only under an MNA.
double sft_exposure(const Sft& s);

LeverageResult leverage(double tier1, const std::vector<double>& on_balance, const std::vector<DerivativeSet>& derivatives,
                        const std::vector<WrittenCreditDerivative>& written_credit_derivatives,
                        const std::vector<Sft>& sfts, const std::vector<OffBalance>& off_balance);

// --- large exposures ---

struct LeCounterparty {
    std::string id;
    std::optional<std::string> group;
    bool gsib = false, exempt = false;
};

struct BankingBookExposure {
    std::string counterparty;
    double value = 0.0;
};

struct OffBalanceExposure {
    std::string counterparty;
    double notional = 0.0, ccf = 0.0;
};

struct Protection {
    std::string counterparty, provider;
    double protected_amount = 0.0;
};

/// A trading book position (KR-51 with a counterparty, KR-66); maturity, cash equity and LGD are read and ignored.
struct TradingPosition {
    std::string id, counterparty, seniority;
    double notional = 0.0, market_value = 0.0;
};

struct CounterpartyRow {
    std::string id;
    double banking_book = 0.0, off_balance = 0.0, trading_book_net_long = 0.0, trading_book_net_short = 0.0;
    double protected_amount = 0.0, received = 0.0, exposure = 0.0;
};

struct GroupRow {
    std::string group;
    std::vector<std::string> members;
    double exposure = 0.0, share = 0.0, limit = 0.0;
    bool large = false, breach = false, exempt = false;
};

struct LargeExposuresResult {
    std::vector<CounterpartyRow> counterparties;
    std::vector<GroupRow> groups;
    std::vector<std::string> report;
};

/// KR-53 for one obligor: (rank, signed JTD) pairs to (net long, net short).
std::pair<double, double> offset_by_seniority(const std::vector<std::pair<int, double>>& positions);
/// LEX30.17: the market value kept on the side of the position (notional >= 0 is long, KR-323).
double jtd(const TradingPosition& p);

LargeExposuresResult large_exposures(double tier1, const std::vector<LeCounterparty>& counterparties,
                                     const std::vector<BankingBookExposure>& banking_book,
                                     const std::vector<OffBalanceExposure>& off_balance,
                                     const std::vector<Protection>& crm,
                                     const std::vector<TradingPosition>& trading_book, bool bank_gsib);

}  // namespace quantforge::leverage
