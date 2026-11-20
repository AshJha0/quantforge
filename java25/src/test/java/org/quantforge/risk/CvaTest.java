package org.quantforge.risk;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.function.Supplier;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;

/**
 * CVA capital (K-8g): unit tests and seeded properties mirroring python/tests/test_stage_k_w2b.py (BA-CVA and SA-CVA
 * parts), plus the reuse of the FRTB sensitivity-based aggregation. The golden replay is StageKW2bCliTest.
 */
class CvaTest {
    private static Cva.Counterparty cp(String id, double ead, double m) {
        return new Cva.Counterparty(id, "financials", "IG", List.of(new Cva.NettingSet(ead, m, false)));
    }

    private static boolean close(double a, double b, double rel) {
        return Math.abs(a - b) <= rel * Math.max(Math.max(Math.abs(a), Math.abs(b)), 1.0);
    }

    private static QfError err(Supplier<?> f) {
        return assertThrows(QfError.class, f::get);
    }

    @Test
    void discountFactor() {
        assertEquals(0.8847968677143805, Cva.discountFactor(5, false));
        assertEquals(1.0, Cva.discountFactor(2.5, true));
        assertEquals("E_DOMAIN", err(() -> Cva.discountFactor(0.0, false)).code());
    }

    @Test
    void baCoreEnums() {
        List<Cva.Counterparty> one = List.of(cp("A", 1, 1));
        String[][] cases = {{"version"}, {"sector"}, {"quality"}, {"relation"}, {"sector"}, {"quality"}, {"sector"},
            {"quality"}};
        List<Supplier<?>> calls = List.of(
                () -> Cva.baCva(one, "BASIC", List.of(), List.of()),
                () -> Cva.baCva(List.of(new Cva.Counterparty("A", "space", "IG", List.of())), "FULL", List.of(),
                        List.of()),
                () -> Cva.baCva(List.of(new Cva.Counterparty("A", "other", "AAA", List.of())), "FULL", List.of(),
                        List.of()),
                () -> Cva.baCva(one, "FULL", List.of(new Cva.SingleNameHedge("A", "COUSIN", "other", "IG", 1, 1)),
                        List.of()),
                () -> Cva.baCva(one, "FULL", List.of(new Cva.SingleNameHedge("A", "DIRECT", "space", "IG", 1, 1)),
                        List.of()),
                () -> Cva.baCva(one, "FULL", List.of(new Cva.SingleNameHedge("A", "DIRECT", "other", "AAA", 1, 1)),
                        List.of()),
                () -> Cva.baCva(one, "FULL", List.of(), List.of(new Cva.IndexHedge(1, 1,
                        List.of(new Cva.Constituent("space", "IG", 1))))),
                () -> Cva.baCva(one, "FULL", List.of(), List.of(new Cva.IndexHedge(1, 1,
                        List.of(new Cva.Constituent("other", "AAA", 1))))));
        for (int i = 0; i < calls.size(); i++) {
            QfError e = err(calls.get(i));
            assertEquals("E_SCHEMA", e.code());
            assertEquals(cases[i][0], e.field());
        }
    }

