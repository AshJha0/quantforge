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
import org.quantforge.curves.JointSolver;
import org.quantforge.curves.Jumps;
import org.quantforge.curves.Ois;
import org.quantforge.curves.Projection;
import org.quantforge.curves.RatesCurves;
import org.quantforge.curves.StepCurve;

/** Stage D wave 1 operations. All inputs are read before the gate, and work comes after it. */
final class OpsRatesCurves {
    private OpsRatesCurves() {}

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
            Jumps jumps = OpsLinear.jumps(in, true);
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
            List<Ois.Quote> quotes = OpsLinear.quotes(in);
            Jumps jumps = OpsLinear.jumps(in, true);
            in.gate();
            Conventions.RateIndex c = Conventions.requireOvernight(id);
            RatesCurves.StepFit fit = RatesCurves.fitSteps(c, asOf, stepDates.toArray(new LocalDate[0]), quotes, jumps);
            return new Out(Operations.out("base_rate", fit.baseRate(), "step_rates", fit.stepRates()).outputs(),
                    Operations.out("max_repricing_error", fit.maxRepricingError()).outputs());
        });
        table.put("rates.futures.convexity", in -> {
            RatesCurves.Convexity r = RatesCurves.convexity(in.real("price"), in.real("start_years"), in.real("end_years"),
                    in.real("sigma"), in.gate(in.real("mean_reversion")));
            return Operations.out("futures_rate", r.futuresRate(), "convexity", r.convexity(),
                    "forward_rate", r.forwardRate());
        });
        table.put("rates.csa.discount", in -> {
            OpsLinear.CurveInput ci = OpsLinear.curve(in, "curve");
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
                    RatesCurves.csaDiscount(c, s, spot, fwdDates, fwds, dates.toArray(new LocalDate[0])));
        });
        table.put("rates.basis.ois_spread", in -> {
            Conventions.RateIndex c = Conventions.overnight(in.string("convention"));
            String tenor = in.string("tenor");
            Ois.checkTenor(tenor);
            OpsLinear.CurveInput d = OpsLinear.curve(in, "discount");
            OpsLinear.CurveInput a = OpsLinear.curve(in, "projection_a");
            OpsLinear.CurveInput b = OpsLinear.curve(in, "projection_b");
            in.gate();
            return Operations.out("spread", RatesCurves.oisSpread(c, tenor, d.build(), a.build(), b.build()));
        });
        table.put("rates.curve.joint_bootstrap", in -> {
            Conventions.RateIndex c = Conventions.overnight(in.string("convention"));
            Conventions.RateIndex ix = Conventions.term(in.string("index"));
            LocalDate asOf = in.date("as_of");
            List<Ois.Quote> ois = OpsLinear.quotes(in, "ois_quotes");
            List<Projection.Quote> term = OpsLinear.termQuotes(in, "term_quotes");
            Curve.Interpolation interp = in.choice("interpolation", Curve.Interpolation.class);
            CurveSolver.Method method = in.choice("method", CurveSolver.Method.class);
            in.gate();
            RatesCurves.Joint j = RatesCurves.jointBootstrap(c, ix, asOf, ois, term, interp, method);
            return new Out(Operations.out("discount_pillars", OpsLinear.pillars(j.discount()),
                    "projection_pillars", OpsLinear.pillars(j.projection())).outputs(),
                    Operations.out("max_repricing_error", j.maxRepricingError()).outputs());
        });
        table.put("rates.curve.joint_solve", in -> {
            LocalDate asOf = in.date("as_of");
            List<In> cs = in.objects("curves");
            in.limit(cs.size() > MAX_LIST, "curves");
            List<JointSolver.CurveSpec> curves = new ArrayList<>();
            for (In c : cs) {
                JointSolver.CurveType type = c.choice("type", JointSolver.CurveType.class);
                boolean pillar = type != JointSolver.CurveType.OIS_STEPS;
                boolean ois = type == JointSolver.CurveType.OIS || type == JointSolver.CurveType.OIS_STEPS;
                LocalDate[] turns = new LocalDate[0];
                if (ois && c.hasKey("turns")) {
                    List<In> tl = c.objects("turns");
                    in.limit(tl.size() > MAX_LIST, "turns");
                    turns = new LocalDate[tl.size()];
                    for (int i = 0; i < turns.length; i++) {
                        turns[i] = tl.get(i).date("date");
                    }
                }
                LocalDate[] steps = null;
                if (type == JointSolver.CurveType.OIS_STEPS) {
                    List<LocalDate> sd = c.dates("step_dates");
                    in.limit(sd.size() > MAX_LIST, "step_dates");
                    steps = sd.toArray(new LocalDate[0]);
                }
                boolean xccy = type == JointSolver.CurveType.XCCY;
                curves.add(new JointSolver.CurveSpec(c.string("name"), type,
                        ois ? c.string("convention") : null,
                        pillar ? c.choice("interpolation", Curve.Interpolation.class) : null,
                        pillar ? OpsLinear.shape(c) : Curve.Shape.NONE,
                        ois ? OpsLinear.jumps(c, false) : Jumps.NONE, turns, steps,
                        type == JointSolver.CurveType.PROJECTION ? c.string("index") : null,
                        type == JointSolver.CurveType.PROJECTION ? c.string("discount") : null,
                        xccy ? c.string("domestic") : null, xccy ? c.string("foreign_projection") : null,
                        xccy ? c.string("domestic_convention") : null, xccy ? c.string("foreign_convention") : null,
                        xccy ? c.date("start") : null));
            }
            List<In> is = in.objects("instruments");
            in.limit(is.size() > 1000, "instruments");
            List<JointSolver.InstrumentSpec> instruments = new ArrayList<>();
            for (In q : is) {
                JointSolver.InstrumentType type = q.choice("type", JointSolver.InstrumentType.class);
                String id = q.string("id");
                String curve = q.string("curve");
                boolean turn = q.bool("turn", false);
                instruments.add(switch (type) {
                    case OIS -> {
                        String tenor = q.string("tenor");
                        org.quantforge.curves.Ois.checkTenor(tenor);
                        yield new JointSolver.InstrumentSpec(id, curve, type, turn, q.real("rate"), tenor, null,
                                null, null, null, null);
                    }
                    case FUTURE -> new JointSolver.InstrumentSpec(id, curve, type, turn, q.real("price"), null, null,
                            q.date("start"), q.date("end"), q.real("sigma"), q.real("mean_reversion"));
                    case FRA -> new JointSolver.InstrumentSpec(id, curve, type, turn, q.real("rate"), null,
                            q.integer("start_months"), null, null, null, null);
                    case DEPOSIT, SWAP -> new JointSolver.InstrumentSpec(id, curve, type, turn, q.real("rate"), null,
                            q.integer("months"), null, null, null, null);
                    case XCCY -> new JointSolver.InstrumentSpec(id, curve, type, turn, q.real("spread"), null,
                            q.integer("months"), null, null, null, null);
                });
            }
            in.gate();
            JointSolver.Result r = JointSolver.solve(asOf, curves, instruments);
            List<Map<String, Object>> co = new ArrayList<>();
            for (JointSolver.SolvedCurve c : r.curves()) {
                if (c.baseRate() != null) {
                    co.add(Operations.out("name", c.name(), "base_rate", c.baseRate(), "step_rates", c.stepRates())
                            .outputs());
                } else {
                    List<Map<String, Object>> p = new ArrayList<>();
                    for (int i = 0; i < c.pillars().length; i++) {
                        p.add(Operations.out("date", c.pillars()[i].toString(), "discount_factor",
                                c.discountFactors()[i]).outputs());
                    }
                    co.add(Operations.out("name", c.name(), "pillars", p).outputs());
                }
            }
            List<Map<String, Object>> tf = new ArrayList<>();
            for (JointSolver.TurnFactor t : r.turnFactors()) {
                tf.add(Operations.out("curve", t.curve(), "date", t.date().toString(), "factor", t.factor()).outputs());
            }
            Map<String, Object> jac = Operations.out("unknowns", r.unknowns(), "quotes", r.quotes(),
                    "matrix", r.jacobian()).outputs();
            return new Out(Operations.out("curves", co, "turn_factors", tf, "jacobian", jac,
                    "turn_sensitivity", r.turnSensitivity()).outputs(),
                    Operations.out("max_repricing_error", r.maxRepricingError()).outputs());
        });
        table.put("rates.funding.curve", in -> {
            OpsLinear.CurveInput ci = OpsLinear.curve(in, "discount");
            List<In> qs = in.objects("quotes");
            in.limit(qs.size() > MAX_LIST, "quotes");
            LocalDate[] ends = new LocalDate[qs.size()];
            double[] rates = new double[ends.length];
            for (int i = 0; i < ends.length; i++) {
                ends[i] = qs.get(i).date("end");
                rates[i] = qs.get(i).real("rate");
            }
            List<LocalDate> dates = in.hasKey("dates") ? in.dates("dates") : List.of();
            in.limit(dates.size() > 10_000, "dates");
            in.gate();
            JointSolver.Funding f = JointSolver.funding(ci.build(), ends, rates, dates.toArray(new LocalDate[0]));
            List<Map<String, Object>> p = new ArrayList<>();
            for (int i = 0; i < ends.length; i++) {
                p.add(Operations.out("date", ends[i].toString(), "discount_factor", f.pillarFactors()[i]).outputs());
            }
            return Operations.out("spreads", f.spreads(), "pillars", p, "discount_factors", f.discountFactors());
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
