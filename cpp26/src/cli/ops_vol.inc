// CLI handlers, the vol verbs.
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.

void op_option_price(const In& in, Out& out) {
    const OptionInput o = option_of(in);
    const double vol = in.real("vol");
    in.ready();
    out.key_real("price", checked_option_price(o, vol));
    out.key_real("forward", o.model_forward());
}

void op_option_implied(const In& in, Out& out) {
    const OptionInput o = option_of(in);
    const double price = in.real("price");
    in.ready();
    out.key_real("vol", implied_vol(o, price));
}

void op_equity_price(const In& in, Out& out) {
    const ForwardInput f = forward_of(in);
    const OptionType type = in.choice("option_type", option_types);
    const double strike = in.real("strike"), vol = in.real("vol"), quantity = in.real("quantity");
    const FxSide side = in.choice("side", fx_sides);
    const string& currency = currency_of(in);
    const auto snapshot = optional_snapshot(in);
    in.ready();
    const EquityForward e = f.solve();
    const double t = double(days_between(f.as_of, f.expiry)) / 365.0;
    if (t == 0 || vol <= 0 || strike <= 0 || quantity <= 0) throw Error("E_DOMAIN", "expiry, vol, strike and quantity must be above 0");
    const double signed_quantity = side == FxSide::Buy ? quantity : -quantity;
    const PositionRisk r = position_risk(e.forward, strike, vol, t, e.discount_factor, type, signed_quantity);
    write_valuation(out, {r.pv, currency, "BLACK_76_EQUITY", snapshot, "EQUITY_FORWARD", f.as_of});
    out.key_real("forward", e.forward);
    out.key_real("delta", r.delta_forward / e.carry_factor);
    out.key_real("gamma", r.gamma_forward / (e.carry_factor * e.carry_factor));
    out.key_real("vega", r.vega);
}

void op_delta_to_strike(const In& in, Out& out) {
    const double f = in.real("forward"), v = in.real("vol"), t = in.real("expiry_years"), delta = in.real("delta");
    const OptionType type = in.choice("option_type", option_types);
    const DeltaScale s = delta_scale_of(in);
    in.ready();
    out.key_real("strike", delta_to_strike(f, v, t, type, delta, s.value()));
}

void op_delta_from_strike(const In& in, Out& out) {
    const double f = in.real("forward"), v = in.real("vol"), t = in.real("expiry_years"), strike = in.real("strike");
    const OptionType type = in.choice("option_type", option_types);
    const DeltaScale s = delta_scale_of(in);
    in.ready();
    out.key_real("delta", delta_from_strike(f, v, t, type, strike, s.value()));
}

void op_smile_rr_bf(const In& in, Out& out) {
    enum class Atm { Forward, DeltaNeutral };
    static constexpr EnumTable<Atm> atm_conventions = {{"ATM_FORWARD", Atm::Forward}, {"DELTA_NEUTRAL", Atm::DeltaNeutral}};
    const double f = in.real("forward"), t = in.real("expiry_years"), atm = in.real("atm_vol");
    const Atm convention = in.choice("atm_convention", atm_conventions);
    const double rr = in.real("rr"), bf = in.real("bf"), delta = in.real("delta");
    const DeltaScale s = delta_scale_of(in);
    in.ready();
    const double scale = s.value();
    const double call_vol = atm + bf + rr / 2, put_vol = atm + bf - rr / 2;
    if (atm <= 0 || call_vol <= 0 || put_vol <= 0) throw Error("E_DOMAIN", "a vol is not above 0");
    if (delta <= 0) throw Error("E_DOMAIN", "delta is not above 0");
    const double call_strike = delta_to_strike(f, call_vol, t, OptionType::Call, delta, scale);
    const double put_strike = delta_to_strike(f, put_vol, t, OptionType::Put, -delta, scale);
    out.key_real("atm_strike", convention == Atm::Forward ? f : f * std::exp(atm * atm * t / 2));
    out.key_real("call_vol", call_vol);
    out.key_real("put_vol", put_vol);
    out.key_real("call_strike", call_strike);
    out.key_real("put_strike", put_strike);
}

