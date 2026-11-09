// Input readers and output writers shared by more than one domain.
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.

Tenor parse_tenor(const string& s) {
    const bool shape = s.size() >= 2 && s.size() <= 5 && s[0] >= '1' && s[0] <= '9' &&
                       std::all_of(s.begin(), s.end() - 1, [](char c) { return c >= '0' && c <= '9'; }) &&
                       string_view("DWMY").find(s.back()) != string_view::npos;
    if (!shape) schema("tenor", "bad tenor");
    return {std::stoi(s.substr(0, s.size() - 1)), s.back()};
}

Compounding compounding_of(const Value& v, string_view key) {
    static constexpr EnumTable<CompoundingKind> kinds = {{"SIMPLE", CompoundingKind::Simple},
                                                         {"PERIODIC", CompoundingKind::Periodic},
                                                         {"CONTINUOUS", CompoundingKind::Continuous}};
    if (v.kind != Kind::Object) schema(key, "expected an object");
    const In in(v);
    Compounding c{in.choice("compounding", kinds), std::nullopt};
    if (c.kind == CompoundingKind::Periodic && in.find("frequency")) c.frequency = in.integer("frequency");
    return c;
}

struct DrawRequest {
    Xoshiro256 rng;
    long long count;
};

long long draw_count(const In& in) {
    const long long count = in.integer("count");
    if (count < 1) schema("count", "must be at least 1");
    return count;
}

int stream_of(long long stream) {
    if (stream < 0 || stream > 1023) schema("stream", "must be 0 to 1023");
    return int(stream);
}

DrawRequest draws(const In& in) {
    const std::uint64_t seed = in.u64("seed");
    const int stream = stream_of(in.integer("stream"));
    const long long count = draw_count(in), skip = in.integer("skip", 0);
    if (skip < 0) schema("skip", "must not be negative");
    in.ready();
    limit_if(count > 100000, "count");
    limit_if(skip > 10000000, "skip");
    Xoshiro256 rng(seed, stream);
    for (long long i = 0; i < skip; ++i) rng.next();
    return {rng, count};
}

void write_u64s(Out& out, Xoshiro256& rng, long long count) {
    out.values.key("values");
    out.values.begin_array();
    for (long long i = 0; i < count; ++i) out.values.string(std::to_string(rng.next()));
    out.values.end_array();
}

RootOptions root_options(const In& in) {
    const RootOptions o{in.real("x_tol", 1e-12), in.real("f_tol", 0.0), in.integer("max_iter", 200)};
    in.ready();
    limit_if(o.max_iter > 100000, "max_iter");
    return o;
}

void write_root(Out& out, const RootResult& r) {
    out.key_real("root", r.root);
    out.diagnostics.key("iterations");
    out.diagnostics.integer(r.iterations);
    out.diagnostic("residual", r.residual);
    out.diagnostics.key("termination");
    out.diagnostics.string(r.termination);
}

Quote quote_of(const Value& v) {
    if (v.kind != Kind::Object) schema("quotes", "expected an object");
    const In q(v);
    if (!v.find("bid")) schema("bid", "missing");
    if (!v.find("ask")) schema("ask", "missing");
    const string& status = q.text("quote_status");
    if (status != "FIRM" && status != "INDICATIVE") schema("quote_status", "must be FIRM or INDICATIVE");
    return {q.text("instrument_id"), q.instant("event_time"), to_maybe_real(*v.find("bid"), "bid"),
            to_maybe_real(*v.find("ask"), "ask"), status};
}

Cutoff parse_cutoff(const string& s) {
    const auto digit = [&](std::size_t i) { return s[i] >= '0' && s[i] <= '9'; };
    if (s.size() != 5 || s[2] != ':' || !digit(0) || !digit(1) || !digit(3) || !digit(4)) schema("cutoff", "expected HH:MM");
    const Cutoff c{(s[0] - '0') * 10 + (s[1] - '0'), (s[3] - '0') * 10 + (s[4] - '0')};
    if (c.hour > 23 || c.minute > 59) schema("cutoff", "expected HH:MM");
    return c;
}

