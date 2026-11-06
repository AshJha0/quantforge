// Stage B operations. Included by dispatch.cpp, inside its anonymous namespace, to share In and Out.

constexpr EnumTable<CurveInterpolation> curve_interpolations = {{"LOG_LINEAR_DF", CurveInterpolation::LogLinearDf},
                                                                {"LINEAR_ZERO", CurveInterpolation::LinearZero}};
constexpr EnumTable<FixedSide> fixed_sides = {{"PAY", FixedSide::Pay}, {"RECEIVE", FixedSide::Receive}};
constexpr EnumTable<FxSide> fx_sides = {{"BUY", FxSide::Buy}, {"SELL", FxSide::Sell}};

constexpr std::size_t max_quotes = 100;

// ---- units ----

void op_units_convert(const In& in, Out& out) {
    static constexpr EnumTable<RateUnit> units = {{"DECIMAL", RateUnit::Decimal}, {"PERCENT", RateUnit::Percent}, {"BP", RateUnit::Bp}};
    const double v = in.real("value");
    const RateUnit from = in.choice("from", units), to = in.choice("to", units);
    out.key_real("value", convert_unit(v, from, to));
}

struct MoneyInput {
    const string* amount;
    string currency;
};

MoneyInput money_of(const In& in) {
    const string& amount = in.text("amount");
    const string& currency = in.text("currency");
    if (classify_amount(amount) == AmountForm::Malformed) schema("amount", "bad amount");
    if (minor_units(currency) < 0) schema("currency", "not listed");
    return {&amount, currency};
}

void limit_amount(const MoneyInput& m) { limit_if(classify_amount(*m.amount) == AmountForm::TooManyDigits, "amount"); }

void op_add_money(const In& in, Out& out) {
    const Value& av = in.need("a");
    const Value& bv = in.need("b");
    if (av.kind != Kind::Object) schema("a", "expected an object");
    if (bv.kind != Kind::Object) schema("b", "expected an object");
    const MoneyInput a = money_of(In(av)), b = money_of(In(bv));
    limit_amount(a);
    limit_amount(b);
    if (a.currency != b.currency) throw Error("E_CURRENCY_MISMATCH", "currencies differ");
    out.key_string("amount", format_shortest(parse_amount(*a.amount) + parse_amount(*b.amount)));
    out.key_string("currency", a.currency);
}

void op_round_money(const In& in, Out& out) {
    const MoneyInput m = money_of(in);
    limit_amount(m);
    out.key_string("amount", round_to_places(parse_amount(*m.amount), minor_units(m.currency)));
    out.key_string("currency", m.currency);
}

void write_strings(Out& out, string_view key, std::initializer_list<string_view> items) {
    out.values.key(key);
    out.values.begin_array();
    for (const string_view s : items) out.values.string(s);
    out.values.end_array();
}

void key_int(Out& out, string_view key, long long v) {
    out.values.key(key);
    out.values.integer(v);
}

void op_conventions_lookup(const In& in, Out& out) {
    const string& id = in.text("id");
    const auto rate = [&](const char* kind, const char* currency, const char* dc, const char* cal, int spot) {
        out.key_string("kind", kind);
        out.key_string("currency", currency);
        out.key_string("day_count", dc);
        out.key_string("calendar", cal);
        key_int(out, "spot_lag", spot);
    };
    const auto tail = [&](const char* fixed_dc) {
        key_int(out, "fixed_months", 12);
        out.key_string("fixed_day_count", fixed_dc);
        out.key_string("business_day_convention", "MODIFIED_FOLLOWING");
    };
    if (id == "SONIA") {
        rate("OVERNIGHT", "GBP", "ACT_365F", "GBLO", 0);
        key_int(out, "payment_lag", 0);
        tail("ACT_365F");
    } else if (id == "SOFR") {
        rate("OVERNIGHT", "USD", "ACT_360", "USGS", 2);
        key_int(out, "payment_lag", 2);
        tail("ACT_360");
    } else if (id == "USD-TERM-3M") {
        rate("TERM", "USD", "ACT_360", "USGS", 2);
        key_int(out, "months", 3);
        tail("THIRTY_360_BOND");
    } else if (id == "GBPUSD" || id == "EURUSD") {
        out.key_string("kind", "FX");
        out.key_string("base", id == "GBPUSD" ? "GBP" : "EUR");
        out.key_string("quote", "USD");
        key_int(out, "spot_lag", 2);
        write_strings(out, "calendars", {id == "GBPUSD" ? "GBLO" : "EUTA", "USGS"});
        out.key_real("pip", 0.0001);
    } else {
        schema("id", "not listed");
    }
}

