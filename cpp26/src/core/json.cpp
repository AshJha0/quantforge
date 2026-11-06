#include "quantforge/core/json.hpp"

#include <charconv>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <unordered_set>

#include "quantforge/core/error.hpp"

namespace quantforge::json {
namespace {

// A backstop for direct callers: the CLI runs the depth scan first.
constexpr int max_depth = 1000;

[[noreturn]] void fail(const std::string& why) { throw Error("E_PARSE", why); }

void append_utf8(std::string& out, std::uint32_t c) {
    if (c < 0x80) {
        out += char(c);
    } else if (c < 0x800) {
        out += char(0xC0 | (c >> 6));
        out += char(0x80 | (c & 0x3F));
    } else if (c < 0x10000) {
        out += char(0xE0 | (c >> 12));
        out += char(0x80 | ((c >> 6) & 0x3F));
        out += char(0x80 | (c & 0x3F));
    } else {
        out += char(0xF0 | (c >> 18));
        out += char(0x80 | ((c >> 12) & 0x3F));
        out += char(0x80 | ((c >> 6) & 0x3F));
        out += char(0x80 | (c & 0x3F));
    }
}

class Parser {
public:
    Parser(std::string_view text, Parsed& result) : s_(text), r_(result) {}

    void run() {
        skip_space();
        value(r_.value, 0);
        skip_space();
        if (p_ != s_.size()) fail("text after the JSON value");
    }

private:
    bool more() const { return p_ < s_.size(); }
    char peek() const { return s_[p_]; }

    void skip_space() {
        while (more() && (peek() == ' ' || peek() == '\t' || peek() == '\n' || peek() == '\r')) ++p_;
    }

    void expect_literal(std::string_view word) {
        if (s_.substr(p_, word.size()) != word) fail("bad literal");
        p_ += word.size();
    }

    void value(Value& v, int depth) {
        if (depth > max_depth) fail("nesting too deep");
        if (!more()) fail("unexpected end of text");
        switch (peek()) {
            case '{': object(v, depth); break;
            case '[': array(v, depth); break;
            case '"':
                v.kind = Kind::String;
                string(v.text);
                break;
            case 't':
                expect_literal("true");
                v.kind = Kind::Bool;
                v.boolean = true;
                break;
            case 'f':
                expect_literal("false");
                v.kind = Kind::Bool;
                break;
            case 'n': expect_literal("null"); break;
            default: number(v);
        }
    }

    void object(Value& v, int depth) {
        v.kind = Kind::Object;
        ++p_;
        skip_space();
        if (more() && peek() == '}') {
            ++p_;
            return;
        }
        std::unordered_set<std::string> seen;
        for (;;) {
            skip_space();
            if (!more() || peek() != '"') fail("expected a key");
            std::string key;
            string(key);
            if (!seen.insert(key).second) r_.duplicate_key = true;
            skip_space();
            if (!more() || peek() != ':') fail("expected ':'");
            ++p_;
            skip_space();
            v.members.push_back(Member{std::move(key), Value{}});
            value(v.members.back().second, depth + 1);
            skip_space();
            if (!more()) fail("unterminated object");
            const char c = s_[p_++];
            if (c == '}') return;
            if (c != ',') fail("expected ',' or '}'");
        }
    }

    void array(Value& v, int depth) {
        v.kind = Kind::Array;
        ++p_;
        skip_space();
        if (more() && peek() == ']') {
            ++p_;
            return;
        }
        for (;;) {
            skip_space();
            v.items.emplace_back();
            value(v.items.back(), depth + 1);
            skip_space();
            if (!more()) fail("unterminated array");
            const char c = s_[p_++];
            if (c == ']') return;
            if (c != ',') fail("expected ',' or ']'");
        }
    }

    std::uint32_t hex4() {
        if (p_ + 4 > s_.size()) fail("short \\u escape");
        std::uint32_t c = 0;
        for (int i = 0; i < 4; ++i) {
            const char h = s_[p_++];
            c <<= 4;
            if (h >= '0' && h <= '9') c |= std::uint32_t(h - '0');
            else if (h >= 'a' && h <= 'f') c |= std::uint32_t(h - 'a' + 10);
            else if (h >= 'A' && h <= 'F') c |= std::uint32_t(h - 'A' + 10);
            else fail("bad \\u escape");
        }
        return c;
    }

    void escape(std::string& out) {
        if (!more()) fail("unterminated escape");
        const char e = s_[p_++];
        switch (e) {
            case '"': out += '"'; return;
            case '\\': out += '\\'; return;
            case '/': out += '/'; return;
            case 'b': out += '\b'; return;
            case 'f': out += '\f'; return;
            case 'n': out += '\n'; return;
            case 'r': out += '\r'; return;
            case 't': out += '\t'; return;
            case 'u': break;
            default: fail("bad escape");
        }
        const std::uint32_t c = hex4();
        if (c >= 0xD800 && c <= 0xDBFF && s_.substr(p_, 2) == "\\u") {
            const std::size_t back = p_;
            p_ += 2;
            const std::uint32_t lo = hex4();
            if (lo >= 0xDC00 && lo <= 0xDFFF) {
                append_utf8(out, 0x10000 + ((c - 0xD800) << 10) + (lo - 0xDC00));
                return;
            }
            p_ = back;
        }
        if (c >= 0xD800 && c <= 0xDFFF) r_.lone_surrogate = true;
        append_utf8(out, c);
    }

