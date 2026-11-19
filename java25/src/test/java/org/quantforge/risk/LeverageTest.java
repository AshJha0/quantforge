package org.quantforge.risk;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.function.Supplier;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;

/**
 * Leverage ratio and large exposures (K-8i): unit tests and seeded properties mirroring
 * python/tests/test_stage_k_w2b.py. The golden replay is StageKW2bCliTest.
 */
class LeverageTest {
    private static QfError err(Supplier<?> f) {
        return assertThrows(QfError.class, f::get);
    }

    private record Parts(double[] on, List<Leverage.DerivativeSet> d, List<Leverage.WrittenCreditDerivative> w,
            List<Leverage.Sft> s, List<Leverage.OffBalance> o) {
        Parts plus(Parts b) {
            double[] on2 = new double[on.length + b.on.length];
            System.arraycopy(on, 0, on2, 0, on.length);
            System.arraycopy(b.on, 0, on2, on.length, b.on.length);
            return new Parts(on2, cat(d, b.d), cat(w, b.w), cat(s, b.s), cat(o, b.o));
        }
    }

    private static <T> List<T> cat(List<T> a, List<T> b) {
        List<T> out = new ArrayList<>(a);
        out.addAll(b);
        return out;
    }

    private static double nonneg(Random r) {
        return 1e6 * r.nextDouble();
    }

    private static Parts parts(Random r) {
        double[] on = new double[r.nextInt(4)];
        for (int i = 0; i < on.length; i++) {
            on[i] = nonneg(r);
        }
        List<Leverage.DerivativeSet> d = new ArrayList<>();
        for (int i = r.nextInt(4); i > 0; i--) {
            d.add(new Leverage.DerivativeSet((2 * r.nextDouble() - 1) * 1e6, nonneg(r), nonneg(r), nonneg(r)));
        }
        List<Leverage.WrittenCreditDerivative> w = new ArrayList<>();
        for (int i = r.nextInt(4); i > 0; i--) {
            w.add(new Leverage.WrittenCreditDerivative(nonneg(r), (2 * r.nextDouble() - 1) * 1e6, nonneg(r)));
        }
        List<Leverage.Sft> s = new ArrayList<>();
        for (int i = r.nextInt(4); i > 0; i--) {
            int n = r.nextInt(4);
            double[] e = new double[n];
            double[] c = new double[n];
            for (int k = 0; k < n; k++) {
                e[k] = nonneg(r);
                c[k] = nonneg(r);
            }
            s.add(new Leverage.Sft(nonneg(r), r.nextBoolean(), e, c));
        }
        List<String> cats = new ArrayList<>(Leverage.CCF_CATEGORIES.keySet());
        List<Leverage.OffBalance> o = new ArrayList<>();
        for (int i = r.nextInt(4); i > 0; i--) {
            o.add(new Leverage.OffBalance(nonneg(r), cats.get(r.nextInt(cats.size()))));
        }
        return new Parts(on, d, w, s, o);
    }

    private static double exposure(Parts p) {
        try {
            return Leverage.leverage(1.0, p.on(), p.d(), p.w(), p.s(), p.o()).exposure();
        } catch (QfError e) {
            assertEquals("E_DOMAIN", e.code()); // exposure measure zero (KR-130)
            return 0.0;
        }
    }

    @Property(tries = 300)
    void leverageNonNegativeAndAdditive(@ForAll long seed) {
        Random r = new Random(seed);
        Parts a = parts(r);
        Parts b = parts(r);
        double ea = exposure(a);
        double eb = exposure(b);
        assertTrue(ea >= 0 && eb >= 0);
        assertTrue(Math.abs(exposure(a.plus(b)) - (ea + eb)) <= 1e-9 * Math.max(1.0, ea + eb));
    }

