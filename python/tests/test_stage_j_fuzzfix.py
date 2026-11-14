"""Stage J lane J-0b: rulings J-0b.1 (horizon limit), J-0b.2 (overflowing squared return), J-0b.3 (ragged rows)."""
import json

import pytest

from quantforge_core.cli.main import run_case


def status(op: str, inputs: str) -> str:
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": "c", "operation": op, "inputs": json.loads(inputs)}))
    return "ok" if r["status"] == "ok" else str(r["error"]["code"])


CASES = [
    ('vol.garch.forecast', '{"omega":5e-06,"alpha":0.12,"beta":0.82,"next_variance":0.0003,"horizon":100001,"periods_per_year":252.0}', 'E_LIMIT'),
    ('vol.garch.forecast', '{"omega":5e-06,"alpha":0.12,"beta":0.82,"next_variance":0.0003,"horizon":2147483648,"periods_per_year":252.0}', 'E_LIMIT'),
    ('vol.garch.estimate', '{"returns":[0.01,-0.012,0.01,-0.012,0.01,-2.6755826e+297,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012],"initial_variance":1e-4,"distribution":"NORMAL","demean":true}', 'E_NON_FINITE'),
    ('exotic.basket.moment', '{"forwards":[100.0,100.0],"weights":[0.5,0.5],"vols":[0.2,0.2],"correlation":[[1.0,1.0],[]],"strike":100.0,"expiry_years":1.0,"rate":0.03,"option_type":"CALL"}', 'E_INPUT'),
    ('exotic.basket.moment', '{"forwards":[100.0,100.0],"weights":[0.5,0.5],"vols":[0.2,0.2],"correlation":[[1.0],[0.0,1.0]],"strike":100.0,"expiry_years":1.0,"rate":0.03,"option_type":"CALL"}', 'E_INPUT'),
    ('exotic.basket.moment', '{"forwards":[100.0,100.0],"weights":[0.5,0.5],"vols":[0.2,0.2],"correlation":[[1.0,0.0],[0.0,1.0,0.0]],"strike":100.0,"expiry_years":1.0,"rate":0.03,"option_type":"CALL"}', 'E_INPUT'),
]


@pytest.mark.parametrize(("op", "inputs", "expected"), CASES)
def test_j0b_rulings(op: str, inputs: str, expected: str) -> None:
    assert status(op, inputs) == expected


def test_horizon_at_the_limit_is_accepted() -> None:
    assert status('vol.garch.forecast', '{"omega":5e-06,"alpha":0.12,"beta":0.82,"next_variance":0.0003,"horizon":100000,"periods_per_year":252.0}') == "ok"
