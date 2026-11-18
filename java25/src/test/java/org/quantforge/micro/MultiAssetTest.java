package org.quantforge.micro;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.Set;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Stream;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestFactory;
import org.quantforge.core.Json;
import org.quantforge.core.QfError;

/**
 * Stage H multi-asset H-22, H-23, H-24: every golden row of auc_h, eqc_h, fxc_h, fxv_h, rtc_h, fut_h and e1_h3,
 * then acceptance A3 (properties) and A4 (labels) of {@code asset-conventions.md}, as the Python tests.
 */
class MultiAssetTest {
    private static final Path GOLD = Path.of("..", "datasets", "golden", "stage_h");
    private static final String[] SUITES = {"auc_h", "eqc_h", "fxc_h", "fxv_h", "rtc_h", "fut_h", "ses_h", "acls_h", "e1_h3"};
    private static final Map<String, Function<Map<?, ?>, Map<String, Object>>> FN = new HashMap<>();
    private static final Set<String> LABELS =
            Set.of(MultiAsset.EQ_LABEL, MultiAsset.IEX_LABEL, MultiAsset.FX_LABEL, MultiAsset.RATES_LABEL);

    static {
        FN.put("micro.eq.round_price", MultiAsset::eqRoundPrice);
        FN.put("micro.eq.fee_check", MultiAsset::eqFeeCheck);
        FN.put("micro.eq.round_lot", MultiAsset::eqRoundLot);
        FN.put("micro.eq.settle_date", MultiAsset::eqSettleDate);
        FN.put("exec.sim.auction.uncross", MultiAsset::auctionUncross);
        FN.put("micro.fx.pip_value", MultiAsset::fxPipValue);
        FN.put("micro.fx.spot_date", MultiAsset::fxSpotDate);
        FN.put("exec.sim.fx.stream", MultiAsset::fxStream);
        FN.put("exec.sim.fx.request", MultiAsset::fxRequest);
        FN.put("micro.rates.parse_32nds", MultiAsset::ratesParse32nds);
        FN.put("micro.rates.format_32nds", MultiAsset::ratesFormat32nds);
        FN.put("micro.rates.tick_value", MultiAsset::ratesTickValue);
        FN.put("micro.rates.bond_price", MultiAsset::ratesBondPrice);
        FN.put("micro.rates.bill_price", MultiAsset::ratesBillPrice);
        FN.put("exec.sim.fut.to_ticks", MultiAsset::futToTicks);
        FN.put("exec.sim.fut.to_text", MultiAsset::futToText);
        FN.put("exec.sim.fut.pnl", MultiAsset::futPnl);
        FN.put("exec.sim.fut.variation", MultiAsset::futVariation);
        FN.put("exec.sim.fut.run", MultiAsset::futRun);
        FN.put("micro.rates.bond_yield", MultiAsset::ratesBondYield);
        FN.put("exec.sim.lit.run", i -> LitMatching.run((String) i.get("tick_size"), (String) i.get("lot_size"),
                (List<?>) i.get("events"), (Map<?, ?>) i.get("fee_schedule"), i.get("session")));
        FN.put("exec.sor.allocate", Sor::allocate);
    }

    private static Object canon(Object v) {
        if (v instanceof Map<?, ?> m) {
            Map<String, Object> t = new TreeMap<>();
            m.forEach((k, x) -> t.put((String) k, canon(x)));
            return t;
        }
        if (v instanceof List<?> l) {
            return l.stream().map(MultiAssetTest::canon).toList();
        }
        return v;
    }

    private static String text(Object v) {
        StringBuilder b = new StringBuilder();
        Json.write(b, canon(v));
        return b.toString();
    }

