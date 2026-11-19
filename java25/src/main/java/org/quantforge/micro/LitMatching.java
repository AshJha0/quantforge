package org.quantforge.micro;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import org.quantforge.core.QfError;

/**
 * {@code exec.sim.lit.run}: a simulated lit matching engine with price-time priority
 * ({@code specifications/10-execution/lit-matching.md}, rulings HR-25 to HR-31). Simulated venue; not a real exchange.
 * Prices, quantities and fees are exact decimals (HR-12) and the engine is deterministic.
 *
 * <p>Priority within a price (HR-27): displayed quantity by {@code seq}, then non-displayed {@code PEG_MID} orders by
 * {@code seq}. An iceberg's hidden quantity is refreshed into a new displayed slice at the back of the queue (new
 * {@code seq}) once its shown part is filled. A peg never takes: it stays one tick away from the opposite best, other
 * pegs included, so two {@code PEG_MID} orders on an on-grid mid never lock (the Python lane's rule).
 */
public final class LitMatching {
    private LitMatching() {}

    public static final String LABEL = "simulated venue; not a real exchange";
    public static final long MAX_EVENTS = 10_000_000L;
    private static final Set<String> TYPES =
            Set.of("LIMIT", "MARKET", "IOC", "FOK", "ICEBERG", "POST_ONLY", "PEG_MID", "PEG_PRIMARY");

    /** No exponent, no trailing zeros, "0" for zero (HR-12). */
    public static String fmt(BigDecimal x) {
        return x.signum() == 0 ? "0" : x.stripTrailingZeros().toPlainString();
    }

    /** Every sum, difference and product is range-checked (HR-58). */
    private static BigDecimal c(BigDecimal x) {
        return OrderBook.range(x, "value", OrderBook.MAX_SCALE);
    }

    private static boolean isPeg(String t) {
        return t.equals("PEG_MID") || t.equals("PEG_PRIMARY");
    }

    private static final class Order {
        final String id;
        final String trader;
        final boolean buy;
        final String type;
        final BigDecimal cap;
        BigDecimal price;
        BigDecimal display = BigDecimal.ZERO;
        BigDecimal hidden = BigDecimal.ZERO;
        final BigDecimal slice;
        long seq;

        Order(String id, String trader, boolean buy, String type, BigDecimal cap, BigDecimal slice) {
            this.id = id;
            this.trader = trader;
            this.buy = buy;
            this.type = type;
            this.cap = cap;
            this.price = cap;
            this.slice = slice;
        }

        BigDecimal open() {
            return c(display.add(hidden));
        }

        boolean mid() {
            return type.equals("PEG_MID");
        }
    }

    private static final class Cons {
        BigDecimal submitted;
        BigDecimal filled = BigDecimal.ZERO;
        BigDecimal cancelled = BigDecimal.ZERO;
        BigDecimal rejected = BigDecimal.ZERO;

        Cons(BigDecimal submitted) {
            this.submitted = submitted;
        }
    }

    private static final class Engine {
        final BigDecimal tick;
        final BigDecimal lot;
        final BigDecimal takerFee;
        final BigDecimal makerRebate;
        final LinkedHashMap<String, Order> resting = new LinkedHashMap<>();
        final Set<String> seen = new HashSet<>();
        long seq;
        final List<Object> fills = new ArrayList<>();
        final List<Object> rejects = new ArrayList<>();
        final List<Object> cancelled = new ArrayList<>();
        final TreeMap<String, BigDecimal> fees = new TreeMap<>();
        final TreeMap<String, Cons> cons = new TreeMap<>();

        Engine(BigDecimal tick, BigDecimal lot, BigDecimal takerFee, BigDecimal makerRebate) {
            this.tick = tick;
            this.lot = lot;
            this.takerFee = takerFee;
            this.makerRebate = makerRebate;
        }

        long nextSeq() {
            return ++seq;
        }

        void onGrid(BigDecimal x, BigDecimal unit, String what) {
            if (x.remainder(unit).signum() != 0) {
                throw new QfError("E_DOMAIN", what + " " + x + " is not a multiple of " + unit, what);
            }
        }

