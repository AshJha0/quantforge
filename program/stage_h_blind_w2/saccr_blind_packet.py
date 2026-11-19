"""Stage K wave 1b SA-CCR blind packet (DR-H2). Builds, into <packet dir>:
  sa-ccr.blind.md          spec with Expected/Derivation/Check columns removed (wave2_extract.awk) and with the
                           sections Worked example, Goldens and Acceptance removed (they state outputs or hints)
  sa-ccr-parameters.json   shared parameter table, unchanged
  stage-k-rulings-w1b.md   rulings, unchanged
  saccr.inputs.json        case id, operation, inputs of the 11 hand value cases saccr_k-0006..0016 (nothing else)
  MANIFEST.sha256
Prints only inputs; never reads or prints the 'expected' field.

    python -I saccr_blind_packet.py <checkout> <packet dir>
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

CASES = [f"saccr_k-{i:04d}" for i in range(6, 17)]


def main():
    root, pk = Path(sys.argv[1]), Path(sys.argv[2])
    pk.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent
    spec = root / "specifications/06-risk/sa-ccr.md"
    out = subprocess.run(["awk", "-f", str(here / "wave2_extract.awk"), str(spec)], capture_output=True, check=True).stdout.decode("utf-8")
    for sec in ("Worked example", "Goldens", "Acceptance"):
        out, n = re.subn(r"^## " + sec + r".*?(?=^## |\Z)", "", out, flags=re.S | re.M)
        if n != 1:
            print("section not found once:", sec, file=sys.stderr)
            return 1
    (pk / "sa-ccr.blind.md").write_text(out, encoding="utf-8", newline="\n")
    for f in ("specifications/06-risk/sa-ccr-parameters.json", "specifications/stage-k-rulings-w1b.md"):
        (pk / Path(f).name).write_bytes((root / f).read_bytes())
    g = json.loads((root / "datasets/golden/stage_k/saccr_k.json").read_text(encoding="utf-8"))
    rows = [{"case_id": c["case_id"], "operation": c["operation"], "inputs": c["inputs"]} for c in g["cases"] if c["case_id"] in CASES]
    assert [r["case_id"] for r in rows] == CASES
    (pk / "saccr.inputs.json").write_text(json.dumps(rows, indent=1), encoding="utf-8", newline="\n")
    names = ["sa-ccr.blind.md", "sa-ccr-parameters.json", "stage-k-rulings-w1b.md", "saccr.inputs.json"]
    (pk / "MANIFEST.sha256").write_text("".join(f"{hashlib.sha256((pk / n).read_bytes()).hexdigest()}  {n}\n" for n in names), newline="\n")
    return 0


sys.exit(main())
