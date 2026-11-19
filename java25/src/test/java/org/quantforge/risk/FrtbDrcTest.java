package org.quantforge.risk;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Json;
import org.quantforge.core.QfError;

/** FRTB DRC and RRAO (K-8a): the shared tables (KR-50), unit rules mirroring the Python tests, and properties (A3). */
class FrtbDrcTest {
    static final Path TABLES = Path.of("..", "specifications", "tables", "stage_k");

    /** The entries of one shared table, key to value. */
    static Map<String, Object> table(String name) throws IOException {
        Map<?, ?> doc = (Map<?, ?>) Json.parse(Files.readString(TABLES.resolve(name + ".json"))).value();
        Map<String, Object> out = new HashMap<>();
        for (Object e : (List<?>) doc.get("entries")) {
            Map<?, ?> m = (Map<?, ?>) e;
            out.put((String) m.get("key"), m.get("value"));
        }
        return out;
    }

    static double d(Object v) {
        return v instanceof Json.Number n ? n.value() : Double.parseDouble((String) v);
    }

    static String code(Runnable r) {
        return assertThrows(QfError.class, r::run).code();
    }

    static FrtbDrc.Position p(String id, String ob, String sen, double n, double mv, double m) {
        return new FrtbDrc.Position(id, ob, "CORPORATE", sen, n, mv, m, false, true);
    }

    @Test
    void parametersMatchTables() throws IOException {
        Map<String, Object> t = table("mar22_drc");
        assertEquals(d(t.get("lgd.covered_bond")), FrtbDrc.lgd("COVERED"));
        assertEquals(d(t.get("lgd.senior_debt")), FrtbDrc.lgd("SENIOR"));
        assertEquals(d(t.get("lgd.non_senior_debt")), FrtbDrc.lgd("NON_SENIOR"));
        assertEquals(d(t.get("lgd.equity")), FrtbDrc.lgd("EQUITY"));
        Map<String, String> names = Map.of("UNRATED", "Unrated", "DEFAULTED", "Defaulted");
        for (String r : FrtbDrc.RATINGS) {
            assertEquals(d(t.get("rw." + names.getOrDefault(r, r))), FrtbDrc.riskWeight(r), r);
        }
        assertEquals(d(t.get("maturity_weight_floor")), FrtbDrcTables.MATURITY_FLOOR);
        assertEquals(d(t.get("capital_horizon_years")), FrtbDrcTables.CAPITAL_HORIZON);
        assertEquals(d(((List<?>) t.get("cash_equity_maturity_choices")).get(0)), FrtbDrcTables.CASH_EQUITY_SHORT);
        assertEquals(d(t.get("ctp_cross_index_factor")), FrtbDrcTables.CTP_CROSS_FACTOR);
        Map<String, Object> r = table("mar23_rrao");
        assertEquals(d(r.get("rw.exotic_underlying")), FrtbDrcTables.RRAO_EXOTIC);
        assertEquals(d(r.get("rw.other_residual_risk")), FrtbDrcTables.RRAO_OTHER);
        assertEquals(List.of(4, 3, 2, 1), FrtbDrc.SENIORITIES.stream().map(FrtbDrc::rank).toList()); // KR-53
    }

    @Test
    void jtdAndWeightDetails() {
        assertEquals(100, FrtbDrc.grossJtd(new FrtbDrc.Position("a", "X", "CORPORATE", "SENIOR", 100, 100, 5, false,
                false)));
        assertEquals(0, FrtbDrc.grossJtd(p("a", "X", "SENIOR", 0, 0, 5)));
        assertEquals(0, FrtbDrc.grossJtd(p("a", "X", "SENIOR", 100, 10, 5))); // long floored at 0
        assertEquals(0, FrtbDrc.grossJtd(p("a", "X", "SENIOR", -100, -10, 5))); // short capped at 0
        assertEquals(0.25, FrtbDrc.maturityWeight(0.1));
        assertEquals(0.6, FrtbDrc.maturityWeight(0.6));
        assertEquals(1, FrtbDrc.maturityWeight(3));
    }

    private static double[] rv(double rank, double v) {
        return new double[] {rank, v};
    }

    @Test
    void offsetGreedyKr53() {
        // a junior short is served after the senior one, so the senior short gets the covered long
        assertArrayEquals(new double[] {0, 0},
                FrtbDrc.offset(List.of(rv(4, 10), rv(1, 10)), List.of(rv(1, -10), rv(4, -10))));
        assertArrayEquals(new double[] {10, -5}, FrtbDrc.offset(List.of(rv(1, 10)), List.of(rv(3, -5))));
        assertArrayEquals(new double[] {6, 0}, FrtbDrc.offset(List.of(rv(3, 10)), List.of(rv(1, -4))));
        assertArrayEquals(new double[] {0, 0}, FrtbDrc.offset(List.of(), List.of()));
    }

