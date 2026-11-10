// CLI handlers, the inflation verbs.
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.

void op_infl_cpi(const In& in, Out& out) {
    const CpiCurve c = cpi_curve_fields(in);
    const Value& a = in.need("months");
    if (a.kind != Kind::Array) schema("months", "expected an array");
    std::vector<long long> months;
    for (const Value& v : a.items) months.push_back(month_of_text(v, "months"));
    in.ready();
    limit_if(c.quotes.size() > max_quotes, "quotes");
    c.check();
    if (months.empty()) throw Error("E_INPUT", "no months", "months");
    Vec cpi;
    for (const long long m : months) cpi.push_back(c.cpi(m));
    out.key_reals("cpi", cpi);
}

void op_zcis_pv(const In& in, Out& out) {
    const CpiCurve c = cpi_curve_of(in);
    const CurveInput d = curve_of(in, "discount");
    const Value& tv = in.need("trade");
    if (tv.kind != Kind::Object) schema("trade", "expected an object");
    const In t(tv);
    const double years = t.real("years"), k = t.real("fixed_rate"), n = t.real("notional");
    const double sign = t.choice<double>("side", {{"RECEIVE_INFLATION", 1.0}, {"PAY_INFLATION", -1.0}});
    const Date pay = t.date("payment_date");
    in.ready();
    d.limit();
    limit_if(c.quotes.size() > max_quotes, "quotes");
    const ZcisPrice p = zcis_price(c, d.build(), years, k, n, sign, pay);
    out.key_real("pv", p.pv);
    out.key_real("index_ratio", p.index_ratio);
}

void op_linker_price(const In& in, Out& out) {
    const Bond b = bond_of(in);
    const Date s = in.date("settlement");
    const double y = in.real("real_yield"), base = in.real("base_ref_cpi");
    const auto fixings = rows_of<CpiFixing>(in, "cpi_fixings", [](const In& r) {
        return CpiFixing{month_of_text(r.need("month"), "month"), r.real("value")};
    });
    in.ready();
    const LinkerPrice p = linker_price(b, s, y, base, fixings);
    out.key_real("ref_cpi", p.ref_cpi);
    out.key_real("index_ratio", p.index_ratio);
    out.key_real("real_clean", p.real_clean);
    out.key_real("real_accrued", p.real_accrued);
    out.key_real("nominal_clean", p.nominal_clean);
    out.key_real("nominal_accrued", p.nominal_accrued);
}

void op_linker_price_curve(const In& in, Out& out) {
    const Bond b = bond_of(in);
    const Date s = in.date("settlement");
    const double base = in.real("base_ref_cpi");
    const CpiCurve c = cpi_curve_of(in);
    const CurveInput d = curve_of(in, "discount");
    in.ready();
    d.limit();
    limit_if(c.quotes.size() > max_quotes, "quotes");
    out.key_real("nominal_dirty", linker_price_curve(b, s, base, c, d.build()));
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

constexpr Entry inflation_ops[] = {
    {"infl.cap.yoy_price", op_yoy_cap_price},
    {"infl.cap.zc_price", op_zc_cap_price},
    {"infl.curve.cpi", op_infl_cpi},
    {"infl.linker.price", op_linker_price},
    {"infl.linker.price_curve", op_linker_price_curve},
    {"infl.zcis.pv", op_zcis_pv},
};
