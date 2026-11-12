"""Stage E: tests aimed at the mutants that survived the stage E mutation run (sampled mutmut
mutants in surfaces_local_vol, heston_slv, fx_smile, exotics, rates_vol, garch_varswap_vix and
credit_options). Each test names the mutants it kills; the equivalent ones are listed at the end.

Error tests check the whole error, code, field and message, since all three reach the caller."""
import copy
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from quantforge_core import arb_surface, rates_vol, variance
from quantforge_core import credit_options as ce
from quantforge_core import exotics as ex
from quantforge_core import fx_smile as fx
from quantforge_core import heston as hm
from quantforge_core.cli.main import run_case
from quantforge_core.errors import QfError
from quantforge_core.smile import Svi

GOLDEN = next(p / "datasets/golden/stage_e_b/ratesvol_e.json"
              for p in Path(__file__).resolve().parents
              if (p / "datasets/golden/stage_e_b/ratesvol_e.json").exists())


def err(f, *args, **kwargs):
    """(code, field, message) of the QfError that f raises."""
    with pytest.raises(QfError) as e:
        f(*args, **kwargs)
    return e.value.code, e.value.field, e.value.message


def _base(operation):
    cases = json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]
    case = next(c for c in cases if c["operation"] == operation
                and c["expected"]["status"] == "ok")
    return copy.deepcopy(case["inputs"])


def run(operation, inputs):
    return run_case(json.dumps({"schema_version": "1.0", "case_id": "t", "operation": operation,
                                "inputs": inputs}))


def cli_err(operation, inputs):
    r = run(operation, inputs)
    assert r["status"] == "error", r
    e = r["error"]
    return e["code"], e.get("field"), e["message"]


# --- credit_options (credit_options) ---

DATES = (date(2026, 11, 6), date(2027, 3, 20), date(2032, 3, 20))
MARKET = (*DATES, 0.035, 0.02, 0.4)


def test_cds_payer_implied_deep_in_the_money() -> None:
    # cds_option_implied 57: a payer's upper bound is scale * forward, not scale * strike
    price = ce.cds_option_price(*MARKET, "PAYER", 0.002, 1e7, 0.5, True)["price"]
    assert ce.cds_option_implied(*MARKET, "PAYER", 0.002, 1e7, price, True) == \
        pytest.approx(0.5, rel=1e-6)  # flat in vol deep in the money


def test_cds_implied_premium_out_of_bounds_error() -> None:
    # cds_option_implied 66, 68
    assert err(ce.cds_option_implied, *MARKET, "RECEIVER", 0.0096, 1e7, -1.0, True) == \
        ("E_DOMAIN", "premium", "the premium has no implied vol")


def test_tranche_and_pool_errors() -> None:
    # tranche_loss 8, _check_pool 13
    assert err(ce.tranche_loss, 0.05, 0.3, 0.4, 0.1, 0.1) == \
        ("E_INPUT", "attachment", "need 0 <= attachment < detachment <= 1")
    assert err(ce.tranche_loss, 0.0, 0.3, 0.4, 0.0, 0.1) == \
        ("E_DOMAIN", "default_probability", "default_probability must be in (0, 1)")


def test_tranche_above_the_maximum_loss_is_empty() -> None:
    # losses never pass 1 - R, so a tranche attaching above it loses nothing
    assert ce.tranche_loss(0.05, 0.3, 0.4, 0.7, 0.9) == pytest.approx(0.0, abs=1e-15)


# --- exotics ---

S, K, T, R, Q, V = 100.0, 100.0, 1.0, 0.05, 0.02, 0.25


def test_exotics_error_messages_and_fields() -> None:
    # _positive 4, barrier 19, asian_geometric 19, lookback 20 and 25
    assert err(ex.barrier, 0.0, K, T, R, Q, V, "CALL", 90.0, 0.0, "DOWN_OUT") == \
        ("E_DOMAIN", "spot", "spot must be above 0")
    assert err(ex.barrier, S, K, T, R, Q, V, "CALL", 90.0, -1.0, "DOWN_OUT") == \
        ("E_DOMAIN", "rebate", "rebate must not be negative")
    assert err(ex.asian_geometric, S, K, T, R, Q, V, "CALL", "CONTINUOUS", [0.5]) == \
        ("E_INPUT", "fixing_years", "fixing_years must be empty for CONTINUOUS")
    assert err(ex.lookback, S, T, R, Q, V, "CALL", 110.0) == \
        ("E_DOMAIN", "running_extreme", "running_extreme is on the wrong side of spot")


