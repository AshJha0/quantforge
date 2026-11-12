package org.quantforge.cli;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.risk.FrtbGirr;
import org.quantforge.risk.FrtbSbm;
import org.quantforge.risk.FrtbVegaCurvature;
import org.quantforge.risk.PortfolioRiskTools;

/** Stage F carry-over wave 2b: FRTB FX, equity, CSR and commodity delta; F3 sensitivities; F4 tools. */
final class OpsFrtbSensitivities {
    private OpsFrtbSensitivities() {}

    private static final int MAX = 100_000;

    private static QfError domain(String key) {
        return new QfError("E_DOMAIN", key + " is out of range", key);
    }

    private static QfError input(String key) {
        return new QfError("E_INPUT", key + " is not valid", key);
    }

    private static Out frtbOut(FrtbGirr.Result r) {
        return frtbOut(r, "delta");
    }

    private static Out frtbOut(FrtbGirr.Result r, String key) {
        Map<String, Object> sc = new LinkedHashMap<>();
        for (FrtbGirr.Scenario s : r.scenarios()) {
            List<Map<String, Object>> bl = new ArrayList<>();
            for (FrtbGirr.Bucket b : s.buckets()) {
                bl.add(Operations.out("bucket", b.currency(), "k", b.k(), "s", b.s(), "s_used", b.sUsed()).outputs());
            }
            sc.put(s.name(), Operations.out("buckets", bl, key, s.delta(), "alternative_used",
                    s.alternativeUsed()).outputs());
        }
        return Operations.out("scenarios", sc, "capital", r.capital(), "binding_scenario", r.binding());
    }

    /** The common reader of an FRTB sensitivity list: string fields, an optional bucket and the value. */
    private record Rows(List<List<String>> text, long[] bucket, double[] s) {}

    private static Rows rows(In in, boolean bucketed, String... keys) {
        List<In> list = in.objects("sensitivities");
        in.limit(list.size() > MAX, "sensitivities");
        List<List<String>> text = new ArrayList<>();
        long[] bucket = new long[list.size()];
        double[] s = new double[list.size()];
        for (int i = 0; i < list.size(); i++) {
            In x = list.get(i);
            List<String> t = new ArrayList<>();
            for (String k : keys) {
                t.add(x.string(k));
            }
            text.add(t);
            if (bucketed) {
                bucket[i] = x.integer("bucket");
            }
            s[i] = x.real("sensitivity");
        }
        return new Rows(text, bucket, s);
    }

    private static List<String> col(Rows r, int j) {
        List<String> out = new ArrayList<>();
        for (List<String> t : r.text()) {
            out.add(t.get(j));
        }
        return out;
    }

    private enum RiskClass { GIRR, CSR_NONSEC, EQ, COMM, FX }

    private enum Measure { DELTA, VEGA, CURVATURE }

    private static final String[] SCENARIOS = {"high", "medium", "low"};