    @TestFactory
    Stream<DynamicTest> goldens() throws IOException {
        List<DynamicTest> out = new ArrayList<>();
        for (String s : SUITES) {
            Map<?, ?> doc = (Map<?, ?>) Json.parse(Files.readString(GOLD.resolve(s + ".json"))).value();
            for (Object o : (List<?>) doc.get("cases")) {
                Map<?, ?> c = (Map<?, ?>) o;
                out.add(DynamicTest.dynamicTest((String) c.get("case_id"), () -> {
                    var fn = FN.get((String) c.get("operation"));
                    Map<?, ?> exp = (Map<?, ?>) c.get("expected");
                    Map<?, ?> inp = (Map<?, ?>) c.get("inputs");
                    if ("error".equals(exp.get("status"))) {
                        QfError e = assertThrows(QfError.class, () -> fn.apply(inp));
                        assertEquals(exp.get("error_code"), e.code(), e.getMessage());
                    } else {
                        Map<String, Object> got = fn.apply(inp);
                        String op = (String) c.get("operation");
                        if (op.equals("micro.rates.bond_yield")) {
                            double want = ((Json.Number) ((Map<?, ?>) exp.get("outputs")).get("yield")).value();
                            assertEquals(want, (Double) got.get("yield"), 1e-10);
                        } else {
                            assertEquals(text(exp.get("outputs")), text(got), String.valueOf(c.get("case_id")));
                        }
                        // A4 as ruled 2026-11-18 (HR-111): venue and simulator outputs carry a label, conventions none
                        boolean venue = op.startsWith("exec.") && !op.equals("exec.sor.allocate");
                        assertTrue(venue ? LABELS.contains(got.get("label")) : !got.containsKey("label"));
                    }
                }));
            }
        }
        return out.stream();
    }

    private static Map<String, Object> m(Object... kv) {
        Map<String, Object> r = new LinkedHashMap<>();
        for (int i = 0; i < kv.length; i += 2) {
            r.put((String) kv[i], kv[i + 1]);
        }
        return r;
    }

    private static String code(Function<Map<?, ?>, Map<String, Object>> fn, Map<?, ?> in) {
        return assertThrows(QfError.class, () -> fn.apply(in)).code();
    }

    // ------------------------------------------------------------------ A3 properties

    @Test
    void a3RoundingNeverMoreAggressive() {
        Random rng = new Random(20261118);
        for (String tier : new String[] {"PENNY", "HALF_PENNY"}) {
            for (int i = 0; i < 2000; i++) {
                BigDecimal p = BigDecimal.valueOf(1 + rng.nextInt(100_000_000 - 1), 5);
                for (String side : new String[] {"BUY", "SELL"}) {
                    BigDecimal r = new BigDecimal((String) MultiAsset.eqRoundPrice(
                            m("price", p.toPlainString(), "side", side, "tick_tier", tier)).get("price"));
                    assertTrue(side.equals("BUY") ? r.compareTo(p) <= 0 : r.compareTo(p) >= 0);
                    BigDecimal tick = new BigDecimal(r.compareTo(BigDecimal.ONE) < 0 ? "0.0001"
                            : tier.equals("HALF_PENNY") ? "0.005" : "0.01");
                    assertTrue(r.remainder(tick).signum() == 0 || r.compareTo(BigDecimal.ONE) == 0);
                }
            }
        }
    }

    @Test
    void a3ThirtySecondsRoundTripOn128Grid() {
        for (int n = 0; n < 128 * 130; n += 7) { // HR-109: quarter-32nds, so the 1/128 grid
            BigDecimal x = BigDecimal.valueOf(n).divide(BigDecimal.valueOf(128));
            String t = (String) MultiAsset.ratesFormat32nds(m("resolution", 128L, "value", x.toPlainString()))
                    .get("text");
            assertEquals(0, new BigDecimal((String) MultiAsset.ratesParse32nds(m("text", t)).get("value"))
                    .compareTo(x));
        }
    }

    @Test
    void a3SpotDateGoodAndAtLeastTPlus1() {
        Random rng = new Random(7);
        LocalDate start = LocalDate.of(2026, 1, 1);
        for (int i = 0; i < 500; i++) {
            Map<String, Object> hol = new LinkedHashMap<>();
            for (String ccy : new String[] {"EUR", "USD", "JPY", "CAD"}) {
                List<Object> d = new ArrayList<>();
                for (int k = 0; k < 15; k++) {
                    d.add(start.plusDays(rng.nextInt(400)).toString());
                }
                hol.put(ccy, d);
            }
            LocalDate t = start.plusDays(rng.nextInt(365));
            for (String pair : new String[] {"EURUSD", "USDJPY", "EURJPY", "USDCAD"}) {
                LocalDate s = LocalDate.parse((String) MultiAsset.fxSpotDate(
                        m("holidays", hol, "pair", pair, "trade_date", t.toString())).get("spot_date"));
                assertTrue(!s.isBefore(t.plusDays(1)));
                for (String ccy : List.of(pair.substring(0, 3), pair.substring(3), "USD")) {
                    assertTrue(s.getDayOfWeek().compareTo(DayOfWeek.SATURDAY) < 0);
                    assertTrue(!((List<?>) hol.get(ccy)).contains(s.toString()));
                }
            }
        }
    }

