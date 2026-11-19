package org.quantforge.micro;

import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import org.quantforge.core.Json;
import org.quantforge.core.QfError;
import org.quantforge.core.Rng;

/**
 * {@code exec.sim.dark.run} and {@code exec.sim.dark.markouts}: a simulated midpoint dark pool
 * ({@code specifications/10-execution/dark-pool.md}, rulings HR-32 to HR-36). Simulated venue; not a real dark pool.
 * A port of the Python reference {@code python/quantforge_core/dark_pool.py}; decimals are exact (HR-12) with the
 * input range of HR-57/HR-58 shared with the lit engine.
 *
 * <p>Crossing (HR-32, HR-33): after every event, while a mid exists, buys are scanned by {@code seq} and for each buy
 * the sells by {@code seq}; the first pair within both limits whose fill {@code min(open_buy, open_sell)} meets both
 * {@code min_qty} fills at the mid. A pair with a {@code CONDITIONAL} side first sends an invitation (HR-34): the owner
 * firms up with probability {@code p_firm} (a {@code core.rng} draw only when 0 &lt; p_firm &lt; 1). With
 * {@code firm_delay} d &gt; 0 both orders are held until event {@code event + d}. A decline suspends the conditional
 * for events {@code event + 1} to {@code event + penalty_events}.
 *
 * <p>Also here: the Kaplan-Meier tail of censored per-venue fills ([GKNV09]) with its Greenwood standard error.
 */
public final class DarkPool {
    private DarkPool() {}

    public static final String LABEL = "simulated venue; not a real dark pool";
    public static final long MAX_EVENTS = 10_000_000L;
    private static final BigDecimal TWO = BigDecimal.valueOf(2);
    private static final MathContext SIXTY = new MathContext(60, RoundingMode.HALF_EVEN);

    private static final class Order {
        final String id;
        final boolean buy;
        BigDecimal open;
        final BigDecimal limit;
        final BigDecimal minQty;
        final boolean conditional;
        final long seq;
        long suspendedTo;
        long heldTo;

        Order(String id, boolean buy, BigDecimal open, BigDecimal limit, BigDecimal minQty, boolean conditional,
                long seq) {
            this.id = id;
            this.buy = buy;
            this.open = open;
            this.limit = limit;
            this.minQty = minQty;
            this.conditional = conditional;
            this.seq = seq;
        }
    }

    private record Pending(long due, Order b, Order s) {}

    /** A non-negative JSON integer (Python {@code _int}), else {@code E_DOMAIN}. */
    static long nonNegInt(Object v, String path) {
        if (v instanceof Json.Number n && n.isIntegerForm() && !n.text().startsWith("-")) {
            try {
                return Long.parseLong(n.text());
            } catch (NumberFormatException e) {
                throw new QfError("E_DOMAIN", path + ": not a non-negative integer", path);
            }
        }
        if (v instanceof Long l && l >= 0) {
            return l;
        }
        if (v instanceof Integer i && i >= 0) {
            return i;
        }
        throw new QfError("E_DOMAIN", path + ": not a non-negative integer", path);
    }

    private static Object get(Map<?, ?> m, String key, Object dflt) {
        return m.containsKey(key) ? m.get(key) : dflt;
    }

    private static final class Pool {
        final BigDecimal tick;
        final BigDecimal lot;
        final BigDecimal pFirm;
        final long delay;
        final long penalty;
        final Rng rng;
        BigDecimal mid;
        final LinkedHashMap<String, Order> orders = new LinkedHashMap<>();
        long seq;
        final List<Object> fills = new ArrayList<>();
        final List<Object> invitations = new ArrayList<>();
        final List<Object> suspensions = new ArrayList<>();
        List<Pending> pending = new ArrayList<>();

        Pool(Map<?, ?> cfg) {
            tick = OrderBook.dec(cfg.get("tick_size"), "config/tick_size");
            lot = OrderBook.dec(cfg.get("lot_size"), "config/lot_size");
            if (tick.signum() <= 0 || lot.signum() <= 0) {
                throw new QfError("E_DOMAIN", "tick_size and lot_size must be positive", "config/tick_size");
            }
            pFirm = OrderBook.dec(get(cfg, "p_firm", "0.8"), "config/p_firm");
            if (pFirm.signum() < 0 || pFirm.compareTo(BigDecimal.ONE) > 0) {
                throw new QfError("E_DOMAIN", "p_firm outside [0, 1]", "config/p_firm");
            }
            delay = nonNegInt(get(cfg, "firm_delay", 0L), "config/firm_delay");
            penalty = nonNegInt(get(cfg, "penalty_events", 0L), "config/penalty_events");
            rng = Rng.seeded(nonNegInt(get(cfg, "seed", 0L), "config/seed"), 0);
        }

