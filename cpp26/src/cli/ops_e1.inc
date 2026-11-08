// Stage E, E1: arbitrage-free SVI surfaces, local vol, forward vol, smile dynamics, vol of vol.
// Included by dispatch.cpp after ops_c_all.inc (uses svi_of and write_svi).

std::vector<SviSlice> slices_of(const In& in) {
    return rows_of<SviSlice>(in, "slices", [](const In& row) { return SviSlice{row.real("expiry_years"), svi_of(row)}; });
}

void write_check(Out& out, const SviSurfaceCheck& c) {
    const auto grid = [&](string_view key, const std::vector<GridViolation>& v) {
        out.values.key(key);
        out.values.begin_array();
        for (const GridViolation& g : v) {
            out.values.begin_object();
            out.values.key("expiry_index");
            out.values.integer((long long)g.expiry_index);
            out.values.key("k_index");
            out.values.integer((long long)g.k_index);
            out.values.end_object();
        }
        out.values.end_array();
    };
    grid("butterfly_violations", c.butterfly);
    grid("calendar_violations", c.calendar);
    out.values.key("wing_violations");
    out.values.begin_array();
    for (const WingViolation& w : c.wings) {
        out.values.begin_object();
        out.values.key("expiry_index");
        out.values.integer((long long)w.expiry_index);
        out.key_string("side", w.side);
        out.key_string("kind", w.kind);
        out.values.end_object();
    }
    out.values.end_array();
    out.values.key("arbitrage_free");
    out.values.boolean(c.arbitrage_free());
}

void op_svi_surface_check(const In& in, Out& out) {
    const auto slices = slices_of(in);
    const Vec k = in.reals("log_moneyness");
    const bool reject = in.boolean("reject");
    in.ready();
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
    const LocalVol r = local_vol_dupire(slices, points);
    out.key_reals("total_variance", r.total_variance);
    out.key_reals("implied_vol", r.implied_vol);
    out.key_reals("local_vol", r.local_vol);
}

void op_forward_vol(const In& in, Out& out) {
    const Vec t = in.reals("expiry_years"), v = in.reals("vols");
    in.ready();
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
    const VolOfVol r = vol_of_vol(v, ppy, m);
    out.key_real("mean_change", r.mean_change);
    out.key_real("vol_of_vol", r.vol_of_vol);
}