def test_quanto_checks_fx_vol_and_accepts_unit_correlation() -> None:
    # quanto 10 (fx_vol check dropped), quanto 15 (rho = 1 refused)
    assert err(ex.quanto, S, K, T, R, 0.01, Q, V, 0.0, 0.3, "CALL") == \
        ("E_DOMAIN", "fx_vol", "fx_vol must be above 0")
    assert ex.quanto(S, K, T, R, 0.01, Q, V, 0.1, 1.0, "CALL") > 0
    assert ex.quanto(S, K, T, R, 0.01, Q, V, 0.1, -1.0, "CALL") > 0


def test_basket_crr_fd_errors() -> None:
    # basket 42 and 54, crr 12 and 16, fd 18
    one = [[1.0]]
    assert err(ex.basket, [100.0], [1.0], [0.2], [[2.0]], K, T, R, "CALL") == \
        ("E_INPUT", "correlation", "correlation must be square, symmetric, unit diagonal, in [-1, 1]")
    assert err(ex.basket, [0.0], [1.0], [0.2], one, K, T, R, "CALL") == \
        ("E_DOMAIN", "forwards", "a forward is not above 0")
    assert err(ex.crr, S, K, T, R, Q, V, "CALL", 0) == \
        ("E_INPUT", "steps", "steps must be at least 1")
    assert err(ex.fd, S, K, T, R, Q, V, "CALL", "EUROPEAN", 4, 10, 4.0) == \
        ("E_INPUT", "grid", "nx must be odd and at least 5")


def test_fd_european_boundary_uses_the_step_end_time() -> None:
    # fd 153: the boundary at step n is discounted over (n + 1) dt. A narrow grid makes the
    # boundary matter; one step can be checked against the Thomas solve done here.
    out = ex.fd(S, K, T, R, Q, V, "PUT", "EUROPEAN", 5, 1, 0.5)
    h = 0.5 * V
    dx = 2 * h / 4
    spots = [math.exp(math.log(S) - h + i * dx) for i in range(5)]
    mu = R - Q - V * V / 2
    a = V * V / (2 * dx * dx) - mu / (2 * dx)
    c = V * V / (2 * dx * dx) + mu / (2 * dx)
    b = 1 + V * V / (dx * dx) + R
    rhs = [max(K - x, 0.0) for x in spots]
    rhs[0], rhs[-1] = (max(K * math.exp(-R * T) - x * math.exp(-Q * T), 0.0)
                       for x in (spots[0], spots[-1]))
    # interior 3x3 system  -a u[i-1] + b u[i] - c u[i+1] = rhs[i], with u[0], u[4] known
    m = [[b, -c, 0.0], [-a, b, -c], [0.0, -a, b]]
    y = [rhs[1] + a * rhs[0], rhs[2], rhs[3] + c * rhs[4]]
    for i in (1, 2):  # forward elimination
        w = m[i][i - 1] / m[i - 1][i - 1]
        m[i] = [p - w * q for p, q in zip(m[i], m[i - 1], strict=True)]
        y[i] -= w * y[i - 1]
    u3 = y[2] / m[2][2]
    u2 = (y[1] - m[1][2] * u3) / m[1][1]
    assert out["price"] == pytest.approx(u2, rel=1e-12)


# --- fx_smile ---

EUR = (1.10, 0.5, 0.03, 0.02)


def test_fx_errors() -> None:
    # _positive 6, delta_to_strike 46, 50 and 53, smile_from_quotes 37
    assert err(fx.delta_to_strike, 0.0, 0.5, 0.03, 0.02, 0.1, "CALL", 0.25, "SPOT") == \
        ("E_DOMAIN", "spot", "spot must be above 0")
    assert err(fx.delta_to_strike, *EUR, 0.1, "CALL", 0.999, "SPOT") == \
        ("E_DOMAIN", "delta", "delta is out of range")
    assert err(fx.smile_from_quotes, *EUR, 0.075, -0.2, 0.002, 0.25, "SPOT", "DNS") == \
        ("E_DOMAIN", "bf", "call_vol is not above 0")