        void onGrid(BigDecimal x, BigDecimal step, String path) {
            if (x.remainder(step).signum() != 0) {
                throw new QfError("E_DOMAIN", path + ": not on the grid " + LitMatching.fmt(step), path);
            }
        }

        void book(Map<?, ?> e, int k) {
            BigDecimal bid = e.get("bid") != null ? OrderBook.dec(e.get("bid"), "events/" + k + "/bid") : null;
            BigDecimal ask = e.get("ask") != null ? OrderBook.dec(e.get("ask"), "events/" + k + "/ask") : null;
            if (bid != null) {
                onGrid(bid, tick, "events/" + k + "/bid");
            }
            if (ask != null) {
                onGrid(ask, tick, "events/" + k + "/ask");
            }
            mid = bid == null || ask == null || bid.compareTo(ask) >= 0 ? null
                    : OrderBook.range(bid.add(ask).divide(TWO), "mid", OrderBook.MAX_SCALE);
        }

        void add(Map<?, ?> e, int k) {
            if (!(e.get("id") instanceof String oid)) {
                throw new QfError("E_SCHEMA", "events/" + k + "/id: not a string", "events");
            }
            if (orders.containsKey(oid)) {
                throw new QfError("E_INPUT", "events/" + k + ": duplicate id " + oid, "events");
            }
            Object side = e.get("side");
            Object kind = e.get("kind");
            if (!("BUY".equals(side) || "SELL".equals(side)) || !("FIRM".equals(kind) || "CONDITIONAL".equals(kind))) {
                throw new QfError("E_SCHEMA", "events/" + k + ": side or kind", "events");
            }
            BigDecimal qty = OrderBook.dec(e.get("qty"), "events/" + k + "/qty");
            BigDecimal mq = OrderBook.dec(get(e, "min_qty", LitMatching.fmt(lot)), "events/" + k + "/min_qty");
            if (qty.signum() <= 0 || mq.signum() <= 0 || mq.compareTo(qty) > 0) {
                throw new QfError("E_DOMAIN", "events/" + k + ": qty must be positive and min_qty <= qty", "events");
            }
            onGrid(qty, lot, "events/" + k + "/qty");
            BigDecimal lim = e.get("limit") != null ? OrderBook.dec(e.get("limit"), "events/" + k + "/limit") : null;
            seq++;
            orders.put(oid, new Order(oid, "BUY".equals(side), qty, lim, mq, "CONDITIONAL".equals(kind), seq));
        }

        void cancel(Map<?, ?> e, int k) {
            Object id = e.get("id");
            if (!(id instanceof String s) || !orders.containsKey(s)) {
                throw new QfError("E_INPUT", "events/" + k + ": unknown id", "events");
            }
            orders.get(s).open = BigDecimal.ZERO;
        }

        boolean eligible(Order o, long n) {
            if (o.open.signum() <= 0 || n <= o.suspendedTo || n < o.heldTo || mid == null) {
                return false;
            }
            if (o.limit == null) {
                return true;
            }
            return o.buy ? o.limit.compareTo(mid) >= 0 : o.limit.compareTo(mid) <= 0;
        }

        static boolean pairOk(Order b, Order s) {
            BigDecimal q = b.open.min(s.open);
            return q.compareTo(b.minQty) >= 0 && q.compareTo(s.minQty) >= 0;
        }

        boolean firm() {
            if (pFirm.compareTo(BigDecimal.ONE) == 0) {
                return true;
            }
            if (pFirm.signum() == 0) {
                return false;
            }
            // Python compares Decimal(repr(u)); Double.toString is the shortest repr since JDK 19.
            return new BigDecimal(Double.toString(rng.nextUniform())).compareTo(pFirm) < 0;
        }

