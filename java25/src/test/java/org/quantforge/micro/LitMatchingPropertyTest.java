package org.quantforge.micro;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import net.jqwik.api.constraints.LongRange;
import org.junit.jupiter.api.Test;

/**
 * Properties of {@code lit-matching.md} on random event streams: every order's quantity is conserved
 * (submitted = filled + resting + cancelled + rejected), the book is never crossed or locked after any event, and
 * the output carries the simulated-venue label. Also the [KR-CRC] component rule of {@code order-book.md}.
 */
class LitMatchingPropertyTest {
    private static final String[] TYPES =
        {"LIMIT", "LIMIT", "LIMIT", "MARKET", "IOC", "FOK", "ICEBERG", "POST_ONLY", "PEG_MID", "PEG_PRIMARY"};

    private static List<Map<String, Object>> events(long seed, int n) {
        Random r = new Random(seed);
        List<Map<String, Object>> out = new ArrayList<>();
        List<String> ids = new ArrayList<>();
        for (int k = 0; k < n; k++) {
            Map<String, Object> e = new LinkedHashMap<>();
            int roll = r.nextInt(10);
            if (roll < 7 || ids.isEmpty()) {
                String id = "O" + k;
                ids.add(id);
                String type = TYPES[r.nextInt(TYPES.length)];
                int qty = 1 + r.nextInt(20);
                e.put("op", "NEW");
                e.put("id", id);
                e.put("trader", "T" + r.nextInt(3));
                e.put("side", r.nextBoolean() ? "BUY" : "SELL");
                e.put("type", type);
                e.put("qty", Integer.toString(qty));
                if (!type.equals("MARKET")) {
                    e.put("price", new BigDecimal(9500 + r.nextInt(11) * 10).movePointLeft(2).toPlainString());
                }
                if (type.equals("ICEBERG")) {
                    e.put("display_qty", Integer.toString(1 + r.nextInt(qty)));
                }
            } else {
                e.put("op", roll < 9 ? "CANCEL" : "MODIFY");
                e.put("id", ids.get(r.nextInt(ids.size())));
                if (roll == 9) {
                    e.put("qty", Integer.toString(1 + r.nextInt(20)));
                }
            }
            out.add(e);
        }
        return out;
    }

    private static Map<String, Object> run(List<Map<String, Object>> ev) {
        return LitMatching.run("0.1", "1", ev, Map.of("taker_fee", "0.0002", "maker_rebate", "0.0001"));
    }

    @SuppressWarnings("unchecked")
    @Property(tries = 60)
    void conservedAndNeverCrossed(@ForAll @LongRange(min = 0, max = 1_000_000) long seed) {
        List<Map<String, Object>> ev = events(seed, 40);
        for (int n = 1; n <= ev.size(); n++) {
            Map<String, Object> out = run(ev.subList(0, n));
            assertEquals(LitMatching.LABEL, out.get("label"));
            Map<String, Map<String, String>> cons = (Map<String, Map<String, String>>) out.get("conservation");
            for (Map<String, String> c : cons.values()) {
                BigDecimal rhs = new BigDecimal(c.get("filled")).add(new BigDecimal(c.get("resting")))
                        .add(new BigDecimal(c.get("cancelled"))).add(new BigDecimal(c.get("rejected")));
                assertEquals(0, new BigDecimal(c.get("submitted")).compareTo(rhs), c.toString());
            }
            Map<String, List<Map<String, Object>>> book = (Map<String, List<Map<String, Object>>>) out.get("book");
            BigDecimal bid = null;
            BigDecimal ask = null;
            for (Map<String, Object> o : book.get("bids")) {
                if (o.get("price") != null) {
                    BigDecimal p = new BigDecimal((String) o.get("price"));
                    bid = bid == null ? p : bid.max(p);
                }
            }
            for (Map<String, Object> o : book.get("asks")) {
                if (o.get("price") != null) {
                    BigDecimal p = new BigDecimal((String) o.get("price"));
                    ask = ask == null ? p : ask.min(p);
                }
            }
            if (bid != null && ask != null) {
                assertTrue(bid.compareTo(ask) < 0, "crossed or locked at event " + n + ": " + bid + " >= " + ask);
            }
        }
    }

    @Test
    void checksumComponent() {
        assertEquals("452852", OrderBook.component("45285.2", 1));
        assertEquals("100000", OrderBook.component("0.00100000", 8));
        assertEquals("0", OrderBook.component("0.0", 1));
    }
}
