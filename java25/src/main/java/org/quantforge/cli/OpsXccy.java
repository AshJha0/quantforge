package org.quantforge.cli;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.Conventions;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.curves.CurveSolver;
import org.quantforge.curves.Xccy;

/** Stage D wave 2, D3: cross-currency basis and NDFs. */
final class OpsXccy {
    private OpsXccy() {}

    static void register(Map<String, Function<In, Out>> table) {
        table.put("fx.xccy.bootstrap", in -> {
            OpsLinear.CurveInput dom = OpsLinear.curve(in, "domestic");
            OpsLinear.CurveInput fp = OpsLinear.curve(in, "foreign_projection");
            Conventions.RateIndex dc = Conventions.overnight(in.string("domestic_convention"));
            Conventions.RateIndex fc = Conventions.overnight(in.string("foreign_convention"));
            LocalDate start = in.date("start");
            List<In> q = in.objects("quotes");
            in.limit(q.size() > 100, "quotes");
            long[] months = new long[q.size()];
            double[] spreads = new double[months.length];
            for (int i = 0; i < months.length; i++) {
                months[i] = q.get(i).integer("months");
                spreads[i] = q.get(i).real("spread");
            }
            Curve.Interpolation interp = in.choice("interpolation", Curve.Interpolation.class);
            in.gate();
            Curve d = dom.build();
            Curve f = fp.build();
            Xccy.checkConventions(dc, fc);
            CurveSolver.Solved s = Xccy.bootstrap(d, f, start, months, spreads, interp);
            return new Out(Operations.out("pillars", OpsLinear.pillars(s.curve())).outputs(),
                    Operations.out("max_repricing_error", s.maxRepricingError()).outputs());
        });
        table.put("fx.xccy.pv", in -> {
            OpsLinear.CurveInput dom = OpsLinear.curve(in, "domestic");
            OpsLinear.CurveInput fp = OpsLinear.curve(in, "foreign_projection");
            OpsLinear.CurveInput fd = OpsLinear.curve(in, "foreign_discount");
            double spot = in.real("spot");
            In t = in.object("trade");
            LocalDate start = t.date("start");
            long months = t.integer("months");
            double notional = t.real("foreign_notional");
            double spread = t.real("spread");
            String side = t.string("side");
            if (!side.equals("RECEIVE_FOREIGN") && !side.equals("PAY_FOREIGN")) {
                throw new QfError("E_SCHEMA", "unknown side", "side");
            }
            in.gate();
            Xccy.Pv r = Xccy.pv(dom.build(), fp.build(), fd.build(), spot, start, months, notional, spread,
                    side.equals("RECEIVE_FOREIGN"));
            return Operations.out("pv", r.pv(), "foreign_leg", r.foreignLeg(), "domestic_leg", r.domesticLeg());
        });
        table.put("fx.ndf.pv", in -> {
            OpsLinear.CurveInput usd = OpsLinear.curve(in, "usd_curve");
            OpsLinear.CurveInput off = OpsLinear.curve(in, "offshore_curve");
            double spot = in.real("spot");
            In t = in.object("trade");
            LocalDate fixingDate = t.date("fixing_date");
            LocalDate payment = t.date("payment_date");
            double strike = t.real("strike");
            double notional = t.real("usd_notional");
            String side = t.string("side");
            if (!side.equals("BUY") && !side.equals("SELL")) {
                throw new QfError("E_SCHEMA", "unknown side", "side");
            }
            Double fixing = in.nullableReal("fixing");
            in.gate();
            Xccy.Ndf r = Xccy.ndf(usd.build(), off.build(), spot, fixingDate, payment, strike, notional,
                    side.equals("BUY"), fixing);
            return Operations.out("pv", r.pv(), "forward", r.forward());
        });
    }
}
