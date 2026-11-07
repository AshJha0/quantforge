package org.quantforge.cli;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.calibration.CurveFits;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.Conventions;
import org.quantforge.curves.Curve;
import org.quantforge.curves.CurveSolver;
import org.quantforge.curves.DatedCompounding;
import org.quantforge.curves.Jumps;
import org.quantforge.curves.Ois;
import org.quantforge.curves.Projection;
import org.quantforge.curves.RatesD;
import org.quantforge.curves.StepCurve;

/** Stage D wave 1 operations. All inputs are read before the gate, and work comes after it. */
final class StageD {
    private StageD() {}

    private static final int MAX_LIST = 100;

    static void register(Map<String, Function<In, Out>> table) {
        table.put("rates.ois.compound_dated", in -> {
            String id = in.string("convention");
            LocalDate start = in.date("start");
            LocalDate end = in.date("end");
            DatedCompounding.Method method = in.choice("method", DatedCompounding.Method.class);
            long k = in.integer("shift_days");
            Fixings f = fixings(in);
            in.gate();
            Conventions.RateIndex c = Conventions.requireOvernight(id);
            DatedCompounding.Result r = DatedCompounding.compound(c, start, end, method, k, f.dates, f.rates);
            return Operations.out("compounded_rate", r.compoundedRate(), "accrual", r.accrual(), "interest", r.interest());
        });
        table.put("rates.fallback.rate", in -> {
            DatedCompounding.Fallback fb = DatedCompounding.fallback(in.string("ibor"));
            LocalDate start = in.date("start");
            LocalDate end = in.date("end");
            Fixings f = fixings(in);
            in.gate();
            DatedCompounding.Result r = DatedCompounding.compound(fb.index(), start, end,
                    DatedCompounding.Method.OBSERVATION_SHIFT, 2, f.dates, f.rates);
            return Operations.out("compounded_rate", r.compoundedRate(), "spread_adjustment", fb.spread(),
                    "fallback_rate", r.compoundedRate() + fb.spread());
        });
        table.put("rates.ois.step_curve", in -> {
            LocalDate asOf = in.date("as_of");
            double base = in.real("base_rate");
            List<In> steps = in.objects("steps");
            in.limit(steps.size() > MAX_LIST, "steps");
            LocalDate[] stepDates = new LocalDate[steps.size()];
            double[] rates = new double[stepDates.length];
            for (int i = 0; i < stepDates.length; i++) {
                stepDates[i] = steps.get(i).date("date");
                rates[i] = steps.get(i).real("rate");
            }
            Jumps jumps = StageB.jumps(in, true);
            List<LocalDate> dates = in.dates("dates");
            in.gate();
            StepCurve curve = StepCurve.of(asOf, base, stepDates, rates, jumps);
            if (dates.isEmpty()) {
                throw new org.quantforge.core.QfError("E_INPUT", "no dates", "dates");
            }
            double[] d = new double[dates.size()];
            double[] fwd = new double[d.length];
            for (int i = 0; i < d.length; i++) {
                d[i] = curve.discount(dates.get(i));
                fwd[i] = curve.forward(dates.get(i));
            }
            return Operations.out("discount_factors", d, "overnight_forwards", fwd);
        });
        table.put("rates.ois.fit_steps", in -> {
            String id = in.string("convention");
            LocalDate asOf = in.date("as_of");
            List<LocalDate> stepDates = in.dates("step_dates");
            in.limit(stepDates.size() > MAX_LIST, "step_dates");
            List<Ois.Quote> quotes = StageB.quotes(in);
            Jumps jumps = StageB.jumps(in, true);
            in.gate();
            Conventions.RateIndex c = Conventions.requireOvernight(id);
            RatesD.StepFit fit = RatesD.fitSteps(c, asOf, stepDates.toArray(new LocalDate[0]), quotes, jumps);
            return new Out(Operations.out("base_rate", fit.baseRate(), "step_rates", fit.stepRates()).outputs(),
                    Operations.out("max_repricing_error", fit.maxRepricingError()).outputs());
        });
        table.put("rates.futures.convexity", in -> {
            RatesD.Convexity r = RatesD.convexity(in.real("price"), in.real("start_years"), in.real("end_years"),
                    in.real("sigma"), in.gate(in.real("mean_reversion")));
            return Operations.out("futures_rate", r.futuresRate(), "convexity", r.convexity(),
                    "forward_rate", r.forwardRate());
        });
        table.put("rates.csa.discount", in -> {
            StageB.CurveInput ci = StageB.curve(in, "curve");
            double s = in.real("collateral_spread");
            Object fxRaw = in.anyValue("fx");
            Double spot = null;
            LocalDate[] fwdDates = new LocalDate[0];
            double[] fwds = new double[0];
            if (fxRaw != null) {
                In fx = in.object("fx");
                spot = fx.real("spot");
                List<In> list = fx.objects("forwards");
                in.limit(list.size() > 10_000, "forwards");
                fwdDates = new LocalDate[list.size()];
                fwds = new double[fwdDates.length];
                for (int i = 0; i < fwds.length; i++) {
                    fwdDates[i] = list.get(i).date("date");
                    fwds[i] = list.get(i).real("forward");
                }
            }
            List<LocalDate> dates = in.dates("dates");
            in.gate();
            Curve c = ci.build();
            return Operations.out("discount_factors",
                    RatesD.csaDiscount(c, s, spot, fwdDates, fwds, dates.toArray(new LocalDate[0])));
        });
        table.put("rates.basis.ois_spread", in -> {
            Conventions.RateIndex c = Conventions.overnight(in.string("convention"));
            String tenor = in.string("tenor");
            Ois.checkTenor(tenor);
            StageB.CurveInput d = StageB.curve(in, "discount");
            StageB.CurveInput a = StageB.curve(in, "projection_a");
            StageB.CurveInput b = StageB.curve(in, "projection_b");
            in.gate();
            return Operations.out("spread", RatesD.oisSpread(c, tenor, d.build(), a.build(), b.build()));
        });
        table.put("rates.curve.joint_bootstrap", in -> {
            Conventions.RateIndex c = Conventions.overnight(in.string("convention"));
            Conventions.RateIndex ix = Conventions.term(in.string("index"));
            LocalDate asOf = in.date("as_of");
            List<Ois.Quote> ois = StageB.quotes(in, "ois_quotes");
            List<Projection.Quote> term = StageB.termQuotes(in, "term_quotes");
            Curve.Interpolation interp = in.choice("interpolation", Curve.Interpolation.class);
            CurveSolver.Method method = in.choice("method", CurveSolver.Method.class);
            in.gate();
            RatesD.Joint j = RatesD.jointBootstrap(c, ix, asOf, ois, term, interp, method);
            return new Out(Operations.out("discount_pillars", StageB.pillars(j.discount()),
                    "projection_pillars", StageB.pillars(j.projection())).outputs(),
                    Operations.out("max_repricing_error", j.maxRepricingError()).outputs());
        });
        table.put("calib.curve.smooth", in -> {
            double[] knots = in.reals("knots");
            double[] m = in.reals("maturities");
            double[] y = in.reals("zero_rates");
            double lambda = in.real("lambda");
            double[] w = in.hasKey("weights") ? in.reals("weights") : null;
            in.gate();
            CurveFits.Smooth r = CurveFits.smooth(knots, m, y, lambda, w);
            return Operations.out("forwards", r.forwards(), "fitted", r.fitted(), "objective", r.objective());
        });
        table.put("calib.curve.robust", in -> {
            double[] m = in.reals("maturities");
            double[] y = in.reals("zero_rates");
            double tau = in.real("tau");
            double delta = in.real("delta");
            in.gate();
            CurveFits.Robust r = CurveFits.robust(m, y, tau, delta);
            List<Long> out = new ArrayList<>();
            for (int i : r.outliers()) {
                out.add((long) i);
            }
            return Operations.out("betas", r.betas(), "residuals", r.residuals(), "outliers", out,
                    "objective", r.objective());
        });
    }

    private record Fixings(LocalDate[] dates, double[] rates) {}

    private static Fixings fixings(In in) {
        List<In> list = in.objects("fixings");
        LocalDate[] d = new LocalDate[list.size()];
        double[] r = new double[d.length];
        for (int i = 0; i < d.length; i++) {
            d[i] = list.get(i).date("date");
            r[i] = list.get(i).real("rate");
        }
        return new Fixings(d, r);
    }
}
