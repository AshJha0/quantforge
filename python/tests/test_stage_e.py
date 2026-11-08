"""Stage E unit tests: E1 (arb-free surfaces, local and forward vol) and E7 (GARCH, variance swaps,
VIX). Values come from the worked examples in the specs; the goldens run in test_conformance.py."""
import json
import math
from datetime import date

import pytest

from quantforge_core import vol_e1, vol_e7
from quantforge_core.cli.main import run_case
from quantforge_core.errors import QfError
from quantforge_core.smile import Svi

SVI = Svi(0.02, 0.1, -0.4, 0.02, 0.2)
SLICES = [vol_e1.Slice(0.25, SVI), vol_e1.Slice(1.0, Svi(0.035, 0.11, -0.35, 0.03, 0.25)),
          vol_e1.Slice(2.0, Svi(0.06, 0.12, -0.3, 0.04, 0.3))]


def code(f, *args, **kwargs):
    with pytest.raises(QfError) as e:
        f(*args, **kwargs)
    return e.value.code


def run(operation, inputs):
    return run_case(json.dumps({"schema_version": "1.0", "case_id": "t", "operation": operation,
                                "inputs": inputs}))


# --- E7 GARCH ---

def test_garch_worked_example():
    loglik, variances, nxt = vol_e7.garch_loglik([0.01, -0.02], 1e-5, 0.1, 0.8, "SAMPLE")
    assert variances == pytest.approx([2.5e-4, 2.2e-4], rel=1e-14)
    assert nxt == pytest.approx(2.26e-4, rel=1e-14)
    assert loglik == pytest.approx(5.410998350356715, abs=1e-12)


def test_garch_loglik_errors():
    f = vol_e7.garch_loglik
    assert code(f, [0.1], 1e-5, 0.1, 0.8, "SAMPLE") == "E_INPUT"
    assert code(f, [0.1, 0.2], 1e-5, 0.1, 0.8, "FIRST") == "E_INPUT"
    assert code(f, [0.1, 0.2], 0.0, 0.1, 0.8, "SAMPLE") == "E_DOMAIN"
    assert code(f, [0.1, 0.2], 1e-5, -0.1, 0.8, "SAMPLE") == "E_DOMAIN"
    assert code(f, [0.1, 0.2], 1e-5, 0.1, -0.8, "SAMPLE") == "E_DOMAIN"
    assert code(f, [0.1, 0.2], 1e-5, 0.1, 0.8, 0.0) == "E_DOMAIN"
    assert code(f, [0.0, 0.0], 1e-5, 0.1, 0.8, "SAMPLE") == "E_DOMAIN"
    assert f([0.1, 0.2], 1e-5, 0.5, 0.6, 0.01)[1][0] == 0.01  # alpha + beta >= 1 allowed


def test_garch_forecast():
    variances, total, vol, long_run = vol_e7.garch_forecast(1e-5, 0.1, 0.8, 2.26e-4, 5, 252)
    assert long_run == pytest.approx(1e-4)
    assert variances == pytest.approx([1e-4 + 0.9**h * 1.26e-4 for h in range(5)], rel=1e-13)
    assert vol == pytest.approx(math.sqrt(total * 252 / 5))
    assert vol_e7.garch_forecast(1e-5, 0.0, 0.0, 2e-4, 2, 252)[0] == [2e-4, 1e-5]
    f = vol_e7.garch_forecast
    assert code(f, 1e-5, 0.1, 0.8, 2e-4, 0, 252) == "E_INPUT"
    assert code(f, 1e-5, 0.1, 0.8, 2e-4, 1, 0) == "E_INPUT"
    assert code(f, 1e-5, 0.1, 0.8, 0.0, 1, 252) == "E_DOMAIN"
    assert code(f, 1e-5, 0.2, 0.8, 2e-4, 1, 252) == "E_DOMAIN"


def _series(n, seed=3):
    import random
    rng = random.Random(seed)
    s2, out = 1e-4, []
    for _ in range(n):
        r = math.sqrt(s2) * rng.gauss(0, 1)
        out.append(r)
        s2 = 2e-6 + 0.08 * r * r + 0.9 * s2
    return out


