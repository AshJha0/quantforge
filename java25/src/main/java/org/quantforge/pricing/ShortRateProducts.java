package org.quantforge.pricing;

import org.quantforge.core.Normal;
import org.quantforge.core.QfError;

/**
 * Short-rate caps and floors (wave 2e, ruling G-19) and the Hull-White sigma calibration (wave 2c, ruling G-17),
 * as specified in short-rate-models.md.
 */
public final class ShortRateProducts {
    private ShortRateProducts() {}

    /**
     * Cap or floor as a portfolio of bond options: a caplet is {@code (1 + K tau)} bond puts struck at
     * {@code 1 / (1 + K tau)}, a floorlet the calls.
     *
     * @param p the model
     * @param r0 short rate today (Vasicek and CIR)
     * @param times period times {@code t_0 < ... < t_m}
     * @param strike simple strike rate
     * @param cap true for a cap, false for a floor
     * @param notional notional
     * @return the caplet (or floorlet) prices in period order
     */
    public static double[] capFloor(ShortRate.Params p, double r0, double[] times, double strike, boolean cap,
                                    double notional) {
        double[] out = new double[times.length - 1];
        for (int i = 1; i < times.length; i++) {
            double g = 1.0 + strike * (times[i] - times[i - 1]);
            out[i - 1] = notional * g * ShortRate.bondOption(p, r0, !cap, 1.0 / g, times[i - 1], times[i]);
        }
        return out;
    }

    /**
     * One swaption of a calibration strip.
     *
     * @param expiry expiry in years
     * @param pay payment times
     * @param rate fixed rate
     * @param payer true for a payer
     * @param target target price per unit notional
     */
    public record Quote(double expiry, double[] pay, double rate, boolean payer, double target) {}

    /**
     * The calibration result.
     *
     * @param sigma fitted volatility
     * @param fitted model prices per unit notional at {@code sigma}
     * @param rmse root mean squared price error
     */
    public record Fit(double sigma, double[] fitted, double rmse) {}

    private static final double LO = 1e-4;
    private static final double HI = 1.0;
    private static final int SCAN = 2000;

    private static ShortRate.Params hw(ShortRate.Curve curve, double a, double sigma) {
        return new ShortRate.Params(ShortRate.Model.HULL_WHITE, a, sigma, 0.0, curve);
    }

    private static double objective(ShortRate.Curve curve, double a, double sigma, Quote[] q) {
        double f = 0.0;
        for (Quote x : q) {
            double e = ShortRate.swaption(hw(curve, a, sigma), x.expiry(), x.pay(), x.rate(), x.payer(), 1.0)
                    .price() - x.target();
            f += e * e;
        }
        return f;
    }

    /** dF/dsigma: the exercise boundary contributes nothing, so each bond option's vega at fixed strike. */
    private static double gradient(ShortRate.Curve curve, double a, double sigma, Quote[] q) {
        ShortRate.Params p = hw(curve, a, sigma);
        double g = 0.0;
        for (Quote x : q) {
            double price = ShortRate.swaption(p, x.expiry(), x.pay(), x.rate(), x.payer(), 1.0).price();
            double vega = 0.0;
            int n = x.pay().length;
            double t0 = x.expiry();
            double rStar = critical(p, x);
            double pt = curve.df(t0);
            for (int i = 0; i < n; i++) {
                double ti = x.pay()[i];
                double c = x.rate() * (ti - (i == 0 ? t0 : x.pay()[i - 1])) + (i == n - 1 ? 1.0 : 0.0);
                double k = ShortRate.zcb(p, rStar, t0, ti);
                double ps = curve.df(ti);
                double sp = sigma * ShortRate.bFactor(a, ti - t0) * Math.sqrt(-Math.expm1(-2.0 * a * t0) / (2.0 * a));
                double h = Math.log(ps / (k * pt)) / sp + sp / 2.0;
                vega += c * ps * Normal.pdf(h) * sp / sigma;
            }
            g += 2.0 * (price - x.target()) * vega;
        }
        return g;
    }

    private static double critical(ShortRate.Params p, Quote x) {
        int n = x.pay().length;
        double t0 = x.expiry();
        double[] c = new double[n];
        for (int i = 0; i < n; i++) {
            c[i] = x.rate() * (x.pay()[i] - (i == 0 ? t0 : x.pay()[i - 1])) + (i == n - 1 ? 1.0 : 0.0);
        }
        return ShortRate.criticalRate(p, t0, x.pay(), c);
    }

    /**
     * Least-squares Hull-White sigma with {@code a} fixed on {@code [1e-4, 1]}: a log-spaced scan brackets the
     * minimum, then bisection on the analytic gradient to a relative width of 1e-15.
     *
     * @param curve the initial curve
     * @param a mean reversion
     * @param q the strip
     * @return sigma, the fitted prices and the rmse
     */
    public static Fit calibrate(ShortRate.Curve curve, double a, Quote[] q) {
        double best = Double.POSITIVE_INFINITY;
        int at = -1;
        double ratio = Math.log(HI / LO) / SCAN;
        for (int i = 0; i <= SCAN; i++) {
            double f;
            try {
                f = objective(curve, a, LO * Math.exp(i * ratio), q);
            } catch (QfError e) {
                continue; // no critical rate at this sigma: not a candidate
            }
            if (f < best) {
                best = f;
                at = i;
            }
        }
        if (at == 0 || at == SCAN) {
            throw new QfError("E_NO_CONVERGENCE", "the minimum is at an end of [1e-4, 1] (ruling G-17)", "swaptions");
        }
        double lo = LO * Math.exp((at - 1) * ratio);
        double hi = LO * Math.exp((at + 1) * ratio);
        for (int it = 0; it < 200 && hi - lo > 1e-15 * hi; it++) {
            double mid = 0.5 * (lo + hi);
            if (gradient(curve, a, mid, q) > 0.0) {
                hi = mid;
            } else {
                lo = mid;
            }
        }
        double sigma = 0.5 * (lo + hi);
        double[] fitted = new double[q.length];
        double f = 0.0;
        for (int i = 0; i < q.length; i++) {
            Quote x = q[i];
            fitted[i] = ShortRate.swaption(hw(curve, a, sigma), x.expiry(), x.pay(), x.rate(), x.payer(), 1.0)
                    .price();
            double e = fitted[i] - x.target();
            f += e * e;
        }
        return new Fit(sigma, fitted, Math.sqrt(f / q.length));
    }
}
