// CLI handlers, stage G: short-rate models, G2++, MC Greeks and swap exposure (04-pricing/short-rate-models.md,
// 06-risk/mc-greeks.md, 06-risk/xva-exposure.md; rulings G-1 to G-21). The maths is in core/shortrate.cpp.
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.

namespace sr = quantforge::shortrate;
namespace mcg = quantforge::mcgreeks;

// An enum whose unknown value is E_INPUT (spec errors list), not E_SCHEMA.
template <class T>
T sr_enum(const In& in, string_view k, std::initializer_list<std::pair<const char*, T>> table) {
    const Value& v = in.need(k);
    if (v.kind != Kind::String) schema(k, "expected a string");
    for (const auto& [name, val] : table)
        if (v.text == name) return val;
    throw Error("E_INPUT", "unknown value", string(k));
}

// F-2 for arrays whose order is checked before ready(): a non-finite element is E_DOMAIN first.
Vec sr_finite(Vec v, string_view key) {
    for (double x : v)
        if (!std::isfinite(x)) throw Error("E_DOMAIN", string(key) + " must be finite", string(key));
    return v;
}
Vec sr_reals(const In& in, string_view key) { return sr_finite(in.reals(key), key); }

sr::Curve sr_curve(const In& in) {
    const Value& cv = in.need("curve");
    if (cv.kind != Kind::Object) schema("curve", "expected an object");
    const In c(cv);
    const Vec times = sr_reals(c, "times"), dfs = sr_reals(c, "discount_factors");
    c.ready();
    limit_if(times.size() > 10000, "curve");
    if (times.empty() || times.size() != dfs.size()) throw Error("E_INPUT", "curve needs matching times and discount factors", "curve");
    for (std::size_t i = 0; i < times.size(); ++i) {
        if (!(times[i] > (i ? times[i - 1] : 0.0))) throw Error("E_INPUT", "curve times must increase from above 0", "curve");
        if (!(dfs[i] > 0)) throw Error("E_DOMAIN", "curve discount factor is not positive", "curve");
    }
    return sr::Curve::from(times, dfs);
}

void sr_positive(double v, const char* key) {
    if (!(v > 0)) throw Error("E_DOMAIN", string(key) + " is not positive", key);
}

// Model and parameters. `option`: the G-5 rule (short_rate refused for HULL_WHITE). `hw_default`: model may be absent.
sr::Params sr_params(const In& in, bool option, bool hw_default = false) {
    sr::Params p{};
    p.model = (hw_default && !in.find("model"))
                  ? sr::Model::HullWhite
                  : sr_enum<sr::Model>(in, "model", {{"VASICEK", sr::Model::Vasicek}, {"CIR", sr::Model::Cir}, {"HULL_WHITE", sr::Model::HullWhite}});
    const bool hw = p.model == sr::Model::HullWhite;
    if (hw && option && in.find("short_rate")) throw Error("E_INPUT", "short_rate is not allowed for HULL_WHITE options", "short_rate");
    p.a = in.real("mean_reversion");
    p.sigma = in.real("sigma");
    sr_positive(p.a, "mean_reversion");
    sr_positive(p.sigma, "sigma");
    if (!hw) {
        p.b = in.real("long_term_mean");
        if (p.model == sr::Model::Cir) sr_positive(p.b, "long_term_mean");
    }
    if (!(hw && option)) {
        p.r0 = in.real("short_rate");
        if (p.model == sr::Model::Cir && !(p.r0 >= 0)) throw Error("E_DOMAIN", "short_rate is negative", "short_rate");
    }
    if (hw) p.curve = sr_curve(in);
    return p;
}

// Hull-White only (Bermudan, callable, calibration, exposure).
sr::Params sr_hw(const In& in, bool with_sigma = true) {
    sr::Params p{};
    p.model = sr::Model::HullWhite;
    p.a = in.real("mean_reversion");
    sr_positive(p.a, "mean_reversion");
    if (with_sigma) {
        p.sigma = in.real("sigma");
        sr_positive(p.sigma, "sigma");
    }
    p.curve = sr_curve(in);
    return p;
}