    @Test
    void baStructureAndDomain() {
        List<Cva.Counterparty> one = List.of(cp("A", 1, 1));
        Cva.SingleNameHedge h = new Cva.SingleNameHedge("A", "DIRECT", "other", "IG", 1, 1);
        assertEquals("E_INPUT", err(() -> Cva.baCva(List.of(cp("A", 1, 1), cp("A", 1, 1)), "REDUCED", List.of(),
                List.of())).code());
        assertEquals("E_INPUT", err(() -> Cva.baCva(one, "REDUCED", List.of(h), List.of())).code());
        assertEquals("E_INPUT", err(() -> Cva.baCva(one, "REDUCED", List.of(), List.of(new Cva.IndexHedge(1, 1,
                List.of())))).code());
        assertEquals("E_INPUT", err(() -> Cva.baCva(one, "FULL", List.of(new Cva.SingleNameHedge("Z", "DIRECT",
                "other", "IG", 1, 1)), List.of())).code());
        assertEquals("E_DOMAIN", err(() -> Cva.baCva(List.of(cp("A", -1, 1)), "REDUCED", List.of(), List.of()))
                .code());
        assertEquals("E_DOMAIN", err(() -> Cva.baCva(List.of(cp("A", 1, 0)), "REDUCED", List.of(), List.of()))
                .code());
        assertEquals("E_DOMAIN", err(() -> Cva.baCva(one, "FULL", List.of(new Cva.SingleNameHedge("A", "DIRECT",
                "other", "IG", 0, 1)), List.of())).code());
        assertEquals("E_DOMAIN", err(() -> Cva.baCva(one, "FULL", List.of(new Cva.SingleNameHedge("A", "DIRECT",
                "other", "IG", 1, -1)), List.of())).code());
        Cva.Constituent whole = new Cva.Constituent("other", "IG", 1);
        assertEquals("E_DOMAIN", err(() -> Cva.baCva(one, "FULL", List.of(), List.of(new Cva.IndexHedge(0, 1,
                List.of(whole))))).code());
        assertEquals("E_DOMAIN", err(() -> Cva.baCva(one, "FULL", List.of(), List.of(new Cva.IndexHedge(1, -1,
                List.of(whole))))).code());
        assertEquals("E_DOMAIN", err(() -> Cva.baCva(one, "FULL", List.of(), List.of(new Cva.IndexHedge(1, 1,
                List.of(new Cva.Constituent("other", "IG", -0.5), new Cva.Constituent("other", "IG", 1.5))))))
                .code());
        assertEquals("E_DOMAIN", err(() -> Cva.baCva(one, "FULL", List.of(), List.of(new Cva.IndexHedge(1, 1,
                List.of(new Cva.Constituent("other", "IG", 0.5)))))).code());
        // structural before domain: a duplicate id with a negative EAD is E_INPUT
        assertEquals("E_INPUT", err(() -> Cva.baCva(List.of(cp("A", -1, 1), cp("A", 1, 1)), "REDUCED", List.of(),
                List.of())).code());
    }

    @Test
    void reducedOutputsAndFullFields() {
        Cva.BaResult red = Cva.baCva(List.of(cp("A", 100, 5)), "REDUCED", List.of(), List.of());
        assertNull(red.ih());
        assertNull(red.kFull());
        assertNull(red.counterparties().get(0).snh());
        assertEquals(Cva.LABEL, red.label());
        assertEquals(12.5 * red.capital(), red.rwa());
        Cva.BaResult none = Cva.baCva(List.of(new Cva.Counterparty("A", "other", "IG", List.of())), "REDUCED",
                List.of(), List.of());
        assertEquals(0.0, none.counterparties().get(0).scva()); // KR-313
    }

    // --- seeded BA-CVA properties (Python: Hypothesis) ---------------------------------------------------------

    private static List<Cva.Counterparty> counterparties(Random r) {
        List<Cva.Counterparty> out = new ArrayList<>();
        int n = 1 + r.nextInt(5);
        for (int i = 0; i < n; i++) {
            List<Cva.NettingSet> ns = new ArrayList<>();
            int k = 1 + r.nextInt(3);
            for (int j = 0; j < k; j++) {
                ns.add(new Cva.NettingSet(r.nextDouble() * 1e9, 0.01 + r.nextDouble() * 39.99, r.nextBoolean()));
            }
            out.add(new Cva.Counterparty("C" + i, Cva.SECTORS.get(r.nextInt(Cva.SECTORS.size())),
                    Cva.QUALITIES.get(r.nextInt(2)), ns));
        }
        return out;
    }

    @Property(tries = 200)
    void baMonotoneInExposure(@ForAll long seed) {
        Random r = new Random(seed);
        List<Cva.Counterparty> cps = counterparties(r);
        int who = r.nextInt(cps.size());
        double factor = 1.0 + 9.0 * r.nextDouble();
        Cva.Counterparty c = cps.get(who);
        List<Cva.NettingSet> grown = new ArrayList<>();
        for (Cva.NettingSet n : c.nettingSets()) {
            grown.add(new Cva.NettingSet(n.ead() * factor, n.m(), n.imm()));
        }
        List<Cva.Counterparty> more = new ArrayList<>(cps);
        more.set(who, new Cva.Counterparty(c.id(), c.sector(), c.quality(), grown));
        double base = Cva.baCva(cps, "REDUCED", List.of(), List.of()).capital();
        assertTrue(Cva.baCva(more, "REDUCED", List.of(), List.of()).capital() >= base * (1 - 1e-12));
    }

