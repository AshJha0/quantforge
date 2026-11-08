package org.quantforge.pricing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.vol.Sabr;

/** E4 by properties: strip reprices every cap, node exactness, implied vol round trip, parity (rates-vol-cube.md). */
class RatesVolTest {
    private static final LocalDate T = LocalDate.of(2026, 11, 6);
    private static final Curve CURVE = Curve.of(T, Curve.Interpolation.LOG_LINEAR_DF,
            new LocalDate[] {LocalDate.of(2028, 11, 6), LocalDate.of(2036, 11, 6), LocalDate.of(2046, 11, 6)},
            new double[] {Math.exp(-0.035 * 2), Math.exp(-0.038 * 10), Math.exp(-0.04 * 20)});

    private static String code(Runnable r) {
        return assertThrows(QfError.class, r::run).code();
    }

    private static double[][] fill(double v) {
        return new double[][] {{v, v}, {v, v}};
    }

    @Test
    void stripRepricesEveryCapAtItsFlatVol() {
        long[] tenors = {12, 24, 36};
        double[] flat = {0.25, 0.24, 0.22};
        for (boolean normal : new boolean[] {false, true}) {
            double[] f = normal ? new double[] {0.009, 0.0088, 0.0085} : flat;
            RatesVol.Strip s = RatesVol.strip(CURVE, CURVE, normal, 3, 0.037, tenors, f, 1e7);
            for (int j = 0; j < tenors.length; j++) {
                CapSwaption.Caplets c = CapSwaption.caplets(CURVE, CURVE, 3, tenors[j]);
                double atStripped = 0.0;
                for (int i = 0; i < c.forward().length; i++) {
                    atStripped += c.price(i, normal, true, 0.037, 1e7, s.capletVols()[i]);
                }
                assertEquals(s.capPrices()[j], atStripped, 1e-6);
            }
            assertEquals(f[0], s.capletVols()[0], 1e-12); // first segment is the first flat vol
        }
        assertEquals("E_ARBITRAGE", code(() -> RatesVol.strip(CURVE, CURVE, false, 3, 0.037, tenors,
                new double[] {0.30, 0.10, 0.05}, 1e7)));
        assertEquals("E_INPUT", code(() -> RatesVol.strip(CURVE, CURVE, false, 3, 0.037, new long[] {12, 13},
                new double[] {0.2, 0.2}, 1e7)));
        assertEquals("E_DOMAIN", code(() -> RatesVol.strip(CURVE, CURVE, false, 3, 0.037, new long[] {12},
                new double[] {0.0}, 1e7)));
    }

    @Test
    void cubeAtANodeUsesTheNodeAndOutsideIsRefused() {
        RatesVol.Cube c = new RatesVol.Cube(new long[] {12, 24}, new long[] {24, 60},
                new double[][] {{0.05, 0.048}, {0.047, 0.045}}, fill(0.5),
                new double[][] {{-0.2, -0.25}, {-0.3, -0.35}}, fill(0.4));
        RatesVol.CubePrice r = RatesVol.priceCube(CURVE, CURVE, c, true, 12, 60, 0.037, 1e7);
        assertEquals(0.048, r.sabr().alpha(), 1e-15);
        assertEquals(-0.25, r.sabr().rho(), 1e-15);
        assertEquals(Sabr.hagan(r.forward(), 0.037, CURVE.time(CapSwaption.start(CURVE, 12)), r.sabr()), r.vol(), 0.0);
        RatesVol.CubePrice rec = RatesVol.priceCube(CURVE, CURVE, c, false, 12, 60, 0.037, 1e7);
        assertEquals(1e7 * r.annuity() * (r.forward() - 0.037), r.price() - rec.price(), 1e-6); // put-call parity
        assertEquals("E_INPUT", code(() -> RatesVol.priceCube(CURVE, CURVE, c, true, 6, 60, 0.037, 1e7)));
        assertEquals("E_INPUT", code(() -> RatesVol.priceCube(CURVE, CURVE, c, true, 12, 120, 0.037, 1e7)));
        assertEquals("E_DOMAIN", code(() -> RatesVol.priceCube(CURVE, CURVE, c, true, 12, 60, 0.0, 1e7)));
    }

    @Test
    void futuresImpliedVolRoundTrips() {
        for (double phi : new double[] {1.0, -1.0}) {
            double p = RatesVol.futuresOption(phi, 111.25, 112.0, 0.1, 0.9962, 0.055);
            double[] v = RatesVol.futuresImpliedVol(phi, 111.25, 112.0, 0.1, 0.9962, p, 0.0425, 6.4);
            assertEquals(0.055, v[0], 1e-12);
            assertEquals(0.055 / (6.4 * 0.0425), v[1], 1e-12);
        }
        assertEquals("E_DOMAIN", code(() -> RatesVol.futuresImpliedVol(1.0, 111.25, 112.0, 0.1, 0.9962, 0.0, 0.04, 6)));
        assertEquals("E_DOMAIN", code(() -> RatesVol.futuresOption(1.0, 111.25, 112.0, 0.0, 0.9962, 0.055)));
    }

    @Test
    void inflationCapsCompoundAndSatisfyParity() {
        double[] cap = RatesVol.zcCap(false, true, 1.1268, 5.0, 0.025, 0.8305, 0.028, 1e7);
        double[] floor = RatesVol.zcCap(false, false, 1.1268, 5.0, 0.025, 0.8305, 0.028, 1e7);
        assertEquals(Math.pow(1.025, 5), cap[1], 1e-15);
        assertEquals(1e7 * 0.8305 * (1.1268 - cap[1]), cap[0] - floor[0], 1e-6);
        RatesVol.YoyPeriod[] q = {new RatesVol.YoyPeriod(1.0, 0.96, 0.0285, 0.75, 0.35)};
        double c = RatesVol.yoyCaplets(false, true, 0.03, 1e7, q)[0];
        double f = RatesVol.yoyCaplets(false, false, 0.03, 1e7, q)[0];
        assertEquals(1e7 * 0.96 * (0.0285 - 0.03), c - f, 1e-8);
        assertEquals("E_INPUT", code(() -> RatesVol.yoyCaplets(false, true, 0.03, 1e7, new RatesVol.YoyPeriod[0])));
        assertEquals("E_DOMAIN", code(() -> RatesVol.yoyCaplets(false, true, 0.0, 1e7, q)));
        assertEquals("E_DOMAIN", code(() -> RatesVol.zcCap(false, true, 1.1, 0.0, 0.02, 0.9, 0.03, 1e7)));
    }
}