def test_garch_fit_beats_neighbours():
    returns = _series(300)
    best = vol_e7.garch_fit(returns, "SAMPLE")
    for omega, alpha, beta in ((2e-6, 0.08, 0.9), (3e-6, 0.1, 0.85), (1e-6, 0.05, 0.94)):
        assert best >= vol_e7.garch_loglik(returns, omega, alpha, beta, "SAMPLE")[0] - 1e-9
    assert vol_e7.garch_fit(returns, 1e-4) > 0
    assert code(vol_e7.garch_fit, returns[:29], "SAMPLE") == "E_INPUT"
    assert code(vol_e7.garch_fit, returns, "X") == "E_INPUT"


# --- E7 variance swaps ---

def _fair(**over):
    args = {"as_of": date(2026, 11, 6), "maturity": date(2027, 11, 6), "spot": 100.0, "rate": 0.04,
                "dividend_yield": 0.0, "put_strikes": [80.0, 90.0, 100.0],
                "call_strikes": [100.0, 110.0, 120.0],
                "vols": [(k, 0.2) for k in (80.0, 90.0, 100.0, 110.0, 120.0)], "extension_step": 10.0,
                "variance_strike": 0.04, "variance_notional": 1e6}
    args.update(over)
    return vol_e7.varswap_fair_strike(**args)


def test_varswap_weights_worked_example():
    w = vol_e7._weights([100.0, 110.0, 120.0], 130.0, 100.0, 1.0)
    assert w[0] == pytest.approx(9.3796e-4, rel=1e-4)
    assert w[1] == pytest.approx(1.6598e-3, rel=1e-4)


def test_varswap_fair_strike_and_errors():
    fair, vol, pv = _fair()
    assert vol == pytest.approx(math.sqrt(fair)) and fair > 0
    assert pv == pytest.approx(1e6 * math.exp(-0.04) * (fair - 0.04))
    assert code(_fair, maturity=date(2026, 11, 6)) == "E_INPUT"
    assert code(_fair, put_strikes=[]) == "E_INPUT"
    assert code(_fair, call_strikes=[100.0, 100.0]) == "E_INPUT"
    assert code(_fair, put_strikes=[110.0]) == "E_INPUT"
    assert code(_fair, call_strikes=[90.0]) == "E_INPUT"
    assert code(_fair, vols=[(80.0, 0.2)]) == "E_INPUT"
    vols = [(k, 0.2) for k in (80.0, 90.0, 100.0, 110.0, 120.0)]
    assert code(_fair, spot=100.0, vols=[(80.0, -0.2), *vols[1:]]) == "E_DOMAIN"
    assert code(_fair, extension_step=0.0) == "E_DOMAIN"
    assert code(_fair, extension_step=80.0) == "E_DOMAIN"


def test_varswap_realized_worked_example():
    variance, _vol, payoff = vol_e7.varswap_realized([100, 101, 99.5, 100.25, 102, 101.5], 252,
                                                    0.04, 1e6)
    assert variance == pytest.approx(0.035427394095297673, rel=1e-12)
    assert payoff == pytest.approx(-4572.605904702326, rel=1e-10)
    assert code(vol_e7.varswap_realized, [100.0], 252, 0.04, 1e6) == "E_INPUT"
    assert code(vol_e7.varswap_realized, [100.0, 0.0], 252, 0.04, 1e6) == "E_DOMAIN"


# --- E7 VIX ---

STRIP = [vol_e7.Quote(90, 10.5, 11.5, 0.5, 0.7), vol_e7.Quote(95, 6.0, 6.6, 1.4, 1.6),
         vol_e7.Quote(100, 2.9, 3.1, 2.9, 3.3), vol_e7.Quote(105, 1.0, 1.2, 5.8, 6.6),
         vol_e7.Quote(110, 0.3, 0.5, 10.0, 11.0)]


