package org.quantforge.cli;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.calibration.LeastSquares;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.Calendars;
import org.quantforge.core.Conventions;
import org.quantforge.core.DayCount;
import org.quantforge.core.Money;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.curves.CurveSolver;
import org.quantforge.curves.Ois;
import org.quantforge.curves.Projection;
import org.quantforge.curves.Schedule;
import org.quantforge.hedging.HedgeSolver;
import org.quantforge.pricing.Fx;
import org.quantforge.pricing.Pricing;
import org.quantforge.risk.RatesRisk;

/** Stage B operations. As in {@link Operations}, all inputs are read before the gate, and work comes after it. */
final class StageB {
    private StageB() {}

    private static final int MAX_QUOTES = 100;

    /** A curve as read. Its rule checks wait until {@link #build()}. */
    record CurveInput(LocalDate asOf, Curve.Interpolation interp, LocalDate[] dates, double[] factors) {
        Curve build() {
            return Curve.of(asOf, interp, dates, factors);
        }
    }

    static CurveInput curve(In in, String key) {
        In c = in.object(key);
        LocalDate asOf = c.date("as_of");
        Curve.Interpolation interp = c.choice("interpolation", Curve.Interpolation.class);
        List<In> pillars = c.objects("pillars");
        in.limit(pillars.size() > MAX_QUOTES, key);
        LocalDate[] dates = new LocalDate[pillars.size()];
        double[] factors = new double[dates.length];
        for (int i = 0; i < dates.length; i++) {
            dates[i] = pillars.get(i).date("date");
            factors[i] = pillars.get(i).real("discount_factor");
        }
        return new CurveInput(asOf, interp, dates, factors);
    }

    private static List<Ois.Quote> quotes(In in) {
        List<Ois.Quote> out = new ArrayList<>();
        List<In> list = in.objects("quotes");
        in.limit(list.size() > MAX_QUOTES, "quotes");
        for (In q : list) {
            String tenor = q.string("tenor");
            Ois.checkTenor(tenor);
            if (q.has("rate")) {
                out.add(new Ois.Quote(tenor, q.real("rate"), null, null));
            } else {
                out.add(new Ois.Quote(tenor, null, q.real("bid"), q.real("ask")));
            }
        }
        return out;
    }

    private static Pricing.OisTrade oisTrade(In t) {
        Conventions.RateIndex c = Conventions.overnight(t.string("convention"));
        String tenor = t.string("tenor");
        Ois.checkTenor(tenor);
        return new Pricing.OisTrade(c, tenor, t.real("fixed_rate"), t.real("notional"), t.choice("side", Pricing.Side.class));
    }

    private static List<Map<String, Object>> pillars(Curve c) {
        LocalDate[] d = c.dates();
        double[] f = c.discountFactors();
        List<Map<String, Object>> out = new ArrayList<>();
        for (int i = 0; i < d.length; i++) {
            out.add(Operations.out("date", d[i].toString(), "discount_factor", f[i]).outputs());
        }
        return out;
    }

    private static int listed(long value, String key, long... allowed) {
        for (long a : allowed) {
            if (a == value) {
                return (int) value;
            }
        }
        throw new QfError("E_SCHEMA", key + " not listed", key);
    }

    private static Money.Amount amount(In in) {
        String text = in.string("amount");
        String currency = in.string("currency");
        Money.checkForm(text);
        Money.checkCurrency(currency);
        in.limit(Money.overDigits(text), "amount");
        return new Money.Amount(new BigDecimal(text), currency);
    }

    static void register(Map<String, Function<In, Out>> table) {
        foundations(table);
        rates(table);
        fx(table);
        calibration(table);
        riskAndHedging(table);
        useCases(table);
    }

