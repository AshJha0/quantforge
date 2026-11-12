package org.quantforge.hedging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;
import org.quantforge.hedging.CrossAssetHedge.Instrument;
import org.quantforge.hedging.CrossAssetHedge.Kind;
import org.quantforge.hedging.CrossAssetHedge.Market;

/** Wave 3 cross-asset hedge: hand checks of the risk definitions and every validation path. */
class CrossAssetHedgeTest {
    static final Market MK = new Market(100, 0.02, 0.25, new double[] {1, 2, 5, 10},
            new double[] {0.03, 0.032, 0.035, 0.037});

    static Instrument of(Kind kind, Double quantity, Object... kv) {
        Map<String, Double> v = new HashMap<>();
        for (int i = 0; i < kv.length; i += 2) {
            v.put((String) kv[i], ((Number) kv[i + 1]).doubleValue());
        }
        if (quantity != null) {
            v.put("quantity", quantity);
        }
        return new Instrument(kind, v, false);
    }

    static Instrument zcb(double t, double notional, Double qty) {
        return of(Kind.ZCB, qty, "expiry_years", t, "notional", notional);
    }

    private static String code(Runnable r) {
        return assertThrows(QfError.class, r::run).code();
    }

    @Test
    void curveIsLinearInZeroRateAndFlatBeforeTheFirstPillar() {
        assertEquals(0.03, MK.zero(0.5, MK.zeroRates()), 0.0);
        assertEquals(0.0335, MK.zero(3.5, MK.zeroRates()), 1e-15);
        assertEquals(0.037, MK.zero(10, MK.zeroRates()), 0.0);
    }

    @Test
    void keyRateRiskSplitsBetweenNeighboursAndStaysOnPillarOneAtTheShortEnd() {
        double[] r = CrossAssetHedge.risk(MK, zcb(3.5, 100, null));
        assertEquals(0.0, r[0], 0.0);
        assertEquals(0.0, r[1], 0.0);
        assertEquals(0.0, r[4], 0.0);
        double p = 100 * Math.exp(-MK.zero(3.5, MK.zeroRates()) * 3.5);
        assertEquals(-p * 3.5 * 1e-4 * 0.5, r[2], 1e-9);
        assertEquals(r[2], r[3], 1e-9);
        double[] s = CrossAssetHedge.risk(MK, zcb(0.5, 100, null));
        assertEquals(0.0, s[2] + s[3] + s[4], 0.0);
        assertEquals(-100 * Math.exp(-0.015) * 0.5 * 1e-4, s[1], 1e-10);
    }

    @Test
    void forwardAndUnderlyingRisks() {
        double[] f = CrossAssetHedge.risk(MK, of(Kind.FORWARD, null, "strike", 100, "expiry_years", 2));
        assertEquals(Math.exp(-0.04), f[0], 1e-13); // S e^{-qT} per 1%: (1.01 - 0.99) S e^{-qT} / 2
        double[] u = CrossAssetHedge.risk(MK, of(Kind.UNDERLYING, null));
        assertEquals(1.0, u[0], 1e-13);
        assertEquals(0.0, u[1] + u[2] + u[3] + u[4], 0.0);
        double[] c = CrossAssetHedge.risk(MK, of(Kind.CALL, null, "strike", 100, "expiry_years", 1));
        double[] p = CrossAssetHedge.risk(MK, of(Kind.PUT, null, "strike", 100, "expiry_years", 1));
        // Put-call parity: call - put = forward, so the risks differ by the forward's.
        double[] fw = CrossAssetHedge.risk(MK, of(Kind.FORWARD, null, "strike", 100, "expiry_years", 1));
        for (int k = 0; k < 5; k++) {
            assertEquals(fw[k], c[k] - p[k], 1e-12);
        }
    }

    @Test
    void squareHedgeLeavesNoResidualAndBondsAloneHaveNoEquityRisk() {
        List<Instrument> book = List.of(of(Kind.CALL, -100.0, "strike", 105, "expiry_years", 3));
        List<Instrument> hedges = List.of(of(Kind.FORWARD, null, "strike", 100, "expiry_years", 3), zcb(1, 100, null),
                zcb(2, 100, null), zcb(5, 100, null), zcb(10, 100, null));
        CrossAssetHedge.Result r = CrossAssetHedge.solve(MK, book, hedges, new double[] {1, 1, 1, 1, 1}, 0.0);
        for (double v : r.residualRisk()) {
            assertEquals(0.0, v, 1e-9);
        }
        CrossAssetHedge.Result bonds = CrossAssetHedge.solve(MK, List.of(zcb(4, 100, 10.0)),
                List.of(zcb(5, 100, null)), new double[] {1, 1, 1, 1, 1}, 0.0);
        assertEquals(0.0, bonds.bookRisk()[0], 0.0);
    }

