// Stage D wave 1 operations. Included by dispatch.cpp after ops_stage_b.inc, sharing its helpers.

std::vector<Fixing> fixings_of(const In& in) {
    const Value& a = in.need("fixings");
    if (a.kind != Kind::Array) schema("fixings", "expected an array");
    std::vector<Fixing> out;
    for (const Value& v : a.items) {
        if (v.kind != Kind::Object) schema("fixings", "expected an object");
        const In row(v);
        out.push_back({row.date("date"), row.real("rate")});
    }
    return out;
}

// convention must be OVERNIGHT: a listed non-overnight record is E_INPUT; an unlisted string E_SCHEMA.
const RateConvention* overnight_of(const In& in) {
    const RateConvention* c = rate_convention(in.text("convention"));
    if (!c) schema("convention", "not listed");
    return c;
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
    in.ready();
    const auto quotes = checked_quotes(raw);
    limit_if(term.size() > max_quotes, "term_quotes");
    check_crossed(raw);
    for (const ProjectionQuote& q : term)
        if (q.months > 1200 || q.months < (q.type == ProjectionQuoteType::Fra ? 0 : 1))
            throw Error("E_INPUT", "months is out of range", "term_quotes");
    const JointCurves j = joint_bootstrap(*c, *index, as_of, quotes, term, interpolation, method);
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

void op_curve_smooth(const In& in, Out& out) {
    const Vec knots = in.reals("knots"), m = in.reals("maturities"), y = in.reals("zero_rates");
    const double lambda = in.real("lambda");
    std::optional<Vec> w;
    if (const Value* wv = in.raw().find("weights")) w = to_reals(*wv, "weights");
    in.ready();
    const SmoothFit f = smooth_fit(knots, m, y, lambda, w);
    out.key_reals("forwards", f.forwards);
    out.key_reals("fitted", f.fitted);
    out.key_real("objective", f.objective);
}

void op_curve_robust(const In& in, Out& out) {
    const Vec m = in.reals("maturities"), y = in.reals("zero_rates");
    const double tau = in.real("tau"), delta = in.real("delta");
    in.ready();
    const RobustFit f = robust_fit(m, y, tau, delta);
    out.key_reals("betas", f.betas);
    out.key_reals("residuals", f.residuals);
    out.values.key("outliers");
    out.values.begin_array();
    for (const std::size_t j : f.outliers) out.values.integer((long long)j);
    out.values.end_array();
    out.key_real("objective", f.objective);
}
