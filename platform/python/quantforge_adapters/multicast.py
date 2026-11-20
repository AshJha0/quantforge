"""K-3 multicast smoke (adapters.md 3.5, KR-278): QF-ITCH-S Add Order messages in QF-MOLD-S packets over UDP
multicast, one sender and two listeners, with sequence gap detection.

    python -m quantforge_adapters.multicast send   --records FILE --ready DIR [--drop-packet K]
    python -m quantforge_adapters.multicast listen --name L1 --ready DIR --out DIR

The packet logic (`packets`, `Listener`) is separate from the sockets so tests drive it in-process.
Simulated; not a certified implementation; not connected to any venue.
"""

import argparse
import hashlib
import json
import socket
import struct
import sys
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from quantforge_adapters import LABEL
from quantforge_adapters.feeds import itch, mold
from quantforge_adapters.records import Record, load

GROUP, PORT = "239.192.0.1", 30001
SESSION = "QFSIM00001"
PER_PACKET = 10


def _ticks(text: str) -> int:
    whole, _, frac = text.partition(".")
    return int(whole) * 10_000 + int((frac + "0000")[:4])


def add_order(r: Record) -> bytes:
    body = r["body"]
    price = _ticks(body["bid"]) if "bid" in body else _ticks(body["price"]) if "price" in body else 1_000_000
    return itch.encode(
        {
            "type": "A",
            "locate": 1,
            "tracking": 0,
            "timestamp": 34_200_000_000_000 + 1_000 * r["seq"],
            "order_ref": r["seq"],
            "side": "B" if r["seq"] % 2 else "S",
            "shares": int(body["qty"]) if "qty" in body else 100,
            "stock": "QFSIM   ",
            "price": price,
        }
    )


def packets(rows: list[Record], drop_packet: int | None = None) -> Iterator[bytes]:
    """Packets of up to 10 blocks in sequence order, then three end-of-session packets. Packet k (1-based)
    is skipped when drop_packet == k (the planted fault)."""
    msgs = [add_order(r) for r in sorted(rows, key=lambda r: r["seq"])]
    for k, start in enumerate(range(0, len(msgs), PER_PACKET), 1):
        if k != drop_packet:
            blocks = msgs[start : start + PER_PACKET]
            yield mold.encode(
                {"session": SESSION, "sequence": start + 1, "count": len(blocks), "blocks": blocks}
            )
    for _ in range(3):
        yield mold.encode(
            {"session": SESSION, "sequence": len(msgs) + 1, "count": mold.END_OF_SESSION, "blocks": []}
        )


def sender_hash(rows: list[Record]) -> str:
    h = hashlib.sha256()
    for r in sorted(rows, key=lambda r: r["seq"]):
        h.update(add_order(r))
    return h.hexdigest()


class Listener:
    def __init__(self) -> None:
        self.gaps = mold.GapDetector()
        self.msgs: dict[int, bytes] = {}
        self.errors: list[str] = []

    def feed(self, data: bytes) -> None:
        if self.gaps.ended:
            return  # the repeated end-of-session packets
        try:
            for seq, block in self.gaps.feed(mold.decode(data)):
                self.msgs[seq] = itch.encode(itch.decode(block))  # decode and re-encode every message
        except Exception as exc:  # noqa: BLE001 (a listener records and continues; the result shows it)
            self.errors.append(f"{type(exc).__name__}: {exc}")

    def result(self, name: str) -> dict[str, Any]:
        h = hashlib.sha256()
        for seq in sorted(self.msgs):
            h.update(self.msgs[seq])
        return {
            "listener": name,
            "n": len(self.msgs),
            "h_bytes": h.hexdigest(),
            "gaps": self.gaps.gaps,
            "duplicates": self.gaps.duplicates,
            "ended": self.gaps.ended,
            "errors": self.errors[:5],
            "label": LABEL,
        }


def run_in_process(
    rows: list[Record], drop_packet: int | None = None, listeners: int = 2
) -> list[dict[str, Any]]:
    ls = [Listener() for _ in range(listeners)]
    for p in packets(rows, drop_packet):
        for lst in ls:
            lst.feed(p)
    return [lst.result(f"L{i + 1}") for i, lst in enumerate(ls)]


def judge(sent_hash: str, results: Iterable[dict[str, Any]], drop_packet: int | None) -> str:
    """PASS when every listener has the sender's hash and no gap; with a planted drop, PASS when every listener
    reports exactly the one gap of the dropped packet."""
    for r in results:
        if drop_packet is None:
            if r["gaps"] or r["errors"] or not r["ended"] or r["h_bytes"] != sent_hash or r["n"] != 10_000:
                return f"FAIL {r['listener']}: gaps {r['gaps'][:3]}, n {r['n']}, errors {r['errors'][:1]}"
        else:
            lo = (drop_packet - 1) * PER_PACKET + 1
            if [tuple(g) for g in r["gaps"]] != [(lo, lo + PER_PACKET - 1)]:
                return f"FAIL {r['listener']}: planted drop gave gaps {r['gaps'][:3]}"
    return "PASS"


# ---- sockets (run in the compose containers on GitHub Actions only) ---------------------------------------


def send(rows: list[Record], ready: Path, listeners: int, drop_packet: int | None) -> None:
    deadline = time.monotonic() + 60
    while len(list(ready.glob("*.ready"))) < listeners:
        if time.monotonic() > deadline:
            raise SystemExit("listeners not ready after 60 s")
        time.sleep(0.5)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    for p in packets(rows, drop_packet):
        s.sendto(p, (GROUP, PORT))
        time.sleep(0.002)  # pacing: a burst could overflow a listener's socket buffer (a drop is a fail)
    (ready / "sender.json").write_text(json.dumps({"h_bytes": sender_hash(rows), "drop_packet": drop_packet}))


def listen(name: str, ready: Path, out: Path, timeout_s: float = 180) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 << 20)
    s.bind(("", PORT))
    s.setsockopt(
        socket.IPPROTO_IP,
        socket.IP_ADD_MEMBERSHIP,
        struct.pack("4sl", socket.inet_aton(GROUP), socket.INADDR_ANY),
    )
    s.settimeout(5)
    ready.mkdir(parents=True, exist_ok=True)
    (ready / f"{name}.ready").write_text("ready")
    lst = Listener()
    deadline = time.monotonic() + timeout_s
    while not lst.gaps.ended and time.monotonic() < deadline:
        try:
            lst.feed(s.recv(65535))
        except TimeoutError:
            continue
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.json").write_text(json.dumps(lst.result(name), indent=1) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("send", "listen", "judge"))
    ap.add_argument("--records", type=Path)
    ap.add_argument("--ready", type=Path, default=Path("/work/ready"))
    ap.add_argument("--out", type=Path, default=Path("/work/out"))
    ap.add_argument("--name", default="L1")
    ap.add_argument("--listeners", type=int, default=2)
    ap.add_argument("--drop-packet", type=int, default=None)
    a = ap.parse_args(argv)
    if a.mode == "send":
        send(load(a.records), a.ready, a.listeners, a.drop_packet)
        return 0
    if a.mode == "listen":
        listen(a.name, a.ready, a.out)
        return 0
    sender = json.loads((a.ready / "sender.json").read_text())
    results = [json.loads(p.read_text()) for p in sorted(a.out.glob("L*.json"))]
    if len(results) != a.listeners:
        print(f"FAIL: {len(results)} listener results")
        return 1
    v = judge(sender["h_bytes"], results, sender["drop_packet"])
    print(v, json.dumps([{k: r[k] for k in ("listener", "n", "gaps")} for r in results]))
    return 0 if v == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
