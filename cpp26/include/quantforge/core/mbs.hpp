#pragma once
// MBS pass-throughs (04-pricing/mbs.md).
#include <vector>

namespace quantforge {

struct MbsPool {
    double balance, wac, net_coupon;
    long long wam, age;
    bool psa;
    double rate_or_speed;
};
struct MbsCashflows {
    std::vector<double> balance, interest, scheduled_principal, prepayment;
    double wal;
};
MbsCashflows mbs_cashflows(const MbsPool& pool);

struct MbsPrice {
    double price, modified_duration, wal;
};
MbsPrice mbs_price(const MbsPool& pool, double yield, long long delay_days);


}  // namespace quantforge
