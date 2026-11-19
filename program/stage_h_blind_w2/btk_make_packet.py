"""Stage K blind packet (DR-H2) for K-8e FRTB backtesting: the 12 btk_k value cases not checked against a printed
Basel figure (btk_k-0013 to 0024; 0001 to 0012 count already, MAR99 Table 2).

Writes, into <packet dir> (which must lie outside every repository worktree):
  README.md                                 the deriver's rules: read only this folder, standard-library Python, outputs
  specs/frtb-ima-backtest.blind.md          the K-8e spec with "Worked example", "Goldens" and "Acceptance" cut, the
                                            printed MAR99 Table 2 probabilities cut from Sources, the tlk_k sentence cut
  rulings/stage-k-rulings-w1b.blind.md      KR-40, 42, 44 (labelled inferred), 45, 46, 47 only; the KR-44 sentence that
                                            names goldens and their outcomes is cut, so is every SA-CCR ruling
  tables/frtb-ima-backtest-tables.blind.json  only the keys the rules use as a lookup or constant (multipliers at 250,
                                            limits, thresholds); the printed Table 1 and Table 2 probabilities are cut,
                                            because the rules define the zone boundaries and the probabilities by the
                                            binomial rule, not as a lookup
  inputs/btk.inputs.json                    per case: case_id, operation, inputs (CASES below; nothing else)
  output_template.json                      field definitions and a results skeleton (every field null)
  MANIFEST.sha256                           SHA-256 of every file above
Never reads btk_expected.json or the golden file; the inputs are written out in CASES (btk_compare.py --self-test
checks them against the golden on the hidden side).

    python -I program/stage_h_blind_w2/btk_make_packet.py <checkout> C:/Work/Claude/qf-blind/btk_packet
"""
import hashlib
import json
import re
import sys
from pathlib import Path

SPEC = "specifications/06-risk/frtb-ima-backtest.md"
RULINGS = "specifications/stage-k-rulings-w1b.md"
TABLE = "specifications/06-risk/frtb-ima-backtest-tables.json"
CUT = ("Worked example", "Goldens", "Acceptance")
KEEP_RULINGS = ("KR-40", "KR-42", "KR-44", "KR-45", "KR-46", "KR-47")
KEEP_TABLE_KEYS = ("source", "coverage", "amber_from_cumulative", "red_from_cumulative", "table_observations",
                   "multiplier_250", "multiplier_red", "desk_limit_99", "desk_limit_975", "max_observations")

Z, D, C = "risk.frtb.backtest.zone", "risk.frtb.backtest.desk", "risk.frtb.backtest.count"
CASES = [
    ("btk_k-0013", Z, {"observations": 250, "exceptions_actual": 3, "exceptions_hypothetical": 7}),
    ("btk_k-0014", Z, {"observations": 500, "exceptions_actual": 9, "exceptions_hypothetical": 8}),
    ("btk_k-0015", Z, {"observations": 100, "exceptions_actual": 2, "exceptions_hypothetical": 0}),
    ("btk_k-0016", Z, {"observations": 1000, "exceptions_actual": 15, "exceptions_hypothetical": 15}),
    ("btk_k-0017", Z, {"observations": 1, "exceptions_actual": 0, "exceptions_hypothetical": 0}),
    ("btk_k-0018", Z, {"observations": 260, "exceptions_actual": 6, "exceptions_hypothetical": 6}),
    ("btk_k-0019", D, {"observations": 250, "exceptions_99_actual": 12, "exceptions_99_hypothetical": 10,
                       "exceptions_975_actual": 30, "exceptions_975_hypothetical": 28}),
    ("btk_k-0020", D, {"observations": 250, "exceptions_99_actual": 13, "exceptions_99_hypothetical": 0,
                       "exceptions_975_actual": 0, "exceptions_975_hypothetical": 0}),
    ("btk_k-0021", D, {"observations": 250, "exceptions_99_actual": 0, "exceptions_99_hypothetical": 0,
                       "exceptions_975_actual": 0, "exceptions_975_hypothetical": 31}),
    ("btk_k-0022", D, {"observations": 250, "exceptions_99_actual": 4, "exceptions_99_hypothetical": 6,
                       "exceptions_975_actual": 11, "exceptions_975_hypothetical": 9}),
    ("btk_k-0023", D, {"observations": 300, "exceptions_99_actual": 12, "exceptions_99_hypothetical": 13,
                       "exceptions_975_actual": 31, "exceptions_975_hypothetical": 30}),
    ("btk_k-0024", C, {"var": [1.0, 1.0, None, 2.0, 0.5], "actual": [-1.0, -1.25, 0.3, None, 0.0],
                       "hypothetical": [-1.5, 0.0, 0.1, -2.5, -0.5]}),
]