StoreRecord record_of(const Value& v) {
    if (v.kind != Kind::Object) schema("records", "expected an object");
    const In r(v);
    if (!v.find("value")) schema("value", "missing");
    const long long sequence = r.integer("sequence");
    if (sequence < 1) schema("sequence", "must be at least 1");
    const string& series = r.text("series_id");
    if (series.empty()) schema("series_id", "empty");
    return {sequence, series, r.instant("event_time"), r.instant("knowledge_time"), *v.find("value"),
            r.boolean("deleted", false), v};
}

std::vector<StoreRecord> log_of(const In& in) {
    const Value& a = in.need("records");
    if (a.kind != Kind::Array) schema("records", "expected an array");
    std::vector<StoreRecord> log;
    log.reserve(a.items.size());
    for (const Value& v : a.items) log.push_back(record_of(v));
    return log;
}

int nesting(const Value& v) {
    int deepest = 0;
    for (const Value& item : v.items) deepest = std::max(deepest, nesting(item));
    for (const auto& m : v.members) deepest = std::max(deepest, nesting(m.second));
    return v.kind == Kind::Array || v.kind == Kind::Object ? deepest + 1 : 0;
}

// Runs once all schema checks are done: limits, then log checks 2 and 3, then the range of
// instants, records first (rulings A2 and A5).
void check_store_nesting(const std::vector<StoreRecord>& log) {
    for (const StoreRecord& r : log)
        for (const auto& m : r.raw.members) limit_if(nesting(m.second) > 64, m.first);
}

void check_store(const std::vector<StoreRecord>& log, const std::vector<std::optional<Instant>>& others) {
    check_log(log);
    for (const StoreRecord& r : log) {
        check_store_instant(r.event_time);
        check_store_instant(r.knowledge_time);
    }
    for (const auto& i : others)
        if (i) check_store_instant(*i);
}

void write_row(Out& out, const StoreRow& r) {
    out.values.begin_object();
    out.key_string("series_id", r.series_id);
    out.key_string("event_time", format_instant(r.event_time));
    out.key_string("knowledge_time", format_instant(r.knowledge_time));
    out.values.key("sequence");
    out.values.integer(r.sequence);
    out.values.key("value");
    out.values.value(r.value);
    out.values.end_object();
}

std::optional<Instant> maybe_instant(const In& in, string_view k) {
    if (!in.find(k)) return std::nullopt;
    return in.instant(k);
}


constexpr EnumTable<CurveInterpolation> curve_interpolations = {{"LOG_LINEAR_DF", CurveInterpolation::LogLinearDf},
                                                                {"LINEAR_ZERO", CurveInterpolation::LinearZero}};

constexpr EnumTable<FixedSide> fixed_sides = {{"PAY", FixedSide::Pay}, {"RECEIVE", FixedSide::Receive}};

constexpr EnumTable<FxSide> fx_sides = {{"BUY", FxSide::Buy}, {"SELL", FxSide::Sell}};

constexpr std::size_t max_quotes = 100;

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

// Jumps: [{date, factor}]. Absent is none when optional; null is E_SCHEMA (ruling D10).
std::vector<Jump> jumps_of(const In& in, bool required) {
    const Value* a = in.raw().find("jumps");
    if (!a) {
        if (required) schema("jumps", "missing");
        return {};
    }
    if (a->kind != Kind::Array) schema("jumps", "expected an array");
    std::vector<Jump> out;
    for (const Value& item : a->items) {
        if (item.kind != Kind::Object) schema("jumps", "expected an object");
        const In row(item);
        out.push_back({row.date("date"), row.real("factor")});
    }
    return out;
}

struct CurveInput {
    Date as_of;
    CurveInterpolation interpolation;
    std::vector<Pillar> pillars;
    std::vector<Jump> jumps;

    void limit() const { limit_if(pillars.size() > max_quotes, "pillars"); }
    Curve build() const { return Curve(as_of, interpolation, pillars, jumps); }
};