    @Property(tries = 200)
    void reducedEqualsFullWithoutHedges(@ForAll long seed) {
        List<Cva.Counterparty> cps = counterparties(new Random(seed));
        Cva.BaResult red = Cva.baCva(cps, "REDUCED", List.of(), List.of());
        Cva.BaResult full = Cva.baCva(cps, "FULL", List.of(), List.of());
        assertTrue(close(full.kHedged(), red.kReduced(), 1e-12));
        assertTrue(close(full.capital(), red.capital(), 1e-12));
        assertEquals(0.0, full.ih());
        if (cps.size() == 1) {
            assertTrue(close(red.kReduced(), red.counterparties().get(0).scva(), 1e-12));
        }
    }

    @Property(tries = 200)
    void fullNeverBelowBetaFloor(@ForAll long seed) {
        Random r = new Random(seed);
        List<Cva.Counterparty> cps = counterparties(r);
        List<String> rel = new ArrayList<>(Cva.RELATIONS.keySet());
        List<Cva.SingleNameHedge> single = new ArrayList<>();
        for (int i = r.nextInt(5); i > 0; i--) {
            single.add(new Cva.SingleNameHedge(cps.get(r.nextInt(cps.size())).id(), rel.get(r.nextInt(3)),
                    Cva.SECTORS.get(r.nextInt(Cva.SECTORS.size())), Cva.QUALITIES.get(r.nextInt(2)),
                    0.01 + 39.99 * r.nextDouble(), 1e9 * r.nextDouble()));
        }
        List<Cva.IndexHedge> index = new ArrayList<>();
        for (int i = r.nextInt(3); i > 0; i--) {
            index.add(new Cva.IndexHedge(0.01 + 39.99 * r.nextDouble(), 1e9 * r.nextDouble(), List.of(
                    new Cva.Constituent(Cva.SECTORS.get(r.nextInt(Cva.SECTORS.size())), Cva.QUALITIES.get(
                            r.nextInt(2)), 1.0))));
        }
        Cva.BaResult out = Cva.baCva(cps, "FULL", single, index);
        assertTrue(out.kFull() >= Cva.BETA * out.kReduced() * (1 - 1e-12));
    }

    @Property(tries = 200)
    void directHedgesOneCounterparty(@ForAll long seed) {
        Random r = new Random(seed);
        Cva.Counterparty c = new Cva.Counterparty("C", "other", "IG", List.of(new Cva.NettingSet(
                1e9 * r.nextDouble(), 0.01 + 39.99 * r.nextDouble(), r.nextBoolean())));
        List<Cva.SingleNameHedge> single = new ArrayList<>();
        for (int i = r.nextInt(4); i > 0; i--) {
            single.add(new Cva.SingleNameHedge("C", "DIRECT", "other", "IG", 0.01 + 39.99 * r.nextDouble(),
                    1e9 * r.nextDouble()));
        }
        Cva.BaResult out = Cva.baCva(List.of(c), "FULL", single, List.of());
        Cva.CounterpartyRow row = out.counterparties().get(0);
        assertEquals(0.0, row.hma());
        assertTrue(Math.abs(out.kHedged() - Math.abs(row.scva() - row.snh())) <= 1e-9 * Math.max(1.0, row.scva()));
    }

    // --- SA-CVA ------------------------------------------------------------------------------------------------

    private static Cva.Sensitivity ir(String bucket, String tenor, double c, double h) {
        return new Cva.Sensitivity(bucket, tenor, null, c, h);
    }

    private static Cva.Sensitivity one(String bucket, String factor, double c) {
        return new Cva.Sensitivity(bucket, factor, null, c, 0.0);
    }

    private static Cva.CreditFactor credit(String name, String tenor, String quality) {
        return new Cva.CreditFactor(name, tenor, quality, null, null, null);
    }