        List<Order> side(boolean buy) {
            List<Order> out = new ArrayList<>();
            for (Order o : resting.values()) {
                if (o.buy == buy && o.price != null) {
                    out.add(o);
                }
            }
            return out;
        }

        BigDecimal best(boolean buy, boolean excludeMid, String exclude) {
            BigDecimal b = null;
            for (Order o : side(buy)) {
                if ((excludeMid && o.mid()) || o.id.equals(exclude)) {
                    continue;
                }
                if (b == null || (buy ? o.price.compareTo(b) > 0 : o.price.compareTo(b) < 0)) {
                    b = o.price;
                }
            }
            return b;
        }

        static boolean marketable(boolean buy, BigDecimal limit, BigDecimal price) {
            return limit == null || (buy ? price.compareTo(limit) <= 0 : price.compareTo(limit) >= 0);
        }

        BigDecimal available(boolean buy, BigDecimal limit) {
            BigDecimal s = BigDecimal.ZERO;
            for (Order o : side(!buy)) {
                if (marketable(buy, limit, o.price)) {
                    s = c(s.add(o.open()));
                }
            }
            return s;
        }

        Order head(boolean buySide, BigDecimal price) {
            Order shown = null;
            Order mid = null;
            for (Order o : side(buySide)) {
                if (o.price.compareTo(price) != 0) {
                    continue;
                }
                if (o.mid()) {
                    if (mid == null || o.seq < mid.seq) {
                        mid = o;
                    }
                } else if (shown == null || o.seq < shown.seq) {
                    shown = o;
                }
            }
            return shown != null ? shown : mid;
        }

        BigDecimal match(Order taker, BigDecimal limit, BigDecimal qty) {
            while (qty.signum() > 0) {
                BigDecimal p = best(!taker.buy, false, null);
                if (p == null || !marketable(taker.buy, limit, p)) {
                    break;
                }
                Order maker = head(!taker.buy, p);
                BigDecimal avail = maker.mid() ? maker.hidden : maker.display;
                BigDecimal q = qty.min(avail);
                trade(taker, maker, p, q);
                qty = c(qty.subtract(q));
                if (maker.mid()) {
                    maker.hidden = c(maker.hidden.subtract(q));
                } else {
                    maker.display = c(maker.display.subtract(q));
                    if (maker.display.signum() == 0 && maker.hidden.signum() > 0) {
                        maker.display = maker.slice.min(maker.hidden);
                        maker.hidden = c(maker.hidden.subtract(maker.display));
                        maker.seq = nextSeq();
                    }
                }
                if (maker.open().signum() == 0) {
                    resting.remove(maker.id);
                }
            }
            return qty;
        }

        void trade(Order taker, Order maker, BigDecimal price, BigDecimal q) {
            Map<String, Object> f = new LinkedHashMap<>();
            f.put("taker_id", taker.id);
            f.put("maker_id", maker.id);
            f.put("price", fmt(price));
            f.put("qty", fmt(q));
            f.put("seq", (long) fills.size() + 1);
            fills.add(f);
            BigDecimal notional = c(price.multiply(q));
            fees.merge(taker.trader, c(takerFee.multiply(notional)), (a, b) -> c(a.add(b)));
            fees.merge(maker.trader, c(makerRebate.multiply(notional)).negate(), (a, b) -> c(a.add(b)));
            cons.get(taker.id).filled = c(cons.get(taker.id).filled.add(q));
            cons.get(maker.id).filled = c(cons.get(maker.id).filled.add(q));
        }

        BigDecimal pegPrice(Order o) {
            BigDecimal p;
            if (o.mid()) {
                BigDecimal bb = best(true, true, null);
                BigDecimal ba = best(false, true, null);
                if (bb == null || ba == null) {
                    return null;
                }
                BigDecimal ticks = c(bb.add(ba)).divide(c(tick.multiply(BigDecimal.TWO)), 0,
                        o.buy ? RoundingMode.FLOOR : RoundingMode.CEILING);
                p = c(c(ticks).multiply(tick));
            } else {
                p = best(o.buy, true, o.id);
                if (p == null) {
                    return null;
                }
            }
            p = o.buy ? p.min(o.cap) : p.max(o.cap);
            // HR-28 rounded away from crossing: a peg stays a tick away from the opposite best, other pegs included.
            BigDecimal opp = best(!o.buy, false, o.id);
            if (opp != null && (o.buy ? p.compareTo(opp) >= 0 : p.compareTo(opp) <= 0)) {
                p = c(o.buy ? opp.subtract(tick) : opp.add(tick));
            }
            return p.signum() > 0 ? p : null;
        }