    private static void foundations(Map<String, Function<In, Out>> table) {
        table.put("core.units.convert", in -> Operations.out("value", Money.convert(in.real("value"),
                in.choice("from", Money.RateUnit.class), in.choice("to", Money.RateUnit.class))));
        table.put("core.units.add_money", in -> {
            Money.Amount a = amount(in.object("a"));
            Money.Amount b = amount(in.object("b"));
            in.gate();
            return Operations.out("amount", Money.add(a, b), "currency", a.currency());
        });
        table.put("core.units.round_money", in -> {
            Money.Amount a = amount(in);
            in.gate();
            return Operations.out("amount", Money.round(a), "currency", a.currency());
        });
        table.put("core.conventions.lookup", in -> new Out(Conventions.lookup(in.string("id")), Map.of()));
        table.put("rates.schedule.generate", in -> {
            LocalDate start = in.date("start");
            LocalDate end = in.date("end");
            int frequency = listed(in.integer("frequency_months"), "frequency_months", 1, 2, 3, 4, 6, 12);
            Calendars.Id cal = in.choice("calendar", Calendars.Id.class);
            boolean eom = in.bool("end_of_month");
            long lag = in.atMost("payment_lag", 30_000);
            in.gate();
            List<Map<String, Object>> periods = new ArrayList<>();
            for (Schedule.Period p : Schedule.generate(start, end, frequency, cal, eom, lag)) {
                periods.add(Operations.out("start", p.start().toString(), "end", p.end().toString(),
                        "payment", p.payment().toString()).outputs());
            }
            return Operations.out("periods", periods);
        });
    }

