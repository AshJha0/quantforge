"""Hidden side of the PUB blind packet (KA-C18, program/STAGE_K_BLIND_PUB.md): split the 28 printed-figure cases
(saccr_k-0001..0005, btk_k-0001..0012, tlk_k-0001..0011) into an inputs file and an expected file.

  pub_cases.json     case id, operation, inputs only (read by pub_make_packet.py, which never reads a golden)
  pub_expected.json  outputs, per-output tolerance class, and the SHA-256 of each golden file read (hidden; never in
                     the packet)

    python -I program/stage_h_blind_w2/pub_extract.py <checkout>

Run once before the packet is built; pub_compare.py --self-test checks both files against the goldens again.
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUITES = {"saccr_k": range(1, 6), "btk_k": range(1, 13), "tlk_k": range(1, 12)}


def ids():
    return [f"{s}-{i:04d}" for s, r in SUITES.items() for i in r]


def main():
    root = Path(sys.argv[1])
    cases, expected, shas = [], {}, {}
    for suite, rng in SUITES.items():
        p = root / "datasets/golden/stage_k" / f"{suite}.json"
        raw = p.read_bytes()
        shas[f"datasets/golden/stage_k/{suite}.json"] = hashlib.sha256(raw).hexdigest()
        gold = {c["case_id"]: c for c in json.loads(raw.decode("utf-8"))["cases"]}
        for i in rng:
            c = gold[f"{suite}-{i:04d}"]
            assert c["expected"]["status"] == "ok", c["case_id"]
            cases.append({"case_id": c["case_id"], "operation": c["operation"], "inputs": c["inputs"]})
            expected[c["case_id"]] = {"operation": c["operation"], "tolerance_class": c["tolerance_class"],
                                      "output_classes": c.get("output_classes", {}),
                                      "outputs": c["expected"]["outputs"]}
    assert [c["case_id"] for c in cases] == ids()
    (HERE / "pub_cases.json").write_text(json.dumps({"cases": cases}, indent=1) + "\n", encoding="utf-8", newline="\n")
    (HERE / "pub_expected.json").write_text(json.dumps({"golden_sha256": shas, "cases": expected}, indent=1) + "\n",
                                            encoding="utf-8", newline="\n")
    print(f"{len(cases)} cases; goldens {shas}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