    @Property(tries = 300)
    void leverageMonotone(@ForAll long seed) {
        Random r = new Random(seed);
        Parts p = parts(r);
        double bump = nonneg(r);
        double before = exposure(p);
        Parts extra = switch (r.nextInt(5)) {
            case 0 -> new Parts(new double[] {bump}, List.of(), List.of(), List.of(), List.of());
            case 1 -> new Parts(new double[0], List.of(new Leverage.DerivativeSet(0, bump, 0, 0)), List.of(),
                    List.of(), List.of());
            case 2 -> new Parts(new double[0], List.of(), List.of(new Leverage.WrittenCreditDerivative(bump, 0, 0)),
                    List.of(), List.of());
            case 3 -> new Parts(new double[0], List.of(), List.of(), List.of(new Leverage.Sft(bump, false,
                    new double[] {bump}, new double[] {0.0})), List.of());
            default -> new Parts(new double[0], List.of(), List.of(), List.of(), List.of(new Leverage.OffBalance(bump,
                    "COMMITMENT")));
        };
        assertTrue(exposure(p.plus(extra)) >= before * (1 - 1e-12));
    }

    @Test
    void leverageBoundaryBinary64() {
        Leverage.LeverageResult out = Leverage.leverage(3.0, new double[] {100.0}, List.of(), List.of(), List.of(),
                List.of());
        assertEquals(3.0 >= 0.03 * 100.0, out.meetsMinimum());
        assertFalse(Leverage.leverage(2.9, new double[] {100.0}, List.of(), List.of(), List.of(), List.of())
                .meetsMinimum());
        assertEquals(Leverage.LEVERAGE_LABEL, out.label());
    }

    @Test
    void leverageErrors() {
        double[] one = {1.0};
        assertEquals("E_SCHEMA", err(() -> Leverage.leverage(1.0, one, List.of(), List.of(), List.of(),
                List.of(new Leverage.OffBalance(1.0, "GUARANTEE")))).code());
        // structural before domain: mismatched SFT legs with tier1 0
        assertEquals("E_INPUT", err(() -> Leverage.leverage(0.0, one, List.of(), List.of(), List.of(
                new Leverage.Sft(1, true, new double[] {1}, new double[0])), List.of())).code());
        assertEquals("E_DOMAIN", err(() -> Leverage.leverage(0.0, one, List.of(), List.of(), List.of(), List.of()))
                .code());
        assertEquals("E_DOMAIN", err(() -> Leverage.leverage(1.0, new double[] {-1}, List.of(), List.of(), List.of(),
                List.of())).code());
        for (Leverage.DerivativeSet d : List.of(new Leverage.DerivativeSet(0, 1, -1, 0),
                new Leverage.DerivativeSet(0, 1, 0, -1), new Leverage.DerivativeSet(0, -1, 0, 0))) {
            assertEquals("E_DOMAIN", err(() -> Leverage.leverage(1.0, one, List.of(d), List.of(), List.of(),
                    List.of())).code());
        }
        for (Leverage.WrittenCreditDerivative w : List.of(new Leverage.WrittenCreditDerivative(-1, 0, 0),
                new Leverage.WrittenCreditDerivative(1, 0, -1))) {
            assertEquals("E_DOMAIN", err(() -> Leverage.leverage(1.0, one, List.of(), List.of(w), List.of(),
                    List.of())).code());
        }
        for (Leverage.Sft s : List.of(new Leverage.Sft(-1, true, new double[0], new double[0]),
                new Leverage.Sft(1, true, new double[] {-1}, new double[] {0}),
                new Leverage.Sft(1, true, new double[] {1}, new double[] {-1}))) {
            assertEquals("E_DOMAIN", err(() -> Leverage.leverage(1.0, one, List.of(), List.of(), List.of(s),
                    List.of())).code());
        }
        assertEquals("E_DOMAIN", err(() -> Leverage.leverage(1.0, one, List.of(), List.of(), List.of(),
                List.of(new Leverage.OffBalance(-1, "COMMITMENT")))).code());
        assertEquals("E_DOMAIN", err(() -> Leverage.leverage(1.0, new double[0], List.of(), List.of(), List.of(),
                List.of())).code());
    }

