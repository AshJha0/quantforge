"""H-24 blind packet 2 comparison (HR-114). Mapping fixed before comparing: blind field names equal the golden
field names (rates.blind.md table), nothing renamed; `label` compared as a string where the golden has one;
decimal strings compared by value (HR-100); `yield` (binary64) compared to the golden's root_finding class,
|a - e| <= 1e-10 + 1e-10 max(|a|, |e|). Classes: MATCH, REPRESENTATION-ONLY (equal by value, different text),
VALUE MISMATCH, MISSING. One run, no rerun of the lane.

    python program/stage_h_blind_w2/rates2_compare.py
"""
import hashlib
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
B = ROOT / "stage_h_blind" / "rates2" / "blind_results.json"
SHA = "3a3a9db05ec1a1a7eeba01bc736672933f27609d050d8020da466496720ca354"
CASES = ["rtc_h-0004", "rtc_h-0007", "rtc_h-0011", "rtc_h-0012", "fut_h-0004", "fut_h-0005", "fut_h-0006"]


def field(a, e):
    if isinstance(e, float):
        return "MATCH" if abs(a - e) <= 1e-10 + 1e-10 * max(abs(a), abs(e)) else "VALUE MISMATCH"
    if isinstance(e, list):
        if not isinstance(a, list) or len(a) != len(e):
            return "VALUE MISMATCH"
        r = [field(x, y) for x, y in zip(a, e)]
        return max(r, key=["MATCH", "REPRESENTATION-ONLY", "VALUE MISMATCH"].index)
    if a == e:
        return "MATCH"
    try:
        return "REPRESENTATION-ONLY" if Decimal(a) == Decimal(e) else "VALUE MISMATCH"
    except Exception:
        return "VALUE MISMATCH"


def main():
    assert hashlib.sha256(B.read_bytes()).hexdigest() == SHA, "blind file changed"
    blind = json.loads(B.read_text(encoding="utf-8"))
    gold = {}
    for s in ("rtc_h", "fut_h"):
        for c in json.loads((ROOT / f"datasets/golden/stage_h/{s}.json").read_text(encoding="utf-8"))["cases"]:
            gold[c["case_id"]] = c["expected"].get("outputs")
    for cid in CASES:
        if cid not in blind:
            print(cid, "MISSING")
            continue
        res = {k: field(blind[cid].get(k), v) if k in blind[cid] else "MISSING" for k, v in gold[cid].items()}
        worst = max(res.values(), key=["MATCH", "REPRESENTATION-ONLY", "MISSING", "VALUE MISMATCH"].index)
        print(cid, worst, json.dumps(res, sort_keys=True))


if __name__ == "__main__":
    main()
