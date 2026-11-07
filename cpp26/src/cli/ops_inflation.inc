// Stage D, D6 inflation. Included by dispatch.cpp after ops_bonds.inc.

long long month_of_text(const Value& v, string_view key) {
    const string& s = to_string(v, key);
    const auto d = s.size() == 7 ? parse_date(s + "-01") : std::nullopt;
    if (!d) schema(key, "expected YYYY-MM");
    return month_index(*d);
}

CpiCurve cpi_curve_fields(const In& c) {
    CpiCurve out{month_of_text(c.need("base_month"), "base_month"), c.real("base_cpi"), {}, std::nullopt};
    out.quotes = rows_of<ZcisQuote>(c, "quotes", [](const In& q) { return ZcisQuote{q.real("years"), q.real("rate")}; });
    const Value* s = c.raw().find("seasonality");
    if (!s) schema("seasonality", "missing");
    if (s->kind != Kind::Null) out.seasonality = to_reals(*s, "seasonality");
    return out;
}

CpiCurve cpi_curve_of(const In& in) {
    const Value& v = in.need("curve");
    if (v.kind != Kind::Object) schema("curve", "expected an object");
    return cpi_curve_fields(In(v));
}

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
