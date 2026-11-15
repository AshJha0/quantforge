package org.quantforge.curves;

import org.quantforge.core.QfError;

/**
 * Stage J curves lane (rulings J-C-1 to J-C-9): the financing term structure over the funding curve
 * ({@code 02-curves/financing-term-structure.md}) and the liquidity cost curve
 * ({@code 10-execution/liquidity-curve.md}).
 */
public final class TermCurves {
    private TermCurves() {}

    static boolean increasingPositive(double[] ts) {
        for (int k = 0; k < ts.length; k++) {
            if (!(ts[k] > 0) || (k > 0 && !(ts[k] > ts[k - 1]))) {
                return false;
            }
        }
        return true;
    }

    /** Linear in y on the knots (0, 0), (ts[k], ys[k]) for t in (0, ts[last]] (J-C-3). */
    static double lin(double[] ts, double[] ys, double t) {
        double x0 = 0;
        double y0 = 0;
        for (int k = 0; k < ts.length; k++) {
            if (t <= ts[k]) {
                return y0 + (t - x0) / (ts[k] - x0) * (ys[k] - y0);
            }
            x0 = ts[k];
            y0 = ys[k];
        }
        return Double.NaN;
    }

    /** Knots of cumulative funding Z(t) t, financing spread S(t) and borrow fee B(t). */
    public static final class FinancingCurve {
        final double[] fundingTimes;
        final double[] fundingCum;
        final double[] quoteTimes;
        final double[] spreadCum;
        final double[] borrowTimes;
        final double[] borrowCum;

        private FinancingCurve(double[] ft, double[] fc, double[] qt, double[] sc, double[] bt, double[] bc) {
            fundingTimes = ft;
            fundingCum = fc;
            quoteTimes = qt;
            spreadCum = sc;
            borrowTimes = bt;
            borrowCum = bc;
        }

        /** Last time every input curve covers. */
        public double cover() {
            double c = Math.min(fundingTimes[fundingTimes.length - 1], quoteTimes[quoteTimes.length - 1]);
            return borrowTimes.length > 0 ? Math.min(c, borrowTimes[borrowTimes.length - 1]) : c;
        }

        double zt(double t) {
            return lin(fundingTimes, fundingCum, t);
        }

        double s(double t) {
            return lin(quoteTimes, spreadCum, t);
        }

        double b(double t) {
            return borrowTimes.length > 0 ? lin(borrowTimes, borrowCum, t) : 0.0;
        }

        /** P_f(t) = exp(-Z(t) t - S(t)). */
        public double financingDf(double t) {
            return Math.exp(-zt(t) - s(t));
        }

        public boolean hasBorrow() {
            return borrowTimes.length > 0;
        }
    }

    /** Bootstraps S(T_i) = ln(1 + R_i T_i) - Z(T_i) T_i (J-C-2) and B(T_j) = b_j T_j (J-C-4). */
    public static FinancingCurve build(double[] ft, double[] fz, double[] qt, double[] qr, double[] bt, double[] bf) {
        if (ft.length != fz.length || qt.length != qr.length || bt.length != bf.length || ft.length == 0
                || qt.length == 0) {
            throw new QfError("E_INPUT", "curve arrays must pair up; funding and quotes non-empty");
        }
        if (!increasingPositive(ft) || !increasingPositive(qt) || !increasingPositive(bt)) {
            throw new QfError("E_INPUT", "times must be positive and strictly increasing");
        }
        for (int i = 0; i < qt.length; i++) {
            if (1.0 + qr[i] * qt[i] <= 0) {
                throw new QfError("E_DOMAIN", "1 + R T must be positive", "repo_rates");
            }
        }
        double[] bc = new double[bt.length];
        for (int j = 0; j < bt.length; j++) {
            if (bf[j] < 0) {
                throw new QfError("E_DOMAIN", "borrow fees must be non-negative", "borrow_fees");
            }
        }
        for (int j = 0; j < bt.length; j++) {
            bc[j] = bf[j] * bt[j];
            if (j > 0 && bc[j] < bc[j - 1]) {
                throw new QfError("E_DOMAIN", "cumulative borrow fee must not fall", "borrow_fees");
            }
        }
        if (qt[qt.length - 1] > ft[ft.length - 1]) {
            throw new QfError("E_DOMAIN", "a quote lies beyond the funding curve", "quote_times");
        }
        double[] fc = new double[ft.length];
        for (int k = 0; k < ft.length; k++) {
            fc[k] = fz[k] * ft[k];
        }
        double[] sc = new double[qt.length];
        for (int i = 0; i < qt.length; i++) {
            sc[i] = Math.log1p(qr[i] * qt[i]) - lin(ft, fc, qt[i]);
        }
        return new FinancingCurve(ft.clone(), fc, qt.clone(), sc, bt.clone(), bc);
    }

    /** repo.term.curve outputs; borrowFee is null without borrow quotes. */
    public record TermCurve(double[] pillarSpreads, double[] spread, double[] financingDf, double[] financingRate,
            double[] forwardFinancing, double[] borrowFee) {}

