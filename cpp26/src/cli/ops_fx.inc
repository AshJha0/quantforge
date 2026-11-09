// CLI handlers, the fx verbs.
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.

void op_fx_spot_date(const In& in, Out& out) {
    const FxPair* p = pair_of(in);
    const Date d = in.date("trade_date");
    in.ready();
    out.key_string("spot_date", format_date(fx_spot_date(*p, d)));
}

void op_fx_outright(const In& in, Out& out) {
    const FxInput f = fx_input(in);
    const Date value_date = in.date("value_date");
    in.ready();
    f.limit();
    const FxOutright r = with_market(f, [&](const FxMarket& m) { return fx_outright(m, value_date); });
    out.key_real("forward", r.forward);
    out.key_real("points", r.points);
}

void op_fx_forward_pv(const In& in, Out& out) {
    const FxInput f = fx_input(in);
    const auto snapshot = snapshot_of_input(in);
    const FxForwardTrade t = fx_trade_of(in.need("trade"), "trade");
    in.ready();
    f.limit();
    FxPrice p = with_market(f, [&](const FxMarket& m) { return fx_forward_price(m, t); });
    p.valuation.data_version = snapshot;
    write_valuation(out, p.valuation);
    out.key_real("fx_delta", p.fx_delta);
}

void op_fx_swap_pv(const In& in, Out& out) {
    const FxInput f = fx_input(in);
    const Value& tv = in.need("trade");
    if (tv.kind != Kind::Object) schema("trade", "expected an object");
    const In t(tv);
    const FxSwapTrade trade{t.real("notional_base"), t.date("near_date"), t.real("near_rate"), t.date("far_date"),
                            t.real("far_rate"), t.choice("far_side", fx_sides)};
    const auto snapshot = snapshot_of_input(in);
    in.ready();
    f.limit();
    FxPrice p = with_market(f, [&](const FxMarket& m) { return fx_swap_price(m, trade); });
    p.valuation.data_version = snapshot;
    write_valuation(out, p.valuation);
    out.key_real("fx_delta", p.fx_delta);
}

void op_fx_implied(const In& in, Out& out) {
    const FxInput f = fx_input(in);
    const Value& a = in.need("points");
    if (a.kind != Kind::Array) schema("points", "expected an array");
    std::vector<FxPoint> points;
    for (const Value& v : a.items) {
        if (v.kind != Kind::Object) schema("points", "expected an object");
        const In p(v);
        const Tenor t = parse_tenor(p.text("tenor"));
        if (t.unit != 'M' && t.unit != 'Y') schema("tenor", "must be in months or years");
        points.push_back({t, p.real("points")});
    }
    in.ready();
    f.limit();
    limit_if(points.size() > max_quotes, "points");
    const auto nodes = with_market(f, [&](const FxMarket& m) { return fx_implied(m, points); });
    out.values.key("nodes");
    out.values.begin_array();
    for (const FxNode& n : nodes) {
        out.values.begin_object();
        out.key_string("value_date", format_date(n.value_date));
        out.key_real("implied_ratio", n.implied_ratio);
        out.key_real("basis_bp", n.basis_bp);
        out.values.end_object();
    }
    out.values.end_array();
}

void op_xccy_bootstrap(const In& in, Out& out) {
    const CurveInput dom = curve_of(in, "domestic"), fp = curve_of(in, "foreign_projection");
    const Value& dc = in.need("domestic_convention");
    const Value& fc = in.need("foreign_convention");
    const Date start = in.date("start");
    const auto quotes = rows_of<XccyQuote>(in, "quotes", [](const In& q) { return XccyQuote{q.integer("months"), q.real("spread")}; });
    const auto interpolation = in.choice("interpolation", curve_interpolations);
    (void)dc;
    (void)fc;
    in.ready();
    dom.limit();
    fp.limit();
    limit_if(quotes.size() > max_quotes, "quotes");
    xccy_conventions(in);
    const SolvedCurve s = xccy_bootstrap(fp.build(), start, quotes, interpolation);
    (void)dom.build();
    write_pillars(out, s.curve);
    out.diagnostic("max_repricing_error", s.max_repricing_error);
}

void op_xccy_pv(const In& in, Out& out) {
    const CurveInput dom = curve_of(in, "domestic"), fp = curve_of(in, "foreign_projection"), fd = curve_of(in, "foreign_discount");
    const double spot = in.real("spot");
    const Value& tv = in.need("trade");
    if (tv.kind != Kind::Object) schema("trade", "expected an object");
    const In t(tv);
    const Date start = t.date("start");
    const long long months = t.integer("months");
    const double nf = t.real("foreign_notional"), spread = t.real("spread");
    const double sign = t.choice<double>("side", {{"RECEIVE_FOREIGN", 1.0}, {"PAY_FOREIGN", -1.0}});
    in.ready();
    dom.limit();
    fp.limit();
    fd.limit();
    if (!(spot > 0.0)) throw Error("E_DOMAIN", "spot is not positive", "spot");
    const auto dates = xccy_schedule(start, months);
    const Curve d = dom.build();
    const double foreign = xccy_leg(dates, nf, fp.build(), fd.build(), spread);
    const double domestic = xccy_leg(dates, nf * spot, d, d, 0.0);
    out.key_real("pv", sign * (spot * foreign - domestic));
    out.key_real("foreign_leg", foreign);
    out.key_real("domestic_leg", domestic);
}

