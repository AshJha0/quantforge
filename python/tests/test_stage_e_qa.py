"""Stage E quality pass: domain errors the earlier suites missed, plus identities checked by hand."""
import itertools
import math

import pytest

from quantforge_core import arb_surface, correlation, credit_options, rates_vol
from quantforge_core.errors import QfError


def error_of(f, *args):
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code, e.value.field


def test_implied_correlation_rejects_a_zero_index_vol():
    assert error_of(correlation.implied, [0.5, 0.5], [0.2, 0.3], 0.0) == ("E_DOMAIN", "index_vol")


def test_implied_correlation_is_one_when_index_vol_is_the_weighted_vol():
    # Two names at 20% and 30%, equal weights: perfect correlation gives an index vol of 25%.
    assert correlation.implied([0.5, 0.5], [0.2, 0.3], 0.25) == pytest.approx(1.0, abs=1e-12)


def test_implied_correlation_is_zero_for_the_independent_index_vol():
    index_vol = math.sqrt(0.25 * 0.04 + 0.25 * 0.09)
    assert correlation.implied([0.5, 0.5], [0.2, 0.3], index_vol) == pytest.approx(0.0, abs=1e-12)


def test_loss_cdf_rejects_an_empty_loss_list():
    assert error_of(credit_options.loss_cdf, 0.02, 0.3, 0.4, []) == ("E_INPUT", "losses")


def test_loss_cdf_rises_and_stays_within_zero_and_one():
    cdf = credit_options.loss_cdf(0.05, 0.3, 0.4, [0.001, 0.01, 0.05, 0.2, 0.59])
    assert all(0.0 <= c <= 1.0 for c in cdf)
    assert all(a <= b + 1e-12 for a, b in itertools.pairwise(cdf))


def test_bond_future_options_satisfy_put_call_parity():
    f, k, t, df, vol = 112.0, 110.0, 0.5, 0.98, 0.07
    call, _ = rates_vol.bondfut_price("CALL", f, k, t, df, vol, 100_000)
    put, _ = rates_vol.bondfut_price("PUT", f, k, t, df, vol, 100_000)
    assert call - put == pytest.approx(df * (f - k), abs=1e-10)


def test_bond_future_premium_scales_by_contract_size_over_100():
    price, premium = rates_vol.bondfut_price("CALL", 112.0, 110.0, 0.5, 0.98, 0.07, 100_000)
    assert premium == pytest.approx(price * 1000.0)


def test_bond_future_implied_rejects_a_bad_yield_or_duration_after_the_premium_check():
    good = ("CALL", 112.0, 110.0, 0.5, 0.98, 2.5)
    assert error_of(rates_vol.bondfut_implied, *good, 0.0, 7.0) == ("E_DOMAIN", "ctd_yield")
    assert error_of(rates_vol.bondfut_implied, *good, 0.04, 0.0) == (
        "E_DOMAIN", "ctd_modified_duration")
    # A premium below intrinsic is reported first, whatever the yield.
    assert error_of(rates_vol.bondfut_implied, "CALL", 112.0, 110.0, 0.5, 0.98, 1.0, 0.0, 0.0) == (
        "E_DOMAIN", "premium")


def test_forward_vols_reject_a_first_expiry_at_zero():
    assert error_of(arb_surface.forward_vols, [0.0, 1.0], [0.2, 0.2]) == ("E_DOMAIN", "expiry_years")


def test_forward_vols_of_a_flat_term_structure_are_flat():
    assert arb_surface.forward_vols([0.5, 1.0, 2.0], [0.2, 0.2, 0.2]) == pytest.approx([0.2] * 3)


def test_forward_vol_by_hand():
    # Total variance 0.04 at 1y and 0.18 at 2y: forward variance 0.14 over one year.
    assert arb_surface.forward_vols([1.0, 2.0], [0.2, 0.3]) == pytest.approx([0.2, math.sqrt(0.14)])
