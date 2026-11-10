// CLI handlers, the rates verbs.
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.

void op_schedule(const In& in, Out& out) {
    const Date start = in.date("start"), end = in.date("end");
    const long long f = in.integer("frequency_months");
    if (f != 1 && f != 2 && f != 3 && f != 4 && f != 6 && f != 12) schema("frequency_months", "not listed");
    const Calendar c = in.choice("calendar", calendars);
    const bool eom = in.boolean("end_of_month");
    const long long lag = in.integer("payment_lag");
    in.ready();
    limit_if(lag > 30000, "payment_lag");
    const auto periods = generate_schedule(start, end, f, c, eom, lag);
    out.values.key("periods");
    out.values.begin_array();
    for (const Period& p : periods) {
        out.values.begin_object();
        out.key_string("start", format_date(p.start));
        out.key_string("end", format_date(p.end));
        out.key_string("payment", format_date(p.payment));
        out.values.end_object();
    }
    out.values.end_array();
}

void op_curve_discount(const In& in, Out& out) {
    const CurveInput ci = curve_of(in, "curve");
    const auto dates = dates_of(in, "dates");
    in.ready();
    ci.limit();
    const Curve c = ci.build();
    Vec df;
    std::vector<MaybeReal> zero;
    for (const Date d : dates) {
        df.push_back(c.discount(d));
        if (d == c.as_of()) zero.push_back(std::nullopt);
        else zero.push_back(-std::log(df.back()) / c.time(d));
    }
    out.key_reals("discount_factors", df);
    out.key_maybes("zero_rates", zero);
}

void op_curve_forward(const In& in, Out& out) {
    const CurveInput ci = curve_of(in, "curve");
    const Date start = in.date("start"), end = in.date("end");
    const DayCount dc = in.choice("day_count", plain_day_counts);
    in.ready();
    ci.limit();
    out.key_real("forward", simple_forward(ci.build(), start, end, dc));
}

// Stage F (Q1): discount factors, zero rates and instantaneous forwards of the smooth curve.
void op_curve_inspect(const In& in, Out& out) {
    const CurveInput ci = curve_of(in, "curve");
    const auto dates = dates_of(in, "dates");
    in.ready();
    ci.limit();
    const Curve c = ci.build();
    Vec df, forwards;
    std::vector<MaybeReal> zero;
    for (const Date d : dates) {
        df.push_back(c.discount(d));
        if (d == c.as_of()) zero.push_back(std::nullopt);
        else zero.push_back(-std::log(df.back()) / c.time(d));
        forwards.push_back(c.instantaneous_forward(d));
    }
    out.key_reals("discount_factors", df);
    out.key_maybes("zero_rates", zero);
    out.key_reals("instantaneous_forwards", forwards);
}

void op_ois_bootstrap(const In& in, Out& out) {
    const RateConvention* c = ois_convention_of(in.need("convention"), "convention");
    const Date as_of = in.date("as_of");
    const auto raw = quotes_of(in);
    const auto interpolation = in.choice("interpolation", curve_interpolations);
    const auto method = in.choice<SolveMethod>("method", {{"SEQUENTIAL", SolveMethod::Sequential}, {"GLOBAL", SolveMethod::Global}});
    const auto jumps = jumps_of(in, false);
    const CurveShape shape = curve_shape_of(in);
    in.ready();
    const auto quotes = checked_quotes(raw);
    check_jumps(as_of, jumps);
    check_crossed(raw);
    const SolvedCurve s = ois_bootstrap(*c, as_of, quotes, interpolation, method, jumps, shape);
    write_pillars(out, s.curve);
    out.diagnostic("max_repricing_error", s.max_repricing_error);
}

void op_ois_compound(const In& in, Out& out) {
    const Vec rates = in.reals("rates");
    const Value& d = in.need("days");
    if (d.kind != Kind::Array) schema("days", "expected an array");
    std::vector<long long> days;
    for (const Value& v : d.items) days.push_back(to_integer(v, "days"));
    const long long denominator = in.integer("denominator");
    if (denominator != 360 && denominator != 365) schema("denominator", "must be 360 or 365");
    in.ready();
    out.key_real("compounded_rate", ois_compound(rates, days, double(denominator)));
}

