#include "quantforge/core/bonds.hpp"

#include <algorithm>
#include <cmath>

#include "quantforge/core/error.hpp"
#include "quantforge/core/finite.hpp"
#include "quantforge/core/linalg.hpp"

namespace quantforge {
namespace {

double days(Date a, Date b) { return double(days_between(a, b)); }

void require_finite_bond(const Bond& b, std::string_view field = "coupon") { require_finite(b.coupon, field); }

Date month_end(Date d) {
    using namespace std::chrono;
    const year_month_day ymd{d};
    return sys_days{ymd.year() / ymd.month() / last};
}

/// Root of a strictly decreasing f, by bracket expansion and Illinois false position to full precision.
template <class F>
double decreasing_root(F f, double guess, double step, double lower_bound) {
    double a = guess, fa = f(a);
    if (fa == 0.0) return a;
    double b = a, fb = fa;
    for (int i = 0; i < 200 && (fa > 0.0) == (fb > 0.0); ++i) {
        if (fa > 0.0) b += step;
        else b = std::max(b - step, lower_bound + (b - lower_bound) / 2.0);
        fb = f(b);
        step *= 2.0;
    }
    if ((fa > 0.0) == (fb > 0.0) || !std::isfinite(fb)) throw Error("E_NO_CONVERGENCE", "no bracket for the root");
    int side = 0;
    for (int i = 0; i < 300; ++i) {
        const double c = (a * fb - b * fa) / (fb - fa);
        if (!(c > std::min(a, b) && c < std::max(a, b))) break;
        const double fc = f(c);
        if (fc == 0.0) return c;
        if ((fc > 0.0) == (fb > 0.0)) {
            b = c;
            fb = fc;
            if (side == -1) fa /= 2.0;
            side = -1;
        } else {
            a = c;
            fa = fc;
            if (side == 1) fb /= 2.0;
            side = 1;
        }
    }
    return std::fabs(fa) < std::fabs(fb) ? a : b;
}

}  // namespace

std::vector<Date> roll_back(Date maturity, int months, Date from, bool month_end_rule) {
    const bool eom = month_end_rule && maturity == month_end(maturity);
    std::vector<Date> out{maturity};
    for (int k = 1;; ++k) {
        Date d = add_months(maturity, -k * months);
        if (eom) d = month_end(d);
        out.push_back(d);
        if (d <= from) break;
    }
    std::ranges::reverse(out);
    return out;
}

BondPeriod bond_period(const Bond& b, Date settlement) {
    require_finite_bond(b);
    if (settlement >= b.maturity) throw Error("E_DATE_ORDER", "settlement must be before maturity", "settlement");
    const auto dates = roll_back(b.maturity, 12 / b.frequency, settlement);
    return {dates[0], dates[1], std::vector<Date>(dates.begin() + 1, dates.end())};
}

double coupon_amount(const Bond& b) {
    require_finite_bond(b);
    return 100.0 * b.coupon / b.frequency;
}

double accrued(const Bond& b, Date settlement) {
    require_finite_bond(b);
    const BondPeriod p = bond_period(b, settlement);
    return coupon_amount(b) * days(p.prev, settlement) / days(p.prev, p.next);
}

namespace {

// The unchecked kernel; the root search below calls it with trial yields.
YieldPrice price_from_yield_raw(const Bond& b, Date settlement, double y) {
    const BondPeriod p = bond_period(b, settlement);
    const double f = b.frequency;
    if (!(1.0 + y / f > 0.0)) throw Error("E_DOMAIN", "1 + yield/frequency must be positive", "yield");
    const double v = 1.0 / (1.0 + y / f), w = days(settlement, p.next) / days(p.prev, p.next);
    const double c = coupon_amount(b);
    double dirty = 0.0, dur = 0.0, conv = 0.0;
    for (std::size_t k = 0; k < p.flows.size(); ++k) {
        const double cf = c + (k + 1 == p.flows.size() ? 100.0 : 0.0), e = double(k) + w;
        const double pv = cf * std::pow(v, e);
        dirty += pv;
        dur += e / f * pv;
        conv += e * (e + 1.0) / (f * f) * pv * v * v;
    }
    const double acc = c * days(p.prev, settlement) / days(p.prev, p.next);
    return {dirty, acc, dirty - acc, dur / dirty * v, dur / dirty, conv / dirty};
}

}  // namespace

YieldPrice price_from_yield(const Bond& b, Date settlement, double y) {
    require_finite_bond(b);
    require_finite(y, "yield");
    return price_from_yield_raw(b, settlement, y);
}

double yield_from_price(const Bond& b, Date settlement, double clean_price) {
    require_finite_bond(b);
    require_finite(clean_price, "clean_price");
    const double acc = accrued(b, settlement);
    if (!(clean_price > 0.0) || !(clean_price + acc > 0.0)) throw Error("E_DOMAIN", "the dirty price is not positive", "clean_price");
    const double f = b.frequency;
    double y = decreasing_root([&](double x) { return price_from_yield_raw(b, settlement, x).clean - clean_price; },
                               b.coupon, 0.01, -f);
    // Newton polish at full precision.
    for (int i = 0; i < 3; ++i) {
        const YieldPrice p = price_from_yield_raw(b, settlement, y);
        const double step = (p.clean - clean_price) / (p.modified_duration * p.dirty);
        if (!std::isfinite(step) || !(1.0 + (y + step) / f > 0.0)) break;
        y += step;
    }
    return y;
}

namespace {

// The unchecked kernel; the z-spread root search calls it with trial spreads.
double curve_dirty_raw(const Bond& b, Date settlement, const Curve& curve, double z) {
    const BondPeriod p = bond_period(b, settlement);
    if (settlement < curve.as_of()) throw Error("E_OUT_OF_RANGE", "settlement is before the curve's as_of", "settlement");
    const auto ds = [&](Date d) { return curve.discount(d) * std::exp(-z * curve.time(d)); };
    const double c = coupon_amount(b);
    double sum = 0.0;
    for (std::size_t k = 0; k < p.flows.size(); ++k) sum += (c + (k + 1 == p.flows.size() ? 100.0 : 0.0)) * ds(p.flows[k]);
    return sum / ds(settlement);
}

}  // namespace

double curve_dirty(const Bond& b, Date settlement, const Curve& curve, double z) {
    require_finite_bond(b);
    require_finite(z, "z");
    return curve_dirty_raw(b, settlement, curve, z);
}

double z_spread(const Bond& b, Date settlement, const Curve& curve, double clean_price) {
    require_finite_bond(b);
    require_finite(clean_price, "clean_price");
    const double target = clean_price + accrued(b, settlement);
    (void)curve_dirty_raw(b, settlement, curve, 0.0);  // checks first
    return decreasing_root([&](double z) { return curve_dirty_raw(b, settlement, curve, z) - target; }, 0.0, 0.01, -HUGE_VAL);
}

AssetSwap asset_swap(const Bond& b, Date settlement, const Curve& curve, double dirty_price) {
    require_finite_bond(b);
    require_finite(dirty_price, "dirty_price");
    const double model = curve_dirty_raw(b, settlement, curve, 0.0);
    const auto dates = roll_back(b.maturity, 3, settlement, false);
    double annuity = 0.0;
    Date s = settlement;
    for (std::size_t j = 1; j < dates.size(); ++j) {
        annuity += days(s, dates[j]) / 360.0 * curve.discount(dates[j]);
        s = dates[j];
    }
    annuity /= curve.discount(settlement);
    return {(model - dirty_price) / (100.0 * annuity), annuity};
}

FrnPrice frn_price(const Frn& n, Date settlement, const Curve& discount, const Curve& projection) {
    require_finite(n.current_rate, "current_rate");
    require_finite(n.margin, "margin");
    require_finite(n.discount_margin, "discount_margin");
    const Bond shape{n.maturity, 0.0, n.frequency};
    const BondPeriod p = bond_period(shape, settlement);
    if (settlement < discount.as_of()) throw Error("E_OUT_OF_RANGE", "settlement is before the curve's as_of", "settlement");
    const auto dm = [&](Date d) { return discount.discount(d) * std::exp(-n.discount_margin * discount.time(d)); };
    double sum = 0.0;
    Date s = p.prev;
    for (std::size_t i = 0; i < p.flows.size(); ++i) {
        const Date e = p.flows[i];
        const double alpha = days(s, e) / 360.0;
        const double r = i == 0 ? n.current_rate : (projection.discount(s) / projection.discount(e) - 1.0) / alpha;
        sum += 100.0 * (r + n.margin) * alpha * dm(e);
        s = e;
    }
    sum += 100.0 * dm(n.maturity);
    const double dirty = sum / dm(settlement);
    const double acc = 100.0 * (n.current_rate + n.margin) * days(p.prev, settlement) / 360.0;
    return {dirty, acc, dirty - acc};
}

namespace {

struct RepoTerms {
    double dirty, t, coupons, coupons_weighted;  // sum c, sum c (end - d)/360
};

RepoTerms repo_terms(const Bond& b, Date start, Date end, double clean_price) {
    if (end <= start) throw Error("E_DATE_ORDER", "end must be after start", "end");
    if (end >= b.maturity) throw Error("E_INPUT", "end must be before maturity", "end");
    const BondPeriod p = bond_period(b, start);
    RepoTerms r{clean_price + accrued(b, start), days(start, end) / 360.0, 0.0, 0.0};
    for (const Date d : p.flows)
        if (d > start && d <= end) {
            r.coupons += coupon_amount(b);
            r.coupons_weighted += coupon_amount(b) * days(d, end) / 360.0;
        }
    return r;
}

}  // namespace

RepoForward repo_forward(const Bond& b, Date start, Date end, double clean_price, double r, std::optional<double> gc) {
    require_finite_bond(b);
    require_finite(clean_price, "clean_price");
    require_finite(r, "repo_rate");
    require_finite(gc, "gc_rate");
    const RepoTerms t = repo_terms(b, start, end, clean_price);
    const double fd = t.dirty * (1.0 + r * t.t) - (t.coupons + r * t.coupons_weighted);
    RepoForward out{t.dirty, fd, fd - accrued(b, end), t.dirty * r * t.t, std::nullopt, std::nullopt};
    if (gc) {
        out.special_spread = *gc - r;
        out.specialness_value = t.dirty * (*gc - r) * t.t;
    }
    return out;
}

double repo_implied_rate(const Bond& b, Date start, Date end, double clean_price, double forward_clean) {
    require_finite_bond(b);
    require_finite(clean_price, "clean_price");
    require_finite(forward_clean, "forward_clean");
    const RepoTerms t = repo_terms(b, start, end, clean_price);
    const double fd = forward_clean + accrued(b, end);
    return (fd - t.dirty + t.coupons) / (t.dirty * t.t - t.coupons_weighted);
}

double conversion_factor(const Bond& b, Date delivery, double notional_coupon, FuturesContract contract) {
    require_finite_bond(b);
    require_finite(notional_coupon, "notional_coupon");
    if (notional_coupon != 0.06) throw Error("E_INPUT", "notional_coupon must be 0.06", "notional_coupon");
    if (b.frequency != 2) throw Error("E_INPUT", "only semi-annual bonds", "bond");
    if (delivery >= b.maturity) throw Error("E_DATE_ORDER", "maturity must follow the delivery month", "delivery_month");
    int months = (year_of(b.maturity) - year_of(delivery)) * 12 + int(month_of(b.maturity)) - int(month_of(delivery));
    // Ruling R1-3: the coupon on the 1/8 of 1% grid, ties up; whole months for the short contracts.
    const double cpn = std::floor(b.coupon * 800.0 + 0.5) / 800.0;
    const bool whole = contract == FuturesContract::TwoYear || contract == FuturesContract::ThreeYear ||
                       contract == FuturesContract::FiveYear;
    const int n = months / 12, z = whole ? months % 12 : months % 12 / 3 * 3;
    const double v = z < 7 ? z : z - 6;
    const double a = std::pow(1.03, -v / 6.0), bb = cpn / 2.0 * (6.0 - v) / 6.0;
    const double c = z < 7 ? std::pow(1.03, -2.0 * n) : std::pow(1.03, -2.0 * n - 1.0);
    const double cf = a * (cpn / 2.0 + (cpn / 0.06) * (1.0 - c) + c) - bb;
    return std::nearbyint(cf * 1e4) / 1e4;  // default rounding mode: half-even
}

Basis futures_basis(double f, Date settlement, Date delivery, double r, const std::vector<BasisBond>& bonds) {
    require_finite(f, "futures_price");
    require_finite(r, "repo_rate");
    for (const BasisBond& x : bonds) {
        require_finite_bond(x.bond, "bonds");
        require_finite(x.clean_price, "bonds");
        require_finite(x.conversion_factor, "bonds");
    }
    if (bonds.empty()) throw Error("E_INPUT", "no bonds", "bonds");
    Basis out{{}, 0};
    for (const BasisBond& x : bonds) {
        const RepoTerms t = repo_terms(x.bond, settlement, delivery, x.clean_price);
        const double invoice = f * x.conversion_factor + accrued(x.bond, delivery);
        const double fd = t.dirty * (1.0 + r * t.t) - (t.coupons + r * t.coupons_weighted);
        out.bonds.push_back({invoice, x.clean_price - f * x.conversion_factor, fd - invoice,
                             (invoice + t.coupons - t.dirty) / (t.dirty * t.t - t.coupons_weighted)});
    }
    for (std::size_t i = 1; i < out.bonds.size(); ++i)
        if (out.bonds[i].implied_repo > out.bonds[out.ctd].implied_repo) out.ctd = i;
    return out;
}

NsFit bond_nelson_siegel(Date settlement, double tau, const std::vector<NsBond>& bonds,
                         const std::optional<std::vector<double>>& weights) {
    require_finite(tau, "tau");
    for (const NsBond& nb : bonds) {
        require_finite_bond(nb.bond, "bonds");
        require_finite(nb.dirty_price, "bonds");
    }
    require_finite(weights, "weights");
    if (weights && weights->size() != bonds.size()) throw Error("E_INPUT", "weights must match bonds", "weights");
    const std::vector<double> w = weights ? *weights : std::vector<double>(bonds.size(), 1.0);
    if (std::ranges::count_if(w, [](double x) { return x > 0.0; }) < 3)
        throw Error("E_INPUT", "at least 3 positive weights are needed", "weights");
    if (!(tau > 0.0)) throw Error("E_DOMAIN", "tau is not positive", "tau");
    for (const double x : w)
        if (!(x >= 0.0)) throw Error("E_DOMAIN", "a weight is negative", "weights");
    struct Flow {
        double t, cf, e1, e2;
    };
    std::vector<std::vector<Flow>> flows;
    for (const NsBond& nb : bonds) {
        const BondPeriod p = bond_period(nb.bond, settlement);
        std::vector<Flow> f;
        for (std::size_t k = 0; k < p.flows.size(); ++k) {
            const double t = days(settlement, p.flows[k]) / 365.0, u = t / tau, e = -std::expm1(-u) / u;
            f.push_back({t, coupon_amount(nb.bond) + (k + 1 == p.flows.size() ? 100.0 : 0.0), e, e - std::exp(-u)});
        }
        flows.push_back(std::move(f));
    }
    const std::size_t n = bonds.size();
    // Residuals and their Jacobian in the betas.
    const auto eval = [&](const std::vector<double>& b, std::vector<double>& r, Matrix* jac) {
        r.assign(n, 0.0);
        if (jac) jac->assign(n, std::vector<double>(3, 0.0));
        for (std::size_t i = 0; i < n; ++i) {
            double model = 0.0;
            for (const Flow& f : flows[i]) {
                const double z = b[0] + b[1] * f.e1 + b[2] * f.e2, pv = f.cf * std::exp(-z * f.t);
                model += pv;
                if (jac) {
                    (*jac)[i][0] -= f.t * pv;
                    (*jac)[i][1] -= f.t * f.e1 * pv;
                    (*jac)[i][2] -= f.t * f.e2 * pv;
                }
            }
            r[i] = model - bonds[i].dirty_price;
        }
    };
    const auto objective = [&](const std::vector<double>& r) {
        double s = 0.0;
        for (std::size_t i = 0; i < n; ++i) s += w[i] * r[i] * r[i];
        return s;
    };
    std::vector<double> b{0.03, 0.0, 0.0}, r;
    Matrix jac;
    eval(b, r, &jac);
    double obj = objective(r), mu = 1e-3;
    for (int it = 0; it < 500; ++it) {
        Matrix a(3, std::vector<double>(3, 0.0));
        std::vector<double> g(3, 0.0);
        for (std::size_t i = 0; i < n; ++i)
            for (int k = 0; k < 3; ++k) {
                g[k] -= w[i] * jac[i][k] * r[i];
                for (int l = 0; l < 3; ++l) a[k][l] += w[i] * jac[i][k] * jac[i][l];
            }
        bool improved = false;
        for (int tries = 0; tries < 40 && !improved; ++tries) {
            Matrix m = a;
            for (int k = 0; k < 3; ++k) m[k][k] *= 1.0 + mu;
            std::vector<double> step = lu_solve(m, g);
            std::vector<double> nb{b[0] + step[0], b[1] + step[1], b[2] + step[2]}, nr;
            eval(nb, nr, nullptr);
            const double no = objective(nr);
            if (std::isfinite(no) && no <= obj) {
                const double change = std::max({std::fabs(step[0]), std::fabs(step[1]), std::fabs(step[2])});
                b = nb;
                improved = true;
                mu = std::max(mu / 10.0, 1e-12);
                if (change < 1e-16 || no == obj) {
                    obj = no;
                    it = 1000;
                    break;
                }
                obj = no;
            } else {
                mu *= 10.0;
            }
        }
        if (!improved) break;
        eval(b, r, &jac);
    }
    eval(b, r, nullptr);
    return {b, r};
}

}  // namespace quantforge
