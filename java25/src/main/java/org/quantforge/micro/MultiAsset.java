package org.quantforge.micro;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.MathContext;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.function.DoubleUnaryOperator;
import java.util.function.Predicate;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.quantforge.core.Json;
import org.quantforge.core.QfError;
import org.quantforge.core.Rng;
import org.quantforge.core.RootFinders;

/**
 * Multi-asset microstructure: equities (H-22), FX spot (H-23) and rates (H-24). Port of the Python
 * {@code quantforge_core/multiasset.py}.
 *
 * <p>Specs: {@code specifications/09-microstructure/asset-conventions.md}, {@code 10-execution/auction.md},
 * {@code fx-rfq-venue.md} and {@code rates-futures-venue.md} (rulings HR-80 to HR-108 in
 * {@code specifications/stage-h-rulings-multiasset.md}). Every venue number is a parameter with a sourced default
 * (HR-80). Prices, quantities, fees and rates are decimal strings (HR-12), computed exactly (a 200-digit context
 * where a quotient may not terminate, as Python) and range-checked (HR-57, HR-58). Every output carries its label
 * (HR-94). Error order HR-66: E_SCHEMA, then structural E_INPUT, then E_DOMAIN, then E_LIMIT; each function parses
 * every field before it checks any domain. The futures venue reuses the lit engine unchanged ({@link LitMatching}).
 */
public final class MultiAsset {
    private MultiAsset() {}

    public static final String EQ_LABEL = "simulated venue; not a real exchange";
    public static final String IEX_LABEL = "IEX only; one venue";
    public static final String FX_LABEL = "simulated venue; not a real exchange; no real FX data";
    public static final String RATES_LABEL = "simulated venue; not a real exchange; no real rates data";

    /** [REGNMS-612] penny tier and the current narrow-spread half-penny tier: rows of [floor, tick]. */
    private static final String[][] DEFAULT_TICK_TABLE = {{"0", "0.0001"}, {"1.00", "0.01"}};
    private static final String[][] HALF_PENNY_TABLE = {{"0", "0.0001"}, {"1.00", "0.005"}};
    /** Dated rule versions: first business day of November 2025, release 34-101070 section VI (HR-110). */
    public static final String RULE_2024_COMPLIANCE = "2025-11-03";
    private static final BigDecimal FEE_CAP_CURRENT = new BigDecimal("0.001"); // [REGNMS-610] read 2026-11-18
    private static final BigDecimal FEE_CAP_OLD = new BigDecimal("0.003");
    private static final List<String> CCY_ORDER = List.of("EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY");
    private static final List<String> T1_PAIRS = List.of("USDCAD"); // HR-89 [BIS-FX]
    private static final Map<String, String[]> CONTRACTS = Map.of( // HR-91, [CME-ZN] and [CME-ZB]
            "ZN", new String[] {"100000", "0.015625"},
            "ZB", new String[] {"100000", "0.03125"});
    private static final Set<Integer> RESOLUTIONS = Set.of(32, 64, 128);
    /** HR-109: CME third digit in quarter-32nds: 0, 2, 5, 7 = 0, 1/4, 1/2, 3/4 and "+" = 1/2. */
    private static final Map<String, Integer> QUARTERS = Map.of("", 0, "0", 0, "2", 1, "5", 2, "+", 2, "7", 3);
    private static final String[] QUARTER_TEXT = {"", "2", "+", "7"};
    private static final Pattern N32 = Pattern.compile("([0-9]+)-([0-9]{2})(.?)");
    private static final Pattern DATE = Pattern.compile("\\d{4}-\\d{2}-\\d{2}");
    public static final int MAX_CANDIDATES = 1_000_000;
    public static final int MAX_ORDERS = 10_000_000;
    private static final int MAX_DAYS = 3660;
    /** Amended Reg NMS 242.600(b)(93): price cap and round lot, then 1 above. */
    private static final long[][] ROUND_LOTS_CURRENT = {{250, 100}, {1000, 40}, {10000, 10}};
    private static final MathContext MC = new MathContext(200, RoundingMode.HALF_EVEN);
    private static final BigDecimal HUNDRED = BigDecimal.valueOf(100);

    // ------------------------------------------------------------------ parsing helpers (E_SCHEMA)

    private static QfError err(String code, String msg, String path) {
        return new QfError(code, msg, path);
    }

    private static Map<?, ?> obj(Object raw, String path) {
        if (raw instanceof Map<?, ?> m) {
            return m;
        }
        throw err("E_SCHEMA", path + ": not an object", path);
    }

    private static Object need(Map<?, ?> raw, String key, String path) {
        if (!raw.containsKey(key)) {
            throw err("E_SCHEMA", path + key + ": missing", path + key);
        }
        return raw.get(key);
    }

    private static Object get(Map<?, ?> raw, String key, Object dflt) {
        return raw.containsKey(key) ? raw.get(key) : dflt;
    }

    private static BigDecimal dec(Map<?, ?> raw, String key, String path) {
        return OrderBook.dec(need(raw, key, path), path + key);
    }

    private static BigDecimal dec(Map<?, ?> raw, String key) {
        return dec(raw, key, "");
    }

    private static BigDecimal decOr(Map<?, ?> raw, String key, String dflt) {
        return OrderBook.dec(get(raw, key, dflt), key);
    }

    /** HR-116: integer inputs within +-(2^53 - 1); outside is E_LIMIT in all four languages. */
    static final BigInteger INT_MAX = BigInteger.ONE.shiftLeft(53).subtract(BigInteger.ONE);

    private static BigInteger inRange(BigInteger x, String path) {
        if (x.abs().compareTo(INT_MAX) > 0) {
            throw err("E_LIMIT", path + ": integer outside +-(2^53 - 1)", path);
        }
        return x;
    }

    private static long intOf(Object v, String path) {
        if (v instanceof Json.Number n && n.isIntegerForm()) {
            return inRange(new BigDecimal(n.text()).toBigIntegerExact(), path).longValue();
        }
        if (v instanceof Long x) {
            return inRange(BigInteger.valueOf(x), path).longValue();
        }
        if (v instanceof Integer x) {
            return x;
        }
        throw err("E_SCHEMA", path + ": not an integer", path);
    }