void op_svi_evaluate(const In& in, Out& out) {
    const Svi s = svi_of(in);
    const Vec k = in.reals("log_moneyness");
    const double t = in.real("expiry_years");
    in.ready();
    limit_if(k.size() > max_quotes, "log_moneyness");
    need_items(k, "log_moneyness");
    check_svi(s);
    if (t <= 0) throw Error("E_DOMAIN", "expiry_years is not above 0");
    Vec w, vols, g;
    for (const double x : k) {
        w.push_back(s.w(x));
        vols.push_back(std::sqrt(w.back() / t));
        g.push_back(s.g(x));
    }
    const double min_g = *std::ranges::min_element(g);
    out.key_reals("total_variance", w);
    out.key_reals("implied_vol", vols);
    out.key_reals("g", g);
    out.key_real("min_g", min_g);
    out.values.key("butterfly_free");
    out.values.boolean(min_g >= 0);
}

void op_svi_calibrate(const In& in, Out& out) {
    const Vec k = in.reals("log_moneyness"), w = in.reals("total_variance");
    const auto weights = optional_weights(in);
    in.ready();
    limit_if(k.size() > max_quotes || w.size() > max_quotes, "log_moneyness");
    const SviFit fit = svi_calibrate(k, w, weights);
    write_svi(out, fit.svi);
    out.key_real("rmse", fit.rmse);
}

void op_ssvi_evaluate(const In& in, Out& out) {
    const Ssvi s{in.real("rho"), in.real("eta"), in.real("gamma")};
    const Vec thetas = in.reals("thetas"), k = in.reals("log_moneyness");
    in.ready();
    limit_if(thetas.size() > max_quotes || k.size() > max_quotes, "thetas");
    need_items(thetas, "thetas");
    need_items(k, "log_moneyness");
    check_ssvi(s, thetas);
    out.values.key("total_variance");
    out.values.begin_array();
    for (const double theta : thetas) {
        out.values.begin_array();
        for (const double x : k) out.values.real(s.w(x, theta));
        out.values.end_array();
    }
    out.values.end_array();
    out.values.key("butterfly_free");
    out.values.boolean(ssvi_butterfly_free(s, thetas));
    out.values.key("calendar_free");
    out.values.boolean(ssvi_calendar_free(s, thetas));
}

void op_ssvi_calibrate(const In& in, Out& out) {
    const Vec thetas = in.reals("thetas"), k = in.reals("log_moneyness");
    const Matrix w = in.matrix("total_variance");
    in.ready();
    limit_if(thetas.size() > max_quotes || k.size() > max_quotes, "thetas");
    need_items(thetas, "thetas");
    need_items(k, "log_moneyness");
    const SsviFit fit = ssvi_calibrate(thetas, k, w);
    out.key_real("rho", fit.ssvi.rho);
    out.key_real("eta", fit.ssvi.eta);
    out.key_real("gamma", fit.ssvi.gamma);
    out.key_real("rmse", fit.rmse);
}

void op_surface_query(const In& in, Out& out) {
    struct Point {
        double t, k;
    };
    const Surface s = surface_of(in);
    const auto points = rows_of<Point>(in, "points", [](const In& r) { return Point{r.real("expiry_years"), r.real("log_moneyness")}; });
    in.ready();
    limit_surface(s);
    limit_if(points.size() > max_quotes, "points");
    need_items(points, "points");
    check_surface(s);
    Vec w, vols;
    for (const Point& p : points) {
        if (p.t <= 0) throw Error("E_DOMAIN", "expiry_years is not above 0");
        w.push_back(surface_total_variance(s, p.t, p.k));
        vols.push_back(std::sqrt(w.back() / p.t));
    }
    out.key_reals("total_variance", w);
    out.key_reals("vols", vols);
}

void op_surface_check(const In& in, Out& out) {
    const Surface s = surface_of(in);
    in.ready();
    limit_surface(s);
    check_surface(s);
    write_surface_check(out, surface_check(s));
}

