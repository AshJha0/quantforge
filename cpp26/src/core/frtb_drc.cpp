#include "quantforge/core/frtb_drc.hpp"

#include <algorithm>
#include <charconv>
#include <cstddef>
#include <numeric>
#include <set>
#include <string_view>
#include <tuple>

#include "quantforge/core/error.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/research.hpp"

namespace quantforge::frtb_drc {
namespace {

#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wc23-extensions"
#endif
constexpr unsigned char drc_bytes[] = {
#embed "../../../specifications/tables/stage_k/mar22_drc.json"
};
constexpr unsigned char rrao_bytes[] = {
#embed "../../../specifications/tables/stage_k/mar23_rrao.json"
};
#if defined(__clang__)
#pragma clang diagnostic pop
#endif

// The `value` of the entry named `key`, a decimal string (HR-12), as binary64.
double entry(const json::Value& doc, std::string_view key) {
    for (const json::Value& e : doc.find("entries")->items)
        if (e.find("key")->text == key) {
            const std::string& s = e.find("value")->text;
            double x = 0.0;
            std::from_chars(s.data(), s.data() + s.size(), x);
            return x;
        }
    throw Error("E_INTERNAL", "table entry missing: " + std::string(key));
}

Params parse_params() {
    const auto drc = json::parse(std::string_view(reinterpret_cast<const char*>(drc_bytes), sizeof drc_bytes));
    const auto rr = json::parse(std::string_view(reinterpret_cast<const char*>(rrao_bytes), sizeof rrao_bytes));
    const json::Value& d = drc.value;
    Params p;
    p.buckets = {"CORPORATE", "SOVEREIGN", "LOCAL_GOV"};  // buckets.nonsec, in the table's order
    p.seniorities = {"COVERED", "SENIOR", "NON_SENIOR", "EQUITY"};
    p.ratings = {"AAA", "AA", "A", "BBB", "BB", "B", "CCC", "UNRATED", "DEFAULTED"};
    p.lgd = {{"COVERED", entry(d, "lgd.covered_bond")},
             {"SENIOR", entry(d, "lgd.senior_debt")},
             {"NON_SENIOR", entry(d, "lgd.non_senior_debt")},
             {"EQUITY", entry(d, "lgd.equity")}};
    for (const std::string& r : p.ratings) {
        const std::string key = r == "UNRATED" ? "rw.Unrated" : r == "DEFAULTED" ? "rw.Defaulted" : "rw." + r;
        p.risk_weight[r] = entry(d, key);
    }
    p.capital_horizon = entry(d, "capital_horizon_years");
    p.maturity_floor = entry(d, "maturity_weight_floor");
    // cash_equity_maturity_choices ["0.25", ">1"]: the first is the short choice of MAR22.16
    {
        double x = 0.0;
        for (const json::Value& e : d.find("entries")->items)
            if (e.find("key")->text == "cash_equity_maturity_choices") {
                const std::string& s = e.find("value")->items.at(0).text;
                std::from_chars(s.data(), s.data() + s.size(), x);
            }
        p.cash_equity_short = x;
    }
    p.ctp_cross_factor = entry(d, "ctp_cross_index_factor");
    p.rrao_weight = {{"EXOTIC", entry(rr.value, "rw.exotic_underlying")},
                     {"OTHER", entry(rr.value, "rw.other_residual_risk")}};
    return p;
}

[[noreturn]] void fail(const char* code, const std::string& message, const std::string& field) {
    throw Error(code, message, field);
}

void check_limit(std::size_t n, const std::string& field) {
    if ((long long)n > max_positions) fail("E_LIMIT", field + " is above its limit of 100000", field);
}

template <class T>
void check_unique(const std::vector<T>& rows, const std::string& field) {
    std::set<std::string> seen;
    for (std::size_t k = 0; k < rows.size(); ++k)
        if (!seen.insert(rows[k].id).second)
            fail("E_INPUT", "duplicate id " + rows[k].id, field + "/" + std::to_string(k) + "/id");
}

void check_maturity(double m, const std::string& path) {
    if (!(m > 0.0)) fail("E_DOMAIN", "maturity_years must be above 0", path);
}

// (rw, net long, net short) of one obligor or netting group.
struct Net {
    double rw, net_long, net_short;
};

// MAR22.23, MAR22.25 and KR-54 over the obligors of one bucket.
BucketRow bucket_charge(const std::string& name, const std::vector<Net>& pairs) {
    std::vector<double> nl, ns, wl, ws;
    for (const Net& x : pairs) {
        nl.push_back(x.net_long);
        ns.push_back(-x.net_short);
        wl.push_back(x.rw * x.net_long);
        ws.push_back(x.rw * -x.net_short);
    }
    const double long_sum = research::fsum(nl), short_sum = research::fsum(ns);
    const double wtd_long = research::fsum(wl), wtd_short = research::fsum(ws);
    const double total = long_sum + short_sum;
    BucketRow b{name, std::nullopt, wtd_long, wtd_short, 0.0};
    if (total > 0.0) {
        b.hbr = long_sum / total;
        b.drc = std::max(wtd_long - *b.hbr * wtd_short, 0.0);
    }
    return b;
}

double total_drc(const std::vector<BucketRow>& buckets) {
    std::vector<double> v;
    for (const BucketRow& b : buckets) v.push_back(b.drc);
    return research::fsum(v);
}

double sec_weight(double m) { return m > 0.0 ? maturity_weight(m) : 0.0; }

// Rows sorted by id in code-point order (KR-302); ids are unique by then.
void sort_rows(std::vector<PositionRow>& rows) {
    std::ranges::stable_sort(rows, [](const PositionRow& a, const PositionRow& b) { return a.id < b.id; });
}

// The scaled JTDs summed per netting key in first-seen order (MAR22.29, MAR22.39(1)); one rw per key (KR-303).
using Key = std::tuple<std::string, std::string, std::string>;
struct Group {
    Key key;
    double rw;
    std::vector<double> parts;
};

std::vector<Group> net_groups(const std::vector<Key>& keys, const std::vector<double>& rws,
                              const std::vector<double>& scaled) {
    std::vector<Group> groups;
    std::map<Key, std::size_t> at;
    for (std::size_t k = 0; k < keys.size(); ++k) {
        const auto [it, fresh] = at.emplace(keys[k], groups.size());
        if (fresh) groups.push_back({keys[k], rws[k], {}});
        else if (groups[it->second].rw != rws[k])
            fail("E_INPUT", "positions netted together carry different rw", "positions/" + std::to_string(k) + "/rw");
        groups[it->second].parts.push_back(scaled[k]);
    }
    return groups;
}

void caller_rw(const std::vector<double>& rws, const std::vector<double>& maturities) {
    for (std::size_t k = 0; k < rws.size(); ++k) {
        const std::string path = "positions/" + std::to_string(k);
        check_maturity(maturities[k], path + "/maturity_years");
        if (!(rws[k] >= 0.0 && rws[k] <= rw_cap)) fail("E_DOMAIN", "rw must be in [0, 12.5]", path + "/rw");
    }
}

}  // namespace

const Params& params() {
    static const Params p = parse_params();
    return p;
}

int rank(const std::string& seniority) {
    if (seniority == "COVERED") return 4;
    if (seniority == "SENIOR") return 3;
    if (seniority == "NON_SENIOR") return 2;
    return 1;  // EQUITY
}

double maturity_weight(double maturity_years) {
    const Params& p = params();
    return maturity_years >= p.capital_horizon ? 1.0 : std::max(maturity_years, p.maturity_floor);
}

double gross_jtd(const Position& p) {
    const double lgd = p.lgd_applies ? params().lgd.at(p.seniority) : 1.0;
    const double pnl = p.market_value - p.notional;
    const double raw = lgd * p.notional + pnl;
    if (p.notional > 0.0) return std::max(raw, 0.0);
    if (p.notional < 0.0) return std::min(raw, 0.0);
    return 0.0;
}

std::pair<double, double> offset(const std::vector<std::pair<int, double>>& longs,
                                 const std::vector<std::pair<int, double>>& shorts) {
    std::vector<std::pair<int, double>> left = longs;
    std::vector<std::size_t> order(left.size());
    std::iota(order.begin(), order.end(), std::size_t{0});
    std::ranges::stable_sort(order, [&](std::size_t a, std::size_t b) { return left[a].first < left[b].first; });
    std::vector<std::size_t> short_order(shorts.size());
    std::iota(short_order.begin(), short_order.end(), std::size_t{0});
    std::ranges::stable_sort(short_order,
                             [&](std::size_t a, std::size_t b) { return shorts[a].first > shorts[b].first; });
    std::vector<double> rest;
    for (const std::size_t k : short_order) {
        const int r = shorts[k].first;
        double need = -shorts[k].second;
        for (const std::size_t j : order) {
            if (need <= 0.0) break;
            if (left[j].first < r || left[j].second <= 0.0) continue;
            const double used = std::min(need, left[j].second);
            left[j].second -= used;
            need -= used;
        }
        if (need > 0.0) rest.push_back(-need);
    }
    std::vector<double> remaining;
    for (const auto& x : left) remaining.push_back(x.second);
    return {research::fsum(remaining), research::fsum(rest)};
}

double ctp_total(const std::vector<double>& bucket_drc) {
    const double factor = params().ctp_cross_factor;
    std::vector<double> terms;
    for (const double d : bucket_drc) terms.push_back(std::max(d, 0.0) + factor * std::min(d, 0.0));
    return std::max(research::fsum(terms), 0.0);
}

NonsecResult drc_nonsec(const std::vector<Position>& positions, const std::map<std::string, std::string>& ratings) {
    check_limit(positions.size(), "positions");
    if (positions.empty()) fail("E_INPUT", "positions is empty", "positions");
    check_unique(positions, "positions");
    std::map<std::string, std::string> bucket_of;
    for (std::size_t k = 0; k < positions.size(); ++k) {
        const Position& p = positions[k];
        const std::string path = "positions/" + std::to_string(k);
        if (!ratings.contains(p.obligor)) fail("E_INPUT", "obligor " + p.obligor + " has no rating", path + "/obligor");
        if (bucket_of.emplace(p.obligor, p.bucket).first->second != p.bucket)  // KR-301
            fail("E_INPUT", "obligor " + p.obligor + " is in two buckets", path + "/bucket");
    }
    const Params& prm = params();
    for (std::size_t k = 0; k < positions.size(); ++k) {
        const Position& p = positions[k];
        const std::string path = "positions/" + std::to_string(k);
        check_maturity(p.maturity_years, path + "/maturity_years");
        if (p.cash_equity) {
            const double m = p.maturity_years;
            if (m != prm.cash_equity_short && m < prm.capital_horizon)  // KR-52
                fail("E_DOMAIN", "cash equity maturity must be 0.25 or at least 1", path);
            if (p.seniority != "EQUITY" || p.notional != p.market_value)  // KR-300
                fail("E_DOMAIN", "cash equity must be EQUITY with notional = market value", path);
        }
        if (p.notional == 0.0 && p.market_value != 0.0)
            fail("E_DOMAIN", "zero notional with a nonzero market value", path + "/notional");
    }

    NonsecResult out;
    std::map<std::string, std::vector<std::pair<int, double>>> longs, shorts;
    for (const Position& p : positions) {
        const double jtd = gross_jtd(p);
        const double w = maturity_weight(p.maturity_years);
        const double scaled = w * jtd;
        out.positions.push_back({p.id, jtd, w, scaled});
        auto& l = longs[p.obligor];
        auto& s = shorts[p.obligor];
        if (scaled > 0.0) l.emplace_back(rank(p.seniority), scaled);
        else if (scaled < 0.0) s.emplace_back(rank(p.seniority), scaled);
    }
    std::map<std::string, std::vector<Net>> per_bucket;
    for (const auto& [name, l] : longs) {  // obligors in code-point order (KR-302)
        const auto [net_long, net_short] = offset(l, shorts[name]);
        const double rw = prm.risk_weight.at(ratings.at(name));
        out.obligors.push_back({name, net_long, net_short, rw});
        per_bucket[bucket_of[name]].push_back({rw, net_long, net_short});
    }
    for (const std::string& b : prm.buckets)
        if (per_bucket.contains(b)) out.buckets.push_back(bucket_charge(b, per_bucket[b]));
    sort_rows(out.positions);
    out.drc = total_drc(out.buckets);
    return out;
}

SecResult drc_sec_nonctp(const std::vector<SecPosition>& positions) {
    check_limit(positions.size(), "positions");
    check_unique(positions, "positions");
    std::vector<Key> keys;
    std::vector<double> rws, weights, scaled, maturities;
    for (const SecPosition& p : positions) {
        keys.emplace_back(p.bucket, p.pool, p.tranche);
        rws.push_back(p.rw);
        weights.push_back(sec_weight(p.maturity_years));
        scaled.push_back(weights.back() * p.market_value);
        maturities.push_back(p.maturity_years);
    }
    const std::vector<Group> groups = net_groups(keys, rws, scaled);
    caller_rw(rws, maturities);
    std::map<std::string, std::vector<Net>> per_bucket;  // buckets in code-point order (KR-302)
    for (const Group& g : groups) {
        const double net = research::fsum(g.parts);
        per_bucket[std::get<0>(g.key)].push_back({g.rw, std::max(net, 0.0), std::min(net, 0.0)});
    }
    SecResult out;
    for (const auto& [name, pairs] : per_bucket) out.buckets.push_back(bucket_charge(name, pairs));
    for (std::size_t k = 0; k < positions.size(); ++k)
        out.positions.push_back({positions[k].id, std::nullopt, weights[k], scaled[k]});
    sort_rows(out.positions);
    out.drc = total_drc(out.buckets);
    return out;
}

CtpResult drc_ctp(const std::optional<std::vector<CtpPosition>>& positions,
                  const std::optional<std::vector<double>>& bucket_drc) {
    if (positions.has_value() == bucket_drc.has_value())
        fail("E_INPUT", "give exactly one of positions and bucket_drc", "positions");
    CtpResult out{};
    if (bucket_drc) {
        check_limit(bucket_drc->size(), "bucket_drc");
        out.by_position = false;
        out.drc = ctp_total(*bucket_drc);
        return out;
    }
    const std::vector<CtpPosition>& ps = *positions;
    check_limit(ps.size(), "positions");
    check_unique(ps, "positions");
    std::vector<Key> keys;
    std::vector<double> rws, weights, scaled, maturities;
    for (const CtpPosition& p : ps) {
        keys.emplace_back(p.index, p.series, p.tranche);
        rws.push_back(p.rw);
        weights.push_back(sec_weight(p.maturity_years));
        scaled.push_back(weights.back() * p.market_value);
        maturities.push_back(p.maturity_years);
    }
    const std::vector<Group> groups = net_groups(keys, rws, scaled);
    caller_rw(rws, maturities);
    std::vector<double> nets, long_parts, short_parts;
    for (const Group& g : groups) {
        nets.push_back(research::fsum(g.parts));
        long_parts.push_back(std::max(nets.back(), 0.0));
        short_parts.push_back(-std::min(nets.back(), 0.0));
    }
    const double long_sum = research::fsum(long_parts), short_sum = research::fsum(short_parts);
    const double total = long_sum + short_sum;
    if (total > 0.0) out.hbr_ctp = long_sum / total;  // KR-54 analogue
    std::map<std::string, std::vector<std::pair<double, double>>> per_index;  // code-point order (KR-302)
    for (std::size_t g = 0; g < groups.size(); ++g)
        per_index[std::get<0>(groups[g].key)].emplace_back(groups[g].rw, nets[g]);
    std::vector<double> drcs;
    for (const auto& [index, pairs] : per_index) {
        std::vector<double> wl, ws;
        for (const auto& [rw, n] : pairs) {
            if (n > 0.0) wl.push_back(rw * n);
            if (n < 0.0) ws.push_back(rw * -n);
        }
        const double wtd_long = research::fsum(wl), wtd_short = research::fsum(ws);
        const double drc_b = wtd_long - out.hbr_ctp.value_or(0.0) * wtd_short;  // MAR22.44: no floor
        out.buckets.push_back({index, std::nullopt, wtd_long, wtd_short, drc_b});
        drcs.push_back(drc_b);
    }
    for (std::size_t k = 0; k < ps.size(); ++k) out.positions.push_back({ps[k].id, std::nullopt, weights[k], scaled[k]});
    sort_rows(out.positions);
    out.by_position = true;
    out.drc = ctp_total(drcs);
    return out;
}

RraoResult rrao(const std::vector<Instrument>& instruments) {
    check_limit(instruments.size(), "instruments");
    check_unique(instruments, "instruments");
    for (std::size_t k = 0; k < instruments.size(); ++k)
        if (!(instruments[k].gross_notional >= 0.0))
            fail("E_DOMAIN", "gross_notional must be 0 or above", "instruments/" + std::to_string(k) + "/gross_notional");
    RraoResult out;
    std::vector<double> addons;
    for (const Instrument& x : instruments) {
        const bool excluded = x.back_to_back || (x.kind == "OTHER" && x.listed_or_clearable);
        const double w = params().rrao_weight.at(x.kind);
        out.instruments.push_back({x.id, w, excluded, excluded ? 0.0 : w * x.gross_notional});
        addons.push_back(out.instruments.back().addon);
    }
    out.rrao = research::fsum(addons);
    return out;
}

}  // namespace quantforge::frtb_drc
