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

/**
 * Cross gamma by revaluation against a closed form. The product {@code N P_a P_b} of two pillar discount factors has,
 * under the zero-rate shifts {@code P_i -> P_i exp(-s_i t_i)}, the exact second derivatives {@code N P_a P_b t_a t_b}
 * (off-diagonal), {@code N P_a P_b t_a^2} (diagonal) and 0 elsewhere; per bp^2 multiply by 1e-8. The OIS closed form
 * is then checked against revaluation on a real swap, and the fall-back path is exercised.
 */
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
    void revaluationGammaMatchesTheClosedFormOfAPillarProduct() {
        Curve c = curve(Curve.Interpolation.LOG_LINEAR_DF);
        double[] p = c.discountFactors();
        LocalDate[] d = c.dates();
        int n = d.length;
        int a = n - 1;
        int b = n - 2;
        double notional = 1e7;
        ToDoubleFunction<Curve> f = k -> notional * k.discountFactors()[a] * k.discountFactors()[b];
        BookRisk.CrossGamma g = BookRisk.crossGamma(c, f, 1.0);
        double ta = c.time(d[a]);
        double tb = c.time(d[b]);
        double v = notional * p[a] * p[b];
        assertEquals(v, g.value(), 1e-9 * v);
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                double ti = (i == a) ? ta : (i == b) ? tb : 0.0;
                double tj = (j == a) ? ta : (j == b) ? tb : 0.0;
                double expected = v * ti * tj * 1e-8;
                assertEquals(expected, g.gamma()[i][j], 1e-6 * v * ta * ta * 1e-8, "gamma[" + i + "][" + j + "]");
            }
        }
    }

    @Test
    void oisClosedFormEqualsRevaluationOnALogLinearCurve() {
        Curve c = curve(Curve.Interpolation.LOG_LINEAR_DF);
        Ois.Legs legs = Ois.legs(Conventions.SOFR, AS_OF, TRADE.tenor());
        BookRisk.CrossGamma a = BookRisk.crossGammaOis(c, legs, -1e7, 0.0345, product(), 1.0);
        BookRisk.CrossGamma b = BookRisk.crossGamma(c, product(), 1.0);
        double scale = 0.0;
        for (double[] row : b.gamma()) {
            for (double x : row) {
                scale = Math.max(scale, Math.abs(x));
            }
        }
        org.junit.jupiter.api.Assertions.assertTrue(scale > 0.0);
        for (int i = 0; i < b.gamma().length; i++) {
            for (int j = 0; j < b.gamma().length; j++) {
                assertEquals(b.gamma()[i][j], a.gamma()[i][j], 1e-4 * scale);
            }
        }
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
