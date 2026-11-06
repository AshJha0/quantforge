#pragma once
#include <chrono>

namespace quantforge {
double act_360(std::chrono::sys_days start, std::chrono::sys_days end);
double act_365f(std::chrono::sys_days start, std::chrono::sys_days end);
}