FIELDS = {
    Z: {"exceptions": "integer, the overall exception count used for the zone",
        "cumulative_probability": "real in [0, 1], P(X <= exceptions) for X ~ Binomial(observations, 0.01)",
        "zone": "string, one of GREEN, AMBER, RED",
        "amber_from": "integer, the smallest count in the amber zone", "red_from": "integer, the smallest count in the red zone",
        "multiplier": "real, or null where the rules give no multiplier"},
    D: {"exceptions_99": "integer", "exceptions_975": "integer",
        "cumulative_probability_99": "real in [0, 1]", "cumulative_probability_975": "real in [0, 1]",
        "breach_99": "boolean", "breach_975": "boolean", "eligible": "boolean"},
    C: {"observations": "integer", "exceptions_actual": "integer", "exceptions_hypothetical": "integer",
        "exceptions": "integer", "days_actual": "list of integers, 0-based day indices, ascending",
        "days_hypothetical": "list of integers, 0-based day indices, ascending"},
}


def skeleton(op):
    return dict.fromkeys(FIELDS[op])


README = """# K-8e blind re-derivation packet (DR-H2): FRTB backtesting zones, desk limits, exception counts

You are the deriver. From the rules in this folder alone, write your own small reference implementation and
compute the outputs of the {n} cases in `inputs/btk.inputs.json`. Nobody will tell you whether you are right until
your results are frozen.

## Hard rules

1. Read nothing outside this folder, except your own working folder `C:/Work/Claude/qf-blind/btk_blind/`, where
   everything you write goes. No repository, no other folder on this machine (not even a listing of the parent
   folder), no web page, no earlier conversation about these operations. If a rule here is unclear, decide, write
   the decision down (rule 4) and go on.
2. Write your reference yourself in Python using the standard library only: no SciPy, NumPy, mpmath or any other
   package, and no imports from any repository. How you evaluate the binomial sums is your choice (for example
   exact rational arithmetic with `fractions.Fraction`, or `decimal` at high precision); state the choice in
   `notes.md`. Convert to binary64 only at the end.
3. Do not round. Report every real as a JSON number at full binary64 precision (Python `json.dumps` of the float).
   Comparison classes, fixed before you started: probabilities use the tolerance class `simple_analytic`,
   |blind - expected| <= 1e-12 + 1e-10 x max(|blind|, |expected|); integers, zones, booleans, the multiplier, null
   and the day lists compare exactly. Every reported field of a case must agree for the case to agree.
4. Write `notes.md`: every ambiguity you met and every assumption you made, each with the case ids it affects and
   the file and section of the rule you read. Write it while you work, not afterwards from memory.

## What to produce (in `C:/Work/Claude/qf-blind/btk_blind/`)

1. `blind_results.json`: copy `output_template.json`'s `results_skeleton` object (it has the form
   `{{"cases": {{"<case_id>": {{...}}}}}}`) and replace every null with your value. Keep the nesting exactly as in the
   skeleton: the case object holds the output fields directly (no extra "outputs" wrapper). A field that the rules
   say has no value for that case stays null. Field meanings are in `output_template.json` under `fields`.
2. `blind_ref.py` (your reference) and `notes.md`.
3. Then, and before you see or ask for anything else: compute the SHA-256 of `blind_results.json`
   (`python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" blind_results.json`),
   write it to `blind_results.sha256`, and report that hash as the first line of your hand-back. After that,
   never change `blind_results.json`; a later correction goes in a separate file with its reason.

## What is here

- `specs/frtb-ima-backtest.blind.md`: the spec with its worked example, case tables and acceptance section removed.
  Rules, formulas, input and output schemas, errors and limits are complete.
- `rulings/stage-k-rulings-w1b.blind.md`: the rulings that decide the choices the spec leaves open. KR-44 is an
  inferred reading (labelled so); apply it as written.
- `tables/frtb-ima-backtest-tables.blind.json`: the constants and the published multipliers the rules use.
- `inputs/btk.inputs.json`: per case the case id, the operation and its inputs. Every case is a value case; errors
  are out of scope.
- `output_template.json`: what to report per operation and per case.
- `MANIFEST.sha256`: hashes of every file here. Check them first (`sha256sum -c MANIFEST.sha256` or Python) and
  say in `notes.md` whether they matched.
"""


def sub1(pattern, repl, text, what, flags=0):
    text, n = re.subn(pattern, repl, text, flags=flags)
    if n != 1:
        raise SystemExit(f"{what}: pattern found {n} times, expected 1")
    return text


