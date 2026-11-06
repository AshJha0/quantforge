"""Snapshot hash, data checks, timezones."""
import hashlib
import json
import struct
import subprocess
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from qf_oracle.common import Suite, note

G = "oracle/python/gen_data.py"
E = "date_and_convention"


def canon(v):
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        x = float(v) + 0.0
        if x == 0:
            x = 0.0
        return "#" + struct.pack(">d", x).hex()
    if isinstance(v, str):
        out = []
        for ch in v:
            if ch == '"':
                out.append('\\"')
            elif ch == "\\":
                out.append("\\\\")
            elif ord(ch) < 0x20:
                out.append(f"\\u{ord(ch):04x}")
            else:
                out.append(ch)
        return '"' + "".join(out) + '"'
    if isinstance(v, list):
        return "[" + ",".join(canon(a) for a in v) + "]"
    keys = sorted(v, key=lambda k: k.encode("utf-8"))
    return "{" + ",".join(canon(k) + ":" + canon(v[k]) for k in keys) + "}"


def snapshot():
    s = Suite("snapshot", "specifications/01-core/snapshot-hash.md", G)
    assert hashlib.sha256(b"abc").hexdigest() == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    op = "core.snapshot.hash"
    docs = ['{}', '{"b":1,"a":[true,null,"x\\n"]}', '{"a":1.0}', '{"a":1}', '{"a":1e0}', '{"a":-0.0}', '{"a":0.1,"b":1e-320,"c":1.7976931348623157e308}',
            '{"é":"é","z":"\\u00e9","e":"e\\u0301"}', '{"\\ud83d\\ude00":"😀","\\uffff":1,"a":"\\u007f"}', '{"snapshot_id":"sha256:ignored","x":[{"snapshot_id":"kept"}]}',
            '{"quotes":[{"instrument_id":"GBP-OIS-1Y","bid":0.0412,"ask":0.0414,"bid_size":null}],"as_of":"2026-11-06T16:00:00Z"}',
            '{ "spaced" : [ 1 , 2 ] }', '{"tab":"\\t","quote":"\\"","back":"\\\\","slash":"\\/"}', '{"a":1e-400}']
    for t in docs:
        v = json.loads(t)
        top = {k: x for k, x in v.items() if k != "snapshot_id"}
        c = canon(top)
        s.add(op, {"document_text": t}, {"canonical": c, "snapshot_id": "sha256:" + hashlib.sha256(c.encode("utf-8")).hexdigest()}, cls=E, verified=["oracle-canon", "sha256-nist-abc"])
    c = canon(json.loads(docs[1]))
    assert c == '{"a":[true,null,"x\\u000a"],"b":#3ff0000000000000}'
    sys_hash = subprocess.run(["sha256sum"], input=c.encode(), capture_output=True, check=True).stdout.split()[0].decode()
    assert sys_hash == hashlib.sha256(c.encode()).hexdigest()
    note("snapshot: hand-written canonical form matches; hashlib matches NIST abc and system sha256sum")
    for t, code in (('{"a":', "E_PARSE"), ('{"a":1,"a":2}', "E_PARSE"), ('{"a":{"b":1,"\\u0062":2}}', "E_PARSE"), ('{"a":1e400}', "E_SCHEMA"), ('{"a":"\\ud800"}', "E_SCHEMA"), ('[1]', "E_SCHEMA"), ('{"a":NaN}', "E_PARSE")):
        s.add(op, {"document_text": t}, error=code, cls=E, tags=["invalid"])
    s.write()


def q(i, t, b, a, st="FIRM"):
    return {"instrument_id": i, "event_time": t, "bid": b, "ask": a, "quote_status": st}


