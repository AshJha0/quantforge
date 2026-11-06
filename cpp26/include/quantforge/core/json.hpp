#pragma once
// A strict JSON reader that keeps what the contract needs: the spelling of numbers, and the rule
// breaks that are not syntax errors. Those are recorded, so the caller can rank them.
#include <cstddef>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace quantforge::json {

enum class Kind { Null, Bool, Number, String, Array, Object };

struct Member;

struct Value {
    Kind kind = Kind::Null;
    bool boolean = false;
    double number = 0.0;
    bool integral = false;  // written with no fraction and no exponent
    std::string text;       // decoded string, or the literal spelling of a number
    std::vector<Value> items;
    std::vector<Member> members;

    const Value* find(std::string_view key) const;
};

struct Member {
    std::string first;
    Value second;
};

struct Parsed {
    Value value;
    bool duplicate_key = false;
    bool number_overflow = false;
    bool lone_surrogate = false;
    int depth = 0;          // deepest nesting; an object or array is one level
    bool too_deep = false;  // beyond the recursion cap: checked for syntax, but not kept
};

/// Throws Error E_PARSE on anything that is not JSON. Rule breaks are flagged in the result.
Parsed parse(std::string_view text);

/// Shortest text that reads back to the same binary64. The value must be finite.
std::string format_real(double v);
void append_string(std::string& out, std::string_view s);

/// Streaming writer. A non-finite real throws Error E_NON_FINITE.
class Writer {
public:
    void begin_object();
    void end_object();
    void begin_array();
    void end_array();
    void key(std::string_view k);
    void real(double v);
    void integer(long long v);
    void string(std::string_view s);
    void boolean(bool b);
    void null();
    void value(const Value& v);
    const std::string& str() const { return out_; }

private:
    void separate();
    std::string out_;
    bool need_comma_ = false;
};

}  // namespace quantforge::json
