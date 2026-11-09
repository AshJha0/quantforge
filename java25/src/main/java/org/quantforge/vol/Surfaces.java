package org.quantforge.vol;

import org.quantforge.core.Finite;

import java.util.ArrayList;
import java.util.List;
import org.quantforge.core.QfError;

/** Stage E1: arbitrage checks on SVI surfaces, SSVI to SVI, local and forward vol (arb-free-surfaces.md,
 * local-and-forward-vol.md, rulings E-A1 to E-A8). */
public final class Surfaces {
    private Surfaces() {}

    public static final int MAX_SLICES = 100;
    public static final int MAX_POINTS = 10_000;

    /** One SVI slice at its expiry. */
    public record Slice(double expiry, Smile.Svi svi) {}

    public record Cell(int expiry, int k) {}

    public record Wing(int expiry, String side, String kind) {}

    public record Check(List<Cell> butterfly, List<Cell> calendar, List<Wing> wings) {
        public boolean arbitrageFree() {
            return butterfly.isEmpty() && calendar.isEmpty() && wings.isEmpty();
        }
    }

    /** Checks the slices object (its E_LIMIT is raised at the input gate, ruling E-A34). */
    public static void checkSlices(List<Slice> slices) {
        checkSliceShape(slices);
        checkSliceValues(slices);
    }

    /** The E_INPUT rules of the slices object. */
    public static void checkSliceShape(List<Slice> slices) {
        if (slices.isEmpty()) {
            throw new QfError("E_INPUT", "slices is empty", "slices");
        }
        for (int j = 1; j < slices.size(); j++) {
            if (!(slices.get(j).expiry() > slices.get(j - 1).expiry())) {
                throw new QfError("E_INPUT", "expiry_years must increase", "slices");
            }
        }
    }

    /** The E_DOMAIN rules of the slices object. */
    public static void checkSliceValues(List<Slice> slices) {
        for (Slice s : slices) {
            if (!(s.expiry() > 0.0)) {
                throw new QfError("E_DOMAIN", "expiry_years must be above 0", "slices");
            }
        }
        for (Slice s : slices) {
            s.svi().check();
        }
        if (slices.size() > MAX_SLICES) {
            throw new QfError("E_LIMIT", "more than " + MAX_SLICES + " slices", "slices");
        }
    }

    /** Strictly increasing, 1 to 10,000 points. */
    public static void checkGrid(double[] k) {
        Finite.check("k", k);
        if (k.length == 0) {
            throw new QfError("E_INPUT", "log_moneyness is empty", "log_moneyness");
        }
        for (int i = 1; i < k.length; i++) {
            if (!(k[i] > k[i - 1])) {
                throw new QfError("E_INPUT", "log_moneyness must increase", "log_moneyness");
            }
        }
        if (k.length > MAX_POINTS) {
            throw new QfError("E_LIMIT", "log_moneyness has too many points", "log_moneyness");
        }
    }

    /** Grid butterfly and calendar checks plus the wing rules, all strict (rulings E-A1, E-A2). */
    public static Check check(List<Slice> slices, double[] k) {
        Finite.check("k", k);
        List<Cell> fly = new ArrayList<>();
        List<Cell> cal = new ArrayList<>();
        List<Wing> wings = new ArrayList<>();
        for (int j = 0; j < slices.size(); j++) {
            Smile.Svi s = slices.get(j).svi();
            for (int i = 0; i < k.length; i++) {
                if (s.g(k[i]) < 0.0) {
                    fly.add(new Cell(j, i));
                }
            }
        }
        for (int j = 1; j < slices.size(); j++) {
            Smile.Svi s = slices.get(j).svi();
            Smile.Svi p = slices.get(j - 1).svi();
            for (int i = 0; i < k.length; i++) {
                if (s.w(k[i]) < p.w(k[i])) {
                    cal.add(new Cell(j, i));
                }
            }
        }
        for (int j = 0; j < slices.size(); j++) {
            Smile.Svi s = slices.get(j).svi();
            if (leftSlope(s) >= 2.0) { // slope 2 is flagged (ruling E-A15)
                wings.add(new Wing(j, "LEFT", "LEE"));
            }
            if (rightSlope(s) >= 2.0) {
                wings.add(new Wing(j, "RIGHT", "LEE"));
            }
            if (j >= 1) {
                Smile.Svi p = slices.get(j - 1).svi();
                if (below(leftSlope(s), leftConstant(s), leftSlope(p), leftConstant(p))) {
                    wings.add(new Wing(j, "LEFT", "CALENDAR"));
                }
                if (below(rightSlope(s), rightConstant(s), rightSlope(p), rightConstant(p))) {
                    wings.add(new Wing(j, "RIGHT", "CALENDAR"));
                }
            }
        }
        return new Check(fly, cal, wings);
    }

    private static boolean below(double s, double c, double sPrev, double cPrev) {
        return s < sPrev || (s == sPrev && c < cPrev);
    }

    static double leftSlope(Smile.Svi s) {
        return s.b() * (1 - s.rho());
    }

    static double leftConstant(Smile.Svi s) {
        return s.a() + s.b() * (1 - s.rho()) * s.m();
    }

    static double rightSlope(Smile.Svi s) {
        return s.b() * (1 + s.rho());
    }

