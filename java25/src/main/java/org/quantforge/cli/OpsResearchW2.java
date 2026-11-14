package org.quantforge.cli;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.research.Allocation;

/** Stage J wave 2 (rulings J-W2-1 to J-W2-15): optimisation, estimation, ES backtest, Baum-Welch. */
final class OpsResearchW2 {
    private static final int ASSETS = 500;
    private static final int ROWS = 1_000_000;
    private static final long CELLS = 10_000_000L;

    private OpsResearchW2() {}

    private static QfError input(String why) {
        return new QfError("E_INPUT", why);
    }

    private static List<Object> rows(double[][] m) {
        List<Object> out = new ArrayList<>();
        for (double[] r : m) {
            out.add(OpsSmile.list(r));
        }
        return out;
    }

    private static List<Object> longs(long[] x) {
        List<Object> out = new ArrayList<>();
        for (long v : x) {
            out.add(v);
        }
        return out;
    }

    /** E_LIMIT for an asset or view matrix: more than 500 rows or any row wider than 500. */
    private static void assetLimit(In in, double[][] m, String key) {
        boolean over = m.length > ASSETS;
        for (double[] r : m) {
            over |= r.length > ASSETS;
        }
        in.limit(over, key);
    }

    private static void needSquare(double[][] m, int n, String what) {
        if (!Allocation.square(m, n)) {
            throw input(what + " must be " + n + " x " + n);
        }
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("research.portfolio.mean_variance", OpsResearchW2::meanVariance);
        table.put("research.portfolio.risk_parity", OpsResearchW2::riskParity);
        table.put("risk.contrib.euler", OpsResearchW2::euler);
        table.put("research.estimate.ledoit_wolf", OpsResearchW2::ledoitWolf);
        table.put("research.estimate.black_litterman", OpsResearchW2::blackLitterman);
        table.put("risk.backtest.es_z2", OpsResearchW2::esZ2);
        table.put("research.regime.baum_welch", OpsResearchW2::baumWelch);
    }

    private static Out meanVariance(In in) {
        double[] mu = in.reals("expected_returns");
        double[][] cov = in.anyMatrix("covariance");
        double gamma = in.real("risk_aversion");
        double[] lo = in.has("lower") ? in.reals("lower") : null;
        double[] hi = in.has("upper") ? in.reals("upper") : null;
        in.limit(mu.length > ASSETS, "expected_returns");
        assetLimit(in, cov, "covariance");
        in.limit(lo != null && lo.length > ASSETS, "lower");
        in.limit(hi != null && hi.length > ASSETS, "upper");
        in.gate();
        int n = mu.length;
        if (n < 1) {
            throw input("at least one asset required");
        }
        needSquare(cov, n, "covariance");
        if (lo == null) {
            lo = new double[n];
        }
        if (hi == null) {
            hi = new double[n];
            Arrays.fill(hi, 1.0);
        }
        if (lo.length != n || hi.length != n) {
            throw input("lower and upper must have N entries");
        }
        Allocation.MeanVariance r = Allocation.meanVariance(mu, cov, gamma, lo, hi);
        return Operations.out("weights", OpsSmile.list(r.weights()), "expected_return", r.expectedReturn(),
                "volatility", r.volatility(), "objective", r.objective(), "at_bound", longs(r.atBound()));
    }

    private static Out riskParity(In in) {
        double[][] cov = in.anyMatrix("covariance");
        double[] b = in.has("budgets") ? in.reals("budgets") : null;
        assetLimit(in, cov, "covariance");
        in.limit(b != null && b.length > ASSETS, "budgets");
        in.gate();
        int n = cov.length;
        if (n < 1) {
            throw input("at least one asset required");
        }
        needSquare(cov, n, "covariance");
        if (b != null && b.length != n) {
            throw input("budgets must have N entries");
        }
        Allocation.RiskParity r = Allocation.riskParity(cov, b);
        return Operations.out("weights", OpsSmile.list(r.weights()), "volatility", r.volatility(), "contributions",
                OpsSmile.list(r.contributions()));
    }