        void fill(Order b, Order s) {
            BigDecimal q = b.open.min(s.open);
            b.open = b.open.subtract(q);
            s.open = s.open.subtract(q);
            Map<String, Object> f = new TreeMap<>();
            f.put("buy_id", b.id);
            f.put("sell_id", s.id);
            f.put("price", LitMatching.fmt(mid));
            f.put("qty", LitMatching.fmt(q));
            f.put("seq", (long) fills.size() + 1);
            fills.add(f);
        }

        boolean invite(Order b, Order s, long n) {
            boolean ok = true;
            Order[][] pairs = {{b, s}, {s, b}};
            for (Order[] p : pairs) {
                Order o = p[0];
                if (!o.conditional) {
                    continue;
                }
                boolean firmed = firm();
                Map<String, Object> inv = new TreeMap<>();
                inv.put("id", o.id);
                inv.put("contra_id", p[1].id);
                inv.put("event", n);
                inv.put("result", firmed ? "FIRMED" : "DECLINED");
                invitations.add(inv);
                if (!firmed) {
                    ok = false;
                    o.suspendedTo = n + penalty;
                    if (penalty > 0) {
                        Map<String, Object> sus = new TreeMap<>();
                        sus.put("id", o.id);
                        sus.put("from_event", n + 1);
                        sus.put("to_event", n + penalty);
                        suspensions.add(sus);
                    }
                }
            }
            return ok;
        }

        void settle(long n) {
            List<Pending> due = new ArrayList<>();
            List<Pending> keep = new ArrayList<>();
            for (Pending p : pending) {
                (p.due() == n ? due : keep).add(p);
            }
            pending = keep;
            for (Pending p : due) {
                p.b().heldTo = 0;
                p.s().heldTo = 0;
                if (invite(p.b(), p.s(), n) && eligible(p.b(), n) && eligible(p.s(), n) && pairOk(p.b(), p.s())) {
                    fill(p.b(), p.s());
                }
            }
        }

        void cross(long n) {
            while (mid != null) {
                List<Order> live = new ArrayList<>();
                for (Order o : orders.values()) {
                    if (eligible(o, n)) {
                        live.add(o);
                    }
                }
                live.sort(Comparator.comparingLong(o -> o.seq));
                Order pb = null;
                Order ps = null;
                search:
                for (Order b : live) {
                    if (!b.buy) {
                        continue;
                    }
                    for (Order s : live) {
                        if (!s.buy && pairOk(b, s)) {
                            pb = b;
                            ps = s;
                            break search;
                        }
                    }
                }
                if (pb == null) {
                    return;
                }
                if (!(pb.conditional || ps.conditional)) {
                    fill(pb, ps);
                } else if (delay > 0) {
                    pb.heldTo = n + delay;
                    ps.heldTo = n + delay;
                    pending.add(new Pending(n + delay, pb, ps));
                } else if (invite(pb, ps, n)) {
                    fill(pb, ps);
                }
            }
        }

        Map<String, Object> output() {
            List<Object> rest = new ArrayList<>();
            orders.values().stream().filter(o -> o.open.signum() > 0).sorted(Comparator.comparingLong(o -> o.seq))
                    .forEach(o -> {
                        Map<String, Object> r = new TreeMap<>();
                        r.put("id", o.id);
                        r.put("side", o.buy ? "BUY" : "SELL");
                        r.put("open_qty", LitMatching.fmt(o.open));
                        r.put("seq", o.seq);
                        rest.add(r);
                    });
            Map<String, Object> out = new TreeMap<>();
            out.put("fills", fills);
            out.put("invitations", invitations);
            out.put("suspensions", suspensions);
            out.put("resting", rest);
            out.put("label", LABEL);
            return out;
        }
    }

    /** One pool run over {@code events} (BOOK, NEW, CANCEL), numbered from 1. */
    /** HR-93: {@code asset_class} (default EQUITY); a dark venue of another class is E_INPUT (HR-113). */
    static String assetClass(Object v, String path, boolean dark) {
        Object x = v == null ? "EQUITY" : v;
        if (!("EQUITY".equals(x) || "FX".equals(x) || "RATES".equals(x))) {
            throw new QfError("E_SCHEMA", path + ": not EQUITY, FX or RATES", path);
        }
        if (dark && !"EQUITY".equals(x)) {
            throw new QfError("E_INPUT", path + ": dark pool is equities only (HR-93, HR-113)", path);
        }
        return (String) x;
    }

