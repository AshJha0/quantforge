package org.quantforge.execution;

import org.quantforge.core.QfError;
import org.quantforge.execution.Execution.Mode;
import org.quantforge.execution.Execution.Side;

/**
 * Stage H wave 2 execution (rulings HR-59 to HR-67): the adaptive algorithms of {@code 10-execution/adaptive-algos.md}
 * (arrival price, close, liquidity seeking, pairs, baskets) and the pre-trade estimate and cost attribution of
 * {@code 10-execution/tca-pretrade.md}. Port of {@code python/quantforge_core/adaptive_exec.py}; error precedence
 * HR-66 (structural E_INPUT before any E_DOMAIN). Reuses the wave-1 TWAP and VWAP of {@link Execution}.
 *
 * <p>Sources, as the specs cite them: [AC00] Almgren and Chriss, J. Risk 3(2), preprint eq. (17) for the arrival
 * holdings and eq. (10) for the timing-risk line; [Kis13] Kissell, I-star form (recalled, UNVERIFIED; parameters
 * are inputs); [Per88] Perold for the total that the attribution splits.
 */
public final class AdaptiveExec {
    private AdaptiveExec() {}

    public enum PairMode { CASH_BALANCED, HEDGED }

    private static QfError input(String field, String why) {
        return new QfError("E_INPUT", field + ": " + why, field);
    }

    private static QfError domain(String field, String why) {
        return new QfError("E_DOMAIN", field + ": " + why, field);
    }

    private static double sign(Side s) {
        return s == Side.BUY ? 1.0 : -1.0;
    }

    private static void buckets(long n) {
        if (n < 1) {
            throw input("n_buckets", "must be at least 1");
        }
    }

    /** HR-2, HR-3: the order is positive, and a whole number of units in UNITS mode. */
    private static void quantity(double x, Mode mode, String field) {
        if (!(x > 0)) {
            throw input(field, "must be positive");
        }
        if (mode == Mode.UNITS && x != Math.floor(x)) {
            throw input(field, "must be a whole number of units in UNITS mode");
        }
    }

    /** cosh(a) / sinh(b) for 0 <= a <= b, b > 0, without overflow. */
    private static double coshOverSinh(double a, double b) {
        if (b <= 700.0) {
            return Math.cosh(a) / Math.sinh(b);
        }
        return Math.exp(a - b) * (1.0 + Math.exp(-2.0 * a)) / (-Math.expm1(-2.0 * b));
    }

    /**
     * HR-3: floor every share, give the missing units one at a time to the largest remainders, ties to the earliest;
     * if rounding left the floors above x, take units back from the smallest remainders, ties to the latest.
     */
    static double[] largestRemainder(double x, double[] exact) {
        int n = exact.length;
        double[] floors = new double[n];
        double[] rem = new double[n];
        long sum = 0;
        for (int i = 0; i < n; i++) {
            floors[i] = Math.floor(exact[i]);
            rem[i] = exact[i] - floors[i];
            sum += (long) floors[i];
        }
        long shortBy = (long) x - sum;
        Integer[] order = new Integer[n];
        for (int i = 0; i < n; i++) {
            order[i] = i;
        }
        java.util.Arrays.sort(order, (a, b) -> {
            int c = Double.compare(rem[b], rem[a]);
            return c != 0 ? c : Integer.compare(a, b);
        });
        for (int k = 0; k < Math.max(shortBy, 0) && k < n; k++) {
            floors[order[k]] += 1;
        }
        for (int k = 0; k < Math.max(-shortBy, 0) && k < n; k++) {
            floors[order[n - 1 - k]] -= 1;
        }
        return floors;
    }

    // ---- adaptive-algos.md ----

