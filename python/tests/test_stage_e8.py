"""Stage E, E8 unit tests: worked examples and identities from
04-pricing/credit-options-and-copulas.md, with SciPy as a second check on the distributions."""
import itertools
import json
import math
from datetime import date

import pytest
from scipy import stats

from quantforge_core import credit_options as ce
from quantforge_core.cli.main import run_case
from quantforge_core.errors import QfError

DATES = (date(2026, 11, 6), date(2027, 3, 20), date(2032, 3, 20))
MARKET = (*DATES, 0.035, 0.02, 0.4)


def code(f, *args):
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code


def test_cds_option_worked_example() -> None:
    out = ce.cds_option_price(*MARKET, "PAYER", 0.012, 1e7, 0.5, True)
    assert out["forward_spread"] == pytest.approx(0.0118877, abs=1e-7)
    assert out["risky_annuity"] == pytest.approx(4.32865, abs=1e-5)
    assert out["price"] == pytest.approx(59847.84, abs=0.01)
    assert out["front_end_protection"] == pytest.approx(43333.06, abs=0.01)
    live = ce.cds_option_price(*MARKET, "PAYER", 0.012, 1e7, 0.5, False)
    assert live["price"] == pytest.approx(out["price"] + out["front_end_protection"])
    receiver = ce.cds_option_price(*MARKET, "RECEIVER", 0.012, 1e7, 0.5, False)
    parity = 1e7 * out["risky_annuity"] * (out["forward_spread"] - 0.012)
    assert out["price"] - receiver["price"] == pytest.approx(parity, abs=1e-6)


def test_cds_option_implied_round_trip_and_errors() -> None:
    price = ce.cds_option_price(*MARKET, "RECEIVER", 0.0096, 1e7, 0.4, True)["price"]
    assert ce.cds_option_implied(*MARKET, "RECEIVER", 0.0096, 1e7, price, True) == \
        pytest.approx(0.4, rel=1e-10)
    f = ce.cds_option_implied
    assert code(f, *MARKET, "PAYER", 0.012, 1e7, 1e4, False) == "E_INPUT"
    assert code(f, *MARKET, "PAYER", 0.012, 1e7, 0.0, True) == "E_DOMAIN"
    assert code(f, *MARKET, "PAYER", 0.012, 1e7, 1e9, True) == "E_DOMAIN"
    p = ce.cds_option_price
    a, e, m = DATES
    assert code(p, a, a, m, 0.03, 0.02, 0.4, "PAYER", 0.01, 1e7, 0.5, True) == "E_INPUT"
    assert code(p, a, e, e, 0.03, 0.02, 0.4, "PAYER", 0.01, 1e7, 0.5, True) == "E_INPUT"
    assert code(p, a, e, m, 0.03, 0.02, 1.0, "PAYER", 0.01, 1e7, 0.5, True) == "E_DOMAIN"
    assert code(p, a, e, m, 0.03, -0.02, 0.4, "PAYER", 0.01, 1e7, 0.5, True) == "E_DOMAIN"
    assert code(p, a, e, m, 0.03, 0.02, 0.4, "PAYER", 0.0, 1e7, 0.5, True) == "E_DOMAIN"
    assert code(p, a, e, m, 0.03, 0.02, 0.4, "PAYER", 0.01, 1e7, -0.5, True) == "E_DOMAIN"


@pytest.mark.parametrize("x,nu", [(-3.0, 3.0), (-0.5, 4.0), (0.0, 5.0), (1.7, 2.5), (6.0, 10.0)])
def test_t_distribution_against_scipy(x, nu) -> None:
    assert ce.t_cdf(x, nu) == pytest.approx(stats.t.cdf(x, nu), rel=1e-12, abs=1e-15)
    assert ce.t_pdf(x, nu) == pytest.approx(stats.t.pdf(x, nu), rel=1e-12)
    p = stats.t.cdf(x, nu)
    assert ce.t_inverse(p, nu) == pytest.approx(x, abs=1e-10)


@pytest.mark.parametrize("h,k,rho", [(-2.0, -1.8, 0.3), (0.5, -0.2, -0.6), (-1.0, 1.0, 0.9),
                                     (60.0, 0.3, 0.2)])
def test_bivariate_normal_against_scipy(h, k, rho) -> None:
    ref = stats.multivariate_normal(mean=[0, 0], cov=[[1, rho], [rho, 1]]).cdf([min(h, 40), k])
    assert ce.bivariate_normal(h, k, rho) == pytest.approx(ref, rel=1e-6, abs=1e-12)
    assert ce.bivariate_normal(-50.0, k, rho) == 0.0