    private static BigInteger bigInt(Object v, String path) {
        if (v instanceof Json.Number n && n.isIntegerForm()) {
            return inRange(new BigInteger(n.text()), path);
        }
        if (v instanceof Long x) {
            return inRange(BigInteger.valueOf(x), path);
        }
        if (v instanceof Integer x) {
            return BigInteger.valueOf(x);
        }
        throw err("E_SCHEMA", path + ": not an integer", path);
    }

    private static long integer(Map<?, ?> raw, String key, String path) {
        return intOf(need(raw, key, path), path + key);
    }

    private static long integer(Map<?, ?> raw, String key) {
        return integer(raw, key, "");
    }

    private static boolean bool(Map<?, ?> raw, String key, boolean dflt) {
        if (get(raw, key, dflt) instanceof Boolean b) {
            return b;
        }
        throw err("E_SCHEMA", key + ": not a boolean", key);
    }

    private static String str(Map<?, ?> raw, String key, String path) {
        if (need(raw, key, path) instanceof String s) {
            return s;
        }
        throw err("E_SCHEMA", path + key + ": not a string", path + key);
    }

    private static String enumOf(Map<?, ?> raw, String key, String path, String... allowed) {
        String v = str(raw, key, path);
        if (!List.of(allowed).contains(v)) {
            throw err("E_SCHEMA", path + key + ": not a listed value", path + key);
        }
        return v;
    }

    private static LocalDate date(Object v, String path) {
        if (v instanceof String s && DATE.matcher(s).matches()) {
            try {
                return LocalDate.parse(s);
            } catch (DateTimeParseException e) {
                throw err("E_SCHEMA", path + ": not an ISO date", path);
            }
        }
        throw err("E_SCHEMA", path + ": not an ISO date", path);
    }

    private static Set<LocalDate> dates(Object v, String path) {
        if (!(v instanceof List<?> l)) {
            throw err("E_SCHEMA", path + ": not an array", path);
        }
        Set<LocalDate> out = new HashSet<>();
        for (int k = 0; k < l.size(); k++) {
            out.add(date(l.get(k), path + "/" + k));
        }
        return out;
    }

    private static List<?> list(Map<?, ?> raw, String key) {
        if (need(raw, key, "") instanceof List<?> l) {
            return l;
        }
        throw err("E_SCHEMA", key + ": not an array", key);
    }

    private static BigDecimal c(BigDecimal x) {
        return OrderBook.range(x, "value", OrderBook.MAX_SCALE);
    }

    private static int places(BigDecimal step) {
        return Math.max(0, step.stripTrailingZeros().scale());
    }

    /** {@code x} printed with exactly {@code places} decimals (HR-100 "printed at the tick decimals"). */
    private static String at(BigDecimal x, int places) {
        return x.setScale(places, RoundingMode.HALF_EVEN).toPlainString();
    }

    private static String fmt(BigDecimal x) {
        return LitMatching.fmt(x);
    }

    /** Exact floor (or ceiling) of a / b for b > 0, as an integer-valued decimal. */
    private static BigDecimal floorDiv(BigDecimal a, BigDecimal b, boolean ceil) {
        BigDecimal[] qr = a.divideAndRemainder(b);
        BigDecimal q = qr[0];
        int r = qr[1].signum();
        if (!ceil && r < 0) {
            q = q.subtract(BigDecimal.ONE);
        } else if (ceil && r > 0) {
            q = q.add(BigDecimal.ONE);
        }
        return q;
    }

    private static Object integerOut(BigInteger v) {
        return v.bitLength() < 63 ? (Object) v.longValue() : new Json.Number(v.doubleValue(), v.toString());
    }

    private static Map<String, Object> out(Object... kv) {
        Map<String, Object> m = new TreeMap<>();
        for (int i = 0; i < kv.length; i += 2) {
            m.put((String) kv[i], kv[i + 1]);
        }
        return m;
    }

    // ------------------------------------------------------------------ equities (H-22)

    /** True when the current (2024-amended) Rule 612/610 text applies at {@code as_of}. */
    private static boolean current(Map<?, ?> raw) {
        LocalDate cd = date(get(raw, "compliance_date", RULE_2024_COMPLIANCE), "compliance_date");
        return !raw.containsKey("as_of") || !date(raw.get("as_of"), "as_of").isBefore(cd);
    }

    private static List<BigDecimal[]> tickTable(Map<?, ?> raw) {
        Object tier = get(raw, "tick_tier", "PENNY");
        if (!"PENNY".equals(tier) && !"HALF_PENNY".equals(tier)) {
            throw err("E_SCHEMA", "tick_tier: not PENNY or HALF_PENNY", "tick_tier");
        }
        boolean cur = current(raw);
        boolean half = "HALF_PENNY".equals(tier);
        if (half && !cur) {
            throw err("E_INPUT", "tick_tier HALF_PENNY before the compliance date", "tick_tier");
        }
        if (half && raw.containsKey("tick_table")) {
            throw err("E_INPUT", "tick_tier HALF_PENNY with an explicit tick_table", "tick_tier");
        }
        Object v;
        if (raw.containsKey("tick_table")) {
            v = raw.get("tick_table");
        } else {
            List<Object> d = new ArrayList<>();
            for (String[] r : half ? HALF_PENNY_TABLE : DEFAULT_TICK_TABLE) {
                d.add(List.of(r[0], r[1]));
            }
            v = d;
        }
        if (!(v instanceof List<?> l)) {
            throw err("E_SCHEMA", "tick_table: not an array", "tick_table");
        }
        List<BigDecimal[]> rows = new ArrayList<>();
        for (int k = 0; k < l.size(); k++) {
            if (!(l.get(k) instanceof List<?> r) || r.size() != 2) {
                throw err("E_SCHEMA", "tick_table/" + k + ": not a [floor, tick] pair", "tick_table");
            }
            rows.add(new BigDecimal[] {OrderBook.dec(r.get(0), "tick_table/" + k + "/0"),
                OrderBook.dec(r.get(1), "tick_table/" + k + "/1")});
        }
        boolean bad = rows.isEmpty() || rows.get(0)[0].signum() != 0;
        for (int k = 1; k < rows.size() && !bad; k++) {
            bad = rows.get(k - 1)[0].compareTo(rows.get(k)[0]) >= 0;
        }
        if (bad) {
            throw err("E_INPUT", "tick_table: floors must start at 0 and increase", "tick_table");
        }
        for (BigDecimal[] r : rows) {
            if (r[1].signum() <= 0) {
                throw err("E_DOMAIN", "tick_table: ticks must be positive", "tick_table");
            }
        }
        return rows;
    }