    /** {@code exec.algo.arrival}: x_j = X sinh(kappa (N - j)) / sinh(kappa N); kappa = 0 is TWAP (HR-59, HR-67). */
    public static double[] arrival(double x, long n, double kappa, Mode mode) {
        buckets(n);
        quantity(x, mode, "quantity");
        if (kappa < 0) {
            throw domain("urgency", "must be non-negative");
        }
        if (kappa == 0) {
            return Execution.twap(x, n, mode);
        }
        // n_j = x_{j-1} - x_j = X 2 sinh(k/2) cosh(k (N - j + 1/2)) / sinh(k N): strictly decreasing, no cancellation.
        double h = 2.0 * Math.sinh(0.5 * kappa);
        double[] exact = new double[(int) n];
        for (int j = 1; j <= n; j++) {
            exact[j - 1] = x * h * coshOverSinh(kappa * (n - j + 0.5), kappa * n);
        }
        return mode == Mode.UNITS ? largestRemainder(x, exact) : exact;
    }

    public record Close(double auctionQuantity, double[] slices) {}

    /** {@code exec.algo.close}: auction min(X, p_c V_c) (UNITS floors p_c V_c); the rest as VWAP (HR-60). */
    public static Close close(double x, double closeVolume, double participation, double[] profile, Mode mode) {
        quantity(x, mode, "quantity");
        if (profile.length == 0) {
            throw input("profile", "must not be empty");
        }
        if (!(participation >= 0 && participation <= 1)) {
            throw domain("auction_participation", "must lie in [0, 1]");
        }
        if (closeVolume < 0) {
            throw domain("close_volume", "must be non-negative");
        }
        double total = 0;
        for (double w : profile) {
            if (w < 0) {
                throw domain("profile", "weights must be non-negative");
            }
            total += w;
        }
        double cap = participation * closeVolume;
        if (mode == Mode.UNITS) {
            double near = Math.rint(cap); // within 1e-12 relative of an integer: snap before flooring
            cap = Math.abs(cap - near) <= 1e-12 * Math.abs(near) ? near : Math.floor(cap);
        }
        double auction = Math.min(x, cap);
        double rest = x - auction;
        if (rest <= 0) {
            return new Close(auction, new double[profile.length]);
        }
        if (total == 0) {
            throw domain("profile", "is all zero with a remainder to place");
        }
        return new Close(auction, Execution.vwap(rest, profile, mode));
    }

    /** avgPrices entries are null for an empty bucket; avgFillPrice null when nothing filled. */
    public record Seek(double[] slices, Double[] avgPrices, double filled, double residual, double notional,
            Double avgFillPrice) {}

    private static boolean inside(boolean buy, double price, double limit) {
        return buy ? price <= limit : price >= limit;
    }

    /** {@code exec.algo.liquidity_seek}: child min(R, alpha A_i), walking levels inside the limit best first (HR-61). */
    public static Seek liquiditySeek(Side side, double x, double limit, double alpha, double[][][] books) {
        boolean buy = side == Side.BUY;
        if (books.length == 0) {
            throw input("books", "must not be empty");
        }
        if (!(x > 0)) {
            throw input("quantity", "must be positive");
        }
        for (int i = 0; i < books.length; i++) {
            double[][] book = books[i];
            for (int k = 0; k < book.length; k++) {
                String path = "books/" + i + "/" + k;
                if (!(book[k][1] > 0)) {
                    throw input(path, "level sizes must be positive");
                }
                if (k > 0 && !(buy ? book[k][0] > book[k - 1][0] : book[k][0] < book[k - 1][0])) {
                    throw input(path, "levels must be strictly ordered best first (asks ascending, bids descending)");
                }
            }
        }
        if (!(alpha > 0 && alpha <= 1)) {
            throw domain("take_fraction", "must lie in (0, 1]");
        }
        if (!(limit > 0)) {
            throw domain("limit_price", "must be positive");
        }
        for (int i = 0; i < books.length; i++) {
            for (int k = 0; k < books[i].length; k++) {
                if (!(books[i][k][0] > 0)) {
                    throw domain("books/" + i + "/" + k, "level prices must be positive");
                }
            }
        }
        double remaining = x;
        double filled = 0;
        double notional = 0;
        double[] slices = new double[books.length];
        Double[] avg = new Double[books.length];
        for (int i = 0; i < books.length; i++) {
            double depth = 0;
            for (double[] lvl : books[i]) {
                if (inside(buy, lvl[0], limit)) {
                    depth += lvl[1];
                }
            }
            double child = Math.min(remaining, alpha * depth);
            double left = child;
            double paid = 0;
            for (double[] lvl : books[i]) {
                if (!inside(buy, lvl[0], limit)) {
                    continue;
                }
                if (left <= 0) {
                    break;
                }
                double take = Math.min(left, lvl[1]);
                paid += take * lvl[0];
                left -= take;
            }
            slices[i] = child;
            avg[i] = child > 0 ? paid / child : null;
            remaining -= child;
            filled += child;
            notional += paid;
        }
        return new Seek(slices, avg, filled, remaining, notional, filled > 0 ? notional / filled : null);
    }