    private static String saCode(Map<String, List<Cva.Sensitivity>> classes, String rep, double m) {
        return err(() -> Cva.saCva(classes, rep, m)).code();
    }

    @Test
    void saCoreSchemaChecks() {
        assertEquals("E_SCHEMA", saCode(Map.of("IR.GAMMA", List.of()), "USD", 1));
        assertEquals("E_SCHEMA", saCode(Map.of("IR", List.of()), "USD", 1));
        assertEquals("E_SCHEMA", saCode(Map.of("IR.DELTA", List.of(ir("USD", "7Y", 1, 0))), "USD", 1));
        assertEquals("E_SCHEMA", saCode(Map.of("IR.VEGA", List.of(ir("USD", "1Y", 1, 0))), "USD", 1));
        assertEquals("E_SCHEMA", saCode(Map.of("CCS.DELTA", List.of(one("2", "X", 1))), "USD", 1));
        assertEquals("E_SCHEMA", saCode(Map.of("FX.DELTA", List.of(new Cva.Sensitivity("EUR", null,
                credit("X", "1Y", "IG"), 1, 0))), "USD", 1));
        assertEquals("E_SCHEMA", saCode(Map.of("CCS.DELTA", List.of(new Cva.Sensitivity("2", null,
                credit("X", "1Y", "AA"), 1, 0))), "USD", 1));
        assertEquals("E_SCHEMA", saCode(Map.of("CCS.DELTA", List.of(new Cva.Sensitivity("2", null,
                credit("X", "2Y", "IG"), 1, 0))), "USD", 1));
        assertEquals("E_INPUT", saCode(Map.of("CCS.VEGA", List.of()), "USD", 1));
        assertEquals("E_INPUT", saCode(Map.of(), "usd", 1));
        assertEquals("E_DOMAIN", saCode(Map.of("IR.DELTA", List.of(ir("USD", "1Y", 1, 0))), "USD", 0.5));
    }

    @Test
    void saStructuralChecks() {
        assertEquals("E_INPUT", saCode(Map.of("IR.DELTA", List.of(ir("usd", "1Y", 1, 0))), "USD", 1));
        assertEquals("E_INPUT", saCode(Map.of("FX.DELTA", List.of(one("USD", "x", 1))), "USD", 1));
        assertEquals("E_INPUT", saCode(Map.of("IR.DELTA", List.of(ir("USD", "CURVE", 1, 0))), "USD", 1));
        assertEquals("E_INPUT", saCode(Map.of("IR.DELTA", List.of(ir("NOK", "5Y", 1, 0))), "USD", 1));
        assertEquals("E_INPUT", saCode(Map.of("IR.DELTA", List.of(ir("USD", "1Y", 1, 0), ir("USD", "1Y", 2, 0))),
                "USD", 1));
        assertEquals("E_INPUT", saCode(Map.of("CCS.DELTA", List.of(new Cva.Sensitivity("9", null,
                credit("X", "1Y", "IG"), 1, 0))), "USD", 1));
        assertEquals("E_INPUT", saCode(Map.of("CCS.DELTA", List.of(new Cva.Sensitivity("8", null,
                credit("X", "1Y", "IG"), 1, 0))), "USD", 1));
        assertEquals("E_INPUT", saCode(Map.of("CCS.DELTA", List.of(
                new Cva.Sensitivity("2", null, credit("X", "1Y", "IG"), 1, 0),
                new Cva.Sensitivity("2", null, credit("X", "5Y", "HY_NR"), 1, 0))), "USD", 1));
        // KR-312: the same name and tenor under 1a and 1b is one factor of bucket 1 twice
        assertEquals("E_INPUT", saCode(Map.of("CCS.DELTA", List.of(
                new Cva.Sensitivity("1a", null, credit("X", "1Y", "IG"), 1, 0),
                new Cva.Sensitivity("1b", null, credit("X", "1Y", "IG"), 1, 0))), "USD", 1));
        assertEquals("E_INPUT", saCode(Map.of("EQ.DELTA", List.of(one("14", "e", 1))), "USD", 1));
        assertEquals("E_INPUT", saCode(Map.of("COM.VEGA", List.of(one("0", "c", 1))), "USD", 1));
        assertEquals("E_INPUT", saCode(Map.of("RCS.DELTA", List.of(one("1", "a", 1), one("1", "b", 1))), "USD", 1));
    }

