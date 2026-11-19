// Stage K wave 1b: SA-CCR (K-8d, 06-risk/sa-ccr.md) and FRTB IMA backtesting (K-8e, 06-risk/frtb-ima-backtest.md).
// Included by dispatch.cpp inside its anonymous namespace once the coordinator registers it
// (program/STAGE_K_W1B_PORTS_HANDOVER.md); needs quantforge/core/saccr.hpp and frtb_backtest.hpp included above.
// Every input is read (E_SCHEMA, enum values included) before in.ready() (E_LIMIT, then the finite rule); the core
// then checks structure (E_INPUT) before domain (E_DOMAIN): the HR-122 order.
#pragma once

constexpr EnumTable<string_view> k_w1b_classes = {
    {"IR", "IR"}, {"FX", "FX"}, {"CREDIT", "CREDIT"}, {"EQUITY", "EQUITY"}, {"COMMODITY", "COMMODITY"}};
constexpr EnumTable<string_view> k_w1b_kinds = {{"LINEAR", "LINEAR"}, {"OPTION", "OPTION"}, {"CDO", "CDO"}};
constexpr EnumTable<string_view> k_w1b_positions = {
    {"LONG", "LONG"}, {"SHORT", "SHORT"}, {"BOUGHT", "BOUGHT"}, {"SOLD", "SOLD"}};
constexpr EnumTable<string_view> k_w1b_treatments = {
    {"NORMAL", "NORMAL"}, {"BASIS", "BASIS"}, {"VOLATILITY", "VOLATILITY"}};
constexpr EnumTable<string_view> k_w1b_option_types = {{"CALL", "CALL"}, {"PUT", "PUT"}};
constexpr EnumTable<string_view> k_w1b_subclasses = {
    {"AAA", "AAA"},         {"AA", "AA"},         {"A", "A"},
    {"BBB", "BBB"},         {"BB", "BB"},         {"B", "B"},
    {"CCC", "CCC"},         {"IG", "IG"},         {"SG", "SG"},
    {"SINGLE", "SINGLE"},   {"INDEX", "INDEX"},   {"ELECTRICITY", "ELECTRICITY"},
    {"OIL_GAS", "OIL_GAS"}, {"METALS", "METALS"}, {"AGRICULTURAL", "AGRICULTURAL"},
    {"OTHER", "OTHER"}};

std::optional<string> k_w1b_opt_choice(const In& r, string_view k, EnumTable<string_view> table) {
    if (!r.find(k)) return std::nullopt;
    return string(r.choice(k, table));
}

std::optional<string> k_w1b_opt_text(const In& r, string_view k) {
    if (!r.find(k)) return std::nullopt;
    return r.text(k);
}

std::optional<double> k_w1b_opt_real(const In& r, string_view k) {
    if (!r.find(k)) return std::nullopt;
    return r.real(k);
}

saccr::Trade k_w1b_trade(const In& r) {
    saccr::Trade t;
    t.id = r.text("id");
    t.asset_class = string(r.choice("asset_class", k_w1b_classes));
    t.notional = r.real("notional");
    t.market_value = r.real("market_value");
    t.maturity = r.real("maturity");
    t.kind = k_w1b_opt_choice(r, "kind", k_w1b_kinds).value_or("LINEAR");
    t.position = string(r.choice("position", k_w1b_positions));
    t.treatment = k_w1b_opt_choice(r, "treatment", k_w1b_treatments).value_or("NORMAL");
    t.start = k_w1b_opt_real(r, "start");
    t.end = k_w1b_opt_real(r, "end");
    t.hedging_set = k_w1b_opt_text(r, "hedging_set");
    t.entity = k_w1b_opt_text(r, "entity");
    t.subclass = k_w1b_opt_choice(r, "subclass", k_w1b_subclasses);
    t.option_type = k_w1b_opt_choice(r, "option_type", k_w1b_option_types);
    t.underlying_price = k_w1b_opt_real(r, "underlying_price");
    t.strike = k_w1b_opt_real(r, "strike");
    t.exercise = k_w1b_opt_real(r, "exercise");
    t.shift = r.real("shift", 0.0);
    t.attachment = k_w1b_opt_real(r, "attachment");
    t.detachment = k_w1b_opt_real(r, "detachment");
    return t;
}

