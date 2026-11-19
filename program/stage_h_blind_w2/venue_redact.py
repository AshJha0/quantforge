"""Removes golden values and verdicts from the H-16 venue blind packet (run by wave2_make_packet.sh venue).

Each rule removes one stated passage and must match exactly once, so a spec edit that moves the text fails the
build instead of leaking. Inputs stay; expected values, derivations and per-case error verdicts go.
    python -I venue_redact.py <packet dir>
"""
import re
import sys
from pathlib import Path

RULES = [
    ("venue-analytics.blind.md", r" Without this, venue_h-0001's A markout \(exactly 0\) comes out[^.]*tolerance\."),
    ("venue-analytics.blind.md", r" N = 10\^18 \+ .*?a 28-digit sum gives N = 0\."),
    ("venue-analytics.blind.md", r", hand and exact rational arithmetic; not blind-checked"),
    ("stage-h-rulings-micro.md", r" Re-derived goldens: venue_h-0008 is now .*?no longer applies"),
    ("stage-h-rulings-micro.md", r" Because the result is correctly rounded, venue_h-0010 is compared[^.|]*\.?"),
    ("stage-h-rulings-w2-exec.md", r" and `venue_h-0008`"),
]


def main():
    pk = Path(sys.argv[1])
    for name, pat in RULES:
        p = pk / name
        s = p.read_text(encoding="utf-8")
        s2, n = re.subn(pat, "", s, flags=re.S)
        if n != 1:
            print(f"{name}: rule {pat!r} matched {n} times", file=sys.stderr)
            return 1
        p.write_text(s2, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