    private static BigDecimal tickAt(List<BigDecimal[]> table, BigDecimal price) {
        BigDecimal t = null;
        for (BigDecimal[] r : table) {
            if (r[0].compareTo(price) <= 0) {
                t = r[1];
            }
        }
        return t;
    }

    private static String labelEq(Map<?, ?> raw) {
        Object src = get(raw, "data_source", "SIMULATED");
        if ("IEX".equals(src)) {
            return IEX_LABEL;
        }
        if ("SIMULATED".equals(src)) {
            return EQ_LABEL;
        }
        throw err("E_SCHEMA", "data_source: not SIMULATED or IEX", "data_source");
    }

    private static void positivePrice(BigDecimal price) {
        if (price.signum() <= 0) {
            throw err("E_DOMAIN", "price must be positive", "price");
        }
    }

    /** {@code micro.eq.round_price} (HR-81): a buy rounds down to the grid, a sell up. */
    public static Map<String, Object> eqRoundPrice(Map<?, ?> raw) {
        BigDecimal price = dec(raw, "price");
        boolean buy = enumOf(raw, "side", "", "BUY", "SELL").equals("BUY");
        List<BigDecimal[]> table = tickTable(raw);
        positivePrice(price);
        BigDecimal tick = tickAt(table, price);
        BigDecimal r = c(floorDiv(price, tick, !buy).multiply(tick));
        // A sell rounded up across a floor lands on the floor, which is on both grids (HR-81).
        return out("price", at(r, places(tickAt(table, r))));
    }

    /** {@code micro.eq.fee_check} (HR-85): the [REGNMS-610] access-fee cap for the price band. */
    public static Map<String, Object> eqFeeCheck(Map<?, ?> raw) {
        BigDecimal price = dec(raw, "price");
        BigDecimal fee = dec(raw, "taker_fee");
        boolean check = bool(raw, "cap_check", true);
        BigDecimal cap0 = current(raw) ? FEE_CAP_CURRENT : FEE_CAP_OLD;
        positivePrice(price);
        BigDecimal cap = price.compareTo(BigDecimal.ONE) >= 0 ? cap0 : c(cap0.multiply(price));
        if (check && fee.compareTo(cap) > 0) {
            throw err("E_DOMAIN", "taker_fee above the Rule 610 cap", "taker_fee");
        }
        return out("cap", fmt(cap), "taker_fee", fmt(fee));
    }

    private static boolean good(LocalDate d, Set<LocalDate> holidays) {
        return d.getDayOfWeek().getValue() <= 5 && !holidays.contains(d);
    }

    private static LocalDate addGood(LocalDate d, long n, Predicate<LocalDate> ok) {
        for (long i = 0; i < n; i++) {
            d = d.plusDays(1);
            int k = 0;
            while (!ok.test(d)) {
                if (++k >= MAX_DAYS) {
                    throw err("E_DOMAIN", "no business day within ten years", "holidays");
                }
                d = d.plusDays(1);
            }
        }
        return d;
    }

    /** {@code micro.eq.round_lot} (HR-82 as dated rule versions). */
    public static Map<String, Object> eqRoundLot(Map<?, ?> raw) {
        BigDecimal price = dec(raw, "price");
        boolean cur = current(raw);
        positivePrice(price);
        long lot = 100;
        if (cur) {
            lot = 1;
            for (long[] r : ROUND_LOTS_CURRENT) {
                if (price.compareTo(BigDecimal.valueOf(r[0])) <= 0) {
                    lot = r[1];
                    break;
                }
            }
        }
        return out("round_lot", lot);
    }

    /** Equities settlement date (HR-86): {@code settle_lag} business days on the supplied calendar. */
    public static Map<String, Object> eqSettleDate(Map<?, ?> raw) {
        LocalDate trade = date(need(raw, "trade_date", ""), "trade_date");
        long lag = intOf(get(raw, "settle_lag", 1L), "settle_lag");
        Set<LocalDate> hol = dates(get(raw, "holidays", List.of()), "holidays");
        if (lag < 0 || lag > 30) {
            throw err("E_DOMAIN", "settle_lag outside 0..30", "settle_lag");
        }
        return out("settle_date", addGood(trade, lag, d -> good(d, hol)).toString());
    }

    // ------------------------------------------------------------------ equity auction (HR-84, HR-96, HR-101)

    private record AOrder(String id, boolean buy, BigDecimal limit, long qty, long seq, boolean onClose) {}

    private record Cand(BigDecimal px, long vol, long imb) {}

    private static Cand nearestRef(List<Cand> keep, BigDecimal ref) {
        BigDecimal dmin = null;
        for (Cand c : keep) {
            BigDecimal d = c.px.subtract(ref).abs();
            dmin = dmin == null || d.compareTo(dmin) < 0 ? d : dmin;
        }
        Cand best = null;
        for (Cand c : keep) {
            if (c.px.subtract(ref).abs().compareTo(dmin) == 0 && (best == null || c.px.compareTo(best.px) > 0)) {
                best = c;
            }
        }
        return best;
    }

