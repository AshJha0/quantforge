// Stage K wave 2b: CVA capital (K-8g, 06-risk/cva-capital.md) and leverage ratio and large exposures, simplified
// (K-8i, 06-risk/leverage-large-exposures.md). A port of python/quantforge_core/cli/ops_k_w2b.py; included by
// dispatch.cpp inside its anonymous namespace, after quantforge/core/cva.hpp and leverage.hpp.
// Error order KR-67 (= HR-122): every input is read first (E_SCHEMA, enum values and factor names included; CCS.VEGA
// is read as a valid key and refused by the core as E_INPUT); in.ready() then raises E_LIMIT (the general per-array
// cap, KR-317) and a non-finite input (F-2, E_DOMAIN); the core raises every structural E_INPUT before E_DOMAIN.
#pragma once

const string& cvl_enum(const In& r, string_view k, const std::vector<string>& allowed) {
    const string& s = r.text(k);
    if (std::find(allowed.begin(), allowed.end(), s) == allowed.end()) schema(k, s + " is not listed");
    return s;
}

std::optional<string> cvl_opt_text(const In& r, string_view k) {
    if (!r.find(k)) return std::nullopt;
    return r.text(k);
}

// An optional array of objects: absent (or null) means empty (KR-319).
template <class Row>
std::vector<Row> cvl_list(const In& in, string_view key, auto&& read) {
    if (!in.find(key)) return {};
    return rows_of<Row>(in, key, read);
}

void cvl_strings(Out& out, string_view k, const std::vector<string>& v) {
    out.values.key(k);
    out.values.begin_array();
    for (const string& s : v) out.values.string(s);
    out.values.end_array();
}

void cvl_bool(Out& out, string_view k, bool b) {
    out.values.key(k);
    out.values.boolean(b);
}

void op_cva_ba(const In& in, Out& out) {
    namespace cv = quantforge::cva;
    const auto cps = rows_of<cv::Counterparty>(in, "counterparties", [](const In& c) {
        cv::Counterparty x;
        x.id = c.text("id");
        x.sector = cvl_enum(c, "sector", cv::sectors());
        x.quality = cvl_enum(c, "quality", cv::qualities());
        x.netting_sets = rows_of<cv::NettingSet>(c, "netting_sets", [](const In& n) {
            return cv::NettingSet{n.real("ead"), n.real("m"), n.boolean("imm", false)};
        });
        return x;
    });
    const string version = cvl_enum(in, "version", cv::versions());
    const auto single = cvl_list<cv::SingleNameHedge>(in, "single_name_hedges", [](const In& h) {
        cv::SingleNameHedge x;
        x.counterparty = h.text("counterparty");
        x.relation = cvl_enum(h, "relation", cv::relations());
        x.sector = cvl_enum(h, "sector", cv::sectors());
        x.quality = cvl_enum(h, "quality", cv::qualities());
        x.m = h.real("m");
        x.notional = h.real("notional");
        return x;
    });
    const auto index_hedges = cvl_list<cv::IndexHedge>(in, "index_hedges", [](const In& h) {
        cv::IndexHedge x;
        x.m = h.real("m");
        x.notional = h.real("notional");
        x.constituents = rows_of<cv::Constituent>(h, "constituents", [](const In& k) {
            cv::Constituent c;
            c.sector = cvl_enum(k, "sector", cv::sectors());
            c.quality = cvl_enum(k, "quality", cv::qualities());
            c.weight = k.real("weight");
            return c;
        });
        return x;
    });
    in.ready();
    const cv::BaResult r = cv::ba_cva(cps, version, single, index_hedges);
    out.key_string("version", r.version);
    out.values.key("counterparties");
    out.values.begin_array();
    for (const cv::CounterpartyRow& c : r.counterparties) {
        out.values.begin_object();
        out.key_string("id", c.id);
        out.key_real("scva", c.scva);
        out.key_maybe("snh", c.snh);
        out.key_maybe("hma", c.hma);
        out.values.key("netting_sets");
        out.values.begin_array();
        for (const double df : c.dfs) {
            out.values.begin_object();
            out.key_real("df", df);
            out.values.end_object();
        }
        out.values.end_array();
        out.values.end_object();
    }
    out.values.end_array();
    out.key_maybe("ih", r.ih);
    out.key_real("k_reduced", r.k_reduced);
    out.key_maybe("k_hedged", r.k_hedged);
    out.key_maybe("k_full", r.k_full);
    out.key_real("capital", r.capital);
    out.key_real("rwa", r.rwa);
    out.key_string("label", cv::label);
}

