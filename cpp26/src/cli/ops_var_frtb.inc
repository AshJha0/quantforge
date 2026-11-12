#include "quantforge/core/var_frtb.hpp"
// CLI handlers: VaR, ES, backtests and FRTB-SA GIRR delta. Included by dispatch.cpp inside its unnamed namespace.

constexpr std::size_t max_f4_scenarios = 1000000;

void put_var(Out& out, const VarResult& r) {
    out.key_real("var", r.var);
    out.key_real("es", r.es);
    out.values.key("tail_count");
    out.values.integer((long long)r.tail_count);
}

void op_var_historical(const In& in, Out& out) {
    const Vec pnl = in.reals("pnl");
    const double c = in.real("confidence");
    in.ready();
    limit_if(pnl.size() > max_f4_scenarios, "pnl");
    put_var(out, var_historical(pnl, c));
}

void op_var_filtered_historical(const In& in, Out& out) {
    const Vec r = in.reals("returns");
    const double p = in.real("position_value");
    const double lambda = in.real("lambda");
    const double c = in.real("confidence");
    in.ready();
    limit_if(r.size() > max_f4_scenarios, "returns");
    const FhsResult f = var_filtered_historical(r, p, lambda, c);
    put_var(out, f.v);
    out.key_real("sigma_next", f.sigma_next);
}

void op_var_parametric(const In& in, Out& out) {
    const double mu = in.real("mean");
    const double sd = in.real("std");
    const double c = in.real("confidence");
    in.ready();
    const ParametricVar v = var_parametric(mu, sd, c);
    out.key_real("var", v.var);
    out.key_real("es", v.es);
}

void op_var_monte_carlo(const In& in, Out& out) {
    const Vec mean = in.reals("mean");
    const Matrix cov = in.matrix("covariance");
    const Vec w = in.reals("weights");
    const long long paths = in.integer("paths");
    const std::uint64_t seed = in.u64("seed");  // ruling F-39: a decimal u64 string
    const double c = in.real("confidence");
    in.ready();
    limit_if(mean.size() > max_quotes, "mean");
    limit_if(paths > 0 && double(paths) * double(std::max<std::size_t>(mean.size(), 1)) > 1e7, "paths");
    put_var(out, var_monte_carlo(mean, cov, w, paths, seed, c));
}

void op_backtest_kupiec(const In& in, Out& out) {
    const long long n = in.integer("observations");
    const long long x = in.integer("exceptions");
    const double c = in.real("confidence");
    in.ready();
    const Kupiec k = backtest_kupiec(n, x, c);
    out.key_real("lr_uc", k.lr_uc);
    out.key_real("p_value", k.p_value);
}

void op_backtest_christoffersen(const In& in, Out& out) {
    const Value& a = in.need("exceptions");
    if (a.kind != Kind::Array) schema("exceptions", "expected an array");
    std::vector<bool> e;
    for (const Value& v : a.items) {
        if (v.kind != Kind::Bool) schema("exceptions", "expected a boolean");
        e.push_back(v.boolean);
    }
    const double c = in.real("confidence");
    in.ready();
    limit_if(e.size() > max_f4_scenarios, "exceptions");
    const Christoffersen r = backtest_christoffersen(e, c);
    out.key_real("lr_uc", r.lr_uc);
    out.key_real("lr_ind", r.lr_ind);
    out.key_real("lr_cc", r.lr_cc);
    out.key_real("p_uc", r.p_uc);
    out.key_real("p_ind", r.p_ind);
    out.key_real("p_cc", r.p_cc);
    out.values.key("transitions");
    out.values.begin_object();
    out.values.key("n00");
    out.values.integer(r.n00);
    out.values.key("n01");
    out.values.integer(r.n01);
    out.values.key("n10");
    out.values.integer(r.n10);
    out.values.key("n11");
    out.values.integer(r.n11);
    out.values.end_object();
}

void op_backtest_traffic_light(const In& in, Out& out) {
    const long long n = in.integer("observations");
    const long long x = in.integer("exceptions");
    const double c = in.real("confidence");
    in.ready();
    limit_if(n > 100000000, "observations");
    const TrafficLight t = backtest_traffic_light(n, x, c);
    out.key_real("cumulative_probability", t.cumulative_probability);
    out.key_string("zone", t.zone == TrafficZone::Green ? "GREEN" : t.zone == TrafficZone::Yellow ? "YELLOW" : "RED");
    out.key_maybe("plus_factor", t.plus_factor);
}

constexpr EnumTable<GirrFactor> girr_factors = {
    {"0.25Y", GirrFactor::T0_25}, {"0.5Y", GirrFactor::T0_5},          {"1Y", GirrFactor::T1},
    {"2Y", GirrFactor::T2},       {"3Y", GirrFactor::T3},              {"5Y", GirrFactor::T5},
    {"10Y", GirrFactor::T10},     {"15Y", GirrFactor::T15},            {"20Y", GirrFactor::T20},
    {"30Y", GirrFactor::T30},     {"INFLATION", GirrFactor::Inflation}, {"XCCY_BASIS", GirrFactor::XccyBasis},
};

