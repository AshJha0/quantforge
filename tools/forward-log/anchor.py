#!/usr/bin/env python3
"""Anchors for the forward-log hash chain (plan 13.2, R4). Standard library only.

A hash chain alone cannot show that the whole log was not rewritten: whoever can push can recompute every
hash. An anchor records (count, head) at a moment, and is then stamped with OpenTimestamps, whose proof ties
the file to a Bitcoin block that nobody here controls. Verifying checks that line `count` of the log still has
hash `head`, so a rewrite of any line up to `count` is caught even if every later hash was recomputed.

  anchor.py make   --log FILE --out-dir DIR [--stamp]   write DIR/<UTC time>.json (and stamp it with `ots`)
  anchor.py verify --log FILE --anchors DIR [--ots]     chain check, then every anchor; --ots also runs `ots verify`
"""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import forward_log as fl  # noqa: E402


def make(log, out_dir, when=None):
    n, head = fl.verify(log)
    if n == 0:
        raise ValueError("log is empty; nothing to anchor")
    when = when or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{when}.json"
    p.write_text(json.dumps({"count": n, "head": head, "time": when}, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return p


def check_anchors(log, anchors_dir):
    """Chain check, then each anchor. Raises ValueError on the first problem. Returns number of anchors."""
    n, _ = fl.verify(log)
    hashes = [e["hash"] for e in fl.read(log)]
    files = sorted(Path(anchors_dir).glob("*.json"))
    for f in files:
        a = json.loads(f.read_text(encoding="utf-8"))
        if a["count"] > n:
            raise ValueError(f"{f.name}: anchor covers {a['count']} lines but the log has {n}; lines were removed")
        if hashes[a["count"] - 1] != a["head"]:
            raise ValueError(f"{f.name}: line {a['count']} hash differs from the anchor; the log was rewritten")
    return len(files)


def ots_verify(anchors_dir):
    """Runs `ots verify` on each stamped anchor. Returns (confirmed, pending). Raises on a bad proof."""
    exe = shutil.which("ots")
    if not exe:
        raise RuntimeError("`ots` not found: pip install opentimestamps-client")
    confirmed = pending = 0
    for proof in sorted(Path(anchors_dir).glob("*.json.ots")):
        r = subprocess.run([exe, "verify", str(proof)], capture_output=True, text=True)
        out = r.stdout + r.stderr
        if "Success!" in out:
            confirmed += 1
        elif "Pending confirmation" in out or "Timestamp not yet complete" in out:
            pending += 1
        else:
            raise ValueError(f"{proof.name}: OpenTimestamps verification failed:\n{out.strip()}")
    return confirmed, pending


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["make", "verify"])
    ap.add_argument("--log", required=True)
    ap.add_argument("--out-dir")
    ap.add_argument("--anchors")
    ap.add_argument("--stamp", action="store_true")
    ap.add_argument("--ots", action="store_true")
    a = ap.parse_args()
    try:
        if a.command == "make":
            if not a.out_dir:
                ap.error("make needs --out-dir")
            p = make(a.log, a.out_dir)
            if a.stamp:
                subprocess.run(["ots", "stamp", str(p)], check=True)
            print(p)
            return 0
        if not a.anchors:
            ap.error("verify needs --anchors")
        k = check_anchors(a.log, a.anchors)
        msg = f"chain ok, {k} anchors match"
        if a.ots:
            c, p = ots_verify(a.anchors)
            msg += f"; OpenTimestamps: {c} confirmed, {p} pending"
        print(msg)
        return 0
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as e:
        print(e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
