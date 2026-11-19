package org.quantforge.risk;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Random;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Json;
import org.quantforge.core.QfError;

/** SA-CCR (K-8d): CRE99 published examples, rules, errors, the shared table, and seeded property tests. */
class SaCcrTest {
    static SaCcr.Trade ir(String id, double n, double mv, double m, String pos, double s, double e, String ccy) {
        return new SaCcr.Trade(id, "IR", n, mv, m, "LINEAR", pos, "NORMAL", s, e, ccy, null, null, null, null, null,
                null, 0.0, null, null);
    }

    static SaCcr.Trade fx(String id, double n, double mv, double m, String pos, String pair) {
        return new SaCcr.Trade(id, "FX", n, mv, m, "LINEAR", pos, "NORMAL", null, null, pair, null, null, null, null,
                null, null, 0.0, null, null);
    }

    static SaCcr.Trade named(String id, String cls, double n, double mv, double m, String pos, String entity,
            String sub) {
        Double s = cls.equals("CREDIT") ? 0.0 : null;
        Double e = cls.equals("CREDIT") ? m : null;
        return new SaCcr.Trade(id, cls, n, mv, m, "LINEAR", pos, "NORMAL", s, e, null, entity, sub, null, null, null,
                null, 0.0, null, null);
    }

    static final List<SaCcr.Trade> EX1 = List.of(
            ir("1", 10000, 30, 10, "LONG", 0, 10, "USD"),
            ir("2", 10000, -20, 4, "SHORT", 0, 4, "USD"),
            new SaCcr.Trade("3", "IR", 5000, 50, 11, "OPTION", "BOUGHT", "NORMAL", 1.0, 11.0, "EUR", null, null, "PUT",
                    0.06, 0.05, 1.0, 0.0, null, null));
    static final List<SaCcr.Trade> EX2 = List.of(
            new SaCcr.Trade("4", "CREDIT", 10000, 20, 3, "LINEAR", "LONG", "NORMAL", 0.0, 3.0, null, "Firm A", "AA",
                    null, null, null, null, 0.0, null, null),
            new SaCcr.Trade("5", "CREDIT", 10000, -40, 6, "LINEAR", "SHORT", "NORMAL", 0.0, 6.0, null, "Firm B", "BBB",
                    null, null, null, null, 0.0, null, null),
            new SaCcr.Trade("6", "CREDIT", 10000, 0, 5, "LINEAR", "LONG", "NORMAL", 0.0, 5.0, null, "CDX.IG", "IG",
                    null, null, null, null, 0.0, null, null));
    static final List<SaCcr.Trade> EX3 = List.of(
            named("7", "COMMODITY", 10000, -50, 0.75, "LONG", "CRUDE_OIL", "OIL_GAS"),
            named("8", "COMMODITY", 20000, -30, 2, "SHORT", "CRUDE_OIL", "OIL_GAS"),
            named("9", "COMMODITY", 10000, 100, 5, "LONG", "SILVER", "METALS"));
    static final SaCcr.Margin WEEKLY = new SaCcr.Margin(0, 5, 150, 5, null, false, false);

    static List<SaCcr.Trade> cat(List<SaCcr.Trade> a, List<SaCcr.Trade> b) {
        List<SaCcr.Trade> out = new ArrayList<>(a);
        out.addAll(b);
        return out;
    }

    static SaCcr.Result ead(List<SaCcr.Trade> t) {
        return SaCcr.ead(t, 0.0, null, true);
    }

    /** KR-30: full precision, rounded half away from zero to the printed digits (CRE99.20). */
    @Test
    void cre99PublishedEads() {
        assertEquals(569, Math.round(ead(EX1).ead()));
        assertEquals(381, Math.round(ead(EX2).ead()));
        assertEquals(5406, Math.round(ead(EX3).ead()));
        assertEquals(936, Math.round(ead(cat(EX1, EX2)).ead()));
        assertEquals(1879, Math.round(SaCcr.ead(cat(EX1, EX3), 200, WEEKLY, true).ead()));
    }