    private static void rates(Map<String, Function<In, Out>> table) {
        table.put("rates.curve.discount", in -> {
            CurveInput ci = curve(in, "curve");
            List<LocalDate> dates = in.dates("dates");
            in.gate();
            Curve c = ci.build();
            double[] d = new double[dates.size()];
            Double[] z = new Double[d.length];
            for (int i = 0; i < d.length; i++) {
                d[i] = c.discount(dates.get(i));
                z[i] = c.zeroRate(dates.get(i));
            }
            return Operations.out("discount_factors", d, "zero_rates", z);
        });
        table.put("rates.curve.forward", in -> {
            CurveInput ci = curve(in, "curve");
            LocalDate start = in.date("start");
            LocalDate end = in.date("end");
            DayCount.Convention dc = in.choice("day_count", DayCount.Convention.class);
            if (dc == DayCount.Convention.BUS_252 || dc == DayCount.Convention.ACT_365L
                    || dc == DayCount.Convention.ACT_ACT_ICMA || dc == DayCount.Convention.THIRTY_E_360_ISDA) {
                throw new QfError("E_SCHEMA", "day_count needs inputs this operation does not take", "day_count");
            }
            in.gate();
            Curve c = ci.build();
            if (!end.isAfter(start)) {
                throw new QfError("E_DATE_ORDER", "end is not after start", "end");
            }
            double alpha = DayCount.yearFraction(dc, start, end, new DayCount.Extras(null, null, null, null, null));
            return Operations.out("forward", (c.discount(start) / c.discount(end) - 1.0) / alpha);
        });
        table.put("rates.ois.bootstrap", in -> {
            Conventions.RateIndex c = Conventions.overnight(in.string("convention"));
            LocalDate asOf = in.date("as_of");
            List<Ois.Quote> quotes = quotes(in);
            Curve.Interpolation interp = in.choice("interpolation", Curve.Interpolation.class);
            CurveSolver.Method method = in.choice("method", CurveSolver.Method.class);
            in.gate();
            CurveSolver.Solved s = Ois.bootstrap(c, asOf, quotes, interp, method, null);
            return new Out(Operations.out("pillars", pillars(s.curve())).outputs(),
                    Operations.out("max_repricing_error", s.maxRepricingError()).outputs());
        });
        table.put("rates.ois.compound", in -> {
            double[] r = in.reals("rates");
            long[] days = in.integers("days");
            int b = listed(in.integer("denominator"), "denominator", 360, 365);
            return Operations.out("compounded_rate", Ois.compound(r, days, b));
        });
        table.put("rates.ois.pv", in -> {
            CurveInput ci = curve(in, "curve");
            String snapshot = in.has("snapshot_id") ? in.string("snapshot_id") : null;
            Pricing.OisTrade t = oisTrade(in.object("trade"));
            in.gate();
            Pricing.OisResult r = Pricing.ois(t, ci.build(), snapshot);
            return Operations.out("valuation", r.valuation().toJson(), "par_rate", r.parRate(), "annuity", r.annuity());
        });
        table.put("rates.projection.bootstrap", in -> {
            CurveInput d = curve(in, "discount");
            Conventions.RateIndex ix = Conventions.term(in.string("index"));
            LocalDate asOf = in.date("as_of");
            Curve.Interpolation interp = in.choice("interpolation", Curve.Interpolation.class);
            List<In> list = in.objects("quotes");
            in.limit(list.size() > MAX_QUOTES, "quotes");
            List<Projection.Quote> quotes = new ArrayList<>();
            for (In q : list) {
                Projection.QuoteType type = q.choice("type", Projection.QuoteType.class);
                long months = q.integer(type == Projection.QuoteType.FRA ? "start_months" : "months");
                quotes.add(new Projection.Quote(type, months, q.real("rate")));
            }
            in.gate();
            CurveSolver.Solved s = Projection.bootstrap(d.build(), ix, asOf, quotes, interp);
            return new Out(Operations.out("pillars", pillars(s.curve())).outputs(),
                    Operations.out("max_repricing_error", s.maxRepricingError()).outputs());
        });
        table.put("rates.swap.pv", in -> {
            CurveInput d = curve(in, "discount");
            CurveInput p = curve(in, "projection");
            String snapshot = in.has("snapshot_id") ? in.string("snapshot_id") : null;
            In t = in.object("trade");
            Pricing.SwapTrade trade = new Pricing.SwapTrade(Conventions.term(t.string("index")), t.integer("tenor_months"),
                    t.real("fixed_rate"), t.real("notional"), t.choice("side", Pricing.Side.class));
            in.gate();
            Pricing.SwapResult r = Pricing.swap(trade, d.build(), p.build(), snapshot);
            return Operations.out("valuation", r.valuation().toJson(), "par_rate", r.parRate());
        });
        table.put("rates.fra.pv", in -> {
            CurveInput d = curve(in, "discount");
            CurveInput p = curve(in, "projection");
            String snapshot = in.has("snapshot_id") ? in.string("snapshot_id") : null;
            In t = in.object("trade");
            Pricing.FraTrade trade = new Pricing.FraTrade(Conventions.term(t.string("index")), t.date("start"),
                    t.real("fixed_rate"), t.real("notional"), t.choice("side", Pricing.Side.class));
            in.gate();
            Pricing.FraResult r = Pricing.fra(trade, d.build(), p.build(), snapshot);
            return Operations.out("valuation", r.valuation().toJson(), "forward_rate", r.forwardRate());
        });
        table.put("rates.basis.spread", in -> {
            CurveInput d = curve(in, "discount");
            CurveInput p = curve(in, "projection");
            Conventions.RateIndex ix = Conventions.term(in.string("index"));
            long months = in.integer("tenor_months");
            in.gate();
            return Operations.out("spread", Projection.basisSpread(d.build(), p.build(), ix, months));
        });
    }

    /** FX inputs as read; {@link #market()} applies the curves' rule checks. */
    private record FxInput(Conventions.FxPair pair, double spot, LocalDate asOf, CurveInput base, CurveInput quote,
                           String snapshotId) {
        Pricing.FxMarket market() {
            if (spot <= 0.0) {
                throw new QfError("E_DOMAIN", "spot must be positive", "spot");
            }
            return new Pricing.FxMarket(pair, spot, asOf, base.build(), quote.build(), snapshotId);
        }
    }