    /** MAR21.7 total over risk classes and measures within each scenario, then the worst scenario (R6-4.1). */
    private static Out sbmTotal(In in) {
        List<In> list = in.objects("components");
        in.limit(list.size() > MAX, "components");
        List<String> ids = new ArrayList<>();
        double[][] charge = new double[list.size()][3];
        for (int i = 0; i < list.size(); i++) {
            In x = list.get(i);
            RiskClass rc = x.choice("risk_class", RiskClass.class);
            Measure m = x.choice("measure", Measure.class);
            In sc = x.object("scenarios");
            for (int k = 0; k < 3; k++) {
                charge[i][k] = sc.real(SCENARIOS[k]);
            }
            ids.add(rc + "/" + m);
        }
        in.gate();
        if (list.isEmpty()) {
            throw new org.quantforge.core.QfError("E_INPUT", "at least one component is needed", "components");
        }
        for (double[] c : charge) {
            for (double v : c) {
                if (v < 0.0) {
                    throw new org.quantforge.core.QfError("E_DOMAIN", "a charge is negative", "components");
                }
            }
        }
        if (new HashSet<>(ids).size() != ids.size()) {
            throw new org.quantforge.core.QfError("E_INPUT", "a risk class and measure appear twice", "components");
        }
        double[] total = new double[3];
        double sumOwn = 0.0;
        for (double[] c : charge) {
            for (int k = 0; k < 3; k++) {
                total[k] += c[k];
            }
            sumOwn += Math.max(c[0], Math.max(c[1], c[2]));
        }
        int bind = 0;
        for (int k = 1; k < 3; k++) {
            if (total[k] > total[bind]) {
                bind = k;
            }
        }
        Map<String, Object> totals = new java.util.LinkedHashMap<>();
        for (int k = 0; k < 3; k++) {
            totals.put(SCENARIOS[k], total[k]);
        }
        return Operations.out("scenario_totals", totals, "capital", total[bind], "binding_scenario", SCENARIOS[bind],
                "sum_of_component_capitals", sumOwn);
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("risk.frtb.sbm_total", OpsFrtbSensitivities::sbmTotal);
        table.put("risk.frtb.fx_delta", in -> {
            Rows r = rows(in, false, "pair");
            Set<String> spec = in.has("specified_pairs") ? new HashSet<>(in.strings("specified_pairs")) : Set.of();
            in.gate();
            return frtbOut(FrtbSbm.fx(col(r, 0), r.s(), spec));
        });
        table.put("risk.frtb.equity_delta", in -> {
            Rows r = rows(in, true, "issuer", "kind");
            in.gate();
            return frtbOut(FrtbSbm.equity(col(r, 0), r.bucket(), col(r, 1), r.s()));
        });
        table.put("risk.frtb.csr_delta", in -> {
            Rows r = rows(in, true, "issuer", "tenor", "curve");
            in.gate();
            return frtbOut(FrtbSbm.csr(col(r, 0), r.bucket(), col(r, 1), col(r, 2), r.s()));
        });
        table.put("risk.frtb.commodity_delta", in -> {
            Rows r = rows(in, true, "commodity", "tenor", "location");
            in.gate();
            return frtbOut(FrtbSbm.commodity(col(r, 0), r.bucket(), col(r, 1), col(r, 2), r.s()));
        });

        table.put("risk.frtb.vega", OpsFrtbSensitivities::vega);
        table.put("risk.frtb.curvature", OpsFrtbSensitivities::curvature);

        table.put("risk.sens.inflation01", in -> {
            double n = in.real("notional");
            long years = in.integer("years");
            double k = in.real("fixed_rate");
            double z = in.real("market_rate");
            double p = in.real("discount_factor");
            in.gate();
            if (years < 1) {
                throw input("years");
            }
            if (!(1.0 + z > 0.0)) {
                throw domain("market_rate");
            }
            if (!(p > 0.0)) {
                throw domain("discount_factor");
            }
            double pv = PortfolioRiskTools.zcisPv(n, years, k, z, p);
            return Operations.out("pv", pv, "inflation01", PortfolioRiskTools.inflation01(n, years, z, p),
                    "inflation01_bump", PortfolioRiskTools.zcisPv(n, years, k, z + 1e-4, p) - pv);
        });
        table.put("risk.sens.dividend_borrow", in -> {
            double s = in.real("spot");
            double k = in.real("strike");
            double t = in.real("expiry_years");
            double r = in.real("rate");
            double q = in.real("dividend_yield");
            double b = in.real("borrow_rate");
            double v = in.real("vol");
            String type = in.string("option_type");
            in.gate();
            if (!(s > 0.0)) {
                throw domain("spot");
            }
            if (!(k > 0.0)) {
                throw domain("strike");
            }
            if (!(t > 0.0)) {
                throw domain("expiry_years");
            }
            if (!(v > 0.0)) {
                throw domain("vol");
            }
            if (!type.equals("CALL") && !type.equals("PUT")) {
                throw input("option_type");
            }
            double[] pv = PortfolioRiskTools.bsmYield(type.equals("CALL"), s, k, t, r, q + b, v);
            return Operations.out("price", pv[0], "dividend01", pv[1] * 1e-4, "borrow01", pv[1] * 1e-4);
        });
        table.put("risk.sens.correlation", in -> {
            double s1 = in.real("spot1");
            double s2 = in.real("spot2");
            double q1 = in.real("quantity1");
            double q2 = in.real("quantity2");
            double y1 = in.real("yield1");
            double y2 = in.real("yield2");
            double v1 = in.real("vol1");
            double v2 = in.real("vol2");
            double rho = in.real("correlation");
            double t = in.real("expiry_years");
            in.gate();
            if (!(s1 > 0.0) || !(s2 > 0.0)) {
                throw domain(s1 > 0.0 ? "spot2" : "spot1");
            }
            if (!(q1 > 0.0) || !(q2 > 0.0)) {
                throw domain(q1 > 0.0 ? "quantity2" : "quantity1");
            }
            if (!(v1 >= 0.0) || !(v2 >= 0.0)) {
                throw domain(v1 >= 0.0 ? "vol2" : "vol1");
            }
            if (!(rho >= -1.0 && rho <= 1.0)) {
                throw domain("correlation");
            }
            if (!(t > 0.0)) {
                throw domain("expiry_years");
            }
            double[] m = PortfolioRiskTools.margrabe(q1 * s1 * Math.exp(-y1 * t), q2 * s2 * Math.exp(-y2 * t), v1, v2, rho, t);
            return Operations.out("price", m[0], "correlation01", m[1], "spread_vol", m[2]);
        });

        table.put("risk.stress.reverse", in -> {
            double[] d = in.reals("direction");
            double[] delta = in.reals("delta");
            double[][] gamma = in.anyMatrix("gamma");
            double loss = in.real("target_loss");
            in.limit(d.length > MAX, "direction");
            in.gate();
            boolean ok = delta.length == d.length && gamma.length == d.length && d.length > 0;
            for (double[] row : gamma) {
                ok &= row.length == d.length;
            }
            if (!ok) {
                throw input("gamma");
            }
            if (!(loss > 0.0)) {
                throw domain("target_loss");
            }
            double k = PortfolioRiskTools.reverseScale(d, delta, gamma, loss);
            double[] shocks = new double[d.length];
            double pnl = 0.0;
            for (int i = 0; i < d.length; i++) {
                shocks[i] = k * d[i];
                pnl += delta[i] * shocks[i];
            }
            for (int i = 0; i < d.length; i++) {
                for (int j = 0; j < d.length; j++) {
                    pnl += 0.5 * shocks[i] * gamma[i][j] * shocks[j];
                }
            }
            return Operations.out("scale", k, "shocks", shocks, "pnl", pnl);
        });
        table.put("risk.limits.check", in -> {
            In m = in.object("measures");
            In l = in.object("limits");
            TreeMap<String, Double> vals = new TreeMap<>();
            for (String k : m.keys()) {
                vals.put(k, m.real(k));
            }
            TreeMap<String, double[]> lim = new TreeMap<>();
            for (String k : l.keys()) {
                In x = l.object(k);
                lim.put(k, new double[] {x.real("soft"), x.real("hard")});
            }
            in.gate();
            for (double[] x : lim.values()) {
                if (!(x[0] >= 0.0 && x[0] <= x[1])) {
                    throw domain("limits");
                }
            }
            Map<String, Object> out = new LinkedHashMap<>();
            int worst = 0;
            String[] names = {"OK", "WARN", "BREACH"};
            for (Map.Entry<String, Double> e : vals.entrySet()) {
                double[] x = lim.get(e.getKey());
                if (x == null) {
                    throw input("limits");
                }
                double a = Math.abs(e.getValue());
                int st = a > x[1] ? 2 : a >= x[0] ? 1 : 0;
                worst = Math.max(worst, st);
                out.put(e.getKey(), Operations.out("utilisation", a / x[1], "status", names[st]).outputs());
            }
            return Operations.out("measures", out, "overall", names[worst]);
        });
        table.put("risk.concentration.measures", in -> {
            double[] x = in.reals("exposures");
            long n = in.integer("top_n");
            in.limit(x.length > MAX, "exposures");
            in.gate();
            if (x.length == 0) {
                throw domain("exposures");
            }
            double[] w = PortfolioRiskTools.weights(x);
            if (n < 1 || n > x.length) {
                throw input("top_n");
            }
            double hhi = 0.0;
            for (double v : w) {
                hhi += v * v;
            }
            return Operations.out("hhi", hhi, "effective_number", 1.0 / hhi, "top_n_share",
                    PortfolioRiskTools.topShare(w, (int) n), "weights", w);
        });
        table.put("risk.var.liquidity_adjusted", in -> {
            double var = in.real("var");
            double z = in.real("z");
            double[] p = in.reals("position_values");
            double[] mu = in.reals("spread_mean");
            double[] sd = in.reals("spread_vol");
            in.limit(p.length > MAX, "position_values");
            in.gate();
            if (mu.length != p.length || sd.length != p.length) {
                throw input("spread_mean");
            }
            if (!(var >= 0.0)) {
                throw domain("var");
            }
            double cost = 0.0;
            for (int i = 0; i < p.length; i++) {
                if (!(mu[i] >= 0.0) || !(sd[i] >= 0.0)) {
                    throw domain(mu[i] >= 0.0 ? "spread_vol" : "spread_mean");
                }
                cost += Math.abs(p[i]) * (mu[i] + z * sd[i]);
            }
            cost *= 0.5;
            return Operations.out("liquidity_cost", cost, "lvar", var + cost);
        });
        table.put("risk.vol.horizon", in -> {
            double sigma = in.real("daily_vol");
            double rho = in.real("ar1");
            long h = in.integer("horizon_days");
            in.limit(h > 100_000, "horizon_days");
            in.gate();
            if (!(sigma > 0.0)) {
                throw domain("daily_vol");
            }
            if (!(Math.abs(rho) < 1.0)) {
                throw domain("ar1");
            }
            if (h < 1) {
                throw domain("horizon_days");
            }
            double ratio = PortfolioRiskTools.varianceRatio(rho, h);
            double sq = sigma * Math.sqrt((double) h);
            return Operations.out("vol", sigma * Math.sqrt(h * ratio), "sqrt_rule_vol", sq, "variance_ratio", ratio);
        });
    }

