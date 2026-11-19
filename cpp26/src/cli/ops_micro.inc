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
    const Value* session = in.find("session");
    if (session && session->kind != Kind::Object) schema("session", "expected an object");
    in.ready();
    micro::lit_run(tick, lot, events, fees, out.values, session);
}

// exec.sim.dark.run: one run (config, events) or several (scenarios), dark-pool.md. Page limit 10,000,000 events.
void op_exec_sim_dark_run(const In& in, Out& out) {
    if (in.find("scenarios")) {
        const Value& runs = array_of(in, "scenarios");
        for (std::size_t k = 0; k < runs.items.size(); ++k)
            if (runs.items[k].kind != Kind::Object) schema("scenarios", "scenarios/" + std::to_string(k) + ": not an object");
        in.ready();
        static const Value empty_object = [] {
            Value v;
            v.kind = Kind::Object;
            return v;
        }();
        static const Value empty_array = [] {
            Value v;
            v.kind = Kind::Array;
            return v;
        }();
        out.values.key("scenarios");
        out.values.begin_array();
        for (const Value& s : runs.items) {
            const Value* c = s.find("config");
            const Value* e = s.find("events");
            out.values.begin_object();
            micro::dark_run(c && c->kind != Kind::Null ? *c : empty_object, e && e->kind != Kind::Null ? *e : empty_array,
                            out.values);
            out.values.end_object();
        }
        out.values.end_array();
        return;
    }
    const Value& config = in.need("config");
    if (config.kind != Kind::Object) schema("config", "expected an object");
    const Value& events = array_of(in, "events");
    in.ready();
    micro::dark_run(config, events, out.values);
}

void op_exec_sim_dark_markouts(const In& in, Out& out) {
    const Value& fills = array_of(in, "fills");
    in.ready();
    micro::dark_markouts(fills, out.values);
}

// exec.sor.allocate: smart-order-router.md; lit_samples page limit 1,000,000 (checked in the library).
void op_exec_sor_allocate(const In& in, Out& out) {
    in.ready();
    micro::sor_allocate(in.raw(), out.values);
}

constexpr Entry micro_w2_ops[] = {
    {"exec.sim.dark.markouts", op_exec_sim_dark_markouts},
    {"exec.sim.dark.run", op_exec_sim_dark_run},
    {"exec.sim.lit.run", op_exec_sim_lit_run},
    {"exec.sor.allocate", op_exec_sor_allocate},
    {"micro.book.rebuild", op_micro_book_rebuild},
};