def test_vix_worked_example():
    forward, k0, variance, used = vol_e7.vix_term_variance(43200, 0.0, STRIP)
    assert (forward, k0, used) == (pytest.approx(99.9), 95, [90, 95, 100, 105, 110])
    assert variance == pytest.approx(0.08188158767696967, rel=1e-12)


def test_vix_zero_bids_skip_and_stop():
    strip = [vol_e7.Quote(k, max(100 - k, 0) + 1, max(100 - k, 0) + 1.2, 0.0 if k in (80, 70) else
                          max(k - 100, 0) + 1, max(k - 100, 0) + 1.2)
             for k in (60, 70, 80, 90, 100, 110, 120)]
    used = vol_e7.vix_term_variance(43200, 0.01, strip)[3]
    assert used == [90, 100, 110, 120]
    strip[3] = vol_e7.Quote(90, 11, 11.2, 0.0, 0.2)  # 90 zero too: second zero at 80 stops
    assert vol_e7.vix_term_variance(43200, 0.01, strip)[3] == [100, 110, 120]


def test_vix_errors():
    f = vol_e7.vix_term_variance
    assert code(f, 0, 0.0, STRIP) == "E_INPUT"
    assert code(f, 10, 0.0, STRIP[:2]) == "E_INPUT"
    assert code(f, 10, 0.0, [*STRIP, STRIP[0]]) == "E_INPUT"
    assert code(f, 10, 0.0, [*STRIP[:4], vol_e7.Quote(110, 0.6, 0.5, 10, 11)]) == "E_INPUT"
    assert code(f, 10, 0.0, [*STRIP[:4], vol_e7.Quote(110, -0.1, 0.5, 10, 11)]) == "E_DOMAIN"
    high = [vol_e7.Quote(k, 0.1, 0.2, 5, 6) for k in (200, 210, 220)]
    assert code(f, 10, 0.0, high) == "E_INPUT"


def test_vix_index():
    index, v1, v2 = vol_e7.vix_index((40000, 0.0, STRIP), (50000, 0.0, STRIP))
    assert v1 > 0 and v2 > 0 and index > 0
    assert code(vol_e7.vix_index, (50000, 0.0, STRIP), (40000, 0.0, STRIP)) == "E_INPUT"
    assert code(vol_e7.vix_index, (44000, 0.0, STRIP), (50000, 0.0, STRIP)) == "E_INPUT"


# --- E1 surfaces ---

def test_surface_check_clean_and_flags():
    ks = [-0.6, -0.2, 0.0, 0.2, 0.6]
    assert vol_e1.surface_check(SLICES, ks, True)["arbitrage_free"] is True
    vogt = Svi(-0.0410, 0.1331, 0.3060, 0.3586, 0.4153)
    report = vol_e1.surface_check([vol_e1.Slice(1.0, vogt)], [-0.2, 0.0, 0.4, 0.8, 0.9], False)
    assert report["butterfly_violations"]
    assert code(vol_e1.surface_check, [vol_e1.Slice(1.0, vogt)], [0.0, 0.8], True) \
        == "E_ARBITRAGE"
    steep = [vol_e1.Slice(1.0, Svi(0.04, 2.5, 0.0, 0.0, 0.1))]
    wings = vol_e1.surface_check(steep, [0.0], False)["wing_violations"]
    assert [w["kind"] for w in wings] == ["LEE", "LEE"]
    low = [SLICES[1], vol_e1.Slice(2.0, Svi(0.01, 0.05, -0.35, 0.03, 0.25))]
    report = vol_e1.surface_check(low, [0.0], False)
    assert report["calendar_violations"] and len(report["wing_violations"]) == 2
    tie = [vol_e1.Slice(1.0, Svi(0.04, 0.5, 0.0, 0.0, 0.25)),
           vol_e1.Slice(2.0, Svi(0.0390625, 0.5, 0.0, 0.0, 0.5))]
    sides = [w["side"] for w in vol_e1.surface_check(tie, [5.0], False)["wing_violations"]]
    assert sides == ["LEFT", "RIGHT"]


