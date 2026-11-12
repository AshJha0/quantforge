"""Stage I wave 2: credit and correlation hedges
(specifications/08-hedging/credit-and-correlation-hedges.md, rulings I-15 to I-19)."""
import math
from datetime import date
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantforge_core import credit
from quantforge_core import credit_correlation_hedges as cch
from quantforge_core.cli import operations  # noqa: F401 - registers the verbs
from quantforge_core.cli.registry import execute
from quantforge_core.curves import CurveData
from quantforge_core.errors import QfError

TRADE = date(2026, 11, 6)
PILLARS = [date(2027, 12, 20), date(2029, 12, 20), date(2031, 12, 20), date(2033, 12, 20),
           date(2036, 12, 20)]
SURVIVAL = [0.9887612955056266, 0.9533647856547852, 0.8989450529594715, 0.8450453062401858,
            0.7636148113028429]
DISCOUNT_JSON = {"as_of": "2026-11-06", "interpolation": "LOG_LINEAR_DF",
                 "pillars": [{"date": "2046-11-06", "discount_factor": 0.458161174870904}]}
Y5, Y7, Y3, Y10 = date(2031, 12, 20), date(2033, 12, 20), date(2029, 12, 20), date(2036, 12, 20)


def discount(interpolation: str = "LOG_LINEAR_DF") -> CurveData:
    return CurveData(TRADE, interpolation, (date(2046, 11, 6),), (0.458161174870904,))


def hedge(book: Any, hedges: Any, targets: Any, recovery: float = 0.4,
          curve: CurveData | None = None, survival: Any = None) -> dict[str, Any]:
    return cch.credit_cds(TRADE, curve or discount(), TRADE, PILLARS, survival or SURVIVAL,
                          recovery, book, hedges, targets)


def code(f: Any, *args: Any, **kwargs: Any) -> str:
    with pytest.raises(QfError) as caught:
        f(*args, **kwargs)
    return caught.value.code


SOLD_7Y = [(Y7, 0.01, 1e7, "SELL_PROTECTION")]


# ----- hedge.credit.cds -----

@pytest.mark.parametrize(("mat", "coupon", "side"), [
    (Y7, 0.01, "SELL_PROTECTION"), (Y5, 0.05, "BUY_PROTECTION"), (Y3, 0.0, "SELL_PROTECTION")])
def test_property_own_contract_returns_the_book_notional(mat: date, coupon: float,
                                                         side: str) -> None:
    out = hedge([(mat, coupon, 2.5e6, side)], [(mat, coupon)], ["CS01"])
    signed = 2.5e6 if side == "BUY_PROTECTION" else -2.5e6
    assert out["notionals"][0] == pytest.approx(-signed, rel=1e-13)
    assert out["after"]["jtd"] == pytest.approx(0.0, abs=1e-6)
    assert all(abs(v) <= 1e-6 for v in out["after"]["buckets"])


@pytest.mark.parametrize(("targets", "short"), [(["CS01", "JTD"], Y3), (["JTD", "BUCKET_2"], Y3),
                                               (["BUCKET_3", "BUCKET_4"], Y7)])
def test_property_targets_are_zero_after(targets: list[str], short: date) -> None:
    book = [*SOLD_7Y, (Y10, 0.05, 4e6, "BUY_PROTECTION")]
    out = hedge(book, [(short, 0.01), (Y10, 0.01)], targets)
    for t in targets:
        value = (out["after"]["cs01"] if t == "CS01" else out["after"]["jtd"] if t == "JTD"
                 else out["after"]["buckets"][int(t[-1]) - 1])
        assert abs(value) <= 1e-6


def test_property_buckets_add_up_to_the_parallel_cs01_to_first_order() -> None:
    out = hedge(SOLD_7Y, [(Y5, 0.01)], ["CS01"])
    book = out["book"]
    assert math.fsum(book["buckets"]) == pytest.approx(book["cs01"], rel=1e-3)
    assert book["buckets"][4] == 0.0  # the 7Y ends before the last section starts


