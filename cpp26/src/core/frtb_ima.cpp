#include "quantforge/core/frtb_ima.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstddef>
#include <numbers>
#include <numeric>
#include <set>
#include <string_view>

#include "quantforge/core/error.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/research.hpp"
#include "quantforge/core/rng.hpp"
#include "quantforge/core/var_frtb.hpp"

namespace quantforge::frtb_ima {
namespace {

#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wc23-extensions"
#endif
constexpr unsigned char rfet_bytes[] = {
#embed "../../../specifications/tables/stage_k/mar31_rfet.json"
};
constexpr unsigned char pla_bytes[] = {
#embed "../../../specifications/tables/stage_k/mar32_pla.json"
};
constexpr unsigned char ima_bytes[] = {
#embed "../../../specifications/tables/stage_k/mar33_ima.json"
};
#if defined(__clang__)
#pragma clang diagnostic pop
#endif

json::Parsed parse_bytes(const unsigned char* bytes, std::size_t n) {
    return json::parse(std::string_view(reinterpret_cast<const char*>(bytes), n));
}

const json::Value& value_of(const json::Value& doc, std::string_view key) {
    for (const json::Value& e : doc.find("entries")->items)
        if (e.find("key")->text == key) return *e.find("value");
    throw Error("E_INTERNAL", "table entry missing: " + std::string(key));
}

double decimal(const json::Value& v) {
    double x = 0.0;
    std::from_chars(v.text.data(), v.text.data() + v.text.size(), x);
    return x;
}

double real_of(const json::Value& doc, std::string_view key) { return decimal(value_of(doc, key)); }
long long whole_of(const json::Value& doc, std::string_view key) { return (long long)value_of(doc, key).number; }

// A decimal string "0.09" as whole hundredths (9), exactly; the table must hold a whole percentage.
long long hundredths(const json::Value& v) {
    const std::string& s = v.text;
    const auto dot = s.find('.');
    const std::string whole = s.substr(0, dot), frac = dot == std::string::npos ? "" : s.substr(dot + 1);
    if (frac.size() > 2 && frac.find_first_not_of('0', 2) != std::string::npos)
        throw Error("E_INTERNAL", "a KS threshold is not a whole percentage: " + s);
    const std::string two = (frac + "00").substr(0, 2);
    return std::stoll(whole) * 100 + std::stoll(two);
}

Params parse_params() {
    const auto rf = parse_bytes(rfet_bytes, sizeof rfet_bytes);
    const auto pl = parse_bytes(pla_bytes, sizeof pla_bytes);
    const auto im = parse_bytes(ima_bytes, sizeof ima_bytes);
    const json::Value &r = rf.value, &p = pl.value, &m = im.value;
    Params q;
    q.pla_green_spearman = real_of(p, "pla.green.spearman_above");
    q.pla_red_spearman = real_of(p, "pla.red.spearman_below");
    q.pla_green_ks_percent = hundredths(value_of(p, "pla.green.ks_below"));
    q.pla_red_ks_percent = hundredths(value_of(p, "pla.red.ks_above"));
    q.pla_window = whole_of(p, "pla.window_days");
    const json::Value& mult = value_of(p, "backtest.zone_multiplier");
    for (int e = 0; e <= 9; ++e) q.multiplier.push_back(decimal(*mult.find(std::to_string(e))));
    q.multiplier_red = decimal(*mult.find("10+"));
    q.es_confidence = real_of(m, "es.confidence");
    q.base_horizon = whole_of(m, "es.base_horizon_days");
    const json::Value& lh = value_of(m, "lh.j");
    for (std::size_t j = 0; j < 5; ++j) q.horizons[j] = (long long)lh.find(std::to_string(j + 1))->number;
    for (const auto& [name, v] : value_of(m, "lh.table").members) q.lh_table.emplace_back(name, (long long)v.number);
    for (const json::Value& v : value_of(m, "lh.specified_fx_pairs").items) q.specified_fx_pairs.push_back(v.text);
    q.imcc_rho = real_of(m, "imcc.rho");
    q.ses_rho = real_of(m, "ses.rho");
    q.rfet_min_days = whole_of(r, "rfet.min_obs_per_year");
    q.rfet_window_days = whole_of(r, "rfet.window_days");
    q.rfet_min_per_window = whole_of(r, "rfet.min_obs_per_window");
    q.rfet_alt_min_days = whole_of(r, "rfet.alt_min_obs_12m");
    q.rfet_lookback_months = whole_of(r, "rfet.lookback_months");
    for (const char* row : {"A", "B", "C", "D"}) {
        std::vector<double>& lows = q.rfet_lower[row];
        for (const json::Value& band : value_of(r, std::string("bucket.") + row).items) lows.push_back(decimal(band.items[0]));
    }
    q.rfet_d_upper = decimal(value_of(r, "bucket.D").items.back().items[1]);
    return q;
}

[[noreturn]] void fail(const char* code, const std::string& message, const std::string& field) {
    throw Error(code, message, field);
}

double pvalue(double ks, long long n) { return kolmogorov_q(ks * std::sqrt(double(n) / 2.0)); }

long long next_horizon(double x) {
    for (const long long h : params().horizons)
        if (double(h) >= x) return h;
    return params().horizons.back();
}

std::pair<std::string, std::string> split_pair(const std::string& text) {
    const auto slash = text.find('/');
    if (slash == std::string::npos) return {text, ""};
    return {text.substr(0, slash), text.substr(slash + 1)};
}

Stressed stressed_of(const Triple& t) {
    const double ratio = t.es_fc / t.es_rc;
    return {ratio, ratio < 1.0, t.es_rs * std::max(1.0, ratio)};
}

void triple_domain(const Triple& t, const std::string& path) {
    if (t.es_rs < 0.0 || t.es_fc < 0.0) fail("E_DOMAIN", "ES must be 0 or above", path);
    if (!(t.es_rc > 0.0)) fail("E_DOMAIN", "es_rc must be above 0", path + "es_rc");
}

double sum_squares(const std::vector<double>& v) {
    std::vector<double> sq;
    sq.reserve(v.size());
    for (const double x : v) sq.push_back(x * x);
    return research::fsum(sq);
}

}  // namespace

const Params& params() {
    static const Params p = parse_params();
    return p;
}

// ---- PLA (MAR32.34 to MAR32.44, KR-56, KR-305) ----

std::vector<long long> doubled_ranks(const std::vector<double>& x) {
    std::vector<std::size_t> order(x.size());
    std::iota(order.begin(), order.end(), std::size_t{0});
    std::ranges::stable_sort(order, [&](std::size_t a, std::size_t b) { return x[a] < x[b]; });
    std::vector<long long> out(x.size(), 0);
    std::size_t i = 0;
    while (i < order.size()) {
        std::size_t j = i;
        while (j + 1 < order.size() && x[order[j + 1]] == x[order[i]]) ++j;
        const auto doubled = (long long)(i + j + 2);  // ranks i+1 .. j+1, mean (i + j + 2) / 2
        for (std::size_t k = i; k <= j; ++k) out[order[k]] = doubled;
        i = j + 1;
    }
    return out;
}

double spearman(const std::vector<double>& hpl, const std::vector<double>& rtpl) {
    const auto n1 = (long long)hpl.size() + 1;
    const std::vector<long long> a = doubled_ranks(hpl), b = doubled_ranks(rtpl);
    long long sxy = 0, sxx = 0, syy = 0;  // |sum| <= n (n-1)^2 < 9.2e18 at n = 1,000,000
    for (std::size_t k = 0; k < a.size(); ++k) {
        const long long u = a[k] - n1, v = b[k] - n1;
        sxy += u * v;
        sxx += u * u;
        syy += v * v;
    }
    if (sxx == 0 || syy == 0)
        fail("E_DOMAIN", "a series is constant: its rank variance is 0", sxx == 0 ? "hpl" : "rtpl");
    return std::max(-1.0, std::min(1.0, double(sxy) / std::sqrt(double(sxx) * double(syy))));
}

long long ks_count(const std::vector<double>& hpl, const std::vector<double>& rtpl) {
    std::vector<double> h = hpl, r = rtpl;
    std::ranges::sort(h);
    std::ranges::sort(r);
    long long best = 0;
    const auto at_or_below = [](const std::vector<double>& s, double x) {
        return (long long)(std::upper_bound(s.begin(), s.end(), x) - s.begin());
    };
    for (const std::vector<double>* pooled : {&h, &r})
        for (const double x : *pooled) best = std::max(best, std::llabs(at_or_below(r, x) - at_or_below(h, x)));
    return best;
}

double kolmogorov_q(double x) {
    if (x <= 0.0) return 1.0;
    std::vector<double> terms;
    if (x < 1.0) {
        const double c = std::numbers::pi * std::numbers::pi / (8.0 * x * x);
        for (long long k = 1;; ++k) {
            const double t = std::exp(-double((2 * k - 1) * (2 * k - 1)) * c);
            if (t == 0.0) break;
            terms.push_back(t);
        }
        return std::max(0.0, 1.0 - std::sqrt(2.0 * std::numbers::pi) / x * research::fsum(terms));
    }
    for (long long k = 1;; ++k) {
        const double t = std::exp(double(-2 * k * k) * x * x);
        if (t == 0.0) break;
        terms.push_back(k % 2 == 1 ? t : -t);
    }
    return std::min(1.0, 2.0 * research::fsum(terms));
}

Pla pla(const std::vector<double>& hpl, const std::vector<double>& rtpl) {
    const auto n = (long long)hpl.size();
    if (n > max_pnl || (long long)rtpl.size() > max_pnl)
        fail("E_LIMIT", "a P&L list is above its limit of 1000000", n > max_pnl ? "hpl" : "rtpl");
    if ((long long)rtpl.size() != n) fail("E_INPUT", "hpl and rtpl differ in length", "rtpl");
    if (n < pla_min_n) fail("E_DOMAIN", "at least 3 observations are needed", "hpl");
    const Params& p = params();
    const double rs = spearman(hpl, rtpl);
    const long long d = ks_count(hpl, rtpl);
    const double ks = double(d) / double(n);
    std::string zone = "AMBER";
    if (rs > p.pla_green_spearman && 100 * d < p.pla_green_ks_percent * n) zone = "GREEN";
    else if (rs < p.pla_red_spearman || 100 * d > p.pla_red_ks_percent * n) zone = "RED";
    return {n, rs, ks, d, zone, pvalue(ks, n), n == p.pla_window};
}

double pla_ks_pvalue(double ks, long long n) {
    if (!(ks >= 0.0 && ks <= 1.0)) fail("E_DOMAIN", "ks must be in [0, 1]", "ks");
    if (n < 1) fail("E_DOMAIN", "n must be at least 1", "n");
    return pvalue(ks, n);
}

// ---- liquidity horizons (MAR33.12, KR-60, KR-306) ----

bool fx_pair_specified(const std::string& pair) {
    const auto [a, b] = split_pair(pair);
    std::set<std::set<std::string>> listed;
    std::set<std::string> partners;
    for (const std::string& s : params().specified_fx_pairs) {
        const auto [x, y] = split_pair(s);
        listed.insert({x, y});
        partners.insert(x);
        partners.insert(y);
    }
    if (listed.contains({a, b})) return true;
    return std::ranges::any_of(partners, [&](const std::string& c) {
        return listed.contains(std::set<std::string>{a, c}) && listed.contains(std::set<std::string>{b, c});
    });
}

Lh liquidity_horizon(const std::optional<std::string>& category, const std::optional<std::string>& fx_pair,
                     const std::optional<std::vector<std::pair<double, long long>>>& constituents,
                     std::optional<double> maturity_days) {
    const int given = int(category.has_value()) + int(fx_pair.has_value()) + int(constituents.has_value());
    if (given != 1) fail("E_INPUT", "give exactly one of category, fx_pair and constituents", "category");
    if (constituents) {
        if (constituents->empty()) fail("E_INPUT", "constituents is empty", "constituents");
        if ((long long)constituents->size() > max_list)
            fail("E_LIMIT", "constituents is above its limit of 100000", "constituents");
    }
    if (fx_pair) {
        const auto [a, b] = split_pair(*fx_pair);
        if (a == b) fail("E_DOMAIN", "an FX pair needs two different currencies", "fx_pair");
    }
    if (maturity_days && !(*maturity_days > 0.0)) fail("E_DOMAIN", "maturity_days must be above 0", "maturity_days");
    const Params& p = params();
    if (constituents) {
        std::vector<double> weights;
        for (std::size_t k = 0; k < constituents->size(); ++k) {
            const auto [w, h] = (*constituents)[k];
            const std::string path = "constituents/" + std::to_string(k);
            if (!(w >= 0.0)) fail("E_DOMAIN", "a constituent weight is negative", path + "/weight");
            if (std::ranges::find(p.horizons, h) == p.horizons.end())
                fail("E_DOMAIN", "a constituent n is not 10, 20, 40, 60 or 120", path + "/n");
            weights.push_back(w);
        }
        if (std::fabs(research::fsum(weights) - 1.0) > 1e-12)
            fail("E_DOMAIN", "constituent weights must sum to 1 within 1e-12", "constituents");
    }
    const auto table = [&](std::string_view name) {
        for (const auto& [key, n] : p.lh_table)
            if (key == name) return n;
        throw Error("E_INTERNAL", "liquidity horizon category missing");
    };
    Lh out{};
    if (category) {
        out.table_n = table(*category);
        out.rule = "table";
    } else if (fx_pair) {
        out.table_n = fx_pair_specified(*fx_pair) ? table("FX_specified_pairs") : table("FX_pairs");
        out.rule = "fx_pair";
    } else {
        std::vector<double> parts;
        for (const auto& [w, h] : *constituents) parts.push_back(w * double(h));
        out.table_n = next_horizon(research::fsum(parts));
        out.rule = "index";
    }
    out.n = out.table_n;
    if (maturity_days && *maturity_days < double(out.table_n)) {
        out.n = next_horizon(*maturity_days);
        out.rule += "+maturity";
    }
    return out;
}

// ---- ES, stressed ES, IMCC, SES (MAR33.4 to MAR33.17) ----

double normal_es_factor() {
    const double c = params().es_confidence;
    const double z = ppnd16(c);
    return std::exp(-z * z / 2.0) / std::sqrt(2.0 * std::numbers::pi) / (1.0 - c);
}

double es_cascade(const std::vector<double>& es_by_horizon) {
    const Params& p = params();
    std::vector<double> parts;
    long long prev = 0;
    for (std::size_t j = 0; j < p.horizons.size() && j < es_by_horizon.size(); ++j) {
        const double w = j == 0 ? 1.0 : double(p.horizons[j] - prev) / double(p.base_horizon);
        prev = p.horizons[j];
        parts.push_back(w * es_by_horizon[j] * es_by_horizon[j]);
    }
    return std::sqrt(research::fsum(parts));
}

EsLh es_lh(const std::optional<std::vector<double>>& es_t, const std::optional<std::vector<double>>& sigma,
           const std::optional<std::vector<std::vector<double>>>& pnl) {
    if (pnl)
        for (std::size_t j = 0; j < pnl->size(); ++j)
            if ((long long)(*pnl)[j].size() > max_pnl)
                fail("E_LIMIT", "a P&L list is above its limit of 1000000", "pnl/" + std::to_string(j));
    const int given = int(es_t.has_value()) + int(sigma.has_value()) + int(pnl.has_value());
    if (given != 1) fail("E_INPUT", "give exactly one of es_t, sigma and pnl", "es_t");
    const Params& p = params();
    const std::string field = es_t ? "es_t" : sigma ? "sigma" : "pnl";
    const std::size_t size = es_t ? es_t->size() : sigma ? sigma->size() : pnl->size();
    if (size != p.horizons.size()) fail("E_INPUT", field + " must have exactly five entries", field);
    EsLh out{field, {}, 0.0};
    if (!pnl) {
        out.es_by_horizon = es_t ? *es_t : *sigma;
        for (std::size_t j = 0; j < out.es_by_horizon.size(); ++j)
            if (out.es_by_horizon[j] < 0.0)
                fail("E_DOMAIN", field + " entries must be 0 or above", field + "/" + std::to_string(j));
        if (sigma) {
            const double f = normal_es_factor();
            for (double& s : out.es_by_horizon) s = f * s;
        }
    } else {
        for (std::size_t j = 0; j < pnl->size(); ++j) {
            const std::vector<double>& list = (*pnl)[j];
            const double v = list.empty() ? 0.0 : var_historical(list, p.es_confidence).es;
            if (v < 0.0)  // KR-307
                fail("E_DOMAIN", "the ES of a P&L list is negative (its tail is a gain)", "pnl/" + std::to_string(j));
            out.es_by_horizon.push_back(v);
        }
    }
    out.es = es_cascade(out.es_by_horizon);
    return out;
}

Stressed es_stressed(const Triple& t) {
    triple_domain(t, "");
    return stressed_of(t);
}

Imcc imcc(const Triple& portfolio, const std::map<std::string, Triple>& classes) {
    if (classes.empty()) fail("E_INPUT", "classes is empty", "classes");
    triple_domain(portfolio, "portfolio.");
    for (const char* c : imcc_classes)
        if (const auto it = classes.find(c); it != classes.end()) triple_domain(it->second, std::string("classes.") + c + ".");
    const Stressed whole = stressed_of(portfolio);
    Imcc out{whole.es, whole.ratio_floored, {}, {}, 0.0};
    std::vector<double> parts;
    for (const char* c : imcc_classes)
        if (const auto it = classes.find(c); it != classes.end()) {
            const Stressed s = stressed_of(it->second);
            out.classes.emplace_back(c, s.es);
            if (s.ratio_floored) out.classes_floored.emplace_back(c);
            parts.push_back(s.es);
        }
    const double rho = params().imcc_rho;
    out.imcc = rho * whole.es + (1.0 - rho) * research::fsum(parts);
    return out;
}

Ses ses(const std::vector<double>& idio_credit, const std::vector<double>& idio_equity, const std::vector<double>& other) {
    const std::array<std::pair<const char*, const std::vector<double>*>, 3> lists = {
        {{"idio_credit", &idio_credit}, {"idio_equity", &idio_equity}, {"other", &other}}};
    for (const auto& [name, list] : lists)
        if ((long long)list->size() > max_list) fail("E_LIMIT", std::string(name) + " is above its limit of 100000", name);
    for (const auto& [name, list] : lists)
        for (std::size_t k = 0; k < list->size(); ++k)
            if ((*list)[k] < 0.0)
                fail("E_DOMAIN", "a stress scenario charge is negative", std::string(name) + "/" + std::to_string(k));
    const double rho = params().ses_rho;
    const double a = std::sqrt(sum_squares(idio_credit));
    const double b = std::sqrt(sum_squares(idio_equity));
    const double s = rho * research::fsum(other);
    const double c = std::sqrt(s * s + (1.0 - rho * rho) * sum_squares(other));
    return {a, b, c, a + b + c};
}

// ---- capital (MAR33.41 to MAR33.45, KR-61, KR-308) ----

double multiplier(long long exceptions) {
    const Params& p = params();
    return exceptions < (long long)p.multiplier.size() ? p.multiplier[std::size_t(exceptions)] : p.multiplier_red;
}

Capital capital(const CapitalInput& in) {
    if ((long long)in.desks.size() > max_list) fail("E_LIMIT", "desks is above its limit of 100000", "desks");
    const std::array<std::pair<const char*, double>, 8> named = {{{"imcc_prev", in.imcc_prev},
                                                                  {"ses_prev", in.ses_prev},
                                                                  {"imcc_avg", in.imcc_avg},
                                                                  {"ses_avg", in.ses_avg},
                                                                  {"drc", in.drc},
                                                                  {"c_u", in.c_u},
                                                                  {"sa_all", in.sa_all},
                                                                  {"qualitative_addon", in.qualitative_addon}}};
    for (const auto& [name, v] : named)
        if (v < 0.0) fail("E_DOMAIN", std::string(name) + " must be 0 or above", name);  // KR-308
    if (in.exceptions < 0) fail("E_DOMAIN", "exceptions must be 0 or above", "exceptions");
    for (std::size_t j = 0; j < in.desks.size(); ++j)
        if (in.desks[j].second < 0.0) fail("E_DOMAIN", "a desk SA must be 0 or above", "desks/" + std::to_string(j) + "/sa");
    std::vector<double> all, amber_parts;
    bool has_amber = false;
    for (const auto& [zone, sa] : in.desks) {
        all.push_back(sa);
        if (zone == "AMBER") {
            amber_parts.push_back(sa);
            has_amber = true;
        }
    }
    const double sa_ga = research::fsum(all), amber = research::fsum(amber_parts);
    if (has_amber && sa_ga == 0.0)
        fail("E_DOMAIN", "SA over the green and amber desks is 0 with an amber desk", "desks");
    Capital out{};
    out.m_c = multiplier(in.exceptions) + in.qualitative_addon;
    out.c_a = std::max(in.imcc_prev + in.ses_prev, out.m_c * in.imcc_avg + in.ses_avg);
    out.ima_ga = out.c_a + in.drc;
    out.sa_ga = sa_ga;
    out.k = has_amber ? surcharge_factor * amber / sa_ga : 0.0;
    out.surcharge = out.k * std::max(0.0, sa_ga - out.ima_ga);
    out.acr_total = std::min(out.ima_ga + out.surcharge + in.c_u, in.sa_all) + std::max(0.0, out.ima_ga - sa_ga);
    return out;
}

// ---- RFET (MAR31.12 to MAR31.16, KR-59) ----

Date months_back(Date d, int months) {
    const int total = year_of(d) * 12 + int(month_of(d)) - 1 - months;
    const int y = total >= 0 ? total / 12 : -((-total + 11) / 12);
    const auto m = unsigned(total - y * 12 + 1);
    const unsigned last = day_of(last_of_month(y, m));
    return make_date(y, m, std::min(day_of(d), last));
}

Rfet rfet(Date as_of, const std::vector<Date>& observations) {
    if ((long long)observations.size() > max_list)
        fail("E_LIMIT", "observations is above its limit of 100000", "observations");
    const Params& p = params();
    const Date start = months_back(as_of, int(p.rfet_lookback_months)) + std::chrono::days(1);
    std::set<Date> in_range;
    for (const Date d : observations)
        if (start <= d && d <= as_of) in_range.insert(d);
    const std::vector<Date> days(in_range.begin(), in_range.end());
    Rfet out{};
    out.window_start = start;
    out.distinct_days = (long long)days.size();
    const Date last = as_of - std::chrono::days(p.rfet_window_days - 1);
    for (Date s = start; s <= last; s += std::chrono::days(1)) {
        const Date end = s + std::chrono::days(p.rfet_window_days - 1);
        const auto count = (long long)(std::upper_bound(days.begin(), days.end(), end) -
                                       std::lower_bound(days.begin(), days.end(), s));
        out.min_window_count = out.min_window_count ? std::min(*out.min_window_count, count) : count;
        if (!out.first_failing_window_start && count < p.rfet_min_per_window) {
            out.first_failing_window_start = s;
            out.first_failing_window_count = count;
        }
    }
    out.crit1 = out.distinct_days >= p.rfet_min_days && !out.first_failing_window_start;
    out.crit2 = out.distinct_days >= p.rfet_alt_min_days;
    out.pass = out.crit1 || out.crit2;
    return out;
}

RfetBucket rfet_bucket(const std::string& row, std::optional<double> t, std::optional<double> delta) {
    const bool d_row = row == "D";
    const std::string field = d_row ? "delta" : "t";
    const std::optional<double>& wanted = d_row ? delta : t;
    const std::optional<double>& other = d_row ? t : delta;
    if (!wanted || other) fail("E_INPUT", "row " + row + " takes " + field + " and nothing else", field);
    const double value = *wanted;
    if (value < 0.0) fail("E_DOMAIN", field + " must be 0 or above", field);
    const Params& p = params();
    if (d_row && !(value < p.rfet_d_upper)) fail("E_DOMAIN", "delta must be below 1", "delta");
    const std::vector<double>& lows = p.rfet_lower.at(row);
    const auto b = std::size_t(std::upper_bound(lows.begin(), lows.end(), value) - lows.begin());
    RfetBucket out{(long long)b, lows[b - 1], std::nullopt};
    if (b < lows.size()) out.upper = lows[b];
    else if (d_row) out.upper = p.rfet_d_upper;
    return out;
}

}  // namespace quantforge::frtb_ima
