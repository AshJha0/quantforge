#!/usr/bin/env python3
"""Helpers for run_r2.sh (H-9 workload R2 and row L7; low-latency-targets.md (f), (g), (h)).

  python r2_meta.py compare SYMBOL PY.json CPP.json RUST.json JAVA.json
      Form A counts of the three harnesses must equal the Python reference (check_r2.py) field by field, and the
      run must pass: no checksum failure, no top-10 failure. Exit 0 = pass; 1 = fail; 2 = equal counts, no top-10 or
      checksum failure, but below-level-10 failures (targets (g): they fail the run unless order-book.md as it stood
      before HR-130 classes them as the venue's; HR-132: the override QF_R2_BELOW10_VENUE_SIDE=1 is set by the
      coordinator only, and it is recorded in the correctness marker).
  python r2_meta.py stamp RESULT.json META.json
      Adds the publication fields of targets (f) to a harness result (machine, OS, compiler or runtime, flags,
      commit, workload hashes, warm-up, repeats, targets commits, labels). META.json is written by run_r2.sh.
"""
import json
import os
import sys
from pathlib import Path

FIELDS = ("checksum_checked", "checksum_failed", "checkpoint_checked", "checkpoint_failed_top10",
          "checkpoint_failed_below10", "checkpoint_matched_at_lo", "checkpoint_matched_at_hi",
          "checkpoint_matched_only_inside_tie", "checkpoint_rows_with_tie", "checkpoint_failed_strict_reading")


def compare(symbol, py, *harness):
    ref = json.loads(Path(py).read_text(encoding="utf-8"))
    ok = True
    for h in harness:
        got = json.loads(Path(h).read_text(encoding="utf-8"))
        fa = got.get("form_a")
        if fa is None:
            print(f"{symbol}: {h} has no form_a block")
            ok = False
            continue
        for f in FIELDS:
            if fa[f] != ref[f]:
                print(f"{symbol}: {Path(h).name} {f} = {fa[f]}, Python reference {ref[f]}")
                ok = False
        if got.get("correctness_mismatches", 1) != 0:
            print(f"{symbol}: {Path(h).name} in-harness std transcription mismatches {got.get('correctness_mismatches')}")
            ok = False
    if ref["book_messages"] == 0 or ref["checkpoint_checked"] == 0 or ref.get("chunk_start_mismatches", 1):
        print(f"{symbol}: reference ran on nothing or its chunk starts disagree")
        ok = False
    if ref["checksum_failed"] or ref["checkpoint_failed_top10"]:
        print(f"{symbol}: FAIL checksum_failed {ref['checksum_failed']}, top-10 {ref['checkpoint_failed_top10']}")
        ok = False
    print(f"{symbol}: counts {json.dumps({f: ref[f] for f in FIELDS})}; harnesses equal: {ok}")
    if not ok:
        return 1
    if ref["checkpoint_failed_below10"]:
        if os.environ.get("QF_R2_BELOW10_VENUE_SIDE") == "1":
            print(f"{symbol}: {ref['checkpoint_failed_below10']} below-level-10 mismatches; coordinator decision "
                  "QF_R2_BELOW10_VENUE_SIDE=1: 'passes with N venue-side holes'")
            return 0
        print(f"{symbol}: {ref['checkpoint_failed_below10']} below-level-10 mismatches: the run fails unless the "
              "coordinator decides they are the venue's (targets (g)); set QF_R2_BELOW10_VENUE_SIDE=1 only then")
        return 2
    return 0


def stamp(result, meta):
    r = json.loads(Path(result).read_text(encoding="utf-8"))
    m = json.loads(Path(meta).read_text(encoding="utf-8"))
    lang = Path(result).name.split("_")[0]
    pub = {k: v for k, v in m.items() if k not in ("languages",)}
    pub.update(m.get("languages", {}).get(lang, {}))
    r["publication"] = pub
    Path(result).write_text(json.dumps(r, separators=(",", ":")) + "\n", encoding="utf-8")
    return 0


def main(argv):
    if len(argv) >= 6 and argv[0] == "compare":
        return compare(*argv[1:])
    if len(argv) == 3 and argv[0] == "stamp":
        return stamp(argv[1], argv[2])
    print(__doc__)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
