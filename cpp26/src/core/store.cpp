#include "quantforge/core/store.hpp"

#include <map>
#include <utility>

#include "quantforge/core/error.hpp"

namespace quantforge {
namespace {

json::Value text_value(std::string s) {
    json::Value v;
    v.kind = json::Kind::String;
    v.text = std::move(s);
    return v;
}

json::Value row_document(const StoreRow& r) {
    json::Value sequence;
    sequence.kind = json::Kind::Number;
    sequence.number = double(r.sequence);
    json::Value row;
    row.kind = json::Kind::Object;
    row.members.push_back({"series_id", text_value(r.series_id)});
    row.members.push_back({"event_time", text_value(format_instant(r.event_time))});
    row.members.push_back({"knowledge_time", text_value(format_instant(r.knowledge_time))});
    row.members.push_back({"sequence", std::move(sequence)});
    row.members.push_back({"value", r.value});
    return row;
}

}  // namespace

std::string format_instant(Instant i) { return format_local(i) + "Z"; }

void check_log(const std::vector<StoreRecord>& log) {
    for (std::size_t i = 1; i < log.size(); ++i)
        if (log[i].sequence <= log[i - 1].sequence) throw Error("E_INPUT", "sequence must strictly increase", "records");
    for (std::size_t i = 1; i < log.size(); ++i)
        if (log[i].knowledge_time < log[i - 1].knowledge_time)
            throw Error("E_INPUT", "knowledge_time must not fall", "records");
}

void check_store_instant(Instant i) {
    const int y = year_of(date_of_seconds(i));
    if (y < 1 || y > 9999) throw Error("E_DATE_RANGE", "instants must lie in years 1 to 9999");
}

std::vector<StoreRow> store_view(const std::vector<StoreRecord>& log, Instant as_of) {
    // std::string orders by unsigned bytes, shorter first, as the spec asks. Sequence rises through
    // the log, so the last record seen for a key is the one with the highest sequence.
    std::map<std::pair<std::string, Instant>, const StoreRecord*> latest;
    for (const StoreRecord& r : log)
        if (r.knowledge_time <= as_of) latest[{r.series_id, r.event_time}] = &r;
    std::vector<StoreRow> rows;
    for (const auto& [key, r] : latest)
        if (!r->deleted) rows.push_back({r->series_id, r->event_time, r->knowledge_time, r->sequence, r->value});
    return rows;
}

SnapshotHash store_snapshot(const std::vector<StoreRecord>& log, Instant as_of) {
    json::Value rows;
    rows.kind = json::Kind::Array;
    for (const StoreRow& r : store_view(log, as_of)) rows.items.push_back(row_document(r));
    json::Value doc;
    doc.kind = json::Kind::Object;
    doc.members.push_back({"as_of", text_value(format_instant(as_of))});
    doc.members.push_back({"rows", std::move(rows)});
    return snapshot_of(doc);
}

Chain store_chain(const std::vector<StoreRecord>& log) {
    Chain c{std::string(64, '0'), {}};
    for (const StoreRecord& r : log) {
        c.head = sha256_hex(c.head + canonical_form(r.raw));
        c.hashes.push_back(c.head);
    }
    return c;
}

std::vector<ReplayPoint> store_replay(const std::vector<StoreRecord>& log, const std::vector<Instant>& checkpoints) {
    for (std::size_t i = 1; i < checkpoints.size(); ++i)
        if (checkpoints[i] < checkpoints[i - 1]) throw Error("E_INPUT", "checkpoints must ascend", "checkpoints");
    std::vector<ReplayPoint> out;
    for (const Instant t : checkpoints)
        out.push_back({t, store_view(log, t).size(), store_snapshot(log, t).snapshot_id});
    return out;
}

}  // namespace quantforge
