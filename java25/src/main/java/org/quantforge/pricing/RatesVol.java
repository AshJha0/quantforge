package org.quantforge.pricing;

import java.util.function.DoubleUnaryOperator;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.vol.Black;
import org.quantforge.vol.Sabr;

/** Stage E4: SABR swaption cube, caplet stripping, bond futures options, inflation caps (rates-vol-cube.md,
 * rulings E-B8 to E-B13). */
public final class RatesVol {
    private RatesVol() {}

    public record Cube(long[] expiriesMonths, long[] tenorsMonths, double[][] alpha, double[][] beta, double[][] rho,
                       double[][] nu) {}

    public record CubePrice(double price, double forward, double annuity, double vol, Sabr.Params sabr) {}

    private static void increasing(long[] x, String key) {
        if (x.length == 0) {
            throw new QfError("E_INPUT", key + " is empty", key);
        }
        for (int i = 1; i < x.length; i++) {
            if (x[i] <= x[i - 1]) {
                throw new QfError("E_INPUT", key + " must increase", key);
            }
        }
    }

    private static void shape(double[][] m, int rows, int cols, String key) {
        if (m.length != rows) {
            throw new QfError("E_INPUT", key + " has the wrong shape", key);
        }
        for (double[] r : m) {
            if (r.length != cols) {
                throw new QfError("E_INPUT", key + " has the wrong shape", key);
            }
        }
    }

    /** {index, weight} of x on increasing nodes; outside is E_INPUT (no extrapolation). */
    private static double[] locate(double[] nodes, double x, String key) {
        int n = nodes.length;
        if (x < nodes[0] || x > nodes[n - 1]) {
            throw new QfError("E_INPUT", key + " is outside the cube", key);
        }
        if (n == 1) {
            return new double[] {0, 0.0};
        }
        int i = 0;
        while (i < n - 2 && x > nodes[i + 1]) {
            i++;
        }
        return new double[] {i, (x - nodes[i]) / (nodes[i + 1] - nodes[i])};
    }

    private static double bilinear(double[][] m, double[] e, double[] l) {
        int i = (int) e[0];
        int j = (int) l[0];
        int i1 = Math.min(i + 1, m.length - 1);
        int j1 = Math.min(j + 1, m[0].length - 1);
        double u = e[1];
        double v = l[1];
        return (1 - u) * (1 - v) * m[i][j] + (1 - u) * v * m[i][j1] + u * (1 - v) * m[i1][j] + u * v * m[i1][j1];
    }

    /** SABR parameters bilinear in (ACT/365F expiry time, tenor years), read at the swaption's forward (E-B8). */
    public static CubePrice priceCube(Curve d, Curve p, Cube c, boolean payer, long expiryMonths, long tenorMonths,
                                      double k, double notional) {
        increasing(c.expiriesMonths(), "expiries_months");
        increasing(c.tenorsMonths(), "tenors_months");
        int rows = c.expiriesMonths().length;
        int cols = c.tenorsMonths().length;
        shape(c.alpha(), rows, cols, "alpha");
        shape(c.beta(), rows, cols, "beta");
        shape(c.rho(), rows, cols, "rho");
        shape(c.nu(), rows, cols, "nu");
        if (expiryMonths < 1 || expiryMonths > 1200 || tenorMonths < 1 || tenorMonths > 1200) {
            throw new QfError("E_INPUT", "expiry_months and tenor_months must be 1 to 1200", "trade");
        }
        double[] te = new double[rows];
        for (int i = 0; i < rows; i++) {
            te[i] = d.time(CapSwaption.start(d, c.expiriesMonths()[i]));
        }
        double[] tl = new double[cols];
        for (int j = 0; j < cols; j++) {
            tl[j] = c.tenorsMonths()[j] / 12.0;
        }
        double t = d.time(CapSwaption.start(d, expiryMonths));
        double[] e = locate(te, t, "expiry_months");
        double[] l = locate(tl, tenorMonths / 12.0, "tenor_months");
        for (int i = 0; i < rows; i++) {
            for (int j = 0; j < cols; j++) {
                if (!(c.alpha()[i][j] > 0.0) || !(c.beta()[i][j] >= 0.0 && c.beta()[i][j] <= 1.0)
                        || !(Math.abs(c.rho()[i][j]) < 1.0) || !(c.nu()[i][j] >= 0.0)) {
                    throw new QfError("E_DOMAIN", "cube SABR parameters out of domain", "cube");
                }
            }
        }
        Sabr.Params s = new Sabr.Params(bilinear(c.alpha(), e, l), bilinear(c.beta(), e, l),
                bilinear(c.rho(), e, l), bilinear(c.nu(), e, l));
        double[] fa = CapSwaption.forwardAnnuity(d, p, expiryMonths, tenorMonths);
        if (!(k > 0.0) || !(fa[0] > 0.0)) {
            throw new QfError("E_DOMAIN", "strike and forward must be above 0", "strike");
        }
        double vol = Sabr.hagan(fa[0], k, fa[2], s);
        double price = notional * fa[1] * Black.lognormal(payer ? 1.0 : -1.0, fa[0], k, fa[2], 1.0, vol);
        return new CubePrice(price, fa[0], fa[1], vol, s);
    }