    private static Out euler(In in) {
        double[] w = in.reals("weights");
        double[][] cov = in.anyMatrix("covariance");
        in.limit(w.length > ASSETS, "weights");
        assetLimit(in, cov, "covariance");
        in.gate();
        int n = w.length;
        if (n < 1) {
            throw input("at least one asset required");
        }
        needSquare(cov, n, "covariance");
        Allocation.Euler r = Allocation.euler(w, cov);
        return Operations.out("volatility", r.volatility(), "marginal", OpsSmile.list(r.marginal()),
                "contributions", OpsSmile.list(r.contributions()), "shares", OpsSmile.list(r.shares()));
    }

    private static Out ledoitWolf(In in) {
        double[][] r = in.anyMatrix("returns");
        long cells = 0;
        boolean wide = false;
        for (double[] row : r) {
            cells += row.length;
            wide |= row.length > ASSETS;
        }
        in.limit(r.length > ROWS || cells > CELLS || wide, "returns");
        in.gate();
        Allocation.LedoitWolf lw = Allocation.ledoitWolf(r);
        return Operations.out("covariance", rows(lw.covariance()), "shrinkage", lw.shrinkage(), "mu", lw.mu());
    }

    private static Out blackLitterman(In in) {
        double[][] cov = in.anyMatrix("covariance");
        double[] pi = in.reals("prior_returns");
        double[][] p = in.anyMatrix("pick");
        double[] q = in.reals("views");
        double[][] om = in.anyMatrix("view_covariance");
        double tau = in.real("tau");
        assetLimit(in, cov, "covariance");
        in.limit(pi.length > ASSETS, "prior_returns");
        assetLimit(in, p, "pick");
        in.limit(q.length > ASSETS, "views");
        assetLimit(in, om, "view_covariance");
        in.gate();
        int n = pi.length;
        int k = q.length;
        if (n < 1 || k < 1) {
            throw input("at least one asset and one view required");
        }
        needSquare(cov, n, "covariance");
        needSquare(om, k, "view_covariance");
        if (p.length != k) {
            throw input("pick must be K x N");
        }
        for (double[] row : p) {
            if (row.length != n) {
                throw input("pick must be K x N");
            }
        }
        Allocation.BlackLitterman r = Allocation.blackLitterman(cov, pi, p, q, om, tau);
        return Operations.out("posterior_returns", OpsSmile.list(r.posteriorReturns()), "posterior_covariance",
                rows(r.posteriorCovariance()), "predictive_covariance", rows(r.predictiveCovariance()));
    }

    private static Out esZ2(In in) {
        double[] l = in.reals("losses");
        double[] v = in.reals("var");
        double[] e = in.reals("es");
        double alpha = in.real("alpha");
        in.limit(l.length > ROWS || v.length > ROWS || e.length > ROWS, "losses");
        in.gate();
        Allocation.Z2 r = Allocation.esZ2(l, v, e, alpha);
        return Operations.out("z2", r.z2(), "exceptions", r.exceptions(), "expected_exceptions",
                r.expectedExceptions());
    }

    private static Out baumWelch(In in) {
        double[] y = in.reals("observations");
        double[] pi = in.reals("initial");
        double[][] a = in.anyMatrix("transition");
        double[] mu = in.reals("means");
        double[] sd = in.reals("sds");
        double tol = in.real("tolerance", 1e-10);
        long maxIter = in.integer("max_iterations", 1000);
        int k = pi.length;
        in.limit(k > 16 || a.length > 16 || mu.length > 16 || sd.length > 16, "initial");
        in.limit(maxIter > 10_000, "max_iterations");
        in.limit(y.length > ROWS, "observations");
        in.limit(In.productOver(y.length, k, CELLS), "observations");
        in.gate();
        if (y.length < 2 || k < 1 || maxIter < 1 || !Allocation.square(a, k) || mu.length != k || sd.length != k) {
            throw input("observations (T >= 2), K x K transition, K means and sds, max_iterations >= 1 required");
        }
        Allocation.BaumWelch r = Allocation.baumWelch(y, pi, a, mu, sd, tol, (int) maxIter);
        return Operations.out("initial", OpsSmile.list(r.initial()), "transition", rows(r.transition()), "means",
                OpsSmile.list(r.means()), "sds", OpsSmile.list(r.sds()), "log_likelihood", r.logLikelihood(),
                "iterations", r.iterations(), "converged", r.converged());
    }
}
