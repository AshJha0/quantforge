"""K-5a v2 (ruling KR-234, audit A response 2026-11-19): k5a_make_packet.py with the 1.1.0 spec, KR-234 kept
(its effect and acceptance cut) and twelve cases. Prepared, not run by the blind lane."""
"""K-5a blind packet (DR-H2) for the five value cases of risk.intraday.delta_gamma_bound (idr_k-0001..0005).

Writes, into <packet dir> (which must lie outside every repository worktree and be empty):
  README.md                              what the blind lane must produce, and the read-nothing-else rule
  specs/intraday-risk-bounds.blind.md    the CONFIRMED spec with the sections "Golden value cases" (every expected
                                         value, the hand derivation, the check columns and the error cases),
                                         "Acceptance" and "Acceptance evidence" cut; header, plain idea, formal
                                         statement and the operation section stay
  rulings/stage-k-rulings-k5a.blind.md   the rulings that bind this operation: KR-7, KR-10, KR-15, KR-17, with
                                         every case id, golden reference and acceptance number cut (see RULING_CUTS)
  inputs/K-5a.inputs.json                per case: case_id, operation, inputs (from k5a_cases.py; nothing else)
  output_template.json                   field definitions and units, and a results skeleton (every field null)
  MANIFEST.sha256                        SHA-256 of every file above
Never reads k5a_expected.json.

    python -I program/stage_h_blind_w2/k5a_make_packet.py <checkout> C:/Work/Claude/qf-blind/k5a_packet
"""

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from k5a_v2_cases import CASES, ITEM

SPEC = "specifications/06-risk/intraday-risk-bounds.md"
RULINGS = "specifications/stage-k-rulings-w1.md"
CUT = (
    "Golden value cases",
    "Acceptance",
)  # "Acceptance" matches "Acceptance (fixed ...)" and "Acceptance evidence"
CUT_COUNT = {"Golden value cases": 1, "Acceptance": 3}  # v2: acceptance 1.1.0, acceptance 1.0.0, evidence 1.0.0
KEEP_RULINGS = ("KR-7", "KR-10", "KR-15", "KR-17", "KR-234")
# Text cut inside the kept rulings: (ruling, regex, what it holds). Each must match exactly once.
RULING_CUTS = [
    ("KR-234", r" \*\*Effect\.\*\*.*?(?= \| derived)", "worked effect figures and the acceptance (case values, run results)"),
    (
        "KR-15",
        r" Goldens are unchanged: idr_k-0005 \(short 2-year leg\) was already generated with `abs\(N\)`",
        "names a golden case and its input",
    ),
    (
        "KR-17",
        r" The 1,000-move acceptance is therefore also checked at 50 digits .*?(?= \|$)",
        "acceptance run results (violations, rounding share, margin) and the golden bounds' history",
    ),
]

FIELDS = {
    "estimate_pnl": "currency units, binary64: the delta-gamma estimate of V(y + h) - V(y), summed over the positions",
    "bound": "currency units, binary64: the error bound of the estimate, summed over the positions (see KR-17)",
    "label": "string, the label the rulings require on this output",
}

README = """# K-5a blind re-derivation packet (DR-H2)

You are the blind lane. Your job: from the rules in this folder alone, write your own small reference
implementation and compute the outputs of the {n} cases in `inputs/`. Nobody will tell you whether you are right
until your results are frozen.

## Hard rules

1. Read nothing outside this folder. No repository, no other folder on this machine, no web page, no earlier
   conversation about this spec. If a rule here is unclear, decide, write the decision down (rule 4) and go on.
2. Write your reference yourself: plain Python (standard library only is fine), no imports from any repository.
   Keep it in your own working folder next to (not inside) this packet, for example `../k5a_blind/`.
3. Do not round. Report every number as a JSON number at full binary64 precision (Python `json.dumps` of the float).
   The comparison is at 1e-9 relative; you do not need to aim for it, just compute in binary64.
4. Write `notes.md`: every ambiguity you met and every assumption you made, each with the case ids it affects and
   the file and section of the rule you read. Write it while you work, not afterwards from memory.

## What to produce (in your own working folder)

1. `blind_results.json`: copy `output_template.json`'s `results_skeleton` object (it has the form
   `{{"cases": {{"<case_id>": {{...}}}}}}`) and replace every null with your value. Keep the nesting exactly as in the
   skeleton: the case object holds the output fields directly (no extra "outputs" wrapper). Field meanings and units
   are in `output_template.json` under `fields`.
2. `blind_ref.py` (your reference) and `notes.md`.
3. Then, and before you see or ask for anything else: compute the SHA-256 of `blind_results.json`
   (`python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" blind_results.json`),
   write it to `blind_results.sha256`, and report that hash as the first line of your hand-back. After that,
   never change `blind_results.json`; a later correction goes in a separate file with its reason.

## What is here

- `specs/intraday-risk-bounds.blind.md`: the spec with its golden case tables, hand derivations and acceptance
  sections removed. The formula, the operation's inputs and outputs are complete.
- `rulings/stage-k-rulings-k5a.blind.md`: the rulings that bind this operation (KR-7 as corrected by KR-15 and
  completed by KR-17; KR-10 for the label).
- `inputs/K-5a.inputs.json`: per case the case id, the operation and its inputs. `notional` is N, `maturity` is T
  in years, `yield` is the continuously compounded yield y as a decimal (0.04 means 4%), `shift` is h, a parallel
  change of every position's yield, as a decimal.
- `output_template.json`: what to report per case.
- `MANIFEST.sha256`: hashes of every file here. Check them first (`sha256sum -c MANIFEST.sha256` or Python) and
  say in `notes.md` whether they matched.

Errors are out of scope: every case here is a value case.
"""


