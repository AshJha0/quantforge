#!/usr/bin/env python3
"""Write (or check) the hand-built simulated feed fixtures of specifications/12-platform/adapters.md §3.

Standard library only, and deliberately independent of the codec in platform/python: the bytes below are the
hex strings derived by hand in the spec, copied here verbatim; this script only writes them to
datasets/feeds/<format>/<name>.bin with a JSON sidecar, and builds datasets/feeds/malformed.json by explicit
byte edits of those fixtures. Label on every file: simulated; not a certified implementation; not connected to
any venue.

    python tools/adapters/build_feed_fixtures.py          # write
    python tools/adapters/build_feed_fixtures.py --check  # fail if any file differs
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "datasets" / "feeds"
LABEL = "simulated; not a certified implementation; not connected to any venue"
TOKEN = "QF0000000001  "
STOCK = "QFSIM   "

ITCH_ADD = "41000100001f1aced9f00000000000000000014200000064514653494d202020000f7314"
ITCH_EXEC = "45000100001f1aced9f3e80000000000000001000000280000000000000007"
ITCH_CANCEL = "58000100001f1aced9f7d000000000000000010000000a"
ITCH_DELETE = "44000100001f1aced9fbb80000000000000001"
OUCH_ENTER = "4f51463030303030303030303120204200000064514653494d202020000f7314000000002020202059504e000000004e20"
OUCH_CANCEL = "58514630303030303030303031202000000000"
FIX_HB = "383d514653494d2e3101393d32340133353d300133343d310134393d5146410135363d5146420131303d32323701"
FIX_NOS = ("383d514653494d2e3101393d36370133353d440133343d320134393d5146410135363d5146420131313d5146310135353d51"
           "4653494d0135343d310133383d3130300134303d320134343d3130312e32350131303d30363601")
FAST_TWO = "fc818151465349cd3d6694e43d66f801c88400e400e402ac"
MOLD_HDR = "514653494d3030303031"  # session QFSIM00001

QUOTE1 = {"template": 1, "seq": 1, "symbol": "QFSIM", "bid_px": 1012500, "bid_size": 100,
          "ask_px": 1012600, "ask_size": 200}
QUOTE2 = {"template": 1, "seq": 2, "symbol": "QFSIM", "bid_px": 1012600, "bid_size": 100,
          "ask_px": 1012700, "ask_size": 300}
ENTER = {"type": "O", "token": TOKEN, "side": "B", "shares": 100, "stock": STOCK, "price": 1012500,
         "time_in_force": 0, "firm": "    ", "display": "Y", "capacity": "P", "sweep": "N",
         "min_qty": 0, "cross_type": "N", "customer_type": " "}
CANCEL = {"type": "X", "token": TOKEN, "shares": 0}

FIXTURES = {
    # name: (format, hex, fields, spec section)
    "fix/heartbeat_1": ("QF-FIX-S", FIX_HB, {"msg_type": "0", "seq": 1, "sender": "QFA", "target": "QFB",
                                             "body": []}, "3.1"),
    "fix/new_order_1": ("QF-FIX-S", FIX_NOS, {"msg_type": "D", "seq": 2, "sender": "QFA", "target": "QFB",
                                              "body": [[11, "QF1"], [55, "QFSIM"], [54, "1"], [38, "100"],
                                                       [40, "2"], [44, "101.25"]]}, "3.1"),
    "itch/system_event_O": ("QF-ITCH-S", "53000000000d18c2e280004f",
                            {"type": "S", "locate": 0, "tracking": 0, "timestamp": 14400000000000,
                             "event": "O"}, "3.2"),
    "itch/add_order_1": ("QF-ITCH-S", ITCH_ADD,
                         {"type": "A", "locate": 1, "tracking": 0, "timestamp": 34200000000000, "order_ref": 1,
                          "side": "B", "shares": 100, "stock": STOCK, "price": 1012500}, "3.2"),
    "itch/order_executed_1": ("QF-ITCH-S", ITCH_EXEC,
                              {"type": "E", "locate": 1, "tracking": 0, "timestamp": 34200000001000,
                               "order_ref": 1, "shares": 40, "match": 7}, "3.2"),
    "itch/order_cancel_1": ("QF-ITCH-S", ITCH_CANCEL,
                            {"type": "X", "locate": 1, "tracking": 0, "timestamp": 34200000002000,
                             "order_ref": 1, "shares": 10}, "3.2"),
    "itch/order_delete_1": ("QF-ITCH-S", ITCH_DELETE,
                            {"type": "D", "locate": 1, "tracking": 0, "timestamp": 34200000003000,
                             "order_ref": 1}, "3.2"),
    "ouch/enter_order_1": ("QF-OUCH-S", OUCH_ENTER, ENTER, "3.3"),
    "ouch/cancel_order_1": ("QF-OUCH-S", OUCH_CANCEL, CANCEL, "3.3"),
    "ouch/accepted_1": ("QF-OUCH-S", "4100001f1aced9f1f451463030303030303030303120200000000000000001",
                        {"type": "A", "timestamp": 34200000000500, "token": TOKEN, "order_ref": 1}, "3.3"),
    "ouch/canceled_1": ("QF-OUCH-S", "4300001f1aced9ffa051463030303030303030303120200000006455",
                        {"type": "C", "timestamp": 34200000004000, "token": TOKEN, "shares": 100,
                         "reason": "U"}, "3.3"),
    "ouch/stream_two": ("QF-OUCH-S", "0031" + OUCH_ENTER + "0013" + OUCH_CANCEL,
                        {"messages": [ENTER, CANCEL]}, "3.3"),
    "fast/quote_two": ("QF-FAST-S", FAST_TWO, {"messages": [QUOTE1, QUOTE2]}, "3.4"),
    "mold/one_block": ("QF-MOLD-S", MOLD_HDR + "0000000000000001" + "0001" + "0024" + ITCH_ADD,
                       {"session": "QFSIM00001", "sequence": 1, "count": 1, "blocks": [ITCH_ADD]}, "3.5"),
    "mold/three_blocks": ("QF-MOLD-S", MOLD_HDR + "0000000000000002" + "0003" + "001f" + ITCH_EXEC
                          + "0017" + ITCH_CANCEL + "0013" + ITCH_DELETE,
                          {"session": "QFSIM00001", "sequence": 2, "count": 3,
                           "blocks": [ITCH_EXEC, ITCH_CANCEL, ITCH_DELETE]}, "3.5"),
    "mold/heartbeat": ("QF-MOLD-S", MOLD_HDR + "0000000000000005" + "0000",
                       {"session": "QFSIM00001", "sequence": 5, "count": 0, "blocks": []}, "3.5"),
    "mold/end_of_session": ("QF-MOLD-S", MOLD_HDR + "0000000000000005" + "ffff",
                            {"session": "QFSIM00001", "sequence": 5, "count": 65535, "blocks": []}, "3.5"),
}


def _fix(body: str) -> str:
    """A QF-FIX-S message with the given body ('|' for SOH), correct BodyLength and checksum: used only to
    build malformed entries that must get past those two checks."""
    b = body.replace("|", "\x01")
    head = f"8=QFSIM.1\x019={len(b)}\x01{b}".encode()
    return (head + f"10={sum(head) % 256:03d}\x01".encode()).hex()


def malformed() -> list[dict]:
    hb = bytes.fromhex(FIX_HB)
    add = bytes.fromhex(ITCH_ADD)
    enter = bytes.fromhex(OUCH_ENTER)
    rows = [
        ("QF-FIX-S", "truncated: last byte removed", hb[:-1].hex(), "E_TRUNCATED"),
        ("QF-FIX-S", "empty", "", "E_TRUNCATED"),
        ("QF-FIX-S", "bad checksum 228", hb[:-4].hex() + "32323801", "E_CHECKSUM"),
        ("QF-FIX-S", "BodyLength 25 for 24 bytes", hb.replace(b"9=24", b"9=25").hex(), "E_LENGTH"),
        ("QF-FIX-S", "unknown MsgType Z", _fix("35=Z|34=1|49=QFA|56=QFB|"), "E_TYPE"),
        ("QF-FIX-S", "BeginString FIX.4.4", hb.replace(b"QFSIM.1", b"FIX.4.4").hex(), "E_FIELD"),
        ("QF-FIX-S", "side 3", _fix("35=D|34=2|49=QFA|56=QFB|11=QF1|55=QFSIM|54=3|38=100|40=2|44=101.25|"),
         "E_FIELD"),
        ("QF-FIX-S", "quantity with leading zero",
         _fix("35=D|34=2|49=QFA|56=QFB|11=QF1|55=QFSIM|54=1|38=0100|40=2|44=101.25|"), "E_FIELD"),
        ("QF-ITCH-S", "empty", "", "E_TRUNCATED"),
        ("QF-ITCH-S", "unknown type Z", "5a" + ITCH_ADD[2:], "E_TYPE"),
        ("QF-ITCH-S", "add order cut to 35 bytes", add[:35].hex(), "E_TRUNCATED"),
        ("QF-ITCH-S", "add order with one extra byte", ITCH_ADD + "00", "E_LENGTH"),
        ("QF-ITCH-S", "side Q", (add[:19] + b"Q" + add[20:]).hex(), "E_FIELD"),
        ("QF-ITCH-S", "zero shares", (add[:20] + b"\x00\x00\x00\x00" + add[24:]).hex(), "E_FIELD"),
        ("QF-ITCH-S", "stock with a 0x00 byte", (add[:24] + b"\x00" + add[25:]).hex(), "E_FIELD"),
        ("QF-ITCH-S", "system event code Z", "53000000000d18c2e280005a", "E_FIELD"),
        ("QF-OUCH-S", "stream: one byte", "00", "E_TRUNCATED"),
        ("QF-OUCH-S", "stream: frame cut short", ("0031" + OUCH_ENTER)[:-2], "E_TRUNCATED"),
        ("QF-OUCH-S", "stream: zero length", "0000", "E_LENGTH"),
        ("QF-OUCH-S", "stream: length 48 for an enter order", "0030" + OUCH_ENTER[:-2], "E_LENGTH"),
        ("QF-OUCH-S", "stream: unknown type Z", "0031" + "5a" + OUCH_ENTER[2:], "E_TYPE"),
        ("QF-OUCH-S", "stream: display Q", "0031" + (enter[:40] + b"Q" + enter[41:]).hex(), "E_FIELD"),
        ("QF-FAST-S", "first message cut after 10 bytes", FAST_TWO[:20], "E_TRUNCATED"),
        ("QF-FAST-S", "template id 2", "fc82" + FAST_TWO[4:34], "E_TYPE"),
        ("QF-FAST-S", "overlong seq 00 81", "fc81" + "0081" + FAST_TWO[6:34], "E_OVERLONG"),
        ("QF-FAST-S", "overlong presence map 7c 80", "7c80" + FAST_TWO[2:34], "E_OVERLONG"),
        ("QF-FAST-S", "u32 seq 2^32 in 5 bytes", "fc81" + "1000000080" + FAST_TWO[6:34], "E_OVERFLOW"),
        ("QF-FAST-S", "u32 seq with 6 bytes and no stop bit", "fc81" + "017f7f7f7f7f" + FAST_TWO[6:34],
         "E_OVERFLOW"),
        ("QF-FAST-S", "second message first: empty dictionary", FAST_TWO[34:], "E_FIELD"),
        ("QF-FAST-S", "redundant symbol in message 2", FAST_TWO[:34] + "94514653" + "49cd00e400e402ac",
         "E_OVERLONG"),
        ("QF-FAST-S", "unused presence bit 5 set", "fe" + FAST_TWO[2:34], "E_FIELD"),
        ("QF-MOLD-S", "19-byte header", (MOLD_HDR + "0000000000000001" + "00")[:38], "E_TRUNCATED"),
        ("QF-MOLD-S", "count 2, one block", MOLD_HDR + "0000000000000001" + "0002" + "0024" + ITCH_ADD,
         "E_TRUNCATED"),
        ("QF-MOLD-S", "block length past the end", MOLD_HDR + "0000000000000001" + "0001" + "0025" + ITCH_ADD,
         "E_TRUNCATED"),
        ("QF-MOLD-S", "trailing byte", MOLD_HDR + "0000000000000001" + "0001" + "0024" + ITCH_ADD + "00",
         "E_LENGTH"),
        ("QF-MOLD-S", "zero block length", MOLD_HDR + "0000000000000001" + "0001" + "0000", "E_LENGTH"),
        ("QF-MOLD-S", "end of session followed by a byte", MOLD_HDR + "0000000000000005" + "ffff" + "00",
         "E_LENGTH"),
        ("QF-MOLD-S", "session byte 0x01", "01" + MOLD_HDR[2:] + "0000000000000005" + "0000", "E_FIELD"),
        ("QF-MOLD-S", "session all spaces", "20" * 10 + "0000000000000005" + "0000", "E_FIELD"),
    ]
    return [{"format": f, "name": n, "hex": h, "code": c} for f, n, h, c in rows]


def files() -> dict[Path, bytes]:
    out: dict[Path, bytes] = {}
    for name, (fmt, hx, fields, sec) in FIXTURES.items():
        data = bytes.fromhex(hx)
        out[OUT / f"{name}.bin"] = data
        side = {"format": fmt, "label": LABEL, "fields": fields, "hex": hx, "length": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "derivation": f"specifications/12-platform/adapters.md section {sec}"}
        out[OUT / f"{name}.json"] = (json.dumps(side, indent=1) + "\n").encode()
    doc = {"label": LABEL, "source": "specifications/12-platform/adapters.md section 3", "cases": malformed()}
    out[OUT / "malformed.json"] = (json.dumps(doc, indent=1) + "\n").encode()
    return out


def main(argv: list[str]) -> int:
    check = "--check" in argv
    bad = 0
    for path, data in files().items():
        if check:
            if not path.exists() or path.read_bytes() != data:
                print(f"STALE {path.relative_to(ROOT)}")
                bad += 1
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print(f"{'checked' if check else 'wrote'} {len(files())} files, {bad} stale")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
