package org.quantforge.pricing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.vol.Black;

/** E4 boundaries, one per rule of rates-vol-cube.md and rulings E-B8 to E-B13, E-B32, E-B37, E-B38. */
class RatesVolBoundaryTest {
    private static final LocalDate T = LocalDate.of(2026, 11, 6);
    private static final Curve CURVE = Curve.of(T, Curve.Interpolation.LOG_LINEAR_DF,
            new LocalDate[] {LocalDate.of(2028, 11, 6), LocalDate.of(2036, 11, 6), LocalDate.of(2046, 11, 6)},
            new double[] {Math.exp(-0.035 * 2), Math.exp(-0.038 * 10), Math.exp(-0.04 * 20)});

    private static String code(Runnable r) {
        return assertThrows(QfError.class, r::run).code();
    }

    private static double[][] grid(double a, double b, double c, double d) {
        return new double[][] {{a, b}, {c, d}};
    }

    private static RatesVol.Cube cube(double[][] alpha, double[][] beta, double[][] rho, double[][] nu) {
        return new RatesVol.Cube(new long[] {12, 24}, new long[] {24, 60}, alpha, beta, rho, nu);
    }

    private static final double[][] A = grid(0.05, 0.048, 0.047, 0.045);
    private static final double[][] B = grid(0.5, 0.5, 0.5, 0.5);
    private static final double[][] R = grid(-0.2, -0.25, -0.3, -0.35);
    private static final double[][] N = grid(0.4, 0.4, 0.4, 0.4);

    private static RatesVol.CubePrice price(RatesVol.Cube c, long e, long l, double k) {
        return RatesVol.priceCube(CURVE, CURVE, c, true, e, l, k, 1e7);
    }

    @Test
    void cubeShapeAndNodeRules() {
        RatesVol.Cube base = cube(A, B, R, N);
        assertEquals("E_INPUT", code(() -> price(new RatesVol.Cube(new long[] {12, 12}, new long[] {24, 60}, A, B, R,
                N), 12, 60, 0.037)));
        assertEquals("E_INPUT", code(() -> price(new RatesVol.Cube(new long[] {12, 24}, new long[] {60, 60}, A, B, R,
                N), 12, 60, 0.037)));
        assertEquals("E_INPUT", code(() -> price(new RatesVol.Cube(new long[0], new long[] {24, 60}, A, B, R, N), 12,
                60, 0.037)));
        double[][] ragged = {{0.5, 0.5}, {0.5}};
        double[][] tall = {{0.5, 0.5}, {0.5, 0.5}, {0.5, 0.5}};
        assertEquals("E_INPUT", code(() -> price(cube(tall, B, R, N), 12, 60, 0.037)));
        assertEquals("E_INPUT", code(() -> price(cube(A, ragged, R, N), 12, 60, 0.037)));
        assertEquals("E_INPUT", code(() -> price(cube(A, B, ragged, N), 12, 60, 0.037)));
        assertEquals("E_INPUT", code(() -> price(cube(A, B, R, ragged), 12, 60, 0.037)));
        assertEquals("E_INPUT", code(() -> price(base, 0, 60, 0.037)));
        assertEquals("E_INPUT", code(() -> price(base, 1201, 60, 0.037)));
        assertEquals("E_INPUT", code(() -> price(base, 12, 0, 0.037)));
        assertEquals("E_INPUT", code(() -> price(base, 12, 1201, 0.037)));
        assertEquals("E_DOMAIN", code(() -> price(base, 12, 60, 0.0)));
    }

    @Test
    void cubeParameterDomainEdges() {
        assertEquals("E_DOMAIN", code(() -> price(cube(grid(0.0, 0.048, 0.047, 0.045), B, R, N), 12, 60, 0.037)));
        assertEquals("E_DOMAIN", code(() -> price(cube(A, grid(1.0000001, 0.5, 0.5, 0.5), R, N), 12, 60, 0.037)));
        assertEquals("E_DOMAIN", code(() -> price(cube(A, grid(-1e-9, 0.5, 0.5, 0.5), R, N), 12, 60, 0.037)));
        assertEquals("E_DOMAIN", code(() -> price(cube(A, B, grid(1.0, -0.25, -0.3, -0.35), N), 12, 60, 0.037)));
        assertEquals("E_DOMAIN", code(() -> price(cube(A, B, grid(-1.0, -0.25, -0.3, -0.35), N), 12, 60, 0.037)));
        assertEquals("E_DOMAIN", code(() -> price(cube(A, B, R, grid(-1e-9, 0.4, 0.4, 0.4)), 12, 60, 0.037)));
        // the closed edges are allowed: beta 0 and 1, nu 0
        price(cube(A, grid(0.0, 1.0, 0.0, 1.0), R, grid(0.0, 0.0, 0.0, 0.0)), 12, 60, 0.037);
    }

