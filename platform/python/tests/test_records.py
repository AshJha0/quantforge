"""KR-270, KR-271, KR-283: the round-trip records, the content hash, and the verdicts with planted faults."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

from quantforge_adapters import records
from quantforge_adapters.records import Verdict

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "datasets" / "adapters" / "records-10000.jsonl"


@pytest.fixture(scope="module")
def rows() -> list[records.Record]:
    return records.load(DATA)


def test_canon_worked_example() -> None:
    rec = {"seq": 1, "kind": "quote", "body": {"bid": "101.25", "ask": "101.26"}}
    form = records.canon(rec)
    literal = b'{"body":{"ask":"101.26","bid":"101.25"},"kind":"quote","seq":#3ff0000000000000}'
    assert form == literal and len(form) == 79
    h = records.content_hash([rec], n=1)
    assert h == hashlib.sha256(literal + b"\n").hexdigest()
    print("adapters.md 1.2 worked example H =", h)


def test_dec() -> None:
    assert records.dec(1012500, 4) == "101.2500"
    assert records.dec(-5, 2) == "-0.05"
    assert records.dec(0, 6) == "0.000000"


def test_records_file_matches_its_sum_and_rules(rows: list[records.Record]) -> None:
    lines = (DATA.with_suffix(".sha256")).read_text(encoding="utf-8").split("\n")
    assert hashlib.sha256(DATA.read_bytes()).hexdigest() == lines[0].split()[0]
    assert records.content_hash(rows) == lines[1].split()[1]
    assert [r["seq"] for r in rows] == list(range(1, 10_001))
    assert all(r["kind"] == records.KINDS[r["seq"] % 4] for r in rows)
    assert max(len(records.canon(r)) for r in rows) <= 512
    assert all(isinstance(r["body"]["value"], float) and 0 <= r["body"]["value"] < 1 for r in rows)


def test_canonical_matches_the_library(rows: list[records.Record]) -> None:
    """KR-283: the services' canonical form is the library's, byte for byte, over every record."""
    lib = pytest.importorskip("quantforge_core.snapshot")
    for r in rows:
        assert records.canonical(r) == lib.canonical(r)


def test_records_regenerate_from_the_library_rng(rows: list[records.Record]) -> None:
    rng = pytest.importorskip("quantforge_core.rng")
    assert records.make_records(rng.next_u64, n=200) == rows[:200]


def test_from_canon_inverts_canon(rows: list[records.Record]) -> None:
    for r in rows[:500]:
        back = records.from_canon(records.canon(r))
        assert records.canon(back) == records.canon(r)
    odd = {"seq": 2, "kind": "x", "body": {"s": 'a"b\\c\né', "l": [None, True, False, -0.0, 1e300]}}
    assert records.canon(records.from_canon(records.canon(odd))) == records.canon(odd)
    with pytest.raises(ValueError):
        records.from_canon(b'{"a":1}x')


# ---- planted faults of adapters.md 1.4 ----------------------------------------------------------------------

def _copy(rows: list[records.Record]) -> list[records.Record]:
    return json.loads(json.dumps(rows))


def test_pass(rows: list[records.Record]) -> None:
    assert records.verdict(rows, _copy(rows), store_count=10_000) == "PASS"


@pytest.mark.parametrize("plant,code", [
    ("drop", "COUNT"), ("duplicate", "COUNT"), ("byte", "HASH"), ("float", "HASH"), ("reorder", "PASS"),
    ("bypass", "BYPASS"),
])
def test_planted_faults(rows: list[records.Record], plant: str, code: str) -> None:
    from quantforge_adapters.smoke import apply_plant

    read, count = apply_plant(plant, _copy(rows), 10_000)
    if code == "PASS":
        assert records.verdict(rows, read, store_count=count) == "PASS"
        return
    with pytest.raises(Verdict) as err:
        records.verdict(rows, read, store_count=count)
    assert err.value.code == code


def test_extra_and_bad_seq_count(rows: list[records.Record]) -> None:
    bad = _copy(rows)
    bad[0]["seq"] = 10_001
    with pytest.raises(Verdict, match="COUNT"):
        records.content_hash(bad)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
