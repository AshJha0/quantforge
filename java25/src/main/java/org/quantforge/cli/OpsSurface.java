package org.quantforge.cli;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.vol.Black;
import org.quantforge.vol.Surface;

/** vol.surface.*, risk.vol.surface_vega */
final class OpsSurface {
    private OpsSurface() {}

    private static Surface surface(In in) {
        In s = in.object("surface");
        double[] t = s.reals("expiry_years");
        double[] k = s.reals("log_moneyness");
        double[][] v = s.anyMatrix("vols");
        in.limit(t.length > OpsForward.MAX_LIST || k.length > OpsForward.MAX_LIST || v.length > OpsForward.MAX_LIST, "surface");
        return new Surface(t, k, v);
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("vol.surface.query", in -> {
            Surface s = surface(in);
            List<In> pts = in.objects("points");
            in.limit(pts.size() > OpsForward.MAX_LIST, "points");
            double[] t = new double[pts.size()];
            double[] k = new double[t.length];
            for (int i = 0; i < t.length; i++) {
                t[i] = pts.get(i).real("expiry_years");
                k[i] = pts.get(i).real("log_moneyness");
            }
            in.gate();
            s.check();
            List<Object> w = new ArrayList<>();
            List<Object> v = new ArrayList<>();
            for (int i = 0; i < t.length; i++) {
                double x = s.totalVariance(t[i], k[i]);
                w.add(x);
                v.add(Math.sqrt(x / t[i]));
            }
            return Operations.out("total_variance", w, "vols", v);
        });
        table.put("vol.surface.check", in -> {
            Surface s = surface(in);
            in.gate();
            s.check();
            List<Object> c = s.calendarViolations();
            List<Object> b = s.butterflyViolations();
            return Operations.out("calendar_violations", c, "butterfly_violations", b, "arbitrage_free",
                    c.isEmpty() && b.isEmpty());
        });
        table.put("risk.vol.surface_vega", in -> {
            Surface s = surface(in);
            List<In> list = in.objects("positions");
            in.limit(list.size() > OpsForward.MAX_LIST, "positions");
            List<Surface.Position> book = new ArrayList<>();
            for (In p : list) {
                book.add(new Surface.Position(Black.phi(p.choice("option_type", Black.OptionType.class)), p.real("forward"),
                        p.real("strike"), p.real("discount_factor"), p.real("expiry_years"), p.real("quantity")));
            }
            in.gate();
            s.check();
            for (Surface.Position p : book) {
                if (p.forward() <= 0.0 || p.strike() <= 0.0 || p.discount() <= 0.0 || p.t() <= 0.0) {
                    throw new QfError("E_DOMAIN", "position input is not positive");
                }
            }
            Surface.Vega r = s.vega(book);
            List<Object> rows = new ArrayList<>();
            for (double[] row : r.bucket()) {
                rows.add(OpsSmile.list(row));
            }
            return Operations.out("pv", r.pv(), "bucket_vega", rows, "parallel_vega", r.parallel(), "bucket_sum", r.sum());
        });
    }
}
