package org.quantforge.execution;

import org.quantforge.core.QfError;

/**
 * Stage H wave 1 (rulings HR-1 to HR-10): execution schedules ({@code 10-execution/schedules.md}), Almgren-Chriss
 * ({@code 10-execution/almgren-chriss.md}), square-root and Obizhaeva-Wang impact ({@code 10-execution/impact.md}),
 * implementation-shortfall TCA ({@code 10-execution/tca.md}) and Avellaneda-Stoikov quotes
 * ({@code 09-microstructure/avellaneda-stoikov.md}).
 */
public final class Execution {
    private Execution() {}

    /** HR-9: schedule buckets and AC steps. */
    public static final long MAX_STEPS = 100_000;
    /** HR-9: TCA fills. */
    public static final int MAX_FILLS = 1_000_000;
    /** HR-10: the label on outputs that rest on assumed parameters. */
    public static final String ASSUMED = "assumed parameters; not calibrated to any venue";

    private static final double TWO_53 = 0x1p53;

    public enum Mode { UNITS, CONTINUOUS }

    public enum Side { BUY, SELL }

    private static QfError input(String field, String why) {
        return new QfError("E_INPUT", field + ": " + why, field);
    }

    private static QfError domain(String field, String why) {
        return new QfError("E_DOMAIN", field + ": " + why, field);
    }

    /** X > 0, and a whole number of units in UNITS mode (schedules.md). */
    private static void checkQuantity(double x, Mode mode) {
        if (!(x > 0)) {
            throw input("quantity", "must be positive");
        }
        if (mode == Mode.UNITS && (x != Math.rint(x) || x > TWO_53)) {
            throw input("quantity", "must be a whole number of units in UNITS mode");
        }
    }

    /** Floor that treats a value within 1e-12 relative of an integer as that integer, so p v / (1 - p) = 250 floors to 250. */
    static double snapFloor(double x) {
        double r = Math.rint(x);
        return Math.abs(x - r) <= 1e-12 * Math.max(1.0, Math.abs(x)) ? r : Math.floor(x);
    }

    // ---- exec.schedule.* ----

    /** TWAP (HR-3): UNITS floors each slice and gives the remainder one unit at a time to the earliest slices. */
    public static double[] twap(double x, long n, Mode mode) {
        if (n < 1) {
            throw input("n_buckets", "must be at least 1");
        }
        checkQuantity(x, mode);
        double[] s = new double[(int) n];
        if (mode == Mode.CONTINUOUS) {
            java.util.Arrays.fill(s, x / n);
            return s;
        }
        long units = (long) x;
        long base = units / n;
        long rem = units % n;
        for (int i = 0; i < n; i++) {
            s[i] = base + (i < rem ? 1 : 0);
        }
        return s;
    }

    /** VWAP (HR-3): slice i = X w_i / sum w; UNITS by largest remainder, ties to the earliest. */
    public static double[] vwap(double x, double[] profile, Mode mode) {
        checkQuantity(x, mode);
        if (profile.length == 0) {
            throw input("profile", "must not be empty");
        }
        double sum = 0;
        for (double w : profile) {
            if (w < 0) {
                throw domain("profile", "weights must be non-negative");
            }
            sum += w;
        }
        if (!(sum > 0)) {
            throw domain("profile", "all weights are zero");
        }
        int n = profile.length;
        double[] s = new double[n];
        for (int i = 0; i < n; i++) {
            s[i] = x * (profile[i] / sum); // ratio first (schedules.md): x w_i underflows when w_i is subnormal
        }
        if (mode == Mode.CONTINUOUS) {
            return s;
        }
        double[] frac = new double[n];
        double allotted = 0;
        for (int i = 0; i < n; i++) {
            double f = Math.floor(s[i]);
            frac[i] = s[i] - f;
            s[i] = f;
            allotted += f;
        }
        long rem = Math.max(0, (long) (x - allotted));
        Integer[] order = new Integer[n];
        for (int i = 0; i < n; i++) {
            order[i] = i;
        }
        // Stable sort: equal remainders keep index order, so the earliest wins.
        java.util.Arrays.sort(order, (a, b) -> Double.compare(frac[b], frac[a]));
        for (int k = 0; k < rem && k < n; k++) {
            s[order[k]] += 1;
        }
        return s;
    }