void op_sabr_hagan(const In& in, Out& out) {
    const SabrInput s = sabr_of(in);
    in.ready();
    s.check();
    Vec vols;
    for (const double x : s.shifted()) vols.push_back(hagan_vol(s.f(), x, s.t, s.p));
    out.key_reals("vols", vols);
}

void op_sabr_density(const In& in, Out& out) {
    enum class OnNegative { Report, Reject };
    static constexpr EnumTable<OnNegative> actions = {{"REPORT", OnNegative::Report}, {"REJECT", OnNegative::Reject}};
    const SabrInput s = sabr_of(in);
    const double h = in.real("h_strike");
    const OnNegative action = in.choice("on_negative", actions);
    in.ready();
    s.check();
    if (h <= 0) throw Error("E_DOMAIN", "h_strike is not above 0");
    const Vec x = s.shifted();
    for (const double k : x)
        if (k - h <= 0) throw Error("E_DOMAIN", "strike - h_strike is not above 0");
    const SabrDensity d = sabr_density(s.f(), x, s.t, s.p, h);
    if (d.negative && action == OnNegative::Reject) throw Error("E_ARBITRAGE", "negative density");
    out.key_reals("density", d.density);
    out.key_real("min_density", d.min_density);
    out.values.key("negative_density");
    out.values.boolean(d.negative);
}

void op_sabr_calibrate(const In& in, Out& out) {
    const double forward = in.real("forward"), t = in.real("expiry_years"), beta = in.real("beta");
    const double shift = optional_real(in, "shift", 0.0);
    Vec strikes = in.reals("strikes");
    const Vec vols = in.reals("vols");
    const auto weights = optional_weights(in);
    in.ready();
    limit_if(strikes.size() > max_quotes || vols.size() > max_quotes, "strikes");
    need_items(strikes, "strikes");
    for (double& k : strikes) k += shift;
    // alpha, rho and nu are outputs here, so stand-ins that pass let the common checks run on the rest.
    check_sabr(t, {1.0, beta, 0.0, 0.0}, forward + shift, strikes);
    const SabrFit fit = sabr_calibrate(forward + shift, t, beta, strikes, vols, weights);
    out.key_real("alpha", fit.alpha);
    out.key_real("rho", fit.rho);
    out.key_real("nu", fit.nu);
    out.key_real("rmse", fit.rmse);
}

void op_sabr_arbfree(const In& in, Out& out) {
    const SabrInput s = sabr_of(in);
    const ArbFreeGrid grid{in.integer("cells"), in.integer("cells_below"), in.integer("steps")};
    in.ready();
    limit_if(grid.cells > 20000 || grid.steps > 20000, "cells");
    s.check();
    if (s.p.beta >= 1) throw Error("E_DOMAIN", "beta must be below 1");
    if (grid.cells_below < 1 || grid.cells_below >= grid.cells || grid.steps < 1) throw Error("E_INPUT", "bad grid");
    const ArbFreeResult r = sabr_arbfree(s.f(), s.shifted(), s.t, s.p, grid);
    out.key_reals("call_prices", r.call_prices);
    out.key_maybes("vols", r.vols);
    out.key_real("mass", r.mass);
    out.key_real("mean", r.mean);
    out.key_real("absorbed", r.absorbed);
    out.key_real("min_density", r.min_density);
}

void op_svi_surface_check(const In& in, Out& out) {
    const auto slices = slices_of(in);
    const Vec k = in.reals("log_moneyness");
    const bool reject = in.boolean("reject");
    in.ready();
    limit_if(slices.size() > 100, "slices");
    limit_if(k.size() > 10000, "log_moneyness");
    write_check(out, svi_surface_check(slices, k, reject));
}

void op_ssvi_to_svi(const In& in, Out& out) {
    const double rho = in.real("rho"), eta = in.real("eta"), gamma = in.real("gamma"), theta = in.real("theta");
    in.ready();
    write_svi(out, ssvi_to_svi(rho, eta, gamma, theta));
}