void op_frtb_girr_delta(const In& in, Out& out) {
    const auto rows = rows_of<GirrSensitivity>(in, "sensitivities", [](const In& r) {
        return GirrSensitivity{r.text("currency"), r.text("curve"), r.choice("risk_factor", girr_factors),
                               r.real("sensitivity")};
    });
    const bool reduction = in.boolean("specified_currency_reduction", false);
    std::optional<std::string> reporting;
    if (in.find("reporting_currency")) reporting = in.text("reporting_currency");
    in.ready();
    limit_if(rows.size() > 10000, "sensitivities");
    const GirrResult g = frtb_girr_delta(rows, reduction, reporting);
    constexpr std::string_view names[] = {"high", "medium", "low"};
    out.values.key("scenarios");
    out.values.begin_object();
    for (std::size_t s = 0; s < 3; ++s) {
        const GirrScenario& sc = g.scenarios[s];
        out.values.key(names[s]);
        out.values.begin_object();
        out.values.key("buckets");
        out.values.begin_array();
        for (const GirrBucket& b : sc.buckets) {
            out.values.begin_object();
            out.key_string("currency", b.currency);
            out.key_real("k", b.k);
            out.key_real("s", b.s);
            out.key_real("s_used", b.s_used);
            out.values.end_object();
        }
        out.values.end_array();
        out.key_real("delta", sc.delta);
        out.values.key("alternative_used");
        out.values.boolean(sc.alternative_used);
        out.values.end_object();
    }
    out.values.end_object();
    out.key_real("capital", g.capital);
    out.key_string("binding_scenario", names[g.binding]);
}

// R6-4.1 (MAR21.7): the SBM total. Each class charge per scenario is summed within the scenario, then the largest
// scenario total is the capital. 06-risk/frtb-sa-girr.md, section risk.frtb.sbm_total.
struct SbmComponent {
    int risk_class, measure;
    std::array<double, 3> charge;  // high, medium, low
};
constexpr EnumTable<int> sbm_classes = {{"GIRR", 0}, {"CSR_NONSEC", 1}, {"EQ", 2}, {"COMM", 3}, {"FX", 4}};
constexpr EnumTable<int> sbm_measures = {{"DELTA", 0}, {"VEGA", 1}, {"CURVATURE", 2}};

void op_frtb_sbm_total(const In& in, Out& out) {
    const auto rows = rows_of<SbmComponent>(in, "components", [](const In& r) {
        SbmComponent c{r.choice("risk_class", sbm_classes), r.choice("measure", sbm_measures), {}};
        const Value& s = r.need("scenarios");
        if (s.kind != Kind::Object) schema("scenarios", "expected an object");
        const In sc(s);
        c.charge = {sc.real("high"), sc.real("medium"), sc.real("low")};
        return c;
    });
    in.ready();
    limit_if(rows.size() > 10000, "components");
    if (rows.empty()) throw Error("E_INPUT", "components needs at least one entry", "components");
    for (const SbmComponent& c : rows)
        for (const double x : c.charge)
            if (x < 0.0) throw Error("E_DOMAIN", "a scenario charge must be at least 0", "components");
    for (std::size_t i = 0; i < rows.size(); ++i)
        for (std::size_t j = 0; j < i; ++j)
            if (rows[i].risk_class == rows[j].risk_class && rows[i].measure == rows[j].measure)
                throw Error("E_INPUT", "a risk class and measure appear twice", "components");
    std::array<double, 3> total{0.0, 0.0, 0.0};
    double own = 0.0;
    for (const SbmComponent& c : rows) {
        for (std::size_t s = 0; s < 3; ++s) total[s] += c.charge[s];
        own += std::max({c.charge[0], c.charge[1], c.charge[2]});
    }
    std::size_t binding = 0;
    for (std::size_t s = 1; s < 3; ++s)
        if (total[s] > total[binding]) binding = s;
    constexpr std::string_view names[] = {"high", "medium", "low"};
    out.values.key("scenario_totals");
    out.values.begin_object();
    for (std::size_t s = 0; s < 3; ++s) out.key_real(names[s], total[s]);
    out.values.end_object();
    out.key_real("capital", total[binding]);
    out.key_string("binding_scenario", names[binding]);
    out.key_real("sum_of_component_capitals", own);
}

constexpr Entry risk_f4_ops[] = {
    {"risk.backtest.christoffersen", op_backtest_christoffersen},
    {"risk.backtest.kupiec", op_backtest_kupiec},
    {"risk.backtest.traffic_light", op_backtest_traffic_light},
    {"risk.frtb.girr_delta", op_frtb_girr_delta},
    {"risk.frtb.sbm_total", op_frtb_sbm_total},
    {"risk.var.filtered_historical", op_var_filtered_historical},
    {"risk.var.historical", op_var_historical},
    {"risk.var.monte_carlo", op_var_monte_carlo},
    {"risk.var.parametric", op_var_parametric},
};
