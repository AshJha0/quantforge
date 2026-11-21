#include "quantforge/core/cva.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <map>
#include <set>
#include <string_view>
#include <tuple>

#include "quantforge/core/error.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/research.hpp"

namespace quantforge::cva {
namespace {

#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wc23-extensions"
#endif
constexpr unsigned char table_bytes[] = {
#embed "../../../specifications/tables/stage_k/mar50_cva.json"
};
#if defined(__clang__)
#pragma clang diagnostic pop
#endif

using json::Kind;
using json::Value;
using std::string;
using std::string_view;

// The `entries` of mar50_cva.json by key (KR-50: the JSON is the only copy).
const std::map<string, Value, std::less<>>& table() {
    static const std::map<string, Value, std::less<>> t = [] {
        const json::Parsed p = json::parse(string_view(reinterpret_cast<const char*>(table_bytes), sizeof table_bytes));
        std::map<string, Value, std::less<>> m;
        for (const Value& e : p.value.find("entries")->items) m.emplace(e.find("key")->text, *e.find("value"));
        return m;
    }();
    return t;
}

const Value& entry(string_view key) { return table().find(key)->second; }

// A decimal string (HR-12), or a cell such as "0.90 legally related": its leading number.
double dec(const Value& v) {
    if (v.kind == Kind::Number) return v.number;
    double x = 0.0;
    std::from_chars(v.text.data(), v.text.data() + v.text.size(), x);
    return x;
}

double num(string_view key) { return dec(entry(key)); }

std::vector<string> keys_of(const Value& object) {
    std::vector<string> out;
    for (const json::Member& m : object.members) out.push_back(m.first);
    return out;
}

std::vector<string> texts_of(const Value& array) {
    std::vector<string> out;
    for (const Value& v : array.items) out.push_back(v.text);
    return out;
}

[[noreturn]] void input_error(const string& message, const string& field) { throw Error("E_INPUT", message, field); }
[[noreturn]] void domain_error(const string& message, const string& field) { throw Error("E_DOMAIN", message, field); }

std::size_t index_in(const std::vector<string>& list, string_view name) {
    return std::size_t(std::find(list.begin(), list.end(), name) - list.begin());
}

double rw_of(const string& sector, const string& quality) {
    return dec(entry("ba.rw").find(sector)->items[index_in(qualities(), quality)]);
}

const char* relation_key(const string& relation) {
    if (relation == "DIRECT") return "direct";
    if (relation == "LEGAL") return "legally_related";
    return "same_sector_region";
}

// --- SA-CVA helpers ---

constexpr const char* ir_curve = "CURVE";  // KR-311

bool currency_code(const string& s) {
    return s.size() == 3 && std::all_of(s.begin(), s.end(), [](char c) { return c >= 'A' && c <= 'Z'; });
}

struct Item {
    string bucket;             // aggregation bucket
    std::vector<string> key;   // risk factor within that bucket
    double rw = 0.0;
    const Sensitivity* s = nullptr;
};

// Bucket order (frtb.bucket_key): by length, then text.
bool bucket_less(const string& a, const string& b) {
    return a.size() != b.size() ? a.size() < b.size() : a < b;
}

double upper(const Value& table_rows, std::size_t a, std::size_t b) {
    return dec(table_rows.items[std::min(a, b)].items[std::max(a, b)]);
}

double ir_rho(const string& a, const string& b) {
    const std::vector<string> tenors = texts_of(entry("ir.tenors_specified"));
    const std::size_t i = index_in(tenors, a), j = index_in(tenors, b);
    return dec(*entry("ir.rho_specified").find(tenors[std::min(i, j)])->find(tenors[std::max(i, j)]));
}

double ccs_rho(const string& bucket, const CreditFactor& f, const CreditFactor& g) {
    const Value& spec = entry("ccs.rho");
    double name;
    const Value* p;
    if (bucket == "8") {
        p = spec.find("bucket_8");
        if (f.index == g.index && f.series == g.series) name = dec(p->find("name")->items[0]);
        else if (f.index == g.index) name = dec(p->find("name")->items[1]);
        else name = dec(p->find("name")->items[2]);
    } else {
        p = spec.find("buckets_1_7");
        if (f.name == g.name) name = dec(p->find("name")->items[0]);
        else if (f.legal_group && f.legal_group == g.legal_group) name = dec(p->find("name")->items[1]);
        else name = dec(p->find("name")->items[2]);
    }
    const double tenor = dec(p->find("tenor")->items[f.tenor == g.tenor ? 0 : 1]);
    const double quality = dec(p->find("quality")->items[f.quality == g.quality ? 0 : 1]);
    return tenor * name * quality;
}

std::size_t rcs_row(int b) { return std::size_t(b <= 7 ? b - 1 : b - 8); }

double gamma_of(const string& cls, const string& b, const string& c) {
    if (cls == "IR") return num("ir.gamma");
    if (cls == "FX") return num("fx.gamma");
    const int x = std::stoi(b), y = std::stoi(c);
    if (cls == "CCS") return upper(entry("ccs.gamma"), std::size_t(x - 1), std::size_t(y - 1));
    if (cls == "RCS") {
        double g = upper(entry("rcs.gamma_same_quality"), rcs_row(x), rcs_row(y));
        if (x <= 14 && y <= 14 && (x <= 7) != (y <= 7)) g /= num("rcs.gamma_cross_quality_divisor");  // MAR50.67(2)
        return g;
    }
    if (cls == "EQ") {  // MAR50.71
        const Value& g = entry("eq.gamma");
        if (x == 11 || y == 11) return dec(*g.find("with_11"));
        if (x <= 10 && y <= 10) return dec(*g.find("within_1_10"));
        if (std::min(x, y) == 12 && std::max(x, y) == 13) return dec(*g.find("12_13"));
        return dec(*g.find("12_or_13_with_1_10"));
    }
    const Value& g = entry("com.gamma");  // MAR50.75
    return dec(*g.find(x == 11 || y == 11 ? "with_11" : "within_1_10"));
}

double rho_of(const string& cls, const string& kind, const string& bucket, const Item& a, const Item& b) {
    if (cls == "IR" && kind == "VEGA") return num("ir.vega_rho");
    if (cls == "IR") {
        if (a.key[0] == ir_curve || b.key[0] == ir_curve) return num("ir.rho_other_ccy_curve_inflation");
        return ir_rho(a.key[0], b.key[0]);
    }
    if (cls == "CCS") return ccs_rho(bucket, *a.s->credit, *b.s->credit);
    return 1.0;  // one factor per bucket: never called with two entries
}

int numbered_count(const string& cls) {
    if (cls == "RCS") return int(entry("rcs.rw").members.size());
    if (cls == "EQ") return int(entry("eq.rw").members.size());
    return int(entry("com.rw").members.size());
}

string lower(string s) {
    for (char& c : s) c = char(c - 'A' + 'a');
    return s;
}

bool eq_large_cap(int b) { return (b >= 1 && b <= 8) || b == 12; }  // KR-315

Item make_item(const string& cls, const string& kind, const Sensitivity& s, const std::set<string>& specified,
               const string& rep) {
    const string& b = s.bucket;
    if (cls == "IR" || cls == "FX") {
        if (!currency_code(b)) input_error(cls + " bucket " + b + " is not a currency code", "bucket");
        if (cls == "FX") {
            if (b == rep) input_error("the reporting currency is not an FX bucket (MAR50.59)", "bucket");
            return {b, {}, num(kind == "DELTA" ? "fx.delta_rw" : "fx.vega_rw"), &s};
        }
        const string& f = s.factor;
        if (kind == "VEGA") return {b, {f}, num("ir.vega_rw"), &s};
        if (specified.contains(b)) {
            if (f == ir_curve) input_error(b + " is a specified currency: tenor factors (MAR50.56)", "factor");
            return {b, {f}, dec(*entry("ir.rw_specified").find(f)), &s};
        }
        if (f != ir_curve && f != "inflation") input_error(b + " is not a specified currency: CURVE and inflation", "factor");
        return {b, {f}, num("ir.rw_other_ccy"), &s};
    }
    if (cls == "CCS") {
        const Value& table_rw = entry("ccs.rw");
        const Value* row = table_rw.find(b);
        if (!row) input_error("CCS bucket " + b + " is not listed", "bucket");
        const CreditFactor& f = *s.credit;
        const double w = dec(row->items[index_in(qualities(), f.quality)]);
        const string agg = (b == "1a" || b == "1b") ? string("1") : b;  // KR-312
        if (b == "8") {
            if (!f.index || !f.series) input_error("bucket 8 factors need index and series (KR-63)", "index");
            return {agg, {*f.index, *f.series, f.tenor}, w, &s};
        }
        return {agg, {f.name, f.tenor}, w, &s};
    }
    const int n = numbered_count(cls);
    bool ok = false;
    for (int k = 1; k <= n && !ok; ++k) ok = b == std::to_string(k);
    if (!ok) input_error(cls + " bucket " + b + " is not listed", "bucket");
    double w;
    if (kind == "DELTA") w = dec(*entry(lower(cls) + ".rw").find(b));
    else if (cls == "EQ") w = dec(*entry("eq.vega_rw").find(eq_large_cap(std::stoi(b)) ? "large_cap" : "other"));
    else w = num(lower(cls) + ".vega_rw");
    return {b, {}, w, &s};
}

// KR-314: a CCS name (bucket 8: an index series) has one quality and one legal group.
void check_names(const std::vector<Item>& items) {
    std::map<std::pair<string, std::vector<std::optional<string>>>, std::pair<string, std::optional<string>>> seen;
    for (const Item& e : items) {
        const CreditFactor& f = *e.s->credit;
        std::vector<std::optional<string>> who;
        if (e.bucket == "8") who = {f.index, f.series};
        else who = {f.name};
        const std::pair<string, std::optional<string>> attrs{f.quality, f.legal_group};
        const auto [it, fresh] = seen.emplace(std::make_pair(e.bucket, who), attrs);
        if (!fresh && it->second != attrs) input_error("name " + f.name + " has two qualities or legal groups", "factor");
    }
}

ClassResult class_capital(const string& key, const string& cls, const string& kind, const std::vector<Item>& items,
                          double m_cva) {
    std::vector<string> order;
    std::map<string, std::vector<const Item*>> by_bucket;
    for (const Item& e : items) {
        auto& v = by_bucket[e.bucket];
        if (v.empty()) order.push_back(e.bucket);
        v.push_back(&e);
    }
    std::stable_sort(order.begin(), order.end(), bucket_less);
    const double r_hedge = num("sa.R");
    ClassResult out{key, {}, 0.0};
    std::vector<double> ks, sb;
    for (const string& name : order) {
        const auto& members = by_bucket[name];
        std::vector<double> ws, wsh, squares, hedge_squares;
        for (const Item* e : members) {
            ws.push_back(e->rw * e->s->s_cva - e->rw * e->s->s_hdg);  // MAR50.51-50.52
            wsh.push_back(e->rw * e->s->s_hdg);
        }
        for (const double w : ws) squares.push_back(w * w);
        for (const double h : wsh) hedge_squares.push_back(h * h);
        double radicand = py_sum(squares);  // frtb.bucket_radicand
        for (std::size_t i = 0; i < members.size(); ++i)
            for (std::size_t j = 0; j < members.size(); ++j)
                if (i != j) radicand += rho_of(cls, kind, name, *members[i], *members[j]) * ws[i] * ws[j];
        radicand = radicand + r_hedge * py_sum(hedge_squares);
        const double k_b = std::sqrt(radicand > 0.0 ? radicand : 0.0);  // KR-62
        const double total = py_sum(ws);
        const double low = k_b < total ? k_b : total;
        const double s_b = low > -k_b ? low : -k_b;  // MAR50.53(3)
        ks.push_back(k_b);
        sb.push_back(s_b);
        out.buckets.push_back({name, k_b, s_b, total, radicand < 0.0});
    }
    std::vector<double> k_squares;
    for (const double k : ks) k_squares.push_back(k * k);
    double cross = py_sum(k_squares);  // frtb.cross_radicand
    for (std::size_t b = 0; b < sb.size(); ++b)
        for (std::size_t c = 0; c < sb.size(); ++c)
            if (b != c) cross += gamma_of(cls, order[b], order[c]) * sb[b] * sb[c];
    out.k = m_cva * std::sqrt(cross > 0.0 ? cross : 0.0);
    return out;
}

}  // namespace

const std::vector<string>& sectors() {
    static const std::vector<string> v = keys_of(entry("ba.rw"));
    return v;
}
const std::vector<string>& qualities() {
    static const std::vector<string> v = {"IG", "HY_NR"};
    return v;
}
const std::vector<string>& versions() {
    static const std::vector<string> v = {"REDUCED", "FULL"};
    return v;
}
const std::vector<string>& relations() {
    static const std::vector<string> v = {"DIRECT", "LEGAL", "SECTOR_REGION"};
    return v;
}
const std::vector<string>& ccs_tenors() {
    static const std::vector<string> v = texts_of(entry("ccs.tenors"));
    return v;
}
const std::vector<string>& ir_delta_factors() {
    static const std::vector<string> v = [] {
        std::vector<string> out = texts_of(entry("ir.tenors_specified"));
        out.emplace_back(ir_curve);
        return out;
    }();
    return v;
}
const std::vector<string>& ir_vega_factors() {
    static const std::vector<string> v = {"IR_VOL", "INFLATION_VOL"};
    return v;
}
const std::vector<string>& class_keys() {
    static const std::vector<string> v = {"IR.DELTA",  "IR.VEGA",  "FX.DELTA", "FX.VEGA", "CCS.DELTA", "CCS.VEGA",
                                          "RCS.DELTA", "RCS.VEGA", "EQ.DELTA", "EQ.VEGA", "COM.DELTA", "COM.VEGA"};
    return v;
}

double py_sum(const std::vector<double>& v) {
    double f = 0.0, c = 0.0;
    for (const double x : v) {
        const double t = f + x;
        if (std::fabs(f) >= std::fabs(x)) c += (f - t) + x;
        else c += (x - t) + f;
        f = t;
    }
    if (c != 0.0 && std::isfinite(c)) f += c;
    return f;
}

double discount_factor(double m, bool imm) {
    if (!(m > 0)) domain_error("m must be positive", "m");
    if (imm) return 1.0;
    const double x = num("ba.df_rate") * m;
    return -std::expm1(-x) / x;
}

BaResult ba_cva(const std::vector<Counterparty>& counterparties, const string& version,
                const std::vector<SingleNameHedge>& single_name_hedges, const std::vector<IndexHedge>& index_hedges) {
    // Structure (E_INPUT), all before any domain check (KR-67).
    std::map<string, std::size_t> position;
    for (std::size_t n = 0; n < counterparties.size(); ++n)
        if (!position.emplace(counterparties[n].id, n).second)
            input_error("counterparty " + counterparties[n].id + " appears twice", "id");  // KR-312
    if (version == "REDUCED" && (!single_name_hedges.empty() || !index_hedges.empty()))
        input_error("hedges are recognised only in the FULL version", "single_name_hedges");
    for (const SingleNameHedge& h : single_name_hedges)
        if (!position.contains(h.counterparty))
            input_error("hedge references unknown counterparty " + h.counterparty, "counterparty");
    // Domain (E_DOMAIN).
    for (const Counterparty& c : counterparties)
        for (const NettingSet& ns : c.netting_sets) {
            if (ns.ead < 0) domain_error("counterparty " + c.id + ": ead must not be negative", "ead");
            if (!(ns.m > 0)) domain_error("counterparty " + c.id + ": m must be positive", "m");
        }
    for (const SingleNameHedge& h : single_name_hedges) {
        if (!(h.m > 0)) domain_error("hedge m must be positive", "m");
        if (h.notional < 0) domain_error("hedge notional must not be negative", "notional");
    }
    for (const IndexHedge& ih : index_hedges) {
        if (!(ih.m > 0)) domain_error("index hedge m must be positive", "m");
        if (ih.notional < 0) domain_error("index hedge notional must not be negative", "notional");
        std::vector<double> weights;
        for (const Constituent& k : ih.constituents) {
            if (k.weight < 0) domain_error("index weights must not be negative", "weight");  // KR-313
            weights.push_back(k.weight);
        }
        if (!(std::fabs(research::fsum(weights) - 1.0) <= 1e-12))
            domain_error("index weights must sum to 1 within 1e-12", "weight");
    }

    const double rho_ba = num("ba.rho"), alpha = num("ba.alpha"), beta = num("ba.beta"), ds = num("ba.ds");
    BaResult out;
    out.version = version;
    std::vector<double> scva;
    for (const Counterparty& c : counterparties) {
        CounterpartyRow row{c.id, 0.0, std::nullopt, std::nullopt, {}};
        std::vector<double> terms;
        for (const NettingSet& ns : c.netting_sets) {
            const double df = discount_factor(ns.m, ns.imm);
            row.dfs.push_back(df);
            terms.push_back(ns.m * ns.ead * df);
        }
        row.scva = rw_of(c.sector, c.quality) * research::fsum(terms) / alpha;  // MAR50.15
        scva.push_back(row.scva);
        out.counterparties.push_back(std::move(row));
    }
    std::vector<double> scva_squares;
    for (const double s : scva) scva_squares.push_back(s * s);
    const double systematic = rho_ba * research::fsum(scva);
    out.k_reduced = std::sqrt(systematic * systematic + (1.0 - rho_ba * rho_ba) * research::fsum(scva_squares));  // MAR50.14
    if (version == "FULL") {
        std::vector<std::vector<double>> snh_parts(counterparties.size()), hma_parts(counterparties.size());
        for (const SingleNameHedge& h : single_name_hedges) {
            const double r = dec(*entry("ba.r_hc").find(relation_key(h.relation)));
            const double x = rw_of(h.sector, h.quality) * h.m * h.notional * discount_factor(h.m);
            const std::size_t p = position.at(h.counterparty);
            snh_parts[p].push_back(r * x);                    // MAR50.23
            hma_parts[p].push_back((1.0 - r * r) * x * x);    // MAR50.25
        }
        const double scalar = num("ba.index_rw_scalar");
        std::vector<double> ih_terms;
        for (const IndexHedge& i : index_hedges) {
            std::vector<double> parts;
            for (const Constituent& k : i.constituents) parts.push_back(k.weight * rw_of(k.sector, k.quality));
            ih_terms.push_back(scalar * research::fsum(parts) * i.m * i.notional * discount_factor(i.m));  // MAR50.24
        }
        const double ih = research::fsum(ih_terms);
        std::vector<double> net, net_squares, hma;
        for (std::size_t n = 0; n < counterparties.size(); ++n) {
            const double snh = research::fsum(snh_parts[n]);
            hma.push_back(research::fsum(hma_parts[n]));
            out.counterparties[n].snh = snh;
            out.counterparties[n].hma = hma.back();
            net.push_back(scva[n] - snh);
        }
        for (const double x : net) net_squares.push_back(x * x);
        const double sys = rho_ba * research::fsum(net) - ih;
        const double k_hedged = std::sqrt(sys * sys + (1.0 - rho_ba * rho_ba) * research::fsum(net_squares) +
                                          research::fsum(hma));  // MAR50.21
        const double k_full = beta * out.k_reduced + (1.0 - beta) * k_hedged;  // MAR50.20
        out.ih = ih;
        out.k_hedged = k_hedged;
        out.k_full = k_full;
        out.capital = ds * k_full;
    } else {
        out.capital = ds * out.k_reduced;
    }
    out.rwa = num("rwa_multiplier") * out.capital;
    return out;
}

SaResult sa_cva(const std::vector<std::pair<string, std::vector<Sensitivity>>>& classes, const string& reporting_currency,
                double m_cva) {
    for (const auto& [key, items] : classes)
        if (key == "CCS.VEGA") input_error("counterparty credit spread has no vega (MAR50.45)", "classes");
    if (!currency_code(reporting_currency)) input_error("reporting_currency is not a currency code", "reporting_currency");
    std::set<string> specified;
    for (const Value& c : entry("ir.specified_currencies").items)
        specified.insert(c.text == "reporting" ? reporting_currency : c.text);
    std::vector<std::tuple<string, string, string, std::vector<Item>>> built;
    for (const string& key : class_keys()) {
        const auto it = std::find_if(classes.begin(), classes.end(), [&](const auto& p) { return p.first == key; });
        if (it == classes.end()) continue;
        const string cls = key.substr(0, key.find('.')), kind = key.substr(key.find('.') + 1);
        std::vector<Item> items;
        for (const Sensitivity& s : it->second) items.push_back(make_item(cls, kind, s, specified, reporting_currency));
        std::set<std::pair<string, std::vector<string>>> seen;
        for (const Item& e : items)
            if (!seen.emplace(e.bucket, e.key).second)
                input_error(key + ": bucket " + e.bucket + " holds one risk factor twice", "factor");
        if (cls == "CCS") check_names(items);
        built.emplace_back(key, cls, kind, std::move(items));
    }
    if (!(m_cva >= 1)) domain_error("m_cva must be at least 1 (MAR50.41)", "m_cva");
    SaResult out;
    out.m_cva = m_cva;
    std::vector<double> ks;
    for (const auto& [key, cls, kind, items] : built) {
        out.classes.push_back(class_capital(key, cls, kind, items, m_cva));
        ks.push_back(out.classes.back().k);
    }
    out.total = research::fsum(ks);
    out.rwa = num("rwa_multiplier") * out.total;
    return out;
}

}  // namespace quantforge::cva