def test_cs01_is_the_central_difference_of_the_spec() -> None:
    """Rebuild the bumped curves by hand and price with `credit.price`."""
    eps = 1e-4 / 0.6
    times = [(d - TRADE).days / 365 for d in PILLARS]

    def pv(sign: float) -> float:
        survival = [q * math.exp(-sign * eps * t) for q, t in zip(SURVIVAL, times, strict=True)]
        hz = credit.Hazard(TRADE, PILLARS, survival)
        return credit.price(TRADE, discount(), hz, 0.4, Y7, 0.01, 1.0, "BUY_PROTECTION",
                            "STANDARD")["pv"]

    out = hedge([(Y7, 0.01, 1.0, "BUY_PROTECTION")], [(Y5, 0.01)], ["CS01"])
    assert out["book"]["cs01"] == pytest.approx((pv(1.0) - pv(-1.0)) / 2, rel=1e-9)
    base = credit.price(TRADE, discount(), credit.Hazard(TRADE, PILLARS, SURVIVAL), 0.4, Y7, 0.01,
                        1.0, "BUY_PROTECTION", "STANDARD")["pv"]
    assert out["book"]["pv"] == pytest.approx(base, rel=1e-14)
    assert out["book"]["jtd"] == pytest.approx(0.6 - base, rel=1e-14)


def test_hedge_upfront_uses_the_clean_upfront() -> None:
    out = hedge(SOLD_7Y, [(Y7, 0.01)], ["CS01"])
    price = credit.price(TRADE, discount(), credit.Hazard(TRADE, PILLARS, SURVIVAL), 0.4, Y7,
                         0.01, 1.0, "BUY_PROTECTION", "STANDARD")
    assert out["hedge_upfront"] == pytest.approx(1e7 * price["upfront"], rel=1e-12)


@pytest.mark.parametrize(("change", "expected"), [
    ({"curve": discount("LINEAR_ZERO"), "book": []}, "E_INPUT"),
    ({"book": []}, "E_INPUT"),
    ({"hedges": []}, "E_INPUT"),
    ({"targets": ["CS01", "JTD"]}, "E_INPUT"),
    ({"hedges": [(Y5, 0.01), (Y7, 0.01)], "targets": ["CS01", "CS01"]}, "E_INPUT"),
    ({"targets": ["BUCKET_6"]}, "E_INPUT"),
    ({"targets": ["BUCKET_0"]}, "E_INPUT"),
    ({"targets": ["THETA"]}, "E_INPUT"),
    ({"hedges": [(TRADE, 0.01)]}, "E_INPUT"),
    ({"book": [(Y7, 0.01, 1e7, "SELL_PROTECTION"), (TRADE, 0.01, 1.0, "BUY_PROTECTION")]},
     "E_INPUT"),
    ({"recovery": 1.0}, "E_DOMAIN"),
    ({"recovery": -0.1}, "E_DOMAIN"),
    ({"book": [(Y7, 0.01, -1.0, "SELL_PROTECTION")]}, "E_DOMAIN"),
    ({"hedges": [(Y5, -0.01)]}, "E_DOMAIN"),
    ({"hedges": [(Y5, 0.01), (Y5, 0.01)], "targets": ["CS01", "JTD"]}, "E_SINGULAR"),
    ({"hedges": [(date(2027, 12, 20), 0.01), (Y3, 0.01)], "targets": ["BUCKET_4", "BUCKET_5"]},
     "E_SINGULAR"),
])
def test_credit_checks(change: dict[str, Any], expected: str) -> None:
    args: dict[str, Any] = {"book": SOLD_7Y, "hedges": [(Y5, 0.01)], "targets": ["CS01"]}
    args.update(change)
    assert code(hedge, **args) == expected


def test_credit_cli_and_limits() -> None:
    inputs: dict[str, Any] = {
        "trade_date": "2026-11-06", "discount": DISCOUNT_JSON,
        "hazard": {"as_of": "2026-11-06",
                   "pillars": [{"date": d.isoformat(), "survival": q}
                               for d, q in zip(PILLARS, SURVIVAL, strict=True)]},
        "recovery": 0.4,
        "book": [{"maturity": "2033-12-20", "coupon": 0.01, "notional": 1e7,
                  "side": "SELL_PROTECTION"}],
        "hedges": [{"maturity": "2033-12-20", "coupon": 0.01}], "targets": ["CS01"]}
    assert execute("hedge.credit.cds", inputs)["notionals"][0] == pytest.approx(1e7, rel=1e-13)
    with pytest.raises(QfError) as caught:
        execute("hedge.credit.cds", {**inputs, "hedges": inputs["hedges"] * 51,
                                     "targets": ["CS01"] * 51})
    assert caught.value.code == "E_LIMIT"
    with pytest.raises(QfError) as caught:
        execute("hedge.credit.cds", {**inputs, "targets": [1]})
    assert caught.value.code == "E_SCHEMA"


