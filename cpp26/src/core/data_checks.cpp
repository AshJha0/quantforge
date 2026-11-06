#include "quantforge/core/data_checks.hpp"

#include <algorithm>
#include <cmath>

#include "quantforge/core/error.hpp"

namespace quantforge {
namespace {

double median(std::vector<double> v) {
    std::ranges::sort(v);
    const std::size_t n = v.size();
    return n % 2 == 1 ? v[n / 2] : (v[n / 2 - 1] + v[n / 2]) / 2.0;
}

bool outlier(double mid, const std::vector<double>& h, double threshold) {
    const double med = median(h);
    std::vector<double> dev;
    dev.reserve(h.size());
    for (const double v : h) dev.push_back(std::fabs(v - med));
    const double mad = median(dev);
    return mad != 0.0 && std::fabs(mid - med) / (1.4826 * mad) > threshold;
}

QuoteCheckResult check_one(const Quote& q, const QuoteCheckInputs& in) {
    QuoteCheckResult r{q.instrument_id, q.quote_status, {}};
    auto& flags = r.quality_flags;
    const auto non_positive = [&] {
        return in.positive_only && ((q.bid && *q.bid <= 0.0) || (q.ask && *q.ask <= 0.0));
    };
    if (!q.bid || !q.ask) {
        if (!q.bid) flags.push_back("MISSING_BID");
        if (!q.ask) flags.push_back("MISSING_ASK");
        if (non_positive()) flags.push_back("NON_POSITIVE");
        r.quote_status = "MISSING";
        return r;
    }
    const double bid = *q.bid, ask = *q.ask, mid = (bid + ask) / 2.0;
    const bool crossed = bid > ask, stale = in.as_of - q.event_time > in.stale_after_seconds;
    if (crossed) flags.push_back("CROSSED");
    if (bid == ask) flags.push_back("LOCKED");
    if (stale) flags.push_back("STALE");
    if (in.max_relative_spread && !crossed && mid != 0.0 && (ask - bid) / std::fabs(mid) > *in.max_relative_spread)
        flags.push_back("WIDE_SPREAD");
    if (non_positive()) flags.push_back("NON_POSITIVE");
    if (!crossed) {
        const auto h = in.history.find(q.instrument_id);
        if (h != in.history.end() && std::ssize(h->second) >= in.outlier_min_history &&
            outlier(mid, h->second, in.outlier_threshold))
            flags.push_back("OUTLIER");
    }
    if (crossed) r.quote_status = "CROSSED";
    else if (stale) r.quote_status = "STALE";
    return r;
}

}  // namespace

std::vector<QuoteCheckResult> check_quotes(const QuoteCheckInputs& in) {
    if (in.stale_after_seconds <= 0) throw Error("E_INPUT", "stale_after_seconds must be positive", "stale_after_seconds");
    if (in.max_relative_spread && *in.max_relative_spread <= 0.0)
        throw Error("E_INPUT", "max_relative_spread must be positive", "max_relative_spread");
    if (in.outlier_threshold <= 0.0) throw Error("E_INPUT", "outlier_threshold must be positive", "outlier_threshold");
    if (in.outlier_min_history < 3) throw Error("E_INPUT", "outlier_min_history must be at least 3", "outlier_min_history");
    for (const Quote& q : in.quotes)
        if (q.event_time > in.as_of) throw Error("E_INPUT", "event_time is after as_of", "quotes");
    std::vector<QuoteCheckResult> out;
    out.reserve(in.quotes.size());
    for (const Quote& q : in.quotes) out.push_back(check_one(q, in));
    return out;
}

}  // namespace quantforge
