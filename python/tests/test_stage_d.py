"""Stage D wave 1 checks that the golden suites do not make on their own."""
import itertools
import json
import math
from datetime import date, timedelta
from typing import Any

import pytest

from quantforge_core import calendars, csa, curve_fits, curves, futures, ois, overnight, steps
from quantforge_core.cli.main import run_case
from quantforge_core.curves import CurveData
from quantforge_core.errors import QfError
from quantforge_core.ois import Quote
from quantforge_core.projection import ProjectionQuote

AS_OF = date(2026, 11, 6)
SOFR = [Quote(t, r) for t, r in (("1M", 0.0386), ("3M", 0.0383), ("1Y", 0.0365), ("5Y", 0.035))]


def _run(operation, inputs):
    document = {"schema_version": "1.0", "case_id": "t", "operation": operation,
                "inputs": inputs}
    out = run_case(json.dumps(document))
    return out if isinstance(out, dict) else json.loads(out)


def _code(operation, inputs):
    out = _run(operation, inputs)
    return out.get("error", {}).get("code") if out.get("status") == "error" else "ok"


def _code_of(f, *args):
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code


def _flat(rate=0.03, jumps=()):
    ds = (date(2027, 11, 8), date(2031, 11, 6))
    return CurveData(AS_OF, "LOG_LINEAR_DF", ds,
                     tuple(math.exp(-rate * (d - AS_OF).days / 365) for d in ds), jumps)


def _fixings(cal, start, end, rate=0.04):
    d, out = start - timedelta(days=10), []
    while d <= end:
        if calendars.is_business_day(cal, d):
            out.append((d, rate + (d.toordinal() % 7) * 1e-4))
        d += timedelta(days=1)
    return out


# Jumps on the curve object

def test_jump_applies_strictly_after_its_date_and_survives_interpolation() -> None:
    jd = date(2026, 12, 31)
    jumped = curves.build(_flat(jumps=((jd, 0.999),)))
    assert jumped.discount(jd) == jumped._smooth(jd)
    after = jd + timedelta(days=1)
    assert jumped.discount(after) == pytest.approx(jumped._smooth(after) * 0.999, rel=1e-15)
    # Pillars hold the full D: a pillar repricing is exact.
    assert jumped.discount(date(2031, 11, 6)) == pytest.approx(_flat().discount_factors[1])


@pytest.mark.parametrize("jumps,code", [
    (((AS_OF, 0.99),), "E_INPUT"),
    (((date(2027, 1, 5), 0.99), (date(2027, 1, 4), 0.99)), "E_INPUT"),
    (((date(2027, 1, 5), 0.0),), "E_DOMAIN"),
])
def test_bad_jumps(jumps, code) -> None:
    assert _code_of(curves.build, _flat(jumps=jumps)) == code


def test_null_jumps_is_schema_error_and_absent_is_none() -> None:
    curve = {"as_of": "2026-11-06", "interpolation": "LOG_LINEAR_DF",
             "pillars": [{"date": "2027-11-08", "discount_factor": 0.97}]}
    assert _code("rates.curve.discount", {"curve": curve, "dates": ["2027-01-01"]}) == "ok"
    assert _code("rates.curve.discount", {"curve": {**curve, "jumps": None},
                                          "dates": ["2027-01-01"]}) == "E_SCHEMA"


@pytest.mark.parametrize("method", ["SEQUENTIAL", "GLOBAL"])
def test_estr_bootstrap_with_jump_reprices(method) -> None:
    jumps = ((date(2026, 12, 31), math.exp(-0.002 / 365)),)
    data, error = ois.bootstrap("ESTR", AS_OF, SOFR, "LOG_LINEAR_DF", method, jumps)
    assert error < 1e-13 and data.jumps == jumps
    curve = curves.build(data)
    for q in SOFR:
        assert ois.par_rate("ESTR", ois.periods("ESTR", AS_OF, q.tenor), curve) == \
            pytest.approx(q.rate, abs=1e-13)


def test_bootstrap_checks_jumps_before_quotes() -> None:
    assert _code_of(ois.bootstrap, "SOFR", AS_OF, [], "LOG_LINEAR_DF", "SEQUENTIAL",
                    ((AS_OF, 1.0),)) == "E_INPUT"
    assert _code_of(ois.bootstrap, "SOFR", AS_OF, [], "LOG_LINEAR_DF", "SEQUENTIAL",
                    ((date(2027, 1, 1), -1.0),)) == "E_DOMAIN"


# Dated compounding and fallbacks

S, E = date(2026, 11, 10), date(2027, 2, 10)


