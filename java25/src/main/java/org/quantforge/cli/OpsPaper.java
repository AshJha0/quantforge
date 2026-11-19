package org.quantforge.cli;

import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.paper.Paper;

/**
 * Stage H paper trading verbs ({@code 10-execution/paper-trading.md}, HR-42 to HR-55; cli-contract.md "Stage H paper
 * trading operations"). Simulated only: no verb reaches a network or a venue (HR-42).
 */
final class OpsPaper {
    private OpsPaper() {}

    static void register(Map<String, Function<In, Out>> table) {
        table.put("paper.book.apply_fill", OpsPaper::applyFill);
        table.put("paper.book.end_of_day", OpsPaper::endOfDay);
        table.put("paper.pretrade.check", OpsPaper::pretrade);
        table.put("paper.ledger.append", OpsPaper::append);
        table.put("paper.ledger.verify", OpsPaper::verify);
        table.put("paper.session.run", OpsPaper::session);
    }

    private static Object opt(In in, String key, Object dflt) {
        return in.has(key) ? in.raw().get(key) : dflt;
    }

    private static List<?> array(In in, String key) {
        if (in.anyValue(key) instanceof List<?> l) {
            return l;
        }
        throw new QfError("E_SCHEMA", key + ": expected an array", key);
    }

    private static Out applyFill(In in) {
        List<?> fills = array(in, "fills");
        Object cash = opt(in, "cash", null);
        Object position = opt(in, "position", "0");
        Object avgCost = opt(in, "avg_cost", "0");
        in.gate();
        return new Out(Paper.bookCase(fills, cash, position, avgCost), Map.of());
    }

    private static Out endOfDay(In in) {
        Object cashOpen = in.has("cash_open") ? in.raw().get("cash_open") : in.string("cash_open");
        List<?> fills = in.has("fills") ? array(in, "fills") : List.of();
        Object position = opt(in, "position_open", "0");
        Object avgCost = opt(in, "avg_cost_open", null);
        Object prevClose = opt(in, "prev_close", null);
        Object close = opt(in, "close", null);
        long days = in.integer("days", 1);
        Object cashRate = opt(in, "cash_rate", "0");
        Object debitRate = opt(in, "debit_rate", "0");
        Object borrowRate = opt(in, "borrow_rate", "0");
        in.gate();
        return new Out(Paper.dayCase(cashOpen, fills, position, avgCost, prevClose, close, days, cashRate, debitRate,
                borrowRate), Map.of());
    }

    private static Out pretrade(In in) {
        Map<?, ?> order = in.object("order").raw();
        Object ref = in.has("ref_price") ? in.raw().get("ref_price") : in.string("ref_price");
        Object position = opt(in, "position", "0");
        String cash = in.string("cash");
        long ordersToday = in.integer("orders_today", 0);
        Map<?, ?> limits = in.object("limits").raw();
        in.gate();
        return new Out(Paper.pretradeCase(order, ref, position, cash, ordersToday, limits), Map.of());
    }

    private static Out append(In in) {
        long seq = in.integer("seq");
        String ts = in.string("ts");
        String kind = in.string("kind");
        Map<?, ?> body = in.object("body").raw();
        String prev = in.has("prev") ? in.string("prev") : "";
        in.gate();
        return new Out(Paper.ledgerAppend(seq, ts, kind, body, prev.isEmpty() ? Paper.GENESIS : prev), Map.of());
    }

    private static Out verify(In in) {
        String text = in.string("text");
        in.gate();
        return new Out(Paper.verify(text), Map.of());
    }

    private static Out session(In in) {
        Object cash = in.has("cash") ? in.raw().get("cash") : in.string("cash");
        Map<?, ?> limits = in.object("limits").raw();
        Map<?, ?> lit = in.object("lit").raw();
        List<?> script = array(in, "script");
        Map<?, ?> dark = in.has("dark") ? in.object("dark").raw() : null;
        in.gate();
        return new Out(Paper.sessionCase(cash, limits, lit, script, dark), Map.of());
    }
}
