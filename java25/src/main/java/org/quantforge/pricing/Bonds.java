package org.quantforge.pricing;

import org.quantforge.core.Finite;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.function.DoubleUnaryOperator;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;

/** Bonds, repo and bond futures (bonds.md, rulings D13 to D16). */
public final class Bonds {
    private Bonds() {}

    /** Face 100; coupon dates step back from maturity, unadjusted. */
    public record Bond(LocalDate maturity, double coupon, int frequency) {
        public double amount() {
            return 100.0 * coupon / frequency;
        }

        /** The k-th coupon date back from maturity (k = 0 is maturity). */
        public LocalDate back(long k) {
            return step(maturity, k * (12L / frequency));
        }

        /** Coupon dates strictly after {@code d}, ascending, plus the one on or before it as element 0. */
        public List<LocalDate> around(LocalDate d) {
            List<LocalDate> out = new ArrayList<>();
            long k = 0;
            LocalDate x = maturity;
            while (x.isAfter(d)) {
                out.addFirst(x);
                x = back(++k);
            }
            out.addFirst(x);
            return out;
        }

        public double accrued(LocalDate d) {
            List<LocalDate> a = around(d);
            return amount() * days(a.get(0), d) / days(a.get(0), a.get(1));
        }
    }

    /** {@code d} minus {@code months}, keeping month end when {@code d} is a month end. */
    static LocalDate step(LocalDate d, long months) {
        LocalDate x = d.minusMonths(months);
        return d.equals(YearMonth.from(d).atEndOfMonth()) ? YearMonth.from(x).atEndOfMonth() : x;
    }

    static long days(LocalDate a, LocalDate b) {
        return ChronoUnit.DAYS.between(a, b);
    }

    public static void checkSettlement(Bond b, LocalDate settlement) {
        if (!settlement.isBefore(b.maturity())) {
            throw new QfError("E_DATE_ORDER", "settlement is not before maturity", "settlement");
        }
    }

    public record YieldPrice(double dirty, double accrued, double clean, double modified, double macaulay,
                             double convexity) {}

    public static YieldPrice fromYield(Bond b, LocalDate settlement, double y) {
        Finite.check("y", y);
        checkSettlement(b, settlement);
        int f = b.frequency();
        if (!(1.0 + y / f > 0.0)) {
            throw new QfError("E_DOMAIN", "1 + y/f must be positive", "yield");
        }
        List<LocalDate> a = b.around(settlement);
        double w = (double) days(settlement, a.get(1)) / days(a.get(0), a.get(1));
        double v = 1.0 / (1.0 + y / f);
        double dirty = 0.0;
        double mac = 0.0;
        double cx = 0.0;
        int n = a.size() - 1;
        for (int k = 0; k < n; k++) {
            double cf = b.amount() + (k == n - 1 ? 100.0 : 0.0);
            double e = k + w;
            double pv = cf * Math.pow(v, e);
            dirty += pv;
            mac += e / f * pv;
            cx += e * (e + 1.0) / ((double) f * f) * pv * v * v;
        }
        double accrued = b.amount() * days(a.get(0), settlement) / days(a.get(0), a.get(1));
        mac /= dirty;
        return new YieldPrice(dirty, accrued, dirty - accrued, mac * v, mac, cx / dirty);
    }

    public static double yieldFromPrice(Bond b, LocalDate settlement, double clean) {
        Finite.check("clean", clean);
        checkSettlement(b, settlement);
        double accrued = b.accrued(settlement);
        if (!(clean > 0.0) || !(clean + accrued > 0.0)) {
            throw new QfError("E_DOMAIN", "dirty price must be positive", "clean_price");
        }
        double lo = -b.frequency() * (1.0 - 1e-12);
        return solveDecreasing(y -> fromYield(b, settlement, y).clean() - clean, b.coupon(), lo, 1e3);
    }

    /** Dirty price on {@code curve} with spread {@code z}, carried to settlement. */
    public static double curveDirty(Bond b, LocalDate settlement, Curve c, double z) {
        Finite.check("z", z);
        checkSettlement(b, settlement);
        if (settlement.isBefore(c.asOf())) {
            throw new QfError("E_OUT_OF_RANGE", "settlement is before the curve's as_of", "settlement");
        }
        List<LocalDate> a = b.around(settlement);
        double sum = 0.0;
        for (int k = 1; k < a.size(); k++) {
            double cf = b.amount() + (k == a.size() - 1 ? 100.0 : 0.0);
            sum += cf * c.discount(a.get(k)) * Math.exp(-z * c.time(a.get(k)));
        }
        return sum / (c.discount(settlement) * Math.exp(-z * c.time(settlement)));
    }