    public static Map<String, Object> run(Map<?, ?> config, List<?> events) {
        assetClass(config.get("asset_class"), "config/asset_class", true);
        if (events.size() > MAX_EVENTS) {
            throw new QfError("E_LIMIT", "more than 10,000,000 events", "events");
        }
        Pool pool = new Pool(config);
        for (int k = 0; k < events.size(); k++) {
            long n = k + 1L;
            Object op = events.get(k) instanceof Map<?, ?> m ? m.get("op") : null;
            if (!("BOOK".equals(op) || "NEW".equals(op) || "CANCEL".equals(op))) {
                throw new QfError("E_SCHEMA", "events/" + k + ": not an event", "events");
            }
            Map<?, ?> e = (Map<?, ?>) events.get(k);
            switch ((String) op) {
                case "BOOK" -> pool.book(e, k);
                case "NEW" -> pool.add(e, k);
                default -> pool.cancel(e, k);
            }
            pool.settle(n);
            pool.cross(n);
        }
        return pool.output();
    }

    /**
     * Markout in bp per horizon: side_sign x (mid - fill_price) / fill_price x 10000 (division in a 60-digit
     * context, as the Python reference), rounded half-even to 6 decimals; positive is good for the order's owner.
     */
    public static Map<String, Object> markouts(List<?> fills) {
        List<Object> out = new ArrayList<>();
        for (int k = 0; k < fills.size(); k++) {
            Object side = fills.get(k) instanceof Map<?, ?> m ? m.get("side") : null;
            if (!("BUY".equals(side) || "SELL".equals(side))) {
                throw new QfError("E_SCHEMA", "fills/" + k + ": side", "fills");
            }
            Map<?, ?> f = (Map<?, ?>) fills.get(k);
            BigDecimal px = OrderBook.dec(f.get("fill_price"), "fills/" + k + "/fill_price");
            if (px.signum() <= 0) {
                throw new QfError("E_DOMAIN", "fills/" + k + "/fill_price: not positive", "fills");
            }
            if (!(f.get("mid_at") instanceof Map<?, ?> mids)) {
                throw new QfError("E_SCHEMA", "fills/" + k + "/mid_at: not an object", "fills");
            }
            BigDecimal sign = "BUY".equals(side) ? BigDecimal.ONE : BigDecimal.ONE.negate();
            Map<String, Object> bp = new TreeMap<>();
            for (Map.Entry<?, ?> h : mids.entrySet()) {
                BigDecimal m = OrderBook.dec(h.getValue(), "fills/" + k + "/mid_at/" + h.getKey());
                BigDecimal v = sign.multiply(m.subtract(px)).divide(px, SIXTY).multiply(BigDecimal.valueOf(10000), SIXTY);
                bp.put((String) h.getKey(), LitMatching.fmt(v.setScale(6, RoundingMode.HALF_EVEN)));
            }
            Map<String, Object> one = new TreeMap<>();
            one.put("markouts_bp", bp);
            one.put("label", LABEL);
            out.add(one);
        }
        Map<String, Object> res = new TreeMap<>();
        res.put("fills", out);
        return res;
    }

    /**
     * Kaplan-Meier tail T(s) = P(liquidity &gt;= s), s = 1..sMax, from (v, r) observations ([GKNV09] section 2: r &lt; v
     * is a direct observation of s = r; r = v is censored, s &gt;= v). Returns {estimate, Greenwood SE} per s; plain KM.
     */
    public static double[][] kmTail(int[][] obs, int sMax) {
        double t = 1.0;
        double gw = 0.0;
        double[][] out = new double[sMax][];
        for (int s = 1; s <= sMax; s++) {
            int j = s - 1;
            int atRisk = 0;
            int d = 0;
            for (int[] o : obs) {
                int v = o[0];
                int r = o[1];
                if ((r < v && r >= j) || (r == v && v > j)) {
                    atRisk++;
                }
                if (r < v && r == j) {
                    d++;
                }
            }
            if (atRisk > 0 && d > 0) {
                t *= 1 - (double) d / atRisk;
                if (atRisk > d) {
                    gw += (double) d / ((double) atRisk * (atRisk - d));
                }
            }
            out[s - 1] = new double[] {t, t * Math.sqrt(gw)};
        }
        return out;
    }
}
