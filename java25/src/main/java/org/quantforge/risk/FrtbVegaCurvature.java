package org.quantforge.risk;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import org.quantforge.core.QfError;

/**
 * FRTB standardised approach vega and curvature for GIRR, CSR non-securitisation, equity, commodity and FX
 * (frtb-sa-vega-curvature.md, ruling G-51).
 */
public final class FrtbVegaCurvature {
    private FrtbVegaCurvature() {}

    /** The risk classes of this slice. */
    public enum RiskClass {
        /** General interest rate risk; buckets are currencies. */
        GIRR,
        /** Credit spread, non-securitisation; buckets 1 to 18. */
        CSR_NONSEC,
        /** Equity; buckets 1 to 13. */
        EQUITY,
        /** Commodity; buckets 1 to 11. */
        COMMODITY,
        /** Foreign exchange; buckets are currency pairs. */
        FX
    }

    /**
     * One vega sensitivity.
     *
     * @param bucket bucket label
     * @param name name (empty for GIRR and FX)
     * @param optionMaturity option maturity in years
     * @param underlyingMaturity underlying residual maturity (GIRR)
     * @param vega the vega sensitivity VR_k
     */
    public record Vega(String bucket, String name, double optionMaturity, double underlyingMaturity, double vega) {}

    /**
     * One curvature factor.
     *
     * @param bucket bucket label
     * @param name name (empty for GIRR and FX)
     * @param up CVR up
     * @param down CVR down
     */
    public record Cvr(String bucket, String name, double up, double down) {}

    /**
     * A curvature bucket.
     *
     * @param bucket label
     * @param k bucket capital
     * @param s selected CVR sum
     * @param up true when the upward shock was selected
     */
    public record CurvBucket(String bucket, double k, double s, boolean up) {}

    /**
     * A curvature scenario.
     *
     * @param name high, medium or low
     * @param buckets the buckets
     * @param curvature the charge
     */
    public record CurvScenario(String name, List<CurvBucket> buckets, double curvature) {}

    /**
     * Curvature result.
     *
     * @param scenarios the three scenarios
     * @param capital the largest charge
     * @param binding its scenario
     */
    public record CurvResult(List<CurvScenario> scenarios, double capital, String binding) {}

    private static final String[] ORDER = {"high", "medium", "low"};

    private static double scale(String sc, double x) {
        return switch (sc) {
            case "high" -> Math.min(1.25 * x, 1.0);
            case "low" -> Math.max(2.0 * x - 1.0, 0.75 * x);
            default -> x;
        };
    }

    /**
     * Checks a bucket label for the class and returns its number (0 for GIRR and FX).
     *
     * @param rc the class
     * @param bucket the label
     * @return the number
     */
    public static int bucketNumber(RiskClass rc, String bucket) {
        if (rc == RiskClass.GIRR || rc == RiskClass.FX) {
            return 0;
        }
        int max = rc == RiskClass.CSR_NONSEC ? 18 : rc == RiskClass.EQUITY ? 13 : 11;
        int b;
        try {
            b = Integer.parseInt(bucket);
        } catch (NumberFormatException e) {
            b = -1;
        }
        if (b < 1 || b > max) {
            throw new QfError("E_INPUT", "unknown bucket " + bucket, "bucket");
        }
        return b;
    }

    private static double gamma(RiskClass rc, String b, String c) {
        return switch (rc) {
            case GIRR -> 0.5;
            case FX -> 0.6;
            case CSR_NONSEC -> FrtbSbm.csrGamma(Integer.parseInt(b), Integer.parseInt(c));
            case EQUITY -> FrtbSbm.eqGamma(Integer.parseInt(b), Integer.parseInt(c));
            case COMMODITY -> b.equals("11") || c.equals("11") ? 0.0 : 0.20;
        };
    }

    private static double nameRho(RiskClass rc, String b, String n1, String n2) {
        if (n1.equals(n2)) {
            return 1.0;
        }
        return switch (rc) {
            case CSR_NONSEC -> b.equals("17") || b.equals("18") ? 0.80 : 0.35;
            case EQUITY -> FrtbSbm.EQ_RHO[Integer.parseInt(b)];
            case COMMODITY -> FrtbSbm.CM_RHO[Integer.parseInt(b)];
            default -> 1.0;
        };
    }