void op_ois_pv(const In& in, Out& out) {
    const CurveInput ci = curve_of(in, "curve");
    const auto snapshot = snapshot_of_input(in);
    const OisTrade trade = ois_trade_of(in.need("trade"));
    in.ready();
    ci.limit();
    const OisPrice p = ois_price(trade, ci.build(), snapshot);
    write_valuation(out, p.valuation);
    out.key_real("par_rate", p.par_rate);
    out.key_real("annuity", p.annuity);
}

void op_projection_bootstrap(const In& in, Out& out) {
    const CurveInput di = curve_of(in, "discount");
    const RateConvention* index = index_of(in.need("index"), "index");
    const Date as_of = in.date("as_of");
    const auto interpolation = in.choice("interpolation", curve_interpolations);
    const Value& a = in.need("quotes");
    if (a.kind != Kind::Array) schema("quotes", "expected an array");
    std::vector<ProjectionQuote> quotes;
    for (const Value& v : a.items) {
        if (v.kind != Kind::Object) schema("quotes", "expected an object");
        const In q(v);
        const auto type = q.choice<ProjectionQuoteType>(
            "type", {{"DEPOSIT", ProjectionQuoteType::Deposit}, {"FRA", ProjectionQuoteType::Fra}, {"SWAP", ProjectionQuoteType::Swap}});
        const long long months = q.integer(type == ProjectionQuoteType::Fra ? "start_months" : "months");
        quotes.push_back({type, months, q.real("rate")});
    }
    in.ready();
    di.limit();
    limit_if(quotes.size() > max_quotes, "quotes");
    for (const ProjectionQuote& q : quotes)
        if (q.months > 1200 || q.months < (q.type == ProjectionQuoteType::Fra ? 0 : 1))
            throw Error("E_INPUT", "months is out of range", "quotes");
    double error = 0.0;
    const Curve c = projection_bootstrap(di.build(), *index, as_of, quotes, interpolation, &error);
    write_pillars(out, c);
    out.diagnostic("max_repricing_error", error);
}

void op_swap_pv(const In& in, Out& out) {
    const CurveInput di = curve_of(in, "discount"), pi = curve_of(in, "projection");
    const auto snapshot = snapshot_of_input(in);
    const Value& tv = in.need("trade");
    if (tv.kind != Kind::Object) schema("trade", "expected an object");
    const In t(tv);
    const SwapTrade trade{index_of(t.need("index"), "index"), t.integer("tenor_months"), t.real("fixed_rate"),
                          t.real("notional"), t.choice("side", fixed_sides)};
    in.ready();
    di.limit();
    pi.limit();
    if (trade.tenor_months < 1 || trade.tenor_months > 1200) throw Error("E_INPUT", "tenor_months is out of range", "tenor_months");
    const SwapPrice p = swap_price(trade, di.build(), pi.build(), snapshot);
    write_valuation(out, p.valuation);
    out.key_real("par_rate", p.par_rate);
}

void op_fra_pv(const In& in, Out& out) {
    const CurveInput di = curve_of(in, "discount"), pi = curve_of(in, "projection");
    const auto snapshot = snapshot_of_input(in);
    const Value& tv = in.need("trade");
    if (tv.kind != Kind::Object) schema("trade", "expected an object");
    const In t(tv);
    const FraTrade trade{index_of(t.need("index"), "index"), t.date("start"), t.real("fixed_rate"), t.real("notional"),
                         t.choice("side", fixed_sides)};
    in.ready();
    di.limit();
    pi.limit();
    const FraPrice p = fra_price(trade, di.build(), pi.build(), snapshot);
    write_valuation(out, p.valuation);
    out.key_real("forward_rate", p.forward_rate);
}

void op_basis_spread(const In& in, Out& out) {
    const CurveInput di = curve_of(in, "discount"), pi = curve_of(in, "projection");
    const RateConvention* index = index_of(in.need("index"), "index");
    const long long months = in.integer("tenor_months");
    in.ready();
    di.limit();
    pi.limit();
    if (months < 1 || months > 1200) throw Error("E_INPUT", "tenor_months is out of range", "tenor_months");
    out.key_real("spread", basis_spread(di.build(), pi.build(), *index, months));
}