quantforge::cva::Sensitivity cvl_sensitivity(const string& cls, const string& kind, const In& s) {
    namespace cv = quantforge::cva;
    cv::Sensitivity x;
    if (cls == "CCS") {
        const Value& fv = s.need("factor");
        if (fv.kind != Kind::Object) schema("factor", "expected an object");
        const In f(fv);
        cv::CreditFactor c;
        c.name = f.text("name");
        c.tenor = cvl_enum(f, "tenor", cv::ccs_tenors());
        c.quality = cvl_enum(f, "quality", cv::qualities());
        c.legal_group = cvl_opt_text(f, "legal_group");
        c.index = cvl_opt_text(f, "index");
        c.series = cvl_opt_text(f, "series");
        x.credit = c;
    } else if (cls == "IR") {
        x.factor = cvl_enum(s, "factor", kind == "DELTA" ? cv::ir_delta_factors() : cv::ir_vega_factors());
    } else {
        x.factor = s.text("factor");
    }
    x.bucket = s.text("bucket");
    x.s_cva = s.real("s_cva");
    x.s_hdg = s.real("s_hdg");
    return x;
}

void op_cva_sa(const In& in, Out& out) {
    namespace cv = quantforge::cva;
    const Value& c = in.need("classes");
    if (c.kind != Kind::Object) schema("classes", "expected an object");
    const In classes_in(c);
    std::vector<std::pair<string, std::vector<cv::Sensitivity>>> classes;
    for (const json::Member& m : c.members) {
        const string& key = m.first;
        if (std::find(cv::class_keys().begin(), cv::class_keys().end(), key) == cv::class_keys().end())
            schema("classes", key + " is not listed");
        const string cls = key.substr(0, key.find('.')), kind = key.substr(key.find('.') + 1);
        classes.emplace_back(key, rows_of<cv::Sensitivity>(classes_in, key, [&](const In& s) {
                                 return cvl_sensitivity(cls, kind, s);
                             }));
    }
    const string& reporting = in.text("reporting_currency");
    const double m_cva = in.real("m_cva", 1.0);
    in.ready();
    const cv::SaResult r = cv::sa_cva(classes, reporting, m_cva);
    out.values.key("classes");
    out.values.begin_object();
    for (const cv::ClassResult& k : r.classes) {
        out.values.key(k.key);
        out.values.begin_object();
        out.values.key("buckets");
        out.values.begin_array();
        for (const cv::BucketRow& b : k.buckets) {
            out.values.begin_object();
            out.key_string("bucket", b.bucket);
            out.key_real("k_b", b.k_b);
            out.key_real("s_b", b.s_b);
            out.key_real("sum_ws", b.sum_ws);
            cvl_bool(out, "floored", b.floored);
            out.values.end_object();
        }
        out.values.end_array();
        out.key_real("k", k.k);
        out.values.end_object();
    }
    out.values.end_object();
    out.key_real("m_cva", r.m_cva);
    out.key_real("total", r.total);
    out.key_real("rwa", r.rwa);
    out.key_string("label", cv::label);
}

void op_capital_leverage(const In& in, Out& out) {
    namespace lv = quantforge::leverage;
    const double tier1 = in.real("tier1");
    const Vec on_balance = in.find("on_balance") ? in.reals("on_balance") : Vec{};
    const auto derivatives = cvl_list<lv::DerivativeSet>(in, "derivatives", [](const In& d) {
        lv::DerivativeSet x;
        x.v = d.real("v");
        x.pfe = d.real("pfe");
        x.cvm_received = d.real("cvm_received", 0.0);
        x.cvm_provided = d.real("cvm_provided", 0.0);
        return x;
    });
    const auto written = cvl_list<lv::WrittenCreditDerivative>(in, "written_credit_derivatives", [](const In& w) {
        lv::WrittenCreditDerivative x;
        x.notional = w.real("notional");
        x.fair_value = w.real("fair_value");
        x.purchased_offset = w.real("purchased_offset", 0.0);
        return x;
    });
    const auto sfts = cvl_list<lv::Sft>(in, "sfts", [](const In& s) {
        lv::Sft x;
        x.gross_assets = s.real("gross_assets");
        x.mna = s.boolean("mna");
        x.exposures = s.reals("exposures");
        x.collateral = s.reals("collateral");
        return x;
    });
    const auto off_balance = cvl_list<lv::OffBalance>(in, "off_balance", [](const In& o) {
        lv::OffBalance x;
        x.notional = o.real("notional");
        x.ccf_category = cvl_enum(o, "ccf_category", lv::ccf_categories());
        return x;
    });
    in.ready();
    const lv::LeverageResult r = lv::leverage(tier1, on_balance, derivatives, written, sfts, off_balance);
    out.key_real("on_balance", r.on_balance);
    out.key_real("derivatives", r.derivatives);
    out.key_real("derivative_netting_sets", r.derivative_netting_sets);
    out.key_real("written_credit_derivatives", r.written_credit_derivatives);
    out.key_real("sfts", r.sfts);
    out.key_real("off_balance", r.off_balance);
    out.key_real("exposure", r.exposure);
    out.key_real("ratio", r.ratio);
    cvl_bool(out, "meets_minimum", r.meets_minimum);
    out.key_string("label", lv::leverage_label);
}

