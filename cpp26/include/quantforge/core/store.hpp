#pragma once
// The as-of store of specifications/01-core/asof-store.md: pure functions of a log.
#include <optional>
#include <string>
#include <vector>

#include "quantforge/core/dates.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/snapshot.hpp"

namespace quantforge {

struct StoreRecord {
    long long sequence;
    std::string series_id;
    Instant event_time;
    Instant knowledge_time;
    json::Value value;
    bool deleted;
    json::Value raw;  // the record as given, for the chain
};

struct StoreRow {
    std::string series_id;
    Instant event_time, knowledge_time;
    long long sequence;
    json::Value value;
};

struct ReplayPoint {
    Instant as_of;
    std::size_t row_count;
    std::string snapshot_id;
};

struct Chain {
    std::string head;
    std::vector<std::string> hashes;
};

std::string format_instant(Instant i);

/// Sequence and knowledge-time order. Throws E_INPUT.
void check_log(const std::vector<StoreRecord>& log);
/// Throws E_DATE_RANGE outside years 1 to 9999, which Z form cannot show.
void check_store_instant(Instant i);
std::vector<StoreRow> store_view(const std::vector<StoreRecord>& log, Instant as_of);
SnapshotHash store_snapshot(const std::vector<StoreRecord>& log, Instant as_of);
Chain store_chain(const std::vector<StoreRecord>& log);
std::vector<ReplayPoint> store_replay(const std::vector<StoreRecord>& log, const std::vector<Instant>& checkpoints);

}  // namespace quantforge
