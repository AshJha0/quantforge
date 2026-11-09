// CLI handlers, the usecase verbs.
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.

void op_usecase_fx(const In& in, Out& out) {
    const FxInput f = fx_input(in);
    const Value& book = in.need("book");
    if (book.kind != Kind::Array) schema("book", "expected an array");
    std::vector<FxForwardTrade> trades;
    for (const Value& v : book.items) trades.push_back(fx_trade_of(v, "book"));
    const double half_spread = in.real("half_spread");
    in.ready();
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
    in.ready();
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

constexpr Entry usecase_ops[] = {
    {"usecase.fx_hedge", op_usecase_fx},
    {"usecase.rates_hedge", op_usecase_rates},
    {"usecase.vol_surface", op_usecase_vol_surface},
};
