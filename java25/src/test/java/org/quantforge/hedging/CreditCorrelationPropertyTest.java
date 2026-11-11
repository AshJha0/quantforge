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
        assertTrue(CorrelationHedge.greeks(mk, exchange(0.5 + rnd.nextDouble(), 0.5 + rnd.nextDouble(), t, null))[4]
                < 0.0);
        for (Kind k : List.of(Kind.CALL_1, Kind.PUT_1, Kind.CALL_2, Kind.PUT_2)) {
            double[] g = CorrelationHedge.greeks(mk, vanilla(k, 100, t, null));
            assertEquals(0.0, g[4], 0.0);
            assertEquals(0.0, g[k == Kind.CALL_1 || k == Kind.PUT_1 ? 1 : 0], 0.0);
        }
    }
}
