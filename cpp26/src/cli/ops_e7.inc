// Stage E, E7: GARCH, variance swaps, VIX. Included by dispatch.cpp after ops_r2.inc.

// "SAMPLE" or a number; any other JSON type is E_SCHEMA. Another string is E_INPUT, raised after ready().
struct InitialVariance {
    std::optional<double> value;
    bool bad_string = false;
};
InitialVariance initial_variance_of(const In& in) {
    const Value& v = in.need("initial_variance");
    if (v.kind == Kind::String) return {std::nullopt, v.text != "SAMPLE"};
    return {to_real(v, "initial_variance"), false};
}
void check_initial_variance(const InitialVariance& iv) {
    if (iv.bad_string) throw Error("E_INPUT", "initial_variance must be SAMPLE or a number", "initial_variance");
}

void op_garch_loglik(const In& in, Out& out) {
    const Vec r = in.reals("returns");
    const double omega = in.real("omega"), alpha = in.real("alpha"), beta = in.real("beta");
    const InitialVariance iv = initial_variance_of(in);
    in.ready();
    if (r.size() < 2) throw Error("E_INPUT", "at least 2 returns are needed", "returns");
    check_initial_variance(iv);
    const GarchLoglik g = garch_loglik(r, omega, alpha, beta, iv.value);
    out.key_real("loglik", g.loglik);
    out.key_reals("variances", g.variances);
    out.key_real("next_variance", g.next_variance);
}

void op_garch_forecast(const In& in, Out& out) {
    const double omega = in.real("omega"), alpha = in.real("alpha"), beta = in.real("beta");
    const double next = in.real("next_variance");
    const long long h = in.integer("horizon");
    const double ppy = in.real("periods_per_year");
    in.ready();
    const GarchForecast f = garch_forecast(omega, alpha, beta, next, h, ppy);
    out.key_reals("variances", f.variances);
    out.key_real("total_variance", f.total_variance);
    out.key_real("annualized_vol", f.annualized_vol);
    out.key_real("long_run_variance", f.long_run_variance);
}

void op_garch_fit(const In& in, Out& out) {
    const Vec r = in.reals("returns");
    const InitialVariance iv = initial_variance_of(in);
    in.ready();
    if (r.size() < 30) throw Error("E_INPUT", "at least 30 returns are needed", "returns");
    check_initial_variance(iv);
    const GarchFit f = garch_fit(r, iv.value);
    out.key_real("loglik", f.loglik);
    out.diagnostic("omega", f.omega);
    out.diagnostic("alpha", f.alpha);
    out.diagnostic("beta", f.beta);
}

void op_varswap_fair(const In& in, Out& out) {
    VarSwapInputs v;
    v.as_of = in.date("as_of");
    v.maturity = in.date("maturity");
    v.spot = in.real("spot");
    v.rate = in.real("rate");
    v.dividend_yield = in.real("dividend_yield");
    v.put_strikes = in.reals("put_strikes");
    v.call_strikes = in.reals("call_strikes");
    v.vols = rows_of<StrikeVol>(in, "vols", [](const In& row) { return StrikeVol{row.real("strike"), row.real("vol")}; });
    v.extension_step = in.real("extension_step");
    v.variance_strike = in.real("variance_strike");
    v.variance_notional = in.real("variance_notional");
    in.ready();
    const VarSwapFair f = varswap_fair_strike(v);
    out.key_real("fair_variance", f.fair_variance);
    out.key_real("fair_vol", f.fair_vol);
    out.key_real("pv", f.pv);
}

void op_varswap_realized(const In& in, Out& out) {
    const Vec p = in.reals("prices");
    const double a = in.real("periods_per_year"), k = in.real("variance_strike"), n = in.real("variance_notional");
    in.ready();
    const VarSwapRealized r = varswap_realized(p, a, k, n);
    out.key_real("realized_variance", r.realized_variance);
    out.key_real("realized_vol", r.realized_vol);
    out.key_real("payoff", r.payoff);
}

VixTerm vix_term_of(const In& in) {
    VixTerm t;
    t.minutes = in.integer("minutes_to_expiry");
    t.rate = in.real("rate");
    t.strip = rows_of<VixQuote>(in, "strip", [](const In& q) {
        return VixQuote{q.real("strike"), q.real("call_bid"), q.real("call_ask"), q.real("put_bid"), q.real("put_ask")};
    });
    return t;
}

VixTerm vix_term_at(const In& in, string_view key) {
    const Value& v = in.need(key);
    if (v.kind != Kind::Object) schema(key, "expected an object");
    return vix_term_of(In(v));
}

void op_vix_term(const In& in, Out& out) {
    const VixTerm t = vix_term_of(in);
    in.ready();
    const VixTermResult r = vix_term_variance(t);
    out.key_real("forward", r.forward);
    out.key_real("k0", r.k0);
    out.key_real("variance", r.variance);
    out.key_reals("strikes_used", r.strikes_used);
}

void op_vix_index(const In& in, Out& out) {
    const VixTerm near = vix_term_at(in, "near"), next = vix_term_at(in, "next");
    in.ready();
    const VixIndex r = vix_index(near, next);
    out.key_real("index", r.index);
    out.key_real("near_variance", r.near_variance);
    out.key_real("next_variance", r.next_variance);
}