    private static double matRho(double t1, double t2) {
        return Math.exp(-0.01 * Math.abs(t1 - t2) / Math.min(t1, t2));
    }

    private static boolean other(RiskClass rc, String b) {
        return rc == RiskClass.EQUITY && b.equals("11") || rc == RiskClass.CSR_NONSEC && b.equals("16");
    }

    /** Buckets in the order (length, text): numeric order for numbers, then text. */
    private static <T> TreeMap<String, List<T>> group(List<T> in, java.util.function.Function<T, String> key) {
        TreeMap<String, List<T>> m = new TreeMap<>((x, y) -> x.length() != y.length()
                ? Integer.compare(x.length(), y.length()) : x.compareTo(y));
        for (T t : in) {
            m.computeIfAbsent(key.apply(t), k -> new ArrayList<>()).add(t);
        }
        return m;
    }

    private static double vegaRw(RiskClass rc, String b) {
        if (rc != RiskClass.EQUITY) {
            return 1.0;
        }
        int n = Integer.parseInt(b);
        return n <= 8 || n == 12 || n == 13 ? 0.7778 : 1.0;
    }

    /**
     * Vega capital (MAR21.92 to 21.95 with MAR21.4 and 21.6).
     *
     * @param rc the class
     * @param in the sensitivities
     * @return the result, as delta's with vega in place of delta
     */
    public static FrtbGirr.Result vega(RiskClass rc, List<Vega> in) {
        if (in.isEmpty()) {
            throw new QfError("E_INPUT", "no sensitivities", "sensitivities");
        }
        TreeMap<String, List<Vega>> bk = group(in, Vega::bucket);
        List<String> ids = new ArrayList<>(bk.keySet());
        int nb = ids.size();
        List<FrtbGirr.Scenario> out = new ArrayList<>();
        double capital = Double.NEGATIVE_INFINITY;
        String binding = null;
        for (String sc : ORDER) {
            double[] k = new double[nb];
            double[] s = new double[nb];
            for (int bi = 0; bi < nb; bi++) {
                String b = ids.get(bi);
                List<Vega> vs = bk.get(b);
                double rw = vegaRw(rc, b);
                double[] ws = new double[vs.size()];
                double sb = 0.0;
                for (int i = 0; i < ws.length; i++) {
                    ws[i] = rw * vs.get(i).vega();
                    sb += ws[i];
                }
                s[bi] = sb;
                if (other(rc, b)) {
                    Map<List<Object>, Double> net = new LinkedHashMap<>();
                    for (int i = 0; i < ws.length; i++) {
                        Vega v = vs.get(i);
                        net.merge(List.of(v.name(), v.optionMaturity(), v.underlyingMaturity()), ws[i], Double::sum);
                    }
                    double sum = 0.0;
                    for (double v : net.values()) {
                        sum += Math.abs(v);
                    }
                    k[bi] = sum;
                    continue;
                }
                double q = 0.0;
                for (int i = 0; i < ws.length; i++) {
                    for (int j = 0; j < ws.length; j++) {
                        double r = 1.0;
                        if (i != j) {
                            Vega a = vs.get(i);
                            Vega c = vs.get(j);
                            r = matRho(a.optionMaturity(), c.optionMaturity());
                            r *= rc == RiskClass.GIRR ? matRho(a.underlyingMaturity(), c.underlyingMaturity())
                                    : nameRho(rc, b, a.name(), c.name());
                            r = scale(sc, Math.min(r, 1.0));
                        }
                        q += ws[i] * ws[j] * r;
                    }
                }
                k[bi] = Math.sqrt(Math.max(q, 0.0));
            }
            double[] used = s.clone();
            double total = total(rc, ids, k, used, sc);
            boolean alt = false;
            if (total < 0.0) {
                alt = true;
                for (int b = 0; b < nb; b++) {
                    used[b] = Math.max(Math.min(s[b], k[b]), -k[b]);
                }
                total = total(rc, ids, k, used, sc);
            }
            double d = Math.sqrt(Math.max(total, 0.0));
            List<FrtbGirr.Bucket> bl = new ArrayList<>();
            for (int b = 0; b < nb; b++) {
                bl.add(new FrtbGirr.Bucket(ids.get(b), k[b], s[b], used[b]));
            }
            out.add(new FrtbGirr.Scenario(sc, bl, d, alt));
            if (d > capital) {
                capital = d;
                binding = sc;
            }
        }
        return new FrtbGirr.Result(out, capital, binding);
    }