def test_copulas() -> None:
    g = ce.joint_default("GAUSSIAN", [0.02, 0.03], 0.3, None)
    assert g["joint_default_probability"] == pytest.approx(0.002288, abs=1e-6)
    t = ce.joint_default("STUDENT_T", [0.02, 0.03], 0.3, 4.0)
    assert t["joint_default_probability"] == pytest.approx(0.005102, abs=1e-6)
    zero = ce.joint_default("GAUSSIAN", [0.02, 0.03], 0.0, None)
    assert zero["joint_default_probability"] == pytest.approx(0.0006, rel=1e-12)
    assert zero["default_correlation"] == pytest.approx(0.0, abs=1e-12)
    assert ce.joint_default("STUDENT_T", [0.1, 0.15], 0.0, 5.0)["default_correlation"] > 0
    f = ce.joint_default
    assert code(f, "GAUSSIAN", [0.02], 0.3, None) == "E_INPUT"
    assert code(f, "STUDENT_T", [0.02, 0.03], 0.3, None) == "E_INPUT"
    assert code(f, "GAUSSIAN", [0.0, 0.03], 0.3, None) == "E_DOMAIN"
    assert code(f, "GAUSSIAN", [0.02, 0.03], 1.0, None) == "E_DOMAIN"
    assert code(f, "STUDENT_T", [0.02, 0.03], 0.3, 0.0) == "E_DOMAIN"


def test_lhp_tranches_add_up_to_pool_loss() -> None:
    points = [0.0, 0.03, 0.07, 0.10, 0.15, 0.30, 1.0]
    losses = [ce.tranche_loss(0.05, 0.3, 0.4, a, d) for a, d in itertools.pairwise(points)]
    assert losses[0] == pytest.approx(0.5411, abs=1e-4)
    weighted = sum(x * (d - a) for x, a, d in zip(losses, points, points[1:]))
    assert weighted == pytest.approx(0.6 * 0.05, abs=1e-14)
    cdf = ce.loss_cdf(0.05, 0.3, 0.4, [0.01, 0.05, 0.2])
    assert cdf == sorted(cdf) and 0 < cdf[0] < cdf[-1] < 1
    f = ce.tranche_loss
    assert code(f, 0.05, 0.3, 0.4, 0.1, 0.1) == "E_INPUT"
    assert code(f, 0.05, 0.3, 0.4, -0.1, 0.1) == "E_INPUT"
    assert code(f, 0.05, 0.3, 0.4, 0.1, 1.1) == "E_INPUT"
    assert code(f, 0.0, 0.3, 0.4, 0.0, 0.1) == "E_DOMAIN"
    assert code(f, 0.05, 1.0, 0.4, 0.0, 0.1) == "E_DOMAIN"
    assert code(f, 0.05, 0.3, 1.0, 0.0, 0.1) == "E_DOMAIN"
    assert code(ce.loss_cdf, 0.05, 0.3, 0.4, [0.6]) == "E_DOMAIN"
    assert ce._capped_mean(0.05, 0.3, 0.0) == 0.0


@pytest.mark.parametrize("operation,inputs,key", [
    ("credit.cdsoption.price", {"as_of": "2026-11-06", "expiry": "2027-03-20",
                                "maturity": "2032-03-20", "rate": 0.035, "hazard_rate": 0.02,
                                "recovery": 0.4, "type": "PAYER", "strike": 0.012,
                                "notional": 1e7, "vol": 0.5, "knock_out": True}, "price"),
    ("credit.cdsoption.implied_vol", {"as_of": "2026-11-06", "expiry": "2027-03-20",
                                      "maturity": "2032-03-20", "rate": 0.035,
                                      "hazard_rate": 0.02, "recovery": 0.4, "type": "PAYER",
                                      "strike": 0.012, "notional": 1e7, "premium": 59847.84,
                                      "knock_out": True}, "vol"),
    ("credit.copula.joint_default", {"copula": "STUDENT_T", "default_probabilities": [0.02, 0.03],
                                     "correlation": 0.3, "degrees_of_freedom": 4},
     "default_correlation"),
    ("credit.lhp.tranche_loss", {"default_probability": 0.05, "correlation": 0.3,
                                 "recovery": 0.4, "attachment": 0.03, "detachment": 0.07},
     "expected_loss_fraction"),
    ("credit.lhp.loss_cdf", {"default_probability": 0.05, "correlation": 0.3, "recovery": 0.4,
                             "losses": [0.01]}, "cdf"),
])
def test_cli(operation, inputs, key) -> None:
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": "t", "operation": operation,
                             "inputs": inputs}))
    assert r["status"] == "ok" and key in r["outputs"], r
    assert math.isfinite(json.dumps(r["outputs"]).count("e") + 0.0)
