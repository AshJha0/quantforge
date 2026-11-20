// Stage K wave 2: FRTB DRC and RRAO (K-8a, 06-risk/frtb-drc-rrao.md) and FRTB IMA (K-8f, 06-risk/frtb-ima.md).
// A port of python/quantforge_core/cli/ops_k_w2a.py and limits_k_w2a.py; included by dispatch.cpp inside its
// anonymous namespace, after quantforge/core/frtb_drc.hpp and frtb_ima.hpp.
// Error order KR-67 (= HR-122): every input is read first (E_SCHEMA, enum values included: bucket, seniority, rating,
// kind, liquidity horizon category, the AAA/BBB form of fx_pair, zone, row, risk-class keys); then the size limits
// (E_LIMIT: the general 100,000 per array, and for risk.frtb.pla and risk.frtb.ima.es_lh, which dispatch.cpp exempts
// from the general scan, the KR-67 sizes below); in.ready() then raises a non-finite input (F-2, E_DOMAIN); the core
// raises every structural E_INPUT before E_DOMAIN.
#pragma once

namespace drc = quantforge::frtb_drc;
namespace ima = quantforge::frtb_ima;

constexpr EnumTable<string_view> w2a_buckets = {
    {"CORPORATE", "CORPORATE"}, {"SOVEREIGN", "SOVEREIGN"}, {"LOCAL_GOV", "LOCAL_GOV"}};
constexpr EnumTable<string_view> w2a_seniorities = {
    {"COVERED", "COVERED"}, {"SENIOR", "SENIOR"}, {"NON_SENIOR", "NON_SENIOR"}, {"EQUITY", "EQUITY"}};
constexpr EnumTable<string_view> w2a_ratings = {
    {"AAA", "AAA"}, {"AA", "AA"}, {"A", "A"}, {"BBB", "BBB"}, {"BB", "BB"}, {"B", "B"},
    {"CCC", "CCC"}, {"UNRATED", "UNRATED"}, {"DEFAULTED", "DEFAULTED"}};
constexpr EnumTable<string_view> w2a_kinds = {{"EXOTIC", "EXOTIC"}, {"OTHER", "OTHER"}};
constexpr EnumTable<string_view> w2a_zones = {{"GREEN", "GREEN"}, {"AMBER", "AMBER"}};
constexpr EnumTable<string_view> w2a_rows = {{"A", "A"}, {"B", "B"}, {"C", "C"}, {"D", "D"}};

std::optional<double> w2a_opt_real(const In& r, string_view k) {
    if (!r.find(k)) return std::nullopt;
    return r.real(k);
}

In w2a_object(const In& in, string_view k) {
    const Value& v = in.need(k);
    if (v.kind != Kind::Object) schema(k, "expected an object");
    return In(v);
}

// KR-67 sizes of the two page-limited verbs, checked after every read and before the finite rule.
void w2a_cap(const In& in, string_view k, std::size_t limit) {
    const Value* v = in.find(k);
    if (v && v->kind == Kind::Array && v->items.size() > limit) limit_if(true, k);
}

void w2a_label(Out& out) { out.key_string("label", drc::label); }

void w2a_rows_out(Out& out, const std::vector<drc::PositionRow>& rows) {
    out.values.key("positions");
    out.values.begin_array();
    for (const drc::PositionRow& r : rows) {
        out.values.begin_object();
        out.key_string("id", r.id);
        if (r.gross_jtd) out.key_real("gross_jtd", *r.gross_jtd);
        out.key_real("weight", r.weight);
        out.key_real("scaled_jtd", r.scaled_jtd);
        out.values.end_object();
    }
    out.values.end_array();
}

void w2a_buckets_out(Out& out, const std::vector<drc::BucketRow>& buckets, bool with_hbr) {
    out.values.key("buckets");
    out.values.begin_array();
    for (const drc::BucketRow& b : buckets) {
        out.values.begin_object();
        out.key_string("bucket", b.bucket);
        if (with_hbr) out.key_maybe("hbr", b.hbr);
        out.key_real("wtd_long", b.wtd_long);
        out.key_real("wtd_short", b.wtd_short);
        out.key_real("drc", b.drc);
        out.values.end_object();
    }
    out.values.end_array();
}