    @Test
    void cre99Intermediates() {
        SaCcr.Result r1 = ead(EX1);
        List<SaCcr.TradeRow> t = r1.trades();
        assertEquals(78694, Math.round(t.get(0).adjustedNotional()));
        assertEquals(36254, Math.round(t.get(1).adjustedNotional()));
        assertEquals(37428, Math.round(t.get(2).adjustedNotional()));
        assertEquals(-0.2694, Math.round(t.get(2).delta() * 1e4) / 1e4);
        assertEquals(-10083, Math.round(t.get(2).effectiveNotional()));
        assertEquals(60.0, r1.rc());
        assertEquals("EUR", r1.hedgingSets().get(0).key());
        assertEquals(29635, Math.round(r1.hedgingSets().get(1).addon() * 100));
        SaCcr.Result r2 = ead(EX2);
        assertEquals(282, Math.round(r2.addonAggregate()));
        assertEquals(965, Math.round(r2.multiplier() * 1000));
        SaCcr.Result r3 = ead(EX3);
        assertEquals(8660, Math.round(r3.trades().get(0).effectiveNotional()));
        assertEquals("ENERGY", r3.hedgingSets().get(0).key());
        assertEquals(2041, Math.round(r3.hedgingSets().get(0).addon()));
        SaCcr.Result r5 = SaCcr.ead(cat(EX1, EX3), 200, WEEKLY, true);
        assertEquals(14L, r5.mporDays());
        assertEquals(0.0, r5.rc());
        assertEquals(80.0, r5.v());
        assertEquals(-7099, Math.round(r5.trades().get(4).effectiveNotional())); // KR-31: printed -7,100
        assertEquals(1401, Math.round(r5.addonAggregate()));
        assertEquals(958, Math.round(r5.multiplier() * 1000));
        assertFalse(r5.capped());
        assertTrue(r5.eadUnmargined() > r5.ead());
        assertTrue(r5.margined());
    }

    @Test
    void sharedTableEqualsSpecFile() throws IOException {
        Map<?, ?> doc = (Map<?, ?>) Json.parse(Files.readString(
                Path.of("..", "specifications", "06-risk", "sa-ccr-parameters.json"))).value();
        List<?> rows = (List<?>) doc.get("table2");
        assertEquals(SaCcrTables.CLASS.length, rows.size());
        for (int i = 0; i < rows.size(); i++) {
            Map<?, ?> r = (Map<?, ?>) rows.get(i);
            assertEquals(r.get("asset_class"), SaCcrTables.CLASS[i]);
            assertEquals(r.get("subclass") == null ? "" : r.get("subclass"), SaCcrTables.SUBCLASS[i]);
            assertEquals(((Json.Number) r.get("supervisory_factor")).value(), SaCcrTables.FACTOR[i]);
            assertEquals(((Json.Number) r.get("option_volatility")).value(), SaCcrTables.OPTION_VOLATILITY[i]);
            Object c = r.get("correlation");
            assertEquals(c == null ? Double.NaN : ((Json.Number) c).value(), SaCcrTables.CORRELATION[i]);
            assertEquals(r.get("hedging_set"), SaCcrTables.HEDGING_SET[i]);
        }
        assertEquals(((Json.Number) doc.get("alpha")).value(), SaCcrTables.ALPHA);
        assertEquals(((Json.Number) doc.get("multiplier_floor")).value(), SaCcrTables.MULTIPLIER_FLOOR);
    }

