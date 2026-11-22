"""Mutation kills for `quantforge_core.xva_aad` (06-risk/xva-aad-adjustments.md, KR-262 to KR-268).

Self-contained (reads no file), so the mutmut copy of python/ can run it: the 50-digit decimal bump of KR-265 on
seeded random requests that switch every branch (overlap off, linear, floor and the exact kink; im and capital
present or absent; zero hazards and zero profile points), golden values written inline, and the wrt rules with the
field each error names."""

import random
from typing import Any

import pytest
from xva_aad_reference import close, flat, random_request, reference

from quantforge_core import xva_aad
from quantforge_core.errors import QfError
from quantforge_core.xva import Name


def _call(inp: dict[str, Any], wrt: list[str] | None = None) -> dict[str, Any]:
    f = inp["funding"]
    return xva_aad.adjustments_aad(
        inp["times"],
        inp["discount_factors"],
        inp["ee"],
        inp["ene"],
        Name(inp["counterparty"]["hazard_rate"], inp["counterparty"]["recovery"]),
        Name(inp["own"]["hazard_rate"], inp["own"]["recovery"]),
        f["borrow_spread"],
        f["lend_spread"],
        f["exclude_dva_overlap"],
        inp.get("im"),
        inp.get("im_spread"),
        inp.get("capital"),
        inp.get("hurdle_rate"),
        wrt,
    )


def _base() -> dict[str, Any]:
    return {
        "times": [0.5, 1.0, 1.5, 2.0],
        "discount_factors": [0.985, 0.97, 0.955, 0.94],
        "ee": [120.0, 150.0, 130.0, 80.0],
        "ene": [-60.0, -90.0, -100.0, -70.0],
        "counterparty": {"hazard_rate": 0.02, "recovery": 0.4},
        "own": {"hazard_rate": 0.01, "recovery": 0.4},
        "funding": {"borrow_spread": 0.008, "lend_spread": 0.008, "exclude_dva_overlap": False},
    }


def _check(inp: dict[str, Any]) -> None:
    got = flat(_call(inp)["gradient"])
    ref = reference(inp)
    assert set(got) == set(ref)
    bad = [(k, got[k], e) for k, e in ref.items() if not close(got[k], e)]
    assert not bad, bad[:3]


def test_random_requests_against_the_50_digit_bump() -> None:
    rng = random.Random(20261121)
    for _ in range(40):
        _check(random_request(rng))


@pytest.mark.parametrize(
    ("own", "lend"),
    [
        ({"hazard_rate": 0.01, "recovery": 0.4}, 0.008),  # linear branch, 20 bp above the kink
        ({"hazard_rate": 0.01, "recovery": 0.5}, 0.005),  # on the kink: linear (KR-264)
        ({"hazard_rate": 0.02, "recovery": 0.4}, 0.008),  # the floor
    ],
)
def test_overlap_branches_against_the_bump(own: dict[str, float], lend: float) -> None:
    inp = _base()
    inp["own"] = own
    inp["funding"].update(lend_spread=lend, exclude_dva_overlap=True)
    inp["im"], inp["im_spread"] = [200.0, 210.0, 190.0, 150.0], 0.006
    inp["capital"], inp["hurdle_rate"] = [40.0, 42.0, 38.0, 30.0], 0.1
    _check(inp)


def test_golden_one_entries_inline() -> None:
    # aadadj_k-0001 (oracle, 50 digits, rounded once).
    g = _call(_base())["gradient"]
    cva, fva = g["cva"], g["fva"]
    assert close(cva["counterparty.hazard_rate"], 133.0258166316599)
    assert close(cva["counterparty.recovery"], -4.51643629000504)
    assert close(cva["own.hazard_rate"], -1.7909357321811956)
    assert cva["own.hazard_buckets"][3] == 0.0
    assert close(cva["counterparty.hazard_buckets"][1], 41.99803817192667)
    assert close(cva["discount_factors"][0], 0.7164119700599001)
    assert close(fva["funding.borrow_spread"], 226.952805418071)
    assert close(fva["funding.lend_spread"], -150.34122754292395)
    assert close(fva["discount_factors"][0], 0.24)
    assert close(fva["own.hazard_buckets"][0], -0.1882463115005883)
    assert cva["ene"] == [0.0] * 4
    assert list(g) == ["cva", "dva", "fca", "fba", "fva"]


def test_zero_hazard_buckets_are_exact_zeros() -> None:
    inp = _base()
    inp["counterparty"]["hazard_rate"] = 0.0
    inp["ee"] = [1.0e5, 0.0, 3.5e4, 0.0]
    b = _call(inp)["gradient"]["cva"]["counterparty.hazard_buckets"]
    assert b[1] == 0.0 and b[3] == 0.0
    assert b[0] != 0.0 and b[2] != 0.0


def test_wrt_filters_in_canonical_order() -> None:
    inp = _base()
    inp["capital"], inp["hurdle_rate"] = [40.0, 42.0, 38.0, 30.0], 0.1
    out = _call(inp, ["hurdle_rate", "ee", "counterparty.hazard_rate"])
    for row in out["gradient"].values():
        assert list(row) == ["counterparty.hazard_rate", "ee", "hurdle_rate"]
    assert out["kva"] == pytest.approx(out["gradient"]["kva"]["hurdle_rate"] * 0.1, rel=1e-14)


@pytest.mark.parametrize(
    ("wrt", "field"),
    [
        ([], "wrt"),
        (["ee", "ee"], "wrt"),
        (["im"], "wrt"),
        (["capital"], "wrt"),
        (["colour"], "wrt"),
    ],
)
def test_wrt_errors_come_before_the_wrapped_checks(wrt: list[str], field: str) -> None:
    inp = _base()
    inp["times"] = [0.5, 0.4, 1.5, 2.0]  # also a structural error of the wrapped operation
    with pytest.raises(QfError) as info:
        _call(inp, wrt)
    assert info.value.code == "E_INPUT"
    assert info.value.field == field


def test_wrapped_errors_pass_through() -> None:
    inp = _base()
    inp["counterparty"]["recovery"] = 1.0
    with pytest.raises(QfError) as info:
        _call(inp)
    assert info.value.code == "E_DOMAIN"


def test_keys() -> None:
    assert xva_aad._keys(False, False) == xva_aad.BASE_KEYS
    assert xva_aad._keys(True, False) == (*xva_aad.BASE_KEYS, "im", "im_spread")
    assert xva_aad._keys(False, True) == (*xva_aad.BASE_KEYS, "capital", "hurdle_rate")
    assert xva_aad.WRAPPED == "xva.adjustments.value"
    assert xva_aad.MAX_BUCKETS == 10_000