    @Test
    void saEmptyAndFlooredFlag() {
        Cva.SaResult out = Cva.saCva(Map.of(), "USD", 1.0);
        assertEquals(0.0, out.total());
        assertTrue(out.classes().isEmpty());
        // KR-62: a correlation form that goes negative is floored at 0 (checked on the shared radicand)
        List<FrtbSbm.Ws> ws = List.of(new FrtbSbm.Ws(0, List.of("a"), 1.0), new FrtbSbm.Ws(0, List.of("b"), -1.0));
        assertTrue(FrtbSbm.bucketRadicand(ws, (a, b) -> 1.5) < 0);
        // R x sum WSH^2 alone keeps K_b positive with offsetting hedges
        Cva.SaResult h = Cva.saCva(Map.of("IR.DELTA", List.of(ir("USD", "1Y", 1e6, 1e6))), "USD", 1.0);
        Cva.BucketRow row = h.classes().get("IR.DELTA").buckets().get(0);
        assertFalse(row.floored());
        assertEquals(0.0, row.sumWs());
        assertTrue(close(row.kB(), Math.sqrt(0.01) * 0.0111 * 1e6, 1e-15));
    }

    private static Map<String, List<Cva.Sensitivity>> irBook(Random r) {
        List<String> ccys = new ArrayList<>(List.of("USD", "EUR", "JPY", "GBP"));
        Collections.shuffle(ccys, r);
        List<Cva.Sensitivity> out = new ArrayList<>();
        for (String ccy : ccys.subList(0, 1 + r.nextInt(3))) {
            List<String> tenors = new ArrayList<>(Cva.IR_TENORS);
            Collections.shuffle(tenors, r);
            for (String t : tenors.subList(0, 1 + r.nextInt(4))) {
                out.add(ir(ccy, t, (2 * r.nextDouble() - 1) * 1e7, (2 * r.nextDouble() - 1) * 1e7));
            }
        }
        return Map.of("IR.DELTA", out);
    }

    @Property(tries = 200)
    void saBucketBoundsAndScaling(@ForAll long seed) {
        Random r = new Random(seed);
        Map<String, List<Cva.Sensitivity>> book = irBook(r);
        double c = 0.0;
        while (Math.abs(c) <= 1e-3) {
            c = 10 * r.nextDouble() - 5;
        }
        Cva.SaResult out = Cva.saCva(book, "USD", 1.0);
        for (Cva.BucketRow row : out.classes().get("IR.DELTA").buckets()) {
            double sq = 0.0;
            for (Cva.Sensitivity s : book.get("IR.DELTA")) {
                if (s.bucket().equals(row.bucket())) {
                    double w = Double.parseDouble((String) Cva.table("ir.rw_specified").get(s.factor())) * s.sHdg();
                    sq += w * w;
                }
            }
            assertTrue(row.kB() >= Math.sqrt(Cva.R_HEDGE * sq) * (1 - 1e-12));
            assertTrue(-row.kB() <= row.sB() && row.sB() <= row.kB());
            assertFalse(row.floored());
        }
        List<Cva.Sensitivity> scaled = new ArrayList<>();
        for (Cva.Sensitivity s : book.get("IR.DELTA")) {
            scaled.add(ir(s.bucket(), s.factor(), c * s.sCva(), c * s.sHdg()));
        }
        double k1 = out.total();
        double k2 = Cva.saCva(Map.of("IR.DELTA", scaled), "USD", 1.0).total();
        assertTrue(Math.abs(k2 - Math.abs(c) * k1) <= 1e-9 * Math.max(1.0, Math.abs(c) * k1));
    }

    @Property(tries = 200)
    void saOrderInvariance(@ForAll long seed) {
        Random r = new Random(seed);
        Map<String, List<Cva.Sensitivity>> book = irBook(r);
        List<Cva.Sensitivity> items = new ArrayList<>(book.get("IR.DELTA"));
        Collections.shuffle(items, r);
        double a = Cva.saCva(book, "USD", 1.0).total();
        double b = Cva.saCva(Map.of("IR.DELTA", items), "USD", 1.0).total();
        assertTrue(Math.abs(a - b) <= 1e-9 * Math.max(1.0, a));
    }

