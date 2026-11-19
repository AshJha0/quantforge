"""Field-by-field compare of the stage K wave-1 blind derivation (stage_k_blind/w1) against the spec goldens.

Mapping, fixed and committed before the first run (coordinator instruction 2026-11-18):
- Field names: identity. The packet named every output (`status`, `row/*`; `discount_factors`,
  `first_changed_index`, `recomputed`; `sigma`, `threshold`, `fire`, `false_alarm_rate`; `estimate_pnl`, `bound`,
  `label`; `status`, `observed_order`, `extrapolated`).
- Representation only, not a difference: integer against float (2 vs 2.0), key order, an error written as
  `{"status": "error", "error_code": C}` against the golden `error.code` C.
- Golden values below are transcribed from the spec tables (Expected columns; bt rows from the shared log, as the
  spec says). inc_k-0001 is not an `update` case, so it has no `first_changed_index`/`recomputed`.
- Tolerances (the spec's): bt exact; inc 1e-15 absolute; trig 1e-14 relative on sigma, threshold and
  false_alarm_rate (the spec states 1e-14 for sigma and threshold; the same is used for the rate); idr
  estimate_pnl 1e-9 relative; idr `bound` only at the precision given (6 decimals: 5e-7 absolute) and PROVISIONAL
  until the oracle fills it to full precision; rich 1e-12 relative (no spec tolerance; library default).
- Gap-decided fields (KR-12..KR-14, written after the blind run) are compared but not counted as blind:
  idr_k-0006, rich_k-0007 (error code); trig_k-0004 `fire`; bt_k-0004 and bt_k-0006 `row`.
- idr_k-0005 is oracle-pending and was not in the packet.
A case is MATCH when every golden leaf has a blind leaf at the same path, there is no extra blind leaf, and every
pair agrees; otherwise VALUE MISMATCH or SHAPE MISMATCH with the paths.

    python -I program/stage_h_blind_w2/k1_compare.py <stage_k_blind/w1 dir>
Exit 1 if the frozen file's SHA-256 differs from the record or any case does not MATCH.
"""
import hashlib
import json
import sys
from pathlib import Path

SHA = "feba0b810c3f53cb2070faae99c6e2edfa96a654525a5cf6149b56462b3b81b9"
Z = "T00:00:00Z"
R1 = {"sequence": 1, "valid_from": "2026-01-01" + Z, "valid_to": None, "knowledge_time": "2026-01-02" + Z, "value": 100}
R2 = {"sequence": 2, "valid_from": "2026-03-01" + Z, "valid_to": None, "knowledge_time": "2026-03-02" + Z, "value": 110}
R3 = {"sequence": 3, "valid_from": "2026-02-01" + Z, "valid_to": "2026-03-01" + Z, "knowledge_time": "2026-04-01" + Z,
      "value": 105}
B = [0.980392156862745098, 0.951697752271640363, 0.914599323034920812]
LBL = "latency-aware analytics on simulated data"
F3, F25 = 0.002699796063260186, 0.012419330651552265
S3, T3 = 1.1547005383792515, 3.4641016151377546
ERR = lambda c: {"error_code": c}  # noqa: E731
G = {
    "bt_k-0001": {"status": "FOUND", "row": R1}, "bt_k-0002": {"status": "FOUND", "row": R3},
    "bt_k-0003": {"status": "FOUND", "row": R2}, "bt_k-0004": {"status": "WITHDRAWN", "row": None},
    "bt_k-0005": {"status": "FOUND", "row": R1}, "bt_k-0006": {"status": "NONE", "row": None},
    "bt_k-0007": {"status": "FOUND", "row": R2}, "bt_k-0008": {"status": "FOUND", "row": R3},
    "bt_k-0009": ERR("E_INPUT"), "bt_k-0010": ERR("E_INPUT"),
    "inc_k-0001": {"discount_factors": B},
    "inc_k-0002": {"discount_factors": [B[0], 0.949814623705232580, 0.914654171439767640], "first_changed_index": 1,
                   "recomputed": 2},
    "inc_k-0003": {"discount_factors": [B[0], B[1], 0.911838227756386082], "first_changed_index": 2, "recomputed": 1},
    "inc_k-0004": {"discount_factors": B, "first_changed_index": None, "recomputed": 0},
    "inc_k-0005": ERR("E_INPUT"), "inc_k-0006": ERR("E_INPUT"),
    "trig_k-0001": {"sigma": S3, "threshold": T3, "fire": True, "false_alarm_rate": F3},
    "trig_k-0002": {"sigma": S3, "threshold": T3, "fire": False, "false_alarm_rate": F3},
    "trig_k-0003": {"sigma": S3, "threshold": 6.928203230275509, "fire": False, "false_alarm_rate": F3},
    "trig_k-0004": {"sigma": 1.0, "threshold": 2.5, "fire": False, "false_alarm_rate": F25},
    "trig_k-0005": {"sigma": 1.0, "threshold": 2.5, "fire": True, "false_alarm_rate": F25},
    "trig_k-0006": ERR("E_INPUT"), "trig_k-0007": ERR("E_DOMAIN"), "trig_k-0008": ERR("E_DOMAIN"),
    "idr_k-0001": {"estimate_pnl": -39913.124212551616, "bound": 17.056891, "label": LBL},
    "idr_k-0002": {"estimate_pnl": 41959.951095246570, "bound": 17.931416, "label": LBL},
    "idr_k-0003": {"estimate_pnl": -10170.171073390556, "bound": 0.266514, "label": LBL},
    "idr_k-0004": {"estimate_pnl": -179097.352235808532, "bound": 2132.111336, "label": LBL},
    "idr_k-0006": ERR("E_DOMAIN"), "idr_k-0007": ERR("E_INPUT"),
    "rich_k-0001": {"status": "OK", "observed_order": 2, "extrapolated": 10.0},
    "rich_k-0002": {"status": "ORDER_MISMATCH", "observed_order": 1, "extrapolated": None},
    "rich_k-0003": {"status": "OK", "observed_order": 1, "extrapolated": 10.0},
    "rich_k-0004": {"status": "NON_MONOTONE", "observed_order": None, "extrapolated": None},
    "rich_k-0005": {"status": "ORDER_MISMATCH", "observed_order": 1.0008982225303467, "extrapolated": None},
    "rich_k-0006": {"status": "OK", "observed_order": 1.0008982225303467, "extrapolated": 230529},
    "rich_k-0007": ERR("E_DOMAIN"), "rich_k-0008": ERR("E_INPUT"),
}
GAP = {("idr_k-0006", "/error_code"), ("rich_k-0007", "/error_code"), ("trig_k-0004", "/fire"),
       ("bt_k-0004", "/row"), ("bt_k-0006", "/row")}