    @Test
    void cubeInterpolatesInTimeAndOnASingleNodeAxis() {
        // at the last expiry node and the last tenor node the parameters are that node's
        RatesVol.CubePrice corner = price(cube(A, B, R, N), 24, 60, 0.037);
        assertEquals(0.045, corner.sabr().alpha(), 1e-15);
        assertEquals(-0.35, corner.sabr().rho(), 1e-15);
        // a tenor between nodes: linear in tenor years
        RatesVol.CubePrice mid = price(cube(A, B, R, N), 12, 42, 0.037);
        assertEquals(0.049, mid.sabr().alpha(), 1e-15);
        // one node per axis: the node itself, at its own expiry and tenor only
        RatesVol.Cube one = new RatesVol.Cube(new long[] {12}, new long[] {60}, new double[][] {{0.048}},
                new double[][] {{0.5}}, new double[][] {{-0.27}}, new double[][] {{0.44}});
        RatesVol.CubePrice p = price(one, 12, 60, 0.037);
        assertEquals(0.048, p.sabr().alpha(), 0.0);
        assertEquals(0.44, p.sabr().nu(), 0.0);
        assertEquals("E_INPUT", code(() -> price(one, 12, 61, 0.037)));
        // three expiry nodes: a point in the last interval
        RatesVol.Cube three = new RatesVol.Cube(new long[] {6, 12, 24}, new long[] {24, 60},
                new double[][] {{0.06, 0.06}, {0.05, 0.05}, {0.04, 0.04}}, grid3(0.5), grid3(-0.3), grid3(0.4));
        double a = price(three, 18, 60, 0.037).sabr().alpha();
        assertEquals(true, a > 0.04 && a < 0.05);
    }

    private static double[][] grid3(double v) {
        return new double[][] {{v, v}, {v, v}, {v, v}};
    }

    @Test
    void stripScheduleAndSearchBounds() {
        long[] t = {12, 24};
        assertEquals("E_INPUT", code(() -> RatesVol.strip(CURVE, CURVE, false, 3, 0.037, new long[] {0},
                new double[] {0.2}, 1e7)));
        assertEquals("E_INPUT", code(() -> RatesVol.strip(CURVE, CURVE, false, 3, 0.037, new long[] {12, 12},
                new double[] {0.2, 0.2}, 1e7)));
        assertEquals("E_INPUT", code(() -> RatesVol.strip(CURVE, CURVE, false, 0, 0.037, t,
                new double[] {0.2, 0.2}, 1e7)));
        assertEquals("E_INPUT", code(() -> RatesVol.strip(CURVE, CURVE, false, 1201, 0.037, t,
                new double[] {0.2, 0.2}, 1e7)));
        assertEquals("E_INPUT", code(() -> RatesVol.strip(CURVE, CURVE, false, 3, 0.037, new long[] {1203},
                new double[] {0.2}, 1e7)));
        assertEquals("E_INPUT", code(() -> RatesVol.strip(CURVE, CURVE, false, 3, 0.037, new long[0],
                new double[0], 1e7)));
        // a first cap of 3 months and start 1 month are allowed
        RatesVol.Strip s = RatesVol.strip(CURVE, CURVE, false, 1, 0.037, new long[] {3, 6}, new double[] {0.2, 0.21},
                1e7);
        assertEquals(0.2, s.capletVols()[0], 1e-10);
        // BLACK_76 with a strike at or below 0 is D7's E_DOMAIN
        assertEquals("E_DOMAIN", code(() -> RatesVol.strip(CURVE, CURVE, false, 3, 0.0, t,
                new double[] {0.2, 0.2}, 1e7)));
        // Bachelier's upper bound is 0.5 (ruling E-B32): a normal vol needing more is E_DOMAIN
        assertEquals("E_DOMAIN", code(() -> RatesVol.strip(CURVE, CURVE, true, 3, 0.037, t,
                new double[] {0.009, 0.8}, 1e7)));
        RatesVol.Strip n = RatesVol.strip(CURVE, CURVE, true, 3, 0.037, t, new double[] {0.2, 0.3}, 1e7);
        assertEquals(true, n.capletVols()[7] > 0.3 && n.capletVols()[7] < 0.5);
    }

