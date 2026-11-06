package org.quantforge.core;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Rate units and exact decimal money (units-and-money.md). */
public final class Money {
    private Money() {}

    public enum RateUnit {
        DECIMAL(1.0), PERCENT(100.0), BP(10_000.0);

        final double perUnit;

        RateUnit(double perUnit) {
            this.perUnit = perUnit;
        }
    }

    public record Amount(BigDecimal value, String currency) {}

    private static final Map<String, Integer> MINOR_UNITS = Map.of("GBP", 2, "USD", 2, "EUR", 2, "JPY", 0);
    private static final Pattern FORM = Pattern.compile("-?([0-9]+)(\\.([0-9]+))?");

    public static double convert(double value, RateUnit from, RateUnit to) {
        return from == to ? value : value / from.perUnit * to.perUnit;
    }

    public static void checkCurrency(String currency) {
        if (!MINOR_UNITS.containsKey(currency)) {
            throw new QfError("E_SCHEMA", "unknown currency " + currency, "currency");
        }
    }

    /** E_SCHEMA on any other form. */
    public static void checkForm(String text) {
        if (!FORM.matcher(text).matches()) {
            throw new QfError("E_SCHEMA", "bad amount " + text, "amount");
        }
    }

    /** True if an amount of the right form has more digits than the limit allows. */
    public static boolean overDigits(String text) {
        Matcher m = FORM.matcher(text);
        return m.matches() && (m.group(1).length() > 18 || (m.group(3) != null && m.group(3).length() > 8));
    }

    public static String add(Amount a, Amount b) {
        if (!a.currency().equals(b.currency())) {
            throw new QfError("E_CURRENCY_MISMATCH", a.currency() + " and " + b.currency());
        }
        return a.value().add(b.value()).stripTrailingZeros().toPlainString();
    }

    public static String round(Amount a) {
        return a.value().setScale(MINOR_UNITS.get(a.currency()), RoundingMode.HALF_EVEN).toPlainString();
    }
}
