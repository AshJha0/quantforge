#include "quantforge/core/joint.hpp"

#include <algorithm>
#include <cmath>
#include <functional>
#include <limits>
#include <map>
#include <optional>
#include <set>

#include "quantforge/core/error.hpp"
#include "quantforge/core/finite.hpp"
#include "quantforge/core/multicurve.hpp"

namespace quantforge {
namespace {

[[noreturn]] void bad(const std::string& message, std::string field = "instruments") {
    throw Error("E_INPUT", message, std::move(field));
}

[[noreturn]] void no_convergence() { throw Error("E_NO_CONVERGENCE", "the joint solve did not converge"); }

constexpr double required = 1e-13;
constexpr std::size_t none = std::numeric_limits<std::size_t>::max();

double days(Date a, Date b) { return double(days_between(a, b)); }

bool pillar_curve(JointCurveType t) { return t != JointCurveType::OisSteps; }

bool allowed(JointCurveType c, JointInstrumentType i) {
    switch (c) {
        case JointCurveType::Ois:
        case JointCurveType::OisSteps:
            return i == JointInstrumentType::Ois || i == JointInstrumentType::Future;
        case JointCurveType::Projection:
            return i == JointInstrumentType::Deposit || i == JointInstrumentType::Fra || i == JointInstrumentType::Swap;
        case JointCurveType::Xccy:
            return i == JointInstrumentType::Xccy;
    }
    return false;
}

// One curve of the system: a block of unknowns and the instruments that pin them.
struct Block {
    const JointCurveSpec* spec = nullptr;
    std::size_t first = 0, size = 0;  // unknown offsets; turns are the last turns.size() of the block
    std::size_t base_count = 0;       // pillars, or 1 + step dates
    std::vector<std::size_t> instruments;  // in instrument order: the block's residual rows
    std::vector<Date> pillars;
    std::vector<Jump> jumps;               // fixed jumps and turns, by date
    std::vector<std::size_t> turn_slot;    // per turn, its index in jumps
    std::size_t discount = none, foreign = none;  // PROJECTION discount; XCCY foreign projection
};

struct Prepared {
    std::size_t curve = 0;
    std::vector<Period> ois;
    ProjectionInstrument projection{};
    std::vector<Date> xccy;
    double alpha = 0.0;   // FUTURE ACT/360 accrual
    double target = 0.0;  // model value that zeroes the residual
    double dq = -1.0;     // d residual / d quote (XCCY filled at the solution)
    Date first{}, last{}; // the dates the model reads
};

struct Built {
    std::vector<std::optional<Curve>> curve;
    std::vector<std::optional<StepCurve>> steps;
    double discount(std::size_t k, Date d) const { return curve[k] ? curve[k]->discount(d) : steps[k]->discount(d); }
};

class System {
public:
    System(Date as_of, const std::vector<JointCurveSpec>& curves, const std::vector<JointInstrument>& instruments)
        : as_of_(as_of), specs_(curves), inst_(instruments) {
        validate();
    }

    JointResult solve();

private:
    Date as_of_;
    const std::vector<JointCurveSpec>& specs_;
    const std::vector<JointInstrument>& inst_;
    std::vector<Block> blocks_;
    std::vector<Prepared> prep_;
    std::size_t n_ = 0;