def strip_spec(text):
    for sec in CUT:
        text = sub1(r"^## " + sec + r".*?(?=^## |\Z)", "", text, f"section '{sec}'", re.S | re.M)
    text = sub1(r"all 176 printed numbers transcribed into `frtb-ima-backtest-tables\.json`",
                "printed numbers not in this packet; no operation here uses them", text, "Table 1 note")
    text = sub1(r"cumulative probabilities 8\.11%.*?99\.99%; ",
                "cumulative probabilities at 250 observations for 0 to 10 exceptions (printed figures removed from "
                "this copy); ", text, "Table 2 figures")
    text = sub1(r"^- The same Table 2 was read on the bis\.org web page.*?\n", "", text, "bis.org line", re.M)
    text = sub1(r" As an outside check of the \*\*existing\*\* operation, suite `tlk_k`.*?not compared\)\.", "", text,
                "tlk_k sentence")
    text = sub1(r"Tables shared by the four builds: `specifications/06-risk/frtb-ima-backtest-tables\.json`\.",
                "Table in this packet: `tables/frtb-ima-backtest-tables.blind.json` (the keys the rules use).",
                text, "table pointer")
    return text.rstrip() + "\n"


def strip_rulings(text):
    lines = text.splitlines()
    head = [ln for ln in lines[:12] if ln.startswith("| # |") or ln.startswith("|---|")][:2]
    rows = []
    for r in KEEP_RULINGS:
        row = [ln for ln in lines if ln.startswith(f"| {r} |")]
        if not row:
            raise SystemExit(f"ruling {r} not found")
        row = row[0]
        if r == "KR-44":
            row = sub1(r" Goldens btk_k-0019 \(12 and 30: eligible\) and btk_k-0021 \(31: breach\) pin our reading", "",
                       row, "KR-44 golden sentence")
        rows.append(row)
    return ("# Stage K rulings wave 1b: excerpt for K-8e (FRTB backtesting)\n\n"
            "From `specifications/stage-k-rulings-w1b.md`, confirmed 2026-11-19 by the stage K coordinator. Only the "
            "K-8e rulings these operations use. Evidence classes: read (the source text on the page), inferred (our "
            "reading where the text is silent or ambiguous). Page numbers are those of the Basel Framework PDF.\n\n"
            "**KR-44 is an inferred reading**: the regulator text allows a second reading (30 exceptions at the 97.5th "
            "percentile itself a breach); the ruling chooses \"more than\" for both numbers and is to be applied as "
            "written.\n\n" + "\n".join(head + rows) + "\n\n"
            "Cut from this copy: KR-30 to KR-39 (SA-CCR), KR-41 (acceptance against printed figures), KR-43 (the "
            "stage F operation's check), the confirmation notes, and one KR-44 sentence that named test cases.\n")


def strip_table(text):
    full = json.loads(text)
    d = {k: full[k] for k in KEEP_TABLE_KEYS}  # KeyError if a key is gone; values unchanged (1.50 prints as 1.5)
    d["note"] = ("Blind-packet copy: the printed MAR99 Table 1 and Table 2 probabilities are removed; the rules define "
                 "probabilities and zone boundaries by the binomial rule, not by lookup.")
    return json.dumps(d, indent=1) + "\n"


def write(pk, rel, data):
    p = pk / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)


def main():
    root, pk = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    if (pk / ".git").exists() or any((q / ".git").exists() for q in pk.parents):
        raise SystemExit("packet dir is inside a git worktree; refusing")
    if pk.exists() and any(pk.iterdir()):
        raise SystemExit(f"{pk} is not empty; remove it first so no stale file survives")
    write(pk, "specs/frtb-ima-backtest.blind.md", strip_spec((root / SPEC).read_text(encoding="utf-8")))
    write(pk, "rulings/stage-k-rulings-w1b.blind.md", strip_rulings((root / RULINGS).read_text(encoding="utf-8")))
    write(pk, "tables/frtb-ima-backtest-tables.blind.json", strip_table((root / TABLE).read_text(encoding="utf-8")))
    rows = [{"case_id": cid, "operation": op, "inputs": inp} for cid, op, inp in CASES]
    write(pk, "inputs/btk.inputs.json", json.dumps({"item": "K-8e", "cases": rows}, indent=1) + "\n")
    tmpl = {"fields": FIELDS, "results_skeleton": {"cases": {cid: skeleton(op) for cid, op, _ in CASES}}}
    write(pk, "output_template.json", json.dumps(tmpl, indent=1) + "\n")
    write(pk, "README.md", README.format(n=len(CASES)))
    files = sorted(p.relative_to(pk).as_posix() for p in pk.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
    man = "".join(f"{hashlib.sha256((pk / f).read_bytes()).hexdigest()}  {f}\n" for f in files)
    write(pk, "MANIFEST.sha256", man)
    print(f"packet {pk}: {len(files)} files; MANIFEST.sha256 {hashlib.sha256(man.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