    private static FxInput fxInput(In in) {
        return new FxInput(Conventions.pair(in.string("pair")), in.real("spot"), in.date("as_of"),
                curve(in, "base_curve"), curve(in, "quote_curve"), in.has("snapshot_id") ? in.string("snapshot_id") : null);
    }

    private static Pricing.FxForward fxForward(In t) {
        return new Pricing.FxForward(t.real("notional_base"), t.real("strike"), t.date("value_date"),
                t.choice("side", Pricing.FxSide.class));
    }

    private static void fx(Map<String, Function<In, Out>> table) {
        table.put("fx.spot_date", in -> {
            Conventions.FxPair p = Conventions.pair(in.string("pair"));
            return Operations.out("spot_date", Fx.spotDate(p, in.date("trade_date")).toString());
        });
        table.put("fx.forward.outright", in -> {
            FxInput f = fxInput(in);
            LocalDate value = in.date("value_date");
            in.gate();
            Pricing.Forward r = Fx.outright(f.market(), value);
            return Operations.out("forward", r.forward(), "points", r.points());
        });
        table.put("fx.forward.pv", in -> {
            FxInput f = fxInput(in);
            Pricing.FxForward t = fxForward(in.object("trade"));
            in.gate();
            Pricing.FxResult r = Fx.forwardPv(f.market(), t);
            return Operations.out("valuation", r.valuation().toJson(), "fx_delta", r.fxDelta());
        });
        table.put("fx.swap.pv", in -> {
            FxInput f = fxInput(in);
            In t = in.object("trade");
            Pricing.FxSwap s = new Pricing.FxSwap(t.real("notional_base"), t.date("near_date"), t.real("near_rate"),
                    t.date("far_date"), t.real("far_rate"), t.choice("far_side", Pricing.FxSide.class));
            in.gate();
            Pricing.FxResult r = Fx.swapPv(f.market(), s);
            return Operations.out("valuation", r.valuation().toJson(), "fx_delta", r.fxDelta());
        });
        table.put("fx.curve.implied", in -> {
            FxInput f = fxInput(in);
            List<Fx.Point> points = new ArrayList<>();
            List<In> list = in.objects("points");
            in.limit(list.size() > MAX_QUOTES, "points");
            for (In p : list) {
                String tenor = p.string("tenor");
                Ois.checkTenor(tenor);
                if (tenor.endsWith("D") || tenor.endsWith("W")) {
                    throw new QfError("E_SCHEMA", "tenors are in M or Y", "points");
                }
                points.add(new Fx.Point(tenor, p.real("points")));
            }
            in.gate();
            List<Map<String, Object>> nodes = new ArrayList<>();
            for (Fx.Node n : Fx.implied(f.market(), points)) {
                nodes.add(Operations.out("value_date", n.valueDate().toString(), "implied_ratio", n.impliedRatio(),
                        "basis_bp", n.basisBp()).outputs());
            }
            return Operations.out("nodes", nodes);
        });
    }

    private static double[] optionalReals(In in, String key) {
        return in.has(key) ? in.reals(key) : null;
    }