void k_w1b_saccr_outputs(const saccr::Result& s, Out& out) {
    out.key_real("ead", s.ead);
    out.key_real("rc", s.rc);
    out.key_real("pfe", s.pfe);
    out.key_real("multiplier", s.multiplier);
    out.key_real("addon_aggregate", s.addon_aggregate);
    out.values.key("addon");
    out.values.begin_object();
    for (std::size_t i = 0; i < saccr::classes.size(); ++i) out.key_real(saccr::classes[i], s.addon[i]);
    out.values.end_object();
    out.key_real("v", s.v);
    out.key_real("c", s.c);
    out.values.key("margined");
    out.values.boolean(s.margined);
    out.values.key("mpor_days");
    if (s.mpor_days) out.values.integer(*s.mpor_days);
    else out.values.null();
    out.key_maybe("ead_unmargined", s.ead_unmargined);
    out.values.key("capped");
    out.values.boolean(s.capped);
    out.values.key("hedging_sets");
    out.values.begin_array();
    for (const saccr::HedgingSet& h : s.hedging_sets) {
        out.values.begin_object();
        out.key_string("asset_class", h.asset_class);
        out.key_string("treatment", h.treatment);
        out.key_string("key", h.key);
        out.key_real("addon", h.addon);
        out.values.end_object();
    }
    out.values.end_array();
    out.values.key("trades");
    out.values.begin_array();
    for (const saccr::TradeRow& t : s.trades) {
        out.values.begin_object();
        out.key_string("id", t.id);
        out.key_maybe("supervisory_duration", t.supervisory_duration);
        out.key_real("adjusted_notional", t.adjusted_notional);
        out.key_real("maturity_factor", t.maturity_factor);
        out.key_real("delta", t.delta);
        out.key_real("effective_notional", t.effective_notional);
        out.key_real("supervisory_factor", t.supervisory_factor);
        out.values.end_object();
    }
    out.values.end_array();
}

void op_saccr_ead(const In& in, Out& out) {
    const auto trades = rows_of<saccr::Trade>(in, "trades", k_w1b_trade);
    std::optional<saccr::Margin> margin;
    if (in.find("margin")) {
        const Value& mv = in.need("margin");
        if (mv.kind != Kind::Object) schema("margin", "expected an object");
        const In m(mv);
        saccr::Margin g;
        g.threshold = m.real("threshold");
        g.mta = m.real("mta");
        g.nica = m.real("nica");
        g.remargin_days = m.integer("remargin_days");
        if (m.find("mpor_days")) g.mpor_days = m.integer("mpor_days");
        g.illiquid = m.boolean("illiquid", false);
        g.disputes = m.boolean("disputes", false);
        margin = g;
    }
    const double collateral = in.real("collateral", 0.0);
    const bool ir_offset = in.boolean("ir_offset", true);
    in.ready();
    k_w1b_saccr_outputs(saccr::ead(trades, collateral, margin, ir_offset), out);
}

void op_frtb_backtest_zone(const In& in, Out& out) {
    const long long n = in.integer("observations");
    const long long a = in.integer("exceptions_actual");
    const long long h = in.integer("exceptions_hypothetical");
    in.ready();
    limit_if(n > 1000000, "observations");  // ruling KR-46, as J-W3-17
    const frtb_backtest::Zone z = frtb_backtest::zone(n, a, h);
    out.values.key("exceptions");
    out.values.integer(z.exceptions);
    out.key_real("cumulative_probability", z.cumulative_probability);
    out.key_string("zone", z.zone);
    out.values.key("amber_from");
    out.values.integer(z.amber_from);
    out.values.key("red_from");
    out.values.integer(z.red_from);
    out.key_maybe("multiplier", z.multiplier);
}

void op_frtb_backtest_desk(const In& in, Out& out) {
    const long long n = in.integer("observations");
    const std::array<long long, 4> counts = {in.integer("exceptions_99_actual"), in.integer("exceptions_99_hypothetical"),
                                             in.integer("exceptions_975_actual"),
                                             in.integer("exceptions_975_hypothetical")};
    in.ready();
    limit_if(n > 1000000, "observations");  // ruling KR-46
    const frtb_backtest::Desk d = frtb_backtest::desk(n, counts);
    out.values.key("exceptions_99");
    out.values.integer(d.exceptions_99);
    out.values.key("exceptions_975");
    out.values.integer(d.exceptions_975);
    out.key_real("cumulative_probability_99", d.cumulative_probability_99);
    out.key_real("cumulative_probability_975", d.cumulative_probability_975);
    out.values.key("breach_99");
    out.values.boolean(d.breach_99);
    out.values.key("breach_975");
    out.values.boolean(d.breach_975);
    out.values.key("eligible");
    out.values.boolean(d.eligible);
}

void k_w1b_integers(Out& out, string_view k, const std::vector<long long>& v) {
    out.values.key(k);
    out.values.begin_array();
    for (const long long x : v) out.values.integer(x);
    out.values.end_array();
}

void op_frtb_backtest_count(const In& in, Out& out) {
    const auto var = in.maybe_reals("var");
    const auto actual = in.maybe_reals("actual");
    const auto hypothetical = in.maybe_reals("hypothetical");
    in.ready();
    const frtb_backtest::Count c = frtb_backtest::count_exceptions(var, actual, hypothetical);
    out.values.key("observations");
    out.values.integer(c.observations);
    out.values.key("exceptions_actual");
    out.values.integer(c.exceptions_actual);
    out.values.key("exceptions_hypothetical");
    out.values.integer(c.exceptions_hypothetical);
    out.values.key("exceptions");
    out.values.integer(c.exceptions);
    k_w1b_integers(out, "days_actual", c.days_actual);
    k_w1b_integers(out, "days_hypothetical", c.days_hypothetical);
}

constexpr Entry k_w1b_ops[] = {
    {"risk.frtb.backtest.count", op_frtb_backtest_count},
    {"risk.frtb.backtest.desk", op_frtb_backtest_desk},
    {"risk.frtb.backtest.zone", op_frtb_backtest_zone},
    {"risk.saccr.ead", op_saccr_ead},
};