    /** POV result: child slices, their sum and the part of the order left (never an error). */
    public record Pov(double[] slices, double filled, double residual) {}

    /** POV (HR-4): child i = min(remaining, p v_i / (1 - p)), floored in UNITS. */
    public static Pov pov(double x, double p, double[] marketVolume, Mode mode) {
        checkQuantity(x, mode);
        if (!(p > 0 && p < 1)) {
            throw domain("participation", "must lie in (0, 1)");
        }
        if (marketVolume.length == 0) {
            throw input("market_volume", "must not be empty");
        }
        for (double v : marketVolume) {
            if (v < 0) {
                throw domain("market_volume", "must be non-negative");
            }
        }
        double ratio = 1 - p;
        double remaining = x;
        double[] s = new double[marketVolume.length];
        double filled = 0;
        for (int i = 0; i < s.length; i++) {
            double raw = p * marketVolume[i] / ratio;
            double c = Math.min(remaining, mode == Mode.UNITS ? snapFloor(raw) : raw);
            s[i] = c;
            filled += c;
            remaining -= c; // running remaining (HR-56): c <= remaining, so never negative
        }
        return new Pov(s, filled, remaining);
    }

    // ---- exec.ac.* ----

    /** Model inputs of [AC00] (HR-5). */
    public record AcParams(double quantity, double horizon, long nSteps, double sigma, double epsilon, double eta,
            double gamma) {}

    /** One optimal trajectory: holdings x_0..x_N, trades n_1..n_N, kappa, E, V and E + lambda V. */
    public record AcTrajectory(double[] holdings, double[] trades, double kappa, double expectedCost, double variance,
            double objective) {}

    /** Checks in the order of almgren-chriss.md; returns eta_tilde. */
    static double checkAc(AcParams p) {
        if (p.nSteps() < 1) {
            throw input("n_steps", "must be at least 1");
        }
        if (!(p.quantity() > 0)) {
            throw input("quantity", "must be positive");
        }
        if (!(p.horizon() > 0)) {
            throw domain("horizon", "must be positive");
        }
        if (p.sigma() < 0) {
            throw domain("sigma", "must be non-negative");
        }
        if (p.epsilon() < 0) {
            throw domain("epsilon", "must be non-negative");
        }
        if (p.gamma() < 0) {
            throw domain("gamma", "must be non-negative");
        }
        double tau = p.horizon() / p.nSteps();
        double etaTilde = p.eta() - p.gamma() * tau / 2;
        if (!(etaTilde > 0)) {
            throw domain("eta", "eta_tilde = eta - gamma tau / 2 must be positive");
        }
        return etaTilde;
    }

    /** HR-6: kappa_tilde = acosh(1 + y) / tau through log1p, y = lambda sigma^2 tau^2 / (2 eta_tilde). */
    static double kappa(double lambda, double sigma, double tau, double etaTilde) {
        double y = lambda * sigma * sigma * tau * tau / (2 * etaTilde);
        return Math.log1p(y + Math.sqrt(y * (y + 2))) / tau;
    }

    /** sinh(a) / sinh(b) for 0 <= a <= b, b > 0; exponential form when b > 700 (HR-6). */
    static double sinhRatio(double a, double b) {
        if (b > 700) {
            return Math.exp(a - b) * (-Math.expm1(-2 * a)) / (-Math.expm1(-2 * b));
        }
        return Math.sinh(a) / Math.sinh(b);
    }

    private static void checkLambda(double lambda) {
        if (lambda < 0) {
            throw domain("risk_aversion", "must be non-negative");
        }
    }

    public static AcTrajectory acTrajectory(AcParams p, double lambda) {
        double etaTilde = checkAc(p);
        checkLambda(lambda);
        return trajectory(p, etaTilde, lambda);
    }