def flat(o, pre=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from flat(v, f"{pre}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from flat(v, f"{pre}[{i}]")
    else:
        yield pre, o


def tol(cid, path):
    item = cid.split("_")[0]
    if item == "inc":
        return ("abs", 1e-15)
    if item == "trig":
        return ("rel", 1e-14)
    if item == "idr":
        return ("abs", 5e-7) if path == "/bound" else ("rel", 1e-9)
    if item == "rich":
        return ("rel", 1e-12)
    return ("exact", 0)


def agree(a, b, t):
    if a is None or b is None or isinstance(a, (str, bool)) or isinstance(b, (str, bool)):
        return a == b and type(a) is type(b) if isinstance(a, bool) or isinstance(b, bool) else a == b
    kind, x = t
    if kind == "exact":
        return a == b
    if kind == "abs":
        return abs(a - b) <= x
    return abs(a - b) <= x * max(abs(a), abs(b))


def main():
    d = Path(sys.argv[1])
    raw = (d / "blind_results.json").read_bytes()
    sha_ok = hashlib.sha256(raw).hexdigest() == SHA
    blind = json.loads(raw)
    bad, counts = 0, {}
    print(f"# blind file SHA-256 {'OK' if sha_ok else 'DIFFERS'}")
    print("case\tresult\tblind_fields\tgap_fields\tprovisional\tdetail")
    for cid, exp in G.items():
        b = blind.get(cid)
        if b is None:
            res, det, nb, ng = "SHAPE MISMATCH", "missing", 0, 0
        else:
            if "error_code" in exp:
                b = {"error_code": b.get("error_code")} if b.get("status") == "error" else b
            # a null row is one leaf; a dict row is five
            ge, bl = dict(flat(exp)), dict(flat(b))
            ge = {("/row" if k.startswith("/row") and exp.get("row") is None else k): v for k, v in ge.items()}
            shape = sorted(set(ge) ^ set(bl))
            vals = [p for p in ge if p in bl and not agree(ge[p], bl[p], tol(cid, p))]
            res = "SHAPE MISMATCH" if shape else ("VALUE MISMATCH" if vals else "MATCH")
            det = ";".join(shape + [f"{p} golden={ge[p]!r} blind={bl[p]!r}" for p in vals])
            ng = sum((cid, p) in GAP for p in ge)
            nb = len(ge) - ng
        prov = "yes" if cid.startswith("idr_k") and "error_code" not in exp else ""
        bad += res != "MATCH"
        counts.setdefault(cid.split("-")[0], []).append(res)
        print(f"{cid}\t{res}\t{nb}\t{ng}\t{prov}\t{det}")
    for k, v in counts.items():
        print(f"# {k}: {v.count('MATCH')}/{len(v)} MATCH")
    print(f"# cases {len(G)}, not MATCH {bad}")
    return 1 if bad or not sha_ok else 0


if __name__ == "__main__":
    sys.exit(main())
