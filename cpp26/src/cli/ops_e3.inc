// Stage E, E3: FX smile. Included by dispatch.cpp after ops_e1.inc.

constexpr EnumTable<FxDeltaType> fx_delta_types = {{"SPOT", FxDeltaType::Spot},
                                                   {"FORWARD", FxDeltaType::Forward},
                                                   {"SPOT_PA", FxDeltaType::SpotPa},
                                                   {"FORWARD_PA", FxDeltaType::ForwardPa}};
constexpr EnumTable<FxAtmType> fx_atm_types = {{"SPOT", FxAtmType::Spot}, {"FORWARD", FxAtmType::Forward}, {"DNS", FxAtmType::Dns}};

GkMarket fx_market_of(const In& in) {
    GkMarket m;
    m.spot = in.real("spot");
    m.expiry_years = in.real("expiry_years");
    m.domestic_rate = in.real("domestic_rate");
    m.foreign_rate = in.real("foreign_rate");
    return m;
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