def test_slices_and_grid_errors():
    f = vol_e1.surface_check
    assert code(f, [], [0.0], False) == "E_INPUT"
    assert code(f, SLICES[::-1], [0.0], False) == "E_INPUT"
    assert code(f, [vol_e1.Slice(0.0, SVI)], [0.0], False) == "E_DOMAIN"
    assert code(f, [vol_e1.Slice(1.0, Svi(0.02, 0.1, 1.0, 0.0, 0.2))], [0.0], False) == "E_DOMAIN"
    assert code(f, SLICES, [], False) == "E_INPUT"
    assert code(f, SLICES, [0.1, 0.0], False) == "E_INPUT"


def test_ssvi_to_svi_matches_ssvi():
    p = vol_e1.ssvi_to_svi(-0.7, 1.2, 0.4, 0.04)
    assert p.a == pytest.approx(0.0102) and p.m > 0
    phi = 1.2 * 0.04**-0.4 * 1.04**-0.6
    for k in (-0.5, 0.0, 0.3):
        ssvi = 0.02 * (1 - 0.7 * phi * k + math.sqrt((phi * k - 0.7) ** 2 + 1 - 0.49))
        assert p.total_variance(k) == pytest.approx(ssvi, rel=1e-14)
    assert code(vol_e1.ssvi_to_svi, 1.0, 1.2, 0.4, 0.04) == "E_DOMAIN"
    assert code(vol_e1.ssvi_to_svi, -0.7, 1.2, 1.4, 0.04) == "E_DOMAIN"


def test_fit_surface_recovers_truth():
    ks = [-0.5, -0.3, -0.15, 0.0, 0.15, 0.3, 0.5]
    rows = [[s.svi.total_variance(k) for k in ks] for s in SLICES]
    slices, rmse, report = vol_e1.fit_surface([0.25, 1.0, 2.0], ks, rows, True)
    assert max(rmse) < 1e-9 and report["arbitrage_free"]
    assert slices[0].svi.a == pytest.approx(0.02, abs=1e-6)
    assert code(vol_e1.fit_surface, [1.0, 0.5], ks, rows[:2], False) == "E_INPUT"
    assert code(vol_e1.fit_surface, [1.0], ks, rows, False) == "E_INPUT"


# --- E1 local and forward vol ---

def test_dupire_flat_vol_is_flat():
    flat = [vol_e1.Slice(1.0, Svi(0.04, 0.0, 0.0, 0.0, 0.1))]
    w, _vols, local = vol_e1.dupire(flat, [(0.5, 0.1), (2.0, -0.2)])
    assert w == pytest.approx([0.02, 0.08]) and local == pytest.approx([0.2, 0.2])
    points = [(0.1, 0.0), (0.25, -0.2), (0.5, 0.0), (1.0, 0.1), (3.0, 0.0)]
    assert all(v > 0 for v in vol_e1.dupire(SLICES, points)[2])
    assert code(vol_e1.dupire, SLICES, []) == "E_INPUT"
    assert code(vol_e1.dupire, SLICES, [(0.0, 0.0)]) == "E_DOMAIN"
    crossing = [SLICES[1], vol_e1.Slice(2.0, Svi(0.01, 0.05, -0.35, 0.03, 0.25))]
    assert code(vol_e1.dupire, crossing, [(1.5, 0.0)]) == "E_ARBITRAGE"
    vogt = [vol_e1.Slice(1.0, Svi(-0.0410, 0.1331, 0.3060, 0.3586, 0.4153))]
    assert code(vol_e1.dupire, vogt, [(1.0, 0.9)]) == "E_ARBITRAGE"


def test_forward_vols():
    assert vol_e1.forward_vols([1.0, 2.0], [0.2, 0.2]) == pytest.approx([0.2, 0.2])
    assert vol_e1.forward_vols([1.0, 4.0], [0.5, 0.25])[1] == 0.0
    assert code(vol_e1.forward_vols, [], []) == "E_INPUT"
    assert code(vol_e1.forward_vols, [2.0, 1.0], [0.2, 0.2]) == "E_INPUT"
    assert code(vol_e1.forward_vols, [1.0, 2.0], [0.2, 0.0]) == "E_DOMAIN"
    assert code(vol_e1.forward_vols, [1.0, 2.0], [0.3, 0.1]) == "E_ARBITRAGE"


