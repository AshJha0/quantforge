package org.quantforge.hedging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.quantforge.hedging.CreditCorrelationHedgeTest.PILLARS;
import static org.quantforge.hedging.CreditCorrelationHedgeTest.credit;
import static org.quantforge.hedging.CreditCorrelationHedgeTest.exchange;
import static org.quantforge.hedging.CreditCorrelationHedgeTest.vanilla;

import java.time.LocalDate;
import java.util.List;
import java.util.Random;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import org.quantforge.hedging.CorrelationHedge.Kind;
import org.quantforge.hedging.CorrelationHedge.Market;

/** The wave 2 property tests named by the spec, on this build's own random data. */
class CreditCorrelationPropertyTest {

    @Property(tries = 20)
    void hedgingWithTheBooksOwnContractReturnsMinusItsNotional(@ForAll long seed) {
        Random rnd = new Random(seed);
        LocalDate m = PILLARS[rnd.nextInt(PILLARS.length)];
        double coupon = rnd.nextBoolean() ? 0.01 : 0.05;
        double notional = 1e6 * (1 + rnd.nextInt(20));
        boolean buyer = rnd.nextBoolean();
        String target = List.of("CS01", "JTD", "BUCKET_1").get(rnd.nextInt(3));
        CreditHedge.Result r = credit(0.4, List.of(new CreditHedge.Trade(m, coupon, notional, buyer)),
                List.of(new CreditHedge.Contract(m, coupon)), List.of(target));
        assertEquals((buyer ? -1 : 1) * notional, r.notionals()[0], 1e-6 * notional);
        assertEquals(0.0, r.after().cs01(), 1e-6);
        assertEquals(0.0, r.after().jtd(), 1e-6 * notional);
    }

    @Property(tries = 200)
    void longExchangeHasNegativeCorrelationRiskAndVanillasNone(@ForAll long seed) {
        Random rnd = new Random(seed);
        Market mk = new Market(50 + 100 * rnd.nextDouble(), 50 + 100 * rnd.nextDouble(), 0.05 * rnd.nextGaussian(),
                0.03 * rnd.nextDouble(), 0.03 * rnd.nextDouble(), 0.05 + 0.5 * rnd.nextDouble(),
                0.05 + 0.5 * rnd.nextDouble(), 1.8 * rnd.nextDouble() - 0.9);
        double t = 0.1 + 3 * rnd.nextDouble();
        double q1 = 0.5 + rnd.nextDouble();
        double q2 = 0.5 + rnd.nextDouble();
        double corr01 = CorrelationHedge.greeks(mk, exchange(q1, q2, t, null))[4];
        // correlation01 = -f1 phi(d1) sqrt(t) v1 v2 / s * 0.01 is negative in exact arithmetic, but phi(d1)
        // underflows to 0 once |d1| > ~38.6 (small spread volatility, far from the money), and the Greek is
        // then -0.0. Strict only where phi(d1) is a normal double (same rule as the Rust and Python tests).
        assertTrue(corr01 <= 0.0);
        if (Math.abs(exchangeD1(mk, q1, q2, t)) < 37.0) {
            assertTrue(corr01 < 0.0);
        }
        for (Kind k : List.of(Kind.CALL_1, Kind.PUT_1, Kind.CALL_2, Kind.PUT_2)) {
            double[] g = CorrelationHedge.greeks(mk, vanilla(k, 100, t, null));
            assertEquals(0.0, g[4], 0.0);
            assertEquals(0.0, g[k == Kind.CALL_1 || k == Kind.PUT_1 ? 1 : 0], 0.0);
        }
    }

    /** Margrabe d1 = (ln(F1 / F2) + s^2 t / 2) / (s sqrt(t)), F_i = q_i S_i exp(-y_i t), s the spread volatility. */
    static double exchangeD1(Market mk, double q1, double q2, double t) {
        double s = Math.sqrt(mk.vol1() * mk.vol1() + mk.vol2() * mk.vol2()
                - 2 * mk.correlation() * mk.vol1() * mk.vol2());
        double f1 = q1 * mk.spot1() * Math.exp(-mk.yield1() * t);
        double f2 = q2 * mk.spot2() * Math.exp(-mk.yield2() * t);
        return (Math.log(f1 / f2) + 0.5 * s * s * t) / (s * Math.sqrt(t));
    }

    /**
     * Regression: spot1 = 126.276, spot2 = 50, vols 0.0662 and 0.05, rho 0.9425 give a spread volatility of
     * about 2.5% and d1 near 115 at t = 0.1, so phi(d1) underflows and correlation01 is exactly zero; the
     * same market with spot1 = 52 is near the money and strictly negative. Mirrors the Rust test
     * deep_in_the_money_exchange_correlation01_underflows_to_zero.
     */
    @net.jqwik.api.Example
    void deepInTheMoneyExchangeCorrelation01UnderflowsToZero() {
        Market far = new Market(126.276, 50.0, 0.0, 0.0, 0.0, 0.0662, 0.05, 0.9425);
        assertTrue(exchangeD1(far, 1, 1, 0.1) > 100.0);
        assertEquals(0.0, CorrelationHedge.greeks(far, exchange(1, 1, 0.1, null))[4], 0.0);
        Market near = new Market(52.0, 50.0, 0.0, 0.0, 0.0, 0.0662, 0.05, 0.9425);
        assertTrue(CorrelationHedge.greeks(near, exchange(1, 1, 0.1, null))[4] < 0.0);
    }
}
