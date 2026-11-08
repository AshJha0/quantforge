"""Convention map rows for the stage E spec B outside-oracle checks (plan rule 11.2.5).

Kept apart from `convmap.py` so the two stage E spec sessions do not edit one table. Rows here extend the stage D table;
`outside_e_b.py` takes every library convention from `ROWS` below (base rows included), never inline. Human-readable copy:
`oracle/CONVENTION_MAP_E_B.md`, written by `outside_e_b.py --write-map`.
"""
import QuantLib as ql

from qf_oracle import convmap as base

LIBRARY = base.LIBRARY
VERSION = base.VERSION
REVIEW = "self-reviewed 2026-11-08"

NEW = {
    # E7 variance swaps
    "VS.DDKZ_SPOT": ("05-volatility/variance-swaps.md replication: DDKZ weights, reference S* = spot, puts walked down, calls up, one extension strike",
                     lambda proc, dk, calls, puts: ql.ReplicatingVarianceSwapEngine(proc, dk, calls, puts),
                     "QuantLib's drift term is 2/T (rT - (e^{rT} - 1)); it ignores the dividend yield, so only q = 0 cases are mapped (ruling E-B3)"),
    "VS.INSTRUMENT": ("05-volatility/variance-swaps.md pv = N_var D (K_fair - K_var), long", lambda K, N, a, m: ql.VarianceSwap(ql.Position.Long, K, N, a, m), ""),
    "PROC.BSM": ("05-volatility/variance-swaps.md flat continuous r and q on ACT/365F; Black vol per listed strike",
                 lambda s, q, r, v: ql.BlackScholesMertonProcess(s, q, r, v), ""),
    "CRV.FLAT_CONT_365F": ("05-volatility/variance-swaps.md flat continuously compounded rate, ACT/365F",
                           lambda a, r: ql.YieldTermStructureHandle(ql.FlatForward(a, r, ql.Actual365Fixed(), ql.Continuous)), ""),
    "VOL.STRIKE_TABLE": ("05-volatility/variance-swaps.md vols given at listed strikes only; the engine reads them only there",
                         lambda a, dates, ks, m: ql.BlackVarianceSurface(a, ql.NullCalendar(), dates, ks, m, ql.Actual365Fixed()),
                         "two identical maturity columns so the surface is defined; read only at listed strikes and the maturity"),
    # E4 rates and inflation vol
    "SABR.SECTION": ("05-volatility/rates-vol-cube.md smile: sabr.md Hagan lognormal vol at the swaption's own forward and expiry time",
                     lambda t, F, a, b, r, n: ql.SabrSmileSection(t, F, [a, b, n, r]), "QuantLib parameter order is alpha, beta, nu, rho"),
    "INTERP.BILINEAR": ("05-volatility/rates-vol-cube.md parameters bilinear in (expiry time ACT/365F, tenor years)",
                        lambda xs, ys, M: ql.BilinearInterpolation(xs, ys, M), "QuantLib's matrix is indexed [y][x]"),
    "SWO.BLACK_ENGINE": ("05-volatility/caps-and-swaptions.md swaption, Black on the forward swap rate, time ACT/365F",
                         lambda h, v: ql.BlackSwaptionEngine(h, ql.QuoteHandle(ql.SimpleQuote(v)), ql.Actual365Fixed()), ""),
    "OPT.BLACK_FORMULA": ("05-volatility/black-models.md BLACK_76, discounted", lambda: ql.blackFormula, "formula level"),
    "OPT.BACHELIER_FORMULA": ("05-volatility/black-models.md BACHELIER, discounted", lambda: ql.bachelierBlackFormula, "formula level"),
    "OPT.BLACK_IMPLIED": ("05-volatility/rates-vol-cube.md implied Black vol from a premium", lambda: ql.blackFormulaImpliedStdDev, "returns the standard deviation; divided by sqrt(t)"),
}
ROWS = {**base.ROWS, **NEW}


def obj(row, *args):
    return ROWS[row][1](*args)