    /** {@code exec.sim.auction.uncross}: one price that trades the most shares (auction.md). */
    public static Map<String, Object> auctionUncross(Map<?, ?> raw) {
        String label = labelEq(raw);
        BigDecimal tick = dec(raw, "tick_size");
        BigDecimal ref = dec(raw, "ref_price");
        enumOf(raw, "phase", "", "OPEN", "CLOSE");
        Object tie = get(raw, "tie_break", "CBOE");
        if (!"CBOE".equals(tie) && !"IEX".equals(tie)) {
            throw err("E_SCHEMA", "tie_break: not CBOE or IEX", "tie_break");
        }
        List<?> orders = list(raw, "orders");
        if (orders.size() > MAX_ORDERS) {
            throw err("E_LIMIT", "more than 10,000,000 orders", "orders");
        }
        List<AOrder> parsed = new ArrayList<>();
        int nb = 0;
        int ns = 0;
        for (int k = 0; k < orders.size(); k++) {
            String p = "orders/" + k + "/";
            Map<?, ?> o = obj(orders.get(k), "orders/" + k);
            boolean buy = enumOf(o, "side", p, "BUY", "SELL").equals("BUY");
            Object lim = need(o, "limit", p);
            BigDecimal limit = "MARKET".equals(lim) ? null : OrderBook.dec(lim, p + "limit");
            long qty = integer(o, "qty", p);
            if (!(get(o, "on_close", false) instanceof Boolean onClose)) {
                throw err("E_SCHEMA", p + "on_close: not a boolean", p + "on_close");
            }
            if (buy) {
                nb++;
            } else {
                ns++;
            }
            if (!(get(o, "id", buy ? "b" + nb : "a" + ns) instanceof String oid)) {
                throw err("E_SCHEMA", p + "id: not a string", p + "id");
            }
            long seq = intOf(get(o, "seq", (long) (k + 1)), p + "seq");
            parsed.add(new AOrder(oid, buy, limit, qty, seq, onClose));
        }
        Set<String> ids = new HashSet<>();
        for (AOrder o : parsed) {
            if (!ids.add(o.id)) {
                throw err("E_INPUT", "duplicate order id", "orders");
            }
        }
        if (tick.signum() <= 0) {
            throw err("E_DOMAIN", "tick_size must be positive", "tick_size");
        }
        if (ref.signum() <= 0) {
            throw err("E_DOMAIN", "ref_price must be positive", "ref_price");
        }
        for (int k = 0; k < parsed.size(); k++) {
            AOrder o = parsed.get(k);
            if (o.qty <= 0) {
                throw err("E_DOMAIN", "orders/" + k + ": qty must be positive", "orders");
            }
            if (o.limit != null && (o.limit.signum() <= 0 || o.limit.remainder(tick).signum() != 0)) {
                throw err("E_DOMAIN", "orders/" + k + ": limit not a positive tick multiple", "orders");
            }
        }
        int places = places(tick);
        List<AOrder> buys = new ArrayList<>();
        List<AOrder> sells = new ArrayList<>();
        List<BigDecimal> limits = new ArrayList<>();
        for (AOrder o : parsed) {
            (o.buy ? buys : sells).add(o);
            if (o.limit != null) {
                limits.add(o.limit);
            }
        }
        buys.sort((a, b) -> {
            int ka = a.limit == null ? 0 : 1;
            int kb = b.limit == null ? 0 : 1;
            if (ka != kb) {
                return Integer.compare(ka, kb);
            }
            int x = ka == 0 ? 0 : b.limit.compareTo(a.limit);
            return x != 0 ? x : Long.compare(a.seq, b.seq);
        });
        sells.sort((a, b) -> {
            int ka = a.limit == null ? 0 : 1;
            int kb = b.limit == null ? 0 : 1;
            if (ka != kb) {
                return Integer.compare(ka, kb);
            }
            int x = ka == 0 ? 0 : a.limit.compareTo(b.limit);
            return x != 0 ? x : Long.compare(a.seq, b.seq);
        });
        Cand best = null;
        if (!buys.isEmpty() && !sells.isEmpty() && !limits.isEmpty()) {
            BigDecimal lo = limits.stream().min(BigDecimal::compareTo).orElseThrow();
            BigDecimal hi = limits.stream().max(BigDecimal::compareTo).orElseThrow();
            BigInteger n = hi.subtract(lo).divideToIntegralValue(tick).toBigInteger().add(BigInteger.ONE);
            if (n.compareTo(BigInteger.valueOf(MAX_CANDIDATES)) > 0) {
                throw err("E_LIMIT", "more than 1,000,000 candidate prices", "orders");
            }
            List<Cand> cands = new ArrayList<>();
            long vmax = Long.MIN_VALUE;
            for (int i = 0; i < n.intValue(); i++) {
                BigDecimal px = lo.add(tick.multiply(BigDecimal.valueOf(i)));
                long b = 0;
                long s = 0;
                for (AOrder x : buys) {
                    if (x.limit == null || x.limit.compareTo(px) >= 0) {
                        b += x.qty;
                    }
                }
                for (AOrder x : sells) {
                    if (x.limit == null || x.limit.compareTo(px) <= 0) {
                        s += x.qty;
                    }
                }
                cands.add(new Cand(px, Math.min(b, s), b - s));
                vmax = Math.max(vmax, Math.min(b, s));
            }
            if (vmax > 0) {
                List<Cand> keep = new ArrayList<>();
                for (Cand c : cands) {
                    if (c.vol == vmax) {
                        keep.add(c);
                    }
                }
                if ("IEX".equals(tie)) { // nearest the reference-range midpoint (ref_price), then higher
                    best = nearestRef(keep, ref);
                } else {
                    long imin = Long.MAX_VALUE;
                    for (Cand c : keep) {
                        imin = Math.min(imin, Math.abs(c.imb));
                    }
                    List<Cand> k2 = new ArrayList<>();
                    for (Cand c : keep) {
                        if (Math.abs(c.imb) == imin) {
                            k2.add(c);
                        }
                    }
                    if (k2.stream().allMatch(c -> c.imb > 0)) {
                        Cand m = k2.get(0);
                        for (Cand c : k2) {
                            m = c.px.compareTo(m.px) > 0 ? c : m;
                        }
                        k2 = List.of(m);
                    } else if (k2.stream().allMatch(c -> c.imb < 0)) {
                        Cand m = k2.get(0);
                        for (Cand c : k2) {
                            m = c.px.compareTo(m.px) < 0 ? c : m;
                        }
                        k2 = List.of(m);
                    }
                    best = nearestRef(k2, ref);
                }
            }
        }
        List<Object> fills = new ArrayList<>();
        List<Object> residual = new ArrayList<>();
        List<Object> cancelled = new ArrayList<>();
        BigDecimal price = best == null ? null : best.px;
        for (List<AOrder> side : List.of(buys, sells)) {
            long left = best == null ? 0 : best.vol;
            for (AOrder o : side) {
                long q = Math.min(o.qty, left);
                if (q > 0) {
                    fills.add(out("id", o.id, "price", at(price, places), "qty", q, "side", o.buy ? "B" : "S"));
                    left -= q;
                }
                if (o.qty - q > 0) {
                    if (o.limit == null || o.onClose) {
                        cancelled.add(o.id);
                    } else {
                        residual.add(out("id", o.id, "limit", at(o.limit, places), "qty", o.qty - q,
                                "side", o.buy ? "B" : "S"));
                    }
                }
            }
        }
        return out("cancelled", cancelled, "fills", fills, "imbalance", best == null ? 0L : best.imb,
                "label", label, "price", price == null ? null : at(price, places), "residual", residual,
                "volume", best == null ? 0L : best.vol);
    }