// Payment times: at least one, strictly increasing, the first after `after`.
Vec sr_payments(const In& in, const char* key, double after) {
    if (!std::isfinite(after)) throw Error("E_DOMAIN", "the start or expiry must be finite", key);  // F-2 first
    const Vec t = sr_reals(in, key);
    limit_if(t.size() > 10000, key);
    if (t.empty()) throw Error("E_INPUT", string(key) + " is empty", key);
    for (std::size_t i = 0; i < t.size(); ++i)
        if (!(t[i] > (i ? t[i - 1] : after))) throw Error("E_INPUT", string(key) + " must increase after the start", key);
    return t;
}

void op_sr_zcb(const In& in, Out& out) {
    const sr::Params p = sr_params(in, false);
    const double t = in.real("t_years"), T = in.real("maturity_years");
    in.ready();
    if (!(t >= 0)) throw Error("E_DOMAIN", "t_years is negative", "t_years");
    if (!(T > t)) throw Error("E_DOMAIN", "maturity_years is not after t_years", "maturity_years");
    const auto [lnA, B] = sr::ln_a_b(p, t, T);
    const double lnP = lnA - B * p.r0;
    out.key_real("discount_factor", std::exp(lnP));
    out.key_real("zero_rate", -lnP / (T - t));
}

void sr_option_dates(double T, double S, double K) {
    if (!(T > 0)) throw Error("E_DOMAIN", "expiry_years is not positive", "expiry_years");
    if (!(S > T)) throw Error("E_DOMAIN", "maturity_years is not after expiry_years", "maturity_years");
    if (!(K > 0)) throw Error("E_DOMAIN", "strike is not positive", "strike");
}

void op_sr_zcb_option(const In& in, Out& out) {
    const sr::Params p = sr_params(in, true);
    const double T = in.real("expiry_years"), S = in.real("maturity_years"), K = in.real("strike");
    const double notional = in.real("notional");
    const bool call = sr_enum<bool>(in, "option_type", {{"CALL", true}, {"PUT", false}});
    in.ready();
    sr_option_dates(T, S, K);
    out.key_real("price", notional * sr::bond_option(p, T, S, K, call));
    out.key_real("bond_price_expiry", sr::bond0(p, T));
    out.key_real("bond_price_maturity", sr::bond0(p, S));
}

void op_sr_swaption(const In& in, Out& out) {
    const sr::Params p = sr_params(in, true, true);
    const double T0 = in.real("expiry_years");
    if (!(T0 > 0)) throw Error("E_DOMAIN", "expiry_years is not positive", "expiry_years");
    const Vec pay = sr_payments(in, "payment_times", T0);
    const double K = in.real("fixed_rate"), notional = in.real("notional");
    const bool payer = sr_enum<bool>(in, "swaption_type", {{"PAYER", true}, {"RECEIVER", false}});
    in.ready();
    const sr::Swaption s = sr::swaption(p, T0, pay, K, payer);
    out.key_real("price", notional * s.price);
    out.key_real("forward_swap_rate", s.forward_swap_rate);
    out.key_real("annuity", notional * s.annuity);
}

void op_sr_capfloor(const In& in, Out& out) {
    const sr::Params p = sr_params(in, true);
    const Vec t = sr_reals(in, "period_times");
    limit_if(t.size() > 10000, "period_times");
    if (t.size() < 2) throw Error("E_INPUT", "period_times needs at least two times", "period_times");
    for (std::size_t i = 1; i < t.size(); ++i)
        if (!(t[i] > t[i - 1])) throw Error("E_INPUT", "period_times must increase", "period_times");
    if (!(t[0] > 0)) throw Error("E_DOMAIN", "the first period time is not positive", "period_times");
    const double K = in.real("strike"), notional = in.real("notional");
    for (std::size_t i = 1; i < t.size(); ++i)
        if (!(1 + K * (t[i] - t[i - 1]) > 0)) throw Error("E_DOMAIN", "1 + strike x accrual is not positive", "strike");
    const bool cap = sr_enum<bool>(in, "cap_floor", {{"CAP", true}, {"FLOOR", false}});
    in.ready();
    sr::CapFloor c = sr::capfloor(p, t, K, cap);
    for (double& v : c.caplets) v *= notional;
    out.key_real("price", notional * c.price);
    out.key_reals("caplet_prices", c.caplets);
}