    void validate();
    void build(std::size_t k, const std::vector<double>& x, Built& b) const;
    double model(std::size_t j, const Built& b) const;
    std::vector<double> residuals(const std::vector<double>& x) const;
    void solve_block(std::size_t k, std::vector<double>& x, Built& b) const;
};

void System::validate() {
    std::map<std::string, std::size_t> names;
    blocks_.resize(specs_.size());
    const auto earlier = [&](const std::string& name, std::size_t k, const char* field) {
        const auto it = names.find(name);
        if (it == names.end()) bad("curve " + specs_[k].name + " names an unknown or later curve", field);
        const JointCurveType t = specs_[it->second].type;
        if (t != JointCurveType::Ois && t != JointCurveType::OisSteps) bad(std::string(field) + " must name an OIS curve", field);
        return it->second;
    };
    for (std::size_t k = 0; k < specs_.size(); ++k) {
        const JointCurveSpec& c = specs_[k];
        Block& b = blocks_[k];
        b.spec = &c;
        if (c.type == JointCurveType::Projection) b.discount = earlier(c.discount, k, "discount");
        if (c.type == JointCurveType::Xccy) {
            earlier(c.domestic, k, "domestic");
            b.foreign = earlier(c.foreign_projection, k, "foreign_projection");
        }
        if (!names.emplace(c.name, k).second) bad("duplicate curve name " + c.name, "curves");
    }
    std::set<std::string> ids;
    prep_.resize(inst_.size());
    for (std::size_t j = 0; j < inst_.size(); ++j) {
        const JointInstrument& in = inst_[j];
        if (!ids.insert(in.id).second) bad("duplicate instrument id " + in.id);
        const auto it = names.find(in.curve);
        if (it == names.end()) bad("instrument " + in.id + " names an unknown curve");
        if (!allowed(specs_[it->second].type, in.type)) bad("instrument " + in.id + " is not allowed on its curve");
        prep_[j].curve = it->second;
        blocks_[it->second].instruments.push_back(j);
    }
    for (const JointCurveSpec& c : specs_) {
        Date previous = as_of_;
        for (const Date d : c.step_dates) {
            if (d <= previous) bad("step_dates must increase and follow as_of", "step_dates");
            previous = d;
        }
        previous = as_of_;
        for (const Date d : c.turns) {
            if (d <= previous) bad("turns must increase and follow as_of", "turns");
            previous = d;
        }
    }
    for (Block& b : blocks_) {
        const JointCurveSpec& c = *b.spec;
        std::size_t turns = 0;
        for (const std::size_t j : b.instruments) turns += inst_[j].turn ? 1 : 0;
        if (turns != c.turns.size()) bad("curve " + c.name + " needs one turn instrument per turn");
        if (c.type == JointCurveType::OisSteps) {
            b.base_count = 1 + c.step_dates.size();
            if (b.instruments.size() != b.base_count + c.turns.size()) bad("curve " + c.name + " needs 1 + step dates + turns instruments");
        } else {
            b.base_count = b.instruments.size() - turns;
            if (b.base_count == 0) bad("curve " + c.name + " has no pillar instrument");
        }
        b.size = b.base_count + c.turns.size();
        b.first = n_;
        n_ += b.size;
        // Fixed jumps and turns together, in date order.
        for (const Jump& jp : c.jumps) b.jumps.push_back(jp);
        for (const Date d : c.turns) b.jumps.push_back({d, 1.0});
        std::sort(b.jumps.begin(), b.jumps.end(), [](const Jump& x, const Jump& y) { return x.date < y.date; });
        check_jumps(as_of_, b.jumps);
        for (const Date d : c.turns)
            for (std::size_t s = 0; s < b.jumps.size(); ++s)
                if (b.jumps[s].date == d) b.turn_slot.push_back(s);
    }
    // Instrument dates and pillars.
    for (std::size_t j = 0; j < inst_.size(); ++j) {
        const JointInstrument& in = inst_[j];
        Prepared& p = prep_[j];
        const JointCurveSpec& c = specs_[p.curve];
        Date pillar{};
        switch (in.type) {
            case JointInstrumentType::Ois:
                p.ois = ois_periods(*c.convention, as_of_, in.tenor);
                p.first = p.ois.front().start;
                p.last = std::max(p.ois.back().end, p.ois.back().payment);
                pillar = p.ois.back().payment;
                p.target = in.rate;
                break;
            case JointInstrumentType::Future:
                p.first = in.start;
                p.last = in.end;
                pillar = in.end;
                break;
            case JointInstrumentType::Deposit:
            case JointInstrumentType::Fra:
            case JointInstrumentType::Swap: {
                const ProjectionQuoteType t = in.type == JointInstrumentType::Deposit ? ProjectionQuoteType::Deposit
                                              : in.type == JointInstrumentType::Fra   ? ProjectionQuoteType::Fra
                                                                                      : ProjectionQuoteType::Swap;
                p.projection = projection_instrument(*c.convention, as_of_, {t, in.months, in.rate});
                p.first = p.projection.start;
                p.last = p.projection.end;
                for (const Period& q : p.projection.floating) p.last = std::max(p.last, q.end);
                pillar = p.projection.pillar();
                p.target = in.rate;
                break;
            }
            case JointInstrumentType::Xccy:
                p.xccy = xccy_schedule(c.start, in.months);
                if (c.start < as_of_) throw Error("E_OUT_OF_RANGE", "start is before as_of", "start");
                p.first = p.xccy.front();
                p.last = p.xccy.back();
                pillar = p.xccy.back();
                p.target = 0.0;
                break;
        }
        if (!in.turn && pillar_curve(c.type)) blocks_[p.curve].pillars.push_back(pillar);
    }
    for (Block& b : blocks_) {
        if (!pillar_curve(b.spec->type)) continue;
        Date previous = as_of_;
        for (const Date d : b.pillars) {
            if (d <= previous) bad("pillar dates must increase in instrument order on curve " + b.spec->name);
            previous = d;
        }
        check_shape(b.spec->interpolation, b.spec->shape, b.pillars);
    }
    for (std::size_t j = 0; j < inst_.size(); ++j) {
        const JointInstrument& in = inst_[j];
        if (in.type != JointInstrumentType::Future) continue;
        if (in.sigma < 0.0) throw Error("E_DOMAIN", "sigma is negative", "sigma");
        if (in.mean_reversion < 0.0) throw Error("E_DOMAIN", "mean_reversion is negative", "mean_reversion");
        if (in.end <= in.start) bad("a future's end must follow its start", "end");
        const Convexity cv =
            futures_convexity(in.price, days(as_of_, in.start) / 365.0, days(as_of_, in.end) / 365.0, in.sigma, in.mean_reversion);
        prep_[j].alpha = days(in.start, in.end) / 360.0;
        prep_[j].target = cv.forward_rate;
        prep_[j].dq = 0.01 * std::exp(-cv.z);
    }
}

void System::build(std::size_t k, const std::vector<double>& x, Built& b) const {
    const Block& bl = blocks_[k];
    std::vector<Jump> jumps = bl.jumps;
    for (std::size_t t = 0; t < bl.turn_slot.size(); ++t) jumps[bl.turn_slot[t]].factor = std::exp(x[bl.first + bl.base_count + t]);
    if (bl.spec->type == JointCurveType::OisSteps) {
        StepCurve s{as_of_, x[bl.first], {}, std::move(jumps)};
        for (std::size_t i = 0; i < bl.spec->step_dates.size(); ++i) s.steps.push_back({bl.spec->step_dates[i], x[bl.first + 1 + i]});
        b.steps[k] = std::move(s);
        b.curve[k].reset();
        return;
    }
    Curve c(as_of_, bl.spec->interpolation);
    c.set_jumps(jumps);
    c.set_shape(bl.spec->shape);
    for (std::size_t i = 0; i < bl.pillars.size(); ++i) c.push(bl.pillars[i], x[bl.first + i]);
    b.curve[k] = std::move(c);
    b.steps[k].reset();
}

double System::model(std::size_t j, const Built& b) const {
    const JointInstrument& in = inst_[j];
    const Prepared& p = prep_[j];
    const std::size_t k = p.curve;
    const Block& bl = blocks_[k];
    const std::function<double(Date)> d = [&](Date x) { return b.discount(k, x); };
    switch (in.type) {
        case JointInstrumentType::Ois:
            return ois_legs(*bl.spec->convention, p.ois, d).par();
        case JointInstrumentType::Future:
            return (d(in.start) / d(in.end) - 1.0) / p.alpha;
        case JointInstrumentType::Deposit:
        case JointInstrumentType::Fra:
        case JointInstrumentType::Swap: {
            const std::function<double(Date)> disc = [&](Date x) { return b.discount(bl.discount, x); };
            return projection_model(*bl.spec->convention, p.projection, disc, *b.curve[k]);
        }
        case JointInstrumentType::Xccy: {
            // The foreign leg of cross-currency.md per unit notional, discounted on the curve solved.
            double sum = 0.0;
            for (std::size_t i = 1; i < p.xccy.size(); ++i) {
                const double alpha = days(p.xccy[i - 1], p.xccy[i]) / 360.0;
                const double forward = b.discount(bl.foreign, p.xccy[i - 1]) / b.discount(bl.foreign, p.xccy[i]) - 1.0;
                sum += (forward + in.spread * alpha) * d(p.xccy[i]);
            }
            return sum + d(p.xccy.back()) - d(p.xccy.front());
        }
    }
    return 0.0;
}

std::vector<double> System::residuals(const std::vector<double>& x) const {
    Built b{std::vector<std::optional<Curve>>(blocks_.size()), std::vector<std::optional<StepCurve>>(blocks_.size())};
    for (std::size_t k = 0; k < blocks_.size(); ++k) build(k, x, b);
    std::vector<double> r(inst_.size());
    for (std::size_t j = 0; j < inst_.size(); ++j) r[j] = model(j, b) - prep_[j].target;
    return r;
}

void System::solve_block(std::size_t k, std::vector<double>& x, Built& b) const {
    const Block& bl = blocks_[k];
    const std::size_t m = bl.size;
    const auto eval = [&](const std::vector<double>& xx, std::vector<double>& r) {
        r.assign(m, std::numeric_limits<double>::quiet_NaN());
        double worst = 0.0;
        try {
            build(k, xx, b);
            for (std::size_t i = 0; i < m; ++i) {
                const std::size_t j = bl.instruments[i];
                r[i] = model(j, b) - prep_[j].target;
                if (!std::isfinite(r[i])) return HUGE_VAL;
                worst = std::max(worst, std::fabs(r[i]));
            }
        } catch (const Error&) {
            return HUGE_VAL;
        }
        return worst;
    };
    std::vector<double> r, rn;
    double norm = eval(x, r);
    if (!std::isfinite(norm)) no_convergence();
    for (int it = 0; it < 100 && norm > 0.0; ++it) {
        Matrix a(m, std::vector<double>(m));
        constexpr double h = 1e-7;
        std::vector<double> up, down;
        for (std::size_t u = 0; u < m; ++u) {
            std::vector<double> xx = x;
            xx[bl.first + u] += h;
            const double nu = eval(xx, up);
            xx[bl.first + u] -= 2.0 * h;
            const double nd = eval(xx, down);
            if (!std::isfinite(nu) || !std::isfinite(nd)) no_convergence();
            for (std::size_t i = 0; i < m; ++i) a[i][u] = (up[i] - down[i]) / (2.0 * h);
        }
        std::vector<double> minus_r(m);
        for (std::size_t i = 0; i < m; ++i) minus_r[i] = -r[i];
        const std::vector<double> dx = lu_solve(a, minus_r);
        bool accepted = false;
        double lambda = 1.0;
        for (int half = 0; half < 40; ++half, lambda *= 0.5) {
            std::vector<double> xn = x;
            for (std::size_t u = 0; u < m; ++u) xn[bl.first + u] += lambda * dx[u];
            const double nn = eval(xn, rn);
            if (nn < norm) {
                x = std::move(xn);
                r = rn;
                norm = nn;
                accepted = true;
                break;
            }
        }
        if (!accepted) break;
    }
    build(k, x, b);  // leave the curve at the accepted point
}

JointResult System::solve() {
    std::vector<double> x(n_, 0.0);
    Built b{std::vector<std::optional<Curve>>(blocks_.size()), std::vector<std::optional<StepCurve>>(blocks_.size())};
    for (std::size_t k = 0; k < blocks_.size(); ++k) {
        const Block& bl = blocks_[k];
        // Starting point: flat at the curve's first quote (steps at base_rate, turn factors 1); an XCCY
        // curve starts on its foreign projection curve, since its quotes are spreads.
        const double r0 = prep_[bl.instruments.front()].target;
        if (bl.spec->type == JointCurveType::OisSteps) {
            for (std::size_t u = 0; u < bl.base_count; ++u) x[bl.first + u] = r0;
        } else {
            for (std::size_t i = 0; i < bl.pillars.size(); ++i)
                x[bl.first + i] = bl.spec->type == JointCurveType::Xccy ? std::log(b.discount(bl.foreign, bl.pillars[i]))
                                                                         : -r0 * days(as_of_, bl.pillars[i]) / 365.0;
        }
        solve_block(k, x, b);
    }
    const std::vector<double> r0 = residuals(x);
    double worst = 0.0;
    for (const double e : r0) {
        if (!std::isfinite(e)) no_convergence();
        worst = std::max(worst, std::fabs(e));
    }
    if (worst > required) no_convergence();

    // dR/dx by central differences, Richardson-combined over h and h/2; rows are instruments, columns
    // unknowns. A residual never reads a later curve, so those entries are exact zeros.
    const std::size_t n = n_;
    Matrix a(n, std::vector<double>(n, 0.0));
    constexpr double h = 1e-5;
    const auto central = [&](std::size_t u, double step) {
        std::vector<double> xx = x;
        xx[u] = x[u] + step;
        const std::vector<double> up = residuals(xx);
        xx[u] = x[u] - step;
        const std::vector<double> down = residuals(xx);
        std::vector<double> d(n);
        for (std::size_t j = 0; j < n; ++j) d[j] = (up[j] - down[j]) / (2.0 * step);
        return d;
    };
    for (std::size_t u = 0; u < n; ++u) {
        const std::vector<double> d1 = central(u, h), d2 = central(u, h / 2.0);
        for (std::size_t j = 0; j < n; ++j) a[j][u] = d1[j] == d2[j] ? d2[j] : (4.0 * d2[j] - d1[j]) / 3.0;
    }
    // Ruling F-26: an instrument whose dates lie on one side of a turn date has exactly zero sensitivity.
    std::vector<std::size_t> turn_unknowns;
    for (const Block& bl : blocks_)
        for (std::size_t t = 0; t < bl.spec->turns.size(); ++t) {
            const std::size_t u = bl.first + bl.base_count + t;
            const Date td = bl.spec->turns[t];
            turn_unknowns.push_back(u);
            for (std::size_t j = 0; j < n; ++j)
                if (!(prep_[j].first <= td && td < prep_[j].last)) a[j][u] = 0.0;
        }

    // dR/dq at the solution.
    Built fin{std::vector<std::optional<Curve>>(blocks_.size()), std::vector<std::optional<StepCurve>>(blocks_.size())};
    for (std::size_t k = 0; k < blocks_.size(); ++k) build(k, x, fin);
    for (std::size_t j = 0; j < n; ++j) {
        if (inst_[j].type != JointInstrumentType::Xccy) continue;
        const Prepared& p = prep_[j];
        double s = 0.0;
        for (std::size_t i = 1; i < p.xccy.size(); ++i) s += days(p.xccy[i - 1], p.xccy[i]) / 360.0 * fin.discount(p.curve, p.xccy[i]);
        prep_[j].dq = s;
    }

    // J = -(dR/dx)^{-1} dR/dq, block by block (ruling F-25): a quote of a later curve gives exact zeros.
    Matrix jac(n, std::vector<double>(n, 0.0));
    for (std::size_t k = 0; k < blocks_.size(); ++k) {
        const Block& bl = blocks_[k];
        const std::size_t m = bl.size;
        Matrix akk(m, std::vector<double>(m));
        for (std::size_t i = 0; i < m; ++i)
            for (std::size_t u = 0; u < m; ++u) akk[i][u] = a[bl.instruments[i]][bl.first + u];
        for (std::size_t q = 0; q < n; ++q) {
            if (prep_[q].curve > k) continue;
            std::vector<double> rhs(m);
            for (std::size_t i = 0; i < m; ++i) {
                const std::size_t row = bl.instruments[i];
                double s = row == q ? prep_[q].dq : 0.0;
                for (std::size_t u = 0; u < bl.first; ++u) s += a[row][u] * jac[u][q];
                rhs[i] = -s;
            }
            const std::vector<double> col = lu_solve(akk, rhs);
            for (std::size_t u = 0; u < m; ++u) jac[bl.first + u][q] = col[u];
        }
    }

    JointResult out;
    for (std::size_t k = 0; k < blocks_.size(); ++k) {
        const Block& bl = blocks_[k];
        JointCurveResult c;
        c.name = bl.spec->name;
        if (bl.spec->type == JointCurveType::OisSteps) {
            c.steps = true;
            c.base_rate = x[bl.first];
            for (std::size_t i = 0; i < bl.spec->step_dates.size(); ++i) c.step_rates.push_back(x[bl.first + 1 + i]);
            out.unknowns.push_back(c.name + ":base");
            for (const Date d : bl.spec->step_dates) out.unknowns.push_back(c.name + ":step:" + format_date(d));
        } else {
            c.pillars = fin.curve[k]->pillars();
            for (const Date d : bl.pillars) out.unknowns.push_back(c.name + ":pillar:" + format_date(d));
        }
        for (std::size_t t = 0; t < bl.spec->turns.size(); ++t) {
            out.unknowns.push_back(c.name + ":turn:" + format_date(bl.spec->turns[t]));
            out.turn_factors.push_back({c.name, bl.spec->turns[t], std::exp(x[bl.first + bl.base_count + t])});
        }
        out.curves.push_back(std::move(c));
    }
    // The solve holds ln of the turn-free curve at a pillar; the reported unknown is ln D, which adds
    // ln factor for each turn strictly before the pillar date.
    Matrix reported = jac;
    for (const Block& bl : blocks_) {
        if (!pillar_curve(bl.spec->type)) continue;
        for (std::size_t i = 0; i < bl.pillars.size(); ++i)
            for (std::size_t t = 0; t < bl.spec->turns.size(); ++t)
                if (bl.spec->turns[t] < bl.pillars[i])
                    for (std::size_t q = 0; q < n; ++q) reported[bl.first + i][q] += jac[bl.first + bl.base_count + t][q];
    }
    out.jacobian = std::move(reported);
    for (const JointInstrument& in : inst_) out.quotes.push_back(in.id);
    for (const std::size_t u : turn_unknowns) {
        std::vector<double> row(n);
        for (std::size_t j = 0; j < n; ++j) row[j] = a[j][u];
        out.turn_sensitivity.push_back(std::move(row));
    }
    out.max_repricing_error = worst;
    return out;
}

}  // namespace

JointResult joint_solve(Date as_of, const std::vector<JointCurveSpec>& curves, const std::vector<JointInstrument>& instruments) {
    for (const JointCurveSpec& c : curves) {
        for (const Jump& j : c.jumps) require_finite(j.factor, "jumps");
        require_finite(c.shape.tension, "tension");
    }
    for (const JointInstrument& in : instruments) {
        require_finite(in.rate, "rate");
        require_finite(in.price, "price");
        require_finite(in.sigma, "sigma");
        require_finite(in.mean_reversion, "mean_reversion");
        require_finite(in.spread, "spread");
    }
    System s(as_of, curves, instruments);
    return s.solve();
}

FundingCurve funding_curve(const Curve& discount, const std::vector<FundingQuote>& quotes, const std::vector<Date>& dates) {
    for (const FundingQuote& q : quotes) require_finite(q.rate, "quotes");
    const Date as_of = discount.as_of();
    if (quotes.empty()) bad("no quotes", "quotes");
    Date previous = as_of;
    for (const FundingQuote& q : quotes) {
        if (q.end <= previous) bad("quote ends must increase and follow as_of", "quotes");
        previous = q.end;
    }
    std::vector<double> t, log_ratio;  // ln(D_ois / P_f) at each end
    for (const FundingQuote& q : quotes) {
        const double g = 1.0 + q.rate * days(as_of, q.end) / 360.0;
        if (!(g > 0.0)) throw Error("E_DOMAIN", "1 + rate tau is not positive", "quotes");
    }
    for (const FundingQuote& q : quotes) {
        const double g = 1.0 + q.rate * days(as_of, q.end) / 360.0;
        t.push_back(days(as_of, q.end) / 365.0);
        log_ratio.push_back(std::log(discount.discount(q.end) * g));
    }
    FundingCurve out;
    for (std::size_t i = 0; i < quotes.size(); ++i) {
        const double numerator = i == 0 ? log_ratio[0] : log_ratio[i] - log_ratio[i - 1];
        out.spreads.push_back(numerator / (i == 0 ? t[0] : t[i] - t[i - 1]));
    }
    const auto integral = [&](double x) {
        double sum = 0.0, from = 0.0;
        for (std::size_t i = 0; i < t.size(); ++i) {
            if (x <= t[i]) return sum + out.spreads[i] * (x - from);
            sum += out.spreads[i] * (t[i] - from);
            from = t[i];
        }
        return sum + out.spreads.back() * (x - from);
    };
    const auto df = [&](Date d) { return discount.discount(d) * std::exp(-integral(days(as_of, d) / 365.0)); };
    for (const FundingQuote& q : quotes) out.pillars.push_back({q.end, df(q.end)});
    for (const Date d : dates) out.discount_factors.push_back(df(d));
    return out;
}

}  // namespace quantforge
