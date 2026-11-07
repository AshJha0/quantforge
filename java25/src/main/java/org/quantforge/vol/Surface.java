package org.quantforge.vol;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.quantforge.core.QfError;

/** Grid vol surface: linear in k on a slice, linear in T in total variance (smile-and-surface.md). */
public final class Surface {
    private final double[] t;
    private final double[] k;
    private final double[][] v;

    public Surface(double[] t, double[] k, double[][] v) {
        this.t = t;
        this.k = k;
        this.v = v;
    }

    public void check() {
        boolean bad = t.length == 0 || k.length == 0 || v.length != t.length;
        for (int i = 1; i < t.length; i++) {
            bad |= t[i] <= t[i - 1];
        }
        for (int i = 1; i < k.length; i++) {
            bad |= k[i] <= k[i - 1];
        }
        for (double[] row : v) {
            bad |= row.length != k.length;
        }
        if (bad) {
            throw new QfError("E_INPUT", "surface grids or shape");
        }
        for (double x : t) {
            if (x <= 0.0) {
                throw new QfError("E_DOMAIN", "grid time is not positive");
            }
        }
        for (double[] row : v) {
            for (double x : row) {
                if (x <= 0.0) {
                    throw new QfError("E_DOMAIN", "vol is not positive");
                }
            }
        }
    }

    private double slice(int j, double x) {
        double[] row = v[j];
        int n = k.length;
        if (x <= k[0]) {
            return row[0] * row[0] * t[j];
        }
        if (x >= k[n - 1]) {
            return row[n - 1] * row[n - 1] * t[j];
        }
        int i = 0;
        while (x >= k[i + 1]) {
            i++;
        }
        double u = (x - k[i]) / (k[i + 1] - k[i]);
        return (1.0 - u) * row[i] * row[i] * t[j] + u * row[i + 1] * row[i + 1] * t[j];
    }

    public double totalVariance(double time, double x) {
        if (time <= 0.0) {
            throw new QfError("E_DOMAIN", "expiry_years must be above 0");
        }
        int n = t.length;
        if (time <= t[0]) {
            return slice(0, x) * time / t[0];
        }
        if (time >= t[n - 1]) {
            return slice(n - 1, x) * time / t[n - 1];
        }
        int j = 0;
        while (time >= t[j + 1]) {
            j++;
        }
        double u = (time - t[j]) / (t[j + 1] - t[j]);
        return (1.0 - u) * slice(j, x) + u * slice(j + 1, x);
    }

    private static Map<String, Object> entry(int j, int i, String kind) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("expiry_index", (long) j);
        m.put("k_index", (long) i);
        if (kind != null) {
            m.put("kind", kind);
        }
        return m;
    }

    public List<Object> calendarViolations() {
        List<Object> out = new ArrayList<>();
        for (int j = 1; j < t.length; j++) {
            for (int i = 0; i < k.length; i++) {
                if (v[j][i] * v[j][i] * t[j] < v[j - 1][i] * v[j - 1][i] * t[j - 1] - 1e-12) {
                    out.add(entry(j, i, null));
                }
            }
        }
        return out;
    }

    public List<Object> butterflyViolations() {
        List<Object> out = new ArrayList<>();
        int n = k.length;
        for (int j = 0; j < t.length; j++) {
            double[] c = new double[n];
            double[] x = new double[n];
            for (int i = 0; i < n; i++) {
                x[i] = Math.exp(k[i]);
                c[i] = Black.lognormal(1.0, 1.0, x[i], t[j], 1.0, v[j][i]);
            }
            double[] s = new double[Math.max(n - 1, 0)];
            for (int i = 0; i + 1 < n; i++) {
                s[i] = (c[i + 1] - c[i]) / (x[i + 1] - x[i]);
                if (s[i] < -1.0 - 1e-12 || s[i] > 1e-12) {
                    out.add(entry(j, i, "SLOPE"));
                }
            }
            for (int i = 0; i + 2 < n; i++) {
                if (s[i + 1] < s[i] - 1e-12) {
                    out.add(entry(j, i + 1, "CONVEXITY"));
                }
            }
        }
        return out;
    }

    public record Position(double phi, double forward, double strike, double discount, double t, double quantity) {}

    public double pv(List<Position> book) {
        double sum = 0.0;
        for (Position p : book) {
            double vol = Math.sqrt(totalVariance(p.t(), Math.log(p.strike() / p.forward())) / p.t());
            sum += p.quantity() * Black.lognormal(p.phi(), p.forward(), p.strike(), p.t(), p.discount(), vol);
        }
        return sum;
    }

    private Surface moved(int j, int i, double h) {
        double[][] m = new double[v.length][];
        for (int r = 0; r < v.length; r++) {
            m[r] = v[r].clone();
        }
        m[j][i] += h;
        return new Surface(t, k, m);
    }

    private Surface parallel(double h) {
        double[][] m = new double[v.length][];
        for (int r = 0; r < v.length; r++) {
            m[r] = v[r].clone();
            for (int i = 0; i < m[r].length; i++) {
                m[r][i] += h;
            }
        }
        return new Surface(t, k, m);
    }

    public record Vega(double pv, double[][] bucket, double parallel, double sum) {}

    public Vega vega(List<Position> book) {
        double h = 1e-4;
        for (double[] row : v) {
            for (double x : row) {
                if (x - h <= 0.0) {
                    throw new QfError("E_DOMAIN", "a node is too low to bump");
                }
            }
        }
        double[][] b = new double[v.length][k.length];
        double sum = 0.0;
        for (int j = 0; j < v.length; j++) {
            for (int i = 0; i < k.length; i++) {
                b[j][i] = (moved(j, i, h).pv(book) - moved(j, i, -h).pv(book)) / 2e-4;
                sum += b[j][i];
            }
        }
        return new Vega(pv(book), b, (parallel(h).pv(book) - parallel(-h).pv(book)) / 2e-4, sum);
    }
}