CurveInput curve_of(const In& in, string_view key) {
    const Value& v = in.need(key);
    if (v.kind != Kind::Object) schema(key, "expected an object");
    const In c(v);
    CurveInput out{c.date("as_of"), c.choice("interpolation", curve_interpolations), {}, {}};
    const Value& p = c.need("pillars");
    if (p.kind != Kind::Array) schema("pillars", "expected an array");
    for (const Value& item : p.items) {
        if (item.kind != Kind::Object) schema("pillars", "expected an object");
        const In row(item);
        out.pillars.push_back({row.date("date"), row.real("discount_factor")});
    }
    out.jumps = jumps_of(c, false);
    return out;
}

std::vector<Date> dates_of(const In& in, string_view key) {
    const Value& a = in.need(key);
    if (a.kind != Kind::Array) schema(key, "expected an array");
    std::vector<Date> out;
    for (const Value& v : a.items) out.push_back(to_date(v, key));
    return out;
}

constexpr EnumTable<DayCount> plain_day_counts = {
    {"ACT_360", DayCount::Act360}, {"ACT_365F", DayCount::Act365F}, {"ACT_364", DayCount::Act364},
    {"ACT_365_25", DayCount::Act365_25}, {"NL_365", DayCount::Nl365}, {"ONE_ONE", DayCount::OneOne},
    {"ACT_ACT_ISDA", DayCount::ActActIsda}, {"ACT_ACT_AFB", DayCount::ActActAfb},
    {"THIRTY_360_BOND", DayCount::Thirty360Bond}, {"THIRTY_360_US", DayCount::Thirty360Us},
    {"THIRTY_E_360", DayCount::ThirtyE360}, {"THIRTY_E_PLUS_360", DayCount::ThirtyEPlus360}};

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
    if (!c) schema(key, "not listed");
    if (c->months != 0) throw Error("E_INPUT", "an overnight convention is needed (ruling D45)", string(key));
    return c;
}

const RateConvention* index_of(const Value& v, string_view key) {
    const RateConvention* c = rate_convention(to_string(v, key));
    if (!c) schema(key, "not listed");
    if (c->months == 0) throw Error("E_INPUT", "a term index is needed (ruling D45)", string(key));
    return c;
}

struct RawQuote {
    Tenor tenor;
    double rate;
    bool crossed;
};

