#include "quantforge/conventions.hpp"
#include <cassert>
#include <chrono>
#include <cmath>
#include <stdexcept>

using namespace std::chrono;
int main() {
    const auto start = sys_days{year{2025}/1/1};
    const auto end = sys_days{year{2025}/1/31};
    assert(std::abs(quantforge::act_360(start, end) - 30.0/360.0) < 1e-14);
    bool threw = false;
    try { (void)quantforge::act_360(end, start); }
    catch (const std::invalid_argument&) { threw = true; }
    assert(threw);
}
