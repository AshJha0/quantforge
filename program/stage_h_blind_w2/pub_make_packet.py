"""Stage K blind packet (DR-H2) for the 28 cases that had only a figure printed in the regulator text (audit KA-C18,
ruling KR-210): saccr_k-0001..0005 (CRE99 Examples 1 to 5), btk_k-0001..0012 and tlk_k-0001..0011 (MAR99 Table 2).
Record: program/STAGE_K_BLIND_PUB.md. Pattern: btk_make_packet.py (K-8e) and saccr_blind_packet.py (W1B).

Writes, into <packet dir> (which must lie outside every repository worktree):
  README.md                                   the deriver's rules (packet and own folder only; standard-library Python;
                                              no remembered published example value)
  specs/sa-ccr.blind.md                       SA-CCR spec without "Worked example", "Goldens", "Acceptance",
                                              "Convergence and limit cases", and without the [CRE99] and [BCBS279]
                                              source lines (they list the five printed EADs and name the examples)
  specs/frtb-ima-backtest.blind.md            K-8e spec stripped as btk_make_packet.strip_spec (worked example, goldens,
                                              acceptance, the printed MAR99 Table 2 probabilities, the tlk_k sentence)
  specs/traffic-light.blind.md                the `risk.backtest.traffic_light` section of var-es-and-backtests.md, the
                                              loss convention, and source [S8] only (its Acceptance names MAR99 Table 2)
  rulings/stage-k-rulings.blind.md            KR-32 to KR-40, KR-42, KR-45 only; KR-30, KR-31 (printed EADs and an
                                              intermediate), KR-41, KR-43 (acceptance against printed figures) are cut
  tables/sa-ccr-parameters.json               supervisory parameters, unchanged (rules, not examples)
  tables/frtb-ima-backtest-tables.blind.json  btk_make_packet.strip_table: multipliers and constants only, no printed
                                              Table 1 or Table 2 probability for any sample size
  inputs/pub.inputs.json                      per case: case_id, operation, inputs (from pub_cases.json; nothing else)
  output_template.json                        field definitions and a results skeleton (every field null)
  MANIFEST.sha256                             SHA-256 of every file above
Never reads pub_expected.json or a golden file.

    python -I program/stage_h_blind_w2/pub_make_packet.py <checkout> C:/Work/Claude/qf-blind/pub_packet
"""
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from btk_make_packet import strip_spec as strip_btk_spec, strip_table as strip_btk_table, sub1  # noqa: E402

SACCR_SPEC = "specifications/06-risk/sa-ccr.md"
SACCR_PARAMS = "specifications/06-risk/sa-ccr-parameters.json"
BTK_SPEC = "specifications/06-risk/frtb-ima-backtest.md"
BTK_TABLE = "specifications/06-risk/frtb-ima-backtest-tables.json"
TL_SPEC = "specifications/06-risk/var-es-and-backtests.md"
RULINGS = "specifications/stage-k-rulings-w1b.md"
SACCR_CUT = ("Worked example", "Goldens", "Acceptance", "Convergence and limit cases")
KEEP_RULINGS = ("KR-32", "KR-33", "KR-34", "KR-35", "KR-36", "KR-37", "KR-38", "KR-39", "KR-40", "KR-42", "KR-45")
DEST = "C:/Work/Claude/qf-blind/pub_blind/"

S, Z, T = "risk.saccr.ead", "risk.frtb.backtest.zone", "risk.backtest.traffic_light"
FIELDS = {
    S: {"ead": "real", "rc": "real", "pfe": "real", "multiplier": "real", "addon_aggregate": "real",
        "addon": "object with exactly the keys IR, FX, CREDIT, EQUITY, COMMODITY, each a real",
        "v": "real", "c": "real", "margined": "boolean", "mpor_days": "integer or null", "ead_unmargined": "real or null",
        "capped": "boolean",
        "hedging_sets": "array of objects {asset_class, treatment, key, addon}, in the order the spec's Outputs paragraph fixes",
        "trades": "array in input order of objects {id, supervisory_duration, adjusted_notional, maturity_factor, delta, "
                  "effective_notional, supervisory_factor}; supervisory_duration null outside IR and CREDIT"},
    Z: {"exceptions": "integer, the overall exception count used for the zone",
        "cumulative_probability": "real in [0, 1], P(X <= exceptions) for X ~ Binomial(observations, 0.01)",
        "zone": "string, one of GREEN, AMBER, RED",
        "amber_from": "integer, the smallest count in the amber zone", "red_from": "integer, the smallest count in the red zone",
        "multiplier": "real, or null where the rules give no multiplier"},
    T: {"cumulative_probability": "real in [0, 1], P(X <= exceptions) for X ~ Binomial(observations, 1 - confidence)",
        "zone": "string, one of GREEN, YELLOW, RED", "plus_factor": "real, or null where the rules give none"},
}


