"""Stage H wave 2 comparison (DR-H2): spec-lane expected vs frozen blind results.

Usage: python -I wave2_compare.py <quantforge checkout> <blind_results.json> [micro]

Expected values are read from the "Golden value cases" tables (Case | Input |
Expected) of order-book.md and lit-matching.md. blind_results.json maps case id
to the blind lane's output object. Each pair is compared byte for byte after
canonical JSON (sorted keys, no spaces, HR-29); numbers that the spec gives as
decimal strings must be strings on both sides (HR-12), so no float coercion is
done. On a mismatch the book is compared level by level (MBP levels and, for
lit cases, MBO orders) and the other top-level keys are listed. Wave 2b adds
dark-pool.md, smart-order-router.md and the prose Expected column of
paper-trading.md (pt_h). A case that differs byte for byte but agrees after
decimal normalisation or a field-name mapping is SHAPE-ONLY. Prints one line per
case: MATCH, SHAPE-ONLY, VALUE MISMATCH or MISSING. Exit code 1 if any is not MATCH.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

SPECS = ["specifications/09-microstructure/order-book.md", "specifications/10-execution/lit-matching.md",
         "specifications/10-execution/dark-pool.md", "specifications/10-execution/smart-order-router.md"]
PREFIXES = ("ob_h-", "lit_h-", "dark_h-", "sor_h-")
PT_SPEC = "specifications/10-execution/paper-trading.md"


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def expected(root):
    out = {}
    for rel in SPECS:
        intable = False
        for line in (Path(root) / rel).read_text(encoding="utf-8").splitlines():
            if line.startswith("| Case | Input | Expected |"):
                intable = True
                continue
            if intable and line.startswith("|"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if cells[0].startswith(PREFIXES):
                    out[cells[0]] = json.loads(cells[2])
            elif intable:
                intable = False
    return out


# --- wave 2b: paper-trading prose expectations and shape-only comparison ---
# pt_h Expected cells are prose ("cash 9909.69, n 1, ..."). They are parsed into
# name -> value pairs; names are mapped onto the blind lane's field names by the
# table below (names and shape only, never values).
PT_ALIAS = {"cash": ("cash", "cash_close"), "n": ("position",), "c": ("avg_cost",), "realised": ("realised",),
            "fees": ("fees",), "market": ("market",), "trading": ("trading",), "financing": ("financing",),
            "total": ("total",), "NAV": ("nav_close",), "interest": ("cash_interest",), "borrow": ("short_borrow",),
            "first_bad_seq": ("verify.first_bad_seq",), "reason": ("verify.reason",), "ok": ("verify.ok",),
            "hash": ("hash",), "canonical bytes": ("canonical_bytes",)}


def pt_expected(root):
    out = {}
    for line in (Path(root) / PT_SPEC).read_text(encoding="utf-8").splitlines():
        if not line.startswith("| pt_h-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        cid, exp = cells[0], cells[2]
        d = {}
        if exp.startswith("canonical bytes"):
            m = re.match(r"canonical bytes `(.*)`; hash `([0-9a-f]+)`", exp)
            d = {"canonical bytes": m.group(1), "hash": m.group(2)}
        elif exp.startswith("`E_"):
            d = {"error": exp.strip("`")}
        elif exp.startswith("["):
            d = {"accepted": False, "reasons": [x.strip() for x in exp.strip("[]").split(",")]}
        elif exp.startswith("accepted"):
            d = {"accepted": True, "reasons": []}
        else:
            for part in re.split(r"[,;]\s*", exp.replace("verify: ", "")):
                k, v = part.strip().rsplit(" ", 1)
                d[k] = {"false": False, "true": True}.get(v, v)
        out[cid] = d
    return out


def getpath(o, path):
    for p in path.split("."):
        if not isinstance(o, dict) or p not in o:
            return None
        o = o[p]
    return o


def same_value(x, y):
    """Value equality allowing decimal-string normalisation and int/str of integers."""
    if isinstance(x, (str, int)) and isinstance(y, (str, int)) and not isinstance(x, bool) and not isinstance(y, bool):
        try:
            return Decimal(str(x)) == Decimal(str(y))
        except InvalidOperation:
            return str(x) == str(y)
    if isinstance(x, list) and isinstance(y, list):
        return len(x) == len(y) and all(same_value(a, b) for a, b in zip(x, y))
    if isinstance(x, dict) and isinstance(y, dict):
        return set(x) == set(y) and all(same_value(x[k], y[k]) for k in x)
    return x == y


def strip_labels(o):
    """Shape mapping only: drop per-item `label` keys (dark_h-0007, where the label's place was not stated)."""
    if isinstance(o, dict):
        return {k: strip_labels(v) for k, v in o.items() if k != "label"}
    if isinstance(o, list):
        return [strip_labels(v) for v in o]
    return o


def pt_compare(e, b):
    """Return (status, notes). Every spec-stated quantity must be present in the blind object."""
    notes = []
    for k, v in e.items():
        cands = PT_ALIAS.get(k, (k,))
        got = [getpath(b, c) for c in cands]
        got = [g for g in got if g is not None]
        if not got:
            notes.append(f"  {k}: spec={v} blind=ABSENT")
        elif not same_value(v, got[0]):
            notes.append(f"  {k}: spec={v} blind={got[0]}")
    return ("VALUE MISMATCH" if notes else "SHAPE-ONLY"), notes


def level_diff(e, b, side_key):
    rows = []
    ev, bv = e.get(side_key, []), b.get(side_key, [])
    for k in range(max(len(ev), len(bv))):
        x = ev[k] if k < len(ev) else None
        y = bv[k] if k < len(bv) else None
        if canon(x) != canon(y):
            rows.append(f"    {side_key}[{k}]: spec={canon(x)} blind={canon(y)}")
    return rows


# --- exec packet (H-14, H-17): expected from datasets/golden/stage_h/{alg_h,tcx_h}.json ---
# Usage: wave2_compare.py <checkout> <blind_results.json> exec
# MATCH: same field names and every number within simple_analytic
# (1e-12 abs + 1e-10 rel). SHAPE-ONLY: values agree once the error shape
# {"status","error_code"} -> {"error"} and blind-only echo fields are allowed.
def _close(a, b):
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_close(a[k], b[k]) for k in a)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) <= 1e-12 + 1e-10 * max(abs(a), abs(b))
    return a == b


