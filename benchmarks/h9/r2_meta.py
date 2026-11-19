#!/usr/bin/env python3
"""Helpers for run_r2.sh (H-9 workload R2 and row L7; low-latency-targets.md (f), (g), (h)).

  python r2_meta.py compare SYMBOL PY.json CPP.json RUST.json JAVA.json
      Form A counts of the three harnesses must equal the Python reference (check_r2.py) field by field, and the
      run must pass: no checksum failure, no top-10 failure. Exit 0 = pass; 1 = fail; 2 = equal counts, no top-10 or
      checksum failure, but below-level-10 failures (targets (g): they fail the run unless order-book.md as it stood
      before HR-130 classes them as the venue's; HR-132: the override QF_R2_BELOW10_VENUE_SIDE=1 is set by the
      coordinator only, and it is recorded in the correctness marker).
      Tie guard (HR-135, fixed before any R2 file was read): per symbol, rows with no tie (lo = hi, compared
      exactly) must be at least NO_TIE_MIN of the checked rows, and rows matched only inside the tie at most
      INSIDE_TIE_MAX; otherwise exit 1 (no correctness marker, no timing) until the coordinator has reviewed it.
  python r2_meta.py inputs R2DIR
      Refuses (exit 1, reasons printed) an input built outside the HR-134 rule: R2_window.json missing or not listed
      in R2_replay.sha256, a sample-only or tolerant build, --after other than 2026-11-19T11:41:24Z, --until, or
      --min-hours/--max-hours given; either symbol's meta file sample-only or tolerant (HR-135, audit KA-B6).
      run_r2.sh calls it before anything else outside SMOKE=1.
  python r2_meta.py stamp RESULT.json META.json
      Adds the publication fields of targets (f) to a harness result (machine, OS, compiler or runtime, flags,
      commit, workload hashes, warm-up, repeats, targets commits, labels). META.json is written by run_r2.sh.
"""
import json
import os
import sys
from pathlib import Path

NO_TIE_MIN = 0.25  # HR-135: the 2026-11-17 sample had 554/846 (BTC/USD) and 677/895 (ETH/USD) rows without a tie
INSIDE_TIE_MAX = 0.06  # HR-135, audit KA-B16: three times the sample's 35 of 1,741 rows (about 2.0 %)
AFTER_RULE = "2026-11-19T11:41:24.000000Z"  # build_r2.py's iso() of AFTER_DEFAULT
SYMBOLS = ("BTC-USD", "ETH-USD")

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
    if ok:
        for why in tie_guard(ref):
            print(f"{symbol}: TIE GUARD (HR-135): {why}; the coordinator reviews this before any timing")
            ok = False
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


def tie_guard(ref):
    """Reasons the tie reading cannot be trusted on this run (empty when it can). HR-135: the tie reading can hide
    only a below-level-10 error, and only on rows with a tie; rows without one are compared exactly."""
    n = ref["checkpoint_checked"]
    if n == 0:
        return ["no checked rows"]
    out = []
    no_tie = n - ref["checkpoint_rows_with_tie"]
    if no_tie < NO_TIE_MIN * n:
        out.append(f"rows without a tie {no_tie} of {n}, below {NO_TIE_MIN:.0%}")
    inside = ref["checkpoint_matched_only_inside_tie"]
    if inside > INSIDE_TIE_MAX * n:
        out.append(f"rows matched only inside the tie {inside} of {n}, above {INSIDE_TIE_MAX:.0%}")
    return out


def input_problems(r2dir):
    """Why the input in r2dir is not a workload input under HR-134 (empty list when it is)."""
    d = Path(r2dir)
    out = []
    try:
        listed = {line.split()[-1] for line in (d / "R2_replay.sha256").read_text(encoding="utf-8").splitlines() if line.strip()}
    except OSError:
        return ["R2_replay.sha256 is missing"]
    if "R2_window.json" not in listed:
        out.append("R2_window.json is not listed in R2_replay.sha256 (built before HR-135, or by hand)")
    try:
        w = json.loads((d / "R2_window.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [*out, "R2_window.json is missing or unreadable"]
    o = w.get("options")
    if not isinstance(o, dict):
        return [*out, "R2_window.json has no options block (built before HR-135)"]
    if o.get("sample_only") is not False:
        out.append("built with --sample-only")
    if o.get("tolerant") is not False:
        out.append("built with --tolerant")
    if o.get("after") != AFTER_RULE:
        out.append(f"built with --after {o.get('after')}")
    if o.get("until") is not None:
        out.append(f"built with --until {o.get('until')}")
    for k in ("min_hours", "max_hours"):
        if o.get(k) is not None:
            out.append(f"built with --{k.replace('_', '-')} {o.get(k)}")
    for s in SYMBOLS:
        try:
            m = json.loads((d / f"R2_{s}.meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out.append(f"R2_{s}.meta.json is missing or unreadable")
            continue
        if m.get("sample_only") is not False:
            out.append(f"R2_{s}.meta.json: sample-only build")
        if m.get("tolerant") is not False:
            out.append(f"R2_{s}.meta.json: tolerant build")
    return out


def inputs(r2dir):
    bad = input_problems(r2dir)
    for why in bad:
        print(f"REFUSED input {r2dir}: {why} (HR-134, HR-135: never a workload input)")
    if not bad:
        print(f"input {r2dir}: built under the HR-134 rule (no sample-only or tolerant option)")
    return 1 if bad else 0


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
    if len(argv) == 2 and argv[0] == "inputs":
        return inputs(argv[1])
    if len(argv) == 3 and argv[0] == "stamp":
        return stamp(argv[1], argv[2])
    print(__doc__)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