    @Test
    void multiplierEdgesAndOverflow() {
        // KR-36: V - C >= 0 is exactly 1 without the exponential; a tiny add-on would overflow exp.
        assertEquals(1.0, SaCcr.multiplier(1e6, Double.MIN_VALUE));
        assertEquals(1.0, SaCcr.multiplier(0.0, 0.0));
        assertEquals(0.05, SaCcr.multiplier(-1.0, 0.0));
        assertEquals(0.05, SaCcr.multiplier(-1e6, Double.MIN_VALUE));
        double m = SaCcr.multiplier(-10.0, 100.0);
        assertTrue(m > 0.05 && m < 1.0);
        // the same through ead: V > 0 and an add-on near the smallest subnormal
        SaCcr.Result r = ead(List.of(fx("a", Double.MIN_VALUE, 5, 1, "LONG", "EURUSD")));
        assertEquals(1.0, r.multiplier());
        assertEquals(7.0, r.ead(), 1e-12);
    }

    @Test
    void rulesAndEdges() {
        assertEquals(10.0 / 250, SaCcr.supervisoryDuration(0, 0));
        assertEquals(1, SaCcr.bucket(0.5));
        assertEquals(2, SaCcr.bucket(1));
        assertEquals(2, SaCcr.bucket(5));
        assertEquals(3, SaCcr.bucket(5.0001));
        SaCcr.Margin daily = new SaCcr.Margin(0, 0, 0, 1, null, false, false);
        assertEquals(10, SaCcr.mporFloor(daily, 1));
        assertEquals(20, SaCcr.mporFloor(daily, 5001));
        assertEquals(40, SaCcr.mporFloor(new SaCcr.Margin(0, 0, 0, 1, null, true, true), 1));
        assertEquals(14, SaCcr.mporFloor(WEEKLY, 5000));
        SaCcr.Trade cdo = new SaCcr.Trade("c", "CREDIT", 100, 0, 1, "CDO", "SOLD", "NORMAL", 0.0, 1.0, null, "T", "IG",
                null, null, null, null, 0.0, 0.03, 0.07);
        assertEquals(-15 / (1.42 * 1.98), SaCcr.supervisoryDelta(cdo), 1e-15);
        SaCcr.Trade call = new SaCcr.Trade("o", "FX", 100, 0, 1, "OPTION", "SOLD", "NORMAL", null, null, "EURUSD",
                null, null, "CALL", 1.1, 1.0, 0.5, 0.0, null, null);
        double d1 = (Math.log(1.1) + 0.5 * 0.15 * 0.15 * 0.5) / (0.15 * Math.sqrt(0.5));
        assertEquals(-org.quantforge.core.Normal.cdf(d1), SaCcr.supervisoryDelta(call), 1e-15);
        // no-offset IR formula, basis and volatility scaling
        SaCcr.Result off = SaCcr.ead(EX1, 0, null, false);
        assertTrue(off.addon().get("IR") > ead(EX1).addon().get("IR"));
        SaCcr.Trade base = named("e", "EQUITY", 100, 0, 1, "LONG", "X", "SINGLE");
        double a0 = ead(List.of(base)).addonAggregate();
        SaCcr.Trade basis = new SaCcr.Trade("e", "EQUITY", 100, 0, 1, "LINEAR", "LONG", "BASIS", null, null, "B1", "X",
                "SINGLE", null, null, null, null, 0.0, null, null);
        SaCcr.Trade vol = new SaCcr.Trade("e", "EQUITY", 100, 0, 1, "LINEAR", "LONG", "VOLATILITY", null, null, "V1",
                "X", "SINGLE", null, null, null, null, 0.0, null, null);
        assertEquals(0.5 * a0, ead(List.of(basis)).addonAggregate(), 1e-12);
        assertEquals(5 * a0, ead(List.of(vol)).addonAggregate(), 1e-12);
        // capped margined EAD, own MPOR estimate above the floor
        SaCcr.Result capped = SaCcr.ead(List.of(fx("a", 100, 0, 1, "LONG", "EURUSD")), 0,
                new SaCcr.Margin(1e6, 0, 0, 1, 15L, false, false), true);
        assertTrue(capped.capped());
        assertEquals(15L, capped.mporDays());
        assertEquals(capped.eadUnmargined(), capped.ead());
        SaCcr.Result unm = ead(List.of(fx("a", 100, 0, 1, "LONG", "EURUSD")));
        assertNull(unm.mporDays());
        assertNull(unm.eadUnmargined());
        assertNull(unm.trades().get(0).supervisoryDuration());
        // code-point order: a supplementary character sorts after U+FFFF-range BMP text
        assertTrue(SaCcr.codePointCompare("～", "😀") < 0);
        assertTrue(SaCcr.codePointCompare("a", "ab") < 0);
        assertEquals(0, SaCcr.codePointCompare("ab", "ab"));
    }

