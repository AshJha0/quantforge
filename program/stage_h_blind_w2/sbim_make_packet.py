"""K-8h blind packet (DR-H2) for the 29 hand value cases of specifications/06-risk/sbim-placeholder.md.

Built exactly like k2_make_packet.py (stage K wave 2). Writes, into <packet dir> (which must lie outside every
repository worktree and be empty):
  README.md                              what the blind lane must produce, and the read-nothing-else rule
  specs/sbim-placeholder.blind.md        the PROPOSED spec with the sections "Worked example", "Hand cases" and
                                         "Acceptance" cut (they print expected values, intermediates and arithmetic;
                                         W1B lesson: an acceptance line can name an output)
  rulings/stage-k-rulings-sbim.blind.md  the rulings with KR-141 (gate classes) cut
  tables/sbim-placeholder.json           the placeholder table, byte for byte
  inputs/K-8h.inputs.json                per case: case_id, operation, inputs (from sbim_cases.py; nothing else)
  output_template.json                   field definitions and a results skeleton (every field to report, null)
  MANIFEST.sha256                        SHA-256 of every file above
Never reads sbim_expected.json. The skeleton's keys (which groups, risk classes, kinds, buckets, factors
and groups exist for a case) come from running sbim_ref.sbim on the case inputs and replacing every leaf by null:
the structure follows from the rules and inputs, and no value is written.

    python -I program/stage_h_blind_w2/sbim_make_packet.py <checkout> C:/Work/Claude/qf-blind/sbim_packet
"""
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sbim_cases import CASES  # noqa: E402
import sbim_ref  # noqa: E402

SPEC = "specifications/06-risk/sbim-placeholder.md"
RULINGS = "specifications/stage-k-rulings-sbim.md"
TABLE = "specifications/tables/stage_k/sbim-placeholder.json"
CUT = ("Worked example", "Hand cases", "Acceptance")
CUT_RULINGS = ("KR-141",)
OP = "risk.sbim.placeholder"

PFX = "groups[<g>].risk_classes[<rc>]"
FIELDS = {
    "total": "sum over groups (step 9)",
    "groups[<g>].im": "group margin (step 8)",
    PFX + ".im": "risk class margin = delta + vega + curvature margins present (step 7)",
    PFX + ".<delta|vega>.margin": "M + K_residual (step 5)",
    PFX + ".<delta|vega>.buckets[<b>].k_b": "K_b of a non-residual bucket (step 4)",
    PFX + ".<delta|vega>.buckets[<b>].s_b": "S_b, the clipped sum (step 4)",
    PFX + ".<delta|vega>.buckets[<b>].sum_ws": "signed sum of WS_k in the bucket before clipping (step 4)",
    PFX + ".<delta|vega>.residual_k": "K_b of the EQ RESIDUAL bucket (step 4); only when it has factors",
    PFX + ".<delta|vega>.cr[<group>]": "concentration factor of the group (step 2): currency for IR and FX, issuer for EQ",
    PFX + ".<delta|vega>.ws[<factor>]": "weighted sensitivity of the risk factor (step 3); factor keys as in step 1",
    PFX + ".curvature.margin": "C_non + C_res (step 6)",
    PFX + ".curvature.cvr[<factor>]": "CVR_k of the vega risk factor (step 6)",
    PFX + ".curvature.buckets[<b>].k_b": "curvature K_b of a non-residual bucket",
    PFX + ".curvature.buckets[<b>].s_b": "curvature S_b (clipped)",
    PFX + ".curvature.buckets[<b>].sum_cvr": "signed sum of CVR_k in the bucket",
    PFX + ".curvature.sum_cvr": "sum of CVR over the non-residual factors",
    PFX + ".curvature.theta": "theta of the non-residual part",
    PFX + ".curvature.lambda": "lambda of the non-residual part",
    PFX + ".curvature.residual.k": "K_res of the EQ RESIDUAL bucket",
    PFX + ".curvature.residual.sum_cvr": "sum of the residual CVR",
    PFX + ".curvature.residual.theta": "theta of the residual part",
    PFX + ".curvature.residual.lambda": "lambda of the residual part",
    PFX + ".curvature.residual.margin": "C_res",
}


def nulls(o):
    if isinstance(o, dict):
        return {k: nulls(v) for k, v in o.items()}
    return None


def skeleton(P, inp):
    return nulls(sbim_ref.sbim(P, inp))


