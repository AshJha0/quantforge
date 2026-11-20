#!/usr/bin/env python3
"""Canonical bytes of the two daily ledgers, pinned (ruling KR-208).

  canonical_selftest.py            check every pin; exit 1 on the first difference
  canonical_selftest.py --print    print the values (to set the pins after a format change, before day 1)

Plain idea. A ledger row is hashed and published once, by an ubuntu runner, and can never be rewritten. So the
bytes a row turns into must not depend on the machine: not on its line endings, its locale, the order a
dictionary happens to have, or how its C library prints a number. This file builds fixed rows (invented values,
no market data) and compares their bytes and SHA-256 with values written down here. It uses the standard
library only and is run two ways: by pytest (python/tests/test_daily_jobs_bytes.py) and directly by the runner's
own `python3`, which is the interpreter the scheduled jobs start the tools with.

What it pins: key order, separators, ASCII escapes, the integer `seq`, decimal and binary64 number strings, the
row hash, the genesis row of each job's real configuration (so a configuration edit shows here before day 1), and
the bytes of a file written the way the writers write it. What it cannot pin: the numbers a fit or a bond price
produces. Those pass through `exp`, `log` and `pow`, and are covered by the paper ledger's golden hashes
(`test_goldens_pl_k`) and by the rebuild tolerances of KR-86 and KR-207.
"""
import hashlib
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "curve_daily"))
import curve_core as curve  # noqa: E402
import paper_core as paper  # noqa: E402

TS = "2027-01-04T23:45:00Z"
ODD = "café   tab\t quote\" back\\slash \x7f"  # every character must come out as ASCII

PINS = {
    "paper.small.line": '{"body":{"cause":"no_curve","date":"2027-01-04","list":["b","a",{"a":"2","z":"1"}],"note":"caf\\u00e9 \\u2028 tab\\t quote\\" back\\\\slash \\u007f","run":{"commit":"0000000000000000000000000000000000000000","impl":"python"}},"format":"qf-paper-ledger/1","hash":"fb9bf34dbab1442dfe9741114172679d1d0d3c1be732595a90a2148da568a1be","kind":"GAP","label":"paper marks on a fitted curve; not tradable","prev":"abababababababababababababababababababababababababababababababab","seq":7,"ts":"2027-01-04T23:45:00Z"}',
    "paper.small.hash": 'fb9bf34dbab1442dfe9741114172679d1d0d3c1be732595a90a2148da568a1be',
    "paper.genesis.hash": '8633f7ad65ae5777d1e2c03da62da21379b9039f4ffa93674aacf373dad53600',
    "paper.numbers": '0.30000000000000004|0.0000001|10000000000000000000000|0|4.81|0.3|0|0|99.92539|0|1.171875|0|1000|7349714.0625|0.01171875',
    "curve.small.line": '{"body":{"cause":"late_window","date":"2027-01-04","list":["b","a",{"a":"2","z":"1"}],"note":"caf\\u00e9 \\u2028 tab\\t quote\\" back\\\\slash \\u007f","run":{"commit":"0000000000000000000000000000000000000000","contract_version":"1.17.0","impl":"python"}},"format":"qf-curve-daily/1","hash":"698e6fc9caea75434b2126aa4ffebbc80e64ff82415faf9e5a2d87c3a4ab122b","kind":"GAP","label":"fitted to public US Treasury par yields with a library Nelson-Siegel fit; not an official curve","prev":"abababababababababababababababababababababababababababababababab","seq":7,"ts":"2027-01-04T23:45:00Z"}',
    "curve.small.hash": '698e6fc9caea75434b2126aa4ffebbc80e64ff82415faf9e5a2d87c3a4ab122b',
    "curve.genesis.hash": '27f997b9834ac5402046facb6f72185d8e910074ee42903c4c8c7fffac3a2543',
    "curve.config.sha256": 'd82f4b15e6c9da4fc80137d20585b4ba41694da4f49bd0c214be664f1caaf7f9',
    "curve.numbers": '0.30000000000000004|1e-07|1e+22|0.0|4.81|0.3333333333333333|5e-324|1.7976931348623157e+308|100.0|10.58',
    "file.sha256": 'c1db1275e60ea7a60a6015c327dd938c0f44c5261030504d677a3b0175197e91',
}