def test_bracket_up_doubles() -> None:
    # _bracket_up 13: the steps are 1, 2, 4, 8, so the first sign change of x - 5 from 0 is 8
    assert fx._bracket_up(lambda x: x - 5.0, 0.0) == 8.0
    assert fx._bracket_up(lambda x: 5.0 - x, 0.0) == 8.0


def test_pa_put_with_a_tiny_delta_walks_left(monkeypatch: pytest.MonkeyPatch):
    # delta_to_strike 117: a small PA put delta needs the bracket walked several units left.
    # The mutant (low = 1.0) never leaves the loop, so cap the delta calls to fail fast.
    calls = [0]
    real = fx._Market.delta

    def counted(self, *args):
        calls[0] += 1
        if calls[0] > 10_000:
            raise RuntimeError("bracket walk does not terminate")
        return real(self, *args)

    monkeypatch.setattr(fx._Market, "delta", counted)
    strike = fx.delta_to_strike(*EUR, 0.8, "PUT", -1e-6, "FORWARD_PA")
    monkeypatch.undo()
    m = fx._Market(*EUR, 0.8)
    assert math.log(strike / m.forward) < -1.0
    assert m.delta("FORWARD_PA", -1.0, strike) == pytest.approx(-1e-6, rel=1e-8)


# --- garch_varswap_vix (variance) ---

def _fair(**over):
    args: dict[str, Any] = {"as_of": date(2026, 11, 6), "maturity": date(2027, 11, 6), "spot": 100.0, "rate": 0.04,
            "dividend_yield": 0.0, "put_strikes": [80.0, 90.0, 100.0],
            "call_strikes": [100.0, 110.0, 120.0],
            "vols": [(k, 0.2) for k in (80.0, 90.0, 100.0, 110.0, 120.0)],
            "extension_step": 10.0, "variance_strike": 0.04, "variance_notional": 1e6}
    args.update(over)
    return variance.varswap_fair_strike(**args)


def test_garch_errors() -> None:
    # _initial_variance 19, _check_initial_text 7 and 9, _check_weights 20 and 29
    r = [0.01, -0.02, 0.005]
    assert err(variance.garch_loglik, r, 1e-5, 0.1, 0.8, -1.0) == \
        ("E_DOMAIN", "initial_variance", "initial_variance must be positive")
    assert err(variance.garch_loglik, r, 1e-5, 0.1, 0.8, "BAD") == \
        ("E_INPUT", "initial_variance", "initial_variance must be SAMPLE or a number")
    assert err(variance.garch_loglik, r, 1e-5, -0.1, 0.8, "SAMPLE") == \
        ("E_DOMAIN", "alpha", "alpha must not be negative")
    assert err(variance.garch_loglik, r, 1e-5, 0.1, -0.8, "SAMPLE") == \
        ("E_DOMAIN", "beta", "beta must not be negative")
    # garch_fit 3
    assert err(variance.garch_fit, r, "SAMPLE") == \
        ("E_INPUT", "returns", "at least 30 returns are needed")


def test_garch_forecast_boundaries() -> None:
    # garch_forecast 9, 42 and 46
    f = variance.garch_forecast
    assert err(f, 1e-5, 0.1, 0.8, 2e-4, 0, 252) == ("E_INPUT", "horizon", "horizon must be at least 1")
    assert err(f, 1e-5, 0.3, 0.7, 2e-4, 5, 252) == \
        ("E_DOMAIN", "alpha", "alpha + beta must be below 1 for a long-run variance")
    # garch_forecast 12: one period a year is valid; the annualised vol is sqrt(total / horizon)
    variances, total, vol, _ = f(1e-5, 0.0, 0.0, 2e-4, 2, 1.0)
    assert variances == [2e-4, 1e-5] and vol == pytest.approx(math.sqrt(total / 2), rel=1e-15)


def test_varswap_negative_spot_field() -> None:
    # varswap_fair_strike 69: strikes on the right sides of a negative spot reach the spot check
    out = err(_fair, spot=-1.0, put_strikes=[-2.0], call_strikes=[-0.5],
              vols=[(-2.0, 0.2), (-0.5, 0.2)])
    assert out == ("E_DOMAIN", "spot", "spot must be positive")


Quote = variance.Quote
STRIP = [Quote(90, 10.5, 11.5, 0.5, 0.7), Quote(95, 6.0, 6.6, 1.4, 1.6),
         Quote(100, 2.9, 3.1, 2.9, 3.3), Quote(105, 1.0, 1.2, 5.8, 6.6),
         Quote(110, 0.3, 0.5, 10.0, 11.0)]


