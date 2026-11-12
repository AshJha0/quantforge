package org.quantforge.hedging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.hedging.CorrelationHedge.Instrument;
import org.quantforge.hedging.CorrelationHedge.Kind;
import org.quantforge.hedging.CorrelationHedge.Market;
import org.quantforge.hedging.CorrelationHedge.Target;
import org.quantforge.pricing.Credit;

/** Wave 2 credit and correlation hedges: the spec's property tests, hand checks and every validation path. */
class CreditCorrelationHedgeTest {
    private static final LocalDate T = LocalDate.of(2026, 11, 6);
    static final Curve DISCOUNT = Curve.of(T, Curve.Interpolation.LOG_LINEAR_DF,
            new LocalDate[] {LocalDate.of(2046, 11, 6)}, new double[] {0.45});
    static final LocalDate[] PILLARS = {LocalDate.of(2027, 12, 20), LocalDate.of(2029, 12, 20),
        LocalDate.of(2031, 12, 20), LocalDate.of(2033, 12, 20), LocalDate.of(2036, 12, 20)};
    static final Credit.Hazard HAZARD = new Credit.Hazard(T, PILLARS,
            new double[] {0.988, 0.953, 0.899, 0.845, 0.763});

    private static String code(Runnable r) {
        return assertThrows(QfError.class, r::run).code();
    }

    static CreditHedge.Result credit(double recovery, List<CreditHedge.Trade> book,
            List<CreditHedge.Contract> hedges, List<String> targets) {
        return CreditHedge.solve(T, DISCOUNT, HAZARD, recovery, book, hedges, targets);
    }


    @Test
    void bucketsSumToAboutTheParallelCs01AndTargetsAreZeroAfter() {
        List<CreditHedge.Trade> book = List.of(new CreditHedge.Trade(PILLARS[3], 0.01, 1e7, false),
                new CreditHedge.Trade(PILLARS[1], 0.05, 4e6, true));
        CreditHedge.Result r = credit(0.4, book, List.of(new CreditHedge.Contract(PILLARS[2], 0.01),
                new CreditHedge.Contract(PILLARS[4], 0.01)), List.of("CS01", "JTD"));
        double sum = 0.0;
        for (double b : r.book().buckets()) {
            sum += b;
        }
        assertEquals(r.book().cs01(), sum, 1e-3 * Math.abs(r.book().cs01()));
        assertEquals(0.0, r.after().cs01(), 1e-6);
        assertEquals(0.0, r.after().jtd(), 1e-6);
        assertEquals(0.0, r.book().buckets()[4], 0.0); // no trade reaches the last section
    }

    @Test
    void cs01IsTheSpecifiedCentralDifference() {
        CreditHedge.Unit u = CreditHedge.unitRisk(T, DISCOUNT, HAZARD, 0.4, PILLARS[2], 0.01);
        double eps = 1e-4 / 0.6;
        double[] up = {eps, eps, eps, eps, eps};
        double[] dn = {-eps, -eps, -eps, -eps, -eps};
        double pu = Credit.price(T, DISCOUNT, HAZARD.shifted(up), 0.4, PILLARS[2], 0.01, 1, true, false).pv();
        double pd = Credit.price(T, DISCOUNT, HAZARD.shifted(dn), 0.4, PILLARS[2], 0.01, 1, true, false).pv();
        assertEquals((pu - pd) / 2, u.risk().cs01(), 0.0);
        assertTrue(u.risk().cs01() > 0.0, "bought protection gains when hazards rise");
        assertEquals(0.6 - u.risk().pv(), u.risk().jtd(), 0.0);
        // A shift of zero reproduces the curve.
        assertEquals(HAZARD.survival(PILLARS[3]), HAZARD.shifted(new double[5]).survival(PILLARS[3]), 1e-15);
    }

    @Test
    void targetNames() {
        assertEquals(0, CreditHedge.targetIndex("CS01", 5));
        assertEquals(1, CreditHedge.targetIndex("JTD", 5));
        assertEquals(6, CreditHedge.targetIndex("BUCKET_5", 5));
        assertEquals(-1, CreditHedge.targetIndex("BUCKET_6", 5));
        assertEquals(-1, CreditHedge.targetIndex("BUCKET_0", 5));
        assertEquals(-1, CreditHedge.targetIndex("PV", 5));
    }