    @Test
    void futuresBoundsAndBracket() {
        assertEquals("E_DOMAIN", code(() -> RatesVol.futuresOption(1, 0.0, 112, 0.1, 0.99, 0.05)));
        assertEquals("E_DOMAIN", code(() -> RatesVol.futuresOption(1, 111, 0.0, 0.1, 0.99, 0.05)));
        assertEquals("E_DOMAIN", code(() -> RatesVol.futuresOption(1, 111, 112, 0.1, 0.0, 0.05)));
        assertEquals("E_DOMAIN", code(() -> RatesVol.futuresOption(1, 111, 112, 0.1, 0.99, -1e-9)));
        assertEquals(0.99 * 0.0, RatesVol.futuresOption(1, 111, 112, 0.1, 0.99, 0.0), 0.0); // vol 0: intrinsic
        assertEquals("E_DOMAIN", code(() -> RatesVol.futuresImpliedVol(1, 111, 112, 0.0, 0.99, 1.0, 0.04, 6)));
        // the put's upper bound is D K, the call's D F; intrinsic itself is refused
        assertEquals("E_DOMAIN", code(() -> RatesVol.futuresImpliedVol(-1, 111, 112, 0.1, 0.99, 0.99 * 112, 0.04, 6)));
        assertEquals("E_DOMAIN", code(() -> RatesVol.futuresImpliedVol(1, 111, 112, 0.1, 0.99, 0.99 * 111, 0.04, 6)));
        assertEquals("E_DOMAIN", code(() -> RatesVol.futuresImpliedVol(-1, 111, 112, 0.1, 0.99, 0.99, 0.04, 6)));
        double nearBound = Black.lognormal(-1, 111, 112, 0.1, 0.99, 3.0);
        assertEquals(3.0, RatesVol.futuresImpliedVol(-1, 111, 112, 0.1, 0.99, nearBound, 0.04, 6)[0], 1e-9);
        double p = RatesVol.futuresOption(1, 111, 112, 0.1, 0.99, 0.06);
        assertEquals("E_DOMAIN", code(() -> RatesVol.futuresImpliedVol(1, 111, 112, 0.1, 0.99, p, 0.0, 6)));
        assertEquals("E_DOMAIN", code(() -> RatesVol.futuresImpliedVol(1, 111, 112, 0.1, 0.99, p, 0.04, 0.0)));
    }

    @Test
    void inflationEdges() {
        RatesVol.YoyPeriod ok = new RatesVol.YoyPeriod(1.0, 0.96, 0.0285, 0.75, 0.35);
        double full = RatesVol.yoyCaplets(false, true, 0.03, 1e7, new RatesVol.YoyPeriod[] {ok})[0];
        double quarter = RatesVol.yoyCaplets(false, true, 0.03, 1e7,
                new RatesVol.YoyPeriod[] {new RatesVol.YoyPeriod(0.25, 0.96, 0.0285, 0.75, 0.35)})[0];
        assertEquals(full / 4, quarter, 1e-9);
        assertEquals("E_DOMAIN", code(() -> RatesVol.yoyCaplets(false, true, 0.03, 1e7,
                new RatesVol.YoyPeriod[] {new RatesVol.YoyPeriod(1.0, 0.96, 0.0, 0.75, 0.35)})));
        assertEquals("E_DOMAIN", code(() -> RatesVol.yoyCaplets(false, true, 0.03, 1e7,
                new RatesVol.YoyPeriod[] {new RatesVol.YoyPeriod(1.0, 0.96, 0.0285, 0.0, 0.35)})));
        assertEquals("E_DOMAIN", code(() -> RatesVol.yoyCaplets(false, true, 0.03, 1e7,
                new RatesVol.YoyPeriod[] {new RatesVol.YoyPeriod(1.0, 0.96, 0.0285, 0.75, -1e-9)})));
        // Bachelier takes a zero strike (a YoY floor at 0%)
        RatesVol.yoyCaplets(true, false, 0.0, 1e7, new RatesVol.YoyPeriod[] {new RatesVol.YoyPeriod(1, 0.96, 0.01, 1,
                0.01)});
        assertEquals("E_DOMAIN", code(() -> RatesVol.zcCap(false, true, 0.0, 5, 0.02, 0.9, 0.03, 1e7)));
        assertEquals("E_DOMAIN", code(() -> RatesVol.zcCap(false, true, 1.1, 5, -1.0, 0.9, 0.03, 1e7)));
        assertEquals("E_DOMAIN", code(() -> RatesVol.zcCap(false, true, 1.1, 5, 0.02, 0.9, -1e-9, 1e7)));
        // a negative strike with 1 + K > 0 is priced; vol 0 is discounted intrinsic
        double[] neg = RatesVol.zcCap(false, true, 1.1, 5, -0.01, 0.9, 0.0, 1e7);
        assertEquals(1e7 * 0.9 * (1.1 - Math.pow(0.99, 5)), neg[0], 1e-6);
        // Bachelier with a forward ratio of 0 is allowed
        RatesVol.zcCap(true, true, 0.0, 5, 0.02, 0.9, 0.03, 1e7);
    }
}
