package org.quantforge.risk;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.LocalDate;
import java.util.List;
import java.util.function.ToDoubleFunction;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Conventions;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.curves.CurveSolver;
import org.quantforge.curves.Ois;
import org.quantforge.pricing.Pricing;

/** Cross gamma by revaluation: symmetry, the closed form against it, and the fall-back to revaluation. */
class BookRiskCrossGammaTest {
    private static final LocalDate AS_OF = LocalDate.of(2026, 11, 6);
    private static final List<Ois.Quote> QUOTES = List.of(new Ois.Quote("1Y", 0.0365, null, null),
            new Ois.Quote("2Y", 0.035, null, null), new Ois.Quote("5Y", 0.035, null, null));
    private static final Pricing.OisTrade TRADE =
            new Pricing.OisTrade(Conventions.SOFR, "2Y", 0.0345, 1e7, Pricing.Side.RECEIVE);

    private static Curve curve(Curve.Interpolation m) {
        return Ois.bootstrap(Conventions.SOFR, AS_OF, QUOTES, m, CurveSolver.Method.SEQUENTIAL, null).curve();
    }

    private static ToDoubleFunction<Curve> product() {
        Ois.Legs legs = Ois.legs(Conventions.SOFR, AS_OF, TRADE.tenor());
        return c -> Pricing.oisPv(TRADE, legs, c);
    }

    @Test
    void revaluationGammaIsSymmetricAndMatchesThePresentValue() {
        Curve c = curve(Curve.Interpolation.LOG_LINEAR_DF);
        BookRisk.CrossGamma g = BookRisk.crossGamma(c, product(), 1.0);
        assertEquals(product().applyAsDouble(c), g.value());
        int n = g.gamma().length;
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                assertEquals(g.gamma()[i][j], g.gamma()[j][i]);
            }
        }
    }

    @Test
    void badBumpRejected() {
        Curve c = curve(Curve.Interpolation.LOG_LINEAR_DF);
        assertThrows(QfError.class, () -> BookRisk.crossGamma(c, product(), 0.0));
        assertThrows(QfError.class, () -> BookRisk.crossGamma(c, product(), Double.NaN));
    }

    @Test
    void nonLogLinearCurveFallsBackToRevaluation() {
        Curve c = curve(Curve.Interpolation.MONOTONE_CONVEX);
        Ois.Legs legs = Ois.legs(Conventions.SOFR, AS_OF, TRADE.tenor());
        BookRisk.CrossGamma a = BookRisk.crossGammaOis(c, legs, 1e7, 0.0345, product(), 1.0);
        BookRisk.CrossGamma b = BookRisk.crossGamma(c, product(), 1.0);
        assertEquals(b.value(), a.value());
        for (int i = 0; i < b.gamma().length; i++) {
            assertArrayEquals(b.gamma()[i], a.gamma()[i]);
        }
    }
}