void op_compound_dated(const In& in, Out& out) {
    const RateConvention* c = overnight_of(in);
    const Date start = in.date("start"), end = in.date("end");
    const auto method = in.choice<ShiftMethod>("method", {{"NONE", ShiftMethod::None},
                                                          {"LOOKBACK", ShiftMethod::Lookback},
                                                          {"OBSERVATION_SHIFT", ShiftMethod::ObservationShift},
                                                          {"LOCKOUT", ShiftMethod::Lockout}});
    const long long k = in.integer("shift_days");
    const auto fixings = fixings_of(in);
    in.ready();
    const DatedCompound r = compound_dated(*c, start, end, method, k, fixings);
    out.key_real("compounded_rate", r.compounded_rate);
    out.key_real("accrual", r.accrual);
    out.key_real("interest", r.interest);
}

void op_fallback_rate(const In& in, Out& out) {
    const string& ibor = in.text("ibor");
    const Date start = in.date("start"), end = in.date("end");
    const auto fixings = fixings_of(in);
    in.ready();
    const FallbackRate r = fallback_rate(ibor, start, end, fixings);
    out.key_real("compounded_rate", r.compounded_rate);
    out.key_real("spread_adjustment", r.spread_adjustment);
    out.key_real("fallback_rate", r.fallback_rate);
}

void op_step_curve(const In& in, Out& out) {
    StepCurve sc{in.date("as_of"), in.real("base_rate"), {}, {}};
    const Value& a = in.need("steps");
    if (a.kind != Kind::Array) schema("steps", "expected an array");
    for (const Value& v : a.items) {
        if (v.kind != Kind::Object) schema("steps", "expected an object");
        const In row(v);
        sc.steps.push_back({row.date("date"), row.real("rate")});
    }
    sc.jumps = jumps_of(in, true);
    const auto dates = dates_of(in, "dates");
    in.ready();
    sc.check();
    if (dates.empty()) throw Error("E_INPUT", "no dates", "dates");
    Vec df, fwd;
    for (const Date d : dates) {
        df.push_back(sc.discount(d));
        fwd.push_back(sc.forward(d));
    }
    out.key_reals("discount_factors", df);
    out.key_reals("overnight_forwards", fwd);
}

void op_fit_steps(const In& in, Out& out) {
    const RateConvention* c = overnight_of(in);
    const Date as_of = in.date("as_of");
    const auto step_dates = dates_of(in, "step_dates");
    const auto raw = quotes_of(in);
    const auto jumps = jumps_of(in, true);
    in.ready();
    const auto quotes = checked_quotes(raw);
    check_crossed(raw);
    const StepFit f = fit_steps(*c, as_of, step_dates, quotes, jumps);
    out.key_real("base_rate", f.base_rate);
    out.key_reals("step_rates", f.step_rates);
    out.diagnostic("max_repricing_error", f.max_repricing_error);
}

void op_futures_convexity(const In& in, Out& out) {
    const double price = in.real("price"), t = in.real("start_years"), big_t = in.real("end_years");
    const double sigma = in.real("sigma"), a = in.real("mean_reversion");
    in.ready();
    const Convexity r = futures_convexity(price, t, big_t, sigma, a);
    out.key_real("futures_rate", r.futures_rate);
    out.key_real("convexity", r.convexity);
    out.key_real("forward_rate", r.forward_rate);
}

void op_csa_discount(const In& in, Out& out) {
    const CurveInput ci = curve_of(in, "curve");
    const double spread = in.real("collateral_spread");
    const Value* fp = in.raw().find("fx");
    if (!fp) schema("fx", "missing");
    const Value& f = *fp;
    std::optional<CsaFx> fx;
    if (f.kind != Kind::Null) {
        if (f.kind != Kind::Object) schema("fx", "expected an object or null");
        const In fi(f);
        fx = CsaFx{fi.real("spot"), {}};
        const Value& a = fi.need("forwards");
        if (a.kind != Kind::Array) schema("forwards", "expected an array");
        for (const Value& v : a.items) {
            if (v.kind != Kind::Object) schema("forwards", "expected an object");
            const In row(v);
            fx->forwards.push_back({row.date("date"), row.real("forward")});
        }
    }
    const auto dates = dates_of(in, "dates");
    in.ready();
    ci.limit();
    const Curve c = ci.build();
    if (dates.empty()) throw Error("E_INPUT", "no dates", "dates");
    out.key_reals("discount_factors", csa_discount(c, spread, fx, dates));
}