    @Test
    void creditChecks() {
        List<CreditHedge.Trade> book = List.of(new CreditHedge.Trade(PILLARS[3], 0.01, 1e7, false));
        List<CreditHedge.Contract> one = List.of(new CreditHedge.Contract(PILLARS[2], 0.01));
        assertEquals("E_INPUT", code(() -> credit(0.4, List.of(), one, List.of("CS01"))));
        assertEquals("E_INPUT", code(() -> credit(0.4, book, List.of(), List.of())));
        assertEquals("E_INPUT", code(() -> credit(0.4, book, one, List.of("CS01", "JTD"))));
        assertEquals("E_INPUT", code(() -> credit(0.4, book, List.of(one.get(0), one.get(0)),
                List.of("CS01", "CS01"))));
        assertEquals("E_INPUT", code(() -> credit(0.4, book, one, List.of("BUCKET_9"))));
        assertEquals("E_INPUT", code(() -> credit(0.4, List.of(new CreditHedge.Trade(T, 0.01, 1, true)), one,
                List.of("CS01"))));
        assertEquals("E_INPUT", code(() -> credit(0.4, book, List.of(new CreditHedge.Contract(T, 0.01)),
                List.of("CS01"))));
        assertEquals("E_DOMAIN", code(() -> credit(1.0, book, one, List.of("CS01"))));
        assertEquals("E_DOMAIN", code(() -> credit(0.4, List.of(new CreditHedge.Trade(PILLARS[3], 0.01, -1, true)),
                one, List.of("CS01"))));
        assertEquals("E_DOMAIN", code(() -> credit(0.4, List.of(new CreditHedge.Trade(PILLARS[3], -0.01, 1, true)),
                one, List.of("CS01"))));
        assertEquals("E_DOMAIN", code(() -> credit(0.4, book, List.of(new CreditHedge.Contract(PILLARS[2], -1)),
                List.of("CS01"))));
        assertEquals("E_SINGULAR", code(() -> credit(0.4, book, List.of(one.get(0), one.get(0)),
                List.of("CS01", "JTD"))));
        assertEquals("E_SINGULAR", code(() -> credit(0.4, book, one, List.of("BUCKET_5"))));
    }

    private static final Market MK = new Market(100, 95, 0.03, 0.01, 0.02, 0.25, 0.2, 0.6);

    static Instrument exchange(double q1, double q2, double t, Double qty) {
        Map<String, Double> v = new HashMap<>(Map.of("quantity1", q1, "quantity2", q2, "expiry_years", t));
        if (qty != null) {
            v.put("quantity", qty);
        }
        return new Instrument(Kind.EXCHANGE, v, false);
    }

    static Instrument vanilla(Kind kind, double k, double t, Double qty) {
        Map<String, Double> v = new HashMap<>(Map.of("strike", k, "expiry_years", t));
        if (qty != null) {
            v.put("quantity", qty);
        }
        return new Instrument(kind, v, false);
    }

    private static double margrabe(Market mk, double t) {
        double s = mk.spreadVol();
        double f1 = mk.spot1() * Math.exp(-mk.yield1() * t);
        double f2 = mk.spot2() * Math.exp(-mk.yield2() * t);
        double d1 = (Math.log(f1 / f2) + 0.5 * s * s * t) / (s * Math.sqrt(t));
        return f1 * Normal.cdf(d1) - f2 * Normal.cdf(d1 - s * Math.sqrt(t));
    }

    @Test
    void exchangeGreeksMatchFiniteDifferences() {
        double[] g = CorrelationHedge.greeks(MK, exchange(1, 1, 1.5, null));
        double h = 1e-4;
        assertEquals((margrabe(new Market(100 + h, 95, 0.03, 0.01, 0.02, 0.25, 0.2, 0.6), 1.5)
                - margrabe(new Market(100 - h, 95, 0.03, 0.01, 0.02, 0.25, 0.2, 0.6), 1.5)) / (2 * h), g[0], 1e-8);
        assertEquals((margrabe(new Market(100, 95 + h, 0.03, 0.01, 0.02, 0.25, 0.2, 0.6), 1.5)
                - margrabe(new Market(100, 95 - h, 0.03, 0.01, 0.02, 0.25, 0.2, 0.6), 1.5)) / (2 * h), g[1], 1e-8);
        double hv = 1e-6;
        assertEquals((margrabe(new Market(100, 95, 0.03, 0.01, 0.02, 0.25 + hv, 0.2, 0.6), 1.5)
                - margrabe(new Market(100, 95, 0.03, 0.01, 0.02, 0.25 - hv, 0.2, 0.6), 1.5)) / (2 * hv), g[2], 1e-6);
        assertEquals((margrabe(new Market(100, 95, 0.03, 0.01, 0.02, 0.25, 0.2 + hv, 0.6), 1.5)
                - margrabe(new Market(100, 95, 0.03, 0.01, 0.02, 0.25, 0.2 - hv, 0.6), 1.5)) / (2 * hv), g[3], 1e-6);
        assertEquals(0.01 * (margrabe(new Market(100, 95, 0.03, 0.01, 0.02, 0.25, 0.2, 0.6 + hv), 1.5)
                - margrabe(new Market(100, 95, 0.03, 0.01, 0.02, 0.25, 0.2, 0.6 - hv), 1.5)) / (2 * hv), g[4], 1e-8);
    }


