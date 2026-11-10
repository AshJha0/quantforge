package org.quantforge.curves;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;

/** Q1: returns its nodes, locality and continuity on pillars (ruling F-22), limits, and the parameter checks. */
class SmoothCurveTest {
    private static final double[] T = {0, 0.1, 0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30};
    private static final double[] Y = {0.043, 0.0425, 0.0412, 0.039, 0.0365, 0.0355, 0.0352, 0.0356, 0.0364,
        0.0376, 0.038, 0.0368};

    private static double[] logs(int bumpAt) {
        double[] ln = new double[T.length];
        for (int i = 1; i < T.length; i++) {
            ln[i] = ln[i - 1] - Y[i - 1] * (T[i] - T[i - 1]) + (i == bumpAt ? 1e-4 : 0.0);
        }
        return ln;
    }

    private static SmoothCurve build(Curve.Interpolation m, double[] ln) {
        return SmoothCurve.of(m, T, ln, 0.5, 4);
    }

    @Test
    void returnsEveryNode() {
        for (Curve.Interpolation m : new Curve.Interpolation[] {Curve.Interpolation.MONOTONE_CONVEX,
            Curve.Interpolation.MONOTONIC_LOG_CUBIC, Curve.Interpolation.TENSION_SPLINE, Curve.Interpolation.HYBRID}) {
            double[] ln = logs(-1);
            SmoothCurve c = build(m, ln);
            for (int i = 0; i < T.length; i++) {
                assertEquals(ln[i], c.lnAt(T[i]), 1e-15, m + " node " + i);
            }
        }
    }

    @Test
    void forwardContinuousAtInteriorPillars() {
        for (Curve.Interpolation m : new Curve.Interpolation[] {Curve.Interpolation.MONOTONE_CONVEX,
            Curve.Interpolation.MONOTONIC_LOG_CUBIC, Curve.Interpolation.TENSION_SPLINE}) {
            SmoothCurve c = build(m, logs(-1));
            for (int i = 1; i < T.length - 1; i++) {
                double left = c.forwardAt(Math.nextDown(T[i]));
                assertEquals(left, c.forwardAt(T[i]), 1e-11, m + " pillar " + i);
            }
        }
    }

    @Test
    void monotoneConvexIsLocalOnPillars() {
        int j = 6;
        SmoothCurve a = build(Curve.Interpolation.MONOTONE_CONVEX, logs(-1));
        SmoothCurve b = build(Curve.Interpolation.MONOTONE_CONVEX, logs(j));
        for (double x = 0.0; x < 30.0; x += 0.01) {
            int section = a.section(x) + 1; // 1-based section index
            if (section < j - 1 || section > j + 2) {
                assertEquals(a.forwardAt(x), b.forwardAt(x), 1e-15, "t = " + x);
            }
        }
    }

    @Test
    void hybridStepsAreUntouchedByLaterPillars() {
        SmoothCurve a = build(Curve.Interpolation.HYBRID, logs(-1));
        SmoothCurve b = build(Curve.Interpolation.HYBRID, logs(8));
        for (double x = 0.0; x < T[4]; x += 0.001) {
            assertEquals(a.forwardAt(x), b.forwardAt(x), 0.0);
            assertEquals(a.lnAt(x), b.lnAt(x), 0.0);
        }
    }

    @Test
    void tensionLimits() {
        double[] ln = logs(-1);
        SmoothCurve loose = SmoothCurve.of(Curve.Interpolation.TENSION_SPLINE, T, ln, 1e-6, 0);
        SmoothCurve looser = SmoothCurve.of(Curve.Interpolation.TENSION_SPLINE, T, ln, 1e-5, 0);
        SmoothCurve stiff = SmoothCurve.of(Curve.Interpolation.TENSION_SPLINE, T, ln, 1000, 0);
        for (double x = 0.05; x < 30; x += 0.37) {
            assertEquals(loose.lnAt(x), looser.lnAt(x), 1e-12);
            int i = stiff.section(x);
            double u = (x - T[i]) / (T[i + 1] - T[i]);
            assertEquals((1 - u) * ln[i] + u * ln[i + 1], stiff.lnAt(x), 1e-5);
        }
    }

    @Test
    void flatForwardsGiveAFlatCurve() {
        double[] ln = new double[T.length];
        for (int i = 1; i < T.length; i++) {
            ln[i] = -0.03 * T[i];
        }
        SmoothCurve c = build(Curve.Interpolation.MONOTONE_CONVEX, ln);
        for (double x = 0.0; x < 30.0; x += 0.5) {
            assertEquals(0.03, c.forwardAt(x), 1e-14);
        }
        assertEquals(0.03, c.lastForward(), 1e-14);
    }

    @Test
    void shapeChecksAtTheirEdges() {
        LocalDate[] dates = {LocalDate.of(2027, 1, 1), LocalDate.of(2028, 1, 1)};
        assertEquals("E_INPUT", assertThrows(QfError.class,
                () -> Curve.Shape.NONE.check(Curve.Interpolation.TENSION_SPLINE, dates)).code());
        assertEquals("E_DOMAIN", assertThrows(QfError.class,
                () -> new Curve.Shape(0.0, null).check(Curve.Interpolation.TENSION_SPLINE, dates)).code());
        assertEquals("E_DOMAIN", assertThrows(QfError.class,
                () -> new Curve.Shape(Math.nextUp(1000.0), null).check(Curve.Interpolation.TENSION_SPLINE, dates))
                .code());
        new Curve.Shape(1000.0, null).check(Curve.Interpolation.TENSION_SPLINE, dates);
        new Curve.Shape(Double.MIN_VALUE, null).check(Curve.Interpolation.TENSION_SPLINE, dates);
        assertEquals("E_INPUT", assertThrows(QfError.class,
                () -> new Curve.Shape(null, LocalDate.of(2027, 1, 2)).check(Curve.Interpolation.HYBRID, dates)).code());
        new Curve.Shape(null, dates[1]).check(Curve.Interpolation.HYBRID, dates);
        Curve.Shape.NONE.check(Curve.Interpolation.MONOTONE_CONVEX, dates); // ignored by the other methods
        assertTrue(Curve.Interpolation.HYBRID.smooth() && !Curve.Interpolation.LINEAR_ZERO.smooth());
    }
}