def data_checks():
    s = Suite("data_checks", "specifications/01-core/data-checks.md", G)
    op = "core.data.check_quotes"
    now = "2026-11-06T16:00:00Z"
    t0 = "2026-11-06T15:59:00Z"
    r = lambda i, st, *fl: {"instrument_id": i, "quote_status": st, "quality_flags": list(fl)}  # noqa: E731
    H = {"Z": [100.0, 100.5, 99.5, 100.2, 99.8, 100.1, 99.9]}  # median 100, MAD 0.2, scale 0.29652
    table = [
        (q("A", t0, 1.0, 1.1), {}, r("A", "FIRM")),
        (q("A", t0, 1.0, 1.1, "INDICATIVE"), {}, r("A", "INDICATIVE")),
        (q("A", t0, None, 1.1), {}, r("A", "MISSING", "MISSING_BID")),
        (q("A", t0, 1.0, None), {}, r("A", "MISSING", "MISSING_ASK")),
        (q("A", t0, None, None), {}, r("A", "MISSING", "MISSING_BID", "MISSING_ASK")),
        (q("A", t0, 1.2, 1.1), {}, r("A", "CROSSED", "CROSSED")),
        (q("A", t0, 1.1, 1.1), {}, r("A", "FIRM", "LOCKED")),
        (q("A", "2026-11-06T15:58:59Z", 1.0, 1.1), {}, r("A", "STALE", "STALE")),
        (q("A", "2026-11-06T15:59:00Z", 1.0, 1.1), {}, r("A", "FIRM")),
        (q("A", "2026-11-06T15:58:59Z", 1.0, 1.1, "INDICATIVE"), {}, r("A", "STALE", "STALE")),
        (q("A", "2026-11-06T15:58:59Z", 1.2, 1.1), {}, r("A", "CROSSED", "CROSSED", "STALE")),
        (q("A", "2026-11-06T15:58:59Z", None, 1.1), {}, r("A", "MISSING", "MISSING_BID")),
        (q("A", t0, 1.0, 1.2), {"max_relative_spread": 0.1}, r("A", "FIRM", "WIDE_SPREAD")),
        (q("A", t0, 1.0, 1.1), {"max_relative_spread": 0.1}, r("A", "FIRM")),
        (q("A", t0, -0.01, -0.005), {}, r("A", "FIRM")),
        (q("A", t0, -0.01, 0.5), {"positive_only": True}, r("A", "FIRM", "NON_POSITIVE")),
        (q("A", t0, None, 0.0), {"positive_only": True}, r("A", "MISSING", "MISSING_BID", "NON_POSITIVE")),
        (q("Z", t0, 101.3, 101.5), {"history": H}, r("Z", "FIRM")),
        (q("Z", t0, 101.5, 101.7), {"history": H}, r("Z", "FIRM", "OUTLIER")),
        (q("Z", t0, 98.3, 98.5), {"history": H}, r("Z", "FIRM", "OUTLIER")),
        (q("Z", t0, 150.0, 149.0), {"history": H}, r("Z", "CROSSED", "CROSSED")),
        (q("Z", t0, 101.5, 101.7), {"history": {"Z": H["Z"][:4]}}, r("Z", "FIRM")),
        (q("Z", t0, 200.0, 201.0), {"history": {"Z": [1.0] * 7}}, r("Z", "FIRM")),
    ]
    for quote, extra, res in table:
        s.add(op, {"as_of": now, "quotes": [quote], "stale_after_seconds": 60, **extra}, {"results": [res]}, cls=E, verified=["hand"])
    s.add(op, {"as_of": now, "quotes": [q("A", t0, 1.0, 1.1), q("B", t0, 2.0, 1.0)], "stale_after_seconds": 60}, {"results": [r("A", "FIRM"), r("B", "CROSSED", "CROSSED")]}, cls=E, verified=["hand"])
    s.add(op, {"as_of": now, "quotes": [q("A", "2026-11-06T16:00:01Z", 1.0, 1.1)], "stale_after_seconds": 60}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {"as_of": now, "quotes": [q("A", t0, 1.0, 1.1, "STALE")], "stale_after_seconds": 60}, error="E_SCHEMA", cls=E, tags=["invalid"])
    s.add(op, {"as_of": now, "quotes": [], "stale_after_seconds": 0}, error="E_INPUT", cls=E, tags=["invalid"])
    s.write()