    // ------------------------------------------------------------------ FX spot (H-23)

    private static String[] pair(Map<?, ?> raw) {
        String p = str(raw, "pair", "");
        String base = p.length() >= 3 ? p.substring(0, 3) : p;
        String quote = p.length() >= 3 ? p.substring(3) : "";
        if (p.length() != 6 || !CCY_ORDER.contains(base) || !CCY_ORDER.contains(quote) || base.equals(quote)) {
            throw err("E_INPUT", "pair: not a pair of two listed currencies", "pair");
        }
        if (CCY_ORDER.indexOf(base) > CCY_ORDER.indexOf(quote)) {
            throw err("E_INPUT", "pair: base must rank before quote (HR-88)", "pair");
        }
        return new String[] {base, quote};
    }

    private static BigDecimal pip(String quote) {
        return new BigDecimal(quote.equals("JPY") ? "0.01" : "0.0001");
    }

    /** FX pip value in the quote currency (HR-87): notional x pip. */
    public static Map<String, Object> fxPipValue(Map<?, ?> raw) {
        BigDecimal notional = dec(raw, "notional");
        String quote = pair(raw)[1];
        if (notional.signum() < 0) {
            throw err("E_DOMAIN", "notional must not be negative", "notional");
        }
        return out("currency", quote, "pip_value", fmt(c(notional.multiply(pip(quote)))));
    }

    /** FX spot value date (HR-89): T+2 (T+1 pairs) good days in both currencies, then a USD day. */
    public static Map<String, Object> fxSpotDate(Map<?, ?> raw) {
        LocalDate trade = date(need(raw, "trade_date", ""), "trade_date");
        Object hraw = get(raw, "holidays", Map.of());
        if (!(hraw instanceof Map<?, ?> hm)) {
            throw err("E_SCHEMA", "holidays: not an object of currency -> dates", "holidays");
        }
        Map<Object, Set<LocalDate>> hol = new LinkedHashMap<>();
        for (Map.Entry<?, ?> e : hm.entrySet()) {
            hol.put(e.getKey(), dates(e.getValue(), "holidays/" + e.getKey()));
        }
        Object t1 = get(raw, "t1_pairs", T1_PAIRS);
        if (!(t1 instanceof List<?> t1l) || !t1l.stream().allMatch(x -> x instanceof String)) {
            throw err("E_SCHEMA", "t1_pairs: not an array of strings", "t1_pairs");
        }
        String[] bq = pair(raw);
        Set<LocalDate> empty = Set.of();
        Predicate<LocalDate> both = d -> good(d, hol.getOrDefault(bq[0], empty))
                && good(d, hol.getOrDefault(bq[1], empty));
        Predicate<LocalDate> nonUsd = d -> { // a USD-only holiday on T+1 does not stop the count
            for (String ccy : bq) {
                if (!ccy.equals("USD") && !good(d, hol.getOrDefault(ccy, empty))) {
                    return false;
                }
            }
            return true;
        };
        LocalDate d = t1l.contains(bq[0] + bq[1]) ? addGood(trade, 1, both)
                : addGood(addGood(trade, 1, nonUsd), 1, both);
        d = addGood(d.minusDays(1), 1, x -> both.test(x) && good(x, hol.getOrDefault("USD", empty)));
        return out("spot_date", d.toString());
    }

    /** {@code exec.sim.fx.stream}: bid rounded down and ask rounded up to the tick (fx-rfq-venue.md). */
    public static Map<String, Object> fxStream(Map<?, ?> raw) {
        List<?> path = list(raw, "mid_path");
        BigDecimal hs = dec(raw, "half_spread_pips");
        List<long[]> times = new ArrayList<>();
        List<BigDecimal> mids = new ArrayList<>();
        for (int k = 0; k < path.size(); k++) {
            Map<?, ?> x = obj(path.get(k), "mid_path/" + k);
            times.add(new long[] {integer(x, "time", "mid_path/" + k + "/")});
            mids.add(dec(x, "mid", "mid_path/" + k + "/"));
        }
        String quote = pair(raw)[1];
        BigDecimal pip = pip(quote);
        BigDecimal tick = decOr(raw, "tick", fmt(pip.divide(BigDecimal.TEN)));
        if (mids.isEmpty()) {
            throw err("E_INPUT", "mid_path is empty", "mid_path");
        }
        if (tick.signum() <= 0 || hs.signum() < 0) {
            throw err("E_DOMAIN", "tick must be positive and half_spread_pips not negative", "tick");
        }
        int places = places(tick);
        List<Object> quotes = new ArrayList<>();
        for (int k = 0; k < mids.size(); k++) {
            BigDecimal mid = mids.get(k);
            if (mid.signum() <= 0) {
                throw err("E_DOMAIN", "mid must be positive", "mid_path");
            }
            BigDecimal half = hs.multiply(pip);
            BigDecimal bid = floorDiv(c(mid.subtract(half)), tick, false).multiply(tick);
            BigDecimal ask = floorDiv(c(mid.add(half)), tick, true).multiply(tick);
            quotes.add(out("ask", at(ask, places), "bid", at(bid, places), "mid", fmt(mid), "time", times.get(k)[0]));
        }
        return out("label", FX_LABEL, "quotes", quotes);
    }