std::vector<RawQuote> quotes_of(const In& in, string_view key = "quotes") {
    const Value& a = in.need(key);
    if (a.kind != Kind::Array) schema(key, "expected an array");
    std::vector<RawQuote> out;
    for (const Value& v : a.items) {
        if (v.kind != Kind::Object) schema(key, "expected an object");
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

const FxPair* pair_of(const In& in) {
    const FxPair* p = fx_pair(in.text("pair"));
    if (!p) schema("pair", "not listed");
    return p;
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
    const Curve base = f.base.build(), quote = f.quote.build();
    if (f.base.as_of != f.as_of || f.quote.as_of != f.as_of) throw Error("E_INPUT", "a curve's as_of differs");
    return use(FxMarket{f.pair, f.spot, f.as_of, &base, &quote});
}

FxForwardTrade fx_trade_of(const Value& v, string_view key) {
    if (v.kind != Kind::Object) schema(key, "expected an object");
    const In t(v);
    return {t.real("notional_base"), t.real("strike"), t.date("value_date"), t.choice("side", fx_sides)};
}

std::optional<Vec> maybe_vector(const In& in, string_view key) {
    if (!in.find(key)) return std::nullopt;
    return in.reals(key);
}


// Ruling C9: an optional key may be absent, but null for one is E_SCHEMA.
double optional_real(const In& in, string_view key, double fallback) {
    const Value* p = in.raw().find(key);
    if (!p) return fallback;
    if (p->kind == Kind::Null) schema(key, "null is not allowed");
    return to_real(*p, key);
}

// Ruling C9: a key where null carries meaning must be present.
void require_key(const In& in, string_view key) {
    if (!in.raw().find(key)) schema(key, "missing");
}

std::optional<string> optional_snapshot(const In& in) {
    const Value* p = in.raw().find("snapshot_id");
    if (!p) return std::nullopt;
    return to_string(*p, "snapshot_id");
}

// Ruling C17: an empty list is E_INPUT, the first rule check.
template <class List>
void need_items(const List& list, string_view key) {
    if (list.empty()) throw Error("E_INPUT", string(key) + " is empty", string(key));
}

template <class Row>
std::vector<Row> rows_of(const In& in, string_view key, Row (*read)(const In&)) {
    const Value& a = in.need(key);
    if (a.kind != Kind::Array) schema(key, "expected an array");
    std::vector<Row> out;
    for (const Value& item : a.items) {
        if (item.kind != Kind::Object) schema(key, "expected an object");
        out.push_back(read(In(item)));
    }
    return out;
}

struct ForwardInput {
    double spot;
    Date as_of, expiry;
    CurveInput funding;
    std::optional<CurveInput> borrow;
    std::vector<Dividend> dividends;

    // Spot comes before the curves' own checks, so curves are built here and not when read.
    EquityForward solve() const {
        limit_if(dividends.size() > max_quotes, "dividends");
        funding.limit();
        if (borrow) borrow->limit();
        if (spot <= 0) throw Error("E_DOMAIN", "spot is not above 0");
        const Curve d = funding.build();
        if (!borrow) return equity_forward(spot, as_of, expiry, d, nullptr, dividends);
        const Curve b = borrow->build();
        return equity_forward(spot, as_of, expiry, d, &b, dividends);
    }
};

ForwardInput forward_of(const In& in) {
    ForwardInput f{in.real("spot"), in.date("as_of"), in.date("expiry"), curve_of(in, "funding_curve"), {}, {}};
    require_key(in, "borrow_curve");
    if (in.find("borrow_curve")) f.borrow = curve_of(in, "borrow_curve");
    f.dividends = rows_of<Dividend>(in, "dividends", [](const In& r) { return Dividend{r.date("ex_date"), r.real("amount")}; });
    return f;
}

ParityQuote parity_quote_of(const In& r) {
    return {r.real("strike"), r.real("call_bid"), r.real("call_ask"), r.real("put_bid"), r.real("put_ask")};
}


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


enum class DeltaConvention { Forward, Spot };

constexpr EnumTable<DeltaConvention> delta_conventions = {{"FORWARD", DeltaConvention::Forward}, {"SPOT", DeltaConvention::Spot}};

struct DeltaScale {
    DeltaConvention convention;
    std::optional<double> scale;

    double value() const {
        // Ruling C15: a scale that does not match the convention is the first rule check.
        if (convention == DeltaConvention::Forward) {
            if (scale) throw Error("E_INPUT", "scale must be null for FORWARD");
            return 1.0;
        }
        if (!scale) throw Error("E_INPUT", "scale must be a number for SPOT");
        if (*scale <= 0) throw Error("E_DOMAIN", "scale is not above 0");
        return *scale;
    }
};

DeltaScale delta_scale_of(const In& in) {
    const DeltaConvention c = in.choice("convention", delta_conventions);
    require_key(in, "scale");
    return {c, to_maybe_real(*in.raw().find("scale"), "scale")};
}

Svi svi_of(const In& in) {
    const Value& v = in.need("svi");
    if (v.kind != Kind::Object) schema("svi", "expected an object");
    const In s(v);
    return {s.real("a"), s.real("b"), s.real("rho"), s.real("m"), s.real("sigma")};
}

void write_svi(Out& out, const Svi& s) {
    out.values.key("svi");
    out.values.begin_object();
    out.key_real("a", s.a);
    out.key_real("b", s.b);
    out.key_real("rho", s.rho);
    out.key_real("m", s.m);
    out.key_real("sigma", s.sigma);
    out.values.end_object();
}

std::optional<Vec> optional_weights(const In& in) {
    const Value* p = in.raw().find("weights");
    if (!p) return std::nullopt;
    if (p->kind == Kind::Null) schema("weights", "null is not allowed");
    return to_reals(*p, "weights");
}


Surface surface_of(const In& in) {
    const Value& v = in.need("surface");
    if (v.kind != Kind::Object) schema("surface", "expected an object");
    const In s(v);
    return {s.reals("expiry_years"), s.reals("log_moneyness"), s.matrix("vols")};
}

void limit_surface(const Surface& s) {
    limit_if(s.expiry_years.size() > max_quotes || s.log_moneyness.size() > max_quotes, "surface");
}

void write_surface_check(Out& out, const SurfaceCheck& c) {
    out.values.key("calendar_violations");
    out.values.begin_array();
    for (const CalendarViolation& v : c.calendar) {
        out.values.begin_object();
        out.values.key("expiry_index");
        out.values.integer((long long)v.expiry_index);
        out.values.key("k_index");
        out.values.integer((long long)v.k_index);
        out.values.end_object();
    }
    out.values.end_array();
    out.values.key("butterfly_violations");
    out.values.begin_array();
    for (const ButterflyViolation& v : c.butterfly) {
        out.values.begin_object();
        out.values.key("expiry_index");
        out.values.integer((long long)v.expiry_index);
        out.values.key("k_index");
        out.values.integer((long long)v.k_index);
        out.key_string("kind", v.kind);
        out.values.end_object();
    }
    out.values.end_array();
    out.values.key("arbitrage_free");
    out.values.boolean(c.calendar.empty() && c.butterfly.empty());
}

struct VegaPosition {
    OptionType type;
    double forward, strike, discount_factor, expiry_years, quantity;
};

double surface_pv(const Surface& s, const std::vector<VegaPosition>& positions) {
    double pv = 0.0;
    for (const VegaPosition& p : positions) {
        const double w = surface_total_variance(s, p.expiry_years, std::log(p.strike / p.forward));
        const double phi = p.type == OptionType::Call ? 1.0 : -1.0;
        pv += p.quantity * black_price(p.forward, p.strike, std::sqrt(w / p.expiry_years), p.expiry_years, p.discount_factor, phi);
    }
    return pv;
}


struct SabrInput {
    double forward, t;
    SabrParameters p;
    double shift;
    Vec strikes;

    double f() const { return forward + shift; }
    Vec shifted() const {
        Vec x = strikes;
        for (double& k : x) k += shift;
        return x;
    }
    void check() const {
        limit_if(strikes.size() > max_quotes, "strikes");
        need_items(strikes, "strikes");
        check_sabr(t, p, f(), shifted());
    }
};

SabrInput sabr_of(const In& in) {
    return {in.real("forward"), in.real("expiry_years"),
            {in.real("alpha"), in.real("beta"), in.real("rho"), in.real("nu")},
            optional_real(in, "shift", 0.0), in.reals("strikes")};
}


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
const RateConvention* overnight_of_key(const In& in, string_view key) {
    const RateConvention* c = rate_convention(in.text(key));
    if (!c) schema(key, "not listed");
    return c;
}

const RateConvention* overnight_of(const In& in) { return overnight_of_key(in, "convention"); }

template <class Row>
std::vector<Row> rows_of(const In& in, string_view key, auto&& read) {
    const Value& a = in.need(key);
    if (a.kind != Kind::Array) schema(key, "expected an array");
    std::vector<Row> out;
    for (const Value& v : a.items) {
        if (v.kind != Kind::Object) schema(key, "expected an object");
        out.push_back(read(In(v)));
    }
    return out;
}

void xccy_conventions(const In& in) {
    const RateConvention* d = overnight_of_key(in, "domestic_convention");
    const RateConvention* f = overnight_of_key(in, "foreign_convention");
    if (d->id != "SOFR" || f->id != "ESTR") throw Error("E_INPUT", "domestic SOFR and foreign ESTR only (ruling D17)");
}


Bond bond_fields(const In& b) {
    const Date maturity = b.date("maturity");
    const double coupon = b.real("coupon");
    const long long f = b.integer("frequency");
    if (f != 1 && f != 2 && f != 4) schema("frequency", "must be 1, 2 or 4");
    return {maturity, coupon, int(f)};
}

Bond bond_of(const In& in) {
    const Value& v = in.need("bond");
    if (v.kind != Kind::Object) schema("bond", "expected an object");
    return bond_fields(In(v));
}

Date delivery_month_of(const In& in) {
    const string& m = in.text("delivery_month");
    const auto d = m.size() == 7 ? parse_date(m + "-01") : std::nullopt;
    if (!d) schema("delivery_month", "expected YYYY-MM");
    return *d;
}


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


constexpr EnumTable<RateVolModel> rate_vol_models = {{"BLACK_76", RateVolModel::Black76}, {"BACHELIER", RateVolModel::Bachelier}};

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


std::vector<CashDividend> cash_dividends_of(const In& in) {
    return rows_of<CashDividend>(in, "dividends", [](const In& r) { return CashDividend{r.date("ex_date"), r.real("amount")}; });
}

std::vector<Constituent> constituents_of(const In& in, string_view key, bool with_dividends) {
    return rows_of<Constituent>(in, key, [&](const In& r) {
        Constituent c{r.text("id"), r.real("shares"), r.real("price"), {}};
        if (with_dividends) c.dividends = cash_dividends_of(r);
        return c;
    });
}


HazardCurve hazard_of(const Value& v, string_view key) {
    if (v.kind != Kind::Object) schema(key, "expected an object");
    const In h(v);
    HazardCurve out{h.date("as_of"), {}, {}};
    for (const auto& [d, s] : rows_of<std::pair<Date, double>>(h, "pillars", [](const In& row) {
             return std::pair{row.date("date"), row.real("survival")};
         })) {
        out.dates.push_back(d);
        out.survival.push_back(s);
    }
    return out;
}

void write_survival(Out& out, const HazardCurve& h) {
    out.values.key("pillars");
    out.values.begin_array();
    for (std::size_t i = 0; i < h.dates.size(); ++i) {
        out.values.begin_object();
        out.key_string("date", format_date(h.dates[i]));
        out.key_real("survival", h.survival[i]);
        out.values.end_object();
    }
    out.values.end_array();
}

// Ruling R1-4: ISDA flat forwards only, checked before every other rule check.
void require_flat_forwards(const CurveInput& d) {
    if (d.interpolation != CurveInterpolation::LogLinearDf)
        throw Error("E_INPUT", "credit needs a LOG_LINEAR_DF discount curve", "discount");
}

std::vector<CdsQuote> cds_quotes_of(const In& in) {
    return rows_of<CdsQuote>(in, "quotes", [](const In& q) { return CdsQuote{parse_tenor(q.text("tenor")), q.real("spread")}; });
}


struct RiskProduct {
    enum class Kind { Ois, Bond } kind;
    OisTrade trade{};
    Bond bond{};
    Date settlement{};
    double notional = 0.0;

    void check() const {
        if (kind == Kind::Bond && !(notional > 0.0)) throw Error("E_DOMAIN", "notional must be positive", "notional");
    }
    double value(const Curve& c) const {
        if (kind == Kind::Ois) return ois_price(trade, c).valuation.pv;
        return notional * curve_dirty(bond, settlement, c, 0.0) / 100.0;
    }
    double face() const { return kind == Kind::Ois ? trade.notional : notional; }
};

RiskProduct product_of(const In& in) {
    const Value& v = in.need("product");
    if (v.kind != Kind::Object) schema("product", "expected an object");
    const In p(v);
    RiskProduct out{p.choice<RiskProduct::Kind>("kind", {{"OIS", RiskProduct::Kind::Ois}, {"BOND", RiskProduct::Kind::Bond}})};
    if (out.kind == RiskProduct::Kind::Ois) {
        out.trade = ois_trade_of(p.need("trade"));
    } else {
        out.bond = bond_of(p);
        out.settlement = p.date("settlement");
        out.notional = p.real("notional");
    }
    return out;
}

double bump_of(const In& in) { return in.find("bump_bp") ? in.real("bump_bp") : 1.0; }

BumpScheme scheme_of(const In& in) {
    if (!in.find("scheme")) return BumpScheme::Central;
    return in.choice<BumpScheme>("scheme", {{"CENTRAL", BumpScheme::Central}, {"FORWARD", BumpScheme::Forward}});
}

CurvePricer pricer_of(const RiskProduct& p) {
    return [p](const Curve& c) { return p.value(c); };
}


std::vector<SviSlice> slices_of(const In& in) {
    return rows_of<SviSlice>(in, "slices", [](const In& row) { return SviSlice{row.real("expiry_years"), svi_of(row)}; });
}

void write_check(Out& out, const SviSurfaceCheck& c) {
    const auto grid = [&](string_view key, const std::vector<GridViolation>& v) {
        out.values.key(key);
        out.values.begin_array();
        for (const GridViolation& g : v) {
            out.values.begin_object();
            out.values.key("expiry_index");
            out.values.integer((long long)g.expiry_index);
            out.values.key("k_index");
            out.values.integer((long long)g.k_index);
            out.values.end_object();
        }
        out.values.end_array();
    };
    grid("butterfly_violations", c.butterfly);
    grid("calendar_violations", c.calendar);
    out.values.key("wing_violations");
    out.values.begin_array();
    for (const WingViolation& w : c.wings) {
        out.values.begin_object();
        out.values.key("expiry_index");
        out.values.integer((long long)w.expiry_index);
        out.key_string("side", w.side);
        out.key_string("kind", w.kind);
        out.values.end_object();
    }
    out.values.end_array();
    out.values.key("arbitrage_free");
    out.values.boolean(c.arbitrage_free());
}


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


std::vector<long long> integers_of(const In& in, string_view key) {
    const Value& a = in.need(key);
    if (a.kind != Kind::Array) schema(key, "expected an array");
    std::vector<long long> out;
    for (const Value& v : a.items) out.push_back(to_integer(v, key));
    return out;
}


ExoticMarket exotic_of(const In& in, bool with_strike = true, bool with_type = true) {
    ExoticMarket m;
    m.spot = in.real("spot");
    m.strike = with_strike ? in.real("strike") : 0.0;
    m.expiry_years = in.real("expiry_years");
    m.rate = in.real("rate");
    m.dividend_yield = in.real("dividend_yield");
    m.vol = in.real("vol");
    m.type = with_type ? in.choice("option_type", option_types) : OptionType::Call;
    return m;
}


// "SAMPLE" or a number; any other JSON type is E_SCHEMA. Another string is E_INPUT, raised after ready().
struct InitialVariance {
    std::optional<double> value;
    bool bad_string = false;
};

InitialVariance initial_variance_of(const In& in) {
    const Value& v = in.need("initial_variance");
    if (v.kind == Kind::String) return {std::nullopt, v.text != "SAMPLE"};
    return {to_real(v, "initial_variance"), false};
}

void check_initial_variance(const InitialVariance& iv) {
    if (iv.bad_string) throw Error("E_INPUT", "initial_variance must be SAMPLE or a number", "initial_variance");
}

VixTerm vix_term_of(const In& in) {
    VixTerm t;
    t.minutes = in.integer("minutes_to_expiry");
    t.rate = in.real("rate");
    t.strip = rows_of<VixQuote>(in, "strip", [](const In& q) {
        return VixQuote{q.real("strike"), q.real("call_bid"), q.real("call_ask"), q.real("put_bid"), q.real("put_ask")};
    });
    return t;
}

VixTerm vix_term_at(const In& in, string_view key) {
    const Value& v = in.need(key);
    if (v.kind != Kind::Object) schema(key, "expected an object");
    return vix_term_of(In(v));
}


CdsOptionInputs cds_option_of(const In& in) {
    CdsOptionInputs c;
    c.as_of = in.date("as_of");
    c.expiry = in.date("expiry");
    c.maturity = in.date("maturity");
    c.rate = in.real("rate");
    c.hazard_rate = in.real("hazard_rate");
    c.recovery = in.real("recovery");
    c.payer = in.choice<bool>("type", {{"PAYER", true}, {"RECEIVER", false}});
    c.strike = in.real("strike");
    c.notional = in.real("notional");
    c.knock_out = in.boolean("knock_out");
    return c;
}