    public record Strip(double[] capletVols, double[] capPrices) {}

    /** Piecewise-constant caplet vols between cap maturities (E-B9); a segment with no positive root is
     * E_ARBITRAGE (E-B10). */
    public static Strip strip(Curve d, Curve p, boolean normal, long startMonths, double k, long[] tenors,
                              double[] flat, double notional) {
        if (tenors.length == 0) {
            throw new QfError("E_INPUT", "cap_tenors_months is empty", "cap_tenors_months");
        }
        for (int i = 0; i < tenors.length; i++) {
            if (tenors[i] < 3 || tenors[i] % 3 != 0 || (i > 0 && tenors[i] <= tenors[i - 1])) {
                throw new QfError("E_INPUT", "cap tenors must be increasing multiples of 3", "cap_tenors_months");
            }
        }
        if (flat.length != tenors.length) {
            throw new QfError("E_INPUT", "one flat vol per cap tenor", "flat_vols");
        }
        for (double v : flat) {
            if (!(v > 0.0)) {
                throw new QfError("E_DOMAIN", "flat vols must be above 0", "flat_vols");
            }
        }
        if (startMonths < 1) {
            throw new QfError("E_INPUT", "start_months must be at least 1", "start_months");
        }
        if (startMonths > 1200 || tenors[tenors.length - 1] > 1200) {
            throw new QfError("E_INPUT", "months must be at most 1200", "cap_tenors_months");
        }
        CapSwaption.Caplets c = CapSwaption.caplets(d, p, startMonths, tenors[tenors.length - 1]);
        CapSwaption.checkBlack(normal, k, c.forward());
        int m = c.forward().length;
        double[] vols = new double[m];
        double[] targets = new double[tenors.length];
        double lower = 1e-10; // search interval [1e-10, 5] Black or [1e-10, 0.5] Bachelier (ruling E-B32)
        double upper = normal ? 0.5 : 5.0;
        int done = 0;
        double known = 0.0;
        for (int j = 0; j < tenors.length; j++) {
            int upto = (int) Math.min(m, tenors[j] / 3);
            double sumFlat = 0.0;
            for (int i = 0; i < upto; i++) {
                sumFlat += c.price(i, normal, true, k, notional, flat[j]);
            }
            double target = sumFlat;
            targets[j] = target;
            int from = done;
            double base = known;
            DoubleUnaryOperator g = v -> {
                double s = base;
                for (int i = from; i < upto; i++) {
                    s += c.price(i, normal, true, k, notional, v);
                }
                return s - target;
            };
            if (!(g.applyAsDouble(lower) < 0.0)) {
                throw new QfError("E_ARBITRAGE", "cap " + j + " needs a caplet vol at or below zero");
            }
            if (g.applyAsDouble(upper) < 0.0) {
                throw new QfError("E_DOMAIN", "cap " + j + " needs a caplet vol above the search bound", "flat_vols");
            }
            double v = bisect(g, lower, upper);
            for (int i = from; i < upto; i++) {
                vols[i] = v;
                known += c.price(i, normal, true, k, notional, v);
            }
            done = upto;
        }
        return new Strip(vols, targets);
    }

    /** Bisection to the last representable midpoint; g(a) < 0 < g(b), g increasing. */
    static double bisect(DoubleUnaryOperator g, double a, double b) {
        for (int i = 0; i < 2000; i++) {
            double mid = 0.5 * (a + b);
            if (mid <= a || mid >= b) {
                break;
            }
            double gm = g.applyAsDouble(mid);
            if (gm == 0.0) {
                return mid;
            }
            if (gm < 0.0) {
                a = mid;
            } else {
                b = mid;
            }
        }
        return 0.5 * (a + b);
    }

