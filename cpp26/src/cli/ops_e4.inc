// Stage E, E4: rates and inflation vol. Included by dispatch.cpp after ops_misc_d.inc (uses rate_vol_models).

std::vector<long long> integers_of(const In& in, string_view key) {
    const Value& a = in.need(key);
    if (a.kind != Kind::Array) schema(key, "expected an array");
    std::vector<long long> out;
    for (const Value& v : a.items) out.push_back(to_integer(v, key));
    return out;
}

void op_swaption_price_cube(const In& in, Out& out) {
    const CurveInput d = curve_of(in, "discount"), p = curve_of(in, "projection");
    const Value& cv = in.need("cube");
    if (cv.kind != Kind::Object) schema("cube", "expected an object");
    const In c(cv);
    SabrCube cube{integers_of(c, "expiries_months"), integers_of(c, "tenors_months"), c.matrix("alpha"), c.matrix("beta"),
                  c.matrix("rho"), c.matrix("nu")};
    const Value& tv = in.need("trade");
    if (tv.kind != Kind::Object) schema("trade", "expected an object");
    const In t(tv);
    const double phi = t.choice<double>("type", {{"PAYER", 1.0}, {"RECEIVER", -1.0}});
    const long long expiry = t.integer("expiry_months"), tenor = t.integer("tenor_months");
    const double k = t.real("strike"), n = t.real("notional");
    in.ready();
    d.limit();
    p.limit();
    const CubeSwaption r = swaption_price_cube(d.build(), p.build(), cube, phi, expiry, tenor, k, n);
    out.key_real("price", r.price);
    out.key_real("forward_rate", r.forward_rate);
    out.key_real("annuity", r.annuity);
    out.key_real("vol", r.vol);
    out.values.key("sabr");
    out.values.begin_object();
    out.key_real("alpha", r.sabr.alpha);
    out.key_real("beta", r.sabr.beta);
    out.key_real("rho", r.sabr.rho);
    out.key_real("nu", r.sabr.nu);
    out.values.end_object();
}

void op_cap_strip(const In& in, Out& out) {
    const CurveInput d = curve_of(in, "discount"), p = curve_of(in, "projection");
    const auto model = in.choice("model", rate_vol_models);
    const long long start = in.integer("start_months");
    const double k = in.real("strike");
    const std::vector<long long> tenors = integers_of(in, "cap_tenors_months");
    const Vec flat = in.reals("flat_vols");
    const double n = in.real("notional");
    in.ready();
    d.limit();
    p.limit();
    const CapStrip r = cap_strip(d.build(), p.build(), model, start, k, tenors, flat, n);
    out.key_reals("caplet_vols", r.caplet_vols);
    out.key_reals("cap_prices", r.cap_prices);
}

void op_bondfut_option_price(const In& in, Out& out) {
    const double phi = in.choice<double>("type", {{"CALL", 1.0}, {"PUT", -1.0}});
    const double f = in.real("futures_price"), k = in.real("strike"), t = in.real("expiry_years");
    const double df = in.real("discount_factor"), vol = in.real("vol"), size = in.real("contract_size");
    in.ready();
    const BondFutOption r = bondfut_option_price(phi, f, k, t, df, vol, size);
    out.key_real("price", r.price);
    out.key_real("contract_value", r.contract_value);
}

void op_bondfut_implied_vol(const In& in, Out& out) {
    const double phi = in.choice<double>("type", {{"CALL", 1.0}, {"PUT", -1.0}});
    const double f = in.real("futures_price"), k = in.real("strike"), t = in.real("expiry_years");
    const double df = in.real("discount_factor"), premium = in.real("premium");
    const double y = in.real("ctd_yield"), dm = in.real("ctd_modified_duration");
    in.ready();
    const BondFutVol r = bondfut_implied_vol(phi, f, k, t, df, premium, y, dm);
    out.key_real("price_vol", r.price_vol);
    out.key_real("yield_vol", r.yield_vol);
}

void op_yoy_cap_price(const In& in, Out& out) {
    const auto model = in.choice("model", rate_vol_models);
    const double phi = in.choice<double>("type", {{"CAP", 1.0}, {"FLOOR", -1.0}});
    const double k = in.real("strike"), n = in.real("notional");
    const auto periods = rows_of<YoyPeriod>(in, "periods", [](const In& q) {
        return YoyPeriod{q.real("accrual"), q.real("discount_factor"), q.real("yoy_forward"), q.real("expiry_years"), q.real("vol")};
    });
    in.ready();
    const CapPrice r = yoy_cap_price(model, phi, k, n, periods);
    out.key_reals("caplets", r.caplets);
    out.key_real("price", r.price);
}

void op_zc_cap_price(const In& in, Out& out) {
    const auto model = in.choice("model", rate_vol_models);
    const double phi = in.choice<double>("type", {{"CAP", 1.0}, {"FLOOR", -1.0}});
    const double fi = in.real("forward_index_ratio"), years = in.real("years"), k = in.real("strike");
    const double df = in.real("discount_factor"), vol = in.real("vol"), n = in.real("notional");
    in.ready();
    const ZcCap r = zc_cap_price(model, phi, fi, years, k, df, vol, n);
    out.key_real("price", r.price);
    out.key_real("strike_ratio", r.strike_ratio);
}