    /**
     * KA-A3 (ruling KR-236): two equity variance swaps on two single names, long and short, labelled V1 and V2, form
     * one hedging set (CRE52.47). SF = 32% x 5 = 1.6, a = +-160, rho = 0.5: sqrt(0.75 x (160^2 + 160^2)) =
     * sqrt(38,400). A volatility trade other than IR or FX needs no hedging_set.
     */
    @Test
    void equityVolatilityTradesFormOneHedgingSet() {
        SaCcr.Trade v1 = new SaCcr.Trade("v1", "EQUITY", 100, 0, 1, "LINEAR", "LONG", "VOLATILITY", null, null, "V1",
                "X", "SINGLE", null, null, null, null, 0.0, null, null);
        SaCcr.Trade v2 = new SaCcr.Trade("v2", "EQUITY", 100, 0, 1, "LINEAR", "SHORT", "VOLATILITY", null, null, "V2",
                "Y", "SINGLE", null, null, null, null, 0.0, null, null);
        SaCcr.Result r = ead(List.of(v1, v2));
        assertEquals(Math.sqrt(38_400.0), r.addon().get("EQUITY"), 1e-15 * Math.sqrt(38_400.0));
        assertEquals(1, r.hedgingSets().size());
        assertEquals("VOLATILITY", r.hedgingSets().get(0).treatment());
        assertEquals("", r.hedgingSets().get(0).key());
        SaCcr.Trade unlabelled = new SaCcr.Trade("v3", "EQUITY", 100, 0, 1, "LINEAR", "LONG", "VOLATILITY", null,
                null, null, "X", "SINGLE", null, null, null, null, 0.0, null, null);
        assertEquals(r.addon().get("EQUITY"), ead(List.of(unlabelled, v2)).addon().get("EQUITY"));
        // the one-entity-two-subclasses check uses the same key: X under V1 and V2 is one entity
        SaCcr.Trade xIndex = new SaCcr.Trade("v4", "EQUITY", 100, 0, 1, "LINEAR", "LONG", "VOLATILITY", null, null,
                "V2", "X", "INDEX", null, null, null, null, 0.0, null, null);
        fails("E_INPUT", "subclass", List.of(v1, xIndex), null);
    }

    private static void fails(String code, String field, List<SaCcr.Trade> t, SaCcr.Margin m) {
        QfError e = assertThrows(QfError.class, () -> SaCcr.ead(t, 0, m, true));
        assertEquals(code, e.code());
        assertEquals(field, e.field());
    }

    private static SaCcr.Trade with(SaCcr.Trade t, String kind, String pos, Double a, Double d) {
        return new SaCcr.Trade(t.id(), t.assetClass(), t.notional(), t.marketValue(), t.maturity(), kind, pos,
                t.treatment(), t.start(), t.end(), t.hedgingSet(), t.entity(), t.subclass(), t.optionType(),
                t.underlyingPrice(), t.strike(), t.exercise(), t.shift(), a, d);
    }