        void reprice() {
            List<Order> pegs = new ArrayList<>();
            for (Order o : resting.values()) {
                if (isPeg(o.type)) {
                    pegs.add(o);
                }
            }
            pegs.sort(Comparator.comparingLong(o -> o.seq));
            for (Order o : pegs) {
                if (!resting.containsKey(o.id)) {
                    continue;
                }
                BigDecimal p = pegPrice(o);
                boolean same = p == null ? o.price == null : o.price != null && p.compareTo(o.price) == 0;
                if (!same) {
                    o.price = p;
                    o.seq = nextSeq();
                }
            }
        }

        void add(Map<?, ?> e, int k) {
            String path = "events/" + k;
            if (!(e.get("id") instanceof String oid) || !(e.get("trader") instanceof String trader)) {
                throw new QfError("E_SCHEMA", path + ": id and trader must be strings", path);
            }
            Object sideRaw = e.get("side");
            if (!("BUY".equals(sideRaw) || "SELL".equals(sideRaw)) || !(e.get("type") instanceof String typ)
                    || !TYPES.contains(typ)) {
                throw new QfError("E_SCHEMA", path + ": bad side or type", path);
            }
            BigDecimal qty = OrderBook.dec(e.get("qty"), path + "/qty");
            BigDecimal limit = typ.equals("MARKET") ? null : OrderBook.dec(e.get("price"), path + "/price");
            if (typ.equals("MARKET") && e.get("price") != null) {
                throw new QfError("E_SCHEMA", path + ": MARKET takes no price", path);
            }
            if (qty.signum() <= 0) {
                throw new QfError("E_DOMAIN", path + ": quantity must be positive", path);
            }
            onGrid(qty, lot, "qty");
            if (limit != null) {
                if (limit.signum() <= 0) {
                    throw new QfError("E_DOMAIN", path + ": price must be positive", path);
                }
                onGrid(limit, tick, "price");
            }
            BigDecimal slice = qty;
            if (typ.equals("ICEBERG")) {
                slice = OrderBook.dec(e.get("display_qty"), path + "/display_qty");
                if (slice.signum() <= 0 || slice.compareTo(qty) > 0) {
                    throw new QfError("E_DOMAIN", path + ": display_qty must be in (0, qty]", path);
                }
                onGrid(slice, lot, "display_qty");
            }
            if (!seen.add(oid)) {
                throw new QfError("E_INPUT", path + ": duplicate id " + oid, path);
            }
            cons.put(oid, new Cons(qty));
            boolean buy = "BUY".equals(sideRaw);
            Order o = new Order(oid, trader, buy, typ, limit, slice);
            if (typ.equals("FOK") && available(buy, limit).compareTo(qty) < 0) {
                reject(oid, "FOK_UNFILLABLE", qty);
                return;
            }
            if (typ.equals("POST_ONLY")) {
                BigDecimal p = best(!buy, false, null);
                if (p != null && marketable(buy, limit, p)) {
                    reject(oid, "POST_ONLY_WOULD_CROSS", qty);
                    return;
                }
            }
            if (isPeg(typ)) {
                o.price = pegPrice(o);
                o.seq = nextSeq();
                if (o.mid()) {
                    o.hidden = qty;
                } else {
                    o.display = qty;
                }
                resting.put(oid, o);
                return;
            }
            BigDecimal rest = match(o, limit, qty);
            if (rest.signum() == 0) {
                return;
            }
            if (typ.equals("MARKET") || typ.equals("IOC")) {
                cancelled.add(idQty(oid, rest));
                cons.get(oid).cancelled = c(cons.get(oid).cancelled.add(rest));
                return;
            }
            o.display = slice.min(rest);
            o.hidden = c(rest.subtract(o.display));
            o.seq = nextSeq();
            resting.put(oid, o);
        }

        static Map<String, Object> idQty(String id, BigDecimal q) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", id);
            m.put("qty", fmt(q));
            return m;
        }

