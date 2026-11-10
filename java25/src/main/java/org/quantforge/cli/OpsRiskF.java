package org.quantforge.cli;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.Conventions;
import org.quantforge.curves.Curve;
import org.quantforge.curves.Ois;
import org.quantforge.risk.BookRisk;
import org.quantforge.risk.FrtbGirr;
import org.quantforge.risk.PortfolioRisk;

/** Stage F slices F3 and F4: book sensitivities, curve risk, VaR/ES, backtests, FRTB. Inputs read before the gate. */
final class OpsRiskF {
    private OpsRiskF() {}

    private enum SwapSide { PAY, RECEIVE }

    private static Map<String, Object> varEs(PortfolioRisk.VarEs r) {
        return Operations.out("var", r.var(), "es", r.es(), "tail_count", r.tailCount()).outputs();
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("risk.var.historical", in -> {
            double[] pnl = in.reals("pnl");
            double c = in.gate(in.real("confidence"));
            return new Out(varEs(PortfolioRisk.historical(pnl, c)), Map.of());
        });
        table.put("risk.var.filtered_historical", in -> {
            double[] r = in.reals("returns");
            double p = in.real("position_value");
            double lambda = in.real("lambda");
            double c = in.gate(in.real("confidence"));
            PortfolioRisk.VarEs v = PortfolioRisk.filtered(r, p, lambda, c);
            return Operations.out("var", v.var(), "es", v.es(), "tail_count", v.tailCount(),
                    "sigma_next", v.sigmaNext());
        });
        table.put("risk.var.parametric", in -> {
            double mu = in.real("mean");
            double s = in.real("std");
            double c = in.gate(in.real("confidence"));
            PortfolioRisk.VarEs v = PortfolioRisk.parametric(mu, s, c);
            return Operations.out("var", v.var(), "es", v.es());
        });
        table.put("risk.var.monte_carlo", in -> {
            double[] mean = in.reals("mean");
            double[][] cov = in.anyMatrix("covariance");
            double[] w = in.reals("weights");
            long paths = in.integer("paths");
            in.limit(paths > 10_000_000, "paths");
            long seed = in.u64("seed");
            double c = in.gate(in.real("confidence"));
            return new Out(varEs(PortfolioRisk.monteCarlo(mean, cov, w, paths, seed, c)), Map.of());
        });
        table.put("risk.frtb.girr_delta", in -> {
            List<In> list = in.objects("sensitivities");
            in.limit(list.size() > 100_000, "sensitivities");
            List<FrtbGirr.Sensitivity> ss = new java.util.ArrayList<>();
            for (In x : list) {
                String rf = x.string("risk_factor");
                FrtbGirr.factor(rf);
                ss.add(new FrtbGirr.Sensitivity(x.string("currency"), x.string("curve"), rf, x.real("sensitivity")));
            }
            boolean red = in.bool("specified_currency_reduction", false);
            String rep = in.has("reporting_currency") ? in.string("reporting_currency") : null;
            in.gate();
            FrtbGirr.Result r = FrtbGirr.delta(ss, red, rep);
            Map<String, Object> sc = new java.util.LinkedHashMap<>();
            for (FrtbGirr.Scenario s : r.scenarios()) {
                List<Map<String, Object>> bl = new java.util.ArrayList<>();
                for (FrtbGirr.Bucket b : s.buckets()) {
                    bl.add(Operations.out("currency", b.currency(), "k", b.k(), "s", b.s(), "s_used", b.sUsed())
                            .outputs());
                }
                sc.put(s.name(), Operations.out("buckets", bl, "delta", s.delta(),
                        "alternative_used", s.alternativeUsed()).outputs());
            }
            return Operations.out("scenarios", sc, "capital", r.capital(), "binding_scenario", r.binding());
        });
        table.put("risk.book.ois_sensitivity", in -> {
            LocalDate asOf = in.date("as_of");
            Conventions.RateIndex c = Conventions.overnight(in.string("convention"));
            List<Ois.Quote> quotes = OpsLinear.quotes(in);
            Curve.Interpolation interp = in.choice("interpolation", Curve.Interpolation.class);
            List<In> list = in.objects("swaps");
            in.limit(list.size() > 100_000, "swaps");
            List<BookRisk.Swap> swaps = new ArrayList<>();
            for (In s : list) {
                swaps.add(new BookRisk.Swap(s.string("id"), s.integer("tenor_years"), s.real("fixed_rate"),
                        s.choice("side", SwapSide.class) == SwapSide.PAY));
            }
            in.gate();
            BookRisk.OisSensitivity r = BookRisk.oisSensitivity(c, asOf, quotes, interp, swaps);
            List<String> ids = new ArrayList<>();
            for (BookRisk.Swap s : swaps) {
                ids.add(s.id());
            }
            List<String> tenors = new ArrayList<>();
            for (Ois.Quote q : quotes) {
                tenors.add(q.tenor());
            }
            List<String> pillars = new ArrayList<>();
            for (LocalDate d : r.pillars()) {
                pillars.add(d.toString());
            }
            return Operations.out("pv", r.pv(), "book_pv", r.bookPv(),
                    "quote_sensitivity", Operations.out("swaps", ids, "quotes", tenors, "matrix",
                            r.quoteSensitivity()).outputs(),
                    "book_sensitivity", r.bookSensitivity(),
                    "zero_jacobian", Operations.out("pillars", pillars, "quotes", tenors, "matrix",
                            r.zeroJacobian()).outputs());
        });
        table.put("risk.curve.pca", in -> {
            double[][] ch = in.anyMatrix("changes");
            long k = in.integer("components");
            in.gate();
            BookRisk.Pca r = BookRisk.pca(ch, k);
            return Operations.out("eigenvalues", r.eigenvalues(), "loadings", r.loadings(),
                    "explained_ratio", r.explained());
        });
        table.put("risk.curve.cross_gamma", in -> {
            OpsLinear.CurveInput ci = OpsLinear.curve(in, "curve");
            In prod = in.object("product");
            if (!prod.string("kind").equals("OIS")) {
                throw new org.quantforge.core.QfError("E_SCHEMA", "product kind must be OIS", "kind");
            }
            In t = prod.object("trade");
            Conventions.RateIndex tc = Conventions.overnight(t.string("convention"));
            String tenor = t.string("tenor");
            Ois.checkTenor(tenor);
            double k = t.real("fixed_rate");
            double notional = t.real("notional");
            org.quantforge.pricing.Pricing.Side sd = t.choice("side", org.quantforge.pricing.Pricing.Side.class);
            org.quantforge.pricing.Pricing.OisTrade trade = new org.quantforge.pricing.Pricing.OisTrade(tc, tenor, k,
                    notional, sd);
            double bump = in.real("bump_bp");
            in.gate();
            Curve curve = ci.build();
            Ois.Legs legs = Ois.legs(tc, curve.asOf(), tenor);
            double signed = (sd == org.quantforge.pricing.Pricing.Side.PAY ? 1.0 : -1.0) * notional;
            BookRisk.CrossGamma g = BookRisk.crossGammaOis(curve, legs, signed, k,
                    cv -> org.quantforge.pricing.Pricing.oisPv(trade, legs, cv), bump);
            return Operations.out("value", g.value(), "cross_gamma", g.gamma());
        });
        table.put("risk.credit.jtd", in -> {
            List<In> list = in.objects("positions");
            in.limit(list.size() > 100_000, "positions");
            List<BookRisk.JtdPosition> ps = new ArrayList<>();
            for (In p : list) {
                ps.add(new BookRisk.JtdPosition(p.string("id"), p.choice("kind", BookRisk.JtdKind.class),
                        p.real("notional"), p.real("recovery"), p.real("market_value")));
            }
            in.gate();
            double[] j = BookRisk.jtd(ps);
            double total = 0.0;
            for (double v : j) {
                total += v;
            }
            return Operations.out("jtd", j, "total", total);
        });
        table.put("risk.backtest.kupiec", in -> {
            long n = in.integer("observations");
            long x = in.integer("exceptions");
            double c = in.gate(in.real("confidence"));
            PortfolioRisk.Kupiec k = PortfolioRisk.kupiec(n, x, c);
            return Operations.out("lr_uc", k.lr(), "p_value", k.pValue());
        });
        table.put("risk.backtest.christoffersen", in -> {
            List<?> raw = in.anyValue("exceptions") instanceof List<?> l ? l : null;
            boolean[] e = bools(in, raw);
            double c = in.gate(in.real("confidence"));
            PortfolioRisk.Christoffersen r = PortfolioRisk.christoffersen(e, c);
            return Operations.out("lr_uc", r.lrUc(), "lr_ind", r.lrInd(), "lr_cc", r.lrCc(), "p_uc", r.pUc(),
                    "p_ind", r.pInd(), "p_cc", r.pCc(), "transitions", Operations.out("n00", r.n00(), "n01", r.n01(),
                            "n10", r.n10(), "n11", r.n11()).outputs());
        });
        table.put("risk.backtest.traffic_light", in -> {
            long n = in.integer("observations");
            long x = in.integer("exceptions");
            double c = in.gate(in.real("confidence"));
            PortfolioRisk.TrafficLight t = PortfolioRisk.trafficLight(n, x, c);
            return Operations.out("cumulative_probability", t.cumulative(), "zone", t.zone(),
                    "plus_factor", t.plusFactor());
        });
    }

    private static boolean[] bools(In in, List<?> raw) {
        if (raw == null) {
            throw new org.quantforge.core.QfError("E_SCHEMA", "exceptions must be an array of booleans", "exceptions");
        }
        boolean[] e = new boolean[raw.size()];
        for (int i = 0; i < e.length; i++) {
            if (!(raw.get(i) instanceof Boolean b)) {
                throw new org.quantforge.core.QfError("E_SCHEMA", "exceptions must be booleans", "exceptions");
            }
            e[i] = b;
        }
        return e;
    }
}
