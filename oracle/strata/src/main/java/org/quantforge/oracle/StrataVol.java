package org.quantforge.oracle;

import com.opengamma.strata.pricer.impl.option.BlackFormulaRepository;
import com.opengamma.strata.pricer.impl.option.NormalFormulaRepository;
import com.opengamma.strata.pricer.impl.volatility.smile.SabrHaganVolatilityFunctionProvider;
import com.opengamma.strata.product.common.PutCall;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * Oracle only. Line kinds, tab separated, results undiscounted:
 * BLACK CALL|PUT F K vol T -> price delta gamma vega vanna volga implied.
 * NORMAL CALL|PUT F K vol T -> price.
 * SABR f k T alpha beta rho nu -> vol.
 */
public final class StrataVol {
  public static void main(String[] args) throws IOException {
    List<String> out = new ArrayList<>();
    for (String line : Files.readAllLines(Path.of(args[0]))) {
      String[] p = line.split("\t");
      if (p[0].equals("SABR")) {
        double v = SabrHaganVolatilityFunctionProvider.DEFAULT.volatility(d(p[1]), d(p[2]), d(p[3]), d(p[4]), d(p[5]), d(p[6]), d(p[7]));
        out.add(line + "\t" + v);
        continue;
      }
      boolean call = p[1].equals("CALL");
      double f = d(p[2]), k = d(p[3]), v = d(p[4]), t = d(p[5]);
      if (p[0].equals("NORMAL")) {
        out.add(line + "\t" + NormalFormulaRepository.price(f, k, t, v, call ? PutCall.CALL : PutCall.PUT));
        continue;
      }
      double price = BlackFormulaRepository.price(f, k, t, v, call);
      out.add(String.join("\t", line, s(price), s(BlackFormulaRepository.delta(f, k, t, v, call)), s(BlackFormulaRepository.gamma(f, k, t, v)),
          s(BlackFormulaRepository.vega(f, k, t, v)), s(BlackFormulaRepository.vanna(f, k, t, v)), s(BlackFormulaRepository.volga(f, k, t, v)),
          s(BlackFormulaRepository.impliedVolatility(price, f, k, t, call))));
    }
    Files.write(Path.of(args[1]), out);
  }

  private static double d(String x) {
    return Double.parseDouble(x);
  }

  private static String s(double x) {
    return Double.toString(x);
  }
}