void op_sr_hw_calibrate(const In& in, Out& out) {
    const sr::Params p = sr_hw(in, false);
    const Value& list = in.need("swaptions");
    if (list.kind != Kind::Array) schema("swaptions", "expected an array");
    limit_if(list.items.size() > 10000, "swaptions");
    if (list.items.empty()) throw Error("E_INPUT", "swaptions is empty", "swaptions");
    std::vector<sr::CalSwaption> strip;
    for (const Value& v : list.items) {
        if (v.kind != Kind::Object) schema("swaptions", "expected an object");
        const In q(v);
        sr::CalSwaption s{};
        s.expiry = q.real("expiry_years");
        if (!(s.expiry > 0)) throw Error("E_DOMAIN", "expiry_years is not positive", "expiry_years");
        s.payment_times = sr_payments(q, "payment_times", s.expiry);
        s.fixed_rate = q.real("fixed_rate");
        s.payer = sr_enum<bool>(q, "swaption_type", {{"PAYER", true}, {"RECEIVER", false}});
        s.target = q.real("target_price");
        q.ready();
        if (!(s.target >= 0)) throw Error("E_DOMAIN", "target_price is negative", "target_price");
        strip.push_back(std::move(s));
    }
    in.ready();
    const sr::Calibration c = sr::hw_calibrate(p.curve, p.a, strip);
    out.key_real("sigma", c.sigma);
    out.key_reals("fitted_prices", c.fitted);
    out.key_real("rmse", c.rmse);
}

sr::Grid sr_grid(const In& in) {
    const Value& gv = in.need("grid");
    if (gv.kind != Kind::Object) schema("grid", "expected an object");
    const In g(gv);
    sr::Grid r{g.integer("nx"), g.integer("steps_per_year"), g.real("width")};
    g.ready();
    if (r.nx < 5 || r.nx % 2 == 0) throw Error("E_INPUT", "nx must be odd and at least 5", "nx");
    limit_if(r.nx > 10001, "nx");
    if (r.steps_per_year < 1) throw Error("E_INPUT", "steps_per_year must be at least 1", "steps_per_year");
    limit_if(r.steps_per_year > 100000, "steps_per_year");
    if (!(r.width > 0)) throw Error("E_DOMAIN", "width is not positive", "width");
    return r;
}

// G-31: combined grid work nx x total steps over the knot intervals at most 5e8.
void sr_grid_work(const sr::Grid& g, const Vec& knots) {
    double steps = 0.0, prev = 0.0;
    for (double t : knots) {
        steps += std::max(1.0, std::ceil(static_cast<double>(g.steps_per_year) * (t - prev)));
        prev = t;
    }
    limit_if(static_cast<double>(g.nx) * steps > 5e8, "grid");
}

bool sr_contains(const Vec& v, double x) { return std::find(v.begin(), v.end(), x) != v.end(); }

void op_sr_bermudan(const In& in, Out& out) {
    const sr::Params p = sr_hw(in);
    const double T0 = in.real("start_years");
    if (!(T0 > 0)) throw Error("E_DOMAIN", "start_years is not positive", "start_years");
    const Vec pay = sr_payments(in, "payment_times", T0);
    const double K = in.real("fixed_rate"), notional = in.real("notional");
    const bool payer = sr_enum<bool>(in, "swaption_type", {{"PAYER", true}, {"RECEIVER", false}});
    const Vec ex = sr_reals(in, "exercise_times");
    limit_if(ex.size() > 10000, "exercise_times");
    Vec resets{T0};
    resets.insert(resets.end(), pay.begin(), pay.end() - 1);
    if (ex.empty()) throw Error("E_INPUT", "exercise_times is empty", "exercise_times");
    for (std::size_t i = 0; i < ex.size(); ++i) {
        if (i && !(ex[i] > ex[i - 1])) throw Error("E_INPUT", "exercise_times must increase", "exercise_times");
        if (!sr_contains(resets, ex[i])) throw Error("E_INPUT", "an exercise time is not a reset date", "exercise_times");
    }
    const sr::Grid g = sr_grid(in);
    sr_grid_work(g, ex);
    in.ready();
    out.key_real("price", notional * sr::bermudan_swaption(p, pay, K, payer, ex, g));
}