# ----- hedge.correlation.neutralise -----

Market8 = tuple[float, float, float, float, float, float, float, float]
MARKET: Market8 = (100.0, 95.0, 0.03, 0.01, 0.02, 0.25, 0.2, 0.6)
EXCHANGE = {"quantity1": 1.0, "quantity2": 1.0, "expiry_years": 1.0}


def neutralise(book: Any, hedges: Any, targets: Any,
               market: Market8 = MARKET) -> dict[str, Any]:
    return cch.correlation_neutralise(*market, book, hedges, targets)


def margrabe(s1: float, s2: float, q1: float, q2: float, v1: float, v2: float, rho: float,
             t: float) -> float:
    s = math.sqrt(v1 * v1 + v2 * v2 - 2 * rho * v1 * v2)
    f1, f2 = s1 * math.exp(-q1 * t), s2 * math.exp(-q2 * t)
    d1 = (math.log(f1 / f2) + s * s * t / 2) / (s * math.sqrt(t))
    return f1 * cch._cdf(d1) - f2 * cch._cdf(d1 - s * math.sqrt(t))


def test_exchange_greeks_against_finite_differences() -> None:
    market = cch._Market(*MARKET)
    g = market.greeks("EXCHANGE", EXCHANGE)
    base = (100.0, 95.0, 0.01, 0.02, 0.25, 0.2, 0.6, 1.0)

    def bumped(index: int, h: float) -> float:
        up, down = list(base), list(base)
        up[index] += h
        down[index] -= h
        return (margrabe(*up) - margrabe(*down)) / (2 * h)

    assert g[0] == pytest.approx(bumped(0, 1e-3), rel=1e-8)
    assert g[1] == pytest.approx(bumped(1, 1e-3), rel=1e-8)
    assert g[2] == pytest.approx(bumped(4, 1e-6), rel=1e-7)
    assert g[3] == pytest.approx(bumped(5, 1e-6), rel=1e-7)
    assert g[4] == pytest.approx(0.01 * bumped(6, 1e-6), rel=1e-7)


@settings(max_examples=60, deadline=None)
@given(st.floats(0.1, 0.6), st.floats(0.1, 0.6), st.floats(-0.9, 0.9), st.floats(0.1, 5.0),
       st.floats(0.8, 1.25))
def test_property_correlation_signs(v1: float, v2: float, rho: float, t: float,
                                    ratio: float) -> None:
    market = cch._Market(100.0, 100.0 * ratio, 0.02, 0.01, 0.0, v1, v2, rho)
    exchange = market.greeks("EXCHANGE", {"quantity1": 1.0, "quantity2": 1.0, "expiry_years": t})
    assert exchange[4] < 0  # a long exchange option loses when correlation rises
    for kind in ("CALL_1", "PUT_1", "CALL_2", "PUT_2"):
        assert market.greeks(kind, {"strike": 100.0, "expiry_years": t})[4] == 0.0


def test_all_five_greeks_are_neutralised() -> None:
    book = [("EXCHANGE", {**EXCHANGE, "quantity": -1000.0})]
    hedges = [("EXCHANGE", {**EXCHANGE, "expiry_years": 0.5}), ("CALL_1",
              {"strike": 100.0, "expiry_years": 1.0}), ("PUT_2", {"strike": 90.0,
              "expiry_years": 1.5}), ("UNDERLYING_1", {}), ("UNDERLYING_2", {})]
    out = neutralise(book, hedges, list(cch.TARGETS))
    scale = max(1.0, *map(abs, out["greeks_before"].values()))
    assert all(abs(v) <= 1e-10 * scale for v in out["greeks_after"].values())


def test_exchange_options_alone_cannot_separate_vega_from_correlation() -> None:
    book = [("EXCHANGE", {**EXCHANGE, "quantity": -1000.0})]
    two = [("EXCHANGE", {**EXCHANGE, "expiry_years": 0.5}),
           ("EXCHANGE", {**EXCHANGE, "expiry_years": 2.0, "quantity1": 1.1})]
    assert code(neutralise, book, two, ["CORRELATION", "VEGA_1"]) == "E_SINGULAR"
    mixed = [two[0], ("CALL_1", {"strike": 100.0, "expiry_years": 1.0})]
    out = neutralise(book, mixed, ["CORRELATION", "VEGA_1"])
    assert abs(out["greeks_after"]["correlation01"]) < 1e-9