README = """# K-8h blind re-derivation packet (DR-H2): sensitivity-based initial margin on placeholder weights

You are the blind lane. Your job: from the rules in this folder alone, write your own small reference
implementation and compute the outputs of the {n} cases in `inputs/`. Nobody will tell you whether you are right
until your results are frozen.

Every number here is computed on PLACEHOLDER WEIGHTS (`tables/sbim-placeholder.json`): round numbers with no
relation to any industry or regulatory margin model. Do not look for, recall or use any outside parameter value.

## Hard rules

1. Read nothing outside this folder. No repository, no other folder on this machine, no web page, no earlier
   conversation about this spec. If a rule here is unclear, decide, write the decision down (rule 4) and go on.
2. Write your reference yourself: plain Python (standard library only is fine), no imports from any repository.
   Keep it in your own working folder next to (not inside) this packet, for example `../sbim_blind/`.
3. Do not round. Report every number as a JSON number at full binary64 precision (Python `json.dumps` of the float).
   The rulings (KR-139) fix the comparison tolerance at 1e-12 relative (1e-15 absolute at 0); you do not need to
   aim for it, just compute in binary64.
4. Write `notes.md`: every ambiguity you met and every assumption you made, each with the case ids it affects and
   the file and section of the rule you read. Write it while you work, not afterwards from memory.

## What to produce (in your own working folder)

1. `blind_results.json`: copy `output_template.json`'s `results_skeleton` object (it has the form
   `{{"cases": {{"<case_id>": {{...}}}}}}`) and replace every null with your value. Keep the nesting exactly as in the
   skeleton: the case object holds the output fields directly (no extra "outputs" wrapper), keyed objects stay
   objects. Field meanings are in `output_template.json` under `fields`. If you believe a field in the skeleton
   should not exist for that case, leave it null and say why in `notes.md`.
2. `blind_ref.py` (your reference) and `notes.md`.
3. Then, and before you see or ask for anything else: compute the SHA-256 of `blind_results.json`
   (`python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" blind_results.json`),
   write it to `blind_results.sha256`, and report that hash as the first line of your hand-back. After that,
   never change `blind_results.json`; a later correction goes in a separate file with its reason.

## What is here

- `specs/sbim-placeholder.blind.md`: the draft spec with its worked example, hand cases and acceptance sections
  removed. Inputs, every formula step, outputs, errors and limits are complete.
- `rulings/stage-k-rulings-sbim.blind.md`: the rulings that decide the choices the spec leaves open.
- `tables/sbim-placeholder.json`: the placeholder parameters (decimal strings).
- `inputs/K-8h.inputs.json`: per case the case id, the operation and its inputs. Each input object is complete.
- `output_template.json`: what to report per case.
- `MANIFEST.sha256`: hashes of every file here. Check them first (`sha256sum -c MANIFEST.sha256` or Python) and
  say in `notes.md` whether they matched.

Errors are out of scope: every case here is a value case.
"""


def strip_spec(text):
    for sec in CUT:
        text, n = re.subn(r"^## " + sec + r".*?(?=^## |\Z)", "", text, flags=re.S | re.M)
        if n != 1:
            raise SystemExit(f"spec: section '{sec}' found {n} times, expected 1")
    return text


def strip_rulings(text):
    out = [ln for ln in text.splitlines() if not any(ln.startswith(f"| {r} |") for r in CUT_RULINGS)]
    return "\n".join(out) + "\n" + "\nCut from this copy: " + ", ".join(CUT_RULINGS) + " (not used by these cases).\n"


def write(pk, rel, data):
    p = pk / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    p.write_bytes(data)


def main():
    root, pk = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    if (pk / ".git").exists() or any((q / ".git").exists() for q in pk.parents):
        raise SystemExit("packet dir is inside a git worktree; refusing")
    if pk.exists() and any(pk.iterdir()):
        raise SystemExit(f"{pk} is not empty; remove it first so no stale file survives")
    P = sbim_ref.load_table(root)
    write(pk, "specs/sbim-placeholder.blind.md", strip_spec((root / SPEC).read_text(encoding="utf-8")))
    write(pk, "rulings/stage-k-rulings-sbim.blind.md", strip_rulings((root / RULINGS).read_text(encoding="utf-8")))
    write(pk, "tables/sbim-placeholder.json", (root / TABLE).read_bytes())
    rows = [{"case_id": cid, "operation": OP, "inputs": inp} for cid, inp in CASES]
    write(pk, "inputs/K-8h.inputs.json", json.dumps({"item": "K-8h", "cases": rows}, indent=1) + "\n")
    tmpl = {"fields": FIELDS,
            "path_notation": "a[<key>].b means object a, member <key>, member b",
            "results_skeleton": {"cases": {cid: skeleton(P, inp) for cid, inp in CASES}}}
    write(pk, "output_template.json", json.dumps(tmpl, indent=1) + "\n")
    write(pk, "README.md", README.format(n=len(CASES)))
    files = sorted(p.relative_to(pk).as_posix() for p in pk.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
    man = "".join(f"{hashlib.sha256((pk / f).read_bytes()).hexdigest()}  {f}\n" for f in files)
    write(pk, "MANIFEST.sha256", man)
    print(f"packet {pk}: {len(files)} files; MANIFEST.sha256 {hashlib.sha256(man.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