    @Test
    void scalingEveryWeightLeavesThePositions() {
        List<Instrument> book = List.of(of(Kind.PUT, 50.0, "strike", 95, "expiry_years", 4),
                of(Kind.FORWARD, -20.0, "strike", 90, "expiry_years", 7));
        List<Instrument> hedges = List.of(of(Kind.UNDERLYING, null), zcb(2, 100, null), zcb(10, 100, null));
        double[] w = {3, 1, 2, 0.5, 1};
        double[] w7 = {21, 7, 14, 3.5, 7};
        double[] a = CrossAssetHedge.solve(MK, book, hedges, w, 0).positions();
        double[] b = CrossAssetHedge.solve(MK, book, hedges, w7, 0).positions();
        for (int j = 0; j < a.length; j++) {
            assertEquals(a[j], b[j], 1e-10 * Math.max(1, Math.abs(a[j])));
        }
    }

    private static String xa(Market mk, List<Instrument> book, List<Instrument> hedges, double[] w, double ridge) {
        return code(() -> CrossAssetHedge.solve(mk, book, hedges, w, ridge));
    }

    @Test
    void checksRunInTheSpecifiedOrder() {
        List<Instrument> book = List.of(zcb(4, 100, 1.0));
        List<Instrument> hedges = List.of(zcb(5, 100, null));
        double[] w = {1, 1, 1, 1, 1};
        assertEquals("E_INPUT", xa(new Market(100, 0, 0.2, new double[0], new double[0]), book, hedges,
                new double[] {1}, 0));
        assertEquals("E_INPUT", xa(new Market(100, 0, 0.2, new double[] {1, 2}, new double[] {0.01}), book, hedges,
                w, 0));
        assertEquals("E_INPUT", xa(new Market(100, 0, 0.2, new double[] {0, 2}, new double[] {0.01, 0.02}), book,
                hedges, new double[] {1, 1, 1}, 0));
        assertEquals("E_INPUT", xa(new Market(100, 0, 0.2, new double[] {2, 2}, new double[] {0.01, 0.02}), book,
                hedges, new double[] {1, 1, 1}, 0));
        assertEquals("E_INPUT", xa(MK, List.of(zcb(4, 100, null)), hedges, w, 0));
        assertEquals("E_INPUT", xa(MK, book, List.of(zcb(4, 100, 1.0)), w, 0));
        assertEquals("E_INPUT", xa(MK, book, List.of(new Instrument(Kind.UNDERLYING, Map.of(), true)), w, 0));
        assertEquals("E_INPUT", xa(MK, List.of(), hedges, w, 0));
        assertEquals("E_INPUT", xa(MK, book, List.of(), w, 0));
        assertEquals("E_INPUT", xa(MK, book, hedges, new double[] {1, 1}, 0));
        assertEquals("E_INPUT", xa(MK, book, List.of(zcb(11, 100, null)), w, 0));
        assertEquals("E_DOMAIN", xa(new Market(0, 0, 0.2, MK.times(), MK.zeroRates()), book, hedges, w, 0));
        assertEquals("E_DOMAIN", xa(new Market(100, 0, 0, MK.times(), MK.zeroRates()), book, hedges, w, 0));
        assertEquals("E_DOMAIN", xa(MK, book, hedges, new double[] {1, 0, 1, 1, 1}, 0));
        assertEquals("E_DOMAIN", xa(MK, book, hedges, w, -1));
        assertEquals("E_DOMAIN", xa(MK, book, List.of(zcb(5, 0, null)), w, 0));
        assertEquals("E_DOMAIN", xa(MK, book, List.of(of(Kind.CALL, null, "strike", -1, "expiry_years", 1)), w, 0));
        assertEquals("E_SINGULAR", xa(MK, book, List.of(zcb(5, 100, null), zcb(5, 100, null)), w, 0));
    }
}
