package org.quantforge.cli;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.micro.DarkPool;
import org.quantforge.micro.LitMatching;
import org.quantforge.micro.MultiAsset;
import org.quantforge.micro.OrderBook;
import org.quantforge.micro.Sor;

/**
 * Stage H wave 2: MBP book rebuild ({@code 09-microstructure/order-book.md}) and the simulated lit matching engine
 * ({@code 10-execution/lit-matching.md}). Page limits replace the general per-array limit (HR-17).
 */
final class OpsMicro {
    private OpsMicro() {}

    static void register(Map<String, Function<In, Out>> table) {
        table.put("micro.book.rebuild", OpsMicro::rebuild);
        table.put("exec.sim.lit.run", OpsMicro::litRun);
        table.put("exec.sim.dark.run", OpsMicro::darkRun);
        table.put("exec.sim.dark.markouts", OpsMicro::darkMarkouts);
        table.put("exec.sor.allocate", OpsMicro::sorAllocate);
        multiAsset(table, "micro.eq.round_price", MultiAsset::eqRoundPrice);
        multiAsset(table, "micro.eq.fee_check", MultiAsset::eqFeeCheck);
        multiAsset(table, "micro.eq.round_lot", MultiAsset::eqRoundLot);
        multiAsset(table, "micro.eq.settle_date", MultiAsset::eqSettleDate);
        multiAsset(table, "exec.sim.auction.uncross", MultiAsset::auctionUncross);
        multiAsset(table, "micro.fx.pip_value", MultiAsset::fxPipValue);
        multiAsset(table, "micro.fx.spot_date", MultiAsset::fxSpotDate);
        multiAsset(table, "exec.sim.fx.stream", MultiAsset::fxStream);
        multiAsset(table, "exec.sim.fx.request", MultiAsset::fxRequest);
        multiAsset(table, "micro.rates.parse_32nds", MultiAsset::ratesParse32nds);
        multiAsset(table, "micro.rates.format_32nds", MultiAsset::ratesFormat32nds);
        multiAsset(table, "micro.rates.tick_value", MultiAsset::ratesTickValue);
        multiAsset(table, "micro.rates.bond_price", MultiAsset::ratesBondPrice);
        multiAsset(table, "micro.rates.bill_price", MultiAsset::ratesBillPrice);
        multiAsset(table, "micro.rates.bond_yield", MultiAsset::ratesBondYield);
        multiAsset(table, "exec.sim.fut.to_ticks", MultiAsset::futToTicks);
        multiAsset(table, "exec.sim.fut.to_text", MultiAsset::futToText);
        multiAsset(table, "exec.sim.fut.pnl", MultiAsset::futPnl);
        multiAsset(table, "exec.sim.fut.variation", MultiAsset::futVariation);
        multiAsset(table, "exec.sim.fut.run", MultiAsset::futRun);
    }

    /** Stage H multi-asset (H-22, H-23, H-24): the whole input object goes to {@link MultiAsset}. */
    private static void multiAsset(Map<String, Function<In, Out>> table, String name,
            Function<Map<?, ?>, Map<String, Object>> fn) {
        table.put(name, in -> {
            in.gate();
            return new Out(fn.apply(in.raw()), Map.of());
        });
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
        Map<?, ?> session = in.has("session") ? in.object("session").raw() : null;
        in.limit(events.size() > LitMatching.MAX_EVENTS, "events");
        in.gate();
        return new Out(LitMatching.run(tick, lot, events, fees, session), Map.of());
    }

    /** One run ({@code config}, {@code events}) or several ({@code scenarios}), {@code 10-execution/dark-pool.md}. */
    private static Out darkRun(In in) {
        if (in.has("scenarios")) {
            List<?> sc = array(in, "scenarios");
            in.gate();
            List<Object> runs = new ArrayList<>();
            for (int k = 0; k < sc.size(); k++) {
                if (!(sc.get(k) instanceof Map<?, ?> s)) {
                    throw new QfError("E_SCHEMA", "scenarios/" + k + ": not an object", "scenarios");
                }
                Map<?, ?> cfg = s.get("config") instanceof Map<?, ?> c ? c : Map.of();
                List<?> ev = s.get("events") instanceof List<?> l ? l : List.of();
                runs.add(DarkPool.run(cfg, ev));
            }
            Map<String, Object> out = new TreeMap<>();
            out.put("scenarios", runs);
            return new Out(out, Map.of());
        }
        Map<?, ?> cfg = in.object("config").raw();
        List<?> events = array(in, "events");
        in.limit(events.size() > DarkPool.MAX_EVENTS, "events");
        in.gate();
        return new Out(DarkPool.run(cfg, events), Map.of());
    }

    private static Out darkMarkouts(In in) {
        List<?> fills = array(in, "fills");
        in.gate();
        return new Out(DarkPool.markouts(fills), Map.of());
    }

    private static Out sorAllocate(In in) {
        in.gate();
        return new Out(Sor.allocate(in.raw()), Map.of());
    }
}