    /** repo.term.curve (J-C-2, J-C-3). */
    public static TermCurve termCurve(FinancingCurve c, double[] q) {
        if (q.length == 0 || !increasingPositive(q)) {
            throw new QfError("E_INPUT", "query_times must be non-empty, positive, increasing", "query_times");
        }
        if (q[q.length - 1] > c.cover()) {
            throw new QfError("E_DOMAIN", "query beyond the coverage of the curve", "query_times");
        }
        int n = q.length;
        double[] pf = new double[n];
        double[] sp = new double[n];
        double[] rate = new double[n];
        double[] fwd = new double[n];
        double[] fee = c.hasBorrow() ? new double[n] : null;
        double pt = 0;
        double pp = 1;
        for (int j = 0; j < n; j++) {
            pf[j] = c.financingDf(q[j]);
            sp[j] = c.s(q[j]) / q[j];
            rate[j] = (1.0 / pf[j] - 1.0) / q[j];
            fwd[j] = (pp / pf[j] - 1.0) / (q[j] - pt);
            pt = q[j];
            pp = pf[j];
            if (fee != null) {
                fee[j] = c.b(q[j]) / q[j];
            }
        }
        double[] pillars = new double[c.quoteTimes.length];
        for (int i = 0; i < pillars.length; i++) {
            pillars[i] = c.spreadCum[i] / c.quoteTimes[i];
        }
        return new TermCurve(pillars, sp, pf, rate, fwd, fee);
    }

    /** eq.forward.term_financed outputs. */
    public record TermForward(double forward, double carry, double carryFactor, double financingDf,
            double pvDividends) {}

    /** F = (S - sum A_i C(t_i)) / C(T), C(t) = exp(-Z(t) t - S(t) + B(t)) (J-C-5). */
    public static TermForward forward(FinancingCurve c, double spot, double maturity, double[] dt, double[] da) {
        if (dt.length != da.length) {
            throw new QfError("E_INPUT", "dividend arrays must pair up", "dividend_amounts");
        }
        for (int k = 1; k < dt.length; k++) {
            if (!(dt[k] > dt[k - 1])) {
                throw new QfError("E_INPUT", "dividend_times must be strictly increasing", "dividend_times");
            }
        }
        if (!(spot > 0)) {
            throw new QfError("E_DOMAIN", "spot must be positive", "spot");
        }
        if (!(maturity > 0 && maturity <= c.cover())) {
            throw new QfError("E_DOMAIN", "maturity must lie in (0, coverage]", "maturity_years");
        }
        for (double a : da) {
            if (a < 0) {
                throw new QfError("E_DOMAIN", "dividends must be non-negative", "dividend_amounts");
            }
        }
        double pv = 0;
        for (int k = 0; k < dt.length; k++) {
            if (dt[k] > 0 && dt[k] <= maturity) {
                pv += da[k] * carry(c, dt[k]);
            }
        }
        double cf = carry(c, maturity);
        double f = (spot - pv) / cf;
        if (!(f > 0)) {
            throw new QfError("E_DOMAIN", "forward is not positive", "dividend_amounts");
        }
        return new TermForward(f, f - spot, cf, c.financingDf(maturity), pv);
    }

    private static double carry(FinancingCurve c, double t) {
        return Math.exp(-c.zt(t) - c.s(t) + c.b(t));
    }

    /** liq.curve.cost outputs; optimalHorizon and minCost are null without an interior optimum. */
    public record LiquidityCurve(double spreadCost, double[][] impact, double[] timingRisk, double[][] totalCost,
            double[] optimalHorizon, double[] minCost) {}

    /** c(Q, h) = s + Y sigma (Q / (V h))^delta + z sigma sqrt(h / 3) (J-C-6 to J-C-8). */
    public static LiquidityCurve liquidity(double halfSpreadBps, double volume, double vol, double coefficient,
            double exponent, double z, double[] sizes, double[] horizons) {
        if (sizes.length == 0 || horizons.length == 0) {
            throw new QfError("E_INPUT", "sizes and horizons_days must be non-empty", "sizes");
        }
        boolean bad = halfSpreadBps < 0 || !(volume > 0) || vol < 0 || coefficient < 0 || z < 0
                || !(exponent > 0 && exponent <= 1);
        for (double q : sizes) {
            bad |= q < 0;
        }
        for (double h : horizons) {
            bad |= !(h > 0);
        }
        if (bad) {
            throw new QfError("E_DOMAIN", "liquidity curve input out of domain");
        }
        double sp = halfSpreadBps / 10000.0;
        int m = horizons.length;
        double[] risk = new double[m];
        for (int j = 0; j < m; j++) {
            risk[j] = z * vol * Math.sqrt(horizons[j] / 3.0);
        }
        double[][] imp = new double[sizes.length][m];
        double[][] tot = new double[sizes.length][m];
        for (int i = 0; i < sizes.length; i++) {
            for (int j = 0; j < m; j++) {
                imp[i][j] = coefficient * vol * Math.pow(sizes[i] / (volume * horizons[j]), exponent);
                tot[i][j] = sp + imp[i][j] + risk[j];
            }
        }
        double b = z * vol / Math.sqrt(3.0);
        double[] hs = null;
        double[] cs = null;
        if (b > 0 && coefficient > 0) {
            hs = new double[sizes.length];
            cs = new double[sizes.length];
            for (int i = 0; i < sizes.length; i++) {
                double a = coefficient * vol * Math.pow(sizes[i] / volume, exponent);
                if (a == 0) {
                    hs[i] = 0.0;
                    cs[i] = sp;
                    continue;
                }
                double h = Math.pow(2.0 * exponent * a / b, 1.0 / (exponent + 0.5));
                hs[i] = h;
                cs[i] = sp + a * Math.pow(h, -exponent) + b * Math.sqrt(h);
            }
        }
        return new LiquidityCurve(sp, imp, risk, tot, hs, cs);
    }
}