    static double rightConstant(Smile.Svi s) {
        return s.a() - s.b() * (1 + s.rho()) * s.m();
    }

    /** The SVI slice equal to an SSVI slice at theta ([GJ14] section 3). */
    public static Smile.Svi ssviToSvi(double rho, double eta, double gamma, double theta) {
        Finite.check("rho", rho);
        Finite.check("eta", eta);
        Finite.check("gamma", gamma);
        Finite.check("theta", theta);
        Smile.check(new Smile.Ssvi(rho, eta, gamma));
        if (!(theta > 0.0)) {
            throw new QfError("E_DOMAIN", "theta must be above 0", "theta");
        }
        double phi = eta * Math.pow(theta, -gamma) * Math.pow(1.0 + theta, gamma - 1.0);
        return new Smile.Svi(theta * (1 - rho * rho) / 2.0, theta * phi / 2.0, rho, -rho / phi,
                Math.sqrt(1 - rho * rho) / phi);
    }

    /** {w, w_k, w_kk, w_T} at (T, k) by ruling E-A4. */
    static double[] surface(List<Slice> slices, double t, double k) {
        int n = slices.size();
        Slice first = slices.getFirst();
        Slice last = slices.getLast();
        if (n == 1 || t < first.expiry() || t >= last.expiry()) {
            Slice s = t < first.expiry() ? first : last;
            double f = t / s.expiry();
            double[] d = derivatives(s.svi(), k);
            return new double[] {d[0] * f, d[1] * f, d[2] * f, d[0] / s.expiry()};
        }
        int j = 0;
        while (slices.get(j + 1).expiry() <= t) {
            j++;
        }
        Slice a = slices.get(j);
        Slice b = slices.get(j + 1);
        double gap = b.expiry() - a.expiry();
        double lambda = (t - a.expiry()) / gap;
        double[] da = derivatives(a.svi(), k);
        double[] db = derivatives(b.svi(), k);
        return new double[] {
            (1 - lambda) * da[0] + lambda * db[0],
            (1 - lambda) * da[1] + lambda * db[1],
            (1 - lambda) * da[2] + lambda * db[2],
            (db[0] - da[0]) / gap};
    }

    /** {w, w', w''} of a raw SVI slice. */
    static double[] derivatives(Smile.Svi s, double k) {
        double e = k - s.m();
        double r = Math.sqrt(e * e + s.sigma() * s.sigma());
        return new double[] {s.w(k), s.b() * (s.rho() + e / r), s.b() * s.sigma() * s.sigma() / (r * r * r)};
    }

    public record LocalVol(double[] totalVariance, double[] impliedVol, double[] localVol) {}

    /** Dupire local vol in total-variance form [Gat06, eq. 1.10]; any arbitrage point is E_ARBITRAGE. */
    public static LocalVol dupire(List<Slice> slices, double[] t, double[] k) {
        Finite.check("t", t);
        Finite.check("k", k);
        int n = t.length;
        double[] w = new double[n];
        double[] iv = new double[n];
        double[] lv = new double[n];
        for (int i = 0; i < n; i++) {
            double[] s = surface(slices, t[i], k[i]);
            double u = 1.0 - k[i] * s[1] / (2.0 * s[0]);
            double g = u * u - (s[1] * s[1] / 4.0) * (1.0 / s[0] + 0.25) + s[2] / 2.0;
            if (!(s[3] > 0.0)) {
                throw new QfError("E_ARBITRAGE", "w_T is not positive: calendar arbitrage at point " + i);
            }
            if (!(g > 0.0)) {
                throw new QfError("E_ARBITRAGE", "g is not positive: butterfly arbitrage at point " + i);
            }
            w[i] = s[0];
            iv[i] = Math.sqrt(s[0] / t[i]);
            lv[i] = Math.sqrt(s[3] / g);
        }
        return new LocalVol(w, iv, lv);
    }

    /** Forward vols between expiries, additive in variance; a negative forward variance is E_ARBITRAGE. */
    public static double[] forwardVols(double[] t, double[] v) {
        Finite.check("t", t);
        Finite.check("v", v);
        double[] out = new double[t.length];
        out[0] = v[0];
        for (int i = 1; i < t.length; i++) {
            double x = (v[i] * v[i] * t[i] - v[i - 1] * v[i - 1] * t[i - 1]) / (t[i] - t[i - 1]);
            if (x < 0.0) {
                throw new QfError("E_ARBITRAGE", "negative forward variance at index " + i);
            }
            out[i] = Math.sqrt(x);
        }
        return out;
    }

    /** {mean change, annualised sample standard deviation of changes} (ruling E-A7). */
    public static double[] volOfVol(double[] v, double periodsPerYear, boolean log) {
        Finite.check("v", v);
        Finite.check("periodsPerYear", periodsPerYear);
        int n = v.length - 1;
        double[] x = new double[n];
        double mean = 0.0;
        for (int i = 0; i < n; i++) {
            x[i] = log ? Math.log(v[i + 1] / v[i]) : v[i + 1] - v[i];
            mean += x[i];
        }
        mean /= n;
        double ss = 0.0;
        for (double d : x) {
            ss += (d - mean) * (d - mean);
        }
        return new double[] {mean, Math.sqrt(periodsPerYear) * Math.sqrt(ss / (n - 1))};
    }
}
