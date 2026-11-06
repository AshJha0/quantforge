#pragma once
// Every failure the library reports. Codes are those of specifications/cli-contract.md.
#include <stdexcept>
#include <string>

namespace quantforge {

class Error : public std::runtime_error {
public:
    Error(std::string code, const std::string& message, std::string field = {})
        : std::runtime_error(message), code_(std::move(code)), field_(std::move(field)) {}
    const std::string& code() const noexcept { return code_; }
    const std::string& field() const noexcept { return field_; }

private:
    std::string code_;
    std::string field_;
};

}  // namespace quantforge