void op_sr_bermudan_ladder(const In& in, Out& out) {
    const sr::Params p = sr_hw(in);
    const Vec P = In(in.need("curve")).reals("discount_factors");
    const double T0 = in.real("start_years");
    if (!(T0 > 0)) throw Error("E_DOMAIN", "start_years is not positive", "start_years");
    const Vec pay = sr_payments(in, "payment_times", T0);
    const double K = in.real("fixed_rate"), notional = in.real("notional");
    const bool payer = sr_enum<bool>(in, "swaption_type", {{"PAYER", true}, {"RECEIVER", false}});
    const Vec ex = sr_reals(in, "exercise_times");
    limit_if(ex.size() > 10000, "exercise_times");
    Vec resets{T0};
    resets.insert(resets.end(), pay.begin(), pay.end() - 1);
    if (ex.empty()) throw Error("E_INPUT", "exercise_times is empty", "exercise_times");
    for (std::size_t i = 0; i < ex.size(); ++i) {
        if (i && !(ex[i] > ex[i - 1])) throw Error("E_INPUT", "exercise_times must increase", "exercise_times");
        if (!sr_contains(resets, ex[i])) throw Error("E_INPUT", "an exercise time is not a reset date", "exercise_times");
    }
    const sr::Grid g = sr_grid(in);
    sr_grid_work(g, ex);
    in.ready();
    sr::Ladder l = sr::bermudan_ladder(p, P, pay, K, payer, ex, g);
    for (double& v : l.d_discount_factors) v *= notional;
    out.key_real("price", notional * l.price);
    out.key_reals("d_price_d_discount_factors", l.d_discount_factors);
    out.key_real("d_price_d_mean_reversion", notional * l.d_mean_reversion);
    out.key_real("d_price_d_sigma", notional * l.d_sigma);
}

void op_sr_callable(const In& in, Out& out) {
    const sr::Params p = sr_hw(in);
    const Vec pay = sr_payments(in, "payment_times", 0.0);
    const double c = in.real("coupon_rate"), notional = in.real("notional");
    const Vec calls = sr_reals(in, "call_times");
    limit_if(calls.size() > 10000, "call_times");
    for (std::size_t i = 0; i < calls.size(); ++i) {
        if (i && !(calls[i] > calls[i - 1])) throw Error("E_INPUT", "call_times must increase", "call_times");
        if (!sr_contains(pay, calls[i]) || calls[i] == pay.back())
            throw Error("E_INPUT", "a call time is not a payment time before the last", "call_times");
    }
    const double cp = in.real("call_price");
    sr_positive(cp, "call_price");
    const sr::Grid g = sr_grid(in);
    sr_grid_work(g, pay);
    in.ready();
    out.key_real("price", notional * sr::callable_bond(p, pay, c, calls, cp, g));
}

sr::G2 g2_params(const In& in) {
    sr::G2 m{};
    m.a = in.real("a");
    m.sigma = in.real("sigma");
    m.b = in.real("b");
    m.eta = in.real("eta");
    m.rho = in.real("rho");
    sr_positive(m.a, "a");
    sr_positive(m.sigma, "sigma");
    sr_positive(m.b, "b");
    sr_positive(m.eta, "eta");
    if (!(m.rho > -1 && m.rho < 1)) throw Error("E_DOMAIN", "rho must lie strictly inside (-1, 1)", "rho");
    m.curve = sr_curve(in);
    return m;
}

void op_g2_zcb(const In& in, Out& out) {
    const sr::G2 m = g2_params(in);
    const double x = in.real("x"), y = in.real("y"), t = in.real("t_years"), T = in.real("maturity_years");
    in.ready();
    if (!(t >= 0)) throw Error("E_DOMAIN", "t_years is negative", "t_years");
    if (!(T > t)) throw Error("E_DOMAIN", "maturity_years is not after t_years", "maturity_years");
    const double P = sr::g2_bond(m, t, T, x, y);
    out.key_real("discount_factor", P);
    out.key_real("zero_rate", -std::log(P) / (T - t));
}

void op_g2_zcb_option(const In& in, Out& out) {
    const sr::G2 m = g2_params(in);
    if (in.find("x") || in.find("y")) throw Error("E_INPUT", "x and y are not allowed for options (both start at 0)", "x");
    const double T = in.real("expiry_years"), S = in.real("maturity_years"), K = in.real("strike");
    const double notional = in.real("notional");
    const bool call = sr_enum<bool>(in, "option_type", {{"CALL", true}, {"PUT", false}});
    in.ready();
    sr_option_dates(T, S, K);
    out.key_real("price", notional * sr::g2_bond_option(m, T, S, K, call));
    out.key_real("bond_price_expiry", m.curve.df(T));
    out.key_real("bond_price_maturity", m.curve.df(S));
}