    private static FrtbVegaCurvature.RiskClass riskClass(In in) {
        String s = in.string("risk_class");
        for (FrtbVegaCurvature.RiskClass c : FrtbVegaCurvature.RiskClass.values()) {
            if (c.name().equals(s)) {
                return c;
            }
        }
        throw input("risk_class");
    }

    /** A bucket label: a string for GIRR and FX, an integer otherwise. */
    private static String bucket(In x, FrtbVegaCurvature.RiskClass rc) {
        return named(rc) ? Long.toString(x.integer("bucket")) : x.string("bucket");
    }

    private static boolean named(FrtbVegaCurvature.RiskClass rc) {
        return rc != FrtbVegaCurvature.RiskClass.GIRR && rc != FrtbVegaCurvature.RiskClass.FX;
    }

    private static Out vega(In in) {
        FrtbVegaCurvature.RiskClass rc = riskClass(in);
        List<In> list = in.objects("sensitivities");
        in.limit(list.size() > MAX, "sensitivities");
        List<FrtbVegaCurvature.Vega> vs = new ArrayList<>();
        boolean missingU = false;
        for (In x : list) {
            String b = bucket(x, rc);
            String name = named(rc) ? x.string("name") : "";
            double t = x.real("option_maturity");
            boolean hasU = x.has("underlying_maturity");
            double u = hasU ? x.real("underlying_maturity") : Double.NaN;
            missingU |= rc == FrtbVegaCurvature.RiskClass.GIRR && !hasU;
            vs.add(new FrtbVegaCurvature.Vega(b, name, t, u, x.real("vega")));
        }
        in.gate();
        if (missingU) {
            throw input("underlying_maturity");
        }
        for (FrtbVegaCurvature.Vega v : vs) {
            FrtbVegaCurvature.bucketNumber(rc, v.bucket());
            if (!(v.optionMaturity() > 0.0)) {
                throw domain("option_maturity");
            }
            if (rc == FrtbVegaCurvature.RiskClass.GIRR && !(v.underlyingMaturity() > 0.0)) {
                throw domain("underlying_maturity");
            }
        }
        return frtbOut(FrtbVegaCurvature.vega(rc, vs), "vega");
    }

