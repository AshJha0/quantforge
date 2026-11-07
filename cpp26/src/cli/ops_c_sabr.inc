// Stage C: SABR.

struct SabrInput {
    double forward, t;
    SabrParameters p;
    double shift;
    Vec strikes;

    double f() const { return forward + shift; }
    Vec shifted() const {
        Vec x = strikes;
        for (double& k : x) k += shift;
        return x;
    }
    void check() const {
        limit_if(strikes.size() > max_quotes, "strikes");
        check_sabr(t, p, f(), shifted());
    }
};

SabrInput sabr_of(const In& in) {
    return {in.real("forward"), in.real("expiry_years"),
            {in.real("alpha"), in.real("beta"), in.real("rho"), in.real("nu")},
            optional_real(in, "shift", 0.0), in.reals("strikes")};
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
    if (x.empty()) throw Error("E_INPUT", "strikes is empty");
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
