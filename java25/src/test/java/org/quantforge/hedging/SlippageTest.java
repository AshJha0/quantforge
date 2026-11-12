package org.quantforge.hedging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import net.jqwik.api.Example;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import org.quantforge.core.QfError;
import org.quantforge.hedging.Slippage.Fill;
import org.quantforge.hedging.Slippage.Order;

/** Wave 4d: the spec's identities as properties, a hand example and every validation path. */
class SlippageTest {

    private static String code(Runnable r) {
        return assertThrows(QfError.class, r::run).code();
    }

    @Property(tries = 200)
    void identitiesHoldPerOrderAndTotalsAreSums(@ForAll long seed) {
        Random rnd = new Random(seed);
        List<Order> orders = new ArrayList<>();
        for (int k = 0; k < 1 + rnd.nextInt(4); k++) {
            double sign = rnd.nextBoolean() ? 1 : -1;
            double q = sign * (100 + rnd.nextInt(1000));
            List<Fill> fills = new ArrayList<>();
            double left = Math.abs(q);
            for (int f = 0; f < rnd.nextInt(4) && left > 1; f++) {
                double size = 1 + rnd.nextInt((int) left);
                left -= size;
                fills.add(new Fill(sign * size, 100 + rnd.nextGaussian()));
            }
            orders.add(new Order(q, 100, 100 + rnd.nextGaussian(), 0.05 * rnd.nextDouble(), 1e-4 * rnd.nextDouble(),
                    fills));
        }
        Slippage.Report r = Slippage.report(orders);
        double[] sum = new double[5];
        for (Slippage.Costs c : r.orders()) {
            assertEquals(c.executionCost() + c.opportunityCost(), c.shortfall(), 1e-9);
            assertEquals(c.executionCost() - c.modelCost(), c.slippage(), 1e-9);
            sum[0] += c.executionCost();
            sum[1] += c.opportunityCost();
            sum[2] += c.shortfall();
            sum[3] += c.modelCost();
            sum[4] += c.slippage();
        }
        Slippage.Costs t = r.total();
        assertEquals(sum[0], t.executionCost(), 1e-9);
        assertEquals(sum[1], t.opportunityCost(), 1e-9);
        assertEquals(sum[2], t.shortfall(), 1e-9);
        assertEquals(sum[3], t.modelCost(), 1e-9);
        assertEquals(sum[4], t.slippage(), 1e-9);
    }

    @Example
    void aSellPartlyFilled() {
        Slippage.Report r = Slippage.report(List.of(new Order(-1000, 50, 49, 0.01, 0.0,
                List.of(new Fill(-600, 49.9)))));
        Slippage.Costs c = r.orders().get(0);
        assertEquals(-600, c.filledQuantity(), 0.0);
        assertEquals(49.9, c.averagePrice(), 1e-12);
        assertEquals(60.0, c.executionCost(), 1e-9); // sold 0.1 below the decision price: a cost
        assertEquals(400.0, c.opportunityCost(), 1e-9); // the rest lost 1.0 per unit
        assertEquals(6.0, c.modelCost(), 1e-12);
        Slippage.Report none = Slippage.report(List.of(new Order(10, 50, 51, 0, 0, List.of())));
        assertNull(none.orders().get(0).averagePrice());
        assertNull(none.total().averagePrice());
    }

    @Example
    void checks() {
        List<Fill> ok = List.of(new Fill(5, 100));
        assertEquals("E_INPUT", code(() -> Slippage.report(List.of())));
        assertEquals("E_INPUT", code(() -> Slippage.report(List.of(new Order(0, 100, 100, 0, 0, List.of())))));
        assertEquals("E_INPUT", code(() -> Slippage.report(List.of(new Order(10, 100, 100, 0, 0,
                List.of(new Fill(-5, 100)))))));
        assertEquals("E_INPUT", code(() -> Slippage.report(List.of(new Order(10, 100, 100, 0, 0,
                List.of(new Fill(0, 100)))))));
        assertEquals("E_INPUT", code(() -> Slippage.report(List.of(new Order(10, 100, 100, 0, 0,
                List.of(new Fill(6, 100), new Fill(5, 100)))))));
        assertEquals("E_DOMAIN", code(() -> Slippage.report(List.of(new Order(10, 0, 100, 0, 0, ok)))));
        assertEquals("E_DOMAIN", code(() -> Slippage.report(List.of(new Order(10, 100, 0, 0, 0, ok)))));
        assertEquals("E_DOMAIN", code(() -> Slippage.report(List.of(new Order(10, 100, 100, 0, 0,
                List.of(new Fill(5, 0)))))));
        assertEquals("E_DOMAIN", code(() -> Slippage.report(List.of(new Order(10, 100, 100, -1, 0, ok)))));
        assertEquals("E_DOMAIN", code(() -> Slippage.report(List.of(new Order(10, 100, 100, 0, -1, ok)))));
    }
}
