"""Rulings D31 to D46: one check per changed path."""
import json
import math
from datetime import date

import pytest

from quantforge_core import bonds, credit, curve_fits, inflation, stage_d3, steps, xccy
from quantforge_core.bonds import Bond
from quantforge_core.cli.main import run_case
from quantforge_core.curves import CurveData
from quantforge_core.errors import QfError

AS_OF = date(2026, 11, 6)


def _flat(as_of=AS_OF, rate=0.03):
    ds = (date(2027, 11, 8), date(2031, 11, 6))
    return CurveData(as_of, "LOG_LINEAR_DF", ds,
                     tuple(math.exp(-rate * (d - as_of).days / 365) for d in ds))


def _code_of(f, *args):
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code


def _code(operation, inputs):
    out = run_case(json.dumps({"schema_version": "1.0", "case_id": "t", "operation": operation,
                               "inputs": inputs}))
    out = out if isinstance(out, dict) else json.loads(out)
    return out["error"]["code"] if out.get("status") == "error" else "ok"


def test_d31_empty_steps_flat_and_empty_dates():
    factors, forwards = steps.step_curve(AS_OF, 0.04, [], (), [date(2027, 11, 6)])
    assert factors[0] == pytest.approx(math.exp(-0.04)) and forwards == [0.04]
    assert _code_of(steps.step_curve, AS_OF, 0.04, [], (), []) == "E_INPUT"


POOL = (1e6, 0.06, 0.055, 60, 0, "PSA", 100.0)


def test_d33_d34_d44_mbs():
    assert _code_of(stage_d3.mbs_cashflows, (*POOL[:3], 1201, *POOL[4:])) == "E_INPUT"
    assert _code_of(stage_d3.mbs_price, POOL, -12.0, 0) == "E_DOMAIN"
    assert _code_of(stage_d3.mbs_cashflows, (1e6, 0.0, 0.06, 60, 0, "PSA", 1.0)) == "E_DOMAIN"


def test_d35_conversion_factor_date_order():
    bond = Bond(date(2026, 11, 15), 0.04, 2)
    assert _code_of(bonds.conversion_factor, bond, 2026, 12, 0.06) == "E_DATE_ORDER"


def test_d36_cds_as_of():
    hz = credit.check_hazard(AS_OF, [date(2031, 12, 20)], [0.9])
    late = credit.check_hazard(date(2026, 11, 5), [date(2031, 12, 20)], [0.9])
    args = (0.4, date(2031, 12, 20), 0.01, 1.0, "BUY_PROTECTION", "STANDARD")
    assert _code_of(credit.price, AS_OF, _flat(), late, *args) == "E_INPUT"
    assert _code_of(credit.price, AS_OF, _flat(date(2026, 11, 5)), hz, *args) == "E_INPUT"
    assert _code_of(credit.index_intrinsic, AS_OF, _flat(), [(late, 0.4, 1.0)],
                    date(2031, 12, 20), 0.01, 0.0) == "E_INPUT"
    assert _code_of(credit.bootstrap, AS_OF, _flat(date(2026, 11, 5)), 0.4,
                    [("1Y", 0.01)]) == "E_INPUT"


def test_d37_weights():
    hz = credit.check_hazard(AS_OF, [date(2031, 12, 20)], [0.9])
    assert _code_of(credit.index_intrinsic, AS_OF, _flat(), [(hz, 0.4, -1.0), (hz, 0.4, 2.0)],
                    date(2031, 12, 20), 0.01, 0.0) == "E_DOMAIN"
    assert _code_of(credit.index_intrinsic, AS_OF, _flat(), [(hz, 0.4, 0.0)],
                    date(2031, 12, 20), 0.01, 0.0) == "E_DOMAIN"
    q = [("1Y", 0.01)]
    assert _code_of(credit.composite, AS_OF, _flat(), 0.4, [(q, 0.0)], 1.0) == "E_DOMAIN"
    bs = [(Bond(date(2028 + k, 11, 15), 0.04, 2), 100.0) for k in range(3)]
    s = date(2026, 11, 9)
    assert _code_of(bonds.fit_nelson_siegel, s, 2.0, bs, [0.0, 0.0, 0.0]) == "E_DOMAIN"
    assert _code_of(bonds.fit_nelson_siegel, s, 2.0, bs, [1.0, 1.0]) == "E_INPUT"