void op_svi_fit_surface(const In& in, Out& out) {
    const Vec t = in.reals("expiry_years"), k = in.reals("log_moneyness");
    const Matrix w = in.matrix("total_variance");
    const bool reject = in.boolean("reject");
    in.ready();
    limit_if(t.size() > 100, "expiry_years");
    limit_if(k.size() > max_quotes, "log_moneyness");
    const SurfaceFit f = svi_fit_surface(t, k, w, reject);
    out.values.key("slices");
    out.values.begin_array();
    for (const SviSlice& s : f.slices) {
        out.values.begin_object();
        out.key_real("expiry_years", s.expiry_years);
        write_svi(out, s.svi);
        out.values.end_object();
    }
    out.values.end_array();
    out.key_reals("rmse", f.rmse);
    write_check(out, f.check);
}

void op_local_dupire(const In& in, Out& out) {
    const auto slices = slices_of(in);
    const auto points = rows_of<LocalVolPoint>(
        in, "points", [](const In& p) { return LocalVolPoint{p.real("expiry_years"), p.real("log_moneyness")}; });
    in.ready();
    limit_if(slices.size() > 100, "slices");
    limit_if(points.size() > 10000, "points");
    const LocalVol r = local_vol_dupire(slices, points);
    out.key_reals("total_variance", r.total_variance);
    out.key_reals("implied_vol", r.implied_vol);
    out.key_reals("local_vol", r.local_vol);
}

void op_forward_vol(const In& in, Out& out) {
    const Vec t = in.reals("expiry_years"), v = in.reals("vols");
    in.ready();
    limit_if(t.size() > max_quotes || v.size() > max_quotes, "expiry_years");
    out.key_reals("forward_vols", forward_vols(t, v));
}

void op_smile_dynamics(const In& in, Out& out) {
    SmileDynamicsInputs s;
    s.svi = svi_of(in);
    s.expiry_years = in.real("expiry_years");
    s.spot = in.real("spot");
    s.spot_shifted = in.real("spot_shifted");
    s.rate = in.real("rate");
    s.dividend_yield = in.real("dividend_yield");
    s.strikes = in.reals("strikes");
    s.rule = in.choice<SmileRule>("rule", {{"STICKY_STRIKE", SmileRule::StickyStrike}, {"STICKY_DELTA", SmileRule::StickyDelta}});
    s.type = in.choice("option_type", option_types);
    in.ready();
    limit_if(s.strikes.size() > max_quotes, "strikes");
    const SmileDynamics r = smile_dynamics(s);
    out.key_reals("vols_base", r.vols_base);
    out.key_reals("vols_shifted", r.vols_shifted);
    out.key_reals("prices_base", r.prices_base);
    out.key_reals("prices_shifted", r.prices_shifted);
    out.key_reals("deltas", r.deltas);
}

void op_volofvol(const In& in, Out& out) {
    const Vec v = in.reals("vols");
    const double ppy = in.real("periods_per_year");
    const VolChange m = in.choice<VolChange>("method", {{"LOG", VolChange::Log}, {"ABSOLUTE", VolChange::Absolute}});
    in.ready();
    limit_if(v.size() > 10000, "vols");
    const VolOfVol r = vol_of_vol(v, ppy, m);
    out.key_real("mean_change", r.mean_change);
    out.key_real("vol_of_vol", r.vol_of_vol);
}

void op_heston_cf(const In& in, Out& out) {
    const double t = in.real("expiry_years");
    const HestonParams h = heston_of(in);
    const Vec u = in.reals("u");
    in.ready();
    limit_if(u.size() > max_quotes, "u");
    if (u.empty()) throw Error("E_INPUT", "u is empty", "u");
    if (!(t > 0)) throw Error("E_DOMAIN", "expiry_years is not above 0", "expiry_years");
    check_heston(h);
    for (const double x : u)
        if (!(x >= 0)) throw Error("E_DOMAIN", "a u is negative", "u");
    Vec re, im;
    for (const double x : u) {
        const std::complex<double> c = heston_cf(t, h, {x, 0.0});
        re.push_back(c.real());
        im.push_back(c.imag());
    }
    out.key_reals("re", re);
    out.key_reals("im", im);
}

