package org.quantforge.hedging;

import java.time.LocalDate;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.quantforge.core.LinearAlgebra;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.pricing.Credit;

/**
 * {@code hedge.credit.cds} ({@code 08-hedging/credit-and-correlation-hedges.md}): CDS notionals that cancel a book's
 * CS01, jump to default or bucketed CS01, on the ISDA legs of {@code credit.cds.price}. CS01 is the central difference
 * of the piecewise-flat hazards with {@code eps = 1e-4 / (1 - R)} (ruling I-15); {@code JTD = (1 - R) - pv} per unit of
 * bought protection, with {@code pv} including the accrued premium (I-16).
 */
public final class CreditHedge {
    private CreditHedge() {}

    /**
     * A book trade.
     *
     * @param maturity scheduled maturity
     * @param coupon running coupon, {@code >= 0}
     * @param notional notional, {@code >= 0}
     * @param buyer true for bought protection
     */
    public record Trade(LocalDate maturity, double coupon, double notional, boolean buyer) {}

    /**
     * A hedge contract, priced per unit notional of bought protection.
     *
     * @param maturity scheduled maturity
     * @param coupon running coupon, {@code >= 0}
     */
    public record Contract(LocalDate maturity, double coupon) {}

    /**
     * Risks of a position or of one unit of bought protection.
     *
     * @param pv value, with the accrued premium
     * @param cs01 parallel CS01
     * @param jtd jump to default
     * @param buckets CS01 per hazard section
     */
    public record Risk(double pv, double cs01, double jtd, double[] buckets) {
        double target(int index) {
            return index == 0 ? cs01 : index == 1 ? jtd : buckets[index - 2];
        }
    }

    /**
     * The answer.
     *
     * @param notionals signed hedge notionals (positive buys protection)
     * @param book the book's risks
     * @param after book plus hedges ({@code pv} is not reported and is 0 here)
     * @param hedgeUpfront {@code sum_j n_j upfront_j}
     */
    public record Result(double[] notionals, Risk book, Risk after, double hedgeUpfront) {}

    private static QfError input(String key, String why) {
        return new QfError("E_INPUT", key + ": " + why, key);
    }

    /** Target index: 0 for CS01, 1 for JTD, 1 + k for BUCKET_k; -1 when unknown. */
    static int targetIndex(String target, int sections) {
        if (target.equals("CS01")) {
            return 0;
        }
        if (target.equals("JTD")) {
            return 1;
        }
        if (target.matches("BUCKET_[1-9][0-9]{0,5}")) {
            int k = Integer.parseInt(target.substring(7));
            return k <= sections ? 1 + k : -1;
        }
        return -1;
    }

    /** Per-unit risks of bought protection on one contract, and its clean upfront per unit. */
    record Unit(Risk risk, double upfront) {}

    static Unit unitRisk(LocalDate t, Curve p, Credit.Hazard q, double r, LocalDate maturity, double coupon) {
        int sections = q.sections();
        double eps = 1e-4 / (1.0 - r);
        Credit.Price base = Credit.price(t, p, q, r, maturity, coupon, 1.0, true, false);
        double[] all = new double[sections];
        java.util.Arrays.fill(all, eps);
        double cs01 = centralDifference(t, p, q, r, maturity, coupon, all);
        double[] buckets = new double[sections];
        for (int k = 0; k < sections; k++) {
            double[] one = new double[sections];
            one[k] = eps;
            buckets[k] = centralDifference(t, p, q, r, maturity, coupon, one);
        }
        return new Unit(new Risk(base.pv(), cs01, (1.0 - r) - base.pv(), buckets), base.upfront());
    }

    private static double centralDifference(LocalDate t, Curve p, Credit.Hazard q, double r, LocalDate maturity,
            double coupon, double[] shift) {
        double[] down = new double[shift.length];
        for (int k = 0; k < shift.length; k++) {
            down[k] = -shift[k];
        }
        double up = Credit.price(t, p, q.shifted(shift), r, maturity, coupon, 1.0, true, false).pv();
        double dn = Credit.price(t, p, q.shifted(down), r, maturity, coupon, 1.0, true, false).pv();
        return (up - dn) / 2.0;
    }