    private static AcTrajectory trajectory(AcParams p, double etaTilde, double lambda) {
        int n = (int) p.nSteps();
        double x = p.quantity();
        double t = p.horizon();
        double tau = t / n;
        double k = lambda == 0 ? 0 : kappa(lambda, p.sigma(), tau, etaTilde);
        double[] h = new double[n + 1];
        h[0] = x;
        for (int j = 1; j < n; j++) {
            if (k == 0) {
                h[j] = x * (n - j) / n; // HR-5: exactly linear, not the kappa -> 0 limit
            } else {
                double tj = j * tau;
                h[j] = x * sinhRatio(k * (t - tj), k * t);
            }
        }
        h[n] = 0;
        double[] trades = new double[n];
        double sumSq = 0;
        double sumHold = 0;
        for (int j = 1; j <= n; j++) {
            trades[j - 1] = h[j - 1] - h[j];
            sumSq += trades[j - 1] * trades[j - 1];
            sumHold += h[j] * h[j];
        }
        double e = 0.5 * p.gamma() * x * x + p.epsilon() * x + etaTilde / tau * sumSq; // [AC00] eq. (8)
        double v = p.sigma() * p.sigma() * tau * sumHold; // [AC00] eq. (5)
        return new AcTrajectory(h, trades, k, e, v, e + lambda * v);
    }

    /** One (lambda, E, V) per entry of {@code lambdas}. */
    public record AcFrontier(double[] riskAversions, double[] expectedCost, double[] variance) {}

    public static AcFrontier acFrontier(AcParams p, double[] lambdas) {
        double etaTilde = checkAc(p);
        if (lambdas.length == 0) {
            throw input("risk_aversions", "must not be empty");
        }
        for (double l : lambdas) {
            checkLambda(l);
        }
        double[] e = new double[lambdas.length];
        double[] v = new double[lambdas.length];
        for (int i = 0; i < lambdas.length; i++) {
            AcTrajectory r = trajectory(p, etaTilde, lambdas[i]);
            e[i] = r.expectedCost();
            v[i] = r.variance();
        }
        return new AcFrontier(lambdas.clone(), e, v);
    }

    // ---- exec.impact.* ----

    /** [TLD11] eq. (1): I = Y sigma sqrt(Q / V), a fraction of price. */
    public static double impactSqrt(double q, double dailyVolume, double dailyVol, double coefficient) {
        if (q < 0) {
            throw domain("quantity", "must be non-negative");
        }
        if (!(dailyVolume > 0)) {
            throw domain("daily_volume", "must be positive");
        }
        if (dailyVol < 0) {
            throw domain("daily_vol", "must be non-negative");
        }
        if (coefficient < 0) {
            throw domain("coefficient", "must be non-negative");
        }
        return coefficient * dailyVol * Math.sqrt(q / dailyVolume);
    }

    /** [OW13] eq. (31): blocks X / (rho T + 2) at both ends, rate rho X / (rho T + 2) between. */
    public record OwOptimal(double initialBlock, double rate, double finalBlock) {}

    public static OwOptimal owOptimal(double x, double t, double rho) {
        if (!(x > 0)) {
            throw input("quantity", "must be positive");
        }
        if (!(t > 0)) {
            throw domain("horizon", "must be positive");
        }
        if (!(rho > 0)) {
            throw domain("resilience", "must be positive");
        }
        double d = rho * t + 2;
        double block = x / d;
        return new OwOptimal(block, rho * x / d, block);
    }

    // ---- exec.tca.shortfall ----

    /** Perold decomposition (HR-8); {@code vwapSlippage} is null without a benchmark. */
    public record Shortfall(double delay, double execution, double opportunity, double total, double totalBps,
            Double vwapSlippage) {}

