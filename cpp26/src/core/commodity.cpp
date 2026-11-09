#include "quantforge/core/commodity.hpp"

#include <algorithm>
#include <cmath>
#include <string>

#include "quantforge/core/error.hpp"

namespace quantforge {

std::vector<double> commodity_forwards(const std::vector<CommodityQuote>& q, const std::optional<std::vector<double>>& seasonality,
                                       const std::vector<long long>& months) {
    if (q.empty()) throw Error("E_INPUT", "no quotes", "quotes");
    for (std::size_t j = 1; j < q.size(); ++j)
        if (q[j].month <= q[j - 1].month) throw Error("E_INPUT", "quote months must strictly increase", "quotes");
    for (const CommodityQuote& x : q)
        if (!(x.price > 0.0)) throw Error("E_DOMAIN", "a price is not positive", "quotes");
    if (seasonality && seasonality->size() != 12) throw Error("E_INPUT", "seasonality needs 12 terms", "seasonality");
    const auto sigma = [&](long long k) { return seasonality ? (*seasonality)[std::size_t(((k % 12) + 12) % 12)] : 0.0; };
    std::vector<double> out;
    for (const long long k : months) {
        if (k < q.front().month || k > q.back().month) throw Error("E_OUT_OF_RANGE", "the month is outside the quotes", "months");
        std::size_t j = 0;
        while (j + 1 < q.size() && q[j + 1].month < k) ++j;
        double l;
        if (k == q[j].month) l = std::log(q[j].price) - sigma(q[j].month);
        else {
            const double l0 = std::log(q[j].price) - sigma(q[j].month), l1 = std::log(q[j + 1].price) - sigma(q[j + 1].month);
            l = l0 + (l1 - l0) * double(k - q[j].month) / double(q[j + 1].month - q[j].month);
        }
        out.push_back(std::exp(l + sigma(k)));
    }
    return out;
}

StorageCarry storage_carry(const Curve& funding, const std::vector<DatedPrice>& f, double u) {
    if (f.size() < 2) throw Error("E_INPUT", "at least two forwards are needed", "forwards");
    Date previous = funding.as_of();
    for (const DatedPrice& x : f) {
        if (x.date <= previous) throw Error("E_INPUT", "forward dates must increase and follow as_of", "forwards");
        previous = x.date;
    }
    if (!(u >= 0.0)) throw Error("E_DOMAIN", "storage_cost is negative", "storage_cost");
    for (const DatedPrice& x : f)
        if (!(x.price > 0.0)) throw Error("E_DOMAIN", "a forward price is not positive", "forwards");
    StorageCarry out;
    for (std::size_t i = 1; i < f.size(); ++i) {
        const double dt = double(days_between(f[i - 1].date, f[i].date)) / 365.0;
        const double d0 = funding.discount(f[i - 1].date), d1 = funding.discount(f[i].date);
        const double r = std::log(d0 / d1) / dt;
        out.convenience_yields.push_back(r + u - std::log(f[i].price / f[i - 1].price) / dt);
        const double carry = d1 * f[i].price - d0 * f[i - 1].price * std::exp(u * dt);
        out.carry_values.push_back(carry);
        out.arbitrage.push_back(carry > 0.0);
    }
    return out;
}

}  // namespace quantforge