void op_ois_spread(const In& in, Out& out) {
    const RateConvention* c = overnight_of(in);
    const Tenor tenor = parse_tenor(in.text("tenor"));
    const CurveInput d = curve_of(in, "discount"), a = curve_of(in, "projection_a"), b = curve_of(in, "projection_b");
    in.ready();
    d.limit();
    a.limit();
    b.limit();
    out.key_real("spread", ois_index_spread(*c, tenor, d.build(), a.build(), b.build()));
}

void op_joint_bootstrap(const In& in, Out& out) {
    const RateConvention* c = ois_convention_of(in.need("convention"), "convention");
    const RateConvention* index = index_of(in.need("index"), "index");
    const Date as_of = in.date("as_of");
    // ois_quotes reuse the bootstrap's parser, which reads "quotes".
    const Value& oq = in.need("ois_quotes");
    Value wrapper;
    wrapper.kind = Kind::Object;
    wrapper.members.push_back(json::Member{"quotes", oq});
    const auto raw = quotes_of(In(wrapper));
    const Value& a = in.need("term_quotes");
    if (a.kind != Kind::Array) schema("term_quotes", "expected an array");
    std::vector<ProjectionQuote> term;
    for (const Value& v : a.items) {
        if (v.kind != Kind::Object) schema("term_quotes", "expected an object");
        const In q(v);
        const auto type = q.choice<ProjectionQuoteType>(
            "type", {{"DEPOSIT", ProjectionQuoteType::Deposit}, {"FRA", ProjectionQuoteType::Fra}, {"SWAP", ProjectionQuoteType::Swap}});
        const long long months = q.integer(type == ProjectionQuoteType::Fra ? "start_months" : "months");
        term.push_back({type, months, q.real("rate")});
    }
    const auto interpolation = in.choice("interpolation", curve_interpolations);
    const auto method = in.choice<SolveMethod>("method", {{"SEQUENTIAL", SolveMethod::Sequential}, {"GLOBAL", SolveMethod::Global}});
    const CurveShape shape = curve_shape_of(in);
    in.ready();
    const auto quotes = checked_quotes(raw);
    limit_if(term.size() > max_quotes, "term_quotes");
    check_crossed(raw);
    for (const ProjectionQuote& q : term)
        if (q.months > 1200 || q.months < (q.type == ProjectionQuoteType::Fra ? 0 : 1))
            throw Error("E_INPUT", "months is out of range", "term_quotes");
    const JointCurves j = joint_bootstrap(*c, *index, as_of, quotes, term, interpolation, method, shape);
    const auto pillars = [&](const char* key, const Curve& curve) {
        out.values.key(key);
        out.values.begin_array();
        for (const Pillar& p : curve.pillars()) {
            out.values.begin_object();
            out.key_string("date", format_date(p.date));
            out.key_real("discount_factor", p.discount_factor);
            out.values.end_object();
        }
        out.values.end_array();
    };
    pillars("discount_pillars", j.discount);
    pillars("projection_pillars", j.projection);
    out.diagnostic("max_repricing_error", j.max_repricing_error);
}

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


// ---- stage F (Q4): joint solve and funding curve ----

std::vector<Date> turns_of(const In& in) {
    const Value* a = in.find("turns");
    if (!a) return {};
    if (a->kind != Kind::Array) schema("turns", "expected an array");
    std::vector<Date> out;
    for (const Value& item : a->items) {
        if (item.kind != Kind::Object) schema("turns", "expected an object");
        out.push_back(In(item).date("date"));
    }
    return out;
}

