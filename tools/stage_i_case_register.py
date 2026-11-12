#!/usr/bin/env python3
"""Per-case stage I outside register (R6-13), from each golden's `verified_by` (written by the generators only when the
named library agreed within the case tolerance, ruling I-2). Classes: library-primitive (scipy, numpy, QuantLib Greeks
assembled by a numpy solve), reimplementation (hedgebt_i, hedgebtcost_i: spec arithmetic on library values), none.
Writes oracle/outside_register_i_cases.json and prints value-only shares with and without wave 5.

    python tools/stage_i_case_register.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = re.compile(r"scipy|numpy|quantlib|highs", re.I)
REIMPL = {"hedgebt_i", "hedgebtcost_i"}


def main():
    rows = []
    for f in sorted((ROOT / "datasets" / "golden" / "stage_i").glob("*.json")):
        for c in json.loads(f.read_text(encoding="utf-8"))["cases"]:
            libs = [v for v in c["verified_by"] if LIB.search(v)]
            cls = "none" if not libs or c["expected"]["status"] != "ok" else ("reimplementation" if f.stem in REIMPL else "library-primitive")
            rows.append({"case_id": c["case_id"], "suite": f.stem, "value": c["expected"]["status"] == "ok", "sweep": f.stem.endswith("5_i"),
                         "class": cls, "library": ", ".join(libs)})
    (ROOT / "oracle" / "outside_register_i_cases.json").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8", newline="\n")
    for sw in (False, True):
        sel = [r for r in rows if r["value"] and (sw or not r["sweep"])]
        k = sum(r["class"] == "library-primitive" for r in sel)
        print(f"stage I value cases {'with' if sw else 'without'} wave 5: {k} of {len(sel)} = {k / len(sel):.1%}")
    allc = [r for r in rows if not r["sweep"]]
    print(f"old all-case rule without wave 5: {sum(r['class'] == 'library-primitive' for r in allc)} of {len(allc)}")


if __name__ == "__main__":
    main()