    @Test
    void partFormulas() {
        assertEquals(1.4 * 15, Leverage.derivativeExposure(new Leverage.DerivativeSet(10, 5, 2, 2)));
        assertEquals(1.4 * 5, Leverage.derivativeExposure(new Leverage.DerivativeSet(-10, 5, 0, 0)));
        assertEquals(90.0, Leverage.writtenCdEffectiveNotional(new Leverage.WrittenCreditDerivative(100, -10, 0)));
        assertEquals(100.0, Leverage.writtenCdEffectiveNotional(new Leverage.WrittenCreditDerivative(100, 10, 0)));
        assertEquals(0.0, Leverage.writtenCdEffectiveNotional(new Leverage.WrittenCreditDerivative(10, -5, 20)));
        assertEquals(10.0, Leverage.sftExposure(new Leverage.Sft(10, true, new double[] {5}, new double[] {7})));
        assertEquals(15.0, Leverage.sftExposure(new Leverage.Sft(10, false, new double[] {5, 1}, new double[] {0,
            2})));
    }

    // --- large exposures ---------------------------------------------------------------------------------------

    private static Map<String, Leverage.GroupRow> le(Map<String, Double> values, List<Leverage.LeCounterparty> cps,
            boolean bankGsib) {
        List<Leverage.BankingBookExposure> bb = new ArrayList<>();
        values.forEach((k, v) -> bb.add(new Leverage.BankingBookExposure(k, v)));
        Map<String, Leverage.GroupRow> out = new HashMap<>();
        for (Leverage.GroupRow g : Leverage.largeExposures(1000.0, cps, bb, List.of(), List.of(), List.of(),
                bankGsib).groups()) {
            out.put(g.group(), g);
        }
        return out;
    }

    private static Leverage.LeCounterparty cp(String id) {
        return new Leverage.LeCounterparty(id, null, false, false);
    }

    @Test
    void largeExposureBoundaries() {
        Map<String, Double> v = new java.util.LinkedHashMap<>();
        v.put("A", 100.0);
        v.put("B", 250.0);
        v.put("C", Math.nextUp(250.0));
        v.put("D", Math.nextDown(100.0));
        Map<String, Leverage.GroupRow> g = le(v, List.of(cp("A"), cp("B"), cp("C"), cp("D")), false);
        assertTrue(g.get("A").large() && !g.get("A").breach());
        assertTrue(g.get("B").large() && !g.get("B").breach());
        assertTrue(g.get("C").breach());
        assertFalse(g.get("D").large());
        Map<String, Leverage.GroupRow> gs = le(Map.of("K", 150.0, "J", 151.0), List.of(
                new Leverage.LeCounterparty("K", null, true, false), new Leverage.LeCounterparty("J", null, true,
                        false)), true);
        assertTrue(!gs.get("K").breach() && gs.get("J").breach());
        assertEquals(150.0, gs.get("J").limit());
    }

    @Test
    void gsibGroupReadingAndExemptions() {
        // KR-133 open reading: a mixed group takes 15% under "any member" (the Python reference)
        assertTrue(Leverage.GSIB_GROUP_ANY_MEMBER);
        Map<String, Leverage.GroupRow> g = le(Map.of("a", 100.0, "b", 100.0), List.of(
                new Leverage.LeCounterparty("a", "G", true, false), new Leverage.LeCounterparty("b", "G", false,
                        true)), true);
        Leverage.GroupRow row = g.get("G");
        assertEquals(150.0, row.limit());
        assertEquals(200.0, row.exposure());
        assertFalse(row.breach()); // only the non-exempt 100 is counted (KR-134)
        assertFalse(row.exempt());
        assertEquals(List.of("a", "b"), row.members());
    }