def skeleton(op):
    return dict.fromkeys(FIELDS[op])


README = """# Blind re-derivation packet (DR-H2): SA-CCR EAD, FRTB backtesting zone, Basel traffic light

You are the deriver. From the rules in this folder alone, write your own small reference implementation and
compute every output of the {n} cases in `inputs/pub.inputs.json`. Nobody will tell you whether you are right until
your results are frozen.

## Hard rules

1. Read nothing outside this folder, except your own working folder `{dest}`, where everything you write goes. No
   repository, no other folder on this machine (not even a listing of the parent folder), no web page, no earlier
   conversation about these operations. If a rule here is unclear, decide, write the decision down (rule 5) and go on.
2. Write your reference yourself in Python using the standard library only: no SciPy, NumPy, mpmath or any other
   package, and no imports from any repository. For the binomial sums, exact rational arithmetic
   (`fractions.Fraction`) or `decimal` at high precision is your choice; state it in `notes.md`. Convert to binary64
   only at the end. For the normal distribution function use `math.erfc` or your own series, and say which.
3. **Do not use any remembered value.** Some of these inputs may look like published regulatory examples or a
   published table. Compute every output from the rules here, and never adjust, check or round a result against a
   figure you remember from a regulator's document, a textbook or anywhere else. If you recognise a case, say so in
   `notes.md` (which case, what you think it is) and still compute it from the rules alone.
4. Do not round. Report every real as a JSON number at full binary64 precision (Python `json.dumps` of the float).
   Comparison classes, fixed before you started: every real uses the tolerance class `simple_analytic`,
   |blind - expected| <= 1e-12 + 1e-10 x max(|blind|, |expected|); integers, strings (zones, ids, keys, asset
   classes, treatments), booleans and null compare exactly; arrays element by element in the order the spec fixes.
   Every reported field of a case, nested fields included, must agree for the case to agree.
5. Write `notes.md`: every ambiguity you met and every assumption you made, each with the case ids it affects and the
   file and section of the rule you read. Write it while you work, not afterwards from memory.

## What to produce (in `{dest}`)

1. `blind_results.json`: copy `output_template.json`'s `results_skeleton` object (form
   `{{"cases": {{"<case_id>": {{...}}}}}}`) and replace every null with your value. Keep the nesting exactly as in the
   skeleton: the case object holds the output fields directly (no extra "outputs" wrapper). A field that the rules
   say has no value for that case stays null. Field meanings are in `output_template.json` under `fields`, per
   operation; the full output definitions are in the specs.
2. `blind_ref.py` (your reference) and `notes.md`.
3. Then, and before you see or ask for anything else: compute the SHA-256 of `blind_results.json`
   (`python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" blind_results.json`),
   write it to `blind_results.sha256`, and report that hash as the first line of your hand-back. After that, never
   change `blind_results.json`; a later correction goes in a separate file with its reason.

## What is here

- `specs/sa-ccr.blind.md`: `risk.saccr.ead`, with its worked example, case tables, acceptance and limit-case
  sections removed. Rules, formulas, input and output schemas, errors and limits are complete.
- `specs/frtb-ima-backtest.blind.md`: `risk.frtb.backtest.zone` (and two related operations not used here), with
  the worked example, case tables, acceptance section and printed probabilities removed.
- `specs/traffic-light.blind.md`: `risk.backtest.traffic_light` and the loss convention it uses.
- `rulings/stage-k-rulings.blind.md`: the rulings that decide choices the specs leave open. Rulings labelled
  inferred are our readings; apply them as written.
- `tables/sa-ccr-parameters.json`: the supervisory parameters (Table 2 of the rules and the other constants).
- `tables/frtb-ima-backtest-tables.blind.json`: the constants and the published multipliers the backtesting rules use.
- `inputs/pub.inputs.json`: per case the case id, the operation and its inputs. Every case is a value case.
- `output_template.json`: what to report per operation and per case.
- `MANIFEST.sha256`: hashes of every file here. Check them first and say in `notes.md` whether they matched.
"""


def cut_sections(text, names):
    for sec in names:
        text = sub1(r"^## " + re.escape(sec) + r".*?(?=^## |\Z)", "", text, f"section '{sec}'", re.S | re.M)
    return text


