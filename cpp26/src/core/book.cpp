#include "quantforge/core/book.hpp"

#include <algorithm>
#include <cmath>
#include <map>
#include <set>

#include "quantforge/core/error.hpp"
#include "quantforge/core/finite.hpp"

namespace quantforge {
namespace {

[[noreturn]] void bad_input(const std::string& message, std::string field = {}) {
    throw Error("E_INPUT", message, std::move(field));
}

struct Holding {
    double quantity = 0.0;
    double average_cost = 0.0;
};

class Book {
public:
    void open(const BookPosition& p) {
        if (held_.count(p.instrument)) bad_input("instrument appears twice in positions", "positions");
        if (p.quantity != 0.0) held_[p.instrument] = Holding{p.quantity, p.average_cost};
    }

    // Weighted average cost (ruling F-34).
    void trade(const std::string& instrument, double dq, double p) {
        if (closed_.count(instrument)) bad_input("trade into a closed instrument", "instrument");
        Holding& h = held_[instrument];
        const double q = h.quantity;
        if (q == 0.0 || (q > 0.0) == (dq > 0.0)) {
            const double qn = q + dq;
            h.average_cost = (q * h.average_cost + dq * p) / qn;
            h.quantity = qn;
            return;
        }
        const double c = std::min(std::fabs(dq), std::fabs(q));
        realized_[instrument] += (q > 0.0 ? 1.0 : -1.0) * c * (p - h.average_cost);
        const double qn = q + dq;
        if (qn == 0.0) {
            held_.erase(instrument);
            return;
        }
        if ((qn > 0.0) != (q > 0.0)) h.average_cost = p;
        h.quantity = qn;
    }

    // EXPIRY, DEFAULT and the first leg of ROLL: a trade of minus the position; the instrument is closed.
    double close(const std::string& instrument, double p) {
        const auto it = held_.find(instrument);
        if (it == held_.end()) bad_input("instrument is not held", "instrument");
        const double q = it->second.quantity;
        trade(instrument, -q, p);
        closed_.insert(instrument);
        return q;
    }