    @Test
    void allFiveGreeksAreHedged() {
        List<Instrument> book = List.of(exchange(1, 1, 1, -1000.0), exchange(1, 1.1, 2, 400.0));
        List<Instrument> hedges = List.of(exchange(1, 1, 0.5, null), vanilla(Kind.CALL_1, 100, 1, null),
                vanilla(Kind.PUT_2, 90, 1, null), new Instrument(Kind.UNDERLYING_1, Map.of(), false),
                new Instrument(Kind.UNDERLYING_2, Map.of(), false));
        CorrelationHedge.Result r = CorrelationHedge.solve(MK, book, hedges, List.of(Target.CORRELATION,
                Target.VEGA_1, Target.VEGA_2, Target.DELTA_1, Target.DELTA_2));
        for (int i = 0; i < 5; i++) {
            assertEquals(0.0, r.after()[i], 1e-9 * Math.max(1.0, Math.abs(r.before()[i])));
        }
    }

    private static String corr(Market mk, List<Instrument> book, List<Instrument> hedges, List<Target> targets) {
        return code(() -> CorrelationHedge.solve(mk, book, hedges, targets));
    }

    @Test
    void correlationChecks() {
        List<Instrument> book = List.of(exchange(1, 1, 1, 1.0));
        List<Instrument> ex = List.of(exchange(1, 1, 0.5, null));
        List<Target> c = List.of(Target.CORRELATION);
        assertEquals("E_INPUT", corr(MK, List.of(exchange(1, 1, 1, null)), ex, c));
        assertEquals("E_INPUT", corr(MK, book, List.of(exchange(1, 1, 1, 1.0)), c));
        assertEquals("E_INPUT", corr(MK, book, List.of(new Instrument(Kind.UNDERLYING_1, Map.of("expiry_years", 1.0),
                false)), List.of(Target.DELTA_1)));
        assertEquals("E_INPUT", corr(MK, book, List.of(new Instrument(Kind.UNDERLYING_1, Map.of(), true)),
                List.of(Target.DELTA_1)));
        assertEquals("E_INPUT", corr(MK, book, List.of(), List.of()));
        assertEquals("E_INPUT", corr(MK, book, ex, List.of(Target.CORRELATION, Target.VEGA_1)));
        assertEquals("E_INPUT", corr(MK, book, List.of(ex.get(0), ex.get(0)),
                List.of(Target.CORRELATION, Target.CORRELATION)));
        assertEquals("E_DOMAIN", corr(new Market(0, 95, 0, 0, 0, 0.2, 0.2, 0), book, ex, c));
        assertEquals("E_DOMAIN", corr(new Market(100, 0, 0, 0, 0, 0.2, 0.2, 0), book, ex, c));
        assertEquals("E_DOMAIN", corr(new Market(100, 95, 0, 0, 0, 0, 0.2, 0), book, ex, c));
        assertEquals("E_DOMAIN", corr(new Market(100, 95, 0, 0, 0, 0.2, 0, 0), book, ex, c));
        assertEquals("E_DOMAIN", corr(new Market(100, 95, 0, 0, 0, 0.2, 0.2, 1.01), book, ex, c));
        assertEquals("E_DOMAIN", corr(new Market(100, 95, 0, 0, 0, 0.2, 0.2, 1.0), book, ex, c));
        assertEquals("E_DOMAIN", corr(MK, List.of(exchange(0, 1, 1, 1.0)), ex, c));
        assertEquals("E_DOMAIN", corr(MK, book, List.of(vanilla(Kind.CALL_1, -1, 1, null)), List.of(Target.DELTA_1)));
        assertEquals("E_SINGULAR", corr(MK, book, List.of(ex.get(0), exchange(1, 1, 2, null)),
                List.of(Target.CORRELATION, Target.VEGA_1)));
        assertEquals("E_SINGULAR", corr(MK, book, List.of(new Instrument(Kind.UNDERLYING_1, Map.of(), false)), c));
    }
}
