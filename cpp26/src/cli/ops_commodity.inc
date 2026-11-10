// CLI handlers, the commodity verbs.
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.

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

constexpr Entry commodity_ops[] = {
    {"cmdty.curve.forward", op_cmdty_forward},
    {"cmdty.storage.carry", op_storage_carry},
};