def test_correlation_one_with_unequal_vols_is_regular() -> None:
    market = (100.0, 95.0, 0.03, 0.01, 0.02, 0.25, 0.2, 1.0)
    out = neutralise([("EXCHANGE", {**EXCHANGE, "quantity": 1.0})],
                     [("EXCHANGE", {**EXCHANGE, "expiry_years": 2.0})], ["CORRELATION"], market)
    assert out["quantities"][0] < 0
    equal = (100.0, 95.0, 0.03, 0.01, 0.02, 0.2, 0.2, 1.0)
    assert code(neutralise, [("EXCHANGE", {**EXCHANGE, "quantity": 1.0})],
                [("UNDERLYING_1", {})], ["DELTA_1"], equal) == "E_DOMAIN"
    # Without an exchange option a zero spread volatility is not a rule.
    assert neutralise([("CALL_1", {"strike": 100.0, "expiry_years": 1.0, "quantity": 1.0})],
                      [("UNDERLYING_1", {})], ["DELTA_1"], equal)["quantities"][0] < 0


@pytest.mark.parametrize(("change", "expected"), [
    ({"targets": ["DELTA_1", "DELTA_2"]}, "E_INPUT"),
    ({"hedges": [], "targets": []}, "E_INPUT"),
    ({"hedges": [("UNDERLYING_1", {}), ("UNDERLYING_2", {})], "targets": ["DELTA_1"] * 2},
     "E_INPUT"),
    ({"hedges": [("UNDERLYING_1", {"expiry_years": 1.0})]}, "E_INPUT"),
    ({"hedges": [("CALL_2", {"strike": 1.0})]}, "E_INPUT"),
    ({"hedges": [("EXCHANGE", {"quantity1": 1.0, "quantity2": 1.0})]}, "E_INPUT"),
    ({"book": [("EXCHANGE", EXCHANGE)]}, "E_INPUT"),
    ({"market": (100.0, 95.0, 0.03, 0.01, 0.02, 0.25, 0.2, 1.01)}, "E_DOMAIN"),
    ({"market": (0.0, 95.0, 0.03, 0.01, 0.02, 0.25, 0.2, 0.5)}, "E_DOMAIN"),
    ({"market": (100.0, 95.0, 0.03, 0.01, 0.02, 0.0, 0.2, 0.5)}, "E_DOMAIN"),
    ({"hedges": [("CALL_1", {"strike": -1.0, "expiry_years": 1.0})]}, "E_DOMAIN"),
    ({"hedges": [("EXCHANGE", {**EXCHANGE, "quantity2": 0.0})]}, "E_DOMAIN"),
    ({"hedges": [("UNDERLYING_1", {}), ("UNDERLYING_1", {})], "targets": ["DELTA_1", "VEGA_1"]},
     "E_SINGULAR"),
    ({"hedges": [("UNDERLYING_1", {})], "targets": ["CORRELATION"]}, "E_SINGULAR"),
])
def test_correlation_checks(change: dict[str, Any], expected: str) -> None:
    args: dict[str, Any] = {"book": [("EXCHANGE", {**EXCHANGE, "quantity": -10.0})],
                            "hedges": [("UNDERLYING_1", {})], "targets": ["DELTA_1"]}
    args.update(change)
    assert code(neutralise, **args) == expected


def test_correlation_cli_and_limits() -> None:
    inputs: dict[str, Any] = {
        "spot1": 100.0, "spot2": 95.0, "rate": 0.03, "yield1": 0.01, "yield2": 0.02,
        "vol1": 0.25, "vol2": 0.2, "correlation": 0.6,
        "book": [{"instrument": "EXCHANGE", **EXCHANGE, "quantity": -1000.0}],
        "hedges": [{"instrument": "UNDERLYING_1"}], "targets": ["DELTA_1"]}
    assert abs(execute("hedge.correlation.neutralise", inputs)["greeks_after"]["delta_1"]) < 1e-9
    for bad, expected in (({"hedges": [{"instrument": "UNDERLYING_1"}] * 6,
                            "targets": ["DELTA_1"] * 6}, "E_LIMIT"),
                          ({"hedges": [{"instrument": "CALL_3"}]}, "E_SCHEMA"),
                          ({"hedges": [{"instrument": "CALL_1", "strike": "x",
                                        "expiry_years": 1.0}]}, "E_SCHEMA")):
        with pytest.raises(QfError) as caught:
            execute("hedge.correlation.neutralise", {**inputs, **bad})
        assert caught.value.code == expected