    @Property(tries = 300)
    void groupIsSumOfMembers(@ForAll long seed) {
        Random r = new Random(seed);
        List<Leverage.LeCounterparty> cps = new ArrayList<>();
        List<Leverage.BankingBookExposure> bb = new ArrayList<>();
        for (int n = 0; n < 1 + r.nextInt(8); n++) {
            cps.add(new Leverage.LeCounterparty("c" + n, String.valueOf("GHI".charAt(r.nextInt(3))), false, false));
            bb.add(new Leverage.BankingBookExposure("c" + n, nonneg(r)));
        }
        Leverage.LargeExposuresResult out = Leverage.largeExposures(1000.0, cps, bb, List.of(), List.of(), List.of(),
                false);
        Map<String, Double> rows = new HashMap<>();
        out.counterparties().forEach(c -> rows.put(c.id(), c.exposure()));
        for (Leverage.GroupRow g : out.groups()) {
            double[] v = g.members().stream().mapToDouble(rows::get).toArray();
            double want = org.quantforge.research.StressDrift.fsum(v);
            assertTrue(Math.abs(g.exposure() - want) <= 1e-12 * Math.max(1.0, Math.abs(want)));
        }
    }

    @Property(tries = 300)
    void protectionMovesExposure(@ForAll long seed) {
        Random r = new Random(seed);
        int n = 2 + r.nextInt(4);
        List<Leverage.LeCounterparty> cps = new ArrayList<>();
        List<Leverage.BankingBookExposure> bb = new ArrayList<>();
        double[] values = new double[n];
        for (int i = 0; i < n; i++) {
            values[i] = nonneg(r);
            cps.add(cp("c" + i));
            bb.add(new Leverage.BankingBookExposure("c" + i, values[i]));
        }
        int a = r.nextInt(n);
        int b = (a + 1 + r.nextInt(n - 1)) % n;
        double amount = values[a] * r.nextDouble();
        double plain = total(Leverage.largeExposures(1000.0, cps, bb, List.of(), List.of(), List.of(), false));
        double moved = total(Leverage.largeExposures(1000.0, cps, bb, List.of(), List.of(new Leverage.Protection(
                "c" + a, "c" + b, amount)), List.of(), false));
        assertTrue(Math.abs(plain - moved) <= 1e-9 * Math.max(1.0, plain));
    }

    private static double total(Leverage.LargeExposuresResult out) {
        return org.quantforge.research.StressDrift.fsum(out.counterparties().stream()
                .mapToDouble(Leverage.CounterpartyRow::exposure).toArray());
    }

    /** Python's tuple equality: -0.0 equals 0.0 (the net short of a fully offset obligor is -0.0). */
    private static void pair(double[] want, double[] got) {
        assertEquals(want[0], got[0], 0.0);
        assertEquals(want[1], got[1], 0.0);
    }

    @Test
    void offsetBySeniority() {
        pair(new double[] {50.0, -20.0}, Leverage.offsetBySeniority(new int[] {1, 3},
                new double[] {50.0, -20.0}));
        pair(new double[] {30.0, 0.0}, Leverage.offsetBySeniority(new int[] {3, 1},
                new double[] {50.0, -20.0}));
        pair(new double[] {0.0, 0.0}, Leverage.offsetBySeniority(new int[0], new double[0]));
        pair(new double[] {15.0, 0.0}, Leverage.offsetBySeniority(new int[] {3, 3, 3},
                new double[] {10.0, 10.0, -5.0}));
        pair(new double[] {0.0, -7.0}, Leverage.offsetBySeniority(new int[] {2, 4, 3, 1},
                new double[] {10.0, 10.0, -15.0, -12.0}));
    }

