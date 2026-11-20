"""Inputs of the K-5a v2 value cases (risk.intraday.delta_gamma_bound, idr_k-0001..0005, 0008..0010 and 0012..0014 (idr_k-0011, h = 0, is all zeros and is left out); ruling
KR-234, audit A response 2026-11-19) for the rerun of the blind packet. Prepared, not run.

Read from datasets/golden/stage_k/idr_k.json (inputs only; the expected values are never read here). Error cases
idr_k-0006 and idr_k-0007 are out of scope: the blind lane derives value cases only.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "datasets" / "golden" / "stage_k" / "idr_k.json"
IDS = tuple(f"idr_k-{i:04d}" for i in (1, 2, 3, 4, 5, 8, 9, 10, 12, 13, 14))
ITEM = "K-5a"
OP = "risk.intraday.delta_gamma_bound"


def load_cases(golden=GOLDEN):
    """[(case_id, item, operation, inputs)] in IDS order; inputs only."""
    doc = json.loads(Path(golden).read_text(encoding="utf-8"))
    by_id = {c["case_id"]: c for c in doc["cases"]}
    out = []
    for cid in IDS:
        c = by_id[cid]
        if c["operation"] != OP or c["expected"]["status"] != "ok":
            raise SystemExit(f"{cid}: not a value case of {OP}")
        out.append((cid, ITEM, OP, c["inputs"]))
    return out


CASES = load_cases()
