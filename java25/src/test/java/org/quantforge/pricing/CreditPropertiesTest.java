package org.quantforge.pricing;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;

/**
 * Credit against independent checks: day-by-day Simpson integrals of both legs, the par-coupon identity,
 * bootstrap repricing, the calendar rules of credit.md and every validation path.
 */
class CreditPropertiesTest {
    private static final LocalDate T = LocalDate.of(2026, 3, 2); // a Monday
    private static final LocalDate FAR = LocalDate.of(2040, 1, 2);
    private static final LocalDate M5 = LocalDate.of(2031, 6, 20);

    private static double years(LocalDate a, LocalDate b) {
        return ChronoUnit.DAYS.between(a, b) / 365.0;
    }

    private static Curve flatRate(double r) {
        return Curve.of(T, Curve.Interpolation.LOG_LINEAR_DF, new LocalDate[] {FAR},
                new double[] {Math.exp(-r * years(T, FAR))});
    }

    /** A rate curve with interior pillars, so the leg integrals see its nodes. */
    private static Curve steepCurve() {
        LocalDate[] d = {LocalDate.of(2027, 1, 15), LocalDate.of(2028, 8, 3), LocalDate.of(2033, 2, 1), FAR};
        double[] z = {0.01, 0.03, 0.045, 0.05};
        double[] df = new double[d.length];
        for (int i = 0; i < d.length; i++) {
            df[i] = Math.exp(-z[i] * years(T, d[i]));
        }
        return Curve.of(T, Curve.Interpolation.LOG_LINEAR_DF, d, df);
    }

    private static Credit.Hazard flat(double h) {
        return new Credit.Hazard(T, new LocalDate[] {FAR}, new double[] {Math.exp(-h * years(T, FAR))});
    }

    private static Credit.Hazard stepped() {
        LocalDate[] d = {LocalDate.of(2027, 5, 11), LocalDate.of(2029, 10, 7), LocalDate.of(2030, 12, 1)};
        return new Credit.Hazard(T, d, new double[] {0.985, 0.90, 0.80});
    }

    private static String code(Runnable r) {
        return assertThrows(QfError.class, r::run).code();
    }

    /** Simpson over one day, where Q and P are each exp-linear so the integrand is smooth. */
    private static double simpson(java.util.function.DoubleUnaryOperator f, double a, double b) {
        int n = 8;
        double w = (b - a) / n;
        double s = f.applyAsDouble(a) + f.applyAsDouble(b);
        for (int i = 1; i < n; i++) {
            s += (i % 2 == 1 ? 4 : 2) * f.applyAsDouble(a + i * w);
        }
        return s * w / 3.0;
    }

    /** Value at year fraction u by exp-linear interpolation between whole days. */
    private static double between(java.util.function.Function<LocalDate, Double> g, LocalDate day, double u) {
        double ua = years(T, day);
        double la = Math.log(g.apply(day));
        double lb = Math.log(g.apply(day.plusDays(1)));
        return Math.exp(la + (lb - la) * (u - ua) * 365.0);
    }

    /** Protection per unit loss: integral of h(u) Q(u) P(u) du over [T, maturity]. */
    private static double protectionOracle(Curve p, Credit.Hazard q, LocalDate maturity) {
        double sum = 0.0;
        for (LocalDate a = T; a.isBefore(maturity); a = a.plusDays(1)) {
            LocalDate day = a;
            double h = Math.log(q.survival(a) / q.survival(a.plusDays(1))) * 365.0;
            sum += h * simpson(u -> between(q::survival, day, u) * between(p::discount, day, u),
                    years(T, a), years(T, a.plusDays(1)));
        }
        return sum;
    }