    private static double[] cumulative(double[] xs) {
        double[] out = new double[xs.length];
        double c = 0;
        for (int i = 0; i < xs.length; i++) {
            c += xs[i];
            out[i] = c;
        }
        return out;
    }

    public record Pair(double[] slicesA, double[] slicesB, double quantityB, double[] cashImbalance) {}

    /** {@code exec.algo.pair}: leg A TWAP, leg B follows r C^A_j, rounded half up in UNITS (HR-62). */
    public static Pair pair(Side sideA, double qa, double pa, Side sideB, double pb, PairMode pairMode,
            Double hedgeRatio, long n, Mode mode) {
        buckets(n);
        quantity(qa, mode, "quantity");  // the leg key, as in Python, C++ and Rust (adaptive-algos.md)
        if (pairMode == PairMode.CASH_BALANCED && sideA == sideB) {
            throw input("leg_b", "a cash-balanced pair needs opposite sides");
        }
        if (pairMode == PairMode.HEDGED && hedgeRatio == null) {
            throw input("hedge_ratio", "HEDGED needs hedge_ratio");
        }
        if (!(pa > 0) || !(pb > 0)) {
            throw domain(pa > 0 ? "leg_b" : "leg_a", "prices must be positive");
        }
        if (pairMode == PairMode.HEDGED && !(hedgeRatio > 0)) {
            throw domain("hedge_ratio", "must be positive");
        }
        double[] slicesA = Execution.twap(qa, n, mode);
        double[] cumA = cumulative(slicesA);
        int m = cumA.length;
        double[] target = new double[m];
        for (int j = 0; j < m; j++) {
            // P_A C first: C_B P_B stays within ulps of C_A P_A
            target[j] = pairMode == PairMode.HEDGED ? hedgeRatio * cumA[j] : cumA[j] * pa / pb;
        }
        double[] cumB = new double[m];
        double[] slicesB = new double[m];
        double prev = 0;
        for (int j = 0; j < m; j++) {
            cumB[j] = mode == Mode.UNITS ? Math.floor(target[j] + 0.5) : target[j];
            slicesB[j] = cumB[j] - prev;
            prev = cumB[j];
        }
        double sa = sign(sideA);
        double sb = sign(sideB);
        double[] cash = new double[m];
        for (int j = 0; j < m; j++) {
            cash[j] = sa * cumA[j] * pa + sb * cumB[j] * pb;
        }
        return new Pair(slicesA, slicesB, cumB[m - 1], cash);
    }

    public record Leg(Side side, double quantity, double price) {}

    public record Basket(double[][] slices, double[] cashImbalance, double grossNotional) {}

    /** {@code exec.algo.basket}: every leg TWAP-sliced, per-bucket cash imbalance, gross notional (HR-63). */
    public static Basket basket(Leg[] legs, long n, Mode mode) {
        if (legs.length == 0) {
            throw input("legs", "must not be empty");
        }
        buckets(n);
        for (Leg g : legs) {
            quantity(g.quantity(), mode, "quantity");
        }
        for (Leg g : legs) {
            if (!(g.price() > 0)) {
                throw domain("legs", "prices must be positive");
            }
        }
        double[][] slices = new double[legs.length][];
        double[][] cums = new double[legs.length][];
        double gross = 0;
        for (int k = 0; k < legs.length; k++) {
            slices[k] = Execution.twap(legs[k].quantity(), n, mode);
            cums[k] = cumulative(slices[k]);
            gross += legs[k].quantity() * legs[k].price();
        }
        double[] cash = new double[(int) n];
        for (int j = 0; j < n; j++) {
            double c = 0;
            for (int k = 0; k < legs.length; k++) {
                c += sign(legs[k].side()) * cums[k][j] * legs[k].price();
            }
            cash[j] = c;
        }
        return new Basket(slices, cash, gross);
    }