void op_xva_swap_ee_hw(const In& in, Out& out) {
    const sr::Params p = sr_hw(in);
    const bool pay_side = sr_enum<bool>(in, "side", {{"PAY", true}, {"RECEIVE", false}});
    const double T0 = in.real("start_years");
    if (!(T0 >= 0)) throw Error("E_DOMAIN", "start_years is negative", "start_years");
    const Vec pay = sr_payments(in, "payment_times", T0);
    const double K = in.real("fixed_rate"), notional = in.real("notional");
    const Vec et = sr_reals(in, "exposure_times");
    limit_if(et.size() > 10000, "exposure_times");
    if (et.empty()) throw Error("E_INPUT", "exposure_times is empty", "exposure_times");
    for (double t : et)
        if (!(t > 0)) throw Error("E_DOMAIN", "an exposure time is not positive", "exposure_times");
    Vec resets{T0};
    resets.insert(resets.end(), pay.begin(), pay.end() - 1);
    for (std::size_t i = 0; i < et.size(); ++i) {
        if (i && !(et[i] > et[i - 1])) throw Error("E_INPUT", "exposure_times must increase", "exposure_times");
        if (!sr_contains(resets, et[i])) throw Error("E_INPUT", "an exposure time is not a reset date", "exposure_times");
    }
    const bool has_h = in.find("hazard_rate") != nullptr, has_r = in.find("recovery") != nullptr;
    if (has_h != has_r) throw Error("E_INPUT", "hazard_rate and recovery come together", has_h ? "recovery" : "hazard_rate");
    std::optional<std::pair<double, double>> hr;
    if (has_h) {
        const double h = in.real("hazard_rate"), R = in.real("recovery");
        if (!(h >= 0)) throw Error("E_DOMAIN", "hazard_rate is negative", "hazard_rate");
        if (!(R >= 0 && R < 1)) throw Error("E_DOMAIN", "recovery must lie in [0, 1)", "recovery");
        hr = std::pair{h, R};
    }
    in.ready();
    sr::Exposure e = sr::swap_ee_hw(p, T0, pay, K, pay_side, et, hr);
    for (double& v : e.discounted_ee) v *= notional;
    out.key_reals("discounted_ee", e.discounted_ee);
    if (e.cva) out.key_real("cva", notional * *e.cva);
}

void op_xva_portfolio_hw(const In& in, Out& out) {
    const sr::Params p = sr_hw(in);
    const Value& tv = in.need("trades");
    if (tv.kind != Kind::Array) schema("trades", "expected an array");
    limit_if(tv.items.size() > 10000, "trades");
    if (tv.items.empty()) throw Error("E_INPUT", "no trades", "trades");
    std::vector<sr::SwapTrade> trades;
    for (const Value& v : tv.items) {
        if (v.kind != Kind::Object) schema("trades", "expected an object");
        const In q(v);
        sr::SwapTrade t{};
        t.notional = q.real("notional");
        t.fixed_rate = q.real("fixed_rate");
        t.pay = sr_enum<bool>(q, "side", {{"PAY", true}, {"RECEIVE", false}});
        t.start = q.real("start_years");
        if (!std::isfinite(t.start) || !(t.start >= 0)) throw Error("E_DOMAIN", "start_years must be finite and >= 0", "start_years");
        t.payment_times = sr_payments(q, "payment_times", t.start);
        q.ready();
        trades.push_back(std::move(t));
    }
    // Common reset dates (G-42): every reset date of the set inside a trade's life is a reset date of that trade.
    std::set<double> all;
    double last = 0.0;
    for (const auto& t : trades) {
        all.insert(t.start);
        for (std::size_t i = 0; i + 1 < t.payment_times.size(); ++i) all.insert(t.payment_times[i]);
        last = std::max(last, t.payment_times.back());
    }
    for (const auto& t : trades) {
        Vec own{t.start};
        own.insert(own.end(), t.payment_times.begin(), t.payment_times.end() - 1);
        for (double r : all)
            if (r >= t.start && r < t.payment_times.back() && !sr_contains(own, r))
                throw Error("E_INPUT", "the trades do not share their reset dates", "trades");
    }
    const Vec et = sr_reals(in, "exposure_times");
    limit_if(et.size() > 10000, "exposure_times");
    if (et.empty()) throw Error("E_INPUT", "exposure_times is empty", "exposure_times");
    for (std::size_t i = 0; i < et.size(); ++i) {
        if (!(et[i] > 0)) throw Error("E_DOMAIN", "an exposure time is not positive", "exposure_times");
        if (i && !(et[i] > et[i - 1])) throw Error("E_INPUT", "exposure_times must increase", "exposure_times");
        if (!all.count(et[i]) || !(et[i] < last)) throw Error("E_INPUT", "an exposure time is not a reset date", "exposure_times");
    }
    const Vec qs = sr_reals(in, "pfe_quantiles");
    limit_if(qs.size() > 100, "pfe_quantiles");
    for (double q : qs)
        if (!(q > 0 && q < 1)) throw Error("E_DOMAIN", "a PFE quantile is outside (0, 1)", "pfe_quantiles");
    const double h = in.real("hazard_rate"), R = in.real("recovery");
    in.ready();
    if (!(h >= 0)) throw Error("E_DOMAIN", "hazard_rate is negative", "hazard_rate");
    if (!(R >= 0 && R < 1)) throw Error("E_DOMAIN", "recovery must lie in [0, 1)", "recovery");
    const sr::PortfolioExposure e = sr::portfolio_exposure_hw(p, trades, et, qs, h, R);
    out.key_reals("discounted_ee", e.discounted_ee);
    out.key_reals("discounted_ene", e.discounted_ene);
    for (std::size_t i = 0; i < qs.size(); ++i) {
        // R6-5.1, R6-5.6: quantiles of the numeraire-deflated exposure, so named deflated_pfe_<100 q>.
        const double pct = qs[i] * 100;
        char name[32];
        if (std::fabs(pct - std::round(pct)) < 1e-9) std::snprintf(name, sizeof name, "deflated_pfe_%d", static_cast<int>(std::lround(pct)));
        else std::snprintf(name, sizeof name, "deflated_pfe_%g", pct);
        out.key_reals(name, e.pfe[i]);
    }
    out.key_real("epe", e.epe);
    out.key_real("cva", e.cva);
}

