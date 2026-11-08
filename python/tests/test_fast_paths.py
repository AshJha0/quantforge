"""The R2 speed-ups must give the same bits as the plain code they replace."""
import random

from quantforge_core import _cal, rng, strictjson
from quantforge_core.errors import QfError


def _stepped(seed, stream, skip, count):
    g = rng.Xoshiro256(rng._splitmix_words(seed, 4))
    for _ in range(stream):
        g.jump()
    for _ in range(skip):
        g.next_u64()
    return [g.next_u64() for _ in range(count)]


def test_polynomial_advance_matches_stepping():
    for seed, stream, skip in [(1, 0, 0), (7, 0, 511), (7, 0, 512), (7, 3, 0), (2**64 - 1, 1023, 9999),
                               (42, 1, 70000)]:
        assert rng.next_u64(seed, stream, 4, skip) == _stepped(seed, stream, skip, 4)


def test_batch_normals_match_single_draws():
    a, b = rng.Xoshiro256.seeded(3, 2), rng.Xoshiro256.seeded(3, 2)
    assert [a.normal() for _ in range(2000)] == b.normals(2000)
    assert a.s == b.s


def _old_depth_ok(text, limit):
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"':
            i += 1
            while i < len(text) and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
        elif ch in "[{":
            depth += 1
            if depth > limit:
                return False
        elif ch in "]}":
            depth -= 1
        i += 1
    return True


def test_depth_scan_matches_character_scan():
    r = random.Random(5)
    for _ in range(50000):
        text = "".join(r.choice('[]{}"\a,') for _ in range(r.randint(0, 30)))
        limit = r.randint(0, 5)
        try:
            strictjson.check_depth(text, limit)
            ok = True
        except QfError:
            ok = False
        assert ok == _old_depth_ok(text, limit), (text, limit)


def test_int_parsing_and_overflow():
    assert strictjson.parse("1" * 299) == (int("1" * 299), False)
    assert strictjson.parse("9" * 400)[1] is True
    assert strictjson.parse("-17") == (-17, False)


def test_cal_shim_matches_stdlib():
    import calendar
    for y in (1900, 2000, 2023, 2024, 2100):
        assert _cal.isleap(y) == calendar.isleap(y)
        for m in range(1, 13):
            assert _cal.monthrange(y, m) == calendar.monthrange(y, m)