    private static void calibration(Map<String, Function<In, Out>> table) {
        table.put("calib.fit", in -> {
            LeastSquares.Model model = in.choice("model", LeastSquares.Model.class);
            boolean noData = model == LeastSquares.Model.ROSENBROCK;
            double[] x = noData && !in.has("x") ? new double[0] : in.reals("x");
            double[] y = noData && !in.has("y") ? new double[0] : in.reals("y");
            double[] start = in.reals("start");
            in.limit(start.length > 20, "start");
            LeastSquares.Method method = in.choice("method", LeastSquares.Method.class);
            double[] weights = optionalReals(in, "weights");
            double lambda = in.real("regularisation", 0.0);
            double[] prior = optionalReals(in, "prior");
            double[] lower = optionalReals(in, "lower");
            double[] upper = optionalReals(in, "upper");
            long maxIter = in.atMost("max_iter", 1000, 100_000);
            boolean report = in.bool("report_parameters", true);
            in.gate();
            LeastSquares.Fit f = LeastSquares.fit(new LeastSquares.Problem(model, x, y, start, method, weights, lambda,
                    prior, lower, upper, maxIter));
            Out out = report ? Operations.out("parameters", f.parameters(), "objective", f.objective())
                    : Operations.out("objective", f.objective());
            return new Out(out.outputs(), Operations.out("iterations", f.iterations(), "status", f.status(),
                    "residuals", f.residuals()).outputs());
        });
        table.put("calib.check_bid_ask", in -> {
            List<Map<String, Object>> breaches = new ArrayList<>();
            for (LeastSquares.Breach b : LeastSquares.checkBidAsk(in.reals("fitted"), in.reals("bid"), in.reals("ask"))) {
                breaches.add(Operations.out("index", b.index(), "side", b.side(), "distance", b.distance()).outputs());
            }
            return Operations.out("breaches", breaches);
        });
        table.put("calib.curve_report", in -> {
            Conventions.RateIndex c = Conventions.overnight(in.string("convention"));
            LocalDate asOf = in.date("as_of");
            List<Ois.Quote> quotes = quotes(in);
            Curve.Interpolation interp = in.choice("interpolation", Curve.Interpolation.class);
            in.gate();
            RatesRisk.CurveReport r = RatesRisk.curveReport(c, asOf, quotes, interp);
            List<String> breaches = r.maxRepricingError() < 1e-13 ? List.of() : List.of("max_repricing_error");
            return new Out(Operations.out("jacobian", r.jacobian(), "condition_number", r.conditionNumber()).outputs(),
                    Operations.out("status", "OK", "max_repricing_error", r.maxRepricingError(),
                            "tolerance_breaches", breaches, "inputs",
                            quotes.stream().map(Ois.Quote::tenor).toList()).outputs());
        });
    }

    private static void riskAndHedging(Map<String, Function<In, Out>> table) {
        table.put("risk.ois.dv01", in -> {
            LocalDate asOf = in.date("as_of");
            List<Ois.Quote> quotes = quotes(in);
            Curve.Interpolation interp = in.choice("interpolation", Curve.Interpolation.class);
            Pricing.OisTrade t = oisTrade(in.object("trade"));
            in.gate();
            RatesRisk.Sensitivity s = RatesRisk.sensitivities(asOf, quotes, interp, List.of(t)).getFirst();
            return Operations.out("dv01", s.dv01(), "key_rate", s.keyRate());
        });
        table.put("risk.cashflows", in -> {
            List<RatesRisk.Cashflow> flows = new ArrayList<>();
            for (In f : in.objects("cashflows")) {
                flows.add(new RatesRisk.Cashflow(f.real("t"), f.real("amount")));
            }
            RatesRisk.CashflowMeasures m = RatesRisk.cashflows(flows, in.gate(in.real("yield")));
            return Operations.out("pv", m.pv(), "duration", m.duration(), "convexity", m.convexity());
        });
        table.put("hedge.solve", in -> {
            double[][] a = in.anyMatrix("a");
            in.limit(a.length > 0 && a[0].length > 20, "a");
            double[] b = in.reals("b");
            double[] w = in.reals("weights");
            double[] c = in.reals("costs");
            double lambda = in.real("lambda");
            in.gate();
            HedgeSolver.Solution s = HedgeSolver.solve(a, b, w, c, lambda);
            return Operations.out("x", s.x(), "residual", s.residual(), "objective", s.objective());
        });
        table.put("hedge.spread_cost", in -> {
            double[] q = in.reals("quantities");
            double[] h = in.reals("half_spreads");
            if (q.length != h.length) {
                throw new QfError("E_INPUT", "lengths differ");
            }
            double cost = 0.0;
            for (int i = 0; i < q.length; i++) {
                if (h[i] < 0.0) {
                    throw new QfError("E_DOMAIN", "half spread is negative", "half_spreads");
                }
                cost += Math.abs(q[i]) * h[i];
            }
            return Operations.out("cost", cost);
        });
    }

