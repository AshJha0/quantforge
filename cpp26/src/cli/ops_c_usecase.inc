// Stage C: use case 3.

void op_usecase_vol_surface(const In& in, Out& out) {
    struct Slice {
        Date expiry;
        std::vector<ParityQuote> quotes;
    };
    struct Target {
        OptionType type;
        double strike;
        Date expiry;
        double quantity;
        FxSide side;
    };
    const Date as_of = in.date("as_of");
    const CurveInput funding = curve_of(in, "funding_curve");
    const auto slices = rows_of<Slice>(in, "slices", [](const In& r) { return Slice{r.date("expiry"), rows_of<ParityQuote>(r, "quotes", parity_quote_of)}; });
    const Vec k_grid = in.reals("k_grid");
    const Value& target_value = in.need("target");
    if (target_value.kind != Kind::Object) schema("target", "expected an object");
    const In tr(target_value);
    const Target target{tr.choice("option_type", option_types), tr.real("strike"), tr.date("expiry"), tr.real("quantity"), tr.choice("side", fx_sides)};
    const string& currency = currency_of(in);
    in.ready();
    funding.limit();
    limit_if(slices.size() > max_quotes || k_grid.size() > max_quotes, "slices");
    for (const Slice& s : slices) limit_if(s.quotes.size() > max_quotes, "quotes");
    need_items(slices, "slices");
    need_items(k_grid, "k_grid");
    for (const Slice& s : slices) need_items(s.quotes, "quotes");

    const Curve curve = funding.build();
    if (curve.as_of() != as_of) throw Error("E_INPUT", "the curve as_of differs");
    Vec forwards, rmses, times, discounts;
    std::vector<Svi> fits;
    for (const Slice& s : slices) {
        if (s.expiry < as_of) throw Error("E_DATE_ORDER", "expiry is before as_of");
        const double t = double(days_between(as_of, s.expiry)) / 365.0, d = curve.discount(s.expiry);
        const ParityForward p = parity_forward(s.quotes, d);
        Vec k, w;
        for (const ParityQuote& q : s.quotes) {
            const bool call = q.strike >= p.forward;
            OptionInput o{VolModel::Black76, call ? OptionType::Call : OptionType::Put, q.strike, t};
            o.forward = p.forward;
            o.discount_factor = d;
            const double v = implied_vol(o, call ? (q.call_bid + q.call_ask) / 2 : (q.put_bid + q.put_ask) / 2);
            k.push_back(std::log(q.strike / p.forward));
            w.push_back(v * v * t);
        }
        const SviFit fit = svi_calibrate(k, w, std::nullopt);
        forwards.push_back(p.forward);
        rmses.push_back(fit.rmse);
        times.push_back(t);
        discounts.push_back(d);
        fits.push_back(fit.svi);
    }

    Surface surface{times, k_grid, {}};
    for (std::size_t j = 0; j < fits.size(); ++j) {
        Vec row;
        for (const double k : k_grid) row.push_back(std::sqrt(fits[j].w(k) / times[j]));
        surface.vols.push_back(std::move(row));
    }
    check_surface(surface);
    const SurfaceCheck check = surface_check(surface);

    std::size_t at = slices.size();
    for (std::size_t j = 0; j < slices.size(); ++j)
        if (slices[j].expiry == target.expiry) at = j;
    if (at == slices.size()) throw Error("E_INPUT", "target expiry is not a slice");
    if (target.strike <= 0 || target.quantity <= 0) throw Error("E_DOMAIN", "strike and quantity must be above 0");
    const double vol = std::sqrt(fits[at].w(std::log(target.strike / forwards[at])) / times[at]);
    const double signed_quantity = target.side == FxSide::Buy ? target.quantity : -target.quantity;
    const PositionRisk r = position_risk(forwards[at], target.strike, vol, times[at], discounts[at], target.type, signed_quantity);

    out.key_reals("forwards", forwards);
    out.key_reals("svi_rmse", rmses);
    out.values.key("arbitrage_free");
    out.values.boolean(check.calendar.empty() && check.butterfly.empty());
    out.key_real("vol", vol);
    write_valuation(out, {r.pv, currency, "BLACK_76_EQUITY", std::nullopt, "EQUITY_FORWARD", as_of});
    out.key_real("delta", r.delta_forward);
    out.key_real("vega", r.vega);
}
