#include <chrono>
#include <cstdio>
#include <limits>
#include <vector>
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

constexpr std::size_t line_limit = 16'777'216;  // BT5, bytes after the CR is removed

using Clock = std::chrono::steady_clock;

// With --timings, adds diagnostics.elapsed_ns and changes nothing else.
std::string finish(const quantforge::cli::CaseResult& r, bool timings, Clock::time_point start) {
    if (!timings) return r.json;
    const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count();
    const std::string value = std::to_string(ns < 0 ? 0 : ns);
    std::string s = r.json;
    // diagnostics is the last member of every result: ...,"diagnostics":{...}}
    const std::size_t close = s.size() - 2;
    s.insert(close, (s[close - 1] == '{' ? "" : ",") + std::string(R"("elapsed_ns":)") + value);
    return s;
}

std::string limit_json() {
    return R"({"schema_version":"1.0","case_id":"unknown","status":"error","error":{"code":"E_LIMIT","message":"the line is above 16777216 bytes"},"diagnostics":{}})";
}

int run_one(bool timings) {
    const std::string text{std::istreambuf_iterator<char>(std::cin), std::istreambuf_iterator<char>()};
    const auto start = Clock::now();
    const auto result = quantforge::cli::run_case(text);
    std::cout << finish(result, timings, start) << '\n' << std::flush;
    return result.ok ? exit_ok : exit_case_error;
}

int run_batch(bool timings) {
    // Room for the limit plus a CR, plus the terminator getline writes.
    std::vector<char> buf(line_limit + 2);
    const auto size = std::streamsize(buf.size());
    for (;;) {
        std::cin.getline(buf.data(), size);
        const std::streamsize got = std::cin.gcount();
        bool over = false;
        std::size_t len = 0;
        if (std::cin.bad()) break;
        if (std::cin.eof()) {
            if (got == 0) break;  // BT2: no partial line left
            len = std::size_t(got);
        } else if (std::cin.fail()) {  // buffer full, no LF yet
            std::cin.clear();
            const auto next = std::cin.peek();  // EOF here sets eofbit; the loop ends after this line
            if (next == '\n' || next == std::char_traits<char>::eof()) {
                if (next == '\n') std::cin.get();
                len = std::size_t(got);
            } else {
                over = true;
                std::cin.ignore(std::numeric_limits<std::streamsize>::max(), '\n');
                std::cin.clear(std::cin.rdstate() & ~std::ios::failbit);
            }
        } else {
            len = std::size_t(got - 1);  // the LF was counted
        }
        const auto start = Clock::now();
        std::string out;
        if (!over && len > 0 && buf[len - 1] == '\r') --len;
        if (over || len > line_limit) out = finish({limit_json(), false}, timings, start);
        else out = finish(quantforge::cli::run_case(std::string_view(buf.data(), len)), timings, start);
        std::cout << out << '\n' << std::flush;
        if (std::cin.eof()) break;
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
    const bool timings = argc == 3 && std::string_view(argv[2]) == "--timings";
    if (argc != 2 && !timings) {
        std::cerr << "usage: quantforge run|batch|--batch [--timings] | version|operations\n";
        return exit_usage;
    }
    const std::string_view command = argv[1];
    try {
        if (command == "run") return run_one(timings);
        if (command == "batch" || command == "--batch") return run_batch(timings);
        if (timings) {
            std::cerr << "--timings applies to run and batch only\n";
            return exit_usage;
        }
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