void op_ndf_pv(const In& in, Out& out) {
    const CurveInput u = curve_of(in, "usd_curve"), o = curve_of(in, "offshore_curve");
    const double spot = in.real("spot");
    const Value& tv = in.need("trade");
    if (tv.kind != Kind::Object) schema("trade", "expected an object");
    const In t(tv);
    const Date fixing_date = t.date("fixing_date"), payment_date = t.date("payment_date");
    const double strike = t.real("strike"), n = t.real("usd_notional");
    const double sign = t.choice<double>("side", {{"BUY", 1.0}, {"SELL", -1.0}});
    const Value* fv = in.raw().find("fixing");
    if (!fv) schema("fixing", "missing");
    const std::optional<double> fixing = fv->kind == Kind::Null ? std::nullopt : std::optional<double>(to_real(*fv, "fixing"));
    in.ready();
    u.limit();
    o.limit();
    const NdfPrice p = ndf_price(u.build(), o.build(), spot, fixing_date, payment_date, strike, n, sign, fixing);
    out.key_real("pv", p.pv);
    out.key_real("forward", p.forward);
}

void op_fx_option_price(const In& in, Out& out) {
    const GkMarket m = fx_market_of(in);
    const double k = in.real("strike"), v = in.real("vol"), n = in.real("notional");
    const OptionType type = in.choice("option_type", option_types);
    in.ready();
    const GkPrice p = fx_option_price(m, k, v, type, n);
    out.key_real("price", p.price);
    out.key_real("premium_pct_foreign", p.premium_pct_foreign);
    out.key_real("forward", p.forward);
    out.key_real("delta", p.delta);
    out.key_real("gamma", p.gamma);
    out.key_real("vega", p.vega);
}

void op_fx_delta_from_strike(const In& in, Out& out) {
    const GkMarket m = fx_market_of(in);
    const double k = in.real("strike"), v = in.real("vol");
    const OptionType type = in.choice("option_type", option_types);
    in.ready();
    const FxDeltas d = fx_deltas_from_strike(m, k, v, type);
    out.values.key("deltas");
    out.values.begin_object();
    out.key_real("SPOT", d.spot);
    out.key_real("FORWARD", d.forward);
    out.key_real("SPOT_PA", d.spot_pa);
    out.key_real("FORWARD_PA", d.forward_pa);
    out.values.end_object();
}

void op_fx_delta_to_strike(const In& in, Out& out) {
    const GkMarket m = fx_market_of(in);
    const double v = in.real("vol"), delta = in.real("delta");
    const OptionType type = in.choice("option_type", option_types);
    const FxDeltaType dt = in.choice("delta_type", fx_delta_types);
    in.ready();
    out.key_real("strike", fx_delta_to_strike(m, v, type, delta, dt));
}

void op_fx_atm_strike(const In& in, Out& out) {
    const GkMarket m = fx_market_of(in);
    const double v = in.real("vol");
    const FxAtmType atm = in.choice("atm_type", fx_atm_types);
    const FxDeltaType dt = in.choice("delta_type", fx_delta_types);
    in.ready();
    out.key_real("strike", fx_atm_strike(m, v, atm, dt));
}

void op_fx_smile_from_quotes(const In& in, Out& out) {
    const GkMarket m = fx_market_of(in);
    const double atm_vol = in.real("atm_vol"), rr = in.real("rr"), bf = in.real("bf"), delta = in.real("delta");
    const FxDeltaType dt = in.choice("delta_type", fx_delta_types);
    const FxAtmType atm = in.choice("atm_type", fx_atm_types);
    in.ready();
    const FxSmile s = fx_smile_from_quotes(m, atm_vol, rr, bf, delta, dt, atm);
    out.key_real("atm_strike", s.atm_strike);
    out.key_real("call_vol", s.call_vol);
    out.key_real("put_vol", s.put_vol);
    out.key_real("call_strike", s.call_strike);
    out.key_real("put_strike", s.put_strike);
}

constexpr Entry fx_ops[] = {
    {"fx.atm.strike", op_fx_atm_strike},
    {"fx.curve.implied", op_fx_implied},
    {"fx.delta.from_strike", op_fx_delta_from_strike},
    {"fx.delta.to_strike", op_fx_delta_to_strike},
    {"fx.forward.outright", op_fx_outright},
    {"fx.forward.pv", op_fx_forward_pv},
    {"fx.ndf.pv", op_ndf_pv},
    {"fx.option.price", op_fx_option_price},
    {"fx.smile.from_quotes", op_fx_smile_from_quotes},
    {"fx.spot_date", op_fx_spot_date},
    {"fx.swap.pv", op_fx_swap_pv},
    {"fx.xccy.bootstrap", op_xccy_bootstrap},
    {"fx.xccy.pv", op_xccy_pv},
};
