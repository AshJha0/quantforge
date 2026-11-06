#include "quantforge/conventions.hpp"
#include <stdexcept>

namespace quantforge {
namespace {
double year_fraction(std::chrono::sys_days start, std::chrono::sys_days end, double basis) {
    if (end < start) throw std::invalid_argument("end date must not precede start date");
    return static_cast<double>((end - start).count()) / basis;
}
}
double act_360(std::chrono::sys_days start, std::chrono::sys_days end) {
    return year_fraction(start, end, 360.0);
}
double act_365f(std::chrono::sys_days start, std::chrono::sys_days end) {
    return year_fraction(start, end, 365.0);
}
}