void op_frtb_drc_nonsec(const In& in, Out& out) {
    const auto positions = rows_of<drc::Position>(in, "positions", [](const In& p) {
        drc::Position x;
        x.id = p.text("id");
        x.obligor = p.text("obligor");
        x.bucket = string(p.choice("bucket", w2a_buckets));
        x.seniority = string(p.choice("seniority", w2a_seniorities));
        x.notional = p.real("notional");
        x.market_value = p.real("market_value");
        x.maturity_years = p.real("maturity_years");
        x.cash_equity = p.boolean("cash_equity", false);
        x.lgd_applies = p.boolean("lgd_applies", true);
        return x;
    });
    const In r = w2a_object(in, "ratings");
    std::map<string, string> ratings;
    for (const auto& [name, v] : r.raw().members) ratings[name] = string(r.choice(name, w2a_ratings));
    in.ready();
    const drc::NonsecResult s = drc::drc_nonsec(positions, ratings);
    w2a_rows_out(out, s.positions);
    out.values.key("obligors");
    out.values.begin_array();
    for (const drc::ObligorRow& o : s.obligors) {
        out.values.begin_object();
        out.key_string("obligor", o.obligor);
        out.key_real("net_long", o.net_long);
        out.key_real("net_short", o.net_short);
        out.key_real("rw", o.rw);
        out.values.end_object();
    }
    out.values.end_array();
    w2a_buckets_out(out, s.buckets, true);
    out.key_real("drc", s.drc);
    w2a_label(out);
}

void op_frtb_drc_sec_nonctp(const In& in, Out& out) {
    const auto positions = rows_of<drc::SecPosition>(in, "positions", [](const In& p) {
        return drc::SecPosition{p.text("id"),          p.text("bucket"),         p.text("pool"), p.text("tranche"),
                                p.real("market_value"), p.real("maturity_years"), p.real("rw")};
    });
    in.ready();
    const drc::SecResult s = drc::drc_sec_nonctp(positions);
    w2a_rows_out(out, s.positions);
    w2a_buckets_out(out, s.buckets, true);
    out.key_real("drc", s.drc);
    w2a_label(out);
    out.key_string("rw_source", drc::rw_source);
}

void op_frtb_drc_ctp(const In& in, Out& out) {
    std::optional<std::vector<drc::CtpPosition>> positions;
    if (in.find("positions"))
        positions = rows_of<drc::CtpPosition>(in, "positions", [](const In& p) {
            return drc::CtpPosition{p.text("id"),          p.text("index"),          p.text("series"), p.text("tranche"),
                                    p.real("market_value"), p.real("maturity_years"), p.real("rw")};
        });
    std::optional<Vec> bucket_drc;
    if (in.find("bucket_drc")) bucket_drc = in.reals("bucket_drc");
    in.ready();
    const drc::CtpResult s = drc::drc_ctp(positions, bucket_drc);
    if (s.by_position) {
        w2a_rows_out(out, s.positions);
        out.key_maybe("hbr_ctp", s.hbr_ctp);
        w2a_buckets_out(out, s.buckets, false);
    }
    out.key_real("drc", s.drc);
    w2a_label(out);
    out.key_string("rw_source", drc::rw_source);
}

void op_frtb_rrao(const In& in, Out& out) {
    const auto instruments = rows_of<drc::Instrument>(in, "instruments", [](const In& x) {
        return drc::Instrument{x.text("id"), x.real("gross_notional"), string(x.choice("kind", w2a_kinds)),
                               x.boolean("listed_or_clearable"), x.boolean("back_to_back")};
    });
    in.ready();
    const drc::RraoResult s = drc::rrao(instruments);
    out.values.key("instruments");
    out.values.begin_array();
    for (const drc::RraoRow& r : s.instruments) {
        out.values.begin_object();
        out.key_string("id", r.id);
        out.key_real("weight", r.weight);
        out.values.key("excluded");
        out.values.boolean(r.excluded);
        out.key_real("addon", r.addon);
        out.values.end_object();
    }
    out.values.end_array();
    out.key_real("rrao", s.rrao);
    w2a_label(out);
}

void op_frtb_pla(const In& in, Out& out) {
    const Vec hpl = in.reals("hpl"), rtpl = in.reals("rtpl");
    w2a_cap(in, "hpl", std::size_t(ima::max_pnl));
    w2a_cap(in, "rtpl", std::size_t(ima::max_pnl));
    in.ready();
    const ima::Pla s = ima::pla(hpl, rtpl);
    out.values.key("n");
    out.values.integer(s.n);
    out.key_real("spearman", s.spearman);
    out.key_real("ks", s.ks);
    out.values.key("ks_count");
    out.values.integer(s.ks_count);
    out.key_string("zone", s.zone);
    out.key_real("ks_pvalue_asymptotic", s.ks_pvalue_asymptotic);
    out.values.key("regulatory_window");
    out.values.boolean(s.regulatory_window);
    w2a_label(out);
}