def test_d38_robust_singular():
    assert _code_of(curve_fits.robust, [5.0] * 4, [0.03] * 4, 2.0, 1e-3) == "E_SINGULAR"
    assert _code_of(curve_fits.robust, [1.0, 5.0, 5.0], [0.03] * 3, 2.0, 1e-3) == "E_SINGULAR"


def test_d39_xccy_start_before_as_of():
    early = date(2026, 11, 5)
    assert _code_of(xccy.bootstrap, _flat(), _flat(), "SOFR", "ESTR", early, [(12, 0.0)],
                    "LOG_LINEAR_DF") == "E_OUT_OF_RANGE"
    assert _code_of(xccy.pv, _flat(), _flat(), _flat(), 1.1, early, 12, 1.0, 0.0,
                    "PAY_FOREIGN") == "E_OUT_OF_RANGE"


@pytest.mark.parametrize("tenor", [0, 1201])
def test_d40_tenor_months(tenor):
    assert _code_of(stage_d3.cap_price, _flat(), _flat(), "BLACK_76", 0.2, "CAP", 3, tenor, 0.03,
                    1.0) == "E_INPUT"
    assert _code_of(stage_d3.swaption_price, _flat(), _flat(), "BLACK_76", 0.2, "PAYER", 12,
                    tenor, 0.03, 1.0) == "E_INPUT"


def test_d42_duplicate_cpi_fixings():
    k = inflation.index(2026, 8)
    assert _code_of(inflation.linker_price, Bond(date(2029, 11, 15), 0.04, 2), date(2026, 11, 9),
                    0.02, 300.0, [(k, 300.0), (k, 301.0), (k + 1, 301.0)]) == "E_INPUT"


def test_d45_convention_kinds():
    base = {"as_of": "2026-11-06", "step_dates": [], "quotes": [{"tenor": "1M", "rate": 0.04}],
            "jumps": []}
    assert _code("rates.ois.fit_steps", {**base, "convention": "USD-TERM-3M"}) == "E_INPUT"
    assert _code("rates.ois.fit_steps", {**base, "convention": "TONA"}) == "E_SCHEMA"


# Second pass, D47 to D63

def test_d52_hazard_and_maturity():
    assert _code_of(credit.check_hazard, AS_OF, [date(2027, 1, 1)], [1.01]) == "E_DOMAIN"
    hz = credit.check_hazard(AS_OF, [date(2031, 12, 20)], [0.9])
    assert _code_of(credit.price, AS_OF, _flat(), hz, 0.4, AS_OF, 0.01, 1.0, "BUY_PROTECTION",
                    "STANDARD") == "E_INPUT"
    assert _code_of(credit.index_intrinsic, AS_OF, _flat(), [(hz, 0.4, 1.0)], AS_OF, 0.01,
                    0.0) == "E_INPUT"


def test_d54_years_limit():
    from quantforge_core.inflation import CpiCurveData
    data = CpiCurveData(inflation.index(2026, 8), 300.0, ((101, 0.02),), None)
    assert _code_of(inflation.cpi, data, [data.base]) == "E_INPUT"


def test_d59_xccy_months_limit():
    assert _code_of(xccy.schedule, ("SOFR", "ESTR"), date(2026, 11, 10), 1203) == "E_INPUT"


def test_d55_bachelier_negative_strike():
    caplets, _ = stage_d3.cap_price(_flat(), _flat(), "BACHELIER", 0.01, "CAP", 3, 12, -0.01, 1.0)
    assert all(c > 0 for c in caplets)
