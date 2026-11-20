"""K-4c v2 blind packet (DR-H2) for the value cases of calib.trigger.check (spec 1.1.0, KR-232, KR-233).

Pattern: k5a_v2_make_packet.py. Writes into <packet dir> (outside every worktree, empty):
  README.md, specs/recalibration-triggers.blind.md, rulings/stage-k-rulings-trig.blind.md,
  inputs/K-4c.inputs.json, output_template.json, MANIFEST.sha256.
Spec cuts: the "Version 1.1.0 in brief" paragraph, the n = 2 worked example and the case id in the far-tail
sentence; sections "Golden value cases", the three "Acceptance" sections and "Limits and open issues".
Rulings kept: KR-6, KR-13, KR-232, KR-233, with case ids, golden lists and acceptance text cut (RULING_CUTS).
Never reads the expected values (trig_v2_expected.json).

    python -I program/stage_h_blind_w2/trig_v2_make_packet.py . C:/Work/Claude/qf-blind/trig_k_v2_packet
"""
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from trig_v2_cases import ITEM, load  # noqa: E402

SPEC = "specifications/03-calibration/recalibration-triggers.md"
RULINGS = "specifications/stage-k-rulings-w1.md"
CUT_COUNT = {"Golden value cases": 1, "Acceptance": 3, "Limits and open issues": 1}
SPEC_CUTS = [
    (r"^\*\*Version 1\.1\.0 in brief\.\*\*.*?\n\n", "1.1.0 summary (audit figures)"),
    (r" Worked example: n = 2, k = 3:.*?against `nominal_rate` 0\.0027\.", "worked example prints case values"),
    (r"; trig_k-0009 holds this", "case id"),
]
KEEP_RULINGS = ("KR-6", "KR-13", "KR-232", "KR-233")
KR13_RESTORE = " Implementations decide equality on the computed binary64 values."
RULING_CUTS = [
    ("KR-13", r" Implementations decide equality on the computed binary64 values; trig_k-0004 is built.*?(?= \|$)",
     KR13_RESTORE, "names a case and its blind status; the binary64-equality sentence is kept"),
    ("KR-232", r" \(trig_k-0009 keeps pinning its far tail\)", "", "case id"),
    ("KR-232", r" \*\*Golden values\*\* change.*?(?= \| derived)", "", "golden changes and the acceptance run"),
    ("KR-233", r" `sigma = 0` is a special case and keeps its golden \(trig_k-0008\)\. New goldens:.*?(?= \| derived)",
     "", "golden list"),
]

FIELDS = {
    "fire": "boolean: whether the trigger fires",
    "sigma": "binary64: the sample standard deviation of the changes (KR-233 arithmetic)",
    "threshold": "binary64: k sigma sqrt(d)",
    "false_alarm_rate": "binary64: the 1.1.0 false-alarm rate (KR-232)",
    "nominal_rate": "binary64: 2 Phi(-k), the known-sigma rate",
}

README = """# K-4c blind re-derivation packet (DR-H2), version 2

You are the blind lane. From the rules in this folder alone, write your own small reference implementation and
compute the outputs of the {n} cases in `inputs/`. Nobody will tell you whether you are right until your results
are frozen.

## Hard rules

1. Read nothing outside this folder (and your own working folder). No repository, no other folder on this machine,
   no web page. If a rule here is unclear, decide, write the decision down (rule 4) and go on.
2. Write your reference yourself: plain Python, standard library only, no imports from any repository.
3. Do not round. Report every number as a JSON number at full binary64 precision (Python `json.dumps` of the float);
   `fire` as a JSON boolean.
4. Write `notes.md`: every ambiguity and assumption, with the case ids it affects and the file and section you read.

## What to produce (in your own working folder)

1. `blind_results.json`: copy `output_template.json`'s `results_skeleton` and replace every null with your value.
   Keep the nesting exactly (`{{"cases": {{"<case_id>": {{field: value}}}}}}`, no "outputs" wrapper).
2. `blind_ref.py` and `notes.md`.
3. Then compute the SHA-256 of `blind_results.json`, write it to `blind_results.sha256`, and report the hash as the
   first line of your hand-back. Never change `blind_results.json` after that.

## What is here

- `specs/recalibration-triggers.blind.md`: the spec without its golden tables and acceptance sections.
- `rulings/stage-k-rulings-trig.blind.md`: KR-6 (superseded in part by KR-232), KR-13, KR-232, KR-233.
- `inputs/K-4c.inputs.json`: per case the inputs `changes`, `x_ref`, `x_now`, `days_since` (d), `k`.
- `output_template.json`, `MANIFEST.sha256` (check it first and say in `notes.md` whether it matched).

Every case here is a value case (no error is expected).
"""


