// CLI handlers, the exotics verbs.
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.

void op_digital(const In& in, Out& out) {
    const ExoticMarket m = exotic_of(in);
    const auto payoff = in.choice<DigitalPayoff>(
        "payoff", {{"CASH_OR_NOTHING", DigitalPayoff::CashOrNothing}, {"ASSET_OR_NOTHING", DigitalPayoff::AssetOrNothing}});
    const double cash = in.real("cash");
    in.ready();
    out.key_real("price", digital_price(m, payoff, cash));
}

void op_barrier(const In& in, Out& out) {
    const ExoticMarket m = exotic_of(in);
    const double h = in.real("barrier"), rebate = in.real("rebate");
    const auto type = in.choice<BarrierType>("barrier_type", {{"DOWN_IN", BarrierType::DownIn},
                                                              {"DOWN_OUT", BarrierType::DownOut},
                                                              {"UP_IN", BarrierType::UpIn},
                                                              {"UP_OUT", BarrierType::UpOut}});
    // Stage G (R9, rulings G-7, G-8): discrete monitoring by the BGK barrier shift.
    bool discrete = false;
    if (const auto* mon = in.find("monitoring")) {
        if (mon->kind != Kind::String) schema("monitoring", "expected a string");
        if (mon->text == "DISCRETE") discrete = true;
        else if (mon->text != "CONTINUOUS") throw Error("E_INPUT", "monitoring is CONTINUOUS or DISCRETE", "monitoring");
    }
    const bool has_m = in.find("monitoring_per_year") != nullptr;
    if (discrete && !has_m) throw Error("E_INPUT", "monitoring_per_year is required with DISCRETE", "monitoring_per_year");
    if (!discrete && has_m) throw Error("E_INPUT", "monitoring_per_year is only allowed with DISCRETE", "monitoring_per_year");
    const long long per_year = has_m ? in.integer("monitoring_per_year") : 0;
    in.ready();
    if (has_m && per_year < 1) throw Error("E_DOMAIN", "monitoring_per_year is below 1", "monitoring_per_year");
    const double unshifted = barrier_price(m, h, rebate, type);  // the domain check uses the unshifted barrier (G-8)
    if (!discrete) {
        out.key_real("price", unshifted);
        return;
    }
    const double beta = 0.5826;
    const bool down = type == BarrierType::DownIn || type == BarrierType::DownOut;
    const double shift = std::exp((down ? -beta : beta) * m.vol * std::sqrt(1.0 / double(per_year)));
    out.key_real("price", barrier_price(m, h * shift, rebate, type));
}

void op_asian_geometric(const In& in, Out& out) {
    const ExoticMarket m = exotic_of(in);
    const bool continuous = in.choice<bool>("averaging", {{"CONTINUOUS", true}, {"DISCRETE", false}});
    const Vec fix = in.reals("fixing_years");
    in.ready();
    limit_if(fix.size() > max_quotes, "fixing_years");
    out.key_real("price", asian_geometric(m, continuous, fix));
}

void op_lookback(const In& in, Out& out) {
    const ExoticMarket m = exotic_of(in, false);
    const double ext = in.real("running_extreme");
    in.ready();
    out.key_real("price", lookback_floating(m, ext));
}

void op_quanto(const In& in, Out& out) {
    QuantoInputs q;
    q.spot = in.real("spot");
    q.strike = in.real("strike");
    q.expiry_years = in.real("expiry_years");
    q.domestic_rate = in.real("domestic_rate");
    q.foreign_rate = in.real("foreign_rate");
    q.dividend_yield = in.real("dividend_yield");
    q.vol = in.real("vol");
    q.fx_vol = in.real("fx_vol");
    q.correlation = in.real("correlation");
    q.type = in.choice("option_type", option_types);
    in.ready();
    out.key_real("price", quanto_price(q));
}

void op_chooser(const In& in, Out& out) {
    const ExoticMarket m = exotic_of(in, true, false);
    const double tc = in.real("choose_years");
    in.ready();
    out.key_real("price", chooser_price(m, tc));
}

void op_kirk(const In& in, Out& out) {
    const double f1 = in.real("forward_1"), f2 = in.real("forward_2"), k = in.real("strike"), t = in.real("expiry_years");
    const double r = in.real("rate"), v1 = in.real("vol_1"), v2 = in.real("vol_2"), rho = in.real("correlation");
    in.ready();
    out.key_real("price", kirk_spread(f1, f2, k, t, r, v1, v2, rho));
}

void op_basket(const In& in, Out& out) {
    const Vec f = in.reals("forwards"), w = in.reals("weights"), v = in.reals("vols");
    const Matrix c = in.matrix("correlation");
    const double k = in.real("strike"), t = in.real("expiry_years"), r = in.real("rate");
    const OptionType type = in.choice("option_type", option_types);
    in.ready();
    limit_if(f.size() > max_quotes || w.size() > max_quotes || v.size() > max_quotes || c.size() > max_quotes, "forwards");
    const BasketPrice b = basket_moment(f, w, v, c, k, t, r, type);
    out.key_real("price", b.price);
    out.key_real("basket_forward", b.basket_forward);
    out.key_real("basket_vol", b.basket_vol);
}

void op_american_crr(const In& in, Out& out) {
    const ExoticMarket m = exotic_of(in);
    const long long steps = in.integer("steps");
    in.ready();
    const AmericanTree a = american_crr(m, steps);
    out.key_real("american", a.american);
    out.key_real("european", a.european);
    out.key_real("early_exercise_premium", a.early_exercise_premium);
}

void op_american_baw(const In& in, Out& out) {
    const ExoticMarket m = exotic_of(in);
    in.ready();
    out.key_real("price", american_baw(m));
}

void op_american_fd(const In& in, Out& out) {
    const ExoticMarket m = exotic_of(in);
    const bool american = in.choice<bool>("exercise", {{"AMERICAN", true}, {"EUROPEAN", false}});
    const Value& gv = in.need("grid");
    if (gv.kind != Kind::Object) schema("grid", "expected an object");
    const In g(gv);
    const FdGrid grid{g.integer("nx"), g.integer("nt"), g.real("width")};
    in.ready();
    const FdResult r = american_fd(m, american, grid);
    out.key_real("price", r.price);
    out.key_real("delta", r.delta);
    out.key_real("gamma", r.gamma);
}

constexpr Entry exotics_ops[] = {
    {"exotic.american.baw", op_american_baw},
    {"exotic.american.crr", op_american_crr},
    {"exotic.american.fd", op_american_fd},
    {"exotic.asian.geometric", op_asian_geometric},
    {"exotic.barrier.price", op_barrier},
    {"exotic.basket.moment", op_basket},
    {"exotic.chooser.price", op_chooser},
    {"exotic.digital.price", op_digital},
    {"exotic.lookback.floating", op_lookback},
    {"exotic.quanto.price", op_quanto},
    {"exotic.spread.kirk", op_kirk},
};
