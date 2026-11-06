package org.quantforge.oracle;

import com.opengamma.strata.basics.ReferenceData;
import com.opengamma.strata.basics.currency.Currency;
import com.opengamma.strata.basics.date.BusinessDayAdjustment;
import com.opengamma.strata.basics.date.BusinessDayConventions;
import com.opengamma.strata.basics.date.DayCounts;
import com.opengamma.strata.basics.date.HolidayCalendarId;
import com.opengamma.strata.basics.date.Tenor;
import com.opengamma.strata.basics.index.OvernightIndices;
import com.opengamma.strata.basics.schedule.Frequency;
import com.opengamma.strata.basics.schedule.PeriodicSchedule;
import com.opengamma.strata.basics.schedule.RollConventions;
import com.opengamma.strata.basics.schedule.Schedule;
import com.opengamma.strata.basics.schedule.SchedulePeriod;
import com.opengamma.strata.basics.schedule.StubConvention;
import com.opengamma.strata.collect.array.DoubleArray;
import com.opengamma.strata.market.curve.CurveName;
import com.opengamma.strata.market.curve.Curves;
import com.opengamma.strata.market.curve.InterpolatedNodalCurve;
import com.opengamma.strata.market.curve.interpolator.CurveExtrapolators;
import com.opengamma.strata.market.curve.interpolator.CurveInterpolators;
import com.opengamma.strata.pricer.rate.ImmutableRatesProvider;
import com.opengamma.strata.pricer.swap.DiscountingSwapTradePricer;
import com.opengamma.strata.product.common.BuySell;
import com.opengamma.strata.product.swap.ResolvedSwapTrade;
import com.opengamma.strata.product.swap.type.FixedOvernightSwapConventions;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;

/**
 * Oracle only. Line kinds, tab separated:
 * SCHED start end months calendar  -> adjusted boundaries from Strata's PeriodicSchedule.
 * OIS conv as_of tenor rate notional PAY|RECEIVE date:df,date:df,... -> PV from Strata's swap pricer.
 */
public final class StrataRates {
  public static void main(String[] args) throws IOException {
    ReferenceData ref = ReferenceData.standard();
    List<String> out = new ArrayList<>();
    for (String line : Files.readAllLines(Path.of(args[0]))) {
      String[] f = line.split("\t");
      if (f[0].equals("SCHED")) {
        BusinessDayAdjustment adj = BusinessDayAdjustment.of(BusinessDayConventions.MODIFIED_FOLLOWING, HolidayCalendarId.of(f[4]));
        PeriodicSchedule ps = PeriodicSchedule.of(LocalDate.parse(f[1]), LocalDate.parse(f[2]), Frequency.ofMonths(Integer.parseInt(f[3])),
            adj, StubConvention.SHORT_INITIAL, RollConventions.NONE);
        Schedule s = ps.createSchedule(ref);
        StringBuilder b = new StringBuilder(s.getPeriods().get(0).getStartDate().toString());
        for (SchedulePeriod p : s.getPeriods()) {
          b.append(',').append(p.getEndDate());
        }
        out.add(line + "\t" + b);
      } else {
        LocalDate val = LocalDate.parse(f[2]);
        boolean sonia = f[1].equals("SONIA");
        Currency ccy = sonia ? Currency.GBP : Currency.USD;
        String[] nodes = f[7].split(",");
        double[] t = new double[nodes.length + 1];
        double[] d = new double[nodes.length + 1];
        d[0] = 1.0;
        for (int i = 0; i < nodes.length; i++) {
          String[] n = nodes[i].split(":");
          t[i + 1] = ChronoUnit.DAYS.between(val, LocalDate.parse(n[0])) / 365.0;
          d[i + 1] = Double.parseDouble(n[1]);
        }
        InterpolatedNodalCurve c = InterpolatedNodalCurve.builder()
            .metadata(Curves.discountFactors(CurveName.of("C"), DayCounts.ACT_365F))
            .xValues(DoubleArray.copyOf(t)).yValues(DoubleArray.copyOf(d))
            .interpolator(CurveInterpolators.LOG_LINEAR)
            .extrapolatorLeft(CurveExtrapolators.LOG_LINEAR).extrapolatorRight(CurveExtrapolators.LOG_LINEAR).build();
        ImmutableRatesProvider rp = ImmutableRatesProvider.builder(val).discountCurve(ccy, c)
            .overnightIndexCurve(sonia ? OvernightIndices.GBP_SONIA : OvernightIndices.USD_SOFR, c).build();
        BuySell side = f[6].equals("PAY") ? BuySell.BUY : BuySell.SELL;
        var conv = sonia ? FixedOvernightSwapConventions.GBP_FIXED_1Y_SONIA_OIS : FixedOvernightSwapConventions.USD_FIXED_1Y_SOFR_OIS;
        ResolvedSwapTrade tr = conv.createTrade(val, Tenor.parse(f[3]), side, Double.parseDouble(f[5]), Double.parseDouble(f[4]), ref).resolve(ref);
        double pv = DiscountingSwapTradePricer.DEFAULT.presentValue(tr, rp).getAmount(ccy).getAmount();
        out.add(String.join("\t", f[0], f[1], f[2], f[3], f[4], f[5], f[6]) + "\t" + pv);
      }
    }
    Files.write(Path.of(args[1]), out);
  }
}
