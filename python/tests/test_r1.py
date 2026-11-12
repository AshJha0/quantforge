"""R1: batch mode in process (BT1 to BT6, BT5 limit, --timings), and rulings R1-3 and R1-4."""
import io
import json
import sys
from datetime import date
from types import SimpleNamespace

import pytest

from quantforge_core.bonds import Bond, conversion_factor
from quantforge_core.cli import main as cli
from quantforge_core.cli.main import run_case

GOOD = (
    '{"schema_version":"1.0","case_id":"c1","operation":"core.daycount.year_fraction",'
    '"inputs":{"convention":"ACT_360","start":"2024-01-01","end":"2024-07-01"}}'
)


def invoke(monkeypatch: pytest.MonkeyPatch, args, data=b""):
    out = io.BytesIO()
    monkeypatch.setattr(sys, "argv", ["quantforge", *args])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(data)))
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=out))
    code = cli.main()
    text = out.getvalue()
    return code, [json.loads(x) for x in text.splitlines()], text


def test_batch_framing(monkeypatch: pytest.MonkeyPatch) -> None:
    data = (GOOD + "\r\n\n  \n\xef\xbb\xbf{}\n").encode("latin-1") + b"\xff\n" + GOOD.encode()
    code, rows, text = invoke(monkeypatch, ["batch"], data)
    assert code == 0
    assert b"\r" not in text and text.endswith(b"\n") and b"\n\n" not in text
    assert [r["status"] for r in rows] == ["ok", "error", "error", "error", "error", "ok"]
    assert all(r["error"]["code"] == "E_PARSE" for r in rows[1:5])
    assert rows[0]["outputs"] == rows[5]["outputs"]
    assert all("elapsed_ns" not in r["diagnostics"] for r in rows)


def test_empty_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    assert invoke(monkeypatch, ["--batch"], b"")[:2] == (0, [])


def test_long_line_is_limit_and_stream_continues(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "MAX_LINE_BYTES", 10)
    monkeypatch.setattr(cli, "_DRAIN_CHUNK", 3)
    long = b"x" * 40
    exact = b"[" + b" " * 8 + b"]"  # 10 bytes: at the limit, so parsed
    data = long + b"\n" + exact + b"\r\n" + b"y" * 11 + b"\r\n" + b"z" * 50
    _, rows, _ = invoke(monkeypatch, ["batch"], data)
    assert [r["error"]["code"] for r in rows] == ["E_LIMIT", "E_SCHEMA", "E_LIMIT", "E_LIMIT"]
    assert all(r["case_id"] == "unknown" for r in rows)


def test_timings(monkeypatch: pytest.MonkeyPatch) -> None:
    _, rows, _ = invoke(monkeypatch, ["--batch", "--timings"], (GOOD + "\nnope\n").encode())
    assert [type(r["diagnostics"]["elapsed_ns"]) for r in rows] == [int, int]
    assert all(r["diagnostics"]["elapsed_ns"] >= 0 for r in rows)
    code, rows, _ = invoke(monkeypatch, ["run", "--timings"], GOOD.encode())
    assert code == 0 and rows[0]["diagnostics"]["elapsed_ns"] >= 0
    plain = invoke(monkeypatch, ["run"], GOOD.encode())[1][0]
    del rows[0]["diagnostics"]["elapsed_ns"]
    assert rows[0] == plain


@pytest.mark.parametrize("args", [
    [], ["--timings", "batch"], ["batch", "--fast"], ["version", "--timings"],
    ["--batch", "--batch"], ["batch", "--timings", "--timings"], ["operations", "x"],
])
def test_bad_arguments(monkeypatch: pytest.MonkeyPatch, args) -> None:
    code, rows, _ = invoke(monkeypatch, args)
    assert code == 64 and rows == []


def test_version_and_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    _, rows, _ = invoke(monkeypatch, ["version"])
    assert rows[0]["language"] == "python" and rows[0]["contract_version"] == "1.11.0"
    _, rows, _ = invoke(monkeypatch, ["operations"])
    assert "bond.futures.conversion_factor" in rows[0] and rows[0] == sorted(rows[0])


def test_run_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    assert invoke(monkeypatch, ["run"], GOOD.encode())[0] == 0
    assert invoke(monkeypatch, ["run"], b"\xff")[0] == 2