def test_smile_dynamics_delta_matches_bump():
    args = (SVI, 0.5, 100.0, 103.0, 0.03, 0.01, [90.0, 100.0, 110.0])
    for option in ("CALL", "PUT"):
        sticky = vol_e1.smile_dynamics(*args, "STICKY_DELTA", option)
        h = 1e-4
        up = vol_e1.smile_dynamics(SVI, 0.5, 100.0 + h, 100.0, 0.03, 0.01, args[6],
                                   "STICKY_DELTA", option)["prices_base"]
        down = vol_e1.smile_dynamics(SVI, 0.5, 100.0 - h, 100.0, 0.03, 0.01, args[6],
                                     "STICKY_DELTA", option)["prices_base"]
        bumps = [(u - d) / (2 * h) for u, d in zip(up, down, strict=True)]
        assert sticky["deltas"] == pytest.approx(bumps, rel=1e-6)
    still = vol_e1.smile_dynamics(*args, "STICKY_STRIKE", "CALL")
    assert still["vols_base"] == still["vols_shifted"]
    f = vol_e1.smile_dynamics
    assert code(f, SVI, 0.5, 100.0, 103.0, 0.0, 0.0, [], "STICKY_STRIKE", "CALL") == "E_INPUT"
    for bad in ((0.0, 100.0, 103.0, [100.0]), (0.5, 0.0, 103.0, [100.0]),
                (0.5, 100.0, 0.0, [100.0]), (0.5, 100.0, 103.0, [0.0])):
        t, s, s1, ks = bad
        assert code(f, SVI, t, s, s1, 0.0, 0.0, ks, "STICKY_STRIKE", "CALL") == "E_DOMAIN"


def test_vol_of_vol():
    vov, mean = vol_e1.vol_of_vol([0.2, 0.21, 0.2], 252, "ABSOLUTE")
    assert mean == pytest.approx(0.0) and vov == pytest.approx(math.sqrt(252) * math.sqrt(0.0002))
    assert vol_e1.vol_of_vol([0.2, 0.22, 0.2], 252, "LOG")[1] == pytest.approx(0.0, abs=1e-15)
    assert code(vol_e1.vol_of_vol, [0.2, 0.2], 252, "LOG") == "E_INPUT"
    assert code(vol_e1.vol_of_vol, [0.2, 0.0, 0.2], 252, "LOG") == "E_DOMAIN"
    assert code(vol_e1.vol_of_vol, [0.2, 0.1, 0.2], 0, "LOG") == "E_DOMAIN"


# --- CLI wiring, schema and limits ---

def test_cli_schema_and_limits():
    r = run("vol.garch.loglik", {"returns": [0.01, 0.02], "omega": 1e-5, "alpha": 0.1,
                                 "beta": 0.8, "initial_variance": [1]})
    assert r["error"]["code"] == "E_SCHEMA"
    r = run("vol.varswap.realized", {"prices": [100.0] * 150, "periods_per_year": 252,
                                     "variance_strike": 0.04, "variance_notional": 1.0})
    assert r["status"] == "ok"  # stage E spec B arrays are not under the stage C cap of 100
    svi = {"a": 0.02, "b": 0.1, "rho": -0.4, "m": 0.02, "sigma": 0.2}
    r = run("vol.svi.surface_check", {"slices": [{"expiry_years": 1.0, "svi": svi}],
                                      "log_moneyness": [i / 1000 for i in range(500)],
                                      "reject": False})
    assert r["status"] == "ok"
    r = run("vol.svi.surface_check", {"slices": [{"expiry_years": 1.0, "svi": svi}],
                                      "log_moneyness": [0.0] * 10_001, "reject": False})
    assert r["error"]["code"] == "E_LIMIT"
    r = run("vol.local.dupire", {"slices": [{"expiry_years": 1.0 + i, "svi": svi}
                                            for i in range(101)],
                                 "points": [{"expiry_years": 1.0, "log_moneyness": 0.0}]})
    assert r["error"]["code"] == "E_LIMIT"