    public static double zSpread(Bond b, LocalDate settlement, Curve c, double clean) {
        Finite.check("clean", clean);
        double dirty = clean + b.accrued(settlement);
        curveDirty(b, settlement, c, 0.0);
        if (!(dirty > 0.0)) {
            throw new QfError("E_DOMAIN", "dirty price must be positive", "clean_price");
        }
        return solveDecreasing(z -> curveDirty(b, settlement, c, z) - dirty, 0.0, -10.0, 10.0);
    }

    public record AssetSwap(double spread, double annuity) {}

    public static AssetSwap assetSwap(Bond b, LocalDate settlement, Curve c, double dirtyPrice) {
        Finite.check("dirtyPrice", dirtyPrice);
        double p = curveDirty(b, settlement, c, 0.0);
        double annuity = 0.0;
        LocalDate e = b.maturity();
        for (long k = 1; e.isAfter(settlement); k++) {
            LocalDate s = b.maturity().minusMonths(3 * k);
            LocalDate start = s.isAfter(settlement) ? s : settlement;
            annuity += days(start, e) / 360.0 * c.discount(e);
            e = s;
        }
        annuity /= c.discount(settlement);
        return new AssetSwap((p - dirtyPrice) / (100.0 * annuity), annuity);
    }

    public record Frn(double dirty, double accrued, double clean) {}

    public static Frn frn(LocalDate settlement, LocalDate maturity, int frequency, double current, double margin,
                          double dm, Curve d, Curve p) {
        Finite.check("current", current);
        Finite.check("margin", margin);
        Finite.check("dm", dm);
        Bond b = new Bond(maturity, 0.0, frequency);
        checkSettlement(b, settlement);
        if (settlement.isBefore(d.asOf()) || settlement.isBefore(p.asOf())) {
            throw new QfError("E_OUT_OF_RANGE", "settlement is before a curve's as_of", "settlement");
        }
        List<LocalDate> a = b.around(settlement);
        double sum = 0.0;
        for (int i = 1; i < a.size(); i++) {
            LocalDate s = a.get(i - 1);
            LocalDate e = a.get(i);
            double alpha = days(s, e) / 360.0;
            double r = i == 1 ? current : (p.discount(s) / p.discount(e) - 1.0) / alpha;
            sum += 100.0 * (r + margin) * alpha * dm(d, e, dm);
        }
        sum += 100.0 * dm(d, maturity, dm);
        double dirty = sum / dm(d, settlement, dm);
        double accrued = 100.0 * (current + margin) * days(a.get(0), settlement) / 360.0;
        return new Frn(dirty, accrued, dirty - accrued);
    }

    private static double dm(Curve d, LocalDate x, double dm) {
        return d.discount(x) * Math.exp(-dm * d.time(x));
    }

    public record Repo(double dirty, double forwardDirty, double forwardClean, double interest, Double specialSpread,
                       Double specialnessValue) {}

    private static void checkTerm(Bond b, LocalDate start, LocalDate end) {
        if (!end.isAfter(start)) {
            throw new QfError("E_DATE_ORDER", "end is not after start", "end");
        }
        if (!end.isBefore(b.maturity())) {
            throw new QfError("E_INPUT", "end is not before maturity", "end");
        }
    }

    /** Coupons in (start, end]: their sum, and the sum of c (end - d)/360. */
    private static double[] coupons(Bond b, LocalDate start, LocalDate end) {
        double sum = 0.0;
        double weighted = 0.0;
        for (LocalDate d : b.around(start)) {
            if (d.isAfter(start) && !d.isAfter(end)) {
                sum += b.amount();
                weighted += b.amount() * days(d, end) / 360.0;
            }
        }
        return new double[] {sum, weighted};
    }

    public static Repo repo(Bond b, LocalDate start, LocalDate end, double clean, double r, Double gc) {
        Finite.check("clean", clean);
        Finite.check("r", r);
        checkTerm(b, start, end);
        double dirty = clean + b.accrued(start);
        double t = days(start, end) / 360.0;
        double[] c = coupons(b, start, end);
        double fwd = dirty * (1.0 + r * t) - (c[0] + r * c[1]);
        Double spread = gc == null ? null : gc - r;
        Double value = gc == null ? null : dirty * (gc - r) * t;
        return new Repo(dirty, fwd, fwd - b.accrued(end), dirty * r * t, spread, value);
    }

    public static double impliedRepo(Bond b, LocalDate start, LocalDate end, double clean, double forwardClean) {
        Finite.check("clean", clean);
        Finite.check("forwardClean", forwardClean);
        checkTerm(b, start, end);
        double dirty = clean + b.accrued(start);
        double fwd = forwardClean + b.accrued(end);
        double[] c = coupons(b, start, end);
        return (fwd + c[0] - dirty) / (dirty * days(start, end) / 360.0 - c[1]);
    }