def test_internal_fault_is_70(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> None:
        raise RuntimeError("x")
    monkeypatch.setitem(cli.COMMANDS, "version", boom)
    assert invoke(monkeypatch, ["version"])[0] == 70


# R1-3: conversion factor contracts and coupon rounding

def _old_cf(coupon, n, z):
    v = z if z < 7 else 3
    big_c = 1.03 ** (-2 * n) if z < 7 else 1.03 ** (-2 * n - 1)
    return round(1.03 ** (-v / 6) * (coupon / 2 + (coupon / 0.06) * (1 - big_c) + big_c)
                 - (coupon / 2) * (6 - v) / 6, 4)


def test_conversion_factor_contracts() -> None:
    bond = Bond(date(2034, 2, 15), 0.04, 2)  # from 2026-03-01: n = 7, z = 11
    ten = conversion_factor(bond, 2026, 3, 0.06)
    assert ten == conversion_factor(bond, 2026, 3, 0.06, "BOND") == _old_cf(0.04, 7, 9)
    five = conversion_factor(bond, 2026, 3, 0.06, "FIVE_YEAR")
    v, big_c = 5, 1.03 ** -15
    expected = round(1.03 ** (-v / 6) * (0.02 + (0.04 / 0.06) * (1 - big_c) + big_c)
                     - 0.02 * (6 - v) / 6, 4)
    assert five == expected and five != ten


def test_conversion_factor_coupon_rounds_to_eighth() -> None:
    on_grid = conversion_factor(Bond(date(2034, 2, 15), 0.04, 2), 2026, 3, 0.06)
    assert conversion_factor(Bond(date(2034, 2, 15), 0.0406, 2), 2026, 3, 0.06) == on_grid
    up = conversion_factor(Bond(date(2034, 2, 15), 0.04125, 2), 2026, 3, 0.06)
    assert conversion_factor(Bond(date(2034, 2, 15), 0.0410, 2), 2026, 3, 0.06) == up


def _cf_case(contract):
    inputs = {"bond": {"maturity": "2034-02-15", "coupon": 0.04, "frequency": 2},
              "delivery_month": "2026-03", "notional_coupon": 0.06, "contract": contract}
    return run_case(json.dumps({"schema_version": "1.0", "case_id": "c",
                                "operation": "bond.futures.conversion_factor",
                                "inputs": inputs}))


def test_conversion_factor_contract_input() -> None:
    assert _cf_case(None)["outputs"] == _cf_case("TEN_YEAR")["outputs"]
    assert _cf_case("ULTRA_BOND")["status"] == "ok"
    assert _cf_case("THIRTY_YEAR")["error"]["code"] == "E_SCHEMA"
    assert _cf_case(5)["error"]["code"] == "E_SCHEMA"


# R1-4: credit discounting must be LOG_LINEAR_DF, before every other rule check

def _bootstrap(interpolation, recovery):
    inputs = {
        "trade_date": "2026-01-02", "recovery": recovery,
        "discount": {"as_of": "2026-01-02", "interpolation": interpolation,
                     "pillars": [{"date": "2031-01-02", "discount_factor": 0.85}]},
        "quotes": [{"tenor": "5Y", "spread": 0.01}],
    }
    return run_case(json.dumps({"schema_version": "1.0", "case_id": "c",
                                "operation": "credit.cds.bootstrap", "inputs": inputs}))


def test_credit_needs_log_linear_df() -> None:
    assert _bootstrap("LOG_LINEAR_DF", 0.4)["status"] == "ok"
    bad = _bootstrap("LINEAR_ZERO", 0.4)["error"]
    assert bad["code"] == "E_INPUT" and bad["field"] == "discount.interpolation"
    # recovery 1.5 breaks a rule too, but the interpolation check comes first
    assert _bootstrap("LINEAR_ZERO", 1.5)["error"]["field"] == "discount.interpolation"


# Coverage of guard clauses in stage C and D core modules

def _code(f, *args):
    from quantforge_core.errors import QfError
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code, e.value.field


def test_xccy_modified_following_rolls_back_at_month_end() -> None:
    from quantforge_core.xccy import _mod_following
    # 2025-05-31 is a Saturday; following would leave May, so it rolls back to Friday
    assert _mod_following(["EUTA"], date(2025, 5, 31)) == date(2025, 5, 30)
    assert _mod_following(["EUTA", "USGS"], date(2025, 3, 1)) == date(2025, 3, 3)


def test_spread_cost_guards() -> None:
    from quantforge_core.hedging import spread_cost
    assert spread_cost([2.0, -3.0], [0.5, 0.25]) == 1.75
    assert _code(spread_cost, [1.0], [0.1, 0.2])[0] == "E_INPUT"
    assert _code(spread_cost, [1.0], [-0.1]) == ("E_DOMAIN", "half_spreads")


def test_vol_surface_guards() -> None:
    from quantforge_core.curves import CurveData
    from quantforge_core.vol_usecase import vol_surface
    curve = CurveData(date(2026, 1, 2), "LOG_LINEAR_DF", (date(2027, 1, 2),), (0.97,))
    target = ("CALL", 100.0, date(2026, 6, 1), 1.0, "LONG")
    assert _code(vol_surface, date(2026, 1, 2), curve, [], [0.0], target)[0] == "E_INPUT"
    q = [object()]
    slices = [(date(2026, 6, 1), q)]
    assert _code(vol_surface, date(2026, 1, 5), curve, slices, [0.0], target)[1] == "as_of"
    unordered = [(date(2026, 9, 1), q), (date(2026, 6, 1), q)]
    assert _code(vol_surface, date(2026, 1, 2), curve, unordered, [0.0], target)[1] == "slices"


# R1-6: USGS Good Friday early closes are business days; SOFR skips every Good Friday

def test_usgs_good_friday_early_close_years() -> None:
    from quantforge_core.calendars import is_business_day
    for d in (date(2007, 4, 6), date(2021, 4, 2), date(2023, 4, 7), date(2026, 4, 3)):
        assert is_business_day("USGS", d)
    for d in (date(2024, 3, 29), date(2027, 3, 26), date(2022, 4, 15)):
        assert not is_business_day("USGS", d)


def test_sofr_skips_good_friday_in_open_years() -> None:
    from quantforge_core.overnight import _back, _business_days
    days = _business_days("USGS", date(2026, 4, 1), date(2026, 4, 7), sofr=True)
    assert date(2026, 4, 3) not in days and len(days) == 4
    assert date(2026, 4, 3) in _business_days("USGS", date(2026, 4, 1), date(2026, 4, 7))
    assert _back("USGS", True, date(2026, 4, 6), 1) == date(2026, 4, 2)
    assert _back("USGS", False, date(2026, 4, 6), 1) == date(2026, 4, 3)
