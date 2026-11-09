// Stage E, E2: Heston, Bates, Merton, SLV. Included by dispatch.cpp after ops_e1.inc (uses slices_of).

HestonParams heston_of(const In& in) {
    const Value& v = in.need("heston");
    if (v.kind != Kind::Object) schema("heston", "expected an object");
    const In h(v);
    return {h.real("v0"), h.real("kappa"), h.real("theta"), h.real("xi"), h.real("rho")};
}

Jumps jumps_of(const In& in) {
    const Value& v = in.need("jumps");
    if (v.kind != Kind::Object) schema("jumps", "expected an object");
    const In j(v);
    return {j.real("intensity"), j.real("mean_log_jump"), j.real("log_jump_vol")};
}

EquityOption equity_option_of(const In& in) {
    EquityOption o;
    o.spot = in.real("spot");
    o.expiry_years = in.real("expiry_years");
    o.rate = in.real("rate");
    o.dividend_yield = in.real("dividend_yield");
    o.type = in.choice("option_type", option_types);
    o.strikes = in.reals("strikes");
    return o;
}

void op_heston_cf(const In& in, Out& out) {
    const double t = in.real("expiry_years");
    const HestonParams h = heston_of(in);
    const Vec u = in.reals("u");
    in.ready();
    limit_if(u.size() > max_quotes, "u");
    if (u.empty()) throw Error("E_INPUT", "u is empty", "u");
    if (!(t > 0)) throw Error("E_DOMAIN", "expiry_years is not above 0", "expiry_years");
    check_heston(h);
    for (const double x : u)
        if (!(x >= 0)) throw Error("E_DOMAIN", "a u is negative", "u");
    Vec re, im;
    for (const double x : u) {
        const std::complex<double> c = heston_cf(t, h, {x, 0.0});
        re.push_back(c.real());
        im.push_back(c.imag());
    }
    out.key_reals("re", re);
    out.key_reals("im", im);
}

void op_heston_price(const In& in, Out& out) {
    const EquityOption o = equity_option_of(in);
    const HestonParams h = heston_of(in);
    in.ready();
    limit_if(o.strikes.size() > max_quotes, "strikes");
    out.key_reals("prices", heston_price(o, h));
}

void op_bates_price(const In& in, Out& out) {
    const EquityOption o = equity_option_of(in);
    const HestonParams h = heston_of(in);
    const Jumps j = jumps_of(in);
    in.ready();
    limit_if(o.strikes.size() > max_quotes, "strikes");
    out.key_reals("prices", bates_price(o, h, j));
}

void op_merton_price(const In& in, Out& out) {
    const EquityOption o = equity_option_of(in);
    const double vol = in.real("vol");
    const Jumps j = jumps_of(in);
    in.ready();
    limit_if(o.strikes.size() > max_quotes, "strikes");
    out.key_reals("prices", merton_price(o, vol, j));
}

void op_slv_leverage(const In& in, Out& out) {
    const double spot = in.real("spot"), t = in.real("expiry_years"), r = in.real("rate"), q = in.real("dividend_yield");
    const HestonParams h = heston_of(in);
    const auto slices = slices_of(in);
    const Value& gv = in.need("grid");
    if (gv.kind != Kind::Object) schema("grid", "expected an object");
    const In g(gv);
    const SlvGrid grid{g.integer("nx"), g.integer("nv"), g.integer("nt"), g.real("x_min"), g.real("x_max"), g.real("v_max")};
    in.ready();
    const SlvLeverage s = slv_leverage(spot, t, r, q, h, slices, grid);
    out.key_reals("x", s.x);
    out.key_reals("leverage", s.leverage);
    out.key_real("mass", s.mass);
}