    /** Risky annuity: premium leg plus accrual on default, integrated day by day. */
    private static double rpv01Oracle(Curve p, Credit.Hazard q, LocalDate maturity) {
        double total = 0.0;
        for (Credit.Period per : Credit.periods(T, maturity)) {
            LocalDate obs = per.pay().minusDays(1);
            total += per.alpha() * q.survival(obs) * p.discount(per.pay());
            LocalDate accStart = per.start().minusDays(1);
            double c = years(T, accStart);
            double aod = 0.0;
            for (LocalDate a = accStart.isAfter(T) ? accStart : T; a.isBefore(obs); a = a.plusDays(1)) {
                LocalDate day = a;
                double h = Math.log(q.survival(a) / q.survival(a.plusDays(1))) * 365.0;
                aod += h * simpson(u -> (u - c) * between(q::survival, day, u) * between(p::discount, day, u),
                        years(T, a), years(T, a.plusDays(1)));
            }
            total += 365.0 / 360.0 * aod;
        }
        return total;
    }

    // ---- Hazard ----

    @Test
    void hazardInterpolatesLogLinearlyAndExtrapolatesTheLastHazard() {
        Credit.Hazard q = stepped();
        assertEquals(1.0, q.survival(T), 0.0);
        assertEquals(1.0, q.survival(T.minusDays(10)), 0.0);
        assertEquals(0.985, q.survival(LocalDate.of(2027, 5, 11)), 1e-15);
        assertEquals(0.90, q.survival(LocalDate.of(2029, 10, 7)), 1e-15);
        assertEquals(0.80, q.survival(LocalDate.of(2030, 12, 1)), 1e-15);
        // first segment starts at Q = 1
        LocalDate mid = LocalDate.of(2026, 10, 1);
        double w = years(T, mid) / years(T, LocalDate.of(2027, 5, 11));
        assertEquals(Math.exp(w * Math.log(0.985)), q.survival(mid), 1e-15);
        // interior segment
        LocalDate a = LocalDate.of(2027, 5, 11);
        LocalDate b = LocalDate.of(2029, 10, 7);
        LocalDate x = LocalDate.of(2028, 3, 3);
        double v = years(a, x) / years(a, b);
        assertEquals(Math.exp(Math.log(0.985) + v * (Math.log(0.90) - Math.log(0.985))), q.survival(x), 1e-15);
        // beyond the last pillar: last segment's hazard, flat
        LocalDate c = LocalDate.of(2030, 12, 1);
        double h = Math.log(0.90 / 0.80) / years(b, c);
        LocalDate late = LocalDate.of(2035, 7, 9);
        assertEquals(0.80 * Math.exp(-h * years(c, late)), q.survival(late), 1e-15);
    }

    @Test
    void singlePillarHazardExtrapolatesFromOne() {
        LocalDate p = LocalDate.of(2028, 3, 2);
        Credit.Hazard q = new Credit.Hazard(T, new LocalDate[] {p}, new double[] {0.9});
        double h = -Math.log(0.9) / years(T, p);
        LocalDate late = LocalDate.of(2031, 1, 1);
        assertEquals(Math.exp(-h * years(T, late)), q.survival(late), 1e-15);
    }

    @Test
    void hazardValidation() {
        LocalDate a = LocalDate.of(2027, 1, 1);
        LocalDate b = LocalDate.of(2028, 1, 1);
        assertEquals("E_INPUT", code(() -> new Credit.Hazard(T, new LocalDate[] {T}, new double[] {0.9})));
        assertEquals("E_INPUT", code(() -> new Credit.Hazard(T, new LocalDate[] {b, a}, new double[] {0.9, 0.8})));
        assertEquals("E_INPUT", code(() -> new Credit.Hazard(T, new LocalDate[] {a, a}, new double[] {0.9, 0.8})));
        assertEquals("E_DOMAIN", code(() -> new Credit.Hazard(T, new LocalDate[] {a}, new double[] {0.0})));
        assertEquals("E_DOMAIN", code(() -> new Credit.Hazard(T, new LocalDate[] {a}, new double[] {1.0000001})));
        assertEquals("E_DOMAIN", code(() -> new Credit.Hazard(T, new LocalDate[] {a}, new double[] {Double.NaN})));
        assertEquals("E_INPUT", code(() -> new Credit.Hazard(T, new LocalDate[0], new double[0])));
        assertEquals(1.0, new Credit.Hazard(T, new LocalDate[] {a}, new double[] {1.0}).survival(b), 0.0);
    }

