package org.quantforge.cli;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.execution.VenueAnalytics;
import org.quantforge.micro.MicroEstimators;
import org.quantforge.micro.MicroEstimators.Estimate;

/**
 * Stage H H-4b microstructure estimators ({@code 09-microstructure/micro-estimators.md}) and H-16 venue analytics
 * ({@code 10-execution/venue-analytics.md}); names fixed in the contract's table. Every input is read before the
 * gate, so E_SCHEMA and a non-finite input (F-2) come before any rule check (HR-75 as amended (HR-66)).
 */
final class OpsMicroEst {
    private OpsMicroEst() {}

    private enum Outcome { CANCEL, FILL }

    private enum Side { BUY, SELL }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("micro.est.arrival_rate", in -> {
            long count = in.integer("count");
            double window = in.gate(in.real("window"));
            return est(MicroEstimators.arrivalRate(count, window), "lambda");
        });
        table.put("micro.est.cancel_rate", in -> {
            List<MicroEstimators.Order> rows = new ArrayList<>();
            for (In o : in.objects("orders")) {
                rows.add(new MicroEstimators.Order(o.real("lifetime"), o.choice("outcome", Outcome.class) == Outcome.CANCEL));
            }
            in.gate();
            return est(MicroEstimators.cancelRate(rows.toArray(MicroEstimators.Order[]::new)), "theta");
        });
        table.put("micro.est.resilience", in -> {
            double sInf = in.real("s_inf");
            List<double[]> pts = new ArrayList<>();
            for (In p : in.objects("points")) {
                pts.add(new double[] {p.real("t"), p.real("s")});
            }
            in.gate();
            return est(MicroEstimators.resilience(sInf, pts.toArray(double[][]::new)), "kappa");
        });
        table.put("micro.est.liquidity_decay", in -> {
            List<double[]> lv = new ArrayList<>();
            for (In p : in.objects("levels")) {
                lv.add(new double[] {p.real("k"), p.real("depth")});
            }
            in.gate();
            return est(MicroEstimators.liquidityDecay(lv.toArray(double[][]::new)), "alpha");
        });
        table.put("micro.est.adverse_selection", in -> {
            double[] x = in.reals("x");
            double[] y = in.gate(in.reals("y"));
            return est(MicroEstimators.adverseSelection(x, y), "lambda_as");
        });
        table.put("micro.est.regime_impact", in -> {
            In reg = in.object("regimes");
            Map<String, MicroEstimators.Sample> rows = new LinkedHashMap<>();
            List<String> labels = new ArrayList<>();
            reg.keys().forEach(labels::add);
            labels.sort(MicroEstimators.CODE_POINT);
            for (String label : labels) {
                In r = reg.object(label);
                rows.put(label, new MicroEstimators.Sample(r.reals("x"), r.reals("y")));
            }
            in.gate();
            MicroEstimators.RegimeImpact ri = MicroEstimators.regimeImpact(rows);
            Map<String, Object> out = new LinkedHashMap<>();
            ri.regimes().forEach((k, v) -> out.put(k, est(v, "lambda_as").outputs()));
            return Operations.out("regimes", out, "ratio", ri.ratio());
        });
        table.put("micro.est.passive_vs_aggressive", in -> {
            double[] p = in.reals("passive");
            double[] a = in.gate(in.reals("aggressive"));
            return est(MicroEstimators.passiveVsAggressive(p, a), "delta");
        });
        table.put("exec.venue.analytics", OpsMicroEst::venue);
    }

    private static Out est(Estimate e, String name) {
        return Operations.out(name, e.value(), "se", e.se());
    }

    private static Out venue(In in) {
        List<double[]> mids = new ArrayList<>();
        for (In m : in.objects("mids")) {
            mids.add(new double[] {m.real("t"), m.real("mid")});
        }
        List<VenueAnalytics.Fill> fills = new ArrayList<>();
        for (In f : in.objects("fills")) {
            fills.add(new VenueAnalytics.Fill(f.string("venue"), f.choice("side", Side.class) == Side.BUY,
                    f.real("quantity"), f.real("price"), f.real("t")));
        }
        List<VenueAnalytics.Order> orders = new ArrayList<>();
        for (In o : in.objects("orders")) {
            orders.add(new VenueAnalytics.Order(o.string("venue"), o.real("sent"), o.real("filled")));
        }
        double[] horizons = in.gate(in.reals("horizons"));
        VenueAnalytics.Result r = VenueAnalytics.analytics(mids.toArray(double[][]::new), fills, orders, horizons);
        List<Map<String, Object>> rows = new ArrayList<>();
        for (VenueAnalytics.Markout m : r.markouts()) {
            rows.add(Operations.out("venue", m.venue(), "h", m.h(), "markout", m.markout(), "markout_bps",
                    m.markoutBps(), "toxicity", m.toxicity()).outputs());
        }
        return Operations.out("fill_rates", new LinkedHashMap<String, Object>(r.fillRates()), "markouts", rows);
    }
}
