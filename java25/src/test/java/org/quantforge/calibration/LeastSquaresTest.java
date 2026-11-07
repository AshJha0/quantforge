package org.quantforge.calibration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.quantforge.calibration.LeastSquares.Method;
import org.quantforge.calibration.LeastSquares.Model;
import org.quantforge.calibration.LeastSquares.Problem;
import org.quantforge.core.QfError;

/** Input checks, exact fits and the bid/ask check of the stage C least-squares fitter. */
class LeastSquaresTest {
    private static final double[] X = {0.0, 1.0, 2.0, 3.0};
    private static final double[] Y = {1.0, 3.0, 5.0, 7.0}; // y = 1 + 2x

    private static Problem linear(Method m, double[] weights, double reg, double[] prior, double[] lo, double[] hi,
                                  long maxIter) {
        return new Problem(Model.LINEAR, X, Y, new double[] {0.0, 0.0}, m, weights, reg, prior, lo, hi, maxIter);
    }

    private static String code(Problem p) {
        return assertThrows(QfError.class, () -> LeastSquares.fit(p)).code();
    }

    @ParameterizedTest
    @EnumSource(Method.class)
    void exactLineIsFittedByEveryMethod(Method m) {
        LeastSquares.Fit f = LeastSquares.fit(linear(m, null, 0.0, null, null, null, 1000));
        assertTrue(f.objective() < 1e-18, m + " objective " + f.objective());
        for (double r : f.residuals()) {
            assertEquals(0.0, r, 1e-9);
        }
    }

    @Test
    void priorAtTheTruthKeepsTheFitExact() {
        LeastSquares.Fit free = LeastSquares.fit(linear(Method.GAUSS_NEWTON, null, 0.0, null, null, null, 1000));
        LeastSquares.Fit held = LeastSquares.fit(
                linear(Method.GAUSS_NEWTON, null, 0.5, free.parameters(), null, null, 1000));
        assertEquals(free.parameters()[0], held.parameters()[0], 1e-9);
        assertEquals(free.parameters()[1], held.parameters()[1], 1e-9);
    }

    @Test
    void inputChecksGiveTheListedCodes() {
        double[] two = {0.0, 0.0};
        assertEquals("E_INPUT", code(linear(Method.GAUSS_NEWTON, new double[] {1.0}, 0, null, null, null, 10)));
        assertEquals("E_INPUT", code(linear(Method.GAUSS_NEWTON, null, 0, null, null, null, 0)));
        assertEquals("E_INPUT", code(linear(Method.GAUSS_NEWTON, null, 0, new double[] {1.0}, null, null, 10)));
        assertEquals("E_INPUT", code(linear(Method.BFGS, null, 0, null, two, null, 10)));
        assertEquals("E_INPUT", code(linear(Method.LEVENBERG_MARQUARDT, null, 0, null, new double[] {0}, null, 10)));
        assertEquals("E_INPUT", code(linear(Method.LEVENBERG_MARQUARDT, null, 0, null, new double[] {1, 1}, two, 10)));
        assertEquals("E_DOMAIN", code(linear(Method.GAUSS_NEWTON, new double[] {1, -1, 1, 1}, 0, null, null, null, 10)));
        assertEquals("E_DOMAIN", code(linear(Method.GAUSS_NEWTON, null, -1.0, null, null, null, 10)));
    }

    @Test
    void boundsHoldTheFitInsideTheBox() {
        LeastSquares.Fit f = LeastSquares.fit(linear(Method.LEVENBERG_MARQUARDT, null, 0.0, null,
                new double[] {-10.0, -10.0}, new double[] {1.5, 1.5}, 1000));
        for (double p : f.parameters()) {
            assertTrue(p <= 1.5 + 1e-12 && p >= -10.0, "parameter " + p);
        }
        assertTrue(f.objective() > 0.0);
    }

    @Test
    void bidAskReportsBothSidesAndRejectsMismatchedLengths() {
        List<LeastSquares.Breach> b = LeastSquares.checkBidAsk(
                new double[] {0.5, 1.5, 3.5}, new double[] {1, 1, 1}, new double[] {2, 2, 2});
        assertEquals(2, b.size());
        assertEquals(new LeastSquares.Breach(0, "BID", 0.5), b.get(0));
        assertEquals(new LeastSquares.Breach(2, "ASK", 1.5), b.get(1));
        assertEquals("E_INPUT", assertThrows(QfError.class,
                () -> LeastSquares.checkBidAsk(new double[2], new double[2], new double[1])).code());
    }
}