    @Test
    void survivalsAndPillarDatesAreCopies() {
        Credit.Hazard q = stepped();
        assertArrayEquals(new double[] {0.985, 0.90, 0.80}, Credit.survivals(q), 1e-15);
        LocalDate[] d = Credit.pillarDates(q);
        assertNotSame(d, Credit.pillarDates(q));
        d[0] = T;
        assertEquals(LocalDate.of(2027, 5, 11), Credit.pillarDates(q)[0]);
    }

    // ---- calendar ----

    @Test
    void weekdaysAndRolls() {
        LocalDate fri = LocalDate.of(2026, 3, 6);
        assertFalse(Credit.weekend(fri));
        assertTrue(Credit.weekend(fri.plusDays(1)));
        assertTrue(Credit.weekend(fri.plusDays(2)));
        assertFalse(Credit.weekend(fri.plusDays(3)));
        assertEquals(fri, Credit.nextWeekday(fri));
        assertEquals(fri.plusDays(3), Credit.nextWeekday(fri.plusDays(1)));
        assertEquals(fri.plusDays(3), Credit.nextWeekday(fri.plusDays(2)));
        assertEquals(LocalDate.of(2026, 3, 11), Credit.addWeekdays(fri, 3));
        assertEquals(LocalDate.of(2026, 3, 5), Credit.addWeekdays(T, 3));
        assertEquals(fri, Credit.addWeekdays(fri, 0));

        assertEquals(LocalDate.of(2025, 12, 20), Credit.roll(LocalDate.of(2026, 1, 5)));
        assertEquals(LocalDate.of(2025, 12, 20), Credit.roll(LocalDate.of(2026, 3, 19)));
        assertEquals(LocalDate.of(2026, 6, 20), Credit.roll(LocalDate.of(2026, 3, 20)));
        assertEquals(LocalDate.of(2026, 6, 20), Credit.roll(LocalDate.of(2026, 9, 19)));
        assertEquals(LocalDate.of(2026, 12, 20), Credit.roll(LocalDate.of(2026, 9, 20)));
        assertEquals(LocalDate.of(2026, 12, 20), Credit.roll(LocalDate.of(2026, 12, 31)));

        assertEquals(LocalDate.of(2030, 12, 20), Credit.maturity(T, "5Y"));
        assertEquals(LocalDate.of(2026, 6, 20), Credit.maturity(T, "6M"));
        assertEquals(LocalDate.of(2031, 6, 20), Credit.maturity(LocalDate.of(2026, 4, 1), "5Y"));
        assertEquals("E_SCHEMA", code(() -> Credit.maturity(T, "2W")));
    }

    @Test
    void scheduleFollowsCreditMd() {
        List<Credit.Period> ps = Credit.periods(T, M5);
        assertEquals(22, ps.size());
        Credit.Period first = ps.getFirst();
        assertEquals(LocalDate.of(2025, 12, 22), first.start()); // 20 Dec 2025 is a Saturday
        assertEquals(LocalDate.of(2026, 3, 20), first.end());
        assertEquals(LocalDate.of(2026, 3, 20), first.pay());
        assertEquals(88 / 360.0, first.alpha(), 1e-15);
        Credit.Period last = ps.getLast();
        assertEquals(LocalDate.of(2031, 3, 20), last.start());
        assertEquals(M5, last.end()); // unadjusted, inclusive
        assertEquals(LocalDate.of(2031, 6, 20), last.pay());
        assertEquals(93 / 360.0, last.alpha(), 1e-15);
        for (int i = 1; i < ps.size(); i++) {
            assertEquals(ps.get(i - 1).end(), ps.get(i).start());
            assertFalse(Credit.weekend(ps.get(i).pay()));
        }
        // weekend maturity: pay rolls, end stays
        LocalDate m = LocalDate.of(2027, 3, 20); // Saturday
        Credit.Period l = Credit.periods(T, m).getLast();
        assertEquals(m, l.end());
        assertEquals(LocalDate.of(2027, 3, 22), l.pay());

        assertEquals("E_INPUT", code(() -> Credit.periods(T, T)));
        assertEquals("E_INPUT", code(() -> Credit.periods(T, T.minusDays(1))));
        // Ruling R6-7.3: a trade date on a coupon date, adjusted or not, is priced; the first period starts at T.
        assertEquals(LocalDate.of(2026, 3, 20), Credit.periods(LocalDate.of(2026, 3, 20), M5).getFirst().start());
        assertEquals(LocalDate.of(2025, 12, 22), Credit.periods(LocalDate.of(2025, 12, 22), M5).getFirst().start());
        Credit.periods(LocalDate.of(2025, 12, 23), M5); // the day after is fine
    }