void op_capital_large_exposures(const In& in, Out& out) {
    namespace lv = quantforge::leverage;
    const double tier1 = in.real("tier1");
    const bool bank_gsib = in.boolean("bank_gsib", false);
    const auto cps = rows_of<lv::LeCounterparty>(in, "counterparties", [](const In& c) {
        lv::LeCounterparty x;
        x.id = c.text("id");
        x.group = cvl_opt_text(c, "group");
        x.gsib = c.boolean("gsib", false);
        x.exempt = c.boolean("exempt", false);
        return x;
    });
    const auto bb = cvl_list<lv::BankingBookExposure>(in, "banking_book", [](const In& b) {
        return lv::BankingBookExposure{b.text("counterparty"), b.real("value")};
    });
    const auto obs = cvl_list<lv::OffBalanceExposure>(in, "off_balance", [](const In& o) {
        return lv::OffBalanceExposure{o.text("counterparty"), o.real("notional"), o.real("ccf")};
    });
    const auto crm = cvl_list<lv::Protection>(in, "crm", [](const In& p) {
        return lv::Protection{p.text("counterparty"), p.text("provider"), p.real("protected")};
    });
    const auto tb = cvl_list<lv::TradingPosition>(in, "trading_book", [](const In& t) {
        lv::TradingPosition x;
        x.id = t.text("id");
        x.counterparty = t.text("counterparty");
        x.seniority = cvl_enum(t, "seniority", lv::seniorities());
        x.notional = t.real("notional");
        x.market_value = t.real("market_value");
        if (t.find("maturity_years")) (void)t.real("maturity_years");  // read and ignored (KR-322)
        (void)t.boolean("cash_equity", false);
        (void)t.boolean("lgd_applies", true);
        return x;
    });
    in.ready();
    const lv::LargeExposuresResult r = lv::large_exposures(tier1, cps, bb, obs, crm, tb, bank_gsib);
    out.values.key("counterparties");
    out.values.begin_array();
    for (const lv::CounterpartyRow& c : r.counterparties) {
        out.values.begin_object();
        out.key_string("id", c.id);
        out.key_real("banking_book", c.banking_book);
        out.key_real("off_balance", c.off_balance);
        out.key_real("trading_book_net_long", c.trading_book_net_long);
        out.key_real("trading_book_net_short", c.trading_book_net_short);
        out.key_real("protected", c.protected_amount);
        out.key_real("received", c.received);
        out.key_real("exposure", c.exposure);
        out.values.end_object();
    }
    out.values.end_array();
    out.values.key("groups");
    out.values.begin_array();
    for (const lv::GroupRow& g : r.groups) {
        out.values.begin_object();
        out.key_string("group", g.group);
        cvl_strings(out, "members", g.members);
        out.key_real("exposure", g.exposure);
        out.key_real("share", g.share);
        cvl_bool(out, "large", g.large);
        out.key_real("limit", g.limit);
        cvl_bool(out, "breach", g.breach);
        cvl_bool(out, "exempt", g.exempt);
        out.values.end_object();
    }
    out.values.end_array();
    cvl_strings(out, "report", r.report);
    out.key_string("label", lv::large_exposures_label);
}

constexpr Entry cva_leverage_ops[] = {
    {"risk.capital.large_exposures", op_capital_large_exposures},
    {"risk.capital.leverage", op_capital_leverage},
    {"risk.cva.ba", op_cva_ba},
    {"risk.cva.sa", op_cva_sa},
};