    @Test
    void nonsecBucketsAndErrors() {
        FrtbDrc.NonsecResult out = FrtbDrc.drcNonsec(List.of(p("z", "Z", "SENIOR", 0, 0, 5),
                p("s", "S", "SENIOR", -10, -10, 5)), Map.of("Z", "A", "S", "B"));
        assertEquals(0.0, out.buckets().get(0).hbr());
        out = FrtbDrc.drcNonsec(List.of(p("z", "Z", "SENIOR", 0, 0, 5)), Map.of("Z", "A"));
        assertEquals(new FrtbDrc.BucketRow("CORPORATE", null, 0, 0, 0), out.buckets().get(0));
        List<FrtbDrc.Position> big = new ArrayList<>();
        for (int k = 0; k <= FrtbDrc.MAX_POSITIONS; k++) {
            big.add(p(Integer.toString(k), "X", "SENIOR", 1, 1, 5));
        }
        assertEquals("E_LIMIT", code(() -> FrtbDrc.drcNonsec(big, Map.of("X", "A"))));
        // structural before domain, over every position (KR-67)
        assertEquals("E_INPUT", code(() -> FrtbDrc.drcNonsec(List.of(p("a", "X", "SENIOR", 1, 1, -1),
                p("b", "Y", "SENIOR", 1, 1, 1)), Map.of("X", "A"))));
        // code-point order of ids and obligors (KR-114): U+FF5E sorts before U+1F600, UTF-16 order would not
        out = FrtbDrc.drcNonsec(List.of(p("😀", "😀", "SENIOR", 1, 1, 5),
                p("～", "～", "SENIOR", 1, 1, 5)), Map.of("😀", "A", "～", "A"));
        assertEquals("～", out.positions().get(0).id());
        assertEquals("～", out.obligors().get(0).obligor());
        assertTrue(FrtbDrc.CODE_POINT.compare("ab", "a") > 0);
    }

    @Test
    void secAndCtpDetails() {
        List<FrtbDrc.SecPosition> s = List.of(new FrtbDrc.SecPosition("a", "B1", "P", "T", 10, 0.5, 0.2),
                new FrtbDrc.SecPosition("b", "B1", "P", "T", -4, 0.5, 0.2));
        assertEquals(0.2 * 3, FrtbDrc.drcSecNonctp(s).buckets().get(0).wtdLong(), 1e-15);
        assertEquals(0, FrtbDrc.drcSecNonctp(List.of(new FrtbDrc.SecPosition("a", "B1", "P", "T", -4, 2, 0.2))).drc());
        assertNull(FrtbDrc.drcCtp(List.of(), null).hbrCtp());
        List<FrtbDrc.CtpPosition> c = List.of(new FrtbDrc.CtpPosition("a", "I", "S", "T", 100, 2, 0.1),
                new FrtbDrc.CtpPosition("b", "I", "S", "T", -40, 2, 0.1));
        FrtbDrc.CtpResult out = FrtbDrc.drcCtp(c, null);
        assertEquals(1.0, out.hbrCtp());
        assertEquals(6.0, out.drc(), 1e-12);
        // two indices, one net short: DRC_b of the short index is negative and enters at half (MAR22.45)
        out = FrtbDrc.drcCtp(List.of(new FrtbDrc.CtpPosition("a", "I", "S", "T", 100, 2, 0.1),
                new FrtbDrc.CtpPosition("b", "J", "S", "T", -40, 2, 0.1)), null);
        assertEquals(10 - 100.0 / 140 * 4 * 0.5, out.drc(), 1e-12);
        assertEquals(0.5, FrtbDrc.ctpTotal(new double[] {-5, 3}), 1e-15);
        assertEquals("E_INPUT", code(() -> FrtbDrc.drcCtp(null, null)));
        assertEquals("E_LIMIT", code(() -> FrtbDrc.drcCtp(null, new double[FrtbDrc.MAX_POSITIONS + 1])));
        assertEquals("E_LIMIT", code(() -> FrtbDrc.drcCtp(Collections.nCopies(FrtbDrc.MAX_POSITIONS + 1,
                c.get(0)), null)));
        assertEquals("E_LIMIT", code(() -> FrtbDrc.drcSecNonctp(Collections.nCopies(FrtbDrc.MAX_POSITIONS + 1,
                s.get(0)))));
        assertEquals("E_DOMAIN", code(() -> FrtbDrc.drcSecNonctp(List.of(new FrtbDrc.SecPosition("a", "B", "P", "T",
                1, 1, 13)))));
    }

