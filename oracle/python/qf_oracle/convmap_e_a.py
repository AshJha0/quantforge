"""Convention mapping table for stage E spec A outside-oracle checks (plan rule 11.2.5).

Same rule as qf_oracle/convmap.py (stage D), kept in its own file so the two stage E spec sessions never
edit one generated file. `outside_e_a.py` takes every QuantLib convention object from here; the reviewed
human-readable copy is `oracle/CONVENTION_MAP_E_A.md`, written by `outside_e_a.py --write-map`.

Review state "self-reviewed 2026-11-08": the spec session read the spec section and the QuantLib 1.44
source or documentation for the object and found them equal. It is not an outside review.
"""
import QuantLib as ql

LIBRARY = "QuantLib"
VERSION = ql.__version__
REVIEW = "self-reviewed 2026-11-08"

# id: (spec reference, library object factory, note)
ROWS = {
    # E1
    "SVI.RAW": ("05-volatility/arb-free-surfaces.md raw SVI w(k) = a + b(rho(k-m) + sqrt((k-m)^2 + sigma^2)), k = ln(K/F)",
                lambda T, F, p: ql.SviSmileSection(T, F, [p["a"], p["b"], p["sigma"], p["rho"], p["m"]]),
                "QuantLib parameter order is (a, b, sigma, rho, m); variance(K) is total variance w at k = ln(K/F)"),
    "SVI.DENSITY": ("05-volatility/arb-free-surfaces.md butterfly: g(k) < 0 iff the risk-neutral density is negative",
                    lambda sec, K: sec.density(K, 1.0, 1e-4),
                    "SmileSection::density: second difference of undiscounted calls in strike, gap 1e-4; only its sign is used, on cases guarded |g| > 1e-6 and away from the far tail"),
    "VOL.CURVE": ("05-volatility/local-and-forward-vol.md forward vol: total variance linear between expiries, time ACT/365F days/365",
                  lambda ref, dates, vols: ql.BlackVarianceCurve(ref, dates, vols, ql.Actual365Fixed(), False),
                  "forceMonotoneVariance off, so QuantLib does not hide a calendar break"),
    "DC.ACT_365F": ("01-core/daycount.md ACT_365F", lambda: ql.Actual365Fixed(), ""),
    "OPT.BLACK_FORMULA": ("05-volatility/black-models.md Black-76 on the forward F = S exp((r-q)T), discount exp(-rT)",
                          lambda ot, K, F, sd, D: ql.blackFormula(ql.Option.Call if ot == "CALL" else ql.Option.Put, K, F, sd, D), ""),
    "OPT.BLACK_CALC": ("05-volatility/local-and-forward-vol.md smile dynamics: spot delta and vega of Black-Scholes with dividend yield",
                       lambda ot, K, F, sd, D: ql.BlackCalculator(ql.PlainVanillaPayoff(ql.Option.Call if ot == "CALL" else ql.Option.Put, K), F, sd, D),
                       "delta(spot) is dV/dS at fixed vol; vega(T) per unit vol"),
    "STAT.SAMPLE": ("05-volatility/local-and-forward-vol.md vol of vol: sample standard deviation, divisor n-1",
                    lambda: ql.IncrementalStatistics(), "standardDeviation uses n-1"),
}


def obj(row, *args):
    """The library object for a row. Raises KeyError for an unmapped row, so no mapping can be inline."""
    return ROWS[row][1](*args)