    @Test
    void a3AuctionVolumeMaximal() {
        Random rng = new Random(11);
        for (int it = 0; it < 300; it++) {
            int n = 1 + rng.nextInt(11);
            List<Object> orders = new ArrayList<>();
            Map<String, Map<String, Object>> ids = new LinkedHashMap<>();
            int nb = 0;
            int ns = 0;
            for (int k = 0; k < n; k++) {
                String lim = rng.nextDouble() < 0.1 ? "MARKET"
                        : BigDecimal.valueOf(990 + rng.nextInt(21), 2).toPlainString();
                boolean buy = rng.nextBoolean();
                Map<String, Object> o = m("limit", lim, "qty", (long) (1 + rng.nextInt(499)), "side",
                        buy ? "BUY" : "SELL");
                orders.add(o);
                ids.put(buy ? "b" + ++nb : "a" + ++ns, o);
            }
            String tie = rng.nextBoolean() ? "CBOE" : "IEX";
            Map<String, Object> out = MultiAsset.auctionUncross(m("orders", orders, "phase", "OPEN",
                    "ref_price", "10.00", "tick_size", "0.01", "tie_break", tie));
            long best = 0;
            boolean hasLimit = false;
            for (int k = 990; k <= 1010; k++) {
                BigDecimal p = BigDecimal.valueOf(k, 2);
                long b = 0;
                long s = 0;
                for (Object x : orders) {
                    Map<?, ?> o = (Map<?, ?>) x;
                    boolean mkt = o.get("limit").equals("MARKET");
                    hasLimit |= !mkt;
                    BigDecimal l = mkt ? null : new BigDecimal((String) o.get("limit"));
                    if (o.get("side").equals("BUY") && (mkt || l.compareTo(p) >= 0)) {
                        b += (Long) o.get("qty");
                    }
                    if (o.get("side").equals("SELL") && (mkt || l.compareTo(p) <= 0)) {
                        s += (Long) o.get("qty");
                    }
                }
                best = Math.max(best, Math.min(b, s));
            }
            assertEquals(hasLimit ? best : 0L, out.get("volume"));
            long filled = 0;
            Map<String, Long> filledBy = new HashMap<>();
            for (Object f : (List<?>) out.get("fills")) {
                Map<?, ?> fm = (Map<?, ?>) f;
                filled += (Long) fm.get("qty");
                filledBy.merge((String) fm.get("id"), (Long) fm.get("qty"), Long::sum);
                Map<String, Object> o = ids.get(fm.get("id"));
                if (!o.get("limit").equals("MARKET")) {
                    int cmp = new BigDecimal((String) fm.get("price")).compareTo(new BigDecimal((String) o.get("limit")));
                    assertTrue(o.get("side").equals("BUY") ? cmp <= 0 : cmp >= 0);
                }
            }
            assertEquals(2 * (Long) out.get("volume"), filled);
            long rest = 0;
            for (Object r : (List<?>) out.get("residual")) {
                rest += (Long) ((Map<?, ?>) r).get("qty");
            }
            long cancelled = 0;
            long total = 0;
            for (var e : ids.entrySet()) {
                total += (Long) e.getValue().get("qty");
                if (((List<?>) out.get("cancelled")).contains(e.getKey())) {
                    cancelled += (Long) e.getValue().get("qty") - filledBy.getOrDefault(e.getKey(), 0L);
                }
            }
            assertEquals(total, filled + rest + cancelled);
        }
    }

    // ------------------------------------------------------------------ paths the goldens do not reach

    private static Map<String, Object> ev(String id, String price, String side, String trader) {
        return m("id", id, "op", "NEW", "price", price, "qty", "3", "side", side, "trader", trader, "type", "LIMIT");
    }