def test_none_matches_plain_compounding_by_hand() -> None:
    fx = _fixings("USGS", S, E)
    rate, accrual, interest = overnight.compound_dated("SOFR", S, E, "NONE", 0, fx)
    table = dict(fx)
    days = [d for d, _ in fx if S <= d <= E]
    growth = math.prod(1 + table[a] * (b - a).days / 360 for a, b in itertools.pairwise(days))
    assert rate == pytest.approx((growth - 1) * 360 / (E - S).days, abs=1e-15)
    assert accrual == (E - S).days / 360 and interest == pytest.approx(rate * accrual)


def test_flat_fixings_give_same_rate_for_every_method() -> None:
    fx = [(d, 0.04) for d, _ in _fixings("USGS", S, E)]
    rates = {m: overnight.compound_dated("SOFR", S, E, m, k, fx)[0]
             for m, k in (("NONE", 0), ("LOOKBACK", 2), ("LOCKOUT", 2))}
    assert max(rates.values()) - min(rates.values()) < 1e-15


def test_lockout_uses_cutoff_fixing_to_the_end() -> None:
    fx = _fixings("USGS", S, E)
    days = [d for d, _ in fx if S <= d <= E]
    # Lockout 1 locks only the last step onto d_{n-1}: the same as NONE.
    assert overnight.compound_dated("SOFR", S, E, "LOCKOUT", 1, fx)[0] == pytest.approx(
        overnight.compound_dated("SOFR", S, E, "NONE", 0, fx)[0], abs=1e-16)
    # Only fixings up to the cut-off d_{n-2} are needed with k = 2.
    needed = [(d, r) for d, r in fx if d <= days[-3]]
    overnight.compound_dated("SOFR", S, E, "LOCKOUT", 2, needed)


@pytest.mark.parametrize("args,code", [
    (("USD-TERM-3M", S, E, "NONE", 0), "E_INPUT"),
    (("SOFR", E, S, "NONE", 0), "E_DATE_ORDER"),
    (("SOFR", S, S, "NONE", 0), "E_DATE_ORDER"),
    (("SOFR", S, E, "LOOKBACK", -1), "E_INPUT"),
    (("SOFR", S, E, "NONE", 1), "E_INPUT"),
    (("SOFR", S, E, "LOCKOUT", 0), "E_INPUT"),
    (("SOFR", S, E, "LOCKOUT", 500), "E_INPUT"),
    (("SOFR", date(2026, 11, 7), E, "NONE", 0), "E_INPUT"),
])
def test_compound_dated_checks(args, code) -> None:
    assert _code_of(overnight.compound_dated, *args, _fixings("USGS", S, E)) == code


def test_duplicate_and_missing_fixings() -> None:
    fx = _fixings("USGS", S, E)
    assert _code_of(overnight.compound_dated, "SOFR", S, E, "NONE", 0, [*fx, fx[-1]]) == "E_INPUT"
    assert _code_of(overnight.compound_dated, "SOFR", S, E, "NONE", 0, fx[:-20]) == "E_INPUT"


def test_fallback_adds_spread_to_shifted_compounding() -> None:
    fx = _fixings("GBLO", S, E)
    rate, spread, total = overnight.fallback("GBP-LIBOR-3M", S, E, fx)
    assert rate == overnight.compound_dated("SONIA", S, E, "OBSERVATION_SHIFT", 2, fx)[0]
    assert spread == 0.0011930 and total == rate + spread
    assert _code("rates.fallback.rate", {"ibor": "EUR-LIBOR-3M", "start": "2026-11-10",
                                         "end": "2027-02-10", "fixings": []}) == "E_SCHEMA"


# Steps

STEPS = [(date(2026, 12, 10), 0.04), (date(2027, 1, 28), 0.038)]


def test_step_takes_effect_on_its_date() -> None:
    factors, forwards = steps.step_curve(AS_OF, 0.0425, STEPS, (),
                                         [AS_OF, date(2026, 12, 9), date(2026, 12, 10)])
    assert factors[0] == 1.0 and forwards == [0.0425, 0.0425, 0.04]
    assert factors[2] == pytest.approx(math.exp(-0.0425 * 34 / 365), rel=1e-15)


def test_step_curve_checks() -> None:
    assert _code_of(steps.step_curve, AS_OF, 0.04, [(AS_OF, 0.03)], (), [AS_OF]) == "E_INPUT"
    assert _code_of(steps.step_curve, AS_OF, 0.04, STEPS[::-1], (), [AS_OF]) == "E_INPUT"
    assert _code_of(steps.step_curve, AS_OF, 0.04, STEPS, ((AS_OF, 1.0),), [AS_OF]) == "E_INPUT"
    assert _code_of(steps.step_curve, AS_OF, 0.04, STEPS, (),
                    [AS_OF - timedelta(days=1)]) == "E_OUT_OF_RANGE"


