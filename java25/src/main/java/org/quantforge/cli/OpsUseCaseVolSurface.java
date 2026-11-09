package org.quantforge.cli;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.pricing.EquityForward;
import org.quantforge.pricing.Pricing;
import org.quantforge.vol.Black;
import org.quantforge.vol.Smile;
import org.quantforge.vol.Surface;

/** usecase.vol_surface (use-cases.md). */
final class OpsUseCaseVolSurface {
    private OpsUseCaseVolSurface() {}

    private record Slice(LocalDate expiry, List<EquityForward.Quote> quotes) {}

    static void register(Map<String, Function<In, Out>> table) {
        table.put("usecase.vol_surface", in -> {
            LocalDate asOf = in.date("as_of");
            OpsLinear.CurveInput ci = OpsLinear.curve(in, "funding_curve");
            List<In> list = in.objects("slices");
            in.limit(list.size() > OpsForward.MAX_LIST, "slices");
            List<Slice> slices = new ArrayList<>();
            for (In s : list) {
                slices.add(new Slice(s.date("expiry"), OpsForward.quotes(s)));
            }
            double[] grid = in.reals("k_grid");
            in.limit(grid.length > OpsForward.MAX_LIST, "k_grid");
            In tg = in.object("target");
            double phi = Black.phi(tg.choice("option_type", Black.OptionType.class));
            double strike = tg.real("strike");
            LocalDate expiry = tg.date("expiry");
            double q = tg.real("quantity");
            double sign = tg.choice("side", Pricing.FxSide.class) == Pricing.FxSide.BUY ? 1.0 : -1.0;
            String currency = in.string("currency");
            in.gate();
            OpsForward.nonEmpty(slices.size(), grid.length);
            for (Slice s : slices) {
                OpsForward.nonEmpty(s.quotes().size());
            }
            Curve curve = ci.build();
            if (!curve.asOf().equals(asOf)) {
                throw new QfError("E_INPUT", "curve as_of differs");
            }
            if (strike <= 0.0 || q <= 0.0) {
                throw new QfError("E_DOMAIN", "strike or quantity");
            }
            int n = slices.size();
            double[] times = new double[n];
            double[] ds = new double[n];
            double[] fs = new double[n];
            Smile.Svi[] fits = new Smile.Svi[n];
            List<Object> forwards = new ArrayList<>();
            List<Object> rmse = new ArrayList<>();
            double[][] vols = new double[n][grid.length];
            int target = -1;
            for (int j = 0; j < n; j++) {
                Slice s = slices.get(j);
                double t = ChronoUnit.DAYS.between(asOf, s.expiry()) / 365.0;
                double d = curve.discount(s.expiry());
                double f = EquityForward.parity(s.quotes(), d).forward();
                int m = s.quotes().size();
                double[] k = new double[m];
                double[] w = new double[m];
                for (int i = 0; i < m; i++) {
                    EquityForward.Quote o = s.quotes().get(i);
                    boolean call = o.strike() >= f;
                    double mid = call ? (o.callBid() + o.callAsk()) / 2.0 : (o.putBid() + o.putAsk()) / 2.0;
                    Black.Option opt = new Black.Option(Black.Model.BLACK_76, call ? 1.0 : -1.0, o.strike(), t, f, 0.0, 0.0, d, 0.0);
                    double v = Black.implied(opt, mid);
                    k[i] = Math.log(o.strike() / f);
                    w[i] = v * v * t;
                }
                Smile.SviFit fit = Smile.calibrateSvi(k, w, null);
                times[j] = t;
                ds[j] = d;
                fs[j] = f;
                fits[j] = fit.svi();
                forwards.add(f);
                rmse.add(fit.rmse());
                for (int i = 0; i < grid.length; i++) {
                    vols[j][i] = Math.sqrt(fit.svi().w(grid[i]) / t);
                }
                if (s.expiry().equals(expiry)) {
                    target = j;
                }
            }
            Surface surface = new Surface(times, grid, vols);
            surface.check();
            boolean free = surface.calendarViolations().isEmpty() && surface.butterflyViolations().isEmpty();
            if (target < 0) {
                throw new QfError("E_INPUT", "target expiry is not a slice's");
            }
            double t = times[target];
            double d = ds[target];
            double f = fs[target];
            double vol = Math.sqrt(fits[target].w(Math.log(strike / f)) / t);
            double root = Math.sqrt(t);
            double d1 = (Math.log(f / strike) + vol * vol * t / 2.0) / (vol * root);
            double pv = sign * q * Black.lognormal(phi, f, strike, t, d, vol);
            Pricing.Valuation v = new Pricing.Valuation(pv, currency, "BLACK_76_EQUITY", null, "EQUITY_FORWARD", asOf);
            return Operations.out("forwards", forwards, "svi_rmse", rmse, "arbitrage_free", free, "vol", vol, "valuation",
                    v.toJson(), "delta", sign * q * d * phi * Normal.cdf(phi * d1), "vega", sign * q * d * f * Normal.pdf(d1) * root);
        });
    }
}