void op_frtb_pla_ks_pvalue(const In& in, Out& out) {
    const double ks = in.real("ks");
    const long long n = in.integer("n");
    in.ready();
    out.key_real("pvalue", ima::pla_ks_pvalue(ks, n));
    w2a_label(out);
}

bool w2a_fx_form(const string& s) {
    const auto upper = [](char c) { return c >= 'A' && c <= 'Z'; };
    return s.size() == 7 && s[3] == '/' && upper(s[0]) && upper(s[1]) && upper(s[2]) && upper(s[4]) && upper(s[5]) &&
           upper(s[6]);
}

void op_frtb_ima_lh(const In& in, Out& out) {
    std::optional<string> category, fx_pair;
    if (in.find("category")) {
        category = in.text("category");
        const auto& table = ima::params().lh_table;
        if (std::ranges::none_of(table, [&](const auto& e) { return e.first == *category; }))
            schema("category", "value is not listed");
    }
    if (in.find("fx_pair")) {
        fx_pair = in.text("fx_pair");
        if (!w2a_fx_form(*fx_pair)) schema("fx_pair", "not of the form AAA/BBB");
    }
    std::optional<std::vector<std::pair<double, long long>>> constituents;
    if (in.find("constituents"))
        constituents = rows_of<std::pair<double, long long>>(
            in, "constituents", [](const In& c) { return std::pair<double, long long>{c.real("weight"), c.integer("n")}; });
    const std::optional<double> maturity = w2a_opt_real(in, "maturity_days");
    in.ready();
    const ima::Lh s = ima::liquidity_horizon(category, fx_pair, constituents, maturity);
    out.values.key("n");
    out.values.integer(s.n);
    out.values.key("table_n");
    out.values.integer(s.table_n);
    out.key_string("rule", s.rule);
    w2a_label(out);
}

void op_frtb_ima_es_lh(const In& in, Out& out) {
    std::optional<Vec> es_t, sigma;
    std::optional<Matrix> pnl;
    if (in.find("es_t")) es_t = in.reals("es_t");
    if (in.find("sigma")) sigma = in.reals("sigma");
    if (in.find("pnl")) pnl = in.matrix("pnl");
    for (const string_view k : {"es_t", "sigma", "pnl"}) w2a_cap(in, k, std::size_t(ima::max_list));
    if (pnl)
        for (std::size_t k = 0; k < pnl->size(); ++k)
            limit_if((long long)(*pnl)[k].size() > ima::max_pnl, "pnl/" + std::to_string(k));
    in.ready();
    const ima::EsLh s = ima::es_lh(es_t, sigma, pnl);
    out.key_string("mode", s.mode);
    out.key_reals("es_by_horizon", s.es_by_horizon);
    out.key_real("es", s.es);
    w2a_label(out);
}

ima::Triple w2a_triple(const In& t) { return {t.real("es_rs"), t.real("es_fc"), t.real("es_rc")}; }

void op_frtb_ima_es_stressed(const In& in, Out& out) {
    const ima::Triple t = w2a_triple(in);
    in.ready();
    const ima::Stressed s = ima::es_stressed(t);
    out.key_real("ratio", s.ratio);
    out.values.key("ratio_floored");
    out.values.boolean(s.ratio_floored);
    out.key_real("es", s.es);
    w2a_label(out);
}

void op_frtb_ima_imcc(const In& in, Out& out) {
    const ima::Triple portfolio = w2a_triple(w2a_object(in, "portfolio"));
    const In c = w2a_object(in, "classes");
    for (const auto& [key, v] : c.raw().members)
        if (std::ranges::find_if(ima::imcc_classes, [&](const char* x) { return key == x; }) == ima::imcc_classes.end())
            schema("classes." + key, "not a risk class (IR, EQ, FX, COM, CS)");
    std::map<string, ima::Triple> classes;
    for (const auto& [key, v] : c.raw().members) classes[key] = w2a_triple(w2a_object(c, key));
    in.ready();
    const ima::Imcc s = ima::imcc(portfolio, classes);
    out.key_real("imcc_c", s.imcc_c);
    out.values.key("portfolio_floored");
    out.values.boolean(s.portfolio_floored);
    out.values.key("classes");
    out.values.begin_object();
    for (const auto& [key, v] : s.classes) out.key_real(key, v);
    out.values.end_object();
    out.values.key("classes_floored");
    out.values.begin_array();
    for (const string& key : s.classes_floored) out.values.string(key);
    out.values.end_array();
    out.key_real("imcc", s.imcc);
    w2a_label(out);
}

