"""Stage H wave 2 goldens: MBP book rebuild (ob_h) and the simulated lit matching engine (lit_h).

Specs: specifications/09-microstructure/order-book.md, specifications/10-execution/lit-matching.md,
section "Golden value cases (stage H wave 2, DR-H2 blind lane)". The inputs and expected outputs are
read from those tables exactly as written by the spec lane; no value is taken from an implementation.
The blind lane (program/STAGE_H_BLIND_WAVE2.md) re-derived 20/20 of them independently; ob_h-0001 and
lit_h-0001 were not blind (the source note prints the checksum; the case text hints at the fill).
As an extra independent check, every ob_h crc32 (and checksum_string, where emitted) is recomputed
here with zlib from the expected book, per [KR-CRC]. Synthetic message lists only (HR-41).

    cd oracle/python && uv run python -W ignore gen_stage_h_w2.py
"""
import json
import zlib
from decimal import Decimal

from qf_oracle import common
from qf_oracle.common import Suite, note

G = "oracle/python/gen_stage_h_w2.py"
FOLDER = "stage_h"
SPEC_OB = "specifications/09-microstructure/order-book.md"
SPEC_LIT = "specifications/10-execution/lit-matching.md"
BLIND = "blind-rederivation (DR-H2, program/STAGE_H_BLIND_WAVE2.md)"
NOT_BLIND = {
    "ob_h-0001": ["hand", "outside: [KR-CRC] printed checksum 3310070434"],
    "lit_h-0001": ["hand"],
}
OPS = {"ob_h": "micro.book.rebuild", "lit_h": "exec.sim.lit.run"}


def table(rel):
    rows, intable = [], False
    for line in (common.ROOT / rel).read_text(encoding="utf-8").splitlines():
        if line.startswith("| Case | Input | Expected |"):
            intable = True
            continue
        if intable and line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells[0].startswith(("ob_h-", "lit_h-")):
                rows.append((cells[0], json.loads(cells[1]), json.loads(cells[2])))
        elif intable:
            intable = False
    return rows


def component(text, decimals):
    v = Decimal(text)
    q = v.quantize(Decimal(1).scaleb(-decimals))
    assert q == v, text
    return format(q, "f").replace(".", "").lstrip("0") or "0"


def ob_check(cid, inp, exp):
    book = exp["book"]
    s = "".join(component(p, inp["price_decimals"]) + component(q, inp["qty_decimals"])
                for side in (book["asks"][:10], book["bids"][:10]) for p, q in side)
    assert (zlib.crc32(s.encode("ascii")) & 0xFFFFFFFF) == exp["crc32"], cid
    if "checksum_string" in exp:
        assert exp["checksum_string"] == s, cid


def lit_check(cid, exp):
    assert exp["label"] == "simulated venue; not a real exchange", cid
    for oid, c in exp["conservation"].items():
        out = sum(Decimal(c[k]) for k in ("filled", "resting", "cancelled", "rejected"))
        assert out == Decimal(c["submitted"]), (cid, oid)


def build():
    suites = []
    for name, spec in (("ob_h", SPEC_OB), ("lit_h", SPEC_LIT)):
        s = Suite(name, spec, G)
        for cid, inp, exp in table(spec):
            assert cid.startswith(name + "-")
            if name == "ob_h":
                ob_check(cid, inp, exp)
            else:
                lit_check(cid, exp)
            verified = NOT_BLIND.get(cid, ["hand", BLIND])
            s.add(OPS[name], inp, exp, cls="date_and_convention", verified=verified,
                  tags=["stage_h", "simulated" if name == "lit_h" else "microstructure"],
                  description=f"{cid} from the spec table" + ("; not blind" if cid in NOT_BLIND else ""))
            s.cases[-1]["case_id"] = cid  # spec ids (ob_h-0009 left the goldens, HR-41)
        add_errors(s, name)
        suites.append(s)
    return suites


def add_errors(s, name):
    """Error cases from the spec's Errors line (hand; not part of the blind lane)."""
    snap = {"type": "snapshot", "bids": [["100.0", "1.00000000"]], "asks": [], "checksum": None,
            "t": "2026-01-01T00:00:00Z"}
    ob = {"messages": [snap], "depth": 10, "price_decimals": 1, "qty_decimals": 8}
    lit = {"tick_size": "1", "lot_size": "1", "fee_schedule": {"maker_rebate": "0", "taker_fee": "0"}}
    buy = {"op": "NEW", "id": "B1", "trader": "T1", "side": "BUY", "type": "LIMIT", "price": "100", "qty": "10"}
    cases = {
        "ob_h": [
            ("depth not in the list", dict(ob, depth=20), "E_DOMAIN"),
            ("negative quantity", dict(ob, messages=[dict(snap, bids=[["100.0", "-1"]])]), "E_DOMAIN"),
            ("non-positive price", dict(ob, messages=[dict(snap, bids=[["0", "1"]])]), "E_DOMAIN"),
            ("price as a number, not a decimal string (HR-12)", dict(ob, messages=[dict(snap, bids=[[100.0, "1"]])]), "E_SCHEMA"),
            ("unknown message type", dict(ob, messages=[dict(snap, type="trade")]), "E_SCHEMA"),
        ],
        "lit_h": [
            ("price off the tick grid", dict(lit, events=[dict(buy, price="100.5")]), "E_DOMAIN"),
            ("non-positive quantity", dict(lit, events=[dict(buy, qty="0")]), "E_DOMAIN"),
            ("display_qty above quantity", dict(lit, events=[dict(buy, type="ICEBERG", display_qty="11")]), "E_DOMAIN"),
            ("duplicate id", dict(lit, events=[buy, dict(buy, price="99")]), "E_INPUT"),
        ],
    }[name]
    first = len(s.cases) + (2 if name == "ob_h" else 1)  # ob_h-0009 is retired (HR-41)
    for k, (desc, inp, code) in enumerate(cases):
        s.add(OPS[name], inp, error=code, cls="date_and_convention", verified=["hand"],
              tags=["stage_h", "error"], description=f"hand: {desc}")
        s.cases[-1]["case_id"] = f"{name}-{first + k:04d}"


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    for s in build():
        s.write()
    common.GOLDEN = keep


if __name__ == "__main__":
    main()