    @Test
    void errors() {
        SaCcr.Trade ok = fx("a", 100, 0, 1, "LONG", "EURUSD");
        fails("E_INPUT", "trades", List.of(), null);
        fails("E_INPUT", "id", List.of(ok, ok), null);
        fails("E_INPUT", "start", List.of(new SaCcr.Trade("a", "IR", 1, 0, 1, "LINEAR", "LONG", "NORMAL", null, null,
                "USD", null, null, null, null, null, null, 0.0, null, null)), null);
        fails("E_INPUT", "hedging_set", List.of(fx("a", 100, 0, 1, "LONG", null)), null);
        fails("E_INPUT", "entity", List.of(named("a", "EQUITY", 1, 0, 1, "LONG", null, "SINGLE")), null);
        fails("E_INPUT", "subclass", List.of(named("a", "EQUITY", 1, 0, 1, "LONG", "X", "IG")), null);
        fails("E_INPUT", "subclass", List.of(new SaCcr.Trade("a", "FX", 1, 0, 1, "LINEAR", "LONG", "NORMAL", null,
                null, "EURUSD", null, "IG", null, null, null, null, 0.0, null, null)), null);
        fails("E_INPUT", "subclass", List.of(named("a", "EQUITY", 1, 0, 1, "LONG", "X", "SINGLE"),
                named("b", "EQUITY", 1, 0, 1, "LONG", "X", "INDEX")), null);
        fails("E_INPUT", "position", List.of(fx("a", 100, 0, 1, "BOUGHT", "EURUSD")), null);
        fails("E_INPUT", "option_type", List.of(with(ok, "OPTION", "BOUGHT", null, null)), null);
        fails("E_INPUT", "kind", List.of(with(ok, "CDO", "BOUGHT", 0.1, 0.2)), null);
        SaCcr.Trade credit = named("c", "CREDIT", 1, 0, 1, "LONG", "T", "IG");
        fails("E_INPUT", "attachment", List.of(with(credit, "CDO", "BOUGHT", null, 0.2)), null);
        fails("E_DOMAIN", "notional", List.of(fx("a", 0, 0, 1, "LONG", "EURUSD")), null);
        fails("E_DOMAIN", "maturity", List.of(fx("a", 1, 0, -1, "LONG", "EURUSD")), null);
        fails("E_DOMAIN", "start", List.of(ir("a", 1, 0, 1, "LONG", 2, 1, "USD")), null);
        fails("E_DOMAIN", "start", List.of(ir("a", 1, 0, 1, "LONG", -1, 1, "USD")), null);
        SaCcr.Trade opt = new SaCcr.Trade("o", "FX", 100, 0, 1, "OPTION", "BOUGHT", "NORMAL", null, null, "EURUSD",
                null, null, "CALL", 1.0, 0.0, 1.0, 0.0, null, null);
        fails("E_DOMAIN", "strike", List.of(opt), null);
        fails("E_DOMAIN", "strike", List.of(new SaCcr.Trade("o", "FX", 100, 0, 1, "OPTION", "BOUGHT", "NORMAL", null,
                null, "EURUSD", null, null, "CALL", 0.0, 1.0, 1.0, 0.0, null, null)), null);
        fails("E_DOMAIN", "exercise", List.of(new SaCcr.Trade("o", "FX", 100, 0, 1, "OPTION", "BOUGHT", "NORMAL", null,
                null, "EURUSD", null, null, "CALL", 1.0, 1.0, 0.0, 0.0, null, null)), null);
        fails("E_DOMAIN", "attachment", List.of(with(credit, "CDO", "BOUGHT", 0.3, 0.3)), null);
        fails("E_DOMAIN", "attachment", List.of(with(credit, "CDO", "BOUGHT", -0.1, 0.3)), null);
        fails("E_DOMAIN", "attachment", List.of(with(credit, "CDO", "BOUGHT", 0.1, 1.3)), null);
        fails("E_DOMAIN", "threshold", List.of(ok), new SaCcr.Margin(-1, 0, 0, 1, null, false, false));
        fails("E_DOMAIN", "mta", List.of(ok), new SaCcr.Margin(0, -1, 0, 1, null, false, false));
        fails("E_DOMAIN", "remargin_days", List.of(ok), new SaCcr.Margin(0, 0, 0, 0, null, false, false));
        fails("E_DOMAIN", "mpor_days", List.of(ok), new SaCcr.Margin(0, 0, 0, 1, 0L, false, false));
        // HR-122: a structural error on a later trade outranks a domain error on an earlier one
        fails("E_INPUT", "hedging_set", List.of(fx("a", -5, 0, 1, "LONG", "EURUSD"), fx("b", 1, 0, 1, "LONG", null)),
                null);
    }

