// Stage D, D7 to D9. Included by dispatch.cpp after ops_bonds.inc.

constexpr EnumTable<RateVolModel> rate_vol_models = {{"BLACK_76", RateVolModel::Black76}, {"BACHELIER", RateVolModel::Bachelier}};

void op_cap_price(const In& in, Out& out) {
    const CurveInput d = curve_of(in, "discount"), p = curve_of(in, "projection");
    const auto model = in.choice("model", rate_vol_models);
    const Value& vv = in.need("vol");
    const bool flat = vv.kind != Kind::Array;
    const Vec vols = flat ? Vec{to_real(vv, "vol")} : to_reals(vv, "vol");
    const Value& tv = in.need("trade");
    if (tv.kind != Kind::Object) schema("trade", "expected an object");
    const In t(tv);
    const double phi = t.choice<double>("type", {{"CAP", 1.0}, {"FLOOR", -1.0}});
    const long long start = t.integer("start_months"), tenor = t.integer("tenor_months");
    const double k = t.real("strike"), n = t.real("notional");
    in.ready();
    d.limit();
    p.limit();
    const CapPrice r = cap_price(d.build(), p.build(), model, vols, flat, phi, start, tenor, k, n);
    out.key_real("price", r.price);
    out.key_reals("caplets", r.caplets);
}

void op_swaption_price(const In& in, Out& out) {
    const CurveInput d = curve_of(in, "discount"), p = curve_of(in, "projection");
    const auto model = in.choice("model", rate_vol_models);
    const double vol = in.real("vol");
    const Value& tv = in.need("trade");
    if (tv.kind != Kind::Object) schema("trade", "expected an object");
    const In t(tv);
    const double phi = t.choice<double>("type", {{"PAYER", 1.0}, {"RECEIVER", -1.0}});
    const long long expiry = t.integer("expiry_months"), tenor = t.integer("tenor_months");
    const double k = t.real("strike"), n = t.real("notional");
    in.ready();
    d.limit();
    p.limit();
    const SwaptionPrice r = swaption_price(d.build(), p.build(), model, vol, phi, expiry, tenor, k, n);
    out.key_real("price", r.price);
    out.key_real("forward_rate", r.forward_rate);
    out.key_real("annuity", r.annuity);
}

void op_cmdty_forward(const In& in, Out& out) {
    const auto quotes = rows_of<CommodityQuote>(in, "quotes", [](const In& q) {
        return CommodityQuote{month_of_text(q.need("month"), "month"), q.real("price")};
    });
    const Value* s = in.raw().find("seasonality");
    if (!s) schema("seasonality", "missing");
    std::optional<Vec> season;
    if (s->kind != Kind::Null) season = to_reals(*s, "seasonality");
    const Value& a = in.need("months");
    if (a.kind != Kind::Array) schema("months", "expected an array");
    std::vector<long long> months;
    for (const Value& v : a.items) months.push_back(month_of_text(v, "months"));
    in.ready();
    limit_if(quotes.size() > max_quotes, "quotes");
    out.key_reals("forwards", commodity_forwards(quotes, season, months));
}

void op_storage_carry(const In& in, Out& out) {
    const CurveInput f = curve_of(in, "funding");
    const auto fwd = rows_of<DatedPrice>(in, "forwards", [](const In& r) { return DatedPrice{r.date("date"), r.real("price")}; });
    const double u = in.real("storage_cost");
    in.ready();
    f.limit();
    const StorageCarry r = storage_carry(f.build(), fwd, u);
    out.key_reals("convenience_yields", r.convenience_yields);
    out.key_reals("carry_values", r.carry_values);
    out.values.key("arbitrage");
    out.values.begin_array();
    for (const bool b : r.arbitrage) out.values.boolean(b);
    out.values.end_array();
}

MbsPool pool_of(const In& in) {
    const Value& v = in.need("pool");
    if (v.kind != Kind::Object) schema("pool", "expected an object");
    const In p(v);
    MbsPool out{p.real("balance"), p.real("wac"), p.real("net_coupon"), p.integer("wam"), p.integer("age"), false, 0.0};
    const Value& pv = p.need("prepayment");
    if (pv.kind != Kind::Object) schema("prepayment", "expected an object");
    const In pp(pv);
    out.psa = pp.choice<bool>("model", {{"CPR", false}, {"PSA", true}});
    out.rate_or_speed = pp.real(out.psa ? "speed" : "rate");
    return out;
}

void op_mbs_cashflows(const In& in, Out& out) {
    const MbsPool p = pool_of(in);
    in.ready();
    const MbsCashflows c = mbs_cashflows(p);
    out.key_reals("balance", c.balance);
    out.key_reals("interest", c.interest);
    out.key_reals("scheduled_principal", c.scheduled_principal);
    out.key_reals("prepayment", c.prepayment);
    out.key_real("wal", c.wal);
}

void op_mbs_price(const In& in, Out& out) {
    const MbsPool p = pool_of(in);
    const double y = in.real("yield");
    const long long delay = in.integer("delay_days");
    in.ready();
    const MbsPrice r = mbs_price(p, y, delay);
    out.key_real("price", r.price);
    out.key_real("modified_duration", r.modified_duration);
    out.key_real("wal", r.wal);
}