def rule_offset(zone, u):
    """The rule table in timezone-and-cutoff.md, from first principles."""
    def lastsun(y, m):
        d = date(y + (m == 12), m % 12 + 1, 1) - timedelta(1)
        return d - timedelta((d.weekday() + 1) % 7)

    def nthsun(y, m, n):
        d = date(y, m, 1)
        return d + timedelta((6 - d.weekday()) % 7 + 7 * (n - 1))
    y = u.year
    if zone in ("UTC", "Asia/Tokyo"):
        return {"UTC": 0, "Asia/Tokyo": 32400}[zone]
    if zone == "America/New_York":
        a = datetime.combine(nthsun(y, 3, 2), datetime.min.time(), timezone.utc) + timedelta(hours=7)
        b = datetime.combine(nthsun(y, 11, 1), datetime.min.time(), timezone.utc) + timedelta(hours=6)
        return -14400 if a <= u < b else -18000
    a = datetime.combine(lastsun(y, 3), datetime.min.time(), timezone.utc) + timedelta(hours=1)
    b = datetime.combine(lastsun(y, 10), datetime.min.time(), timezone.utc) + timedelta(hours=1)
    base = 0 if zone == "Europe/London" else 3600
    return base + (3600 if a <= u < b else 0)


def z(u):
    return u.strftime("%Y-%m-%dT%H:%M:%SZ")