    /** CME Treasury futures contracts (ruling R1-3). The first three count whole months. */
    public enum Contract {
        TWO_YEAR(true), THREE_YEAR(true), FIVE_YEAR(true), TEN_YEAR(false), ULTRA_TEN_YEAR(false), BOND(false),
        ULTRA_BOND(false);

        final boolean wholeMonths;

        Contract(boolean wholeMonths) {
            this.wholeMonths = wholeMonths;
        }
    }

    public static double conversionFactor(Bond b, YearMonth delivery, double notional, Contract contract) {
        Finite.check("notional", notional);
        if (notional != 0.06) {
            throw new QfError("E_INPUT", "notional_coupon must be 0.06", "notional_coupon");
        }
        if (b.frequency() != 2) {
            throw new QfError("E_INPUT", "semi-annual bonds only", "bond");
        }
        long months = (b.maturity().getYear() * 12L + b.maturity().getMonthValue())
                - (delivery.getYear() * 12L + delivery.getMonthValue());
        if (months < 0) {
            throw new QfError("E_DATE_ORDER", "maturity is before the delivery month", "bond");
        }
        long n = months / 12;
        long z = contract.wholeMonths ? months % 12 : (months % 12) / 3 * 3;
        double v = z < 7 ? z : z - 6;
        double a = Math.pow(1.03, -v / 6.0);
        double cpn = Math.floor(b.coupon() * 800.0 + 0.5) / 800.0; // nearest 1/8 of 1%, ties up
        double bb = cpn / 2.0 * (6.0 - v) / 6.0;
        double c = z < 7 ? Math.pow(1.03, -2.0 * n) : Math.pow(1.03, -2.0 * n - 1.0);
        double cf = a * (cpn / 2.0 + cpn / 0.06 * (1.0 - c) + c) - bb;
        if (!Double.isFinite(cf)) { // a finite coupon such as -1e308 can overflow (ruling R6-8)
            throw new QfError("E_DOMAIN", "conversion factor overflows binary64", "bond");
        }
        return new BigDecimal(cf).setScale(4, RoundingMode.HALF_EVEN).doubleValue();
    }

    public record Basis(double invoice, double grossBasis, double netBasis, double impliedRepo) {}

    public static Basis basis(Bond b, double clean, double cf, double futures, LocalDate settlement, LocalDate delivery,
                              double r) {
        Finite.check("clean", clean);
        Finite.check("cf", cf);
        Finite.check("futures", futures);
        Finite.check("r", r);
        checkTerm(b, settlement, delivery);
        double invoice = futures * cf + b.accrued(delivery);
        double dirty = clean + b.accrued(settlement);
        double[] c = coupons(b, settlement, delivery);
        double t = days(settlement, delivery) / 360.0;
        double fwd = repo(b, settlement, delivery, clean, r, null).forwardDirty();
        return new Basis(invoice, clean - futures * cf, fwd - invoice, (invoice + c[0] - dirty) / (dirty * t - c[1]));
    }

    /**
     * Root of a decreasing function: bracket from {@code guess} inside [lo, hi], then secant steps kept inside the
     * bracket, with bisection when they leave it.
     */
    public static double solveDecreasing(DoubleUnaryOperator g, double guess, double lo, double hi) {
        Finite.check("guess", guess);
        Finite.check("lo", lo);
        Finite.check("hi", hi);
        double a = guess;
        double fa = g.applyAsDouble(a);
        if (fa == 0.0) {
            return a;
        }
        double step = 0.01;
        double b = a;
        double fb = fa;
        for (int i = 0; i < 200 && Math.signum(fb) == Math.signum(fa); i++) {
            b = fa > 0 ? Math.min(hi, a + step) : Math.max(lo, a - step);
            fb = g.applyAsDouble(b);
            if (Math.signum(fb) == Math.signum(fa)) {
                a = b;
                fa = fb;
                step *= 2.0;
                if (b == hi || b == lo) {
                    break;
                }
            }
        }
        if (Math.signum(fb) == Math.signum(fa) || Double.isNaN(fb)) {
            throw new QfError("E_NO_CONVERGENCE", "no root in range");
        }
        // a, b bracket the root.
        for (int i = 0; i < 200; i++) {
            double x = b - fb * (b - a) / (fb - fa);
            double lower = Math.min(a, b);
            double upper = Math.max(a, b);
            if (!(x > lower && x < upper)) {
                x = 0.5 * (a + b);
            }
            double fx = g.applyAsDouble(x);
            if (fx == 0.0 || x == lower || x == upper) {
                return x;
            }
            if (Math.signum(fx) == Math.signum(fa)) {
                a = x;
                fa = fx;
                // Illinois: halve the stale end so the secant keeps moving.
                fb /= 2.0;
            } else {
                b = x;
                fb = fx;
                fa /= 2.0;
            }
            if (Math.abs(b - a) <= 1e-17 + 4e-16 * Math.abs(x)) {
                return Math.abs(fa) < Math.abs(fb) ? a : b;
            }
        }
        return Math.abs(fa) < Math.abs(fb) ? a : b;
    }