// ---- schedules and curves ----

void op_schedule(const In& in, Out& out) {
    const Date start = in.date("start"), end = in.date("end");
    const long long f = in.integer("frequency_months");
    if (f != 1 && f != 2 && f != 3 && f != 4 && f != 6 && f != 12) schema("frequency_months", "not listed");
    const Calendar c = in.choice("calendar", calendars);
    const bool eom = in.boolean("end_of_month");
    const long long lag = in.integer("payment_lag");
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

struct CurveInput {
    Date as_of;
    CurveInterpolation interpolation;
    std::vector<Pillar> pillars;

    void limit() const { limit_if(pillars.size() > max_quotes, "pillars"); }
    Curve build() const { return Curve(as_of, interpolation, pillars); }
};

CurveInput curve_of(const In& in, string_view key) {
    const Value& v = in.need(key);
    if (v.kind != Kind::Object) schema(key, "expected an object");
    const In c(v);
    CurveInput out{c.date("as_of"), c.choice("interpolation", curve_interpolations), {}};
    const Value& p = c.need("pillars");
    if (p.kind != Kind::Array) schema("pillars", "expected an array");
    for (const Value& item : p.items) {
        if (item.kind != Kind::Object) schema("pillars", "expected an object");
        const In row(item);
        out.pillars.push_back({row.date("date"), row.real("discount_factor")});
    }
    return out;
}

std::vector<Date> dates_of(const In& in, string_view key) {
    const Value& a = in.need(key);
    if (a.kind != Kind::Array) schema(key, "expected an array");
    std::vector<Date> out;
    for (const Value& v : a.items) out.push_back(to_date(v, key));
    return out;
}

void op_curve_discount(const In& in, Out& out) {
    const CurveInput ci = curve_of(in, "curve");
    const auto dates = dates_of(in, "dates");
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

constexpr EnumTable<DayCount> plain_day_counts = {
    {"ACT_360", DayCount::Act360}, {"ACT_365F", DayCount::Act365F}, {"ACT_364", DayCount::Act364},
    {"ACT_365_25", DayCount::Act365_25}, {"NL_365", DayCount::Nl365}, {"ONE_ONE", DayCount::OneOne},
    {"ACT_ACT_ISDA", DayCount::ActActIsda}, {"ACT_ACT_AFB", DayCount::ActActAfb},
    {"THIRTY_360_BOND", DayCount::Thirty360Bond}, {"THIRTY_360_US", DayCount::Thirty360Us},
    {"THIRTY_E_360", DayCount::ThirtyE360}, {"THIRTY_E_PLUS_360", DayCount::ThirtyEPlus360}};

void op_curve_forward(const In& in, Out& out) {
    const CurveInput ci = curve_of(in, "curve");
    const Date start = in.date("start"), end = in.date("end");
    const DayCount dc = in.choice("day_count", plain_day_counts);
    ci.limit();
    out.key_real("forward", simple_forward(ci.build(), start, end, dc));
}

void write_pillars(Out& out, const Curve& c) {
    out.values.key("pillars");
    out.values.begin_array();
    for (const Pillar& p : c.pillars()) {
        out.values.begin_object();
        out.key_string("date", format_date(p.date));
        out.key_real("discount_factor", p.discount_factor);
        out.values.end_object();
    }
    out.values.end_array();
}

void write_valuation(Out& out, const Valuation& v) {
    out.values.key("valuation");
    out.values.begin_object();
    out.key_real("pv", v.pv);
    out.key_string("currency", v.currency);
    out.key_string("model", v.model);
    out.values.key("data_version");
    if (v.data_version) out.values.string(*v.data_version);
    else out.values.null();
    out.key_string("conventions", v.conventions);
    out.key_string("as_of", format_date(v.as_of));
    out.values.end_object();
}

const RateConvention* ois_convention_of(const Value& v, string_view key) {
    const RateConvention* c = rate_convention(to_string(v, key));
    if (!c || c->months != 0) schema(key, "not listed");
    return c;
}

const RateConvention* index_of(const Value& v, string_view key) {
    const RateConvention* c = rate_convention(to_string(v, key));
    if (!c || c->months == 0) schema(key, "not listed");
    return c;
}

struct RawQuote {
    Tenor tenor;
    double rate;
    bool crossed;
};

std::vector<RawQuote> quotes_of(const In& in) {
    const Value& a = in.need("quotes");
    if (a.kind != Kind::Array) schema("quotes", "expected an array");
    std::vector<RawQuote> out;
    for (const Value& v : a.items) {
        if (v.kind != Kind::Object) schema("quotes", "expected an object");
        const In q(v);
        const Tenor t = parse_tenor(q.text("tenor"));
        if (q.find("rate")) {
            out.push_back({t, q.real("rate"), false});
        } else {
            const double bid = q.real("bid"), ask = q.real("ask");
            out.push_back({t, (bid + ask) / 2.0, bid > ask});
        }
    }
    return out;
}

// The quote checks: E_LIMIT is the caller's first rule here.
std::vector<OisQuote> checked_quotes(const std::vector<RawQuote>& raw) {
    limit_if(raw.size() > max_quotes, "quotes");
    std::vector<OisQuote> out;
    for (const RawQuote& q : raw) out.push_back({q.tenor, q.rate});
    return out;
}

void check_crossed(const std::vector<RawQuote>& raw) {
    if (raw.empty()) return;  // ois_bootstrap reports it
    for (const RawQuote& q : raw)
        if (q.crossed) throw Error("E_INPUT", "bid is above ask", "quotes");
}

void op_ois_bootstrap(const In& in, Out& out) {
    const RateConvention* c = ois_convention_of(in.need("convention"), "convention");
    const Date as_of = in.date("as_of");
    const auto raw = quotes_of(in);
    const auto interpolation = in.choice("interpolation", curve_interpolations);
    const auto method = in.choice<SolveMethod>("method", {{"SEQUENTIAL", SolveMethod::Sequential}, {"GLOBAL", SolveMethod::Global}});
    const auto quotes = checked_quotes(raw);
    check_crossed(raw);
    const SolvedCurve s = ois_bootstrap(*c, as_of, quotes, interpolation, method);
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
    out.key_real("compounded_rate", ois_compound(rates, days, double(denominator)));
}

OisTrade ois_trade_of(const Value& v) {
    if (v.kind != Kind::Object) schema("trade", "expected an object");
    const In t(v);
    return {ois_convention_of(t.need("convention"), "convention"), parse_tenor(t.text("tenor")), t.real("fixed_rate"),
            t.real("notional"), t.choice("side", fixed_sides)};
}

std::optional<string> snapshot_of_input(const In& in) {
    if (!in.find("snapshot_id")) return std::nullopt;
    return in.text("snapshot_id");
}

void op_ois_pv(const In& in, Out& out) {
    const CurveInput ci = curve_of(in, "curve");
    const auto snapshot = snapshot_of_input(in);
    const OisTrade trade = ois_trade_of(in.need("trade"));
    ci.limit();
    const OisPrice p = ois_price(trade, ci.build(), snapshot);
    write_valuation(out, p.valuation);
    out.key_real("par_rate", p.par_rate);
    out.key_real("annuity", p.annuity);
}

// ---- projection ----

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
    di.limit();
    pi.limit();
    if (months < 1 || months > 1200) throw Error("E_INPUT", "tenor_months is out of range", "tenor_months");
    out.key_real("spread", basis_spread(di.build(), pi.build(), *index, months));
}

// ---- FX ----

const FxPair* pair_of(const In& in) {
    const FxPair* p = fx_pair(in.text("pair"));
    if (!p) schema("pair", "not listed");
    return p;
}

void op_fx_spot_date(const In& in, Out& out) {
    const FxPair* p = pair_of(in);
    out.key_string("spot_date", format_date(fx_spot_date(*p, in.date("trade_date"))));
}

struct FxInput {
    const FxPair* pair;
    double spot;
    Date as_of;
    CurveInput base, quote;

    void limit() const {
        base.limit();
        quote.limit();
    }
};

FxInput fx_input(const In& in) {
    return {pair_of(in), in.real("spot"), in.date("as_of"), curve_of(in, "base_curve"), curve_of(in, "quote_curve")};
}

// Spot is the first rule, then the curves.
template <class Use>
auto with_market(const FxInput& f, Use&& use) {
    check_fx_market({f.pair, f.spot, f.as_of, nullptr, nullptr});
    if (f.base.as_of != f.as_of || f.quote.as_of != f.as_of) throw Error("E_INPUT", "a curve's as_of differs");
    const Curve base = f.base.build(), quote = f.quote.build();
    return use(FxMarket{f.pair, f.spot, f.as_of, &base, &quote});
}

void op_fx_outright(const In& in, Out& out) {
    const FxInput f = fx_input(in);
    const Date value_date = in.date("value_date");
    f.limit();
    const FxOutright r = with_market(f, [&](const FxMarket& m) { return fx_outright(m, value_date); });
    out.key_real("forward", r.forward);
    out.key_real("points", r.points);
}

FxForwardTrade fx_trade_of(const Value& v, string_view key) {
    if (v.kind != Kind::Object) schema(key, "expected an object");
    const In t(v);
    return {t.real("notional_base"), t.real("strike"), t.date("value_date"), t.choice("side", fx_sides)};
}

void op_fx_forward_pv(const In& in, Out& out) {
    const FxInput f = fx_input(in);
    const auto snapshot = snapshot_of_input(in);
    const FxForwardTrade t = fx_trade_of(in.need("trade"), "trade");
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
    f.limit();
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

// ---- calibration ----

std::optional<Vec> maybe_vector(const In& in, string_view key) {
    if (!in.find(key)) return std::nullopt;
    return in.reals(key);
}

void op_calib_fit(const In& in, Out& out) {
    FitInputs f;
    f.model = in.choice<FitModel>("model", {{"LINEAR", FitModel::Linear}, {"EXPONENTIAL", FitModel::Exponential},
                                            {"NELSON_SIEGEL", FitModel::NelsonSiegel}, {"ROSENBROCK", FitModel::Rosenbrock}});
    if (f.model != FitModel::Rosenbrock || in.find("x")) f.x = in.reals("x");
    if (f.model != FitModel::Rosenbrock || in.find("y")) f.y = in.reals("y");
    f.start = in.reals("start");
    f.method = in.choice<FitMethod>("method", {{"GAUSS_NEWTON", FitMethod::GaussNewton},
                                               {"LEVENBERG_MARQUARDT", FitMethod::LevenbergMarquardt}, {"BFGS", FitMethod::Bfgs}});
    f.weights = maybe_vector(in, "weights");
    f.regularisation = in.real("regularisation", 0.0);
    f.prior = maybe_vector(in, "prior");
    f.lower = maybe_vector(in, "lower");
    f.upper = maybe_vector(in, "upper");
    f.max_iter = in.integer("max_iter", 1000);
    const bool report = in.boolean("report_parameters", true);
    limit_if(f.start.size() > 20, "start");
    limit_if(f.max_iter > 100000, "max_iter");
    const FitResult r = fit(f);
    if (report) out.key_reals("parameters", r.parameters);
    out.key_real("objective", r.objective);
    out.diagnostics.key("iterations");
    out.diagnostics.integer(r.iterations);
    out.diagnostics.key("status");
    out.diagnostics.string(r.status);
    out.diagnostics.key("residuals");
    out.diagnostics.begin_array();
    for (const double v : r.residuals) out.diagnostics.real(v);
    out.diagnostics.end_array();
}

void op_check_bid_ask(const In& in, Out& out) {
    const Vec fitted = in.reals("fitted"), bid = in.reals("bid"), ask = in.reals("ask");
    const auto breaches = check_bid_ask(fitted, bid, ask);
    out.values.key("breaches");
    out.values.begin_array();
    for (const Breach& b : breaches) {
        out.values.begin_object();
        key_int(out, "index", (long long)b.index);
        out.key_string("side", b.side);
        out.key_real("distance", b.distance);
        out.values.end_object();
    }
    out.values.end_array();
}

void op_curve_report(const In& in, Out& out) {
    const RateConvention* c = ois_convention_of(in.need("convention"), "convention");
    const Date as_of = in.date("as_of");
    const auto raw = quotes_of(in);
    const auto interpolation = in.choice("interpolation", curve_interpolations);
    const auto quotes = checked_quotes(raw);
    check_crossed(raw);
    const CurveReport r = curve_report(*c, as_of, quotes, interpolation);
    out.values.key("jacobian");
    out.values.begin_array();
    for (const Vec& row : r.jacobian) {
        out.values.begin_array();
        for (const double v : row) out.values.real(v);
        out.values.end_array();
    }
    out.values.end_array();
    out.key_real("condition_number", r.condition_number);
    out.diagnostics.key("inputs");
    out.diagnostics.begin_array();
    for (const Value& q : in.need("quotes").items) out.diagnostics.string(q.find("tenor")->text);
    out.diagnostics.end_array();
    out.diagnostics.key("status");
    out.diagnostics.string("OK");
    out.diagnostic("max_repricing_error", r.max_repricing_error);
    out.diagnostics.key("tolerance_breaches");
    out.diagnostics.begin_array();
    out.diagnostics.end_array();
}

// ---- risk ----

void op_ois_dv01(const In& in, Out& out) {
    const Date as_of = in.date("as_of");
    const auto raw = quotes_of(in);
    const auto interpolation = in.choice("interpolation", curve_interpolations);
    const OisTrade trade = ois_trade_of(in.need("trade"));
    const auto quotes = checked_quotes(raw);
    check_crossed(raw);
    const RateRisk r = rate_risk(trade, bumped_curves(*trade.convention, as_of, quotes, interpolation));
    out.key_real("dv01", r.dv01);
    out.key_reals("key_rate", r.key_rate);
}

void op_cashflows(const In& in, Out& out) {
    const Value& a = in.need("cashflows");
    if (a.kind != Kind::Array) schema("cashflows", "expected an array");
    std::vector<Cashflow> flows;
    for (const Value& v : a.items) {
        if (v.kind != Kind::Object) schema("cashflows", "expected an object");
        const In c(v);
        flows.push_back({c.real("t"), c.real("amount")});
    }
    const CashflowRisk r = cashflow_risk(flows, in.real("yield"));
    out.key_real("pv", r.pv);
    out.key_real("duration", r.duration);
    out.key_real("convexity", r.convexity);
}

// ---- hedges ----

void op_hedge_solve(const In& in, Out& out) {
    const Matrix a = in.matrix("a");
    const Vec b = in.reals("b"), weights = in.reals("weights"), costs = in.reals("costs");
    const double lambda = in.real("lambda");
    limit_if(!a.empty() && a[0].size() > 20, "a");
    const HedgeResult r = hedge_solve(a, b, weights, costs, lambda);
    out.key_reals("x", r.x);
    out.key_reals("residual", r.residual);
    out.key_real("objective", r.objective);
}

void op_spread_cost(const In& in, Out& out) {
    const Vec q = in.reals("quantities"), h = in.reals("half_spreads");
    out.key_real("cost", spread_cost(q, h));
}

// ---- use cases ----

void op_usecase_fx(const In& in, Out& out) {
    const FxInput f = fx_input(in);
    const Value& book = in.need("book");
    if (book.kind != Kind::Array) schema("book", "expected an array");
    std::vector<FxForwardTrade> trades;
    for (const Value& v : book.items) trades.push_back(fx_trade_of(v, "book"));
    const double half_spread = in.real("half_spread");
    f.limit();
    if (half_spread < 0.0) throw Error("E_DOMAIN", "half_spread is negative", "half_spread");
    double pv = 0.0, delta = 0.0;
    with_market(f, [&](const FxMarket& m) {
        for (const FxForwardTrade& t : trades) {
            const FxPrice p = fx_forward_price(m, t);
            pv += p.valuation.pv;
            delta += p.fx_delta;
        }
        return 0;
    });
    const double hedge = -delta;
    out.key_real("pv", pv);
    out.key_real("fx_delta", delta);
    out.key_real("hedge_spot_base", hedge);
    out.key_real("residual_delta", delta + hedge);
    out.key_real("hedge_cost", std::fabs(hedge) * half_spread);
}

void op_usecase_rates(const In& in, Out& out) {
    const Date as_of = in.date("as_of");
    const auto raw = quotes_of(in);
    const auto interpolation = in.choice("interpolation", curve_interpolations);
    const OisTrade trade = ois_trade_of(in.need("trade"));
    const Value& ht = in.need("hedge_tenors");
    if (ht.kind != Kind::Array) schema("hedge_tenors", "expected an array");
    std::vector<Tenor> tenors;
    for (const Value& v : ht.items) tenors.push_back(parse_tenor(to_string(v, "hedge_tenors")));
    const double unit = in.real("hedge_unit_notional"), half_spread_bp = in.real("half_spread_bp");
    const auto quotes = checked_quotes(raw);
    limit_if(tenors.size() > 20, "hedge_tenors");
    check_crossed(raw);
    if (half_spread_bp < 0.0) throw Error("E_DOMAIN", "half_spread_bp is negative", "half_spread_bp");

    const RateConvention& c = *trade.convention;
    const Curve curve = ois_bootstrap(c, as_of, quotes, interpolation, SolveMethod::Sequential).curve;
    const BumpedCurves bumped = bumped_curves(c, as_of, quotes, interpolation);
    const RateRisk risk = rate_risk(trade, bumped);
    Matrix columns(risk.key_rate.size(), Vec(tenors.size()));
    Vec column_sums;
    for (std::size_t h = 0; h < tenors.size(); ++h) {
        OisTrade hedge{&c, tenors[h], 0.0, unit, FixedSide::Pay};
        hedge.fixed_rate = ois_price(hedge, curve).par_rate;
        const RateRisk hr = rate_risk(hedge, bumped);
        double sum = 0.0;
        for (std::size_t i = 0; i < hr.key_rate.size(); ++i) {
            columns[i][h] = hr.key_rate[i];
            sum += hr.key_rate[i];
        }
        column_sums.push_back(sum);
    }
    const HedgeResult solved = hedge_solve(columns, risk.key_rate, Vec(risk.key_rate.size(), 1.0), Vec(tenors.size(), 0.0), 0.0);
    double cost = 0.0;
    for (std::size_t h = 0; h < tenors.size(); ++h) cost += std::fabs(solved.x[h]) * std::fabs(column_sums[h]) * half_spread_bp;
    out.key_real("pv", ois_price(trade, curve).valuation.pv);
    out.key_real("dv01", risk.dv01);
    out.key_reals("key_rate", risk.key_rate);
    out.key_reals("hedge_units", solved.x);
    out.key_reals("residual_key_rate", solved.residual);
    out.key_real("hedge_cost", cost);
}
