"""Wave-2 execution packet helper (H-14, H-17).

Usage: python -I wave2_exec_blind.py <checkout> <packet dir>

Writes <packet>/<suite>.inputs.json (cases without "expected") and
<packet>/coordinator/LEAKS.tsv: one row per case and expected value, with
whether that value's text occurs anywhere in the blind files. The coordinator
directory is not part of the blind packet and is not in MANIFEST.sha256.
Exit status 1 if any distinctive expected value (4 or more characters, not
also an input value of that case) occurs as a number in that case's blind
table row or its inputs-only JSON entry.
"""
import json
import os
import re
import sys

SUITES = ["alg_h", "tcx_h"]


def flat(v):
    if isinstance(v, dict):
        for x in v.values():
            yield from flat(x)
    elif isinstance(v, list):
        for x in v:
            yield from flat(x)
    elif v is not None and not isinstance(v, str):
        yield repr(v)


def main(root, pkt):
    os.makedirs(os.path.join(pkt, "coordinator"), exist_ok=True)
    rows, blind_cases = [], {}
    for s in SUITES:
        with open(os.path.join(root, "datasets/golden/stage_h", s + ".json"), encoding="utf-8") as fh:
            d = json.load(fh)
        blind = dict(d)
        blind["cases"] = [{k: v for k, v in c.items() if k != "expected"} for c in d["cases"]]
        with open(os.path.join(pkt, s + ".inputs.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(blind, fh, indent=1)
            fh.write("\n")
        for c in blind["cases"]:
            blind_cases[c["case_id"]] = c
        for c in d["cases"]:
            exp = c["expected"]
            if exp["status"] == "error":
                rows.append((c["case_id"], "error_code", exp["error_code"], "n/a"))
                continue
            inputs = set(flat(c["inputs"]))
            for k, v in exp.items():
                if k == "status":
                    continue
                rows.append((c["case_id"], k, json.dumps(v), "|".join(sorted(inputs))))
    texts = ""
    for f in sorted(os.listdir(pkt)):
        p = os.path.join(pkt, f)
        if os.path.isfile(p) and f != "MANIFEST.sha256":
            with open(p, encoding="utf-8") as fh:
                texts += fh.read()
    out = []
    for cid, k, v, flag in rows:
        if flag == "n/a":
            out.append((cid, k, v, "n/a"))
            continue
        hits = []
        for tok in flat(json.loads(v)):
            t = tok[:-2] if tok.endswith(".0") else tok
            scope = "\n".join(l for l in texts.splitlines() if l.startswith("| " + cid + " |"))
            scope += json.dumps(blind_cases.get(cid, {}))
            if len(t) >= 4 and tok not in flag.split("|") and re.search(r"(?<![\d.])" + re.escape(t) + r"(?![\d])", scope):
                hits.append(t)
        out.append((cid, k, v, "LEAK " + ",".join(hits) if hits else "clean"))
    with open(os.path.join(pkt, "coordinator", "LEAKS.tsv"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("case_id\tfield\texpected\tstatus_in_blind_files\n")
        for r in out:
            fh.write("\t".join(r) + "\n")
    return out


if __name__ == "__main__":
    res = main(sys.argv[1], sys.argv[2])
    leaks = [r for r in res if r[3].startswith("LEAK")]
    for r in leaks:
        print("\t".join(r))
    sys.exit(1 if leaks else 0)