    // ---- tca-pretrade.md ----

    public record Pretrade(double istarBps, double impactBps, double spreadBps, double expectedCostBps,
            double durationDays, double timingRiskBps, Double expectedCost, Double timingRisk) {}

    /** {@code exec.tca.pretrade}: I* = a1 (X/adv)^a2 sigma^a3; timing risk beside the cost, never added (HR-64). */
    public static Pretrade pretrade(double x, double adv, double sigma, double p, double halfSpread, double a1,
            double a2, double a3, double a4, double b1, Double price) {
        if (!(x > 0)) {
            throw input("quantity", "must be positive");
        }
        if (!(adv > 0)) {
            throw domain("adv", "must be positive");
        }
        if (sigma < 0) {
            throw domain("daily_vol", "must be non-negative");
        }
        if (!(p > 0 && p < 1)) {
            throw domain("participation", "must lie in (0, 1)");
        }
        if (halfSpread < 0) {
            throw domain("half_spread_bps", "must be non-negative");
        }
        if (!(a1 > 0)) {
            throw domain("params", "a1 must be positive");
        }
        if (!(b1 >= 0 && b1 <= 1)) {
            throw domain("params", "b1 must lie in [0, 1]");
        }
        if (price != null && !(price > 0)) {
            throw domain("price", "must be positive");
        }
        if (sigma == 0 && a3 <= 0) {
            throw domain("daily_vol", "0 to a non-positive power");
        }
        double istar = a1 * Math.pow(x / adv, a2) * Math.pow(sigma, a3);
        double impact = b1 * istar * Math.pow(p, a4) + (1.0 - b1) * istar;
        double cost = halfSpread + impact;
        double duration = x / (p * adv);
        double timing = 1e4 * sigma * Math.sqrt(duration / 3.0);
        Double ec = price == null ? null : cost * x * price / 1e4;
        Double tr = price == null ? null : timing * x * price / 1e4;
        return new Pretrade(istar, impact, halfSpread, cost, duration, timing, ec, tr);
    }

    public record Attribution(double delay, double impact, double spread, double execution, double opportunity,
            double fees, double total, double totalBps) {}

    /** {@code exec.tca.attribution}: delay, impact and spread on executed quantity; opportunity and fees (HR-65). */
    public static Attribution attribution(Side side, double decision, double arrivalMid, double end, double x,
            double[] q, double[] px, double[] mid, double fees) {
        double s = sign(side);
        if (!(x > 0)) {
            throw input("order_quantity", "must be positive");
        }
        for (double v : q) {
            if (!(v > 0)) {
                throw input("fills", "fill quantities must be positive");
            }
        }
        double filled = 0;
        for (double v : q) {
            filled += v;
        }
        if (filled > x) {
            throw input("fills", "fills add up to more than the order");
        }
        if (!(decision > 0)) {
            throw domain("decision_price", "prices and mids must be positive");
        }
        if (!(arrivalMid > 0)) {
            throw domain("arrival_mid", "prices and mids must be positive");
        }
        if (!(end > 0)) {
            throw domain("end_price", "prices and mids must be positive");
        }
        for (int i = 0; i < q.length; i++) {
            if (!(px[i] > 0) || !(mid[i] > 0)) {
                throw domain("fills", "prices and mids must be positive");
            }
        }
        double imp = 0;
        double spr = 0;
        for (int i = 0; i < q.length; i++) {
            imp += q[i] * (mid[i] - arrivalMid);
            spr += q[i] * (px[i] - mid[i]);
        }
        // + 0.0 turns the -0 of a SELL into +0
        double delay = s * filled * (arrivalMid - decision) + 0.0;
        double impact = s * imp + 0.0;
        double spread = s * spr + 0.0;
        double opportunity = s * (x - filled) * (end - decision) + 0.0;
        double total = delay + impact + spread + opportunity + fees;
        return new Attribution(delay, impact, spread, impact + spread, opportunity, fees, total,
                total / (x * decision) * 1e4);
    }
}