void op_mc_greeks(const In& in, Out& out) {
    mcg::Inputs q{};
    q.payoff = sr_enum<mcg::Payoff>(in, "payoff", {{"CALL", mcg::Payoff::Call}, {"PUT", mcg::Payoff::Put}, {"DIGITAL_CALL", mcg::Payoff::DigitalCall}});
    q.method = sr_enum<mcg::Method>(in, "method", {{"PATHWISE", mcg::Method::Pathwise}, {"LIKELIHOOD_RATIO", mcg::Method::LikelihoodRatio}, {"BUMP", mcg::Method::Bump}});
    q.paths = in.integer("paths");
    if (q.paths < 2) throw Error("E_INPUT", "paths must be at least 2", "paths");
    limit_if(q.paths > 10000000, "paths");
    q.seed = in.u64("seed");
    q.spot = in.real("spot");
    q.strike = in.real("strike");
    q.expiry_years = in.real("expiry_years");
    q.rate = in.real("rate");
    q.dividend_yield = in.real("dividend_yield");
    q.vol = in.real("vol");
    sr_positive(q.spot, "spot");
    sr_positive(q.strike, "strike");
    sr_positive(q.expiry_years, "expiry_years");
    sr_positive(q.vol, "vol");
    const bool want_eps = q.method == mcg::Method::Pathwise && q.payoff == mcg::Payoff::DigitalCall;
    const bool want_h = q.method == mcg::Method::Bump;
    const bool has_eps = in.find("smoothing_width") != nullptr, has_h = in.find("bump_relative") != nullptr;
    if (want_eps != has_eps) throw Error("E_INPUT", "smoothing_width is required for a pathwise digital only", "smoothing_width");
    if (want_h != has_h) throw Error("E_INPUT", "bump_relative is required for BUMP only", "bump_relative");
    if (has_eps) {
        q.smoothing_width = in.real("smoothing_width");
        sr_positive(q.smoothing_width, "smoothing_width");
    }
    if (has_h) {
        q.bump_relative = in.real("bump_relative");
        if (!(q.bump_relative > 0 && q.bump_relative < 1)) throw Error("E_DOMAIN", "bump_relative must lie in (0, 1)", "bump_relative");
    }
    in.ready();
    const mcg::Result r = mcg::greeks(q);
    out.key_real("price", r.price);
    out.key_real("price_se", r.price_se);
    out.key_real("delta", r.delta);
    out.key_real("delta_se", r.delta_se);
    out.key_real("vega", r.vega);
    out.key_real("vega_se", r.vega_se);
}