void op_frtb_ima_ses(const In& in, Out& out) {
    const Vec a = in.reals("idio_credit"), b = in.reals("idio_equity"), o = in.reals("other");
    in.ready();
    const ima::Ses s = ima::ses(a, b, o);
    out.key_real("idio_credit", s.idio_credit);
    out.key_real("idio_equity", s.idio_equity);
    out.key_real("other", s.other);
    out.key_real("ses", s.ses);
    w2a_label(out);
}

void op_frtb_ima_capital(const In& in, Out& out) {
    ima::CapitalInput c;
    c.desks = rows_of<std::pair<string, double>>(in, "desks", [](const In& d) {
        return std::pair<string, double>{string(d.choice("zone", w2a_zones)), d.real("sa")};
    });
    c.imcc_prev = in.real("imcc_prev");
    c.ses_prev = in.real("ses_prev");
    c.imcc_avg = in.real("imcc_avg");
    c.ses_avg = in.real("ses_avg");
    c.exceptions = in.integer("exceptions");
    c.drc = in.real("drc");
    c.c_u = in.real("c_u");
    c.sa_all = in.real("sa_all");
    c.qualitative_addon = in.real("qualitative_addon", 0.0);
    in.ready();
    const ima::Capital s = ima::capital(c);
    out.key_real("m_c", s.m_c);
    out.key_real("c_a", s.c_a);
    out.key_real("ima_ga", s.ima_ga);
    out.key_real("sa_ga", s.sa_ga);
    out.key_real("k", s.k);
    out.key_real("surcharge", s.surcharge);
    out.key_real("acr_total", s.acr_total);
    w2a_label(out);
}

void w2a_maybe_integer(Out& out, string_view k, const std::optional<long long>& v) {
    out.values.key(k);
    if (v) out.values.integer(*v);
    else out.values.null();
}

void op_frtb_rfet(const In& in, Out& out) {
    const Date as_of = in.date("as_of");
    const std::vector<Date> observations = dates_of(in, "observations");
    in.ready();
    const ima::Rfet s = ima::rfet(as_of, observations);
    out.key_string("window_start", format_date(s.window_start));
    out.values.key("distinct_days");
    out.values.integer(s.distinct_days);
    w2a_maybe_integer(out, "min_window_count", s.min_window_count);
    out.values.key("first_failing_window_start");
    if (s.first_failing_window_start) out.values.string(format_date(*s.first_failing_window_start));
    else out.values.null();
    w2a_maybe_integer(out, "first_failing_window_count", s.first_failing_window_count);
    out.values.key("crit1");
    out.values.boolean(s.crit1);
    out.values.key("crit2");
    out.values.boolean(s.crit2);
    out.values.key("pass");
    out.values.boolean(s.pass);
    w2a_label(out);
}

void op_frtb_rfet_bucket(const In& in, Out& out) {
    const string row(in.choice("row", w2a_rows));
    const std::optional<double> t = w2a_opt_real(in, "t"), delta = w2a_opt_real(in, "delta");
    in.ready();
    const ima::RfetBucket s = ima::rfet_bucket(row, t, delta);
    out.values.key("bucket");
    out.values.integer(s.bucket);
    out.key_real("lower", s.lower);
    out.key_maybe("upper", s.upper);
    w2a_label(out);
}

constexpr Entry frtb_drc_ima_ops[] = {
    {"risk.frtb.drc_ctp", op_frtb_drc_ctp},
    {"risk.frtb.drc_nonsec", op_frtb_drc_nonsec},
    {"risk.frtb.drc_sec_nonctp", op_frtb_drc_sec_nonctp},
    {"risk.frtb.ima.capital", op_frtb_ima_capital},
    {"risk.frtb.ima.es_lh", op_frtb_ima_es_lh},
    {"risk.frtb.ima.es_stressed", op_frtb_ima_es_stressed},
    {"risk.frtb.ima.imcc", op_frtb_ima_imcc},
    {"risk.frtb.ima.lh", op_frtb_ima_lh},
    {"risk.frtb.ima.ses", op_frtb_ima_ses},
    {"risk.frtb.pla", op_frtb_pla},
    {"risk.frtb.pla.ks_pvalue", op_frtb_pla_ks_pvalue},
    {"risk.frtb.rfet", op_frtb_rfet},
    {"risk.frtb.rfet.bucket", op_frtb_rfet_bucket},
    {"risk.frtb.rrao", op_frtb_rrao},
};