    private static Out curvature(In in) {
        FrtbVegaCurvature.RiskClass rc = riskClass(in);
        List<In> list = in.objects("factors");
        in.limit(list.size() > MAX, "factors");
        boolean scalar = in.bool("fx_scalar", false);
        List<FrtbVegaCurvature.Cvr> fs = new ArrayList<>();
        for (In x : list) {
            String b = bucket(x, rc);
            String name = named(rc) ? x.string("name") : "";
            fs.add(new FrtbVegaCurvature.Cvr(b, name, x.real("cvr_up"), x.real("cvr_down")));
        }
        in.gate();
        for (FrtbVegaCurvature.Cvr f : fs) {
            FrtbVegaCurvature.bucketNumber(rc, f.bucket());
        }
        FrtbVegaCurvature.CurvResult r = FrtbVegaCurvature.curvature(rc, fs, scalar);
        Map<String, Object> sc = new LinkedHashMap<>();
        for (FrtbVegaCurvature.CurvScenario s : r.scenarios()) {
            List<Map<String, Object>> bl = new ArrayList<>();
            for (FrtbVegaCurvature.CurvBucket b : s.buckets()) {
                bl.add(Operations.out("bucket", b.bucket(), "k", b.k(), "s", b.s(), "selected", b.up() ? "UP" : "DOWN")
                        .outputs());
            }
            sc.put(s.name(), Operations.out("buckets", bl, "curvature", s.curvature()).outputs());
        }
        return Operations.out("scenarios", sc, "capital", r.capital(), "binding_scenario", r.binding());
    }
}
