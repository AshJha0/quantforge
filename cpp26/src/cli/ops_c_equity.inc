// Stage C: equity forward. Included by dispatch.cpp, inside its anonymous namespace, after stage B.

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

void op_eq_outright(const In& in, Out& out) {
    const ForwardInput f = forward_of(in);
    in.ready();
    const EquityForward r = f.solve();
    out.key_real("forward", r.forward);
    out.key_real("discount_factor", r.discount_factor);
    out.key_real("carry_factor", r.carry_factor);
    out.key_real("pv_dividends", r.pv_dividends);
}

void op_eq_flat(const In& in, Out& out) {
    const double spot = in.real("spot"), rate = in.real("rate"), borrow = in.real("borrow"), t = in.real("expiry_years");
    const auto dividends = rows_of<TimedDividend>(in, "dividends", [](const In& r) { return TimedDividend{r.real("time_years"), r.real("amount")}; });
    in.ready();
    limit_if(dividends.size() > max_quotes, "dividends");
    out.key_real("forward", equity_forward_flat(spot, rate, borrow, t, dividends));
}

ParityQuote parity_quote_of(const In& r) {
    return {r.real("strike"), r.real("call_bid"), r.real("call_ask"), r.real("put_bid"), r.real("put_ask")};
}

void op_eq_parity(const In& in, Out& out) {
    const auto quotes = rows_of<ParityQuote>(in, "quotes", parity_quote_of);
    require_key(in, "discount_factor");
    const auto d = to_maybe_real(*in.raw().find("discount_factor"), "discount_factor");
    in.ready();
    limit_if(quotes.size() > max_quotes, "quotes");
    const ParityForward r = parity_forward(quotes, d);
    out.key_real("forward", r.forward);
    out.key_real("discount_factor", r.discount_factor);
    out.key_real("max_residual", r.max_residual);
    out.key_reals("outside_spread", r.outside_spread);
}