    /** {@code exec.sim.fx.request}: last look (HR-97); strict comparisons, exact decimals. */
    public static Map<String, Object> fxRequest(Map<?, ?> raw) {
        Map<?, ?> q = obj(need(raw, "quote", ""), "quote");
        BigDecimal bid = dec(q, "bid", "quote/");
        BigDecimal ask = dec(q, "ask", "quote/");
        BigDecimal qmid = dec(q, "quote_mid", "quote/");
        boolean buy = enumOf(raw, "side", "", "BUY", "SELL").equals("BUY");
        BigDecimal qty = dec(raw, "qty");
        BigDecimal after = dec(raw, "mid_after");
        BigDecimal thr = dec(raw, "threshold_pips");
        boolean sym = bool(raw, "symmetric", true);
        BigDecimal prr = dec(raw, "p_random_reject");
        boolean drawn = !raw.containsKey("u");
        double uf = 0;
        BigDecimal u;
        if (drawn) { // HR-97: u from core.rng, stream = request_index (rng.md jumps)
            BigInteger seed = bigInt(need(raw, "seed", ""), "seed");
            BigInteger idx = bigInt(need(raw, "request_index", ""), "request_index");
            if (seed.signum() < 0) { // HR-116: seed within 0..2^53 - 1
                throw err("E_LIMIT", "seed below 0", "seed");
            }
            if (idx.signum() < 0 || idx.bitLength() > 32) { // HR-116: request_index within 0..2^32 - 1
                throw err("E_LIMIT", "request_index outside 0..2^32 - 1", "request_index");
            }
            uf = Rng.seeded(seed.longValue(), idx.longValue()).nextUniform();
            u = new BigDecimal(uf);
        } else {
            u = dec(raw, "u");
        }
        String quote = pair(raw)[1];
        if (bid.compareTo(ask) > 0) {
            throw err("E_INPUT", "quote: bid above ask", "quote");
        }
        if (qty.signum() <= 0 || thr.signum() < 0 || prr.signum() < 0 || prr.compareTo(BigDecimal.ONE) > 0
                || u.signum() < 0 || u.compareTo(BigDecimal.ONE) >= 0) {
            throw err("E_DOMAIN", "qty > 0, threshold >= 0, p in [0, 1], u in [0, 1)", "u");
        }
        BigDecimal move = c(after.subtract(qmid).divide(pip(quote)));
        BigDecimal adverse = buy ? move : move.negate();
        String outcome;
        if ((sym ? move.abs() : adverse).compareTo(thr) > 0) {
            outcome = "LL_PRICE";
        } else if (u.compareTo(prr) < 0) {
            outcome = "LL_RANDOM";
        } else {
            outcome = "FILL";
        }
        String price = outcome.equals("FILL") ? fmt(buy ? ask : bid) : null;
        Map<String, Object> r = out("label", FX_LABEL, "move_pips", fmt(move), "outcome", outcome, "price", price);
        if (drawn) {
            r.put("u", uf);
        }
        return r;
    }

    // ------------------------------------------------------------------ rates (H-24)

    /** {@code H-FF[f]} (HR-90; {@code 3} = 3/8 of a 32nd) to its exact value. */
    public static BigDecimal parse32nds(Object text, String path) {
        if (!(text instanceof String s)) {
            throw err("E_SCHEMA", path + ": not a string", path);
        }
        Matcher m = N32.matcher(s);
        if (!m.matches() || !QUARTERS.containsKey(m.group(3))) {
            throw err("E_SCHEMA", path + ": not H-FF[q] with q in 0, 2, 5, 7, + (HR-109)", path);
        }
        int ff = Integer.parseInt(m.group(2));
        if (ff > 31) {
            throw err("E_DOMAIN", path + ": 32nds above 31", path);
        }
        BigDecimal frac = BigDecimal.valueOf(ff * 4L + QUARTERS.get(m.group(3))).divide(BigDecimal.valueOf(128));
        return OrderBook.range(new BigDecimal(new BigInteger(m.group(1))).add(frac), path, OrderBook.MAX_SCALE);
    }

    public static String format32nds(BigDecimal x, long resolution) {
        if (resolution > 128 || !RESOLUTIONS.contains((int) resolution)) {
            throw err("E_DOMAIN", "resolution not 32, 64 or 128", "resolution");
        }
        if (x.signum() < 0 || x.multiply(BigDecimal.valueOf(resolution)).remainder(BigDecimal.ONE).signum() != 0) {
            throw err("E_DOMAIN", "value not on the requested grid", "value");
        }
        BigInteger h = x.toBigInteger();
        int quarters = x.subtract(new BigDecimal(h)).multiply(BigDecimal.valueOf(128)).intValueExact();
        int ff = quarters / 4;
        return h + "-" + (ff < 10 ? "0" : "") + ff + QUARTER_TEXT[quarters % 4];
    }

    /** 32nds text to a decimal (HR-90). */
    public static Map<String, Object> ratesParse32nds(Map<?, ?> raw) {
        return out("value", fmt(parse32nds(need(raw, "text", ""), "text")));
    }

    /** A decimal to 32nds text at {@code resolution} parts per point (HR-90). */
    public static Map<String, Object> ratesFormat32nds(Map<?, ?> raw) {
        BigDecimal x = dec(raw, "value");
        long res = integer(raw, "resolution");
        return out("text", format32nds(x, res));
    }

    private static BigDecimal[] contract(Map<?, ?> raw) {
        Map<?, ?> cm = obj(get(raw, "contract", Map.of("symbol", "ZN")), "contract");
        Object sym = cm.get("symbol");
        if (sym != null && !(sym instanceof String)) {
            throw err("E_SCHEMA", "contract/symbol: not a string", "contract/symbol");
        }
        String[] d = CONTRACTS.getOrDefault(sym == null ? "" : (String) sym, new String[] {null, null});
        BigDecimal face = OrderBook.dec(get(cm, "face", d[0]), "contract/face");
        BigDecimal tick = OrderBook.dec(get(cm, "tick", d[1]), "contract/tick");
        if (face.signum() <= 0 || tick.signum() <= 0) {
            throw err("E_DOMAIN", "contract face and tick must be positive", "contract");
        }
        return new BigDecimal[] {face, tick};
    }