    private static void useCases(Map<String, Function<In, Out>> table) {
        table.put("usecase.fx_hedge", in -> {
            FxInput f = fxInput(in);
            List<Pricing.FxForward> book = new ArrayList<>();
            for (In t : in.objects("book")) {
                book.add(fxForward(t));
            }
            double halfSpread = in.real("half_spread");
            in.gate();
            if (halfSpread < 0.0) {
                throw new QfError("E_DOMAIN", "half_spread is negative", "half_spread");
            }
            Pricing.FxMarket m = f.market();
            double pv = 0.0;
            double delta = 0.0;
            for (Pricing.FxForward t : book) {
                Pricing.FxResult r = Fx.forwardPv(m, t);
                pv += r.valuation().pv();
                delta += r.fxDelta();
            }
            double hedge = -delta;
            return Operations.out("pv", pv, "fx_delta", delta, "hedge_spot_base", hedge,
                    "residual_delta", delta + hedge, "hedge_cost", Math.abs(hedge) * halfSpread);
        });
        table.put("usecase.rates_hedge", in -> {
            LocalDate asOf = in.date("as_of");
            List<Ois.Quote> quotes = quotes(in);
            Curve.Interpolation interp = in.choice("interpolation", Curve.Interpolation.class);
            Pricing.OisTrade trade = oisTrade(in.object("trade"));
            List<String> tenors = in.strings("hedge_tenors");
            tenors.forEach(Ois::checkTenor);
            in.limit(tenors.size() > 20, "hedge_tenors");
            double unit = in.real("hedge_unit_notional");
            double halfSpread = in.real("half_spread_bp");
            in.gate();
            if (halfSpread < 0.0) {
                throw new QfError("E_DOMAIN", "half_spread_bp is negative", "half_spread_bp");
            }
            Curve curve = Ois.bootstrap(trade.convention(), asOf, quotes, interp, CurveSolver.Method.SEQUENTIAL, null).curve();
            double pv = Pricing.ois(trade, curve, null).valuation().pv();
            List<Pricing.OisTrade> all = new ArrayList<>(List.of(trade));
            for (String tenor : tenors) {
                double par = Ois.legs(trade.convention(), asOf, tenor).parRate(curve);
                all.add(new Pricing.OisTrade(trade.convention(), tenor, par, unit, Pricing.Side.PAY));
            }
            List<RatesRisk.Sensitivity> sens = RatesRisk.sensitivities(asOf, quotes, interp, all);
            double[] key = sens.getFirst().keyRate();
            int rows = key.length;
            int cols = tenors.size();
            double[][] c = new double[rows][cols];
            double[] ones = new double[rows];
            java.util.Arrays.fill(ones, 1.0);
            for (int h = 0; h < cols; h++) {
                double[] column = sens.get(h + 1).keyRate();
                for (int r = 0; r < rows; r++) {
                    c[r][h] = column[r];
                }
            }
            HedgeSolver.Solution s = HedgeSolver.solve(c, key, ones, new double[cols], 0.0);
            double cost = 0.0;
            for (int h = 0; h < cols; h++) {
                double sum = 0.0;
                for (int r = 0; r < rows; r++) {
                    sum += c[r][h];
                }
                cost += Math.abs(s.x()[h]) * Math.abs(sum) * halfSpread;
            }
            return Operations.out("pv", pv, "dv01", sens.getFirst().dv01(), "key_rate", key, "hedge_units", s.x(),
                    "residual_key_rate", s.residual(), "hedge_cost", cost);
        });
    }
}