    @Test
    void futRunReusesLitEngine() {
        List<Object> ev = List.of(ev("S1", "110-16", "SELL", "M"), ev("B1", "110-16", "BUY", "P"),
                ev("S2", "110-17+", "SELL", "P"), ev("B2", "110-17+", "BUY", "N"));
        Map<String, Object> out = MultiAsset.futRun(m("contract", m("symbol", "ZN"), "events", ev,
                "fee_per_contract", "1.00"));
        assertEquals(MultiAsset.RATES_LABEL, out.get("label"));
        assertEquals("134.625", ((Map<?, ?>) out.get("pnl")).get("P"));
        assertEquals("110.5", ((Map<?, ?>) ((List<?>) out.get("fills")).get(0)).get("price"));
        assertEquals("E_DOMAIN", code(MultiAsset::futRun, m("events", List.of(ev("S1", "110-162", "SELL", "M")))));
    }

    @Test
    void morePaths() {
        assertTrue(!MultiAsset.eqRoundPrice(m("price", "5", "side", "BUY")).containsKey("label"));
        assertEquals(MultiAsset.IEX_LABEL, MultiAsset.auctionUncross(m("orders", List.of(), "phase", "OPEN",
                "ref_price", "1", "tick_size", "0.01", "data_source", "IEX")).get("label"));
        assertEquals("0.001", MultiAsset.eqFeeCheck(m("price", "20", "taker_fee", "0.01", "cap_check", false))
                .get("cap"));
        assertEquals("100", MultiAsset.ratesBondPrice(m("coupon", "0", "frequency", 1L, "periods", 1L, "yield", "0"))
                .get("price"));
        assertEquals(List.of("-62.5", "62.5"), MultiAsset.futVariation(m("price", "110-00", "qty", 2L,
                "settlements", List.of("110-01", "110-00"), "side", "SELL")).get("variation_margin"));
        assertEquals("2026-11-27", MultiAsset.fxSpotDate(m("pair", "USDCAD", "trade_date", "2026-11-25",
                "holidays", m("USD", List.of("2026-11-26")))).get("spot_date"));
        Function<Map<?, ?>, Map<String, Object>> rp = MultiAsset::eqRoundPrice;
        assertEquals("E_INPUT", code(rp, m("price", "1", "side", "BUY", "tick_table", List.of(List.of("1", "0.01")))));
        assertEquals("E_DOMAIN", code(rp, m("price", "1", "side", "BUY", "tick_table", List.of(List.of("0", "0")))));
        assertEquals("E_SCHEMA", code(rp, m("price", "1", "side", "BUY", "tick_tier", "X")));
        assertEquals("E_SCHEMA", code(rp, m("price", 1L, "side", "BUY")));
        assertEquals("E_SCHEMA", code(MultiAsset::eqSettleDate, m("trade_date", "2026-13-01")));
        assertEquals("E_INPUT", code(MultiAsset::fxPipValue, m("notional", "1", "pair", "USDEUR")));
        assertEquals("E_INPUT", code(MultiAsset::fxPipValue, m("notional", "1", "pair", "EUR")));
        assertEquals("E_DOMAIN", code(MultiAsset::ratesFormat32nds, m("value", "1", "resolution", 100L)));
        assertEquals("E_SCHEMA", code(MultiAsset::ratesParse32nds, m("text", "1-1")));
        assertEquals("E_SCHEMA", code(MultiAsset::ratesParse32nds, m("text", "1-013")));
        assertEquals("E_DOMAIN", code(MultiAsset::ratesBondYield, m("coupon", "0.04", "frequency", 2L,
                "periods", 2L, "price", "0.0001")));
        assertEquals("E_DOMAIN", code(MultiAsset::ratesParse32nds, m("text", "1-32")));
        assertEquals("E_SCHEMA", code(MultiAsset::ratesParse32nds, m("text", 1L)));
        assertEquals("E_DOMAIN", code(MultiAsset::futToText, m("ticks", 1L, "contract", m("face", "1", "tick", "0.1"))));
        assertEquals("E_SCHEMA", code(MultiAsset::futToTicks, m("price", "1", "contract", m("symbol", 3L))));
        assertEquals("E_INPUT", code(MultiAsset::futVariation, m("side", "BUY", "qty", 1L, "price", "1",
                "settlements", List.of())));
        assertEquals("E_DOMAIN", code(MultiAsset::eqSettleDate, m("trade_date", "2026-11-18", "settle_lag", 31L)));
    }