    @Test
    void rraoDetails() {
        FrtbDrc.RraoResult out = FrtbDrc.rrao(List.of(new FrtbDrc.Instrument("a", 100, "EXOTIC", true, false),
                new FrtbDrc.Instrument("b", 100, "OTHER", false, true),
                new FrtbDrc.Instrument("c", 100, "OTHER", true, false),
                new FrtbDrc.Instrument("d", 1000, "OTHER", false, false)));
        assertEquals(List.of(false, true, true, false), out.instruments().stream().map(FrtbDrc.RraoRow::excluded)
                .toList());
        assertEquals(2.0, out.rrao());
        assertEquals("E_LIMIT", code(() -> FrtbDrc.rrao(Collections.nCopies(FrtbDrc.MAX_POSITIONS + 1,
                new FrtbDrc.Instrument("a", 1, "OTHER", false, false)))));
    }

    // ---- properties (spec A3), as python/tests/test_stage_k_w2a.py test_drc_properties -------------------------

    private static final String[] OBLIGORS = {"A", "B", "C"};
    private static final Map<String, String> RATING = Map.of("A", "BBB", "B", "BB", "C", "AA");
    private static final Map<String, String> BUCKET = Map.of("A", "CORPORATE", "B", "CORPORATE", "C", "SOVEREIGN");
    private static final double[] MATURITIES = {0.1, 0.25, 0.5, 0.9, 1.0, 3.0};

    private static List<FrtbDrc.Position> book(Random rnd, double scale) {
        int size = 1 + rnd.nextInt(12);
        List<FrtbDrc.Position> out = new ArrayList<>();
        for (int k = 0; k < size; k++) {
            String o = OBLIGORS[rnd.nextInt(3)];
            String sen = FrtbDrc.SENIORITIES.get(rnd.nextInt(4));
            double n = rnd.nextInt(2001) - 1000;
            double mv = rnd.nextInt(2001) - 1000;
            double m = MATURITIES[rnd.nextInt(MATURITIES.length)];
            if (!(n == 0 && mv != 0)) {
                out.add(new FrtbDrc.Position("p" + k, o, BUCKET.get(o), sen, scale * n, scale * mv, m, false, true));
            }
        }
        if (out.isEmpty()) {
            out.add(new FrtbDrc.Position("p0", "A", "CORPORATE", "SENIOR", 1, 1, 1, false, true));
        }
        return out;
    }

    private static Map<String, Double> byBucket(FrtbDrc.NonsecResult r) {
        Map<String, Double> m = new HashMap<>();
        r.buckets().forEach(b -> m.put(b.bucket(), b.drc()));
        return m;
    }

    @Property(tries = 300)
    void drcProperties(@ForAll long seed) {
        Random rnd = new Random(seed);
        List<FrtbDrc.Position> book = book(new Random(seed), 1.0);
        FrtbDrc.NonsecResult out = FrtbDrc.drcNonsec(book, RATING);
        assertTrue(out.drc() >= 0);
        for (FrtbDrc.BucketRow b : out.buckets()) {
            assertTrue(b.drc() >= 0 && (b.hbr() == null || (b.hbr() >= 0 && b.hbr() <= 1)));
        }
        // adding a long never lowers its bucket's DRC
        String ob = OBLIGORS[rnd.nextInt(3)];
        double extra = rnd.nextInt(1001);
        List<FrtbDrc.Position> more = new ArrayList<>(book);
        more.add(new FrtbDrc.Position("new", ob, BUCKET.get(ob), FrtbDrc.SENIORITIES.get(rnd.nextInt(4)), extra, extra,
                2.0, false, true));
        double after = byBucket(FrtbDrc.drcNonsec(more, RATING)).get(BUCKET.get(ob));
        assertTrue(after >= byBucket(out).getOrDefault(BUCKET.get(ob), 0.0) - 1e-9 * (1 + after));
        // permutation leaves every output unchanged (totals to rounding)
        List<FrtbDrc.Position> shuffled = new ArrayList<>(book);
        Collections.shuffle(shuffled, rnd);
        FrtbDrc.NonsecResult again = FrtbDrc.drcNonsec(shuffled, RATING);
        assertEquals(out.positions(), again.positions());
        assertEquals(out.drc(), again.drc(), 1e-12 * (1 + out.drc()));
        // scaling every amount by c scales DRC by c
        double c = 2.5;
        assertEquals(c * out.drc(), FrtbDrc.drcNonsec(book(new Random(seed), c), RATING).drc(),
                1e-12 * (1 + c * out.drc()));
    }
}