def time_cases():
    s = Suite("time", "specifications/01-core/timezone-and-cutoff.md", G)
    zones = ["UTC", "Europe/London", "Europe/Berlin", "America/New_York", "Asia/Tokyo"]
    checked = 0
    for zn in zones:
        tz = ZoneInfo(zn)
        u = datetime(2007, 1, 1, tzinfo=timezone.utc)
        while u.year < 2038:
            assert rule_offset(zn, u) == u.astimezone(tz).utcoffset().total_seconds(), (zn, u)
            checked += 1
            u += timedelta(minutes=30)
    note(f"time: rule table matches zoneinfo at {checked} half-hour instants, 2007 to 2037, five zones")
    for zn in zones:
        for u in (datetime(2024, 3, 31, 0, 59, 59), datetime(2024, 3, 31, 1, 0, 0), datetime(2024, 10, 27, 0, 59, 59), datetime(2024, 10, 27, 1, 0, 0),
                  datetime(2024, 3, 10, 6, 59, 59), datetime(2024, 3, 10, 7, 0, 0), datetime(2024, 11, 3, 5, 59, 59), datetime(2024, 11, 3, 6, 0, 0),
                  datetime(2007, 1, 1, 0, 0, 0), datetime(2037, 12, 31, 23, 59, 59)):
            uu = u.replace(tzinfo=timezone.utc)
            loc = uu.astimezone(ZoneInfo(zn))
            s.add("core.time.utc_offset", {"zone": zn, "instant": z(uu)}, {"offset_seconds": int(loc.utcoffset().total_seconds())}, cls=E, verified=["rules", "zoneinfo"])
            s.add("core.time.to_local", {"zone": zn, "instant": z(uu)}, {"local": loc.strftime("%Y-%m-%dT%H:%M:%S")}, cls=E, verified=["rules", "zoneinfo"])
    ti = "core.time.to_instant"
    s.add(ti, {"zone": "Europe/London", "local": "2024-07-01T12:00:00"}, {"instant": "2024-07-01T11:00:00Z"}, cls=E, verified=["hand"])
    s.add(ti, {"zone": "Europe/London", "local": "2024-07-01T12:00:00", "overlap": "LATER"}, {"instant": "2024-07-01T11:00:00Z"}, cls=E, verified=["hand"])
    s.add(ti, {"zone": "America/New_York", "local": "2024-01-15T09:30:00"}, {"instant": "2024-01-15T14:30:00Z"}, cls=E, verified=["hand"])
    s.add(ti, {"zone": "Europe/London", "local": "2024-03-31T01:30:00"}, error="E_NONEXISTENT_LOCAL_TIME", cls=E, tags=["invalid"])
    s.add(ti, {"zone": "America/New_York", "local": "2024-03-10T02:30:00"}, error="E_NONEXISTENT_LOCAL_TIME", cls=E, tags=["invalid"])
    s.add(ti, {"zone": "Europe/London", "local": "2024-10-27T01:30:00"}, error="E_AMBIGUOUS_LOCAL_TIME", cls=E, tags=["invalid"])
    s.add(ti, {"zone": "Europe/London", "local": "2024-10-27T01:30:00", "overlap": "EARLIER"}, {"instant": "2024-10-27T00:30:00Z"}, cls=E, verified=["hand"])
    s.add(ti, {"zone": "Europe/London", "local": "2024-10-27T01:30:00", "overlap": "LATER"}, {"instant": "2024-10-27T01:30:00Z"}, cls=E, verified=["hand"])
    s.add(ti, {"zone": "America/New_York", "local": "2024-11-03T01:30:00", "overlap": "EARLIER"}, {"instant": "2024-11-03T05:30:00Z"}, cls=E, verified=["hand"])
    s.add(ti, {"zone": "America/New_York", "local": "2024-11-03T01:30:00", "overlap": "LATER"}, {"instant": "2024-11-03T06:30:00Z"}, cls=E, verified=["hand"])
    bd = "core.time.business_date"
    for inst, zn, cut, cal, res in (("2024-07-01T14:59:59Z", "Europe/London", "16:00", "GBLO", "2024-07-01"), ("2024-07-01T15:00:00Z", "Europe/London", "16:00", "GBLO", "2024-07-02"),
                                    ("2024-01-15T15:59:59Z", "Europe/London", "16:00", "GBLO", "2024-01-15"), ("2024-01-15T16:00:00Z", "Europe/London", "16:00", "GBLO", "2024-01-16"),
                                    ("2024-03-29T10:00:00Z", "Europe/London", "16:00", "GBLO", "2024-04-02"), ("2024-07-06T10:00:00Z", "Europe/London", "16:00", "GBLO", "2024-07-08"),
                                    ("2024-07-05T22:00:00Z", "America/New_York", "17:00", "USGS", "2024-07-08"), ("2024-07-05T20:59:59Z", "America/New_York", "17:00", "USGS", "2024-07-05"),
                                    ("2024-12-31T23:30:00Z", "Asia/Tokyo", "15:00", "EUTA", "2025-01-02")):
        s.add(bd, {"instant": inst, "zone": zn, "cutoff": cut, "calendar": cal}, {"date": res}, cls=E, verified=["hand"])
    s.add(bd, {"instant": "2024-07-01T15:00:00Z", "zone": "Europe/London", "cutoff": "25:00", "calendar": "GBLO"}, error="E_SCHEMA", cls=E, tags=["invalid"])
    s.add("core.time.utc_offset", {"zone": "Mars/Base", "instant": "2024-07-01T15:00:00Z"}, error="E_SCHEMA", cls=E, tags=["invalid"])
    s.add("core.time.utc_offset", {"zone": "UTC", "instant": "2006-12-31T23:59:59Z"}, error="E_DATE_RANGE", cls=E, tags=["invalid"])
    s.add("core.time.utc_offset", {"zone": "UTC", "instant": "2024-07-01T15:00:00.5Z"}, error="E_SCHEMA", cls=E, tags=["invalid"])
    s.write()


def main():
    snapshot()
    data_checks()
    time_cases()


if __name__ == "__main__":
    main()