    @Test
    void largeExposuresCoreChecksAndJtd() {
        List<Leverage.LeCounterparty> a = List.of(cp("A"));
        assertEquals("E_SCHEMA", err(() -> Leverage.largeExposures(1.0, a, List.of(), List.of(), List.of(), List.of(
                new Leverage.TradingPosition("p", "A", "SUPER", 1, 1)), false)).code());
        assertEquals(0.0, Leverage.jtd(new Leverage.TradingPosition("p", "A", "SENIOR", -10, 5)));
        assertEquals(0.0, Leverage.jtd(new Leverage.TradingPosition("p", "A", "SENIOR", 10, -5)));
        Leverage.LargeExposuresResult out = Leverage.largeExposures(100.0, a, List.of(), List.of(
                new Leverage.OffBalanceExposure("A", 50.0, 0.2)), List.of(), List.of(), false);
        assertEquals(List.of("A"), out.report());
        assertEquals(10.0, out.counterparties().get(0).offBalance());
        // structure (E_INPUT) before domain (E_DOMAIN), in Python's order
        assertEquals("E_INPUT", err(() -> Leverage.largeExposures(0.0, List.of(cp("A"), cp("A")), List.of(),
                List.of(), List.of(), List.of(), false)).code());
        assertEquals("E_INPUT", err(() -> Leverage.largeExposures(1.0, List.of(new Leverage.LeCounterparty("A", "B",
                false, false), cp("B")), List.of(), List.of(), List.of(), List.of(), false)).code());
        assertEquals("E_INPUT", err(() -> Leverage.largeExposures(1.0, a, List.of(new Leverage.BankingBookExposure(
                "Z", 1)), List.of(), List.of(), List.of(), false)).code());
        assertEquals("E_INPUT", err(() -> Leverage.largeExposures(1.0, a, List.of(), List.of(), List.of(
                new Leverage.Protection("A", "A", 1)), List.of(), false)).code());
        assertEquals("E_INPUT", err(() -> Leverage.largeExposures(1.0, a, List.of(), List.of(), List.of(), List.of(
                new Leverage.TradingPosition("p", "A", "SENIOR", 1, 1), new Leverage.TradingPosition("p", "A",
                        "SENIOR", 1, 1)), false)).code());
        assertEquals("E_DOMAIN", err(() -> Leverage.largeExposures(0.0, a, List.of(), List.of(), List.of(), List.of(),
                false)).code());
        assertEquals("E_DOMAIN", err(() -> Leverage.largeExposures(1.0, a, List.of(new Leverage.BankingBookExposure(
                "A", -1)), List.of(), List.of(), List.of(), false)).code());
        assertEquals("E_DOMAIN", err(() -> Leverage.largeExposures(1.0, a, List.of(), List.of(
                new Leverage.OffBalanceExposure("A", -1, 0.5)), List.of(), List.of(), false)).code());
        assertEquals("E_DOMAIN", err(() -> Leverage.largeExposures(1.0, a, List.of(), List.of(
                new Leverage.OffBalanceExposure("A", 1, 1.5)), List.of(), List.of(), false)).code());
        List<Leverage.LeCounterparty> ab = List.of(cp("A"), cp("B"));
        assertEquals("E_DOMAIN", err(() -> Leverage.largeExposures(1.0, ab, List.of(), List.of(), List.of(
                new Leverage.Protection("A", "B", -1)), List.of(), false)).code());
        assertEquals("E_DOMAIN", err(() -> Leverage.largeExposures(1.0, ab, List.of(), List.of(), List.of(
                new Leverage.Protection("A", "B", 1)), List.of(), false)).code());
    }

    @Test
    void reportOrderAndTopN() {
        List<Leverage.LeCounterparty> cps = new ArrayList<>();
        List<Leverage.BankingBookExposure> bb = new ArrayList<>();
        for (int i = 0; i < 25; i++) {
            cps.add(cp(String.format("c%02d", i)));
            bb.add(new Leverage.BankingBookExposure(String.format("c%02d", i), i == 3 ? 500.0 : 1.0));
        }
        Leverage.LargeExposuresResult out = Leverage.largeExposures(1000.0, cps, bb, List.of(), List.of(), List.of(),
                false);
        assertEquals(Leverage.TOP_N, out.report().size());
        assertEquals("c03", out.report().get(0));
        assertEquals("c00", out.report().get(1)); // ties by label
    }
}