    // Copies one raw UTF-8 sequence, rejecting overlong forms, surrogates and bad bytes.
    void raw_utf8(std::string& out) {
        const auto b = static_cast<unsigned char>(s_[p_]);
        std::size_t extra = 0;
        std::uint32_t c = 0, least = 0;
        if (b < 0x80) {
            out += char(b);
            ++p_;
            return;
        }
        if (b >= 0xC2 && b <= 0xDF) { extra = 1; c = b & 0x1Fu; least = 0x80; }
        else if (b >= 0xE0 && b <= 0xEF) { extra = 2; c = b & 0x0Fu; least = 0x800; }
        else if (b >= 0xF0 && b <= 0xF4) { extra = 3; c = b & 0x07u; least = 0x10000; }
        else fail("invalid UTF-8");
        if (p_ + extra >= s_.size()) fail("invalid UTF-8");
        for (std::size_t i = 1; i <= extra; ++i) {
            const auto n = static_cast<unsigned char>(s_[p_ + i]);
            if ((n & 0xC0) != 0x80) fail("invalid UTF-8");
            c = (c << 6) | (n & 0x3Fu);
        }
        if (c < least || c > 0x10FFFF || (c >= 0xD800 && c <= 0xDFFF)) fail("invalid UTF-8");
        out.append(s_.substr(p_, extra + 1));
        p_ += extra + 1;
    }

    void string(std::string& out) {
        ++p_;
        for (;;) {
            if (!more()) fail("unterminated string");
            const auto c = static_cast<unsigned char>(peek());
            if (c == '"') {
                ++p_;
                return;
            }
            if (c < 0x20) fail("control character in string");
            if (c == '\\') {
                ++p_;
                escape(out);
            } else {
                raw_utf8(out);
            }
        }
    }

    bool digit() const { return more() && peek() >= '0' && peek() <= '9'; }

    void number(Value& v) {
        const std::size_t start = p_;
        bool integral = true;
        if (more() && peek() == '-') ++p_;
        if (!digit()) fail("bad number");
        if (peek() == '0') ++p_;
        else while (digit()) ++p_;
        if (more() && peek() == '.') {
            integral = false;
            ++p_;
            if (!digit()) fail("bad number");
            while (digit()) ++p_;
        }
        if (more() && (peek() == 'e' || peek() == 'E')) {
            integral = false;
            ++p_;
            if (more() && (peek() == '+' || peek() == '-')) ++p_;
            if (!digit()) fail("bad number");
            while (digit()) ++p_;
        }
        v.kind = Kind::Number;
        v.integral = integral;
        v.text = std::string(s_.substr(start, p_ - start));
        // strtod, not from_chars: it gives the nearest value on underflow, and this program
        // never leaves the C locale.
        v.number = std::strtod(v.text.c_str(), nullptr);
        if (std::isinf(v.number)) r_.number_overflow = true;
    }

    std::string_view s_;
    Parsed& r_;
    std::size_t p_ = 0;
};

}  // namespace

const Value* Value::find(std::string_view key) const {
    for (const auto& [k, v] : members)
        if (k == key) return &v;
    return nullptr;
}

Parsed parse(std::string_view text) {
    Parsed result;
    Parser(text, result).run();
    return result;
}

bool deeper_than(std::string_view text, int limit) {
    int depth = 0;
    bool in_string = false;
    for (std::size_t i = 0; i < text.size(); ++i) {
        const char c = text[i];
        if (in_string) {
            if (c == '\\') ++i;
            else if (c == '"') in_string = false;
        } else if (c == '"') {
            in_string = true;
        } else if (c == '[' || c == '{') {
            if (++depth > limit) return true;
        } else if (c == ']' || c == '}') {
            --depth;
        }
    }
    return false;
}

std::string format_real(double v) {
    char b[64];
    const auto r = std::to_chars(b, b + sizeof b, v);
    return std::string(b, r.ptr);
}

void append_string(std::string& out, std::string_view s) {
    out += '"';
    for (const char ch : s) {
        const auto c = static_cast<unsigned char>(ch);
        if (c == '"') out += "\\\"";
        else if (c == '\\') out += "\\\\";
        else if (c < 0x20) {
            char b[8];
            std::snprintf(b, sizeof b, "\\u%04x", unsigned(c));
            out += b;
        } else out += ch;
    }
    out += '"';
}

void Writer::separate() {
    if (need_comma_) out_ += ',';
    need_comma_ = true;
}
void Writer::begin_object() { separate(); out_ += '{'; need_comma_ = false; }
void Writer::end_object() { out_ += '}'; need_comma_ = true; }
void Writer::begin_array() { separate(); out_ += '['; need_comma_ = false; }
void Writer::end_array() { out_ += ']'; need_comma_ = true; }
void Writer::key(std::string_view k) {
    separate();
    append_string(out_, k);
    out_ += ':';
    need_comma_ = false;
}
void Writer::real(double v) {
    if (!std::isfinite(v)) throw Error("E_NON_FINITE", "a result is NaN or infinite");
    separate();
    out_ += format_real(v);
}
void Writer::integer(long long v) { separate(); out_ += std::to_string(v); }
void Writer::string(std::string_view s) { separate(); append_string(out_, s); }
void Writer::boolean(bool b) { separate(); out_ += b ? "true" : "false"; }
void Writer::null() { separate(); out_ += "null"; }
void Writer::value(const Value& v) {
    switch (v.kind) {
        case Kind::Null: null(); break;
        case Kind::Bool: boolean(v.boolean); break;
        case Kind::Number: real(v.number); break;
        case Kind::String: string(v.text); break;
        case Kind::Array:
            begin_array();
            for (const Value& item : v.items) value(item);
            end_array();
            break;
        case Kind::Object:
            begin_object();
            for (const Member& m : v.members) {
                key(m.first);
                value(m.second);
            }
            end_object();
            break;
    }
}

}  // namespace quantforge::json
