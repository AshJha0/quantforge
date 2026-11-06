#pragma once
#include <map>
#include <optional>
#include <string>
#include <vector>

#include "quantforge/core/dates.hpp"

namespace quantforge {

struct Quote {
    std::string instrument_id;
    Instant event_time;
    std::optional<double> bid, ask;
    std::string quote_status;  // as sent: FIRM or INDICATIVE
};

struct QuoteCheckInputs {
    Instant as_of;
    std::vector<Quote> quotes;
    long long stale_after_seconds;
    std::optional<double> max_relative_spread;
    bool positive_only = false;
    double outlier_threshold = 5.0;
    long long outlier_min_history = 5;
    std::map<std::string, std::vector<double>> history;
};

struct QuoteCheckResult {
    std::string instrument_id;
    std::string quote_status;
    std::vector<std::string> quality_flags;
};

std::vector<QuoteCheckResult> check_quotes(const QuoteCheckInputs& in);

}  // namespace quantforge