def test_fit_steps_recovers_truth_with_jump() -> None:
    jumps = ((date(2026, 12, 31), 0.9999),)
    truth = steps.StepCurve(AS_OF, 0.0425, STEPS, jumps)
    quotes = [Quote(t, ois.par_rate("SOFR", ois.periods("SOFR", AS_OF, t), truth))
              for t in ("3W", "2M", "6M")]
    base, rates, error = steps.fit_steps("SOFR", AS_OF, [d for d, _ in STEPS], quotes, jumps)
    assert base == pytest.approx(0.0425, abs=1e-12) and error < 1e-13
    assert rates == pytest.approx([0.04, 0.038], abs=1e-12)


def test_fit_steps_checks() -> None:
    dates = [d for d, _ in STEPS]
    q = [Quote("3W", 0.04), Quote("2M", 0.04), Quote("6M", 0.04)]
    assert _code_of(steps.fit_steps, "SOFR", AS_OF, dates, q[:2], ()) == "E_INPUT"
    assert _code_of(steps.fit_steps, "SOFR", AS_OF, dates[::-1], q, ()) == "E_INPUT"
    bad = [Quote("2M", 0.04), Quote("3M", 0.04), Quote("6M", 0.04)]
    assert _code_of(steps.fit_steps, "SOFR", AS_OF, dates, bad, ()) == "E_INPUT"
    assert _code_of(steps.fit_steps, "SOFR", AS_OF, dates, q, ((AS_OF, 1.0),)) == "E_INPUT"


def test_step_ops_require_jumps_key() -> None:
    inputs = {"as_of": "2026-11-06", "base_rate": 0.04, "steps": [], "dates": ["2026-11-06"]}
    assert _code("rates.ois.step_curve", inputs) == "E_SCHEMA"
    assert _code("rates.ois.step_curve", {**inputs, "jumps": []}) == "ok"


# Futures

def test_convexity_zero_mean_reversion_limit_is_continuous() -> None:
    at_zero = futures.convexity(96, 1, 1.25, 0.01, 0)
    near = futures.convexity(96, 1, 1.25, 0.01, 1e-9)
    assert at_zero[0] == pytest.approx(0.04) and at_zero[1] == pytest.approx(near[1], rel=1e-7)
    assert at_zero[2] == at_zero[0] - at_zero[1]


@pytest.mark.parametrize("args,code", [
    ((96, 1, 1, 0.01, 0.03), "E_INPUT"), ((96, -1, 1, 0.01, 0.03), "E_DOMAIN"),
    ((96, 0, 1, -0.01, 0.03), "E_DOMAIN"), ((96, 0, 1, 0.01, -0.03), "E_DOMAIN"),
])
def test_convexity_checks(args, code) -> None:
    assert _code_of(futures.convexity, *args) == code


# CSA and basis

def test_csa_discount_spread_and_fx() -> None:
    d = date(2028, 1, 3)
    base = curves.build(_flat()).discount(d)
    t = (d - AS_OF).days / 365
    assert csa.discount(_flat(), 0.001, None, [d])[0] == pytest.approx(base * math.exp(-0.001 * t))
    got = csa.discount(_flat(), 0.0, (1.1, [(d, 1.12)]), [d])[0]
    assert got == pytest.approx(base * 1.1 / 1.12)


@pytest.mark.parametrize("fx,dates,code", [
    ((0.0, []), [AS_OF], "E_DOMAIN"),
    ((1.1, [(AS_OF, -1.0)]), [AS_OF], "E_DOMAIN"),
    ((1.1, []), [AS_OF], "E_INPUT"),
    (None, [AS_OF - timedelta(days=1)], "E_OUT_OF_RANGE"),
])
def test_csa_checks(fx, dates, code) -> None:
    assert _code_of(csa.discount, _flat(), 0.0, fx, dates) == code


def test_csa_requires_fx_key() -> None:
    curve = {"as_of": "2026-11-06", "interpolation": "LOG_LINEAR_DF",
             "pillars": [{"date": "2027-11-08", "discount_factor": 0.97}]}
    inputs = {"curve": curve, "collateral_spread": 0.0, "dates": ["2027-01-01"]}
    assert _code("rates.csa.discount", inputs) == "E_SCHEMA"
    assert _code("rates.csa.discount", {**inputs, "fx": None}) == "ok"


def test_ois_spread_is_fair_rate_difference_and_checks_as_of() -> None:
    a, b, d = _flat(0.035), _flat(0.03), _flat(0.03)
    ps = ois.periods("SOFR", AS_OF, "2Y")
    # With the discount curve equal to B, leg B's fair rate is B's own par rate.
    expected = ois.par_rate("SOFR", ps, curves.build(a)) - ois.par_rate("SOFR", ps, curves.build(b))
    spread = csa.ois_spread("SOFR", "2Y", d, a, b)
    assert spread > 0 and csa.ois_spread("SOFR", "2Y", d, b, b) == 0.0
    assert abs(spread - expected) < 1e-4
    other = CurveData(date(2026, 11, 5), "LOG_LINEAR_DF", a.dates, a.discount_factors)
    assert _code_of(csa.ois_spread, "SOFR", "2Y", d, a, other) == "E_INPUT"