def test_vix_terms_must_differ() -> None:
    # vix_index 6: two terms both exactly at 30 days bracket nothing
    n = variance.MINUTES_30D
    assert err(variance.vix_index, (n, 0.0, STRIP), (n, 0.0, STRIP)) == \
        ("E_INPUT", "near", "the terms must bracket 30 days with near before next")


def test_vix_negative_interpolated_variance() -> None:
    # vix_index 38 and 39: K0 = 102 sits far below the forward 129 with tiny prices, so the
    # (F / K0 - 1)^2 term wins and both term variances are negative
    strip = [Quote(101, 50, 50, 0.01, 0.01), Quote(102, 1.5, 1.5, 0, 0),
             Quote(130, 0.01, 0.01, 1.01, 1.01)]
    assert variance.vix_term_variance(43200, 0.0, strip)[2] < 0
    assert err(variance.vix_index, (43100, 0.0, strip), (43300, 0.0, strip)) == \
        ("E_DOMAIN", "near", "the interpolated variance is negative")


# --- heston_slv (heston) ---

H = hm.Heston(0.04, 1.5, 0.04, 0.5, -0.7)
FLAT = [arb_surface.Slice(1.0, Svi(0.04, 0.0, 0.0, 0.0, 0.1))]


def test_heston_errors() -> None:
    # _input 5, _check_common 6, heston_cf 15
    assert err(hm.heston_cf, 1.0, H, []) == ("E_INPUT", "u", "u is empty")
    assert err(hm.heston_price, 100.0, [], 1.0, 0.0, 0.0, H, "CALL") == \
        ("E_INPUT", "strikes", "strikes is empty")
    assert err(hm.heston_cf, 0.0, H, [1.0]) == \
        ("E_DOMAIN", "expiry_years", "expiry_years must be above 0")


def test_slv_errors_and_two_time_steps() -> None:
    # slv_leverage 8 (nt = 2 refused), 37, 53
    lo, hi = math.log(100) - 1.0, math.log(100) + 1.0
    out: dict[str, Any] = hm.slv_leverage(100.0, 1.0, 0.0, 0.0, H, FLAT, hm.Grid(11, 5, 2, lo, hi, 0.25))
    assert len(out["leverage"]) == 11
    grid = hm.Grid(11, 5, 4, lo, hi, 0.25)
    assert err(hm.slv_leverage, 0.0, 1.0, 0.0, 0.0, H, FLAT, grid) == \
        ("E_DOMAIN", "spot", "spot must be above 0")
    assert err(hm.slv_leverage, 100.0, 0.0, 0.0, 0.0, H, FLAT, grid) == \
        ("E_DOMAIN", "expiry_years", "expiry_years must be above 0")


# Reference output of the unmutated solver on a small grid with carry and correlation, so the
# drift at t = 0, the first interior row, the cross term and the boundary rows all count.
SLV_REF = {"leverage": [0.7567192932516402, 0.694103940389056, 0.7159740073240974,
                        0.7371748981932825, 0.7571749678561518, 0.7760802723194763,
                        0.7953261473023993, 0.8186380795714608, 0.8558863556202758,
                        0.9347961563515759, 0.7567192932516402],
           "mass": 0.9719926197335328}


def test_slv_reference_values() -> None:
    # slv_leverage 272, 295 and 334
    lo, hi = math.log(100) - 1.0, math.log(100) + 1.0
    out = hm.slv_leverage(100.0, 1.0, 0.05, 0.01, H, FLAT, hm.Grid(11, 7, 6, lo, hi, 0.25))
    assert out["leverage"] == pytest.approx(SLV_REF["leverage"], rel=1e-12)
    assert out["mass"] == pytest.approx(SLV_REF["mass"], rel=1e-12)


def test_slv_start_density_uses_the_drifted_local_vol() -> None:
    # slv_leverage 151: the t = 0 local vol is read at ln S + (r - q) dt; a skewed slice makes
    # the point matter (a flat one does not)
    skew = [arb_surface.Slice(1.0, Svi(0.03, 0.1, -0.5, 0.0, 0.2))]
    lo, hi = math.log(100) - 1.0, math.log(100) + 1.0
    out: dict[str, Any] = hm.slv_leverage(100.0, 1.0, 0.05, 0.01, H, skew, hm.Grid(11, 7, 6, lo, hi, 0.25))
    assert out["leverage"][5] == pytest.approx(0.8221523246794936, rel=1e-12)
    assert out["mass"] == pytest.approx(0.8170518283911051, rel=1e-12)


