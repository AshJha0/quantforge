#include "quantforge/core/leverage.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <map>
#include <set>
#include <string_view>

#include "quantforge/core/error.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/research.hpp"

namespace quantforge::leverage {
namespace {

#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wc23-extensions"
#endif
constexpr unsigned char lev_bytes[] = {
#embed "../../../specifications/tables/stage_k/lev_leverage.json"
};
constexpr unsigned char lex_bytes[] = {
#embed "../../../specifications/tables/stage_k/lex_large_exposures.json"
};
#if defined(__clang__)
#pragma clang diagnostic pop
#endif

using json::Kind;
using json::Value;
using std::string;
using std::string_view;
using Table = std::map<string, Value, std::less<>>;

Table load(const unsigned char* bytes, std::size_t size) {
    const json::Parsed p = json::parse(string_view(reinterpret_cast<const char*>(bytes), size));
    Table m;
    for (const Value& e : p.value.find("entries")->items) m.emplace(e.find("key")->text, *e.find("value"));
    return m;
}

const Table& lev() {
    static const Table t = load(lev_bytes, sizeof lev_bytes);
    return t;
}

const Table& lex() {
    static const Table t = load(lex_bytes, sizeof lex_bytes);
    return t;
}

// A decimal string (HR-12) or a JSON number.
double dec(const Value& v) {
    if (v.kind == Kind::Number) return v.number;
    double x = 0.0;
    std::from_chars(v.text.data(), v.text.data() + v.text.size(), x);
    return x;
}

double num(const Table& t, string_view key) { return dec(t.find(key)->second); }

// LEV30.49-30.54: input category (KR-65) to the table key.
const char* ccf_key(const string& category) {
    if (category == "NIF_RUF") return "nif_ruf";
    if (category == "TRANSACTION_CONTINGENT") return "transaction_related_contingent";
    if (category == "COMMITMENT") return "commitments";
    if (category == "TRADE_LC") return "short_term_trade_lc";
    if (category == "UNCONDITIONALLY_CANCELLABLE") return "unconditionally_cancellable";
    return "direct_credit_substitutes_and_other_100pct_items";
}

int rank_of(const string& seniority) {
    if (seniority == "COVERED") return 4;
    if (seniority == "SENIOR") return 3;
    if (seniority == "NON_SENIOR") return 2;
    return 1;  // EQUITY
}

[[noreturn]] void input_error(const string& message, const string& field) { throw Error("E_INPUT", message, field); }
[[noreturn]] void domain_error(const string& message, const string& field) { throw Error("E_DOMAIN", message, field); }

void not_negative(double value, const string& field) {
    if (value < 0) domain_error(field + " must not be negative", field);
}

double fsum3(double a, double b, double c) { return research::fsum({a, b, c}); }

}  // namespace

const std::vector<string>& ccf_categories() {
    static const std::vector<string> v = {"DIRECT_CREDIT_SUBSTITUTE", "FORWARD_PURCHASE", "OTHER_CREDIT_SUBSTITUTE",
                                          "NIF_RUF",  "TRANSACTION_CONTINGENT", "COMMITMENT", "TRADE_LC",
                                          "UNCONDITIONALLY_CANCELLABLE"};
    return v;
}

const std::vector<string>& seniorities() {
    static const std::vector<string> v = {"COVERED", "SENIOR", "NON_SENIOR", "EQUITY"};
    return v;
}

double derivative_exposure(const DerivativeSet& d) {
    const double rc = d.v - d.cvm_received + d.cvm_provided;
    return num(lev(), "deriv.alpha") * ((0.0 > rc ? 0.0 : rc) + d.pfe);
}

double written_cd_effective_notional(const WrittenCreditDerivative& w) {
    const double reduction = -w.fair_value > 0.0 ? -w.fair_value : 0.0;
    const double x = w.notional - reduction - w.purchased_offset;
    return 0.0 > x ? 0.0 : x;
}

double sft_exposure(const Sft& s) {
    double add;
    if (s.mna) {
        const double x = research::fsum(s.exposures) - research::fsum(s.collateral);
        add = x > 0.0 ? x : 0.0;
    } else {
        std::vector<double> parts;
        for (std::size_t k = 0; k < s.exposures.size(); ++k) {
            const double x = s.exposures[k] - s.collateral[k];
            parts.push_back(x > 0.0 ? x : 0.0);
        }
        add = research::fsum(parts);
    }
    return s.gross_assets + add;
}

LeverageResult leverage(double tier1, const std::vector<double>& on_balance, const std::vector<DerivativeSet>& derivatives,
                        const std::vector<WrittenCreditDerivative>& written_credit_derivatives,
                        const std::vector<Sft>& sfts, const std::vector<OffBalance>& off_balance) {
    for (const Sft& s : sfts)
        if (s.exposures.size() != s.collateral.size()) input_error("exposures and collateral differ in length", "collateral");
    if (!(tier1 > 0)) domain_error("tier1 must be positive", "tier1");
    for (const double x : on_balance) not_negative(x, "on_balance");
    for (const DerivativeSet& d : derivatives) {
        not_negative(d.cvm_received, "cvm_received");
        not_negative(d.cvm_provided, "cvm_provided");
        not_negative(d.pfe, "pfe");
    }
    for (const WrittenCreditDerivative& w : written_credit_derivatives) {
        not_negative(w.notional, "notional");
        not_negative(w.purchased_offset, "purchased_offset");
    }
    for (const Sft& s : sfts) {
        not_negative(s.gross_assets, "gross_assets");
        for (const double e : s.exposures) not_negative(e, "exposures");
        for (const double c : s.collateral) not_negative(c, "collateral");
    }
    for (const OffBalance& o : off_balance) not_negative(o.notional, "notional");

    LeverageResult r;
    r.on_balance = research::fsum(on_balance);
    std::vector<double> parts;
    for (const DerivativeSet& d : derivatives) parts.push_back(derivative_exposure(d));
    r.derivative_netting_sets = research::fsum(parts);
    parts.clear();
    for (const WrittenCreditDerivative& w : written_credit_derivatives) parts.push_back(written_cd_effective_notional(w));
    r.written_credit_derivatives = research::fsum(parts);
    r.derivatives = r.derivative_netting_sets + r.written_credit_derivatives;  // KR-320
    parts.clear();
    for (const Sft& s : sfts) parts.push_back(sft_exposure(s));
    r.sfts = research::fsum(parts);
    parts.clear();
    const Value& ccf = lev().find("ccf")->second;
    for (const OffBalance& o : off_balance) parts.push_back(o.notional * dec(*ccf.find(ccf_key(o.ccf_category))));
    r.off_balance = research::fsum(parts);
    r.exposure = research::fsum({r.on_balance, r.derivatives, r.sfts, r.off_balance});  // LEV20.5
    if (!(r.exposure > 0)) domain_error("the exposure measure is zero: no ratio (KR-321)", "on_balance");
    r.ratio = tier1 / r.exposure;                                              // LEV20.3
    r.meets_minimum = tier1 >= num(lev(), "min_leverage_ratio") * r.exposure;  // LEV20.7, binary64
    return r;
}

std::pair<double, double> offset_by_seniority(const std::vector<std::pair<int, double>>& positions) {
    std::vector<std::pair<int, double>> longs;
    std::vector<std::pair<int, double>> shorts;
    for (const auto& [r, j] : positions) {
        if (j > 0) longs.emplace_back(r, j);
        else if (j < 0) shorts.emplace_back(r, -j);
    }
    std::vector<std::size_t> long_order(longs.size());
    for (std::size_t i = 0; i < longs.size(); ++i) long_order[i] = i;
    std::stable_sort(long_order.begin(), long_order.end(),
                     [&](std::size_t a, std::size_t b) { return longs[a].first < longs[b].first; });
    std::stable_sort(shorts.begin(), shorts.end(), [](const auto& a, const auto& b) { return a.first > b.first; });
    std::vector<double> left_short;
    for (const auto& [r, start] : shorts) {
        double amount = start;
        for (const std::size_t i : long_order) {
            if (amount <= 0) break;
            if (longs[i].first >= r && longs[i].second > 0) {
                const double used = longs[i].second < amount ? longs[i].second : amount;
                longs[i].second -= used;
                amount -= used;
            }
        }
        left_short.push_back(amount);
    }
    std::vector<double> rest;
    for (const auto& l : longs) rest.push_back(l.second);
    return {research::fsum(rest), -research::fsum(left_short)};
}

double jtd(const TradingPosition& p) {
    if (p.notional >= 0) return 0.0 > p.market_value ? 0.0 : p.market_value;
    return 0.0 < p.market_value ? 0.0 : p.market_value;
}

LargeExposuresResult large_exposures(double tier1, const std::vector<LeCounterparty>& counterparties,
                                     const std::vector<BankingBookExposure>& banking_book,
                                     const std::vector<OffBalanceExposure>& off_balance,
                                     const std::vector<Protection>& crm,
                                     const std::vector<TradingPosition>& trading_book, bool bank_gsib) {
    // Structure (E_INPUT).
    std::map<string, std::optional<string>> group_of;
    std::map<string, std::size_t> position_of;
    for (std::size_t n = 0; n < counterparties.size(); ++n) {
        const LeCounterparty& c = counterparties[n];
        if (!group_of.emplace(c.id, c.group).second)
            input_error("counterparty " + c.id + " appears twice (so possibly in two groups)", "id");
        position_of.emplace(c.id, n);
    }
    for (const LeCounterparty& c : counterparties)
        if (c.group && group_of.contains(*c.group) && group_of.at(*c.group) != c.group)
            input_error("group " + *c.group + " is also a counterparty outside it (KR-324)", "group");
    const auto known = [&](const string& name, const string& field) {
        if (!group_of.contains(name)) input_error("unknown counterparty " + name, field);
    };
    for (const BankingBookExposure& b : banking_book) known(b.counterparty, "counterparty");
    for (const OffBalanceExposure& o : off_balance) known(o.counterparty, "counterparty");
    for (const Protection& p : crm) known(p.counterparty, "counterparty");
    for (const Protection& p : crm) known(p.provider, "provider");
    for (const TradingPosition& t : trading_book) known(t.counterparty, "counterparty");
    for (const Protection& p : crm)
        if (p.provider == p.counterparty) input_error("a counterparty cannot protect itself", "provider");
    std::set<string> ids;
    for (const TradingPosition& t : trading_book)
        if (!ids.insert(t.id).second) input_error("position id " + t.id + " appears twice", "id");
    // Domain (E_DOMAIN).
    if (!(tier1 > 0)) domain_error("tier1 must be positive", "tier1");
    for (const BankingBookExposure& b : banking_book) not_negative(b.value, "value");
    for (const OffBalanceExposure& o : off_balance) {
        not_negative(o.notional, "notional");
        if (!(0 <= o.ccf && o.ccf <= 1)) domain_error("ccf must lie in [0, 1]", "ccf");
    }
    for (const Protection& p : crm) not_negative(p.protected_amount, "protected");

    const std::size_t n_cp = counterparties.size();
    std::vector<std::vector<double>> bb(n_cp), obs(n_cp), prot(n_cp), recv(n_cp);
    std::vector<std::vector<std::pair<int, double>>> positions(n_cp);
    const double ccf_floor = num(lex(), "exposure.obs_ccf_floor");
    for (const BankingBookExposure& b : banking_book) bb[position_of.at(b.counterparty)].push_back(b.value);
    for (const OffBalanceExposure& o : off_balance)
        obs[position_of.at(o.counterparty)].push_back(o.notional * (ccf_floor > o.ccf ? ccf_floor : o.ccf));
    for (const Protection& p : crm) {
        prot[position_of.at(p.counterparty)].push_back(p.protected_amount);
        recv[position_of.at(p.provider)].push_back(p.protected_amount);
    }
    for (const TradingPosition& t : trading_book)
        positions[position_of.at(t.counterparty)].emplace_back(rank_of(t.seniority), jtd(t));

    LargeExposuresResult out;
    std::vector<double> exposure(n_cp);
    for (std::size_t n = 0; n < n_cp; ++n) {
        const LeCounterparty& c = counterparties[n];
        const auto [net_long, net_short] = offset_by_seniority(positions[n]);  // LEX30.22-30.23, 30.30
        const double b_sum = research::fsum(bb[n]), o_sum = research::fsum(obs[n]);
        const double p_sum = research::fsum(prot[n]), r_sum = research::fsum(recv[n]);
        const double gross = fsum3(b_sum, o_sum, net_long);
        if (p_sum > gross) domain_error("counterparty " + c.id + ": protected amount above its exposure", "protected");
        exposure[n] = fsum3(gross, -p_sum, r_sum);  // LEX30.13-30.15
        out.counterparties.push_back({c.id, b_sum, o_sum, net_long, net_short, p_sum, r_sum, exposure[n]});
    }
    std::map<string, std::vector<std::size_t>> members;  // ordered by name: code-point order on UTF-8 bytes
    for (std::size_t n = 0; n < n_cp; ++n)
        members[counterparties[n].group ? *counterparties[n].group : counterparties[n].id].push_back(n);
    const double large_share = num(lex(), "large_exposure_threshold");
    const double limit_plain = num(lex(), "limit"), limit_gsib = num(lex(), "limit.gsib_to_gsib");
    for (const auto& [name, ms] : members) {
        std::vector<double> all, counted;
        bool gsib = false, exempt = true;
        GroupRow g;
        g.group = name;
        for (const std::size_t n : ms) {
            const LeCounterparty& c = counterparties[n];
            all.push_back(exposure[n]);
            if (!c.exempt) counted.push_back(exposure[n]);  // KR-325
            gsib = gsib || c.gsib;
            exempt = exempt && c.exempt;
            g.members.push_back(c.id);
        }
        g.exposure = research::fsum(all);  // LEX10.9
        g.share = g.exposure / tier1;
        g.large = g.exposure >= large_share * tier1;                      // LEX10.8, binary64 (KR-326)
        g.limit = ((bank_gsib && gsib) ? limit_gsib : limit_plain) * tier1;  // KR-324: any member flagged
        g.breach = research::fsum(counted) > g.limit;
        g.exempt = exempt;
        out.groups.push_back(std::move(g));
    }
    std::vector<std::size_t> ranked(out.groups.size());
    for (std::size_t k = 0; k < ranked.size(); ++k) ranked[k] = k;
    std::stable_sort(ranked.begin(), ranked.end(), [&](std::size_t a, std::size_t b) {
        const GroupRow &x = out.groups[a], &y = out.groups[b];
        if (x.exposure != y.exposure) return x.exposure > y.exposure;
        return x.group < y.group;
    });  // LEX20.4: largest first, ties by name
    const auto top_n = std::size_t(num(lex(), "report.top_n"));
    for (std::size_t k = 0; k < ranked.size(); ++k)
        if (out.groups[ranked[k]].large || k < top_n) out.report.push_back(out.groups[ranked[k]].group);
    return out;
}

}  // namespace quantforge::leverage
