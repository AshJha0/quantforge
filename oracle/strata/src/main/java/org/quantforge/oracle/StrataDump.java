package org.quantforge.oracle;

import com.opengamma.strata.basics.ReferenceData;
import com.opengamma.strata.basics.date.DayCount;
import com.opengamma.strata.basics.date.DayCount.ScheduleInfo;
import com.opengamma.strata.basics.date.HolidayCalendar;
import com.opengamma.strata.basics.date.HolidayCalendarId;
import com.opengamma.strata.basics.schedule.Frequency;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

/**
 * Oracle only. Reads day-count requests as tab-separated lines
 * (strata_name, start, end, period_end_or_dash, frequency_months, eom, maturity_or_dash)
 * and writes the same lines with the Strata year fraction appended. Also dumps holidays.
 */
public final class StrataDump {
  record Info(LocalDate periodEnd, int months, boolean eom, LocalDate maturity) implements ScheduleInfo {
    @Override public LocalDate getStartDate() { throw new UnsupportedOperationException(); }
    @Override public LocalDate getEndDate() { return maturity; }
    @Override public LocalDate getPeriodEndDate(LocalDate date) { return periodEnd; }
    @Override public Frequency getFrequency() { return Frequency.ofMonths(months); }
    @Override public boolean isEndOfMonthConvention() { return eom; }
  }

  public static void main(String[] args) throws IOException {
    Path in = Path.of(args[0]);
    Path out = Path.of(args[1]);
    List<String> rows = new ArrayList<>();
    for (String line : Files.readAllLines(in)) {
      String[] f = line.split("\t");
      LocalDate s = LocalDate.parse(f[1]);
      LocalDate e = LocalDate.parse(f[2]);
      LocalDate pe = f[3].equals("-") ? e : LocalDate.parse(f[3]);
      LocalDate mat = f[6].equals("-") ? e : LocalDate.parse(f[6]);
      Info info = new Info(pe, Integer.parseInt(f[4]), f[5].equals("1"), mat);
      double v = DayCount.of(f[0]).yearFraction(s, e, info);
      rows.add(line + "\t" + v);
    }
    Files.write(out.resolve("daycount.tsv"), rows);
    ReferenceData ref = ReferenceData.standard();
    for (String id : List.of("GBLO", "USGS", "EUTA")) {
      HolidayCalendar cal = HolidayCalendarId.of(id).resolve(ref);
      List<String> hol = new ArrayList<>();
      for (LocalDate d = LocalDate.of(2000, 1, 1); d.getYear() <= 2050; d = d.plusDays(1)) {
        if (d.getDayOfWeek().getValue() < 6 && cal.isHoliday(d)) {
          hol.add(d.toString());
        }
      }
      Files.write(out.resolve("holidays-" + id + ".txt"), hol);
    }
  }
}