# --- rates_vol ---

def test_cube_alpha_error() -> None:
    # price_cube 147
    inputs = _base("rates.swaption.price_cube")
    inputs["cube"]["alpha"][0][0] = 0.0
    assert cli_err("rates.swaption.price_cube", inputs) == ("E_DOMAIN", "cube", "alpha must be above 0")


@pytest.mark.parametrize("change,expected", [
    ({"cap_tenors_months": [13]},
     ("E_INPUT", "cap_tenors_months", "cap tenors must be multiples of 3 months")),  # 11
    ({"flat_vols": [0.24]}, ("E_INPUT", "flat_vols", "one flat vol per cap tenor")),  # 35
    ({"start_months": 0}, ("E_INPUT", "start_months", "start_months must be at least 1")),  # 50
])
def test_strip_errors(change, expected) -> None:
    inputs = dict(_base("rates.cap.strip"), **change)
    assert cli_err("rates.cap.strip", inputs) == expected


def test_strip_black_search_bound_is_five() -> None:
    # cap_strip 143 (Black bound 0.5) and 199 (field of the bound error)
    inputs = _base("rates.cap.strip")
    assert inputs["model"] == "BLACK_76"
    n = len(inputs["flat_vols"])
    assert run("rates.cap.strip", dict(inputs, flat_vols=[0.8] * n))["status"] == "ok"
    code, field, _ = cli_err("rates.cap.strip", dict(inputs, flat_vols=[6.0] * n))
    assert (code, field) == ("E_DOMAIN", "flat_vols")


def test_strip_arbitrage_error_field() -> None:
    # cap_strip 199: a steep fall in flat vol needs a negative caplet vol
    inputs = _base("rates.cap.strip")
    n = len(inputs["flat_vols"])
    assert cli_err("rates.cap.strip", dict(inputs, flat_vols=[0.5] + [0.05] * (n - 1))) ==         ("E_ARBITRAGE", "flat_vols", "a caplet segment needs a vol at or below zero")


def test_rates_option_errors() -> None:
    # _futures_option 23 and 26, yoy_price 5, 19 and 21, zc_price 29
    assert err(rates_vol.bondfut_price, "PUT", 111.25, 0.0, 0.1, 0.9962, 0.055, 1e5) == \
        ("E_DOMAIN", "strike", "strike must be above 0")
    assert err(rates_vol.yoy_price, "BLACK_76", "CAP", 0.03, 1e7, []) == \
        ("E_INPUT", "periods", "periods is empty")
    period = (1.0, 0.96, 0.0285, 0.75, 0.35)
    assert err(rates_vol.yoy_price, "BLACK_76", "CAP", 0.0, 1e7, [period]) == \
        ("E_DOMAIN", "strike", "BLACK_76 needs a positive strike and forwards")
    assert err(rates_vol.zc_price, "BACHELIER", "CAP", 1.02, 0.0, 0.02, 0.95, 0.01, 1e6) == \
        ("E_DOMAIN", "years", "years must be above 0")


def test_yoy_black_refuses_a_negative_forward() -> None:
    # yoy_price 16: the forward is the third field; the expiry (fourth) is positive here
    period = (1.0, 0.96, -0.005, 0.75, 0.35)
    assert err(rates_vol.yoy_price, "BLACK_76", "CAP", 0.03, 1e7, [period])[:2] == \
        ("E_DOMAIN", "strike")


# --- surfaces_local_vol (arb_surface) ---

SVI = Svi(0.02, 0.1, -0.4, 0.02, 0.2)


def test_surface_errors() -> None:
    # check_slices_input 3, check_slices 11, _check 108
    assert err(arb_surface.surface_check, [], [0.0], True) == ("E_INPUT", "slices", "slices is empty")
    assert err(arb_surface.surface_check, [arb_surface.Slice(-1.0, SVI)], [0.0], True) == \
        ("E_DOMAIN", "slices", "an expiry_years is not positive")
    vogt = Svi(-0.0410, 0.1331, 0.3060, 0.3586, 0.4153)
    assert err(arb_surface.surface_check, [arb_surface.Slice(1.0, vogt)], [0.0, 0.8], True) == \
        ("E_ARBITRAGE", "slices", "the surface has arbitrage")


