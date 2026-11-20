"""KF-1 (stage K round 1 follow-up audit): every `limits_first` library entry point accepts its
arguments by keyword. The guard used to pass the caller's keywords to the size check, whose own
signature named only its first parameter, so a keyword call raised a raw TypeError."""

from __future__ import annotations

import pytest

from quantforge_core import stage_k
from quantforge_core.errors import QfError

POS = stage_k.ZeroPosition(notional=100.0, maturity=2.0, yield_=0.03)


def test_bitemporal_query_by_keyword() -> None:
    assert stage_k.bitemporal_query(records=[], series_id="a", knowledge_as_of=1, valid_at=1) == (
        "NONE",
        None,
    )
    assert stage_k.bitemporal_query([], series_id="a", knowledge_as_of=1, valid_at=1)[0] == "NONE"


def test_par_annual_by_keyword() -> None:
    assert stage_k.par_annual(quotes=[0.01, 0.02]) == stage_k.par_annual([0.01, 0.02])


def test_incremental_update_by_keyword() -> None:
    q = [0.01, 0.02]
    dfs = stage_k.par_annual(q)["discount_factors"]
    by_kw = stage_k.incremental_update(previous_quotes=q, previous_dfs=dfs, new_quotes=[0.01, 0.03])
    assert by_kw == stage_k.incremental_update(q, dfs, [0.01, 0.03])


def test_trigger_check_by_keyword() -> None:
    args = {"x_ref": 0.0, "x_now": 1.0, "days_since": 1.0, "k": 3.0}
    want = stage_k.trigger_check([1.0, 2.0, 4.0], 0.0, 1.0, 1.0, 3.0)
    assert stage_k.trigger_check(changes=[1.0, 2.0, 4.0], **args) == want
    assert stage_k.trigger_check([1.0, 2.0, 4.0], 0.0, 1.0, days_since=1.0, k=3.0) == want


def test_delta_gamma_bound_by_keyword() -> None:
    want = stage_k.delta_gamma_bound([POS], 0.001)
    assert stage_k.delta_gamma_bound(positions=[POS], shift=0.001) == want
    assert stage_k.delta_gamma_bound([POS], shift=0.001) == want


def test_keyword_call_keeps_limit_before_finite_rule() -> None:
    # KR-230 order holds for a keyword call too: E_LIMIT before the finite rule.
    big = [0.0] * (stage_k.MAX_CHANGES + 1)
    with pytest.raises(QfError) as e:
        stage_k.trigger_check(changes=big, x_ref=float("nan"), x_now=1.0, days_since=1.0, k=3.0)
    assert e.value.code == "E_LIMIT"


def test_a_missing_argument_names_the_public_function() -> None:
    """KF-16: omitting the checked argument raises the TypeError Python gives, naming `trigger_check`, not the
    private limit check."""
    with pytest.raises(TypeError, match=r"^trigger_check\(\) missing"):
        stage_k.trigger_check()  # type: ignore[call-arg]
    with pytest.raises(TypeError, match=r"^trigger_check\(\) missing"):
        stage_k.trigger_check(x_ref=1.0, x_now=1.0, days_since=1.0, k=3.0)  # type: ignore[call-arg]


def test_limit_check_reaches_a_wrapper_that_hides_parameter_names() -> None:
    """mutmut replaces each function by a (*args, **kwargs) trampoline; the guard must still pass the caller's
    arguments to the limit check (PR #59 mutation job: "the unmutated build does not pass")."""
    from quantforge_core import finite

    seen: list[tuple[object, ...]] = []

    def real_check(xs: list[float], k: float) -> None:
        seen.append((xs, k))
        if len(xs) > 2:
            raise QfError("E_LIMIT", "too many")

    def real(xs: list[float], k: float) -> float:
        return sum(xs) * k

    def check_tramp(*args: object, **kwargs: object) -> None:
        real_check(*args, **kwargs)  # type: ignore[arg-type]

    def tramp(*args: object, **kwargs: object) -> float:
        return real(*args, **kwargs)  # type: ignore[arg-type]

    finite.limits_first(check_tramp)(tramp)
    wrapped = finite._wrap(tramp)
    assert wrapped([1.0, 2.0], 3.0) == 9.0
    assert seen == [([1.0, 2.0], 3.0)]
    with pytest.raises(QfError) as e:
        wrapped([1.0, 2.0, 3.0], 1.0)
    assert e.value.code == "E_LIMIT"
