#include "quantforge/core/saccr.hpp"

#include <algorithm>
#include <cmath>
#include <initializer_list>
#include <map>
#include <set>
#include <string_view>
#include <tuple>

#include "quantforge/core/error.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/research.hpp"
#include "quantforge/core/stats.hpp"

namespace quantforge::saccr {
namespace {

#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wc23-extensions"
#endif
constexpr unsigned char table_bytes[] = {
#embed "../../../specifications/06-risk/sa-ccr-parameters.json"
};
#if defined(__clang__)
#pragma clang diagnostic pop
#endif

double num(const json::Value& doc, std::initializer_list<std::string_view> path) {
    const json::Value* v = &doc;
    for (const auto k : path) v = v->find(k);
    return v->number;
}

long long whole(const json::Value& doc, std::initializer_list<std::string_view> path) {
    return (long long)num(doc, path);
}

Params parse_params() {
    const std::string_view text(reinterpret_cast<const char*>(table_bytes), sizeof table_bytes);
    const auto parsed = json::parse(text);
    const json::Value& d = parsed.value;
    Params p{};
    p.alpha = num(d, {"alpha"});
    p.floor = num(d, {"multiplier_floor"});
    p.year_days = whole(d, {"business_days_per_year"});
    p.min_days = whole(d, {"min_business_days"});
    p.sd_rate = num(d, {"supervisory_duration_rate"});
    p.rho12 = num(d, {"ir_bucket_correlations", "b1_b2"});
    p.rho23 = num(d, {"ir_bucket_correlations", "b2_b3"});
    p.rho13 = num(d, {"ir_bucket_correlations", "b1_b3"});
    p.bucket1_below = num(d, {"ir_bucket_bounds_years", "bucket1_below"});
    p.bucket2_up_to = num(d, {"ir_bucket_bounds_years", "bucket2_up_to_and_including"});
    p.margined_mf_scale = num(d, {"margined_maturity_factor_scale"});
    p.mpor_daily = whole(d, {"mpor_floor_days", "daily_margin"});
    p.mpor_non_daily_base = whole(d, {"mpor_floor_days", "non_daily_base"});
    p.mpor_large = whole(d, {"mpor_floor_days", "large_or_illiquid"});
    p.mpor_large_trades_above = whole(d, {"mpor_floor_days", "large_netting_set_trades_above"});
    p.mpor_dispute_multiplier = whole(d, {"mpor_floor_days", "dispute_multiplier"});
    p.scale = {num(d, {"treatment_scale", "NORMAL"}), num(d, {"treatment_scale", "BASIS"}),
               num(d, {"treatment_scale", "VOLATILITY"})};
    p.cdo_numerator = num(d, {"cdo_delta", "numerator"});
    p.cdo_slope = num(d, {"cdo_delta", "slope"});
    for (const json::Value& r : d.find("table2")->items) {
        Row row;
        row.asset_class = r.find("asset_class")->text;
        if (const auto* s = r.find("subclass"); s->kind == json::Kind::String) row.subclass = s->text;
        row.factor = r.find("supervisory_factor")->number;
        if (const auto* c = r.find("correlation"); c->kind == json::Kind::Number) row.correlation = c->number;
        row.option_volatility = r.find("option_volatility")->number;
        if (const auto* h = r.find("hedging_set")) row.hedging_set = h->text;
        p.table2.push_back(std::move(row));
    }
    return p;
}

const Row* find_row(std::string_view cls, const std::optional<std::string>& sub) {
    const std::string_view s = sub ? std::string_view(*sub) : std::string_view();
    for (const Row& r : params().table2)
        if (r.asset_class == cls && r.subclass == s) return &r;
    return nullptr;
}

// Only after the structural checks, which guarantee the row exists.
const Row& row_of(const Trade& t) { return *find_row(t.asset_class, t.subclass); }

double min_years() { return double(params().min_days) / double(params().year_days); }

std::size_t index_of(const auto& list, std::string_view name) {
    for (std::size_t i = 0; i < list.size(); ++i)
        if (name == list[i]) return i;
    return 0;
}

double factor_of(const Trade& t) { return row_of(t).factor * params().scale[index_of(treatments, t.treatment)]; }

[[noreturn]] void input_error(const std::string& field, const std::string& message) {
    throw Error("E_INPUT", message, field);
}

[[noreturn]] void domain_error(const std::string& field, const std::string& message) {
    throw Error("E_DOMAIN", message, field);
}

template <class T>
void need(const Trade& t, const std::optional<T>& v, const std::string& field, const std::string& why) {
    if (!v) input_error(field, "trade " + t.id + ": " + field + " is required " + why);
}

void structure(const std::vector<Trade>& trades) {
    if (trades.empty()) input_error("trades", "trades is empty");
    std::set<std::string> seen;
    for (const Trade& t : trades) {
        if (!seen.insert(t.id).second) input_error("id", "duplicate trade id " + t.id);
        const std::string& c = t.asset_class;
        if (c == "IR" || c == "CREDIT") {
            need(t, t.start, "start", "for IR and CREDIT trades");
            need(t, t.end, "end", "for IR and CREDIT trades");
        }
        if (c == "IR" || c == "FX" || t.treatment != "NORMAL")
            need(t, t.hedging_set, "hedging_set", "for IR, FX, basis and volatility trades");
        if (c == "CREDIT" || c == "EQUITY" || c == "COMMODITY") {
            need(t, t.entity, "entity", "for CREDIT, EQUITY and COMMODITY trades");
            need(t, t.subclass, "subclass", "for CREDIT, EQUITY and COMMODITY trades");
            if (!find_row(c, t.subclass))
                input_error("subclass", "trade " + t.id + ": subclass " + *t.subclass + " is not a " + c + " subclass");
        } else if (t.subclass) {
            input_error("subclass", "trade " + t.id + ": " + c + " trades take no subclass");
        }
        const bool linear = t.position == "LONG" || t.position == "SHORT";
        if ((t.kind == "LINEAR") != linear)
            input_error("position", "trade " + t.id + ": position " + t.position + " does not fit kind " + t.kind);
        if (t.kind == "OPTION") {
            need(t, t.option_type, "option_type", "for OPTION trades");
            need(t, t.underlying_price, "underlying_price", "for OPTION trades");
            need(t, t.strike, "strike", "for OPTION trades");
            need(t, t.exercise, "exercise", "for OPTION trades");
        }
        if (t.kind == "CDO") {
            if (c != "CREDIT") input_error("kind", "trade " + t.id + ": CDO tranches are CREDIT trades");
            need(t, t.attachment, "attachment", "for CDO trades");
            need(t, t.detachment, "detachment", "for CDO trades");
        }
    }
    std::map<std::tuple<std::string, std::string, std::string, std::string>, std::string> entity_sub;
    for (const Trade& t : trades) {
        if (!t.entity || !t.subclass) continue;
        const auto key = std::make_tuple(t.asset_class, t.treatment, t.hedging_set.value_or(""), *t.entity);
        const auto [it, fresh] = entity_sub.emplace(key, *t.subclass);
        if (!fresh && it->second != *t.subclass) input_error("subclass", "entity " + *t.entity + " has two subclasses");
    }
}

double or0(const std::optional<double>& v) { return v.value_or(0.0); }

void domain(const std::vector<Trade>& trades, const std::optional<Margin>& margin) {
    for (const Trade& t : trades) {
        if (!(t.notional > 0)) domain_error("notional", "trade " + t.id + ": notional must be positive");
        if (!(t.maturity > 0)) domain_error("maturity", "trade " + t.id + ": maturity must be positive");
        if (t.start && t.end && !(0 <= *t.start && *t.start <= *t.end))
            domain_error("start", "trade " + t.id + ": need 0 <= start <= end");
        if (t.kind == "OPTION") {
            const double p = or0(t.underlying_price) + t.shift;
            const double k = or0(t.strike) + t.shift;
            if (!(p > 0 && k > 0)) domain_error("strike", "trade " + t.id + ": shifted price and strike must be positive");
            if (!(or0(t.exercise) > 0)) domain_error("exercise", "trade " + t.id + ": exercise must be positive");
        }
        if (t.kind == "CDO") {
            const double a = or0(t.attachment);
            const double d = or0(t.detachment);
            if (!(0 <= a && a < d && d <= 1))
                domain_error("attachment", "trade " + t.id + ": need 0 <= attachment < detachment <= 1");
        }
    }
    if (margin) {
        if (margin->threshold < 0) domain_error("threshold", "threshold must not be negative");
        if (margin->mta < 0) domain_error("mta", "mta must not be negative");
        if (margin->remargin_days < 1) domain_error("remargin_days", "remargin_days must be at least 1");
        if (margin->mpor_days && *margin->mpor_days < 1) domain_error("mpor_days", "mpor_days must be at least 1");
    }
}

void finite_or_throw(const char* field, double v) {
    if (!std::isfinite(v)) domain_error(field, std::string(field) + " must be finite");
}

void finite_or_throw(const char* field, const std::optional<double>& v) {
    if (v) finite_or_throw(field, *v);
}

void check_finite(const std::vector<Trade>& trades, double collateral, const std::optional<Margin>& margin) {
    for (const Trade& t : trades) {
        finite_or_throw("notional", t.notional);
        finite_or_throw("market_value", t.market_value);
        finite_or_throw("maturity", t.maturity);
        finite_or_throw("shift", t.shift);
        finite_or_throw("start", t.start);
        finite_or_throw("end", t.end);
        finite_or_throw("underlying_price", t.underlying_price);
        finite_or_throw("strike", t.strike);
        finite_or_throw("exercise", t.exercise);
        finite_or_throw("attachment", t.attachment);
        finite_or_throw("detachment", t.detachment);
    }
    finite_or_throw("collateral", collateral);
    if (margin) {
        finite_or_throw("threshold", margin->threshold);
        finite_or_throw("mta", margin->mta);
        finite_or_throw("nica", margin->nica);
    }
}

double single_factor(const std::vector<std::pair<double, double>>& pairs) {
    std::vector<double> sys, idio;
    for (const auto& [r, a] : pairs) {
        sys.push_back(r * a);
        idio.push_back((1.0 - r * r) * a * a);
    }
    const double s = research::fsum(sys);
    return std::sqrt(s * s + research::fsum(idio));
}

std::string group_key(const Trade& t) {
    const bool normal = t.treatment == "NORMAL";
    if (t.asset_class == "COMMODITY" && normal) return row_of(t).hedging_set.value_or("");
    if ((t.asset_class == "CREDIT" || t.asset_class == "EQUITY") && normal) return "";
    return t.hedging_set.value_or("");
}

struct Netting {
    double ead_value, pfe, m;
    std::array<double, 5> by_class;
    std::vector<HedgingSet> rows;
    std::vector<double> deltas, eff;
};

double ir_addon(const std::vector<Trade>& trades, const std::vector<std::size_t>& members, const std::vector<double>& eff,
                std::size_t treatment, bool offset) {
    const Params& p = params();
    std::array<std::vector<double>, 3> parts;
    for (const std::size_t i : members) parts[std::size_t(bucket(or0(trades[i].end)) - 1)].push_back(eff[i]);
    const double b1 = research::fsum(parts[0]);
    const double b2 = research::fsum(parts[1]);
    const double b3 = research::fsum(parts[2]);
    const double en =
        offset ? std::sqrt(std::max(b1 * b1 + b2 * b2 + b3 * b3 + p.rho12 * b1 * b2 + p.rho23 * b2 * b3 + p.rho13 * b1 * b3,
                                    0.0))
               : std::fabs(b1) + std::fabs(b2) + std::fabs(b3);
    return find_row("IR", std::nullopt)->factor * p.scale[treatment] * en;
}

Netting netting(const std::vector<Trade>& trades, const std::vector<double>& mf, const std::vector<double>& d,
                double v_minus_c, double rc, bool offset) {
    Netting out{};
    const std::size_t n = trades.size();
    for (std::size_t i = 0; i < n; ++i) {
        out.deltas.push_back(supervisory_delta(trades[i]));
        out.eff.push_back(d[i] * mf[i] * out.deltas[i]);
    }
    // std::string compares as unsigned bytes, which for UTF-8 is code-point order, as Python sorts.
    std::map<std::tuple<std::size_t, std::size_t, std::string>, std::vector<std::size_t>> groups;
    for (std::size_t i = 0; i < n; ++i)
        groups[{index_of(classes, trades[i].asset_class), index_of(treatments, trades[i].treatment),
                group_key(trades[i])}]
            .push_back(i);
    for (const auto& [g, members] : groups) {
        const auto& [cls, treatment, key] = g;
        double addon = 0.0;
        if (cls == 0) {
            addon = ir_addon(trades, members, out.eff, treatment, offset);
        } else if (cls == 1) {
            std::vector<double> s;
            for (const std::size_t i : members) s.push_back(out.eff[i]);
            addon = find_row("FX", std::nullopt)->factor * params().scale[treatment] * std::fabs(research::fsum(s));
        } else {
            std::map<std::string, std::vector<std::size_t>> entities;
            for (const std::size_t i : members) entities[trades[i].entity.value_or("")].push_back(i);
            std::vector<std::pair<double, double>> pairs;
            for (const auto& [name, idx] : entities) {
                const Trade& first = trades[idx.front()];
                std::vector<double> s;
                for (const std::size_t i : idx) s.push_back(out.eff[i]);
                pairs.emplace_back(row_of(first).correlation.value_or(0.0), factor_of(first) * research::fsum(s));
            }
            addon = single_factor(pairs);
        }
        out.by_class[cls] += addon;
        out.rows.push_back({classes[cls], treatments[treatment], key, addon});
    }
    const double aggregate = research::fsum(std::vector<double>(out.by_class.begin(), out.by_class.end()));
    out.m = multiplier(v_minus_c, aggregate);
    out.pfe = out.m * aggregate;
    out.ead_value = params().alpha * (rc + out.pfe);
    return out;
}

}  // namespace

const Params& params() {
    static const Params p = parse_params();
    return p;
}

double supervisory_duration(double start, double end) {
    const double r = params().sd_rate;
    const double sd = (std::exp(-r * start) - std::exp(-r * end)) / r;
    return std::max(sd, min_years());
}

long long mpor_floor(const Margin& m, std::size_t trade_count) {
    const Params& p = params();
    long long base = m.remargin_days == 1 ? p.mpor_daily : p.mpor_non_daily_base + m.remargin_days;
    if ((long long)trade_count > p.mpor_large_trades_above || m.illiquid) base = std::max(base, p.mpor_large);
    return m.disputes ? p.mpor_dispute_multiplier * base : base;
}

double supervisory_delta(const Trade& t) {
    if (t.kind == "LINEAR") return t.position == "LONG" ? 1.0 : -1.0;
    const bool bought = t.position == "BOUGHT";
    if (t.kind == "CDO") {
        const Params& p = params();
        const double a = or0(t.attachment);
        const double d = or0(t.detachment);
        const double v = p.cdo_numerator / ((1.0 + p.cdo_slope * a) * (1.0 + p.cdo_slope * d));
        return bought ? v : -v;
    }
    const double sigma = row_of(t).option_volatility;
    const double tt = or0(t.exercise);
    const double pr = or0(t.underlying_price) + t.shift;
    const double k = or0(t.strike) + t.shift;
    const double d1 = (std::log(pr / k) + 0.5 * sigma * sigma * tt) / (sigma * std::sqrt(tt));
    const double sign = bought ? 1.0 : -1.0;
    return sign * (t.option_type == std::optional<std::string>("CALL") ? normal_cdf(d1) : -normal_cdf(-d1));
}

double multiplier(double v_minus_c, double addon) {
    if (v_minus_c >= 0) return 1.0;
    const double fl = params().floor;
    if (addon == 0.0) return fl;
    return std::min(1.0, fl + (1.0 - fl) * std::exp(v_minus_c / (2.0 * (1.0 - fl) * addon)));
}

int bucket(double end) {
    const Params& p = params();
    return end < p.bucket1_below ? 1 : end <= p.bucket2_up_to ? 2 : 3;
}

Result ead(const std::vector<Trade>& trades, double collateral, const std::optional<Margin>& margin, bool ir_offset) {
    check_finite(trades, collateral, margin);
    structure(trades);
    domain(trades, margin);
    const std::size_t n = trades.size();
    std::vector<double> mv;
    for (const Trade& t : trades) mv.push_back(t.market_value);
    const double v = research::fsum(mv);
    const double c = collateral;
    std::vector<std::optional<double>> sd;
    std::vector<double> d, mf_un;
    for (const Trade& t : trades) {
        if (t.asset_class == "IR" || t.asset_class == "CREDIT") {
            const double s = supervisory_duration(or0(t.start), or0(t.end));
            sd.emplace_back(s);
            d.push_back(t.notional * s);
        } else {
            sd.emplace_back(std::nullopt);
            d.push_back(t.notional);
        }
        mf_un.push_back(std::sqrt(std::min(std::max(t.maturity, min_years()), 1.0)));
    }
    const double rc_un = std::max(v - c, 0.0);
    Netting un = netting(trades, mf_un, d, v - c, rc_un, ir_offset);
    Result r{};
    std::vector<double> mf = mf_un;
    if (!margin) {
        r.rc = rc_un;
    } else {
        const Params& p = params();
        const long long mpor = std::max(mpor_floor(*margin, n), margin->mpor_days.value_or(0));
        mf.assign(n, p.margined_mf_scale * std::sqrt(double(mpor) / double(p.year_days)));
        r.rc = std::max(std::max(v - c, margin->threshold + margin->mta - margin->nica), 0.0);
        r.mpor_days = mpor;
        r.ead_unmargined = un.ead_value;
    }
    const Netting res = margin ? netting(trades, mf, d, v - c, r.rc, ir_offset) : un;
    r.capped = margin && un.ead_value < res.ead_value;
    r.ead = margin ? std::min(res.ead_value, un.ead_value) : res.ead_value;
    r.pfe = res.pfe;
    r.multiplier = res.m;
    r.addon = res.by_class;
    r.addon_aggregate = research::fsum(std::vector<double>(res.by_class.begin(), res.by_class.end()));
    r.v = v;
    r.c = c;
    r.margined = margin.has_value();
    r.hedging_sets = res.rows;
    for (std::size_t i = 0; i < n; ++i)
        r.trades.push_back({trades[i].id, sd[i], d[i], mf[i], res.deltas[i], res.eff[i], factor_of(trades[i])});
    return r;
}

}  // namespace quantforge::saccr