    private static BigDecimal tickValue(BigDecimal face, BigDecimal tick) {
        return c(face.multiply(tick).divide(HUNDRED));
    }

    /** Futures tick value = face x tick / 100 (HR-91). */
    public static Map<String, Object> ratesTickValue(Map<?, ?> raw) {
        BigDecimal face = dec(raw, "face");
        BigDecimal tick = dec(raw, "tick");
        if (face.signum() <= 0 || tick.signum() <= 0) {
            throw err("E_DOMAIN", "face and tick must be positive", "face");
        }
        return out("tick_value", fmt(tickValue(face, tick)));
    }

    private static String price9(BigDecimal p) {
        return fmt(p.setScale(9, RoundingMode.HALF_EVEN));
    }

    /** Coupon bond price on a coupon date, street convention (HR-92), 9 decimals. */
    public static Map<String, Object> ratesBondPrice(Map<?, ?> raw) {
        BigDecimal cp = dec(raw, "coupon");
        BigDecimal y = dec(raw, "yield");
        long f = integer(raw, "frequency");
        long n = integer(raw, "periods");
        if (f != 1 && f != 2 && f != 4 && f != 12) {
            throw err("E_DOMAIN", "frequency not 1, 2, 4 or 12", "frequency");
        }
        if (n < 1 || n > 1200) {
            throw err("E_DOMAIN", "periods outside 1..1200", "periods");
        }
        BigDecimal fd = BigDecimal.valueOf(f);
        BigDecimal g = BigDecimal.ONE.add(y.divide(fd, MC), MC);
        if (g.signum() <= 0) {
            throw err("E_DOMAIN", "yield at or below -frequency", "yield");
        }
        BigDecimal cpn = HUNDRED.multiply(cp, MC).divide(fd, MC);
        BigDecimal p = BigDecimal.ZERO;
        BigDecimal gi = BigDecimal.ONE;
        MathContext wide = new MathContext(260, RoundingMode.HALF_EVEN);
        for (int i = 1; i <= n; i++) {
            gi = gi.multiply(g, wide);
            p = p.add(cpn.divide(gi.round(MC), MC), MC);
        }
        p = p.add(HUNDRED.divide(gi.round(MC), MC), MC);
        return out("price", price9(c(p.setScale(30, RoundingMode.HALF_EVEN))));
    }

    /** Yield from a coupon-date price (HR-92): Brent ({@code core.solve}), tolerance 1e-12, binary64. */
    public static Map<String, Object> ratesBondYield(Map<?, ?> raw) {
        BigDecimal cp = dec(raw, "coupon");
        BigDecimal p = dec(raw, "price");
        long f = integer(raw, "frequency");
        long n = integer(raw, "periods");
        if (f != 1 && f != 2 && f != 4 && f != 12) {
            throw err("E_DOMAIN", "frequency not 1, 2, 4 or 12", "frequency");
        }
        if (n < 1 || n > 1200) {
            throw err("E_DOMAIN", "periods outside 1..1200", "periods");
        }
        if (p.signum() <= 0) {
            throw err("E_DOMAIN", "price must be positive", "price");
        }
        double cf = HUNDRED.multiply(cp).divide(BigDecimal.valueOf(f), MC).doubleValue();
        double pf = p.doubleValue();
        double fd = f;
        DoubleUnaryOperator g = y -> {
            double d = 1.0 + y / fd;
            double s = 0.0;
            for (int i = 1; i <= n; i++) {
                s += cf / Math.pow(d, i);
            }
            return s + 100.0 / Math.pow(d, n) - pf;
        };
        double lo = -0.99 * f;
        double hi = 10.0;
        if (g.applyAsDouble(lo) * g.applyAsDouble(hi) > 0) {
            throw err("E_DOMAIN", "no yield in (-0.99 f, 10)", "price");
        }
        double y = RootFinders.brent(g, lo, hi, new RootFinders.Tolerances(1e-12, 0.0, 200)).root();
        return out("yield", y);
    }

    /** Bill price on the discount basis [UST-BILL]: 100 (1 - d days / 360), 9 decimals. */
    public static Map<String, Object> ratesBillPrice(Map<?, ?> raw) {
        BigDecimal d = dec(raw, "discount");
        long days = integer(raw, "days");
        if (days < 0 || days > 366) {
            throw err("E_DOMAIN", "days outside 0..366", "days");
        }
        BigDecimal x = d.multiply(BigDecimal.valueOf(days), MC).divide(BigDecimal.valueOf(360), MC);
        BigDecimal p = HUNDRED.multiply(BigDecimal.ONE.subtract(x, MC), MC);
        return out("price", price9(p));
    }

    private static BigInteger futTicks(Object v, BigDecimal tick, String path) {
        BigDecimal x = v instanceof String s && s.length() > 1 && s.substring(1).contains("-")
                ? parse32nds(v, path) : OrderBook.dec(v, path);
        if (x.signum() < 0 || x.remainder(tick).signum() != 0) {
            throw err("E_DOMAIN", path + ": price off the contract grid", path);
        }
        return x.divide(tick, MC).toBigIntegerExact();
    }

    /** Futures price (32nds text or decimal) to integer ticks (rates-futures-venue.md). */
    public static Map<String, Object> futToTicks(Map<?, ?> raw) {
        Object v = need(raw, "price", "");
        BigDecimal tick = contract(raw)[1];
        return out("label", RATES_LABEL, "ticks", integerOut(futTicks(v, tick, "price")));
    }

    /** Integer ticks to 32nds text at the contract resolution. */
    public static Map<String, Object> futToText(Map<?, ?> raw) {
        long t = integer(raw, "ticks");
        BigDecimal tick = contract(raw)[1];
        if (t < 0) {
            throw err("E_DOMAIN", "ticks must not be negative", "ticks");
        }
        BigDecimal res = BigDecimal.ONE.divide(tick, MC);
        if (res.remainder(BigDecimal.ONE).signum() != 0 || res.compareTo(BigDecimal.valueOf(128)) > 0
                || !RESOLUTIONS.contains(res.intValue())) {
            throw err("E_DOMAIN", "contract tick is not 1/32, 1/64 or 1/128", "contract");
        }
        return out("label", RATES_LABEL, "text", format32nds(BigDecimal.valueOf(t).multiply(tick), res.intValue()));
    }