void op_joint_solve(const In& in, Out& out) {
    const Date as_of = in.date("as_of");
    const Value& cs = in.need("curves");
    if (cs.kind != Kind::Array) schema("curves", "expected an array");
    std::vector<JointCurveSpec> curves;
    std::vector<const Value*> xccy_curves;
    for (const Value& v : cs.items) {
        if (v.kind != Kind::Object) schema("curves", "expected an object");
        const In c(v);
        JointCurveSpec s;
        s.name = c.text("name");
        s.type = c.choice<JointCurveType>("type", {{"OIS", JointCurveType::Ois},
                                                   {"OIS_STEPS", JointCurveType::OisSteps},
                                                   {"PROJECTION", JointCurveType::Projection},
                                                   {"XCCY", JointCurveType::Xccy}});
        switch (s.type) {
            case JointCurveType::Ois:
                s.convention = ois_convention_of(c.need("convention"), "convention");
                s.interpolation = c.choice("interpolation", curve_interpolations);
                s.shape = curve_shape_of(c);
                s.jumps = jumps_of(c, false);
                s.turns = turns_of(c);
                break;
            case JointCurveType::OisSteps:
                s.convention = ois_convention_of(c.need("convention"), "convention");
                s.step_dates = dates_of(c, "step_dates");
                s.jumps = jumps_of(c, false);
                s.turns = turns_of(c);
                break;
            case JointCurveType::Projection:
                s.convention = index_of(c.need("index"), "index");
                s.discount = c.text("discount");
                s.interpolation = c.choice("interpolation", curve_interpolations);
                s.shape = curve_shape_of(c);
                break;
            case JointCurveType::Xccy:
                s.domestic = c.text("domestic");
                s.foreign_projection = c.text("foreign_projection");
                (void)overnight_of_key(c, "domestic_convention");
                (void)overnight_of_key(c, "foreign_convention");
                s.start = c.date("start");
                s.interpolation = c.choice("interpolation", curve_interpolations);
                s.shape = curve_shape_of(c);
                xccy_curves.push_back(&v);
                break;
        }
        curves.push_back(std::move(s));
    }
    const Value& is = in.need("instruments");
    if (is.kind != Kind::Array) schema("instruments", "expected an array");
    std::vector<JointInstrument> instruments;
    for (const Value& v : is.items) {
        if (v.kind != Kind::Object) schema("instruments", "expected an object");
        const In q(v);
        JointInstrument j;
        j.id = q.text("id");
        j.curve = q.text("curve");
        j.type = q.choice<JointInstrumentType>("type", {{"OIS", JointInstrumentType::Ois},
                                                       {"FUTURE", JointInstrumentType::Future},
                                                       {"DEPOSIT", JointInstrumentType::Deposit},
                                                       {"FRA", JointInstrumentType::Fra},
                                                       {"SWAP", JointInstrumentType::Swap},
                                                       {"XCCY", JointInstrumentType::Xccy}});
        j.turn = q.boolean("turn", false);
        switch (j.type) {
            case JointInstrumentType::Ois:
                j.tenor = parse_tenor(q.text("tenor"));
                j.rate = q.real("rate");
                break;
            case JointInstrumentType::Future:
                j.start = q.date("start");
                j.end = q.date("end");
                j.price = q.real("price");
                j.sigma = q.real("sigma");
                j.mean_reversion = q.real("mean_reversion");
                break;
            case JointInstrumentType::Deposit:
            case JointInstrumentType::Swap:
                j.months = q.integer("months");
                j.rate = q.real("rate");
                break;
            case JointInstrumentType::Fra:
                j.months = q.integer("start_months");
                j.rate = q.real("rate");
                break;
            case JointInstrumentType::Xccy:
                j.months = q.integer("months");
                j.spread = q.real("spread");
                break;
        }
        instruments.push_back(std::move(j));
    }
    in.ready();
    limit_if(curves.size() > max_quotes, "curves");
    limit_if(instruments.size() > max_quotes, "instruments");
    for (const Value* v : xccy_curves) xccy_conventions(In(*v));
    for (const JointInstrument& j : instruments) {
        const bool fra = j.type == JointInstrumentType::Fra;
        if ((j.type == JointInstrumentType::Deposit || j.type == JointInstrumentType::Swap || fra) &&
            (j.months > 1200 || j.months < (fra ? 0 : 1)))
            throw Error("E_INPUT", "months is out of range", "instruments");
    }
    const JointResult r = joint_solve(as_of, curves, instruments);
    out.values.key("curves");
    out.values.begin_array();
    for (const JointCurveResult& c : r.curves) {
        out.values.begin_object();
        out.key_string("name", c.name);
        if (c.steps) {
            out.key_real("base_rate", c.base_rate);
            out.key_reals("step_rates", c.step_rates);
        } else {
            out.values.key("pillars");
            out.values.begin_array();
            for (const Pillar& p : c.pillars) {
                out.values.begin_object();
                out.key_string("date", format_date(p.date));
                out.key_real("discount_factor", p.discount_factor);
                out.values.end_object();
            }
            out.values.end_array();
        }
        out.values.end_object();
    }
    out.values.end_array();
    out.values.key("turn_factors");
    out.values.begin_array();
    for (const TurnFactor& t : r.turn_factors) {
        out.values.begin_object();
        out.key_string("curve", t.curve);
        out.key_string("date", format_date(t.date));
        out.key_real("factor", t.factor);
        out.values.end_object();
    }
    out.values.end_array();
    const auto strings = [&](const char* key, const std::vector<string>& items) {
        out.values.key(key);
        out.values.begin_array();
        for (const string& s : items) out.values.string(s);
        out.values.end_array();
    };
    const auto matrix = [&](const char* key, const Matrix& m) {
        out.values.key(key);
        out.values.begin_array();
        for (const auto& row : m) {
            out.values.begin_array();
            for (const double x : row) out.values.real(x);
            out.values.end_array();
        }
        out.values.end_array();
    };
    out.values.key("jacobian");
    out.values.begin_object();
    strings("unknowns", r.unknowns);
    strings("quotes", r.quotes);
    matrix("matrix", r.jacobian);
    out.values.end_object();
    matrix("turn_sensitivity", r.turn_sensitivity);
    out.diagnostic("max_repricing_error", r.max_repricing_error);
}