    /** With no hedge, SA-CVA K_b is the FRTB SBM medium-scenario K_b of the same weighted sensitivities. */
    @Property(tries = 200)
    void saBucketMatchesSbmAggregation(@ForAll long seed) {
        Random r = new Random(seed);
        List<String> tenors = new ArrayList<>(List.of("1Y", "5Y", "10Y"));
        Collections.shuffle(tenors, r);
        List<Cva.Sensitivity> book = new ArrayList<>();
        List<FrtbSbm.Ws> ws = new ArrayList<>();
        for (String t : tenors.subList(0, 1 + r.nextInt(3))) {
            double s = (2 * r.nextDouble() - 1) * 1e7;
            book.add(ir("USD", t, s, 0.0));
            ws.add(new FrtbSbm.Ws(1, List.of(t), Double.parseDouble((String) Cva.table("ir.rw_specified").get(t)) * s));
        }
        double kCva = Cva.saCva(Map.of("IR.DELTA", book), "USD", 1.0).classes().get("IR.DELTA").buckets().get(0).kB();
        FrtbGirr.Result sbm = FrtbSbm.aggregate(ws, Map.of(1, "USD"), (b, x, y) -> Cva.irRho(x.get(0), y.get(0)),
                (b, c) -> 0.5, java.util.Set.of());
        double kSbm = sbm.scenarios().stream().filter(s -> s.name().equals("medium")).findFirst().orElseThrow()
                .buckets().get(0).k();
        assertEquals(kSbm, kCva, 1e-9 * Math.max(1.0, kSbm));
    }

    @Test
    void saMoreClassesDirect() {
        Map<String, List<Cva.Sensitivity>> book = new LinkedHashMap<>();
        book.put("RCS.DELTA", List.of(one("1", "r", 1e5), one("8", "r", 1e5)));
        book.put("EQ.VEGA", List.of(one("13", "e", 1e3), one("4", "e", 1e3)));
        book.put("COM.DELTA", List.of(one("11", "c", 1e4), one("1", "c", 1e4)));
        book.put("EQ.DELTA", List.of(one("12", "e", 1e4), one("13", "e", 1e4)));
        book.put("CCS.DELTA", List.of(
                new Cva.Sensitivity("8", null, new Cva.CreditFactor("I", "1Y", "IG", null, "CDX", "S1"), 1e5, 0),
                new Cva.Sensitivity("8", null, new Cva.CreditFactor("I", "5Y", "IG", null, "CDX", "S1"), 1e5, 0)));
        Cva.SaResult out = Cva.saCva(book, "USD", 1.0);
        Map<String, Cva.ClassResult> cls = out.classes();
        assertEquals(List.of("CCS.DELTA", "RCS.DELTA", "EQ.DELTA", "EQ.VEGA", "COM.DELTA"),
                new ArrayList<>(cls.keySet())); // KR-316 order
        double w0 = 0.005 * 1e5;
        double w1 = 0.02 * 1e5;
        assertTrue(close(cls.get("RCS.DELTA").k(), Math.sqrt(w0 * w0 + w1 * w1 + 2 * 0.5 * w0 * w1), 1e-12));
        assertTrue(close(cls.get("COM.DELTA").k(), Math.hypot(0.5 * 1e4, 0.3 * 1e4), 1e-12));
        double a = 0.78 * 1e3;
        double b = 1e3;
        assertTrue(close(cls.get("EQ.VEGA").k(), Math.sqrt(a * a + b * b + 2 * 0.45 * a * b), 1e-12));
        a = 0.15 * 1e4;
        b = 0.25 * 1e4;
        assertTrue(close(cls.get("EQ.DELTA").k(), Math.sqrt(a * a + b * b + 2 * 0.75 * a * b), 1e-12));
        double w = 0.015 * 1e5;
        assertTrue(close(cls.get("CCS.DELTA").k(), Math.sqrt(2 * w * w + 2 * 0.9 * w * w), 1e-12));
        // bucket order by (length, text): 4 before 13
        assertEquals("4", cls.get("EQ.VEGA").buckets().get(0).bucket());
    }