def strip_saccr(text):
    text = cut_sections(text, SACCR_CUT)
    text = sub1(r"^- \[CRE99\].*?\n", "", text, "[CRE99] source line", re.M)
    text = sub1(r"^- \[BCBS279\].*?\n", "", text, "[BCBS279] source line", re.M)
    text = sub1(r"; formula image read on CRE99 p\.528\)", ")", text, "CRE99 page pointer in [CRE52]")
    text = sub1(r"Rulings KR-30 to KR-39 \(`specifications/stage-k-rulings-w1b\.md`\)",
                "Rulings KR-32 to KR-39 (`rulings/stage-k-rulings.blind.md`)", text, "rulings pointer")
    text = sub1(r"^- The supervisory parameters are in `specifications/06-risk/sa-ccr-parameters\.json`.*?\n",
                "- The supervisory parameters are in `tables/sa-ccr-parameters.json`.\n", text, "parameters pointer", re.M)
    return text.rstrip() + "\n"


def strip_traffic_light(text):
    title = text.splitlines()[0]
    conv = re.search(r"^Losses are positive.*?$", text, re.M).group(0)
    sec = re.search(r"^## `risk\.backtest\.traffic_light`.*?(?=^## )", text, re.S | re.M).group(0)
    s8 = re.search(r"^- \[S8\].*?$", text, re.M).group(0)
    return (f"{title}: excerpt for `risk.backtest.traffic_light`\n\n"
            "From `var-es-and-backtests.md` (stage F). Only the loss convention, the operation's section and its source. "
            "Cut from this copy: the other operations, the acceptance section, the other sources.\n\n"
            f"{conv}\n\n{sec.rstrip()}\n\n## Sources\n\n{s8}\n")


def strip_rulings(text):
    lines = text.splitlines()
    head = [ln for ln in lines if ln.startswith("| # |") or ln.startswith("|---|")][:2]
    rows = []
    for r in KEEP_RULINGS:
        row = [ln for ln in lines if ln.startswith(f"| {r} |")]
        if not row:
            raise SystemExit(f"ruling {r} not found")
        rows.append(row[0])
    return ("# Stage K rulings wave 1b: excerpt for SA-CCR and the backtesting zone\n\n"
            "From `specifications/stage-k-rulings-w1b.md`, confirmed 2026-11-19 by the stage K coordinator. Only the "
            "rulings these operations use. Evidence classes: read (the source text on the page), inferred (our reading "
            "where the text is silent or ambiguous). Page numbers are those of the Basel Framework PDF.\n\n"
            + "\n".join(head + rows) + "\n\n"
            "Cut from this copy: KR-30, KR-31 (acceptance rounding against printed figures), KR-41, KR-43 (acceptance "
            "against a printed table), KR-44, KR-46, KR-47 (operations or limits not used here), the confirmation notes.\n")


def write(pk, rel, data):
    p = pk / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)


def build(root, pk, cases):
    write(pk, "specs/sa-ccr.blind.md", strip_saccr((root / SACCR_SPEC).read_text(encoding="utf-8")))
    btk = strip_btk_spec((root / BTK_SPEC).read_text(encoding="utf-8"))
    write(pk, "specs/frtb-ima-backtest.blind.md", btk)
    write(pk, "specs/traffic-light.blind.md", strip_traffic_light((root / TL_SPEC).read_text(encoding="utf-8")))
    write(pk, "rulings/stage-k-rulings.blind.md", strip_rulings((root / RULINGS).read_text(encoding="utf-8")))
    write(pk, "tables/sa-ccr-parameters.json", (root / SACCR_PARAMS).read_bytes())
    write(pk, "tables/frtb-ima-backtest-tables.blind.json", strip_btk_table((root / BTK_TABLE).read_text(encoding="utf-8")))
    write(pk, "inputs/pub.inputs.json", json.dumps({"cases": cases}, indent=1) + "\n")
    tmpl = {"fields": FIELDS, "results_skeleton": {"cases": {c["case_id"]: skeleton(c["operation"]) for c in cases}}}
    write(pk, "output_template.json", json.dumps(tmpl, indent=1) + "\n")
    write(pk, "README.md", README.format(n=len(cases), dest=DEST))
    files = sorted(p.relative_to(pk).as_posix() for p in pk.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
    man = "".join(f"{hashlib.sha256((pk / f).read_bytes()).hexdigest()}  {f}\n" for f in files)
    write(pk, "MANIFEST.sha256", man)
    return files, hashlib.sha256(man.encode()).hexdigest()


def main():
    root, pk = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    if (pk / ".git").exists() or any((q / ".git").exists() for q in pk.parents):
        raise SystemExit("packet dir is inside a git worktree; refusing")
    if pk.exists() and any(pk.iterdir()):
        raise SystemExit(f"{pk} is not empty; remove it first so no stale file survives")
    cases = json.loads((HERE / "pub_cases.json").read_text(encoding="utf-8"))["cases"]
    files, h = build(root, pk, cases)
    print(f"packet {pk}: {len(files)} files; MANIFEST.sha256 {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