void op_funding_curve(const In& in, Out& out) {
    const CurveInput di = curve_of(in, "discount");
    const Value& a = in.need("quotes");
    if (a.kind != Kind::Array) schema("quotes", "expected an array");
    std::vector<FundingQuote> quotes;
    for (const Value& v : a.items) {
        if (v.kind != Kind::Object) schema("quotes", "expected an object");
        const In q(v);
        quotes.push_back({q.date("end"), q.real("rate")});
    }
    const std::vector<Date> dates = in.find("dates") ? dates_of(in, "dates") : std::vector<Date>{};
    in.ready();
    di.limit();
    limit_if(quotes.size() > max_quotes, "quotes");
    const FundingCurve f = funding_curve(di.build(), quotes, dates);
    out.key_reals("spreads", f.spreads);
    out.values.key("pillars");
    out.values.begin_array();
    for (const Pillar& p : f.pillars) {
        out.values.begin_object();
        out.key_string("date", format_date(p.date));
        out.key_real("discount_factor", p.discount_factor);
        out.values.end_object();
    }
    out.values.end_array();
    out.key_reals("discount_factors", f.discount_factors);
}

constexpr Entry rates_ops[] = {
    {"rates.basis.ois_spread", op_ois_spread},
    {"rates.basis.spread", op_basis_spread},
    {"rates.bondfut.implied_vol", op_bondfut_implied_vol},
    {"rates.bondfut.option_price", op_bondfut_option_price},
    {"rates.cap.price", op_cap_price},
    {"rates.cap.strip", op_cap_strip},
    {"rates.csa.discount", op_csa_discount},
    {"rates.curve.discount", op_curve_discount},
    {"rates.curve.forward", op_curve_forward},
    {"rates.curve.inspect", op_curve_inspect},
    {"rates.curve.joint_bootstrap", op_joint_bootstrap},
    {"rates.curve.joint_solve", op_joint_solve},
    {"rates.fallback.rate", op_fallback_rate},
    {"rates.fra.pv", op_fra_pv},
    {"rates.funding.curve", op_funding_curve},
    {"rates.futures.convexity", op_futures_convexity},
    {"rates.ois.bootstrap", op_ois_bootstrap},
    {"rates.ois.compound", op_ois_compound},
    {"rates.ois.compound_dated", op_compound_dated},
    {"rates.ois.fit_steps", op_fit_steps},
    {"rates.ois.pv", op_ois_pv},
    {"rates.ois.step_curve", op_step_curve},
    {"rates.projection.bootstrap", op_projection_bootstrap},
    {"rates.schedule.generate", op_schedule},
    {"rates.swap.pv", op_swap_pv},
    {"rates.swaption.price", op_swaption_price},
    {"rates.swaption.price_cube", op_swaption_price_cube},
};
