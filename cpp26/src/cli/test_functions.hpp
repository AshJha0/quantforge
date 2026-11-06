#pragma once
// The registry of specifications/01-core/test-functions.md. It lives in the CLI layer only.
#include <string_view>

#include "quantforge/core/root.hpp"

namespace quantforge::cli {

struct RootFunction {
    Fn f, df;
};

/// Both throw Error E_SCHEMA on an unknown name.
RootFunction root_function(std::string_view name);
Fn plain_function(std::string_view name);

}  // namespace quantforge::cli
