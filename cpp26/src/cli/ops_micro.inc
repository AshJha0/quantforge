// CLI handlers, stage H wave 2: micro.book.rebuild (specifications/09-microstructure/order-book.md, HR-11 to
// HR-17) and exec.sim.lit.run (specifications/10-execution/lit-matching.md, HR-25 to HR-31). Both carry their own
// page limits (50,000,000 messages; 10,000,000 events) in place of the general array limit (cli-contract,
// "Stage H wave 2 operations"). Decimal strings in and out (HR-12); exact arithmetic in micro::.

const Value& array_of(const In& in, string_view k) {
    const Value& a = in.need(k);
    if (a.kind != Kind::Array) schema(k, "expected an array");
    return a;
}

void op_micro_book_rebuild(const In& in, Out& out) {
    const Value& messages = array_of(in, "messages");
    const long long depth = in.integer("depth");
    const long long pdec = in.integer("price_decimals"), qdec = in.integer("qty_decimals");
    const Value* checkpoints = in.find("checkpoints") ? &array_of(in, "checkpoints") : nullptr;
    const bool emit = in.boolean("emit_checksum_string", false);
    in.ready();
    micro::book_rebuild(messages, depth, pdec, qdec, checkpoints, emit, out.values);
}

void op_exec_sim_lit_run(const In& in, Out& out) {
    const string& tick = in.text("tick_size");
    const string& lot = in.text("lot_size");
    const Value& events = array_of(in, "events");
    const Value& fees = in.need("fee_schedule");
    if (fees.kind != Kind::Object) schema("fee_schedule", "expected an object");
    in.ready();
    micro::lit_run(tick, lot, events, fees, out.values);
}

constexpr Entry micro_w2_ops[] = {
    {"exec.sim.lit.run", op_exec_sim_lit_run},
    {"micro.book.rebuild", op_micro_book_rebuild},
};
