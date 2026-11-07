// Stage C: surface query, check and surface vega.

Surface surface_of(const In& in) {
    const Value& v = in.need("surface");
    if (v.kind != Kind::Object) schema("surface", "expected an object");
    const In s(v);
    return {s.reals("expiry_years"), s.reals("log_moneyness"), s.matrix("vols")};
}

void limit_surface(const Surface& s) {
    limit_if(s.expiry_years.size() > max_quotes || s.log_moneyness.size() > max_quotes, "surface");
}

void op_surface_query(const In& in, Out& out) {
    struct Point {
        double t, k;
    };
    const Surface s = surface_of(in);
    const auto points = rows_of<Point>(in, "points", [](const In& r) { return Point{r.real("expiry_years"), r.real("log_moneyness")}; });
    in.ready();
    limit_surface(s);
    limit_if(points.size() > max_quotes, "points");
    need_items(points, "points");
    check_surface(s);
    Vec w, vols;
    for (const Point& p : points) {
        if (p.t <= 0) throw Error("E_DOMAIN", "expiry_years is not above 0");
        w.push_back(surface_total_variance(s, p.t, p.k));
        vols.push_back(std::sqrt(w.back() / p.t));
    }
    out.key_reals("total_variance", w);
    out.key_reals("vols", vols);
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

void op_surface_check(const In& in, Out& out) {
    const Surface s = surface_of(in);
    in.ready();
    limit_surface(s);
    check_surface(s);
    write_surface_check(out, surface_check(s));
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

void op_surface_vega(const In& in, Out& out) {
    const Surface s = surface_of(in);
    const auto positions = rows_of<VegaPosition>(in, "positions", [](const In& r) {
        return VegaPosition{r.choice("option_type", option_types), r.real("forward"), r.real("strike"),
                            r.real("discount_factor"), r.real("expiry_years"), r.real("quantity")};
    });
    in.ready();
    limit_surface(s);
    limit_if(positions.size() > max_quotes, "positions");
    need_items(positions, "positions");
    check_surface(s);
    for (const VegaPosition& p : positions)
        if (p.forward <= 0 || p.strike <= 0 || p.discount_factor <= 0 || p.expiry_years <= 0)
            throw Error("E_DOMAIN", "a position input is not above 0");
    constexpr double bump = 1e-4;
    for (const Vec& row : s.vols)
        for (const double v : row)
            if (v - bump <= 0) throw Error("E_DOMAIN", "a node vol is too low to bump");
    Surface moved = s;
    Matrix buckets = s.vols;
    double bucket_sum = 0.0;
    for (std::size_t j = 0; j < s.vols.size(); ++j)
        for (std::size_t i = 0; i < s.vols[j].size(); ++i) {
            moved.vols[j][i] = s.vols[j][i] + bump;
            const double up = surface_pv(moved, positions);
            moved.vols[j][i] = s.vols[j][i] - bump;
            const double down = surface_pv(moved, positions);
            moved.vols[j][i] = s.vols[j][i];
            buckets[j][i] = (up - down) / (2 * bump);
            bucket_sum += buckets[j][i];
        }
    const auto shifted = [&](double by) {
        Surface all = s;
        for (Vec& row : all.vols)
            for (double& v : row) v += by;
        return surface_pv(all, positions);
    };
    out.key_real("pv", surface_pv(s, positions));
    out.values.key("bucket_vega");
    out.values.begin_array();
    for (const Vec& row : buckets) {
        out.values.begin_array();
        for (const double x : row) out.values.real(x);
        out.values.end_array();
    }
    out.values.end_array();
    out.key_real("parallel_vega", (shifted(bump) - shifted(-bump)) / (2 * bump));
    out.key_real("bucket_sum", bucket_sum);
}
