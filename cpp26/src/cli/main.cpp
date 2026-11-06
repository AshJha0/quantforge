#include <cstdio>
#include <exception>
#include <iostream>
#include <iterator>
#include <string>
#include <string_view>

#include "dispatch.hpp"

#if defined(_WIN32)
#include <fcntl.h>
#include <io.h>
#endif

namespace {

constexpr int exit_ok = 0, exit_case_error = 2, exit_usage = 64, exit_fault = 70;

int run_one() {
    const std::string text{std::istreambuf_iterator<char>(std::cin), std::istreambuf_iterator<char>()};
    const auto result = quantforge::cli::run_case(text);
    std::cout << result.json << '\n' << std::flush;
    return result.ok ? exit_ok : exit_case_error;
}

int run_batch() {
    std::string line;
    while (std::getline(std::cin, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        std::cout << quantforge::cli::run_case(line).json << '\n' << std::flush;
    }
    return exit_ok;
}

}  // namespace

int main(int argc, char** argv) {
#if defined(_WIN32)
    // UTF-8 bytes pass through unchanged, with no CRLF translation.
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
#endif
    if (argc != 2) {
        std::cerr << "usage: quantforge run|batch|version|operations\n";
        return exit_usage;
    }
    const std::string_view command = argv[1];
    try {
        if (command == "run") return run_one();
        if (command == "batch") return run_batch();
        if (command == "version") {
            std::cout << quantforge::cli::version_json() << '\n';
            return exit_ok;
        }
        if (command == "operations") {
            std::cout << quantforge::cli::operations_json() << '\n';
            return exit_ok;
        }
    } catch (const std::exception& e) {
        std::cerr << "internal fault: " << e.what() << '\n';
        return exit_fault;
    }
    std::cerr << "unknown command\n";
    return exit_usage;
}