def exec_main(root, blind_path):
    blind = json.loads(Path(blind_path).read_text(encoding="utf-8"))
    bad = n = 0
    for suite in ("alg_h", "tcx_h"):
        cases = json.loads((Path(root) / "datasets/golden/stage_h" / (suite + ".json")).read_text(encoding="utf-8"))["cases"]
        for c in cases:
            n += 1
            cid, e = c["case_id"], dict(c["expected"])
            b = blind.get(cid)
            if b is None:
                print(f"{cid}	MISSING"); bad += 1; continue
            st = e.pop("status")
            if st == "error" and "error_code" in e:
                e = {"error": e["error_code"]}
            elif st == "ok" and "outputs" in e:  # goldens moved to {status, outputs} after the compare
                e = dict(e["outputs"])
            if _close(e, b):
                print(f"{cid}	MATCH" if c["expected"].get("status") != "error" or "error" in c["expected"] else f"{cid}	SHAPE-ONLY (error shape)")
                continue
            if set(b) > set(e) and _close(e, {k: b[k] for k in e}):
                print(f"{cid}	SHAPE-ONLY (blind adds {sorted(set(b) - set(e))})"); continue
            bad += 1
            print(f"{cid}	VALUE MISMATCH")
            for k in sorted(set(e) | set(b)):
                if not _close(e.get(k), b.get(k)):
                    print(f"  {k}: spec={canon(e.get(k))} blind={canon(b.get(k))}")
    print(f"{n - bad}/{n} MATCH or SHAPE-ONLY")
    sys.exit(1 if bad else 0)


