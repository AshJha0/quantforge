// Stage C: Black models, Greeks and the equity option.

constexpr EnumTable<VolModel> vol_models = {{"BLACK_SCHOLES", VolModel::BlackScholes},
                                            {"BLACK_76", VolModel::Black76},
                                            {"BACHELIER", VolModel::Bachelier}};

OptionInput option_of(const In& in) {
    OptionInput o{in.choice("model", vol_models), in.choice("option_type", option_types), in.real("strike"), in.real("expiry_years")};
    const auto forbid = [&](std::initializer_list<string_view> keys) {
        for (const string_view k : keys)
            if (in.raw().find(k)) schema(k, "not an input of this model");
    };
    if (o.model == VolModel::BlackScholes) {
        forbid({"forward", "discount_factor", "shift"});
        o.spot = in.real("spot");
        o.rate = in.real("rate");
        o.yield = in.real("yield");
    } else {
        forbid({"spot", "rate", "yield"});
        if (o.model == VolModel::Bachelier) forbid({"shift"});  // ruling C8
        o.forward = in.real("forward");
        o.discount_factor = in.real("discount_factor");
        o.shift = optional_real(in, "shift", 0.0);
    }
    return o;
}

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

void op_vol_greeks(const In& in, Out& out) {
    const OptionInput o = option_of(in);
    const double vol = in.real("vol");
    in.ready();
    const Greeks g = option_greeks(o, vol);
    out.key_real("price", g.price);
    out.key_real("delta", g.delta);
    out.key_real("gamma", g.gamma);
    out.key_real("vega", g.vega);
    out.key_real("theta", g.theta);
    out.key_real("rho", g.rho);
    out.key_real("vanna", g.vanna);
    out.key_real("volga", g.volga);
}

void op_vol_bump_greeks(const In& in, Out& out) {
    const OptionInput o = option_of(in);
    const double vol = in.real("vol");
    in.ready();
    const BumpGreeks g = bump_greeks(o, vol);
    out.key_real("delta", g.delta);
    out.key_real("gamma", g.gamma);
    out.key_real("vega", g.vega);
    out.key_real("volga", g.volga);
    out.key_real("vanna", g.vanna);
}

// Black-76 pieces for a signed position: sign q D phi N(phi d1), and so on.
struct PositionRisk {
    double pv, delta_forward, gamma_forward, vega;
};

PositionRisk position_risk(double f, double k, double v, double t, double d, OptionType type, double signed_quantity) {
    OptionInput o{VolModel::Black76, type, k, t};
    o.forward = f;
    o.discount_factor = d;
    const Greeks g = option_greeks(o, v);
    return {signed_quantity * g.price, signed_quantity * g.delta, signed_quantity * g.gamma, signed_quantity * g.vega};
}

const string& currency_of(const In& in) {
    const string& c = in.text("currency");
    if (minor_units(c) < 0) schema("currency", "not listed");
    return c;
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