def values():
    out = {}
    pcfg = paper.load_config()
    body = {"date": "2027-01-04", "cause": "no_curve", "note": ODD, "list": ["b", "a", {"z": "1", "a": "2"}],
            "run": {"impl": "python", "commit": "0" * 40}}
    small = paper.make_row(7, TS, "GAP", pcfg["label"], body, "ab" * 32)
    out["paper.small.line"] = paper.line(small)
    out["paper.small.hash"] = small["hash"]
    out["paper.genesis.hash"] = paper.make_row(0, TS, "GENESIS", pcfg["label"], paper.genesis_body(pcfg),
                                               paper.GENESIS)["hash"]
    out["paper.numbers"] = "|".join([
        paper.fstr(0.1 + 0.2), paper.fstr(1e-7), paper.fstr(1e22), paper.fstr(-0.0), paper.fstr(4.81),
        paper.rstr(0.1 + 0.2, 6), paper.rstr(2.5e-7, 6), paper.rstr(3.5e-7, 6), paper.rstr(99.9253895, 6),
        paper.rstr(-1e-9, 6), paper.rstr(1.171875, 10), paper.plain(Decimal("-0.000")), paper.plain(Decimal("1E+3")),
        paper.plain(Decimal("7349714.062500")), paper.plain(Decimal("0.00390625") * 3)])
    ccfg = curve.load_config()
    cbody = {"date": "2027-01-04", "cause": "late_window", "note": ODD, "list": ["b", "a", {"z": "1", "a": "2"}],
             "run": {"impl": "python", "contract_version": "1.17.0", "commit": "0" * 40}}
    csmall = curve.make_row(7, TS, "GAP", ccfg, cbody, "ab" * 32)
    out["curve.small.line"] = curve.line(csmall)
    out["curve.small.hash"] = csmall["hash"]
    out["curve.genesis.hash"] = curve.make_row(0, TS, "GENESIS", ccfg,
                                               {"config": ccfg, "config_sha256": curve.config_sha(ccfg)},
                                               curve.GENESIS)["hash"]
    out["curve.config.sha256"] = curve.config_sha(ccfg)
    out["curve.numbers"] = "|".join([
        curve.fstr(0.1 + 0.2), curve.fstr(1e-7), curve.fstr(1e22), curve.fstr(-0.0), curve.fstr(4.81),
        curve.fstr(1 / 3), curve.fstr(5e-324), curve.fstr(1.7976931348623157e308), curve.fstr(100.0),
        curve.fstr(float("10.58"))])
    # a file written the way run_day.py writes it, read back as bytes
    text = paper.line(small) + "\n" + curve.line(csmall) + "\n"
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "ledger.jsonl"
        p.write_bytes(text.encode("ascii"))
        data = p.read_bytes()
        if paper.read_text(p) != text or curve.read_ledger(p) != text:
            raise RuntimeError("a ledger file does not read back as it was written")
    if b"\r" in data or not data.endswith(b"\n") or data.count(b"\n") != 2:
        raise RuntimeError("a ledger file was not written with bare line feeds")
    out["file.sha256"] = hashlib.sha256(data).hexdigest()
    return out


def imports_the_jobs_need():
    """The modules the scheduled tools load under the runner's own interpreter, apart from the CLI itself."""
    sys.path.insert(0, str(paper.ROOT / "tools" / "forward-log"))
    sys.path.insert(0, str(paper.ROOT / "tools" / "workflows"))
    sys.path.insert(0, str(paper.ROOT / "conformance" / "runner"))
    import anchor_evidence  # noqa: F401
    import common  # noqa: F401
    import forward_log  # noqa: F401
    from runner import resolve_command  # noqa: F401
    windows = paper.holdout_windows()
    if not windows or dict(curve.holdout_windows()) != dict(windows):
        raise RuntimeError("the prereg holdout windows could not be read, or the two tools read them differently")
    return sorted(windows)


def check():
    """List of differences from the pins; empty when every pin holds."""
    got = values()
    return [f"{k}: got {got[k]!r}, pinned {PINS[k]!r}" for k in PINS if got[k] != PINS[k]]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--print" in argv:
        for k, v in values().items():
            print(f'    "{k}": {v!r},')
        return 0
    bad = check()
    for b in bad:
        print(f"DIFFERENT: {b}", file=sys.stderr)
    studies = imports_the_jobs_need()
    print(f"python {sys.version.split()[0]} on {sys.platform}: {len(PINS) - len(bad)} of {len(PINS)} pins hold; "
          f"holdout windows read for {len(studies)} studies")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