    /**
     * Solves the hedge. The caller has already applied the {@code LOG_LINEAR_DF} check (ruling R1-4) and built the
     * curves.
     *
     * @param t trade date
     * @param p discount curve
     * @param q hazard curve
     * @param recovery recovery rate {@code R}, in {@code [0, 1)}
     * @param book the trades to hedge, at least one
     * @param hedges the hedge contracts, as many as targets
     * @param targets distinct names from {@code CS01}, {@code JTD}, {@code BUCKET_1} to {@code BUCKET_P}
     * @return the notionals, the book's risks and the risks after the hedge
     * @throws QfError {@code E_INPUT}, {@code E_DOMAIN} or {@code E_SINGULAR}, in the specification's order
     */
    public static Result solve(LocalDate t, Curve p, Credit.Hazard q, double recovery, List<Trade> book,
            List<Contract> hedges, List<String> targets) {
        if (book.isEmpty()) {
            throw input("book", "empty");
        }
        if (hedges.isEmpty()) {
            throw input("hedges", "empty");
        }
        if (targets.size() != hedges.size()) {
            throw input("targets", "one target per hedge contract");
        }
        int sections = q.sections();
        Set<Integer> seen = new HashSet<>();
        int[] index = new int[targets.size()];
        for (int i = 0; i < index.length; i++) {
            index[i] = targetIndex(targets.get(i), sections);
            if (index[i] < 0) {
                throw input("targets", "unknown target " + targets.get(i));
            }
            if (!seen.add(index[i])) {
                throw input("targets", "repeated target " + targets.get(i));
            }
        }
        for (Trade tr : book) {
            if (!tr.maturity().isAfter(t)) {
                throw input("book", "maturity on or before trade_date");
            }
        }
        for (Contract c : hedges) {
            if (!c.maturity().isAfter(t)) {
                throw input("hedges", "maturity on or before trade_date");
            }
        }
        if (!(recovery >= 0.0 && recovery < 1.0)) {
            throw new QfError("E_DOMAIN", "recovery must be in [0, 1)", "recovery");
        }
        for (Trade tr : book) {
            if (!(tr.notional() >= 0.0)) {
                throw new QfError("E_DOMAIN", "notional below 0", "book");
            }
            if (!(tr.coupon() >= 0.0)) {
                throw new QfError("E_DOMAIN", "coupon below 0", "book");
            }
        }
        for (Contract c : hedges) {
            if (!(c.coupon() >= 0.0)) {
                throw new QfError("E_DOMAIN", "coupon below 0", "hedges");
            }
        }
        int n = hedges.size();
        Risk[] unit = new Risk[n];
        double[] upfront = new double[n];
        for (int j = 0; j < n; j++) {
            Unit u = unitRisk(t, p, q, recovery, hedges.get(j).maturity(), hedges.get(j).coupon());
            upfront[j] = u.upfront();
            unit[j] = u.risk();
        }
        double pv = 0.0;
        double cs01 = 0.0;
        double jtd = 0.0;
        double[] buckets = new double[sections];
        for (Trade tr : book) {
            Risk[] one = {unitRisk(t, p, q, recovery, tr.maturity(), tr.coupon()).risk()};
            double s = (tr.buyer() ? 1.0 : -1.0) * tr.notional();
            pv += s * one[0].pv();
            cs01 += s * one[0].cs01();
            jtd += s * one[0].jtd();
            for (int k = 0; k < sections; k++) {
                buckets[k] += s * one[0].buckets()[k];
            }
        }
        Risk before = new Risk(pv, cs01, jtd, buckets);
        double[][] g = new double[n][n];
        double[] rhs = new double[n];
        for (int i = 0; i < n; i++) {
            rhs[i] = -before.target(index[i]);
            for (int j = 0; j < n; j++) {
                g[i][j] = unit[j].target(index[i]);
            }
        }
        double[] sv = LinearAlgebra.singularValues(g);
        if (!(sv[n - 1] > Dense.RANK_TOL * sv[0])) {
            throw new QfError("E_SINGULAR", "the hedge risk matrix is singular", "hedges");
        }
        double[] notionals = LinearAlgebra.solve(g, rhs);
        double cs = cs01;
        double jd = jtd;
        double[] bk = buckets.clone();
        double up = 0.0;
        for (int j = 0; j < n; j++) {
            notionals[j] += 0.0;
            cs += notionals[j] * unit[j].cs01();
            jd += notionals[j] * unit[j].jtd();
            for (int k = 0; k < sections; k++) {
                bk[k] += notionals[j] * unit[j].buckets()[k];
            }
            up += notionals[j] * upfront[j];
        }
        return new Result(notionals, before, new Risk(0.0, cs, jd, bk), up);
    }
}