@pytest.mark.parametrize("operation,inputs,key", [
    ("vol.ssvi.to_svi", {"rho": -0.7, "eta": 1.2, "gamma": 0.4, "theta": 0.04}, "svi"),
    ("vol.forward.vol", {"expiry_years": [1.0, 2.0], "vols": [0.2, 0.21]}, "forward_vols"),
    ("vol.volofvol.measure", {"vols": [0.2, 0.21, 0.2], "periods_per_year": 252,
                              "method": "LOG"}, "vol_of_vol"),
    ("vol.smile.dynamics", {"svi": {"a": 0.02, "b": 0.1, "rho": -0.4, "m": 0.02, "sigma": 0.2},
                            "expiry_years": 0.5, "spot": 100.0, "spot_shifted": 103.0,
                            "rate": 0.03, "dividend_yield": 0.01, "strikes": [100.0],
                            "rule": "STICKY_DELTA", "option_type": "PUT"}, "deltas"),
    ("vol.garch.forecast", {"omega": 1e-5, "alpha": 0.1, "beta": 0.8, "next_variance": 2e-4,
                            "horizon": 3, "periods_per_year": 252}, "annualized_vol"),
])
def test_cli_operations(operation, inputs, key):
    r = run(operation, inputs)
    assert r["status"] == "ok" and key in r["outputs"]


_SVI_JSON = {"a": 0.02, "b": 0.1, "rho": -0.4, "m": 0.02, "sigma": 0.2}
_STRIP_JSON = [dict(zip(("strike", "call_bid", "call_ask", "put_bid", "put_ask"),
                        (q.strike, q.call_bid, q.call_ask, q.put_bid, q.put_ask))) for q in STRIP]


@pytest.mark.parametrize("operation,inputs,key", [
    ("vol.garch.loglik", {"returns": [0.01, -0.02], "omega": 1e-5, "alpha": 0.1, "beta": 0.8,
                          "initial_variance": "SAMPLE"}, "loglik"),
    ("vol.garch.fit", {"returns": _series(60), "initial_variance": 1e-4}, "loglik"),
    ("vol.varswap.fair_strike", {"as_of": "2026-11-06", "maturity": "2027-11-06", "spot": 100.0,
                                 "rate": 0.04, "dividend_yield": 0.01, "put_strikes": [90.0, 100.0],
                                 "call_strikes": [100.0, 110.0],
                                 "vols": [{"strike": k, "vol": 0.2} for k in (90.0, 100.0, 110.0)],
                                 "extension_step": 10.0, "variance_strike": 0.04,
                                 "variance_notional": 1e6}, "fair_vol"),
    ("vol.varswap.realized", {"prices": [100.0, 101.0, 99.0], "periods_per_year": 252,
                              "variance_strike": 0.04, "variance_notional": 1e6}, "payoff"),
    ("vol.vix.term_variance", {"minutes_to_expiry": 43200, "rate": 0.0, "strip": _STRIP_JSON},
     "strikes_used"),
    ("vol.vix.index", {"near": {"minutes_to_expiry": 40000, "rate": 0.0, "strip": _STRIP_JSON},
                       "next": {"minutes_to_expiry": 50000, "rate": 0.0, "strip": _STRIP_JSON}},
     "index"),
    ("vol.svi.fit_surface", {"expiry_years": [1.0], "log_moneyness": [-0.4, -0.2, 0.0, 0.2, 0.4],
                             "total_variance": [[SVI.total_variance(k)
                                                 for k in (-0.4, -0.2, 0.0, 0.2, 0.4)]],
                             "reject": False}, "slices"),
    ("vol.local.dupire", {"slices": [{"expiry_years": 1.0, "svi": _SVI_JSON}],
                          "points": [{"expiry_years": 0.5, "log_moneyness": 0.0}]}, "local_vol"),
])
def test_cli_more_operations(operation, inputs, key):
    r = run(operation, inputs)
    assert r["status"] == "ok" and key in r["outputs"], r
