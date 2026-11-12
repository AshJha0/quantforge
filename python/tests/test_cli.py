"""The command-line contract, through a real process."""
import json
import subprocess
import sys

import pytest

from quantforge_core.cli.main import run_case
from quantforge_core.cli.operations import OPERATIONS

CMD = [sys.executable, "-m", "quantforge_core.cli.main"]
GOOD = (
    '{"schema_version":"1.0","case_id":"c1","operation":"core.daycount.year_fraction",'
    '"inputs":{"convention":"ACT_360","start":"2024-01-01","end":"2024-07-01"}}'
)


def call(*args, data=b""):
    return subprocess.run([*CMD, *args], input=data, capture_output=True, timeout=60, check=False)


def envelope(operation, inputs, case_id="c"):
    return json.dumps(
        {"schema_version": "1.0", "case_id": case_id, "operation": operation, "inputs": inputs}
    )


def code(text):
    return run_case(text)["error"]["code"]


def test_run_ok_exits_zero() -> None:
    p = call("run", data=GOOD.encode())
    assert p.returncode == 0
    assert json.loads(p.stdout)["outputs"] == {"year_fraction": 182 / 360}


def test_run_error_exits_two_with_unknown_case_id() -> None:
    p = call("run", data=b"{not json")
    assert p.returncode == 2
    result = json.loads(p.stdout)
    assert result["case_id"] == "unknown"
    assert result["error"]["code"] == "E_PARSE"


def test_batch_survives_a_bad_line_and_keeps_order() -> None:
    p = call("batch", data=GOOD.encode() + b"\nnonsense\n\xff\n" + GOOD.encode() + b"\n")
    assert p.returncode == 0
    statuses = [json.loads(line)["status"] for line in p.stdout.splitlines()]
    assert statuses == ["ok", "error", "error", "ok"]


def test_unknown_command_exits_64_with_empty_stdout() -> None:
    p = call("nope")
    assert p.returncode == 64
    assert p.stdout == b""


def test_version_and_operations() -> None:
    version = json.loads(call("version").stdout)
    assert version["contract_version"] == "1.11.0"  # ruling I-51
    assert version["language"] == "python"
    names = json.loads(call("operations").stdout)
    assert names == sorted(OPERATIONS)


def test_line_separators_in_output_stay_on_one_line() -> None:
    text = envelope("core.snapshot.hash", {"document_text": '{"a":" \u0085"}'})
    p = call("batch", data=text.encode() + b"\n")
    assert len(p.stdout.decode().splitlines()) == 1


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", "E_PARSE"),
        ('{"a":1,"a":2}', "E_PARSE"),
        ("[1]", "E_SCHEMA"),
        ('{"schema_version":"1.0","case_id":"c"}', "E_SCHEMA"),
        (envelope("core.nothing.here", {}), "E_UNSUPPORTED_OPERATION"),
        (envelope("Bad Name", {}), "E_SCHEMA"),
        (GOOD.replace('"2024-01-01"', "1e400"), "E_SCHEMA"),
        (envelope("core.rng.next_u64", {"seed": 1, "stream": 0, "count": 1}), "E_SCHEMA"),
        (envelope("core.calendar.holidays", {"calendar": "GBLO", "year": 2000.0}), "E_SCHEMA"),
        (envelope("core.stats.summary", {"x": [1.0, None]}), "E_SCHEMA"),
    ],
)
def test_envelope_and_type_errors(text, expected) -> None:
    assert code(text) == expected


def test_overflowing_result_is_non_finite() -> None:
    text = envelope("core.integrate.trapezoid", {"function": "exp", "a": 0, "b": 1000, "n": 2})
    assert code(text) == "E_NON_FINITE"


def test_no_state_between_cases() -> None:
    assert run_case(GOOD) == run_case(GOOD)
