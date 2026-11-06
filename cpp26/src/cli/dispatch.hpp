#pragma once
// The CLI contract as functions, so that tests can reach it without a process.
#include <string>
#include <string_view>
#include <vector>

namespace quantforge::cli {

struct CaseResult {
    std::string json;  // one line, no newline
    bool ok;
};

/// Runs one case document. Calculation failures come back as results; only bugs throw.
CaseResult run_case(std::string_view text);

std::vector<std::string> operations();
std::string operations_json();
std::string version_json();

}  // namespace quantforge::cli