    private static final String[] SUBS_CREDIT = {"AAA", "AA", "A", "BBB", "BB", "B", "CCC", "IG", "SG"};
    private static final String[] SUBS_EQUITY = {"SINGLE", "INDEX"};
    private static final String[] SUBS_CMDTY = {"ELECTRICITY", "OIL_GAS", "METALS", "AGRICULTURAL", "OTHER"};

    static List<SaCcr.Trade> portfolio(Random r, double scale) {
        List<SaCcr.Trade> out = new ArrayList<>();
        int count = 1 + r.nextInt(6);
        for (int k = 0; k < count; k++) {
            String cls = SaCcr.CLASSES.get(r.nextInt(5));
            String pos = r.nextBoolean() ? "LONG" : "SHORT";
            double n = (1.0 + r.nextDouble() * 1e7) * scale;
            double v = -1e5 + 2e5 * r.nextDouble();
            double m = 0.01 + 30 * r.nextDouble();
            String id = Integer.toString(k);
            switch (cls) {
                case "IR" -> {
                    double s = 5 * r.nextDouble();
                    out.add(ir(id, n, v, m, pos, s, s + m, r.nextBoolean() ? "USD" : "EUR"));
                }
                case "FX" -> out.add(fx(id, n, v, m, pos, r.nextBoolean() ? "EURUSD" : "USDJPY"));
                default -> {
                    String[] subs = cls.equals("CREDIT") ? SUBS_CREDIT : cls.equals("EQUITY") ? SUBS_EQUITY : SUBS_CMDTY;
                    String sub = subs[r.nextInt(subs.length)];
                    out.add(named(id, cls, n, v, m, pos, sub + "-" + r.nextInt(3), sub));
                }
            }
        }
        return out;
    }

    /** Seeded properties (spec "Acceptance"): multiplier range, netting bound, monotone in notional and collateral. */
    @Test
    void properties() {
        for (int trial = 0; trial < 300; trial++) {
            long seed = 1000 + trial;
            List<SaCcr.Trade> t = portfolio(new Random(seed), 1.0);
            List<SaCcr.Trade> bigger = portfolio(new Random(seed), 1.5);
            double c = -1e5 + 2e5 * new Random(seed * 7).nextDouble();
            SaCcr.Result r = SaCcr.ead(t, c, null, true);
            assertTrue(r.multiplier() >= 0.05 && r.multiplier() <= 1.0);
            double alone = 0.0;
            for (SaCcr.Trade x : t) {
                alone += ead(List.of(x)).addonAggregate();
            }
            assertTrue(r.addonAggregate() <= alone * (1 + 1e-12) + 1e-9);
            assertTrue(SaCcr.ead(bigger, c, null, true).ead() >= r.ead() * (1 - 1e-12));
            assertTrue(SaCcr.ead(t, c + 100.0, null, true).ead() <= r.ead() * (1 + 1e-12) + 1e-9);
        }
        // multiplier strictly inside (0.05, 1] wherever exp does not underflow
        Random r = new Random(5);
        for (int i = 0; i < 2000; i++) {
            double addon = Math.exp(-5 + 15 * r.nextDouble());
            double vc = -addon * 30 * r.nextDouble();
            double m = SaCcr.multiplier(vc, addon);
            assertTrue(m > 0.05 && m <= 1.0, () -> vc + " " + addon);
        }
    }
}