    /** One participant's round trip (HR-102): (sell - buy) ticks x qty x tick value - fees. */
    public static Map<String, Object> futPnl(Map<?, ?> raw) {
        long qty = integer(raw, "qty");
        Object bp = need(raw, "buy_price", "");
        Object sp = need(raw, "sell_price", "");
        BigDecimal fee = decOr(raw, "fee_per_contract", "0");
        BigDecimal[] ft = contract(raw);
        if (qty <= 0 || fee.signum() < 0) {
            throw err("E_DOMAIN", "qty must be positive and fee not negative", "qty");
        }
        BigInteger s = futTicks(sp, ft[1], "sell_price");
        BigInteger d = s.subtract(futTicks(bp, ft[1], "buy_price"));
        BigDecimal q = BigDecimal.valueOf(qty);
        BigDecimal fees = c(fee.multiply(BigDecimal.valueOf(2)).multiply(q));
        BigDecimal pnl = c(new BigDecimal(d).multiply(q).multiply(tickValue(ft[0], ft[1])).subtract(fees));
        return out("fees", fmt(fees), "label", RATES_LABEL, "pnl", fmt(pnl));
    }

    /** Daily variation margin (HR-92, HR-103): previous mark = fill price on the trade day. */
    public static Map<String, Object> futVariation(Map<?, ?> raw) {
        boolean buy = enumOf(raw, "side", "", "BUY", "SELL").equals("BUY");
        long qty = integer(raw, "qty");
        Object p0 = need(raw, "price", "");
        List<?> settles = list(raw, "settlements");
        BigDecimal[] ft = contract(raw);
        if (settles.isEmpty()) {
            throw err("E_INPUT", "settlements is empty", "settlements");
        }
        if (qty <= 0) {
            throw err("E_DOMAIN", "qty must be positive", "qty");
        }
        BigInteger mark = futTicks(p0, ft[1], "price");
        BigDecimal tv = tickValue(ft[0], ft[1]);
        BigDecimal sq = BigDecimal.valueOf(buy ? qty : -qty);
        List<Object> out = new ArrayList<>();
        for (int k = 0; k < settles.size(); k++) {
            BigInteger t = futTicks(settles.get(k), ft[1], "settlements/" + k);
            out.add(fmt(c(new BigDecimal(t.subtract(mark)).multiply(sq).multiply(tv))));
            mark = t;
        }
        return out("label", RATES_LABEL, "variation_margin", out);
    }

    /**
     * {@code exec.sim.fut.run}: the lit engine unchanged on the contract tick grid, plus P&amp;L per trader marked at
     * the last trade, minus {@code fee_per_contract} per contract per side (HR-102).
     */
    public static Map<String, Object> futRun(Map<?, ?> raw) {
        List<?> events = list(raw, "events");
        BigDecimal fee = decOr(raw, "fee_per_contract", "0");
        BigDecimal[] ft = contract(raw);
        BigDecimal tick = ft[1];
        if (fee.signum() < 0) {
            throw err("E_DOMAIN", "fee_per_contract must not be negative", "fee_per_contract");
        }
        Map<String, String> trader = new LinkedHashMap<>();
        List<Object> mapped = new ArrayList<>();
        for (int k = 0; k < events.size(); k++) {
            Map<Object, Object> e = new LinkedHashMap<>(obj(events.get(k), "events/" + k));
            if (e.get("price") instanceof String) {
                e.put("price", fmt(new BigDecimal(futTicks(e.get("price"), tick, "events/" + k + "/price"))
                        .multiply(tick)));
            }
            if ("NEW".equals(e.get("op")) && e.get("id") instanceof String id && e.get("trader") instanceof String t) {
                trader.put(id, t);
            }
            mapped.add(e);
        }
        Map<String, Object> lit = LitMatching.run(fmt(tick), "1", mapped,
                Map.of("maker_rebate", "0", "taker_fee", "0"));
        BigDecimal tv = tickValue(ft[0], tick);
        Map<String, Boolean> buyer = new LinkedHashMap<>();
        for (Object o : mapped) {
            Map<?, ?> e = (Map<?, ?>) o;
            if ("NEW".equals(e.get("op"))) {
                buyer.put((String) e.get("id"), "BUY".equals(e.get("side")));
            }
        }
        Map<String, BigDecimal> pos = new TreeMap<>();
        Map<String, BigDecimal> cash = new TreeMap<>();
        Map<String, BigDecimal> fees = new TreeMap<>();
        BigDecimal last = null;
        for (Object fo : (List<?>) lit.get("fills")) {
            Map<?, ?> f = (Map<?, ?>) fo;
            BigDecimal p = new BigDecimal((String) f.get("price"));
            BigDecimal q = new BigDecimal((String) f.get("qty"));
            last = p;
            for (Object oid : new Object[] {f.get("maker_id"), f.get("taker_id")}) {
                String t = trader.get(oid);
                BigDecimal sq = buyer.get(oid) ? q : q.negate();
                pos.merge(t, sq, BigDecimal::add);
                cash.put(t, cash.getOrDefault(t, BigDecimal.ZERO).subtract(sq.multiply(p).divide(tick, MC)));
                fees.put(t, c(fees.getOrDefault(t, BigDecimal.ZERO).add(fee.multiply(q))));
            }
        }
        BigDecimal mark = (last == null ? BigDecimal.ZERO : last).divide(tick, MC);
        Map<String, Object> pnl = new TreeMap<>();
        for (String t : pos.keySet()) {
            pnl.put(t, fmt(c(pos.get(t).multiply(mark).add(cash.get(t)).multiply(tv).subtract(fees.get(t)))));
        }
        Map<String, Object> feeOut = new TreeMap<>();
        fees.forEach((t, v) -> feeOut.put(t, fmt(v)));
        Map<String, Object> result = new TreeMap<>(lit);
        result.put("fees", feeOut);
        result.put("pnl", pnl);
        result.put("label", RATES_LABEL);
        return result;
    }
}
