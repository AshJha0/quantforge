package org.quantforge.cli;

import java.util.Map;
import java.util.function.DoubleUnaryOperator;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;

/** The test-function registry of test-functions.md. It lives in the CLI layer only. */
final class TestFunctions {
    private TestFunctions() {}

    record Pair(DoubleUnaryOperator f, DoubleUnaryOperator df) {}

    private static double bsCall(double x) {
        double s = 100.0;
        double k = 100.0;
        double r = 0.01;
        double d1 = (Math.log(s / k) + (r + x * x / 2.0)) / x;
        double d2 = d1 - x;
        return s * Normal.cdf(d1) - k * Math.exp(-r) * Normal.cdf(d2);
    }

    private static double bsVega(double x) {
        double d1 = (0.01 + x * x / 2.0) / x;
        return 100.0 * Normal.pdf(d1);
    }

    private static final Map<String, Pair> ROOT = Map.of(
            "cubic_wallis", new Pair(x -> x * x * x - 2.0 * x - 5.0, x -> 3.0 * x * x - 2.0),
            "cos_minus_x", new Pair(x -> Math.cos(x) - x, x -> -Math.sin(x) - 1.0),
            "exp_minus_two", new Pair(x -> Math.exp(x) - 2.0, Math::exp),
            "triple_root", new Pair(x -> (x - 1.0) * (x - 1.0) * (x - 1.0), x -> 3.0 * (x - 1.0) * (x - 1.0)),
            "square", new Pair(x -> x * x, x -> 2.0 * x),
            "no_real_root", new Pair(x -> x * x + 1.0, x -> 2.0 * x),
            "steep_atan", new Pair(x -> Math.atan(1000.0 * (x - 0.3)),
                    x -> 1000.0 / (1.0 + 1e6 * (x - 0.3) * (x - 0.3))),
            "bs_vol_atm", new Pair(x -> bsCall(x) - 10.0, TestFunctions::bsVega));

    private static final Map<String, DoubleUnaryOperator> PLAIN = Map.of(
            "exp", Math::exp,
            "sin", Math::sin,
            "runge", x -> 1.0 / (1.0 + 25.0 * x * x),
            "sqrt", Math::sqrt,
            "inv_sqrt", x -> 1.0 / Math.sqrt(x),
            "normal_pdf", Normal::pdf,
            "oscillatory", x -> Math.cos(50.0 * x) * Math.exp(-x),
            "poly5", x -> Math.pow(x, 5) - 3.0 * x * x + 1.0);

    static Pair root(String name) {
        Pair p = ROOT.get(name);
        if (p == null) {
            throw new QfError("E_SCHEMA", "unknown function " + name, "function");
        }
        return p;
    }

    static DoubleUnaryOperator plain(String name) {
        DoubleUnaryOperator f = PLAIN.get(name);
        if (f == null) {
            throw new QfError("E_SCHEMA", "unknown function " + name, "function");
        }
        return f;
    }
}