    BookResult result() const {
        BookResult r;
        for (const auto& [name, h] : held_) r.positions.push_back({name, h.quantity, h.average_cost});
        for (const auto& [name, pnl] : realized_) {
            r.realized.emplace_back(name, pnl);
            r.total_realized += pnl;
        }
        return r;
    }

private:
    std::map<std::string, Holding> held_;
    std::map<std::string, double> realized_;
    std::set<std::string> closed_;
};

}  // namespace

BookResult apply_lifecycle(const std::vector<BookPosition>& positions, const std::vector<BookEvent>& events) {
    for (const BookPosition& p : positions) {
        require_finite(p.quantity, "quantity");
        require_finite(p.average_cost, "average_cost");
    }
    for (const BookEvent& e : events) {
        require_finite(e.quantity, "quantity");
        require_finite(e.price, "price");
        require_finite(e.to_price, "to_price");
    }
    for (std::size_t i = 1; i < events.size(); ++i)
        if (events[i].date < events[i - 1].date) bad_input("events are not in date order", "events");
    for (const BookEvent& e : events)
        if (e.type == BookEventType::Trade && e.quantity == 0.0)
            throw Error("E_DOMAIN", "trade quantity is 0", "quantity");

    Book book;
    for (const BookPosition& p : positions) book.open(p);
    std::map<std::pair<std::string, Date>, double> fixings;
    for (const BookEvent& e : events) {
        switch (e.type) {
        case BookEventType::Trade: book.trade(e.instrument, e.quantity, e.price); break;
        case BookEventType::Fixing:
            if (!fixings.emplace(std::make_pair(e.instrument, e.date), e.price).second)
                bad_input("the same index is fixed twice on one date", "index");
            break;
        case BookEventType::Expiry:
        case BookEventType::Default: book.close(e.instrument, e.price); break;
        case BookEventType::Roll: {
            const double q = book.close(e.instrument, e.price);
            book.trade(e.to, q, e.to_price);
            break;
        }
        }
    }
    BookResult r = book.result();
    for (const auto& [key, value] : fixings) r.fixings.push_back({key.first, key.second, value});
    return r;
}

std::vector<Mark> resolve_marks(Date as_of, const std::vector<std::string>& instruments,
                                const std::vector<MarkSource>& sources, long long max_age_days,
                                const std::vector<std::pair<std::string, double>>& ipv, double ipv_threshold) {
    require_finite(ipv_threshold, "ipv_threshold");
    for (const MarkSource& s : sources)
        for (const MarkQuote& q : s.quotes) require_finite(q.price, "price");
    for (const auto& [name, price] : ipv) require_finite(price, "ipv");
    std::set<std::string> names;
    for (const MarkSource& s : sources)
        if (!names.insert(s.name).second) bad_input("source names repeat", "sources");
    if (max_age_days < 0) throw Error("E_DOMAIN", "max_age_days is negative", "max_age_days");
    for (const auto& [name, price] : ipv)
        if (!(price > 0.0)) throw Error("E_DOMAIN", "an IPV price is not positive", "ipv");

    std::vector<Mark> out;
    for (const std::string& instrument : instruments) {
        Mark m;
        m.instrument = instrument;
        // 1. The first source, in priority order, with a quote on as_of.
        for (std::size_t s = 0; s < sources.size() && !m.price; ++s)
            for (const MarkQuote& q : sources[s].quotes)
                if (q.instrument == instrument && q.date == as_of) {
                    m.price = q.price;
                    m.source = sources[s].name;
                    m.status = s == 0 ? MarkStatus::Primary : MarkStatus::Fallback;
                    m.age_days = 0;
                    break;
                }
        // 2. The most recent quote within max_age_days, from any source; the earlier source wins a tie.
        if (!m.price) {
            for (const MarkSource& s : sources)
                for (const MarkQuote& q : s.quotes) {
                    if (q.instrument != instrument || !(q.date < as_of)) continue;
                    const int age = days_between(q.date, as_of);
                    if (age > max_age_days) continue;
                    if (!m.age_days || age < *m.age_days) {
                        m.price = q.price;
                        m.source = s.name;
                        m.status = MarkStatus::Stale;
                        m.age_days = age;
                    }
                }
        }
        if (m.price)
            for (const auto& [name, price] : ipv)
                if (name == instrument) {
                    m.ipv_diff = (*m.price - price) / price;
                    m.ipv_breach = std::fabs(*m.ipv_diff) > ipv_threshold;
                    break;
                }
        out.push_back(std::move(m));
    }
    return out;
}

FactorAttribution factor_attribution(const std::vector<double>& y, const Matrix& f, std::size_t factor_names) {
    require_finite(y, "portfolio_returns");
    require_finite(f, "factor_returns");
    const std::size_t t = y.size();
    if (f.size() != t) bad_input("portfolio_returns and factor_returns differ in length", "factor_returns");
    const std::size_t k = factor_names;
    for (const auto& row : f)
        if (row.size() != k) bad_input("factor_names and factor_returns columns differ", "factor_names");
    if (k == 0) bad_input("no factors", "factor_names");
    if (t < k + 2) bad_input("fewer than K + 2 observations", "portfolio_returns");

    Matrix x(t, std::vector<double>(k + 1, 1.0));
    for (std::size_t i = 0; i < t; ++i)
        for (std::size_t j = 0; j < k; ++j) x[i][j + 1] = f[i][j];
    const std::vector<double> sv = singular_values(x);
    if (!(sv.back() >= 1e-12 * sv.front())) throw Error("E_DOMAIN", "the factors are collinear", "factor_returns");

    // Centred regression: the slopes and the slope block of (X'X)^-1 equal those of the centred problem.
    const double n = double(t);
    double ybar = 0.0;
    for (const double v : y) ybar += v;
    ybar /= n;
    std::vector<double> fbar(k, 0.0);
    for (const auto& row : f)
        for (std::size_t j = 0; j < k; ++j) fbar[j] += row[j];
    for (double& v : fbar) v /= n;
    Matrix s(k, std::vector<double>(k, 0.0));
    std::vector<double> sy(k, 0.0);
    double sst = 0.0;
    for (std::size_t i = 0; i < t; ++i) {
        const double yc = y[i] - ybar;
        sst += yc * yc;
        for (std::size_t a = 0; a < k; ++a) {
            const double ca = f[i][a] - fbar[a];
            sy[a] += ca * yc;
            for (std::size_t b = 0; b < k; ++b) s[a][b] += ca * (f[i][b] - fbar[b]);
        }
    }
    FactorAttribution r;
    r.betas = lu_solve(s, sy);
    r.mean_return = ybar;
    r.alpha = ybar;
    for (std::size_t j = 0; j < k; ++j) {
        r.contributions.push_back(r.betas[j] * fbar[j]);
        r.alpha -= r.contributions[j];
    }
    double ssr = 0.0;
    for (std::size_t i = 0; i < t; ++i) {
        double e = y[i] - ybar;
        for (std::size_t j = 0; j < k; ++j) e -= r.betas[j] * (f[i][j] - fbar[j]);
        ssr += e * e;
    }
    r.r_squared = 1.0 - ssr / sst;
    const double var = ssr / double(t - k - 1);
    r.residual_vol = std::sqrt(var);
    for (std::size_t j = 0; j < k; ++j) {
        std::vector<double> unit(k, 0.0);
        unit[j] = 1.0;
        r.beta_se.push_back(std::sqrt(var * lu_solve(s, unit)[j]));
    }
    return r;
}

}  // namespace quantforge