    public static double[] nsBetas(List<Bond> bonds, double[] dirty, double[] w, LocalDate settlement, double tau) {
        Finite.check("dirty", dirty);
        Finite.check("w", w);
        Finite.check("tau", tau);
        if (!(tau > 0.0)) {
            throw new QfError("E_DOMAIN", "tau must be positive", "tau");
        }
        for (Bond b : bonds) {
            checkSettlement(b, settlement);
        }
        int positive = 0;
        for (double v : w) {
            if (v < 0.0 || Double.isNaN(v)) {
                throw new QfError("E_DOMAIN", "weights must not be negative", "weights");
            }
            positive += v > 0.0 ? 1 : 0;
        }
        double total = 0.0;
        for (double v : w) {
            total += v;
        }
        if (!(total > 0.0)) {
            throw new QfError("E_DOMAIN", "weights sum to zero", "weights");
        }
        if (positive < 3) {
            throw new QfError("E_INPUT", "need at least 3 positive weights", "bonds");
        }
        double[] beta = {0.03, 0.0, 0.0};
        double mu = 1e-3;
        double obj = nsObjective(bonds, dirty, w, settlement, tau, beta);
        for (int it = 0; it < 200; it++) {
            double[][] jtj = new double[3][3];
            double[] jtr = new double[3];
            for (int i = 0; i < bonds.size(); i++) {
                double[] grad = new double[3];
                double r = nsModel(bonds.get(i), settlement, tau, beta, grad) - dirty[i];
                for (int p = 0; p < 3; p++) {
                    jtr[p] += w[i] * grad[p] * r;
                    for (int q = 0; q < 3; q++) {
                        jtj[p][q] += w[i] * grad[p] * grad[q];
                    }
                }
            }
            boolean moved = false;
            for (int tries = 0; tries < 30; tries++) {
                double[][] m = new double[3][3];
                for (int p = 0; p < 3; p++) {
                    m[p] = jtj[p].clone();
                    m[p][p] *= 1.0 + mu;
                }
                double[] d;
                try {
                    d = org.quantforge.core.LinearAlgebra.solve(m, jtr);
                } catch (QfError e) {
                    mu *= 10.0;
                    continue;
                }
                double[] cand = {beta[0] - d[0], beta[1] - d[1], beta[2] - d[2]};
                double co = nsObjective(bonds, dirty, w, settlement, tau, cand);
                if (co <= obj) {
                    moved = !(cand[0] == beta[0] && cand[1] == beta[1] && cand[2] == beta[2]);
                    beta = cand;
                    obj = co;
                    mu = Math.max(mu / 10.0, 1e-12);
                    break;
                }
                mu *= 10.0;
            }
            if (!moved) {
                break;
            }
        }
        return beta;
    }

    private static double nsObjective(List<Bond> bonds, double[] dirty, double[] w, LocalDate s, double tau,
                                      double[] beta) {
        double sum = 0.0;
        for (int i = 0; i < bonds.size(); i++) {
            double r = nsModel(bonds.get(i), s, tau, beta, null) - dirty[i];
            sum += w[i] * r * r;
        }
        return sum;
    }

    /** Model dirty price; fills {@code grad} with its derivative in the betas when not null. */
    public static double nsModel(Bond b, LocalDate settlement, double tau, double[] beta, double[] grad) {
        Finite.check("tau", tau);
        Finite.check("beta", beta);
        Finite.check("grad", grad);
        List<LocalDate> a = b.around(settlement);
        double sum = 0.0;
        for (int k = 1; k < a.size(); k++) {
            double cf = b.amount() + (k == a.size() - 1 ? 100.0 : 0.0);
            double t = days(settlement, a.get(k)) / 365.0;
            double u = t / tau;
            double e = -Math.expm1(-u) / u;
            double x2 = e - Math.exp(-u);
            double z = beta[0] + beta[1] * e + beta[2] * x2;
            double pv = cf * Math.exp(-z * t);
            sum += pv;
            if (grad != null) {
                grad[0] -= pv * t;
                grad[1] -= pv * t * e;
                grad[2] -= pv * t * x2;
            }
        }
        return sum;
    }
}