def main():
    root, blind_path = sys.argv[1], sys.argv[2]
    if len(sys.argv) > 3 and sys.argv[3] == "exec":
        exec_main(root, blind_path)
    exp = expected(root)
    blind = json.loads(Path(blind_path).read_text(encoding="utf-8"))
    bad = 0
    for cid in sorted(exp):
        if cid not in blind:
            print(f"{cid}\tMISSING")
            bad += 1
            continue
        e, b = exp[cid], blind[cid]
        if canon(e) == canon(b):
            print(f"{cid}\tMATCH")
            continue
        if same_value(e, b):
            print(f"{cid}\tSHAPE-ONLY (decimal normalisation; same values)")
            continue
        if same_value(strip_labels(e), strip_labels(b)):
            print(f"{cid}\tSHAPE-ONLY (label placement only; same values)")
            continue
        bad += 1
        print(f"{cid}\tVALUE MISMATCH")
        for key in sorted(set(e) | set(b)):
            if canon(e.get(key)) != canon(b.get(key)) and key not in ("book", "mbp"):
                print(f"  {key}: spec={canon(e.get(key))} blind={canon(b.get(key))}")
        for bk in ("book", "mbp"):
            eb, bb = e.get(bk) or {}, b.get(bk) or {}
            for side in ("bids", "asks"):
                for r in level_diff(eb, bb, side):
                    print(f"  {bk}:" + r.strip())
    pte = pt_expected(root)
    for cid in sorted(pte):
        if cid not in blind:
            print(f"{cid}	MISSING")
            bad += 1
            continue
        st, notes = pt_compare(pte[cid], blind[cid])
        bad += st != "SHAPE-ONLY"
        print(f"{cid}	{st} (prose expected; spec-stated fields only)")
        for n in notes:
            print(n)
    exp = {**exp, **pte}
    extra = sorted(set(blind) - set(exp))
    if extra:
        print("blind-only cases (ignored): " + ", ".join(extra))
    print(f"{len(exp) - bad}/{len(exp)} MATCH or SHAPE-ONLY")
    sys.exit(1 if bad else 0)


# --- micro packet (H-4b mest_h, H-16 venue_h): prose expected, binary64 tolerance ---
MICRO_SPECS = ["specifications/09-microstructure/micro-estimators.md", "specifications/10-execution/venue-analytics.md"]
NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:e-?\d+)?(?![\w])")


def micro_expected(root):
    out = {}
    for rel in MICRO_SPECS:
        for line in (Path(root) / rel).read_text(encoding="utf-8").splitlines():
            if line.startswith(("| mest_h-", "| venue_h-")):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                out[cells[0]] = cells[2]
    return out


def flat(o, pre=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from flat(v, f"{pre}{k}.")
    else:
        yield pre.rstrip("."), o


def close(a, b):
    return abs(a - b) <= 1e-15 if a == 0 or b == 0 else abs(a - b) <= 1e-12 * max(abs(a), abs(b))


def micro_compare(exp, b):
    """MATCH: same error code, or the spec's numbers and the blind numbers agree as
    sorted multisets to 1e-12 relative (1e-15 absolute at 0) and every blind leaf
    name is named in the Expected cell. Same numbers under other names: SHAPE-ONLY."""
    if exp.startswith("`E_"):
        return ("MATCH" if exp.strip("`") == b else "VALUE MISMATCH"), []
    if isinstance(b, str):
        return "VALUE MISMATCH", [f"  spec={exp} blind={b}"]
    leaves = list(flat(b))
    text = re.sub(r"[AB]:", "", exp.replace(",", ""))
    en = sorted(float(x) for x in NUM.findall(text))
    bn = sorted(float(v) for _, v in leaves)
    if len(en) != len(bn) or not all(close(x, y) for x, y in zip(en, bn)):
        return "VALUE MISMATCH", [f"  spec numbers={en}", f"  blind numbers={bn}"]
    names = {k.split(".")[-1].split("|")[0] for k, _ in leaves}
    missing = [n for n in names if n not in exp]
    return ("SHAPE-ONLY", [f"  blind names not in spec: {missing}"]) if missing else ("MATCH", [])


def micro_main(root, blind_path):
    exp = micro_expected(root)
    blind = json.loads(Path(blind_path).read_text(encoding="utf-8"))
    bad = 0
    for cid in sorted(exp):
        if cid not in blind:
            print(f"{cid}	MISSING (not in blind packet or added post-blind)")
            continue
        st, notes = micro_compare(exp[cid], blind[cid])
        bad += st == "VALUE MISMATCH"
        print(f"{cid}	{st}")
        for n in notes:
            print(n)
    print(f"{len(exp) - bad}/{len(exp)} not VALUE MISMATCH")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    if len(sys.argv) > 3 and sys.argv[3] == "micro":
        micro_main(sys.argv[1], sys.argv[2])
    main()