        void reject(String oid, String reason, BigDecimal qty) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", oid);
            m.put("reason", reason);
            rejects.add(m);
            cons.get(oid).rejected = c(cons.get(oid).rejected.add(qty));
        }

        void unknown(String oid) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", oid);
            m.put("reason", "UNKNOWN_ID");
            rejects.add(m);
        }

        void cancel(Map<?, ?> e, int k) {
            if (!(e.get("id") instanceof String oid)) {
                throw new QfError("E_SCHEMA", "events/" + k + ": id must be a string", "events/" + k);
            }
            Order o = resting.remove(oid);
            if (o == null) {
                unknown(oid);
                return;
            }
            cancelled.add(idQty(oid, o.open()));
            cons.get(oid).cancelled = c(cons.get(oid).cancelled.add(o.open()));
        }

        void modify(Map<?, ?> e, int k) {
            String path = "events/" + k;
            if (!(e.get("id") instanceof String oid)) {
                throw new QfError("E_SCHEMA", path + ": id must be a string", path);
            }
            BigDecimal qty = OrderBook.dec(e.get("qty"), path + "/qty");
            if (qty.signum() <= 0) {
                throw new QfError("E_DOMAIN", path + ": quantity must be positive", path);
            }
            onGrid(qty, lot, "qty");
            if (e.get("price") != null) {
                throw new QfError("E_SCHEMA", path + ": MODIFY takes id and qty only (wave 1b)", path);
            }
            Order o = resting.get(oid);
            if (o == null) {
                unknown(oid);
                return;
            }
            // qty is the new open displayed quantity; a PEG_MID's whole quantity is non-displayed.
            BigDecimal old = o.mid() ? o.hidden : o.display;
            int c = qty.compareTo(old);
            if (c == 0) {
                return;
            }
            if (o.mid()) {
                o.hidden = qty;
            } else {
                o.display = qty;
            }
            Cons cs = cons.get(oid);
            if (c < 0) {
                cs.cancelled = c(cs.cancelled.add(c(old.subtract(qty))));
            } else {
                cs.submitted = c(cs.submitted.add(c(qty.subtract(old))));
                o.seq = nextSeq();
            }
        }

        Map<String, Object> output() {
            Map<String, Object> book = new LinkedHashMap<>();
            Map<String, Object> mbp = new LinkedHashMap<>();
            for (boolean buy : new boolean[] {true, false}) {
                List<Order> priced = new ArrayList<>();
                List<Order> unpriced = new ArrayList<>();
                for (Order o : resting.values()) {
                    if (o.buy == buy) {
                        (o.price != null ? priced : unpriced).add(o);
                    }
                }
                Comparator<Order> byPrice = Comparator.comparing(o -> o.price);
                priced.sort((buy ? byPrice.reversed() : byPrice).thenComparingLong(o -> o.seq));
                unpriced.sort(Comparator.comparingLong(o -> o.seq));
                List<Object> entries = new ArrayList<>();
                for (List<Order> l : List.of(priced, unpriced)) {
                    for (Order o : l) {
                        Map<String, Object> m = new LinkedHashMap<>();
                        m.put("id", o.id);
                        m.put("price", o.price == null ? null : fmt(o.price));
                        m.put("display_qty", fmt(o.display));
                        m.put("hidden_qty", fmt(o.hidden));
                        m.put("seq", o.seq);
                        entries.add(m);
                    }
                }
                TreeMap<BigDecimal, BigDecimal> levels =
                        new TreeMap<>(buy ? Comparator.<BigDecimal>reverseOrder() : Comparator.<BigDecimal>naturalOrder());
                for (Order o : priced) {
                    levels.merge(o.price, o.display, (a, b) -> c(a.add(b)));
                }
                List<Object> lv = new ArrayList<>();
                levels.forEach((p, q) -> {
                    if (q.signum() > 0) {
                        lv.add(List.of(fmt(p), fmt(q)));
                    }
                });
                book.put(buy ? "bids" : "asks", entries);
                mbp.put(buy ? "bids" : "asks", lv);
            }
            Map<String, Object> feeOut = new LinkedHashMap<>();
            fees.forEach((t, v) -> feeOut.put(t, fmt(v)));
            Map<String, Object> consOut = new LinkedHashMap<>();
            cons.forEach((oid, c) -> {
                Order live = resting.get(oid);
                Map<String, Object> m = new LinkedHashMap<>();
                m.put("submitted", fmt(c.submitted));
                m.put("filled", fmt(c.filled));
                m.put("resting", fmt(live == null ? BigDecimal.ZERO : live.open()));
                m.put("cancelled", fmt(c.cancelled));
                m.put("rejected", fmt(c.rejected));
                consOut.put(oid, m);
            });
            Map<String, Object> out = new LinkedHashMap<>();
            out.put("fills", fills);
            out.put("rejects", rejects);
            out.put("cancelled", cancelled);
            out.put("book", book);
            out.put("mbp", mbp);
            out.put("fees", feeOut);
            out.put("conservation", consOut);
            out.put("label", LABEL);
            return out;
        }
    }


    static final List<String> PHASES = List.of("PRE_OPEN", "CONTINUOUS", "PRE_CLOSE", "CLOSED"); // HR-83

    /**
     * Equity session phases (asset-conventions.md 1.3, HR-83, HR-112; auction.md). In PRE_OPEN, NEW LIMIT and MARKET
     * orders collect in a call book without matching; at CONTINUOUS the call book is uncrossed by
     * {@code exec.sim.auction.uncross} (phase OPEN) and its unfilled limit orders rest in the continuous book in
     * allocation order. In PRE_CLOSE only {@code on_close} orders are accepted, into a second call book uncrossed at
     * CLOSED (phase CLOSE); unfilled on-close orders are cancelled (HR-96). The continuous book does not join the
     * closing cross. Orders in the wrong phase are rejected with reason PHASE. Auction fills pay
     * {@code auction_fee} x notional.
     */
    private static final class Session {
        private record Call(String id, String side, Object limit, long qty, BigDecimal qtyDec, boolean onClose) {}

        final Engine eng;
        final BigDecimal fee;
        String phase;
        final BigDecimal ref;
        final Object tie;
        List<Call> call = new ArrayList<>();
        final Map<String, String> trader = new HashMap<>();
        final List<Object> auctions = new ArrayList<>();

        Session(Engine eng, Object raw, BigDecimal fee) {
            if (!(raw instanceof Map<?, ?> m)) {
                throw new QfError("E_SCHEMA", "session: not an object", "session");
            }
            this.eng = eng;
            this.fee = fee;
            Object ph = m.containsKey("phase") ? m.get("phase") : "PRE_OPEN";
            if (!PHASES.contains(ph)) {
                throw new QfError("E_SCHEMA", "session/phase: not a phase", "session/phase");
            }
            phase = (String) ph;
            ref = OrderBook.dec(m.get("ref_price"), "session/ref_price");
            tie = m.containsKey("tie_break") ? m.get("tie_break") : "CBOE";
        }

        /** True when the session handled the event (the engine must not). */
        boolean event(Map<?, ?> e, int k) {
            Object op = e.get("op");
            if ("PHASE".equals(op)) {
                move(e.get("phase"), k);
                return true;
            }
            if (phase.equals("CONTINUOUS")) {
                return false;
            }
            if ("CANCEL".equals(op)) {
                for (int i = 0; i < call.size(); i++) {
                    Call c = call.get(i);
                    if (c.id.equals(e.get("id"))) {
                        call.remove(i);
                        eng.cancelled.add(Engine.idQty(c.id, c.qtyDec));
                        eng.cons.get(c.id).cancelled = c.qtyDec;
                        return true;
                    }
                }
                return false;
            }
            if (!"NEW".equals(op)) {
                return false;
            }
            String path = "events/" + k;
            if (!(e.get("id") instanceof String oid) || !(e.get("trader") instanceof String tr)) {
                throw new QfError("E_SCHEMA", path + ": id and trader must be strings", path);
            }
            Object side = e.get("side");
            if (!("BUY".equals(side) || "SELL".equals(side)) || !(e.get("type") instanceof String typ)
                    || !TYPES.contains(typ)) {
                throw new QfError("E_SCHEMA", path + ": bad side or type", path);
            }
            Object oc = e.containsKey("on_close") ? e.get("on_close") : Boolean.FALSE;
            if (!(oc instanceof Boolean onClose)) {
                throw new QfError("E_SCHEMA", path + "/on_close: not a boolean", path);
            }
            BigDecimal qty = OrderBook.dec(e.get("qty"), path + "/qty");
            boolean market = typ.equals("MARKET");
            BigDecimal limit = market ? null : OrderBook.dec(e.get("price"), path + "/price");
            if (eng.seen.contains(oid)) {
                throw new QfError("E_INPUT", path + ": duplicate id " + oid, path);
            }
            if (qty.signum() <= 0) {
                throw new QfError("E_DOMAIN", path + ": quantity must be positive", path);
            }
            eng.onGrid(qty, eng.lot, "qty");
            if (limit != null) {
                if (limit.signum() <= 0) {
                    throw new QfError("E_DOMAIN", path + ": price must be positive", path);
                }
                eng.onGrid(limit, eng.tick, "price");
            }
            eng.seen.add(oid);
            eng.cons.put(oid, new Cons(qty));
            boolean ok = (typ.equals("LIMIT") || market)
                    && (phase.equals("PRE_OPEN") || (phase.equals("PRE_CLOSE") && onClose));
            if (!ok) {
                eng.reject(oid, "PHASE", qty);
                return true;
            }
            trader.put(oid, tr);
            call.add(new Call(oid, (String) side, market ? "MARKET" : e.get("price"),
                    qty.divide(eng.lot).toBigIntegerExact().longValueExact(), qty, phase.equals("PRE_CLOSE")));
            return true;
        }

        void move(Object to, int k) {
            if (!PHASES.contains(to)) {
                throw new QfError("E_SCHEMA", "events/" + k + "/phase: not a phase", "events/" + k);
            }
            if (PHASES.indexOf(to) != PHASES.indexOf(phase) + 1) {
                throw new QfError("E_INPUT", "events/" + k + ": phase " + phase + " cannot move to " + to,
                        "events/" + k);
            }
            if (to.equals("CONTINUOUS")) {
                uncross("OPEN");
            } else if (to.equals("CLOSED")) {
                uncross("CLOSE");
            }
            phase = (String) to;
        }

        void uncross(String auctionPhase) {
            BigDecimal lot = eng.lot;
            List<Object> orders = new ArrayList<>();
            for (int n = 0; n < call.size(); n++) {
                Call c = call.get(n);
                Map<String, Object> o = new LinkedHashMap<>();
                o.put("id", c.id);
                o.put("side", c.side);
                o.put("limit", c.limit);
                o.put("qty", c.qty);
                o.put("seq", (long) n + 1);
                o.put("on_close", c.onClose);
                orders.add(o);
            }
            Map<String, Object> in = new LinkedHashMap<>();
            in.put("orders", orders);
            in.put("phase", auctionPhase);
            in.put("ref_price", fmt(ref));
            in.put("tick_size", fmt(eng.tick));
            in.put("tie_break", tie);
            Map<String, Object> res = MultiAsset.auctionUncross(in);
            List<Object> fills = new ArrayList<>();
            for (Object fo : (List<?>) res.get("fills")) {
                Map<?, ?> f = (Map<?, ?>) fo;
                String id = (String) f.get("id");
                BigDecimal q = c(BigDecimal.valueOf((Long) f.get("qty")).multiply(lot));
                BigDecimal px = new BigDecimal((String) f.get("price"));
                Map<String, Object> m = new LinkedHashMap<>();
                m.put("id", id);
                m.put("price", fmt(px));
                m.put("qty", fmt(q));
                m.put("side", f.get("side"));
                fills.add(m);
                eng.cons.get(id).filled = c(eng.cons.get(id).filled.add(q));
                String t = trader.get(id);
                eng.fees.put(t, c(eng.fees.getOrDefault(t, BigDecimal.ZERO).add(c(fee.multiply(c(px.multiply(q)))))));
            }
            for (Object ro : (List<?>) res.get("residual")) {
                Map<?, ?> r = (Map<?, ?>) ro;
                String id = (String) r.get("id");
                BigDecimal q = c(BigDecimal.valueOf((Long) r.get("qty")).multiply(lot));
                BigDecimal limit = new BigDecimal((String) r.get("limit"));
                Order o = new Order(id, trader.get(id), "B".equals(r.get("side")), "LIMIT", limit, q);
                o.display = q;
                o.hidden = BigDecimal.ZERO;
                o.seq = eng.nextSeq();
                eng.resting.put(id, o);
            }
            for (Object oid : (List<?>) res.get("cancelled")) {
                Call cl = call.stream().filter(x -> x.id.equals(oid)).findFirst().orElseThrow();
                BigDecimal left = c(cl.qtyDec.subtract(eng.cons.get(cl.id).filled));
                eng.cancelled.add(Engine.idQty(cl.id, left));
                eng.cons.get(cl.id).cancelled = left;
            }
            Map<String, Object> a = new LinkedHashMap<>();
            a.put("fills", fills);
            a.put("imbalance", fmt(c(BigDecimal.valueOf((Long) res.get("imbalance")).multiply(lot))));
            a.put("phase", auctionPhase);
            a.put("price", res.get("price") == null ? null : fmt(new BigDecimal((String) res.get("price"))));
            a.put("volume", fmt(c(BigDecimal.valueOf((Long) res.get("volume")).multiply(lot))));
            auctions.add(a);
            call = new ArrayList<>();
        }
    }

    /** Runs the event list. {@code feeSchedule} holds {@code taker_fee} and {@code maker_rebate} decimal strings. */
    public static Map<String, Object> run(String tickSize, String lotSize, List<?> events, Map<?, ?> feeSchedule) {
        return run(tickSize, lotSize, events, feeSchedule, null);
    }

    /**
     * Runs the event list with an optional equity {@code session} (HR-112): {@code phase}, {@code ref_price},
     * {@code tie_break}; PHASE events move it forward and {@code fee_schedule.auction_fee} prices auction fills.
     */
    public static Map<String, Object> run(String tickSize, String lotSize, List<?> events, Map<?, ?> feeSchedule,
            Object session) {
        BigDecimal tick = OrderBook.dec(tickSize, "tick_size");
        BigDecimal lot = OrderBook.dec(lotSize, "lot_size");
        if (tick.signum() <= 0 || lot.signum() <= 0) {
            throw new QfError("E_DOMAIN", "tick_size and lot_size must be positive", "tick_size");
        }
        BigDecimal taker = OrderBook.dec(feeSchedule.get("taker_fee"), "fee_schedule/taker_fee");
        BigDecimal rebate = OrderBook.dec(feeSchedule.get("maker_rebate"), "fee_schedule/maker_rebate");
        if (events.size() > MAX_EVENTS) {
            throw new QfError("E_LIMIT", "more than 10,000,000 events", "events");
        }
        Engine eng = new Engine(tick, lot, taker, rebate);
        Session ses = null;
        if (session != null) {
            Object af = feeSchedule.containsKey("auction_fee") ? feeSchedule.get("auction_fee") : "0";
            ses = new Session(eng, session, OrderBook.dec(af, "fee_schedule/auction_fee"));
        }
        for (int k = 0; k < events.size(); k++) {
            Object op = events.get(k) instanceof Map<?, ?> m ? m.get("op") : null;
            if (!("NEW".equals(op) || "CANCEL".equals(op) || "MODIFY".equals(op)
                    || (ses != null && "PHASE".equals(op)))) {
                throw new QfError("E_SCHEMA", "events/" + k + ": not an event", "events");
            }
            Map<?, ?> e = (Map<?, ?>) events.get(k);
            if (ses != null && ses.event(e, k)) {
                continue;
            }
            switch ((String) op) {
                case "NEW" -> eng.add(e, k);
                case "CANCEL" -> eng.cancel(e, k);
                default -> eng.modify(e, k);
            }
            eng.reprice();
        }
        Map<String, Object> out = eng.output();
        if (ses != null) {
            out.put("auctions", ses.auctions);
            Map<?, ?> cons = (Map<?, ?>) out.get("conservation");
            for (Session.Call c : ses.call) { // still in a call book at the end: counted as resting
                @SuppressWarnings("unchecked")
                Map<String, Object> m = (Map<String, Object>) cons.get(c.id());
                m.put("resting", fmt(c.qtyDec()));
            }
            out.put("phase", ses.phase);
        }
        return out;
    }
}