def strip_spec(text):
    for pat, _ in SPEC_CUTS:
        text, n = re.subn(pat, "", text, flags=re.MULTILINE | re.DOTALL)
        if n != 1:
            raise SystemExit(f"spec cut {pat!r} matched {n}")
    for sec, want in CUT_COUNT.items():
        text, n = re.subn(r"^## " + sec + r".*?(?=^## |\Z)", "", text, flags=re.DOTALL | re.MULTILINE)
        if n != want:
            raise SystemExit(f"spec section {sec!r} found {n}, expected {want}")
    if "blind:strip" in text or re.search(r"trig_k-\d{4}", text):
        raise SystemExit("spec: a strip block or case id survived")
    return text.rstrip() + "\n"


def strip_rulings(text):
    rows = {}
    for ln in text.splitlines():
        for r in KEEP_RULINGS:
            if ln.startswith(f"| {r} |"):
                rows.setdefault(r, ln)
    if set(rows) != set(KEEP_RULINGS):
        raise SystemExit(f"rulings found {sorted(rows)}")
    for r, pat, repl, _ in RULING_CUTS:
        rows[r], n = re.subn(pat, repl, rows[r], flags=re.DOTALL)
        if n != 1:
            raise SystemExit(f"ruling cut in {r} matched {n}")
    body = "\n".join(rows[r] for r in KEEP_RULINGS)
    if re.search(r"trig_k-\d{4}", body):
        raise SystemExit("rulings: a case id survived")
    return ("# Stage K rulings that bind `calib.trigger.check` (excerpt)\n\n"
            "From `stage-k-rulings-w1.md`. KR-232 supersedes the `false_alarm_rate` of KR-6; KR-233 completes KR-6.\n"
            "Text naming test cases, goldens or acceptance results is cut.\n\n"
            "| # | Point | Ruling | Evidence |\n|---|---|---|---|\n" + body + "\n")


def write(pk, rel, data):
    p = pk / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data.encode("utf-8"))


def build(root, pk):
    cases = load(root)
    write(pk, "specs/recalibration-triggers.blind.md", strip_spec((root / SPEC).read_text(encoding="utf-8")))
    write(pk, "rulings/stage-k-rulings-trig.blind.md", strip_rulings((root / RULINGS).read_text(encoding="utf-8")))
    rows = [{"case_id": cid, "operation": op, "inputs": inp} for cid, op, inp in cases]
    write(pk, f"inputs/{ITEM}.inputs.json", json.dumps({"item": ITEM, "cases": rows}, indent=1) + "\n")
    tmpl = {"fields": FIELDS, "results_skeleton": {"cases": {cid: dict.fromkeys(FIELDS) for cid, _, _ in cases}}}
    write(pk, "output_template.json", json.dumps(tmpl, indent=1) + "\n")
    write(pk, "README.md", README.format(n=len(cases)))
    files = sorted(p.relative_to(pk).as_posix() for p in pk.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
    man = "".join(f"{hashlib.sha256((pk / f).read_bytes()).hexdigest()}  {f}\n" for f in files)
    write(pk, "MANIFEST.sha256", man)
    return files, hashlib.sha256(man.encode()).hexdigest()


def main():
    root, pk = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    if any((q / ".git").exists() for q in [pk, *pk.parents]):
        raise SystemExit("packet dir is inside a git worktree; refusing")
    if pk.exists() and any(pk.iterdir()):
        raise SystemExit("packet dir not empty")
    files, h = build(root, pk)
    print("\n".join(files))
    print("MANIFEST.sha256 file hash:", h)


if __name__ == "__main__":
    main()
