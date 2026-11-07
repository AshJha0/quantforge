package org.quantforge.vol;

import java.util.ArrayList;
import java.util.List;
import org.quantforge.core.QfError;

/** SVI and SSVI (smile-and-surface.md). */
public final class Smile {
    private Smile() {}

    public record Svi(double a, double b, double rho, double m, double sigma) {
        public void check() {
            if (b < 0.0 || Math.abs(rho) >= 1.0 || sigma <= 0.0 || a + b * sigma * Math.sqrt(1.0 - rho * rho) <= 0.0) {
                throw new QfError("E_DOMAIN", "svi parameters");
            }
        }

        public double w(double k) {
            double e = k - m;
            return a + b * (rho * e + Math.sqrt(e * e + sigma * sigma));
        }

        public double g(double k) {
            double e = k - m;
            double r = Math.sqrt(e * e + sigma * sigma);
            double w = w(k);
            double w1 = b * (rho + e / r);
            double w2 = b * sigma * sigma / (r * r * r);
            double u = 1.0 - k * w1 / (2.0 * w);
            return u * u - (w1 * w1 / 4.0) * (1.0 / w + 0.25) + w2 / 2.0;
        }
    }

    public record SviFit(Svi svi, double rmse) {}

    private static Svi svi(double[] p) {
        double b = Math.exp(p[1]);
        double rho = Math.tanh(p[2]);
        double sigma = Math.exp(p[4]);
        return new Svi(Math.exp(p[0]) - b * sigma * Math.sqrt(1.0 - rho * rho), b, rho, p[3], sigma);
    }

    public static SviFit calibrateSvi(double[] k, double[] w, double[] weights) {
        int n = k.length;
        if (n < 5 || w.length != n || (weights != null && weights.length != n)) {
            throw new QfError("E_INPUT", "too few points, or lengths differ");
        }
        for (int i = 1; i < n; i++) {
            if (k[i] <= k[i - 1]) {
                throw new QfError("E_INPUT", "log_moneyness must increase");
            }
        }
        double min = Double.POSITIVE_INFINITY;
        double max = 0.0;
        double sw = 0.0;
        for (int i = 0; i < n; i++) {
            if (w[i] <= 0.0 || (weights != null && weights[i] <= 0.0)) {
                throw new QfError("E_DOMAIN", "total_variance or weight");
            }
            min = Math.min(min, w[i]);
            max = Math.max(max, w[i]);
            sw += weights == null ? 1.0 : weights[i];
        }
        double span = k[n - 1] - k[0];
        List<double[]> starts = new ArrayList<>();
        for (double mf : new double[] {0.25, 0.5, 0.75}) {
            for (double sf : new double[] {0.05, 0.2, 0.6}) {
                for (double rho : new double[] {-0.6, 0.0, 0.6}) {
                    for (double vf : new double[] {0.5, 0.95}) {
                        starts.add(new double[] {Math.log(vf * min), Math.log(Math.max(max - min, 1e-6 * max) / span * 2.0),
                                Fit.atanh(rho), k[0] + mf * span, Math.log(sf * span)});
                    }
                }
            }
        }
        double[] best = Fit.best(p -> {
            Svi s = svi(p);
            double[] r = new double[n];
            for (int i = 0; i < n; i++) {
                r[i] = Math.sqrt(weights == null ? 1.0 : weights[i]) * (s.w(k[i]) - w[i]);
            }
            return r;
        }, starts);
        Svi s = svi(best);
        double sum = 0.0;
        for (int i = 0; i < n; i++) {
            double e = s.w(k[i]) - w[i];
            sum += (weights == null ? 1.0 : weights[i]) * e * e;
        }
        return new SviFit(s, Math.sqrt(sum / sw));
    }

    public record Ssvi(double rho, double eta, double gamma) {
        public double phi(double theta) {
            return eta * Math.pow(theta, -gamma) * Math.pow(1.0 + theta, gamma - 1.0);
        }

        public double w(double k, double theta) {
            double p = phi(theta) * k;
            return theta / 2.0 * (1.0 + rho * p + Math.sqrt((p + rho) * (p + rho) + 1.0 - rho * rho));
        }

        public boolean butterflyFree(double[] thetas) {
            double a = 1.0 + Math.abs(rho);
            for (double t : thetas) {
                double p = phi(t);
                if (!(t * p * a < 4.0 && t * p * p * a <= 4.0)) {
                    return false;
                }
            }
            return true;
        }

        public boolean calendarFree(double[] thetas) {
            for (double t : thetas) {
                if (rho * rho * (1.0 - gamma) / (1.0 + t) > 1.0 + Math.sqrt(1.0 - rho * rho)) {
                    return false;
                }
            }
            return true;
        }
    }

    public static void checkThetas(double[] thetas) {
        for (double t : thetas) {
            if (t <= 0.0) {
                throw new QfError("E_DOMAIN", "theta is not positive");
            }
        }
        for (int i = 1; i < thetas.length; i++) {
            if (thetas[i] <= thetas[i - 1]) {
                throw new QfError("E_INPUT", "thetas must increase");
            }
        }
    }

    public static void check(Ssvi s) {
        if (Math.abs(s.rho()) >= 1.0 || s.eta() <= 0.0 || s.gamma() <= 0.0 || s.gamma() > 1.0) {
            throw new QfError("E_DOMAIN", "ssvi parameters");
        }
    }

    public record SsviFit(Ssvi ssvi, double rmse) {}

    private static Ssvi ssvi(double[] p) {
        return new Ssvi(Math.tanh(p[0]), Math.exp(p[1]), 1.0 / (1.0 + Math.exp(-p[2])));
    }

    public static SsviFit calibrateSsvi(double[] thetas, double[] k, double[][] w) {
        int count = 0;
        boolean ragged = w.length != thetas.length;
        for (double[] row : w) {
            ragged |= row.length != k.length;
            count += row.length;
        }
        if (ragged || count < 3) {
            throw new QfError("E_INPUT", "too few points, or ragged rows");
        }
        checkThetas(thetas);
        int total = count;
        List<double[]> starts = new ArrayList<>();
        for (double rho : new double[] {-0.7, -0.3, 0.0, 0.3, 0.7}) {
            for (double eta : new double[] {0.3, 1.0, 2.5}) {
                for (double g : new double[] {0.2, 0.5, 0.8}) {
                    starts.add(new double[] {Fit.atanh(rho), Math.log(eta), Math.log(g / (1.0 - g))});
                }
            }
        }
        double[] best = Fit.best(p -> {
            Ssvi s = ssvi(p);
            double[] r = new double[total];
            int c = 0;
            for (int j = 0; j < thetas.length; j++) {
                for (int i = 0; i < k.length; i++) {
                    r[c++] = s.w(k[i], thetas[j]) - w[j][i];
                }
            }
            return r;
        }, starts);
        Ssvi s = ssvi(best);
        double sum = 0.0;
        for (int j = 0; j < thetas.length; j++) {
            for (int i = 0; i < k.length; i++) {
                double e = s.w(k[i], thetas[j]) - w[j][i];
                sum += e * e;
            }
        }
        return new SsviFit(s, Math.sqrt(sum / total));
    }
}
