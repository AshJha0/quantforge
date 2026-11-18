package org.quantforge.cli;

import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.micro.LitMatching;
import org.quantforge.micro.OrderBook;

/**
 * Stage H wave 2: MBP book rebuild ({@code 09-microstructure/order-book.md}) and the simulated lit matching engine
 * ({@code 10-execution/lit-matching.md}). Page limits replace the general per-array limit (HR-17).
 */
final class OpsMicro {
    private OpsMicro() {}

    static void register(Map<String, Function<In, Out>> table) {
        table.put("micro.book.rebuild", OpsMicro::rebuild);
        table.put("exec.sim.lit.run", OpsMicro::litRun);
    }

    private static List<?> array(In in, String key) {
        if (in.anyValue(key) instanceof List<?> l) {
            return l;
        }
        throw new QfError("E_SCHEMA", key + ": expected an array", key);
    }

    private static Out rebuild(In in) {
        List<?> messages = array(in, "messages");
        long depth = in.integer("depth");
        long pdec = in.integer("price_decimals");
        long qdec = in.integer("qty_decimals");
        List<?> checkpoints = in.has("checkpoints") ? array(in, "checkpoints") : null;
        boolean emit = in.bool("emit_checksum_string", false);
        in.limit(messages.size() > OrderBook.MAX_MESSAGES, "messages");
        in.limit(checkpoints != null && checkpoints.size() > OrderBook.MAX_MESSAGES, "checkpoints");
        in.gate();
        return new Out(OrderBook.rebuild(messages, depth, pdec, qdec, checkpoints, emit), Map.of());
    }

    private static Out litRun(In in) {
        String tick = in.string("tick_size");
        String lot = in.string("lot_size");
        List<?> events = array(in, "events");
        Map<?, ?> fees = in.object("fee_schedule").raw();
        in.limit(events.size() > LitMatching.MAX_EVENTS, "events");
        in.gate();
        return new Out(LitMatching.run(tick, lot, events, fees), Map.of());
    }
}