    private static double total(RiskClass rc, List<String> ids, double[] k, double[] s, String sc) {
        double t = 0.0;
        for (double x : k) {
            t += x * x;
        }
        for (int b = 0; b < k.length; b++) {
            for (int c = 0; c < k.length; c++) {
                if (b != c) {
                    t += scale(sc, gamma(rc, ids.get(b), ids.get(c))) * s[b] * s[c];
                }
            }
        }
        return t;
    }

    private static double psi(double a, double b) {
        return a < 0.0 && b < 0.0 ? 0.0 : 1.0;
    }

    private static double kSide(RiskClass rc, String b, List<Cvr> fs, boolean up, String sc) {
        double q = 0.0;
        for (Cvr f : fs) {
            double x = Math.max(up ? f.up() : f.down(), 0.0);
            q += x * x;
        }
        for (int i = 0; i < fs.size(); i++) {
            for (int j = 0; j < fs.size(); j++) {
                if (i != j) {
                    double a = up ? fs.get(i).up() : fs.get(i).down();
                    double c = up ? fs.get(j).up() : fs.get(j).down();
                    double r = nameRho(rc, b, fs.get(i).name(), fs.get(j).name());
                    q += scale(sc, r * r) * a * c * psi(a, c);
                }
            }
        }
        return Math.sqrt(Math.max(q, 0.0));
    }

    /**
     * Curvature capital (MAR21.5, 21.98 to 21.101).
     *
     * @param rc the class
     * @param in the CVR factors
     * @param fxScalar divide every CVR by 1.5 (FX only)
     * @return the result
     */
    public static CurvResult curvature(RiskClass rc, List<Cvr> in, boolean fxScalar) {
        if (in.isEmpty()) {
            throw new QfError("E_INPUT", "no factors", "factors");
        }
        if (fxScalar && rc != RiskClass.FX) {
            throw new QfError("E_INPUT", "fx_scalar applies to FX only", "fx_scalar");
        }
        Set<List<String>> seen = new HashSet<>();
        List<Cvr> scaled = new ArrayList<>();
        for (Cvr c : in) {
            if (!seen.add(List.of(c.bucket(), c.name()))) {
                throw new QfError("E_INPUT", "same factor twice", "factors");
            }
            scaled.add(fxScalar ? new Cvr(c.bucket(), c.name(), c.up() / 1.5, c.down() / 1.5) : c);
        }
        TreeMap<String, List<Cvr>> bk = group(scaled, Cvr::bucket);
        List<String> ids = new ArrayList<>(bk.keySet());
        List<CurvScenario> out = new ArrayList<>();
        double capital = Double.NEGATIVE_INFINITY;
        String binding = null;
        for (String sc : ORDER) {
            List<CurvBucket> rows = new ArrayList<>();
            for (String b : ids) {
                List<Cvr> fs = bk.get(b);
                double up = 0.0;
                double dn = 0.0;
                for (Cvr f : fs) {
                    up += f.up();
                    dn += f.down();
                }
                double kp;
                double km;
                if (other(rc, b)) {
                    kp = 0.0;
                    km = 0.0;
                    for (Cvr f : fs) {
                        kp += Math.max(f.up(), 0.0);
                        km += Math.max(f.down(), 0.0);
                    }
                } else {
                    kp = kSide(rc, b, fs, true, sc);
                    km = kSide(rc, b, fs, false, sc);
                }
                boolean selUp = kp > km || (kp == km && up > dn);
                rows.add(new CurvBucket(b, Math.max(kp, km), selUp ? up : dn, selUp));
            }
            double t = 0.0;
            for (CurvBucket r : rows) {
                t += r.k() * r.k();
            }
            for (int i = 0; i < rows.size(); i++) {
                for (int j = 0; j < rows.size(); j++) {
                    if (i != j) {
                        double g = gamma(rc, rows.get(i).bucket(), rows.get(j).bucket());
                        double si = rows.get(i).s();
                        double sj = rows.get(j).s();
                        t += scale(sc, g * g) * si * sj * psi(si, sj);
                    }
                }
            }
            double cv = Math.sqrt(Math.max(t, 0.0));
            out.add(new CurvScenario(sc, rows, cv));
            if (cv > capital) {
                capital = cv;
                binding = sc;
            }
        }
        return new CurvResult(out, capital, binding);
    }
}