void op_heston_price(const In& in, Out& out) {
    const EquityOption o = equity_option_of(in);
    const HestonParams h = heston_of(in);
    in.ready();
    limit_if(o.strikes.size() > max_quotes, "strikes");
    out.key_reals("prices", heston_price(o, h));
}

void op_bates_price(const In& in, Out& out) {
    const EquityOption o = equity_option_of(in);
    const HestonParams h = heston_of(in);
    const Jumps j = jumps_of(in);
    in.ready();
    limit_if(o.strikes.size() > max_quotes, "strikes");
    out.key_reals("prices", bates_price(o, h, j));
}

void op_merton_price(const In& in, Out& out) {
    const EquityOption o = equity_option_of(in);
    const double vol = in.real("vol");
    const Jumps j = jumps_of(in);
    in.ready();
    limit_if(o.strikes.size() > max_quotes, "strikes");
    out.key_reals("prices", merton_price(o, vol, j));
}

void op_slv_leverage(const In& in, Out& out) {
    const double spot = in.real("spot"), t = in.real("expiry_years"), r = in.real("rate"), q = in.real("dividend_yield");
    const HestonParams h = heston_of(in);
    const auto slices = slices_of(in);
    const Value& gv = in.need("grid");
    if (gv.kind != Kind::Object) schema("grid", "expected an object");
    const In g(gv);
    const SlvGrid grid{g.integer("nx"), g.integer("nv"), g.integer("nt"), g.real("x_min"), g.real("x_max"), g.real("v_max")};
    in.ready();
    const SlvLeverage s = slv_leverage(spot, t, r, q, h, slices, grid);
    out.key_reals("x", s.x);
    out.key_reals("leverage", s.leverage);
    out.key_real("mass", s.mass);
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

constexpr Entry vol_ops[] = {
    {"vol.bates.price", op_bates_price},
    {"vol.delta.from_strike", op_delta_from_strike},
    {"vol.delta.to_strike", op_delta_to_strike},
    {"vol.equity.price", op_equity_price},
    {"vol.forward.vol", op_forward_vol},
    {"vol.garch.fit", op_garch_fit},
    {"vol.garch.forecast", op_garch_forecast},
    {"vol.garch.loglik", op_garch_loglik},
    {"vol.heston.cf", op_heston_cf},
    {"vol.heston.price", op_heston_price},
    {"vol.local.dupire", op_local_dupire},
    {"vol.merton.price", op_merton_price},
    {"vol.option.implied", op_option_implied},
    {"vol.option.price", op_option_price},
    {"vol.sabr.arbfree", op_sabr_arbfree},
    {"vol.sabr.calibrate", op_sabr_calibrate},
    {"vol.sabr.density", op_sabr_density},
    {"vol.sabr.hagan", op_sabr_hagan},
    {"vol.slv.leverage", op_slv_leverage},
    {"vol.smile.dynamics", op_smile_dynamics},
    {"vol.smile.rr_bf", op_smile_rr_bf},
    {"vol.ssvi.calibrate", op_ssvi_calibrate},
    {"vol.ssvi.evaluate", op_ssvi_evaluate},
    {"vol.ssvi.to_svi", op_ssvi_to_svi},
    {"vol.surface.check", op_surface_check},
    {"vol.surface.query", op_surface_query},
    {"vol.svi.calibrate", op_svi_calibrate},
    {"vol.svi.evaluate", op_svi_evaluate},
    {"vol.svi.fit_surface", op_svi_fit_surface},
    {"vol.svi.surface_check", op_svi_surface_check},
    {"vol.varswap.fair_strike", op_varswap_fair},
    {"vol.varswap.realized", op_varswap_realized},
    {"vol.vix.index", op_vix_index},
    {"vol.vix.term_variance", op_vix_term},
    {"vol.volofvol.measure", op_volofvol},
};