    public static Shortfall shortfall(Side side, double decision, double arrival, double end, double x,
            double[] fillQty, double[] fillPrice, double fees, Double benchmarkVwap) {
        if (!(x > 0)) {
            throw input("order_quantity", "must be positive");
        }
        double q = 0;
        for (double qi : fillQty) {
            if (!(qi > 0)) {
                throw input("fills", "fill quantities must be positive");
            }
            q += qi;
        }
        if (q > x) {
            throw input("fills", "fills add up to more than the order");
        }
        if (!(decision > 0)) {
            throw domain("decision_price", "must be positive");
        }
        if (!(arrival > 0)) {
            throw domain("arrival_price", "must be positive");
        }
        if (!(end > 0)) {
            throw domain("end_price", "must be positive");
        }
        for (double pi : fillPrice) {
            if (!(pi > 0)) {
                throw domain("fills", "fill prices must be positive");
            }
        }
        if (benchmarkVwap != null && !(benchmarkVwap > 0)) {
            throw domain("benchmark_vwap", "must be positive");
        }
        double s = side == Side.BUY ? 1 : -1;
        double delay = s * q * (arrival - decision);
        double exec = 0;
        double notional = 0;
        for (int i = 0; i < fillQty.length; i++) {
            exec += fillQty[i] * (fillPrice[i] - arrival);
            notional += fillQty[i] * fillPrice[i];
        }
        exec *= s;
        double opp = s * (x - q) * (end - decision) + 0.0; // + 0.0: a full sell gives 0, not -0
        double total = delay + exec + opp + fees;
        Double slip = benchmarkVwap == null ? null : s * (notional - q * benchmarkVwap); // s Q (avg_fill - VWAP)
        return new Shortfall(delay, exec, opp, total, total / (x * decision) * 1e4, slip);
    }

    // ---- usecase.execution_tca (use case 5, 04-pricing/use-cases.md) ----

    public record ExecutionTca(double[] lots, double expectedCost, double variance, double filled, double fees,
            Shortfall shortfall) {}

    public static ExecutionTca executionTca(AcParams p, double lambda, Side side, double decision, double arrival,
            double end, double[] fillPrices, long completedSteps, double feePerUnit) {
        if (!(p.quantity() >= 1) || p.quantity() != Math.rint(p.quantity()) || p.quantity() > TWO_53) {
            throw input("quantity", "must be an Integer >= 1");
        }
        if (fillPrices.length != p.nSteps()) {
            throw input("fill_prices", "needs one price per step");
        }
        if (completedSteps < 0 || completedSteps > p.nSteps()) {
            throw input("completed_steps", "must lie in 0 to n_steps");
        }
        if (feePerUnit < 0) {
            throw domain("fee_per_unit", "must be non-negative");
        }
        AcTrajectory ac = acTrajectory(p, lambda);
        double[] lots = vwap(p.quantity(), ac.trades(), Mode.UNITS);
        int k = (int) completedSteps;
        double[] q = java.util.Arrays.copyOf(lots, k);
        double[] px = java.util.Arrays.copyOf(fillPrices, k);
        double filled = 0;
        for (double x : q) {
            filled += x;
        }
        double fees = feePerUnit * filled;
        Shortfall s = shortfall(side, decision, arrival, end, p.quantity(), q, px, fees, null);
        return new ExecutionTca(lots, ac.expectedCost(), ac.variance(), filled, fees, s);
    }

    // ---- micro.mm.as_quotes ----

    /** [AS08] eqs. (29)-(30), p. 221 (HR-7). */
    public record Quotes(double reservation, double spread, double bid, double ask) {}

    public static Quotes asQuotes(double mid, double q, double gamma, double sigma, double timeLeft, double k) {
        if (!(gamma > 0)) {
            throw domain("risk_aversion", "must be positive");
        }
        if (!(k > 0)) {
            throw domain("k", "must be positive");
        }
        if (sigma < 0) {
            throw domain("sigma", "must be non-negative");
        }
        if (timeLeft < 0) {
            throw domain("time_left", "must be non-negative");
        }
        double risk = gamma * sigma * sigma * timeLeft;
        double r = mid - q * risk;
        double spread = risk + 2 / gamma * Math.log1p(gamma / k);
        return new Quotes(r, spread, r - spread / 2, r + spread / 2);
    }
}
