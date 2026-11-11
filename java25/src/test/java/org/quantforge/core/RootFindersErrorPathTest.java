package org.quantforge.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.DoubleUnaryOperator;
import org.junit.jupiter.api.Test;
import org.quantforge.core.RootFinders.Termination;
import org.quantforge.core.RootFinders.Tolerances;

/** Error paths and exact-root shortcuts of the three root-finders. */
class RootFindersErrorPathTest {
    private static final Tolerances TOL = new Tolerances(1e-12, 0.0, 100);
    private static final DoubleUnaryOperator LINE = x -> x - 1.0;

    private static void code(String expected, Runnable r) {
        assertEquals(expected, assertThrows(QfError.class, r::run).code());
    }

    @Test
    void badToleranceRejected() {
        code("E_INPUT", () -> RootFinders.bisection(LINE, 0, 2, new Tolerances(0.0, 0.0, 10)));
        code("E_INPUT", () -> RootFinders.brent(LINE, 0, 2, new Tolerances(1e-9, -1.0, 10)));
        code("E_INPUT", () -> RootFinders.newton(LINE, x -> 1.0, 0.5, null, null, new Tolerances(1e-9, 0.0, 0)));
    }

    @Test
    void badBracketRejected() {
        code("E_INPUT", () -> RootFinders.bisection(LINE, 2, 0, TOL));
        code("E_INPUT", () -> RootFinders.brent(LINE, 1, 1, TOL));
        code("E_INPUT", () -> RootFinders.newton(LINE, x -> 1.0, 1.0, 3.0, 2.0, TOL));
    }

    @Test
    void notBracketedRejected() {
        code("E_NOT_BRACKETED", () -> RootFinders.bisection(LINE, 2, 3, TOL));
        code("E_NOT_BRACKETED", () -> RootFinders.brent(LINE, 2, 3, TOL));
        code("E_NOT_BRACKETED", () -> RootFinders.newton(LINE, x -> 1.0, 2.5, 2.0, 3.0, TOL));
    }

    @Test
    void nonFiniteFunctionRejected() {
        code("E_NON_FINITE", () -> RootFinders.bisection(x -> Double.NaN, 0, 1, TOL));
        code("E_NON_FINITE", () -> RootFinders.brent(x -> Double.POSITIVE_INFINITY, 0, 1, TOL));
        code("E_NON_FINITE", () -> RootFinders.newton(LINE, x -> Double.NaN, 0.5, null, null, TOL));
    }

    @Test
    void endpointRootsAreExact() {
        assertEquals(Termination.EXACT, RootFinders.bisection(LINE, 1, 3, TOL).termination());
        assertEquals(Termination.EXACT, RootFinders.bisection(LINE, -1, 1, TOL).termination());
        assertEquals(Termination.EXACT, RootFinders.brent(LINE, 1, 3, TOL).termination());
        assertEquals(Termination.EXACT, RootFinders.brent(LINE, -1, 1, TOL).termination());
        assertEquals(0, RootFinders.brent(LINE, -1, 1, TOL).iterations());
    }

    @Test
    void bisectionMidpointExact() {
        RootFinders.Result r = RootFinders.bisection(LINE, 0, 2, TOL);
        assertEquals(Termination.EXACT, r.termination());
        assertEquals(1.0, r.root());
    }

    @Test
    void noConvergenceWhenIterationsExhausted() {
        Tolerances t = new Tolerances(1e-300, 0.0, 3);
        code("E_NO_CONVERGENCE", () -> RootFinders.bisection(x -> x - 0.3, 0, 1, t));
        code("E_NO_CONVERGENCE", () -> RootFinders.newton(x -> x * x * x - 2, x -> 3 * x * x, 5.0, null, null,
            new Tolerances(1e-300, 0.0, 2)));
    }

    @Test
    void newtonZeroDerivativeAndOutsideX0() {
        code("E_ZERO_DERIVATIVE", () -> RootFinders.newton(x -> x * x - 1, x -> 0.0, 3.0, null, null, TOL));
        code("E_INPUT", () -> RootFinders.newton(LINE, x -> 1.0, 5.0, 0.0, 2.0, TOL));
    }

    @Test
    void newtonBracketedFallsBackToBisection() {
        // atan-like flat tail: the raw Newton step leaves [0, 10], so the safeguard bisects.
        RootFinders.Result r = RootFinders.newton(x -> Math.atan(x - 1.0), x -> 1.0 / (1.0 + (x - 1.0) * (x - 1.0)),
            9.0, 0.0, 10.0, new Tolerances(1e-12, 0.0, 200));
        assertEquals(1.0, r.root(), 1e-9);
    }

    @Test
    void newtonStartsAtExactRoot() {
        RootFinders.Result r = RootFinders.newton(LINE, x -> 1.0, 1.0, null, null, TOL);
        assertEquals(Termination.EXACT, r.termination());
    }
}
