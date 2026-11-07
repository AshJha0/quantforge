// Stage C: delta conventions, smile, SVI, SSVI.

enum class DeltaConvention { Forward, Spot };
constexpr EnumTable<DeltaConvention> delta_conventions = {{"FORWARD", DeltaConvention::Forward}, {"SPOT", DeltaConvention::Spot}};

struct DeltaScale {
    DeltaConvention convention;
    std::optional<double> scale;

    double value() const {
        if (convention == DeltaConvention::Forward) {
            if (scale) throw Error("E_INPUT", "scale must be null for FORWARD");
            return 1.0;
        }
        if (!scale || *scale <= 0) throw Error("E_DOMAIN", "scale is not above 0");
        return *scale;
    }
};

DeltaScale delta_scale_of(const In& in) {
    const DeltaConvention c = in.choice("convention", delta_conventions);
    require_key(in, "scale");
    return {c, to_maybe_real(*in.raw().find("scale"), "scale")};
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

Svi svi_of(const In& in) {
    const Value& v = in.need("svi");
    if (v.kind != Kind::Object) schema("svi", "expected an object");
    const In s(v);
    return {s.real("a"), s.real("b"), s.real("rho"), s.real("m"), s.real("sigma")};
}

void write_svi(Out& out, const Svi& s) {
    out.values.key("svi");
    out.values.begin_object();
    out.key_real("a", s.a);
    out.key_real("b", s.b);
    out.key_real("rho", s.rho);
    out.key_real("m", s.m);
    out.key_real("sigma", s.sigma);
    out.values.end_object();
}

void op_svi_evaluate(const In& in, Out& out) {
    const Svi s = svi_of(in);
    const Vec k = in.reals("log_moneyness");
    const double t = in.real("expiry_years");
    in.ready();
    limit_if(k.size() > max_quotes, "log_moneyness");
    check_svi(s);
    if (t <= 0) throw Error("E_DOMAIN", "expiry_years is not above 0");
    if (k.empty()) throw Error("E_INPUT", "log_moneyness is empty");
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

std::optional<Vec> optional_weights(const In& in) {
    const Value* p = in.raw().find("weights");
    if (!p) return std::nullopt;
    if (p->kind == Kind::Null) schema("weights", "null is not allowed");
    return to_reals(*p, "weights");
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
    const SsviFit fit = ssvi_calibrate(thetas, k, w);
    out.key_real("rho", fit.ssvi.rho);
    out.key_real("eta", fit.ssvi.eta);
    out.key_real("gamma", fit.ssvi.gamma);
    out.key_real("rmse", fit.rmse);
}