    @Test
    void correlationsAndOpenReadings() {
        assertEquals(0.90, Cva.first("0.90 legally related"));
        assertEquals(0.91, Cva.irRho("2Y", "1Y"));
        Cva.CreditFactor a = new Cva.CreditFactor("A", "1Y", "IG", "G", null, null);
        Cva.CreditFactor b = new Cva.CreditFactor("B", "5Y", "HY_NR", "G", null, null);
        Cva.CreditFactor c = new Cva.CreditFactor("C", "1Y", "IG", null, null, null);
        assertEquals(0.90 * 0.90 * 0.80, Cva.ccsRho("2", a, b));
        assertEquals(1.0 * 0.50 * 1.0, Cva.ccsRho("2", a, c));
        Cva.CreditFactor i1 = new Cva.CreditFactor("x", "1Y", "IG", null, "CDX", "S1");
        Cva.CreditFactor i2 = new Cva.CreditFactor("x", "1Y", "IG", null, "CDX", "S2");
        Cva.CreditFactor i3 = new Cva.CreditFactor("x", "1Y", "IG", null, "ITX", "S1");
        assertEquals(0.90, Cva.ccsRho("8", i1, i2));
        assertEquals(0.80, Cva.ccsRho("8", i1, i3));
        assertEquals(0.10, Cva.ccsGamma("1", "2"));
        assertEquals(0.10, Cva.ccsGamma("1a", "2"));
        assertEquals(0.45, Cva.ccsGamma("8", "1"));
        assertEquals(0.75 / 2, Cva.rcsGamma("1", "9")); // rows 0 and 1, quality differs
        assertEquals(0.75, Cva.rcsGamma("16", "17"));
        assertEquals(0.0, Cva.rcsGamma("15", "16"));
        assertEquals(0.15, Cva.eqGamma("1", "10"));
        assertEquals(0.0, Cva.eqGamma("11", "1"));
        assertEquals(0.45, Cva.eqGamma("12", "3"));
        assertEquals(0.75, Cva.eqGamma("13", "12"));
        assertEquals(0.20, Cva.comGamma("1", "2"));
        // the three marked readings, as the Python reference implements them
        assertTrue(Cva.CCS_MERGE_1A_1B);
        assertEquals("1", Cva.ccsAggregationBucket("1a"));
        assertEquals("1", Cva.ccsAggregationBucket("1b"));
        assertEquals("2", Cva.ccsAggregationBucket("2"));
        assertEquals("large_cap", Cva.eqVegaKey(12));
        assertEquals("other", Cva.eqVegaKey(9));
        // Python's built-in sum (compensated) against plain left-to-right addition
        assertEquals(2.0, Cva.pySum(new double[] {1e16, 1.0, 1.0, -1e16}));
        assertEquals(0.0, Cva.pySum(new double[0]));
        assertEquals(1.0, Cva.pySum(new double[] {1.0, 1e100, 1.0, -1e100}) / 2.0);
    }

    @Test
    void irOtherCurrencyAndVega() {
        Cva.SaResult out = Cva.saCva(Map.of("IR.DELTA", List.of(ir("NOK", "CURVE", 1e6, 0), ir("NOK", "inflation",
                1e6, 0)), "IR.VEGA", List.of(ir("USD", "IR_VOL", 1e3, 0), ir("USD", "INFLATION_VOL", 1e3, 0)),
                "FX.VEGA", List.of(one("EUR", "v", 1e3))), "USD", 1.5);
        double w = 0.0158 * 1e6;
        assertTrue(close(out.classes().get("IR.DELTA").k(), 1.5 * Math.sqrt(2 * w * w + 2 * 0.4 * w * w), 1e-12));
        assertTrue(close(out.classes().get("IR.VEGA").k(), 1.5 * Math.sqrt(2e6 + 2 * 0.4 * 1e6), 1e-12));
        assertTrue(close(out.classes().get("FX.VEGA").k(), 1.5 * 1e3, 1e-12));
        assertEquals(1.5, out.mCva());
    }
}
