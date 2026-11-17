// CLI handlers, stage J wave 3 (rulings J-W3-1 to J-W3-14): scenario stress, interpolation backtests and drift
// detectors. The research.* verbs carry their own page limits (J-W3-14); risk.scenario.* keep the general limit too.

void op_risk_scenario_historical_shock(const In& in, Out& out) {
    const std::vector<Date> d = dates_of(in, "dates");
    const Vec t = in.reals("tenors");
    const Matrix y = in.matrix("yields");
    const Date start = in.date("start_date"), end = in.date("end_date");
    bool wide = false;
    for (const Vec& r : y) wide = wide || r.size() > 100;
    limit_if(t.size() > 100, "tenors");
    limit_if(wide, "yields");
    in.ready();
    std::vector<long long> days;
    for (const Date x : d) days.push_back(x.time_since_epoch().count());
    const research::Shock r = research::historical_shock(days, t, y, start.time_since_epoch().count(),
                                                         end.time_since_epoch().count());
    out.key_reals("start_yields", r.start_yields);
    out.key_reals("end_yields", r.end_yields);
    out.key_reals("shift_bp", r.shift_bp);
    out.key_real("level_bp", r.level_bp);
    out.key_real("slope_bp", r.slope_bp);
}

void op_risk_scenario_replay(const In& in, Out& out) {
    const Vec bt = in.reals("base_tenors"), by = in.reals("base_yields");
    const Vec st = in.reals("shock_tenors"), sb = in.reals("shock_bp");
    const double scale = in.real("scale", 1.0);
    std::optional<Vec> dv01;
    if (in.find("dv01")) dv01 = in.reals("dv01");
    limit_if(bt.size() > 100 || by.size() > 100, "base_tenors");
    limit_if(st.size() > 100 || sb.size() > 100, "shock_tenors");
    limit_if(dv01 && dv01->size() > 100, "dv01");
    in.ready();
    const research::Replay r = research::replay(bt, by, st, sb, scale, dv01);
    out.key_reals("applied_bp", r.applied_bp);
    out.key_reals("shocked_yields", r.shocked_yields);
    if (r.pnl) out.key_real("pnl", *r.pnl);
}

void op_research_interp_loo(const In& in, Out& out) {
    const int m = in.choice<int>("method", {{"linear", 0}, {"log_linear", 1}, {"cubic_natural", 2}, {"monotone_pchip", 3}});
    const Vec x = in.reals("x"), y = in.reals("y");
    limit_if(x.size() > 10000 || y.size() > 10000, "x");
    in.ready();
    const research::LooBacktest r = research::interp_loo(m, x, y);
    out.key_reals("errors", r.errors);
    out.key_real("max_abs_error", r.max_abs_error);
    out.key_real("rmse", r.rmse);
}

void op_research_surface_holdout(const In& in, Out& out) {
    const int m = in.choice<int>("method", {{"linear", 0}, {"cubic_natural", 2}, {"monotone_pchip", 3}});
    const Vec e = in.reals("expiries"), k = in.reals("strikes");
    const Matrix v = in.matrix("vols");
    const std::vector<long long> h = integers_of(in, "holdout");
    bool wide = v.size() > 1000;
    for (const Vec& r : v) wide = wide || r.size() > 1000;
    limit_if(e.size() > 1000 || k.size() > 1000 || h.size() > 1000, "strikes");
    limit_if(wide, "vols");
    in.ready();
    const research::SurfaceBacktest r = research::surface_holdout(m, e, k, v, h);
    key_matrix(out, "errors", r.errors);
    out.key_real("max_abs_error", r.max_abs_error);
    out.key_real("rmse", r.rmse);
}

void op_research_drift_cusum(const In& in, Out& out) {
    const Vec x = in.reals("x");
    const double k = in.real("k"), h = in.real("h"), mu0 = in.real("mu0", 0.0), sigma = in.real("sigma", 1.0);
    const bool reset = in.boolean("reset", true);
    limit_if(x.size() > 10000000, "x");
    in.ready();
    const research::Alarms a = research::cusum(x, k, h, mu0, sigma, reset);
    key_integers(out, "alarms", a.alarms);
    key_integers(out, "directions", a.directions);
    out.key_real("s_plus", a.s_plus);
    out.key_real("s_minus", a.s_minus);
}

void op_research_drift_page_hinkley(const In& in, Out& out) {
    const Vec x = in.reals("x");
    const double delta = in.real("delta"), lambda = in.real("lambda");
    const int dir = in.find("direction") ? in.choice<int>("direction", {{"up", 1}, {"down", -1}, {"both", 0}}) : 0;
    const bool reset = in.boolean("reset", true);
    limit_if(x.size() > 10000000, "x");
    in.ready();
    const research::Alarms a = research::page_hinkley(x, delta, lambda, dir, reset);
    key_integers(out, "alarms", a.alarms);
    key_integers(out, "directions", a.directions);
}

void op_research_drift_psi(const In& in, Out& out) {
    const Vec r = in.reals("reference"), t = in.reals("test");
    const long long bins = in.integer("bins", 10);
    const double th = in.real("threshold", 0.25);
    limit_if(r.size() > 1000000, "reference");
    limit_if(t.size() > 1000000, "test");
    limit_if(bins > 1000, "bins");
    in.ready();
    const research::Psi p = research::psi(r, t, bins, th);
    out.key_real("psi", p.psi);
    out.key_reals("reference_shares", p.reference_shares);
    out.key_reals("test_shares", p.test_shares);
    out.values.key("alarm");
    out.values.boolean(p.alarm);
}

void op_research_drift_ks(const In& in, Out& out) {
    const Vec a = in.reals("a"), b = in.reals("b");
    const double level = in.real("level", 0.05);
    limit_if(a.size() > 1000000 || b.size() > 1000000, "a");
    limit_if(product_above(static_cast<long long>(a.size()), static_cast<long long>(b.size()), 4000000), "b");
    in.ready();
    const research::Ks r = research::ks(a, b, level);
    out.key_real("statistic", r.statistic);
    out.key_real("p_value", r.p_value);
    out.values.key("reject");
    out.values.boolean(r.reject);
}

constexpr Entry research_w3_ops[] = {
    {"risk.scenario.historical_shock", op_risk_scenario_historical_shock},
    {"risk.scenario.replay", op_risk_scenario_replay},
    {"research.backtest.interp_loo", op_research_interp_loo},
    {"research.backtest.surface_holdout", op_research_surface_holdout},
    {"research.drift.cusum", op_research_drift_cusum},
    {"research.drift.page_hinkley", op_research_drift_page_hinkley},
    {"research.drift.psi", op_research_drift_psi},
    {"research.drift.ks", op_research_drift_ks},
};