def test_dupire_forward_vol_errors() -> None:
    # dupire 4 and 10, forward_vols 14
    assert err(arb_surface.dupire, [arb_surface.Slice(1.0, SVI)], []) == ("E_INPUT", "points", "points is empty")
    assert err(arb_surface.forward_vols, [1.0, 0.5], [0.2, 0.2]) == \
        ("E_INPUT", "expiry_years", "expiry_years must be strictly increasing")


def test_smile_dynamics_errors_and_call_delta() -> None:
    # smile_dynamics 13, 26, 33 and 68
    f = arb_surface.smile_dynamics
    args = (SVI, 1.0, 100.0, 101.0, 0.02, 0.01, [100.0], "STICKY_STRIKE", "CALL")
    assert err(f, SVI, 0.0, *args[2:]) == ("E_DOMAIN", "expiry_years", "expiry_years must be above 0")
    assert err(f, SVI, 1.0, 0.0, *args[3:]) == ("E_DOMAIN", "spot", "spot must be above 0")
    assert err(f, SVI, 1.0, 100.0, 0.0, *args[4:]) == \
        ("E_DOMAIN", "spot_shifted", "spot_shifted must be above 0")
    call = f(*args)
    put = f(*args[:-1], "PUT")
    assert 0 < call["deltas"][0] < 1 and -1 < put["deltas"][0] < 0
    fwd = 100.0 * math.exp(0.01)
    parity = math.exp(-0.02) * (fwd - 100.0)
    assert call["prices_base"][0] - put["prices_base"][0] == pytest.approx(parity, rel=1e-12)


def test_vol_of_vol_by_hand() -> None:
    # vol_of_vol 51: changes 1, 2, 1 have mean 4/3 and sample variance 1/3
    vov, mean = arb_surface.vol_of_vol([1.0, 2.0, 4.0, 5.0], 4.0, "ABSOLUTE")
    assert mean == pytest.approx(4 / 3, rel=1e-15)
    assert vov == pytest.approx(2 * math.sqrt(1 / 3), rel=1e-14)


# Equivalent mutants (no observable change), one line each:
# credit_options cds_option_implied 94: the E_NO_CONVERGENCE bracket error is unreachable; the Black
#   price reaches the cap (forward or strike times scale) long before vol 1e6.
# credit_options cds_option_implied 107: max_iter 500 -> brent default 200; Brent converges in far fewer.
# credit_options _beta_fraction 25: 999 -> 1000 iterations; the fraction converges in well under 100.
# credit_options _beta_fraction 68: the tiny guard only acts when |1 + num / c| <= 1e-300, never here.
# credit_options _beta_fraction 84: < vs <= 1e-16 on a float difference; the tie is not reachable.
# credit_options tranche_loss 52: min(a / (1 - R), 2.0) vs 1.0; _capped_mean returns p for any k >= 1.
# credit_options _incomplete_beta 28: both branches are the same function (symmetry I_x(a, b) =
#   1 - I_{1-x}(b, a)); moving the switch point changes only rounding.
# exotics basket 92: strict=None is falsy like strict=False; lengths are checked equal before.
# fx_smile _pa_call_peak 15: high 1.0 -> 2.0 only widens a Brent bracket; same root to 1e-15.
# fx_smile delta_to_strike 122: -1e4 vs -10001 on an integer walk; the bracket is found near -10
#   or not at all, see 128.
# fx_smile delta_to_strike 128 and 133: unreachable; a put's PA delta tends to -0 on the left, so
#   gap = delta(x) - target is positive for any target below 0 long before x = -1e4.
# arb_surface _check 43: strict=False; ws and previous both have len(ks) entries.
# heston: none.
# rates_vol price_cube 206: forward <= 0 vs < 0 differs only at a swap rate of exactly 0.0.
# rates_vol _futures_option 41: black.price treats any model other than BACHELIER as Black-76.
# rates_vol bondfut_implied 47: gap(high) == 0 exactly at a power of 2 does not happen in floats
#   here, and Brent returns the same root if it did.
# rates_vol bondfut_implied 52: high doubles from 1, so it is never exactly 1e6.