    @Test
    void hr93AssetClassDarkAndSor() {
        for (String cls : new String[] {"FX", "RATES"}) {
            assertEquals("E_UNSUPPORTED_OPERATION", assertThrows(QfError.class, () -> DarkPool.run(
                    m("lot_size", "1", "tick_size", "0.01", "p_firm", "1", "seed", 1L, "asset_class", cls),
                    List.of())).code());
        }
        assertTrue(DarkPool.run(m("lot_size", "1", "tick_size", "0.01", "p_firm", "1", "seed", 1L,
                "asset_class", "EQUITY"), List.of()).containsKey("label"));
        Map<String, Object> base = m("S", "4", "f", "0.3", "h", "0.5", "lambda_o", "1", "lambda_u", "1",
                "theta", "0", "lit_samples", List.of(List.of("0"), List.of("4")), "asset_class", "FX",
                "venues", List.of(m("Q", "0", "as", "0", "kind", "LIT", "r", "0.2", "asset_class", "FX"),
                        m("as", "0.1", "kind", "DARK", "r", "0", "tail", List.of("0.5", "0"), "asset_class", "FX")));
        assertEquals("E_UNSUPPORTED_OPERATION", code(Sor::allocate, base));
        base.put("asset_class", "RATES");
        assertEquals("E_INPUT", code(Sor::allocate, base));
    }

    @Test
    void lastLookDrawReproducible() {
        Map<String, Object> inp = m("mid_after", "1.0852", "p_random_reject", "0.5", "pair", "EURUSD", "qty", "1",
                "quote", m("ask", "1.0852", "bid", "1.0850", "quote_mid", "1.0851"), "side", "BUY",
                "threshold_pips", "2", "seed", 7L, "request_index", 5L);
        Map<String, Object> out = MultiAsset.fxRequest(inp);
        assertEquals(org.quantforge.core.Rng.seeded(7, 5).nextUniform(), (Double) out.get("u"));
        assertEquals(text(out), text(MultiAsset.fxRequest(inp)));
        inp.put("request_index", -1L);
        assertEquals("E_SCHEMA", code(MultiAsset::fxRequest, inp));
    }

    @Test
    void sessionConservationAndPhaseOrder() {
        List<Object> ev = new ArrayList<>(List.of(
                m("id", "B1", "op", "NEW", "qty", "5", "side", "BUY", "trader", "A", "type", "LIMIT", "price", "1.00"),
                m("id", "S1", "op", "NEW", "qty", "5", "side", "SELL", "trader", "B", "type", "LIMIT", "price", "1.01"),
                m("id", "S1", "op", "CANCEL")));
        Map<String, Object> fees = m("maker_rebate", "0", "taker_fee", "0");
        Map<String, Object> out = LitMatching.run("0.01", "1", ev, fees, m("ref_price", "1"));
        assertEquals("PRE_OPEN", out.get("phase"));
        assertEquals(List.of(), out.get("auctions"));
        Map<?, ?> cons = (Map<?, ?>) out.get("conservation");
        assertEquals("5", ((Map<?, ?>) cons.get("B1")).get("resting"));
        assertEquals("5", ((Map<?, ?>) cons.get("S1")).get("cancelled"));
        ev.set(2, m("op", "PHASE", "phase", "CONTINUOUS"));
        out = LitMatching.run("0.01", "1", ev, fees, m("ref_price", "1"));
        assertEquals(null, ((Map<?, ?>) ((List<?>) out.get("auctions")).get(0)).get("price"));
        assertEquals(1, ((List<?>) ((Map<?, ?>) out.get("book")).get("bids")).size());
        ev.add(m("op", "PHASE", "phase", "PRE_OPEN"));
        assertEquals("E_INPUT", assertThrows(QfError.class,
                () -> LitMatching.run("0.01", "1", ev, fees, m("ref_price", "1"))).code());
    }
}