def strip_spec(text):
    # v2: the 1.1.0 summary paragraph and the worked example name cases and print their values
    text, n1 = re.subn(r"^\*\*Version 1\.1\.0 in brief\.\*\*.*?\n", "", text, flags=re.MULTILINE)
    text, n2 = re.subn(r" Worked example: idr_k-0008 .*?(?=\n)", "", text)
    if (n1, n2) != (1, 1):
        raise SystemExit(f"spec v2 cuts matched {(n1, n2)}, expected (1, 1)")
    for sec in CUT:
        text, n = re.subn(
            r"^## " + sec + r".*?(?=^## |\Z)", "", text, flags=re.DOTALL | re.MULTILINE
        )
        if n != CUT_COUNT[sec]:
            raise SystemExit(
                f"spec: section '{sec}' found {n} times, expected {CUT_COUNT[sec]}"
            )
    if "blind:strip" in text or re.search(r"idr_k-\d{4}", text):
        raise SystemExit("spec: a strip block or a case id survived the cut")
    return text.rstrip() + "\n"


def strip_rulings(text):
    rows = {}  # the ruling row itself is the first row with that number; later rows are the confirmation table's
    for ln in text.splitlines():
        for r in KEEP_RULINGS:
            if ln.startswith(f"| {r} |"):
                rows.setdefault(r, ln)
    if set(rows) != set(KEEP_RULINGS):
        raise SystemExit(f"rulings: found {sorted(rows)}, expected {KEEP_RULINGS}")
    for r, pat, _ in RULING_CUTS:
        rows[r], n = re.subn(pat, "", rows[r])
        if n != 1:
            raise SystemExit(f"rulings: cut in {r} matched {n} times, expected 1")
    body = "\n".join(rows[r] for r in KEEP_RULINGS)
    if re.search(r"idr_k-\d{4}", body):
        raise SystemExit("rulings: a case id survived the cut")
    return (
        "# Stage K rulings that bind `risk.intraday.delta_gamma_bound` (excerpt)\n\n"
        "From `stage-k-rulings-w1.md` (CONFIRMED 2026-11-19). KR-15 corrects KR-7 and KR-17 completes it; they\n"
        "bind together. Only these four rulings are copied; text naming test cases or acceptance results is cut.\n\n"
        "| # | Point | Ruling |\n|---|---|---|\n" + body + "\n"
    )


def write(pk, rel, data):
    p = pk / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    p.write_bytes(data)


def skeleton():
    return dict.fromkeys(FIELDS)


def build(root, pk):
    write(
        pk,
        "specs/intraday-risk-bounds.blind.md",
        strip_spec((root / SPEC).read_text(encoding="utf-8")),
    )
    write(
        pk,
        "rulings/stage-k-rulings-k5a.blind.md",
        strip_rulings((root / RULINGS).read_text(encoding="utf-8")),
    )
    rows = [
        {"case_id": cid, "operation": op, "inputs": inp} for cid, _, op, inp in CASES
    ]
    write(
        pk,
        f"inputs/{ITEM}.inputs.json",
        json.dumps({"item": ITEM, "cases": rows}, indent=1) + "\n",
    )
    tmpl = {
        "fields": FIELDS,
        "results_skeleton": {"cases": {cid: skeleton() for cid, *_ in CASES}},
    }
    write(pk, "output_template.json", json.dumps(tmpl, indent=1) + "\n")
    write(pk, "README.md", README.format(n=len(CASES)))
    files = sorted(
        p.relative_to(pk).as_posix()
        for p in pk.rglob("*")
        if p.is_file() and p.name != "MANIFEST.sha256"
    )
    man = "".join(
        f"{hashlib.sha256((pk / f).read_bytes()).hexdigest()}  {f}\n" for f in files
    )
    write(pk, "MANIFEST.sha256", man)
    return files, hashlib.sha256(man.encode()).hexdigest()


def main():
    root, pk = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    if (pk / ".git").exists() or any((q / ".git").exists() for q in pk.parents):
        raise SystemExit("packet dir is inside a git worktree; refusing")
    if pk.exists() and any(pk.iterdir()):
        raise SystemExit(
            f"{pk} is not empty; remove it first so no stale file survives"
        )
    files, h = build(root, pk)
    print(f"packet {pk}: {len(files)} files; MANIFEST.sha256 {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