    // ---- pricing ----

    @Test
    void legsMatchDayByDayIntegrals() {
        Curve[] curves = {flatRate(0.0), flatRate(0.04), steepCurve()};
        Credit.Hazard[] hazards = {flat(0.02), flat(0.6), stepped()};
        for (Curve p : curves) {
            for (Credit.Hazard q : hazards) {
                Credit.Price px = Credit.price(T, p, q, 0.4, M5, 0.01, 1.0, true, false);
                double prot = protectionOracle(p, q, M5);
                assertEquals(0.6 * prot, px.protection(), 1e-10 * prot);
                double rpv01 = rpv01Oracle(p, q, M5);
                assertEquals(rpv01, px.rpv01(), 1e-10 * rpv01);
            }
        }
    }

    @Test
    void flatClosedFormProtection() {
        double h = 0.03;
        double r = 0.05;
        double tau = years(T, M5);
        Credit.Price px = Credit.price(T, flatRate(r), flat(h), 0.25, M5, 0.01, 1.0, true, false);
        assertEquals(0.75 * h / (h + r) * -Math.expm1(-(h + r) * tau), px.protection(), 1e-13);
    }

    @Test
    void zeroHazardAndZeroRateLeaveNoProtection() {
        Credit.Hazard q = new Credit.Hazard(T, new LocalDate[] {FAR}, new double[] {1.0});
        Credit.Price px = Credit.price(T, flatRate(0.0), q, 0.4, M5, 0.01, 1.0, true, false);
        assertEquals(0.0, px.protection(), 0.0);
        double alphas = Credit.periods(T, M5).stream().mapToDouble(Credit.Period::alpha).sum();
        assertEquals(alphas, px.rpv01(), 1e-14);
    }

    @Test
    void priceIdentities() {
        Curve p = steepCurve();
        Credit.Hazard q = stepped();
        double c = 0.01;
        double n = 1e7;
        Credit.Price b = Credit.price(T, p, q, 0.4, M5, c, n, true, false);
        Credit.Price s = Credit.price(T, p, q, 0.4, M5, c, n, false, false);
        Credit.Price dig = Credit.price(T, p, q, 0.4, M5, c, n, true, true);
        assertEquals(b.protection() / 0.6, dig.protection(), 1e-15);
        assertEquals(-b.pv(), s.pv(), 0.0);
        assertEquals(b.parSpread(), s.parSpread(), 0.0);
        double accrued = c * ChronoUnit.DAYS.between(LocalDate.of(2025, 12, 22), T.plusDays(1)) / 360.0;
        assertEquals(accrued, b.accrued(), 1e-16);
        double pcs = p.discount(LocalDate.of(2026, 3, 5));
        assertEquals(n * (b.protection() - c * b.rpv01() + accrued * pcs), b.pv(), 1e-6);
        assertEquals((b.protection() - c * b.rpv01()) / pcs + accrued, b.upfront(), 1e-15);
        // at the par coupon the upfront vanishes
        Credit.Price atPar = Credit.price(T, p, q, 0.4, M5, b.parSpread(), n, true, false);
        assertEquals(0.0, atPar.upfront(), 1e-15);
        assertEquals(b.rpv01(), atPar.rpv01(), 0.0);
    }