    private static void checkFutures(double f, double k, double t, double df) {
        if (!(t > 0.0) || !(f > 0.0) || !(k > 0.0) || !(df > 0.0)) {
            throw new QfError("E_DOMAIN", "expiry_years, futures_price, strike and discount_factor must be above 0");
        }
    }

    /** Black-76 on the futures price, premium paid at the discount date (E-B11). Per 100 face. */
    public static double futuresOption(double phi, double f, double k, double t, double df, double vol) {
        checkFutures(f, k, t, df);
        if (!(vol >= 0.0)) {
            throw new QfError("E_DOMAIN", "vol must not be negative", "vol");
        }
        return Black.lognormal(phi, f, k, t, df, vol);
    }

    /** {price vol, yield vol = price vol / (duration x yield)} (E-B11). */
    public static double[] futuresImpliedVol(double phi, double f, double k, double t, double df, double premium,
                                             double yield, double duration) {
        checkFutures(f, k, t, df);
        double intrinsic = df * Math.max(phi * (f - k), 0.0);
        double bound = df * (phi > 0 ? f : k);
        if (!(premium > intrinsic) || !(premium < bound)) {
            throw new QfError("E_DOMAIN", "premium is outside the no-arbitrage range", "premium");
        }
        DoubleUnaryOperator g = v -> Black.lognormal(phi, f, k, t, df, v) - premium;
        double hi = 1.0;
        for (int i = 0; i < 200 && g.applyAsDouble(hi) < 0.0; i++) {
            hi *= 2.0;
        }
        if (!(yield > 0.0) || !(duration > 0.0)) {
            throw new QfError("E_DOMAIN", "ctd_yield and ctd_modified_duration must be above 0 (ruling E-B38)", "ctd_yield");
        }
        double v = bisect(g, 0.0, hi);
        return new double[] {v, v / (duration * yield)};
    }

    private static double option(boolean normal, double phi, double f, double k, double t, double v) {
        return normal ? Black.normal(phi, f, k, t, 1.0, v) : Black.lognormal(phi, f, k, t, 1.0, v);
    }

    public record YoyPeriod(double accrual, double discount, double forward, double expiry, double vol) {}

    /** YoY caplets with option time to the fixing (E-B12). Returns the caplets; the price is their sum. */
    public static double[] yoyCaplets(boolean normal, boolean cap, double k, double notional, YoyPeriod[] periods) {
        if (periods.length == 0) {
            throw new QfError("E_INPUT", "periods is empty", "periods");
        }
        for (YoyPeriod q : periods) {
            if (!normal && (!(k > 0.0) || !(q.forward() > 0.0))) {
                throw new QfError("E_DOMAIN", "BLACK_76 needs a positive strike and forward", "strike");
            }
            if (!(q.expiry() > 0.0)) {
                throw new QfError("E_DOMAIN", "expiry_years must be above 0", "periods");
            }
            if (!(q.vol() >= 0.0)) {
                throw new QfError("E_DOMAIN", "vol must not be negative", "periods");
            }
        }
        double[] out = new double[periods.length];
        for (int i = 0; i < out.length; i++) {
            YoyPeriod q = periods[i];
            out[i] = notional * q.accrual() * q.discount() * option(normal, cap ? 1.0 : -1.0, q.forward(), k,
                    q.expiry(), q.vol());
        }
        return out;
    }

    /** {price, strike ratio (1 + K)^T} of a zero-coupon inflation cap or floor (E-B13). */
    public static double[] zcCap(boolean normal, boolean cap, double fwdRatio, double years, double k, double df,
                                 double vol, double notional) {
        if (!normal && !(fwdRatio > 0.0)) {
            throw new QfError("E_DOMAIN", "BLACK_76 needs a positive forward", "forward_index_ratio");
        }
        if (!(1.0 + k > 0.0)) {
            throw new QfError("E_DOMAIN", "1 + strike must be above 0 (ruling E-B37)", "strike");
        }
        double ratio = Math.pow(1.0 + k, years);
        if (!(years > 0.0)) {
            throw new QfError("E_DOMAIN", "years must be above 0", "years");
        }
        if (!(vol >= 0.0)) {
            throw new QfError("E_DOMAIN", "vol must not be negative", "vol");
        }
        return new double[] {notional * df * option(normal, cap ? 1.0 : -1.0, fwdRatio, ratio, years, vol), ratio};
    }
}