constexpr Entry shortrate_ops[] = {
    {"rates.shortrate.zcb", op_sr_zcb},
    {"rates.shortrate.zcb_option", op_sr_zcb_option},
    {"rates.shortrate.swaption", op_sr_swaption},
    {"rates.shortrate.capfloor", op_sr_capfloor},
    {"rates.shortrate.hw_calibrate", op_sr_hw_calibrate},
    {"rates.shortrate.bermudan_swaption", op_sr_bermudan},
    {"rates.shortrate.callable_bond", op_sr_callable},
    {"rates.shortrate.bermudan_ladder", op_sr_bermudan_ladder},
    {"rates.g2pp.zcb", op_g2_zcb},
    {"rates.g2pp.zcb_option", op_g2_zcb_option},
    {"xva.exposure.swap_ee_hw", op_xva_swap_ee_hw},
    {"risk.mc.greeks", op_mc_greeks},
    {"xva.exposure.portfolio_hw", op_xva_portfolio_hw},
};

namespace lmmns = quantforge::lmm;

lmmns::Abcd lmm_abcd(const In& in) {
    const Value& av = in.need("abcd");
    if (av.kind != Kind::Object) schema("abcd", "expected an object");
    const In a(av);
    lmmns::Abcd v{a.real("a"), a.real("b"), a.real("c"), a.real("d")};
    a.ready();
    if (!(v.c > 0)) throw Error("E_DOMAIN", "c is not positive", "abcd");
    if (!(v.d >= 0)) throw Error("E_DOMAIN", "d is negative", "abcd");
    if (!(v.a + v.d > 0)) throw Error("E_DOMAIN", "a + d is not positive", "abcd");
    return v;
}

void op_lmm_capfloor(const In& in, Out& out) {
    const sr::Curve c = sr_curve(in);
    const lmmns::Abcd v = lmm_abcd(in);
    const Vec t = sr_reals(in, "period_times");
    limit_if(t.size() > 10000, "period_times");
    if (t.size() < 2) throw Error("E_INPUT", "period_times needs at least two times", "period_times");
    for (std::size_t i = 1; i < t.size(); ++i)
        if (!(t[i] > t[i - 1])) throw Error("E_INPUT", "period_times must increase", "period_times");
    if (!(t[0] > 0)) throw Error("E_DOMAIN", "the first fixing is not after 0", "period_times");
    const double K = in.real("strike"), notional = in.real("notional");
    if (!(K > 0)) throw Error("E_DOMAIN", "strike is not positive (lognormal)", "strike");
    const bool cap = sr_enum<bool>(in, "cap_floor", {{"CAP", true}, {"FLOOR", false}});
    in.ready();
    lmmns::CapFloor r = lmmns::capfloor(c, v, t, K, cap);
    for (double& x : r.caplets) x *= notional;
    out.key_real("price", notional * r.price);
    out.key_reals("caplet_prices", r.caplets);
    out.key_reals("forward_rates", r.forwards);
    out.key_reals("black_vols", r.black_vols);
}

void op_lmm_swaption(const In& in, Out& out) {
    const sr::Curve c = sr_curve(in);
    const lmmns::Abcd v = lmm_abcd(in);
    const double beta = in.real("correlation_beta");
    if (!(beta >= 0)) throw Error("E_DOMAIN", "correlation_beta is negative", "correlation_beta");
    const double T0 = in.real("expiry_years");
    if (!(T0 > 0)) throw Error("E_DOMAIN", "expiry_years is not positive", "expiry_years");
    const Vec pay = sr_payments(in, "payment_times", T0);
    const double K = in.real("fixed_rate"), notional = in.real("notional");
    if (!(K > 0)) throw Error("E_DOMAIN", "fixed_rate is not positive (lognormal)", "fixed_rate");
    const bool payer = sr_enum<bool>(in, "side", {{"PAY", true}, {"RECEIVE", false}});
    in.ready();
    const lmmns::Swaption s = lmmns::swaption_rebonato(c, v, beta, T0, pay, K, payer);
    out.key_real("price", notional * s.price);
    out.key_real("swap_rate", s.swap_rate);
    out.key_real("annuity", s.annuity);
    out.key_real("black_vol", s.black_vol);
}

constexpr Entry lmm_ops[] = {
    {"rates.lmm.capfloor", op_lmm_capfloor},
    {"rates.lmm.swaption_rebonato", op_lmm_swaption},
};