    @Test
    void asOfMustMatch() {
        Curve p = flatRate(0.02);
        Credit.Hazard q = flat(0.02);
        LocalDate t1 = T.plusDays(1);
        assertEquals("E_INPUT", code(() -> Credit.checkAsOf(t1, p, null)));
        Credit.Hazard q1 = new Credit.Hazard(t1, new LocalDate[] {FAR}, new double[] {0.7});
        assertEquals("E_INPUT", code(() -> Credit.checkAsOf(T, p, q1)));
        Credit.checkAsOf(T, p, q);
        Credit.checkAsOf(T, p, null);
        assertEquals("E_INPUT", code(() -> Credit.price(T, p, q1, 0.4, M5, 0.01, 1.0, true, false)));
        assertEquals("E_DOMAIN", code(() -> Credit.price(T, p, q, -0.01, M5, 0.01, 1.0, true, false)));
        assertEquals("E_DOMAIN", code(() -> Credit.price(T, p, q, Double.NaN, M5, 0.01, 1.0, true, false)));
    }

    // ---- bootstrap ----

    @Test
    void bootstrapRepricesEveryQuoteAtPar() {
        Curve p = steepCurve();
        String[] tenors = {"6M", "1Y", "3Y", "5Y", "7Y", "10Y"};
        double[] spreads = {0.004, 0.0055, 0.009, 0.012, 0.0135, 0.015};
        Credit.Hazard q = Credit.bootstrap(T, p, 0.4, tenors, spreads);
        LocalDate[] d = Credit.pillarDates(q);
        double[] s = Credit.survivals(q);
        assertEquals(tenors.length, d.length);
        for (int j = 0; j < tenors.length; j++) {
            assertEquals(Credit.maturity(T, tenors[j]), d[j]);
            Credit.Price px = Credit.price(T, p, q, 0.4, d[j], spreads[j], 1.0, true, false);
            // 1e-9, not 1e-13: each pillar is solved on the curve cut at that pillar, and a weekend
            // maturity's observation day (pay - 1) lies past it, where the cut curve extrapolates.
            assertEquals(spreads[j], px.parSpread(), 1e-9);
            assertEquals(0.0, px.upfront(), 1e-9);
            assertTrue(s[j] < (j == 0 ? 1.0 : s[j - 1]));
        }
    }

    @Test
    void bootstrapOfAFlatSpreadIsNearlyFlatHazard() {
        double sp = 0.01;
        Credit.Hazard q = Credit.bootstrap(T, flatRate(0.03), 0.4, new String[] {"1Y", "5Y"},
                new double[] {sp, sp});
        double[] s = Credit.survivals(q);
        LocalDate[] d = Credit.pillarDates(q);
        double h1 = -Math.log(s[0]) / years(T, d[0]);
        double h2 = Math.log(s[0] / s[1]) / years(d[0], d[1]);
        assertEquals(sp / 0.6, h1, 2e-4); // the credit triangle, to within accrual effects
        assertEquals(h1, h2, 2e-4);
    }

    @Test
    void bootstrapValidation() {
        Curve p = flatRate(0.02);
        assertEquals("E_INPUT", code(() -> Credit.bootstrap(T, p, 0.4, new String[0], new double[0])));
        assertEquals("E_INPUT", code(() -> Credit.bootstrap(T, p, 0.4, new String[] {"5Y", "3Y"},
                new double[] {0.01, 0.01})));
        assertEquals("E_INPUT", code(() -> Credit.bootstrap(T, p, 0.4, new String[] {"5Y", "60M"},
                new double[] {0.01, 0.01})));
        assertEquals("E_DOMAIN", code(() -> Credit.bootstrap(T, p, 0.4, new String[] {"5Y"},
                new double[] {Double.NaN})));
        assertEquals("E_DOMAIN", code(() -> Credit.bootstrap(T, p, -0.1, new String[] {"5Y"},
                new double[] {0.01})));
        assertEquals("E_INPUT", code(() -> Credit.bootstrap(T.plusDays(1), p, 0.4, new String[] {"5Y"},
                new double[] {0.01})));
    }
}