def test_joint_bootstrap_matches_two_step_and_checks_lists() -> None:
    term = [ProjectionQuote("DEPOSIT", 3, 0.0395), ProjectionQuote("SWAP", 24, 0.037)]
    seq = csa.joint_bootstrap("SOFR", "USD-TERM-3M", AS_OF, SOFR, term, "LOG_LINEAR_DF",
                              "SEQUENTIAL")
    glo = csa.joint_bootstrap("SOFR", "USD-TERM-3M", AS_OF, SOFR, term, "LOG_LINEAR_DF", "GLOBAL")
    assert seq[2] < 1e-13 and glo[2] < 1e-13
    assert seq[1].discount_factors == pytest.approx(glo[1].discount_factors, abs=1e-12)
    args: tuple[Any, Any]
    for args in ((SOFR, []), ([], term)):
        assert _code_of(csa.joint_bootstrap, "SOFR", "USD-TERM-3M", AS_OF, *args,
                        "LOG_LINEAR_DF", "SEQUENTIAL") == "E_INPUT"


# Fits

def test_smooth_exact_fit_at_zero_lambda_and_flat_at_large_lambda() -> None:
    f, _, obj = curve_fits.smooth([1, 2], [1, 2], [0.03, 0.04], 0.0)
    assert f == pytest.approx([0.03, 0.05]) and obj == pytest.approx(0, abs=1e-20)
    f, _, _ = curve_fits.smooth([1, 2], [1, 2], [0.03, 0.04], 1e9)
    assert f[0] == pytest.approx(f[1], abs=1e-9)


@pytest.mark.parametrize("args,code", [
    (([1], [1], [0.03, 0.04], 0.0), "E_INPUT"),
    (([1], [], [], 0.0), "E_INPUT"),
    (([2, 1], [1], [0.03], 0.0), "E_INPUT"),
    (([0, 1], [1], [0.03], 0.0), "E_INPUT"),
    (([1], [1], [0.03], -1.0), "E_DOMAIN"),
    (([1], [0], [0.03], 0.0), "E_DOMAIN"),
    (([1], [2], [0.03], 0.0), "E_INPUT"),
    (([1, 2], [0.5], [0.03], 0.0), "E_SINGULAR"),
])
def test_smooth_checks(args, code) -> None:
    assert _code_of(curve_fits.smooth, *args) == code


def test_smooth_weight_checks() -> None:
    assert _code_of(curve_fits.smooth, [1], [1], [0.03], 0.0, [1.0, 1.0]) == "E_INPUT"
    assert _code_of(curve_fits.smooth, [1], [1], [0.03], 0.0, [-1.0]) == "E_DOMAIN"


def test_robust_without_outliers_is_least_squares_and_flags_one() -> None:
    ms = [0.5, 1, 2, 3, 5, 7, 10, 20]
    truth = [0.04, -0.01, 0.005]
    ys = [sum(b * x for b, x in zip(truth, curve_fits._basis(m, 2.0))) for m in ms]
    betas, res, out, obj = curve_fits.robust(ms, ys, 2.0, 1e-3)
    assert betas == pytest.approx(truth, abs=1e-12) and out == [] and obj < 1e-25
    ys[3] += 0.01
    betas, res, out, _ = curve_fits.robust(ms, ys, 2.0, 1e-3)
    assert out == [3]
    # First-order condition of the Huber objective.
    xs = [curve_fits._basis(m, 2.0) for m in ms]
    for p in range(3):
        g = sum((r if abs(r) <= 1e-3 else 1e-3 * math.copysign(1, r)) * x[p]
                for r, x in zip(res, xs))
        assert abs(g) < 1e-14


@pytest.mark.parametrize("args,code", [
    (([1, 2], [0.03, 0.03], 1.0, 1e-3), "E_INPUT"),
    (([1, 2, 3], [0.03, 0.03], 1.0, 1e-3), "E_INPUT"),
    (([1, 2, 3], [0.03] * 3, 0.0, 1e-3), "E_DOMAIN"),
    (([1, 2, 3], [0.03] * 3, 1.0, 0.0), "E_DOMAIN"),
    (([0, 2, 3], [0.03] * 3, 1.0, 1e-3), "E_DOMAIN"),
])
def test_robust_checks(args, code) -> None:
    assert _code_of(curve_fits.robust, *args) == code


def test_fits_weights_null_is_schema() -> None:
    inputs = {"knots": [1], "maturities": [1], "zero_rates": [0.03], "lambda": 0.0}
    assert _code("calib.curve.smooth", inputs) == "ok"
    assert _code("calib.curve.smooth", {**inputs, "weights": None}) == "E_SCHEMA"
