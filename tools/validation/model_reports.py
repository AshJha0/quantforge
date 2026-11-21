#!/usr/bin/env python3
"""Write one validation report per model of docs/model-inventory.md (plan 14.8 K-7, check RE5, ruling KR-224).

    python tools/validation/model_reports.py              write docs/validation/models/<id>.md and its README.md
    python tools/validation/model_reports.py --check      exit 1 if a page is missing, stale or not a model's
    python tools/validation/model_reports.py --self-test  planted faults must fail

Plain idea: the inventory says what each model is for and where its evidence lives, but the evidence itself is
spread over goldens, outside registers, unit tests and mutation settings. A report puts it on one page per model,
with every number counted from the repository when the page is built, so a page cannot drift from the tree.

What is read and from where (standard library only):
- purpose, inputs, limitations, the inventory's own validation text, challenger, review date: the model's entry in
  docs/model-inventory.md (quoted, evidence class read);
- spec files: the inventory index row's Spec cell, else the entry's "Validation report" line, else the first
  specifications/ path in the entry;
- operations: names in backticks on the entry's Purpose line that are in specifications/name-map.json (a name
  starting with "." continues the previous one's prefix); else the stage G and I lists of tools/inventory_counts.py;
  else every operation whose name-map spec is one of the model's specs; else the operations of the golden suites
  named on the Validation line;
- golden cases by class (`ok` value-checked, `error`, `same_as` and `any` invariance) per operation: every file
  under datasets/golden, as tools/case_figures.py counts them;
- outside-checked value cases: oracle/OUTSIDE_SHARES.json `per_operation`, counted with re-derivation where the
  rule allows it (tools/outside_shares.py); operations of stages A to C are not in that table and are listed so;
- unit-test files: test files in each language's test tree that contain the operation name or the language's
  function name from name-map.json (a string match: a count of files that name the function, not of assertions);
- mutation: modules of conformance/mutation/stages.json whose suite pattern matches one of the model's suites.
- status rung: Implemented when the model's operations have golden cases, else Specified (docs/validation/
  status-ladder.md); no model is Validated, Benchmarked or Operationally tested.
"""
import argparse
import fnmatch
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
INVENTORY = ROOT / "docs" / "model-inventory.md"
OUT = ROOT / "docs" / "validation" / "models"
MARK = "<!-- Hand-filled below this line: the generator keeps it. -->"
ID = r"(M\d+|ME-A\d+|EB\d+|MF-\d+|MG-\d+|MI-\d+|MJ-\d+|MH-\d+|MK-\d+)"
HEAD = re.compile(r"^### " + ID + r" (.+)$", re.M)
LANG_TESTS = {"python": ("python/tests", ("*.py",)), "java": ("java25/src/test", ("*.java",)),
              "cpp": ("cpp26/tests", ("*.cpp", "*.hpp", "*.h")), "rust": ("rust", ("*.rs",))}
# Operations an entry covers that the rules above miss, read from the entry's Purpose text (the name map files
# rates.ois.bootstrap under the curve framework spec, while M2's Purpose is "curves from par OIS quotes").
EXTRA_OPS = {"M2": ["rates.ois.bootstrap"]}
CLASSES = (("ok", "value-checked"), ("error", "error"), ("same_as", "invariance"), ("any", "invariance base"))


def slug(mid):
    return mid.lower()


def resolve_spec(token):
    token = token.strip().strip("`").split("#")[0]
    if not token.endswith(".md"):
        return None
    for cand in (ROOT / token, ROOT / "specifications" / token):
        if cand.is_file():
            return cand.relative_to(ROOT).as_posix()
    hits = [p for p in (ROOT / "specifications").rglob(Path(token).name)]
    return hits[0].relative_to(ROOT).as_posix() if len(hits) == 1 else None


def parse_inventory(text):
    index = {}
    for line in text.splitlines():
        m = re.match(r"^\| " + ID + r" \| (.*)$", line)
        if m:
            cells = [c.strip() for c in m.group(2).rstrip("|").split(" | ")]
            index[m.group(1)] = cells  # model, spec, stage, status, outside
    heads = list(HEAD.finditer(text))
    entries = []
    for i, h in enumerate(heads):
        end = len(text)
        nxt = re.compile(r"^#{2,3} ", re.M).search(text, h.end())
        if nxt:
            end = nxt.start()
        body = text[h.end():end]
        fields = {}
        for fm in re.finditer(r"^- \*\*([^*]+):\*\* (.*)$", body, re.M):
            fields[fm.group(1).strip()] = fm.group(2).strip()
        # "**Review:** date" sits inside the Validation line
        val = fields.get("Validation", "")
        rv = re.search(r"\*\*Review:\*\* (.*)$", val)
        if rv:
            fields["Review"] = rv.group(1).strip()
            fields["Validation"] = val[:rv.start()].strip()
        entries.append({"id": h.group(1), "title": h.group(2).strip(), "fields": fields, "body": body,
                        "index": index.get(h.group(1))})
    return entries


def specs_of(e):
    out = []
    if e["index"] and len(e["index"]) > 1:
        cell = e["index"][1]
        toks = re.findall(r"`([^`]+\.md)`", cell)
        base = None
        for t in toks:
            r = resolve_spec(t if "/" in t or base is None else f"{base}/{t}")
            if r:
                out.append(r)
                base = str(Path(r).parent.relative_to("specifications").as_posix()) if r.startswith("specifications/") else base
    if not out:
        vr = e["fields"].get("Validation report", "")
        out += [r for r in (resolve_spec(t) for t in re.findall(r"`([^`]+\.md)`", vr)) if r and r.startswith("specifications/")]
    if not out:
        m = re.search(r"`(specifications/[^`]+\.md)`", e["body"])
        if m and resolve_spec(m.group(1)):
            out.append(resolve_spec(m.group(1)))
    return list(dict.fromkeys(out))


def load_goldens():
    cases = defaultdict(list)  # op -> [(suite, case)]
    suite_ops = defaultdict(set)
    for p in sorted((ROOT / "datasets" / "golden").rglob("*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        for c in doc.get("cases", []):
            op = c.get("operation")
            if op:
                cases[op].append((p.stem, p.relative_to(ROOT).as_posix(), c))
                suite_ops[p.stem].add(op)
    return cases, suite_ops


def load_tests():
    files = {}
    for lang, (base, pats) in LANG_TESTS.items():
        root = ROOT / base
        found = []
        for pat in pats:
            for p in root.rglob(pat):
                rel = p.relative_to(ROOT).as_posix()
                if lang == "rust" and "/tests/" not in rel:
                    continue
                if "/target/" in rel or "/build/" in rel:
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
                found.append((rel, set(re.findall(r"\w+", text)) | set(re.findall(r"\w+(?:\.\w+)+", text))))
        files[lang] = found
    return files


def ops_of(e, names, spec_ops, suite_ops, entries_gi):
    purpose = e["fields"].get("Purpose", "")
    ops, prev = [], None
    for t in re.findall(r"`([a-z.][a-z0-9_.]*)`", purpose):
        full = t
        if t.startswith(".") and prev:
            full = prev.rsplit(".", 1)[0] + t
        if full in names:
            ops.append(full)
            prev = full
    if ops:
        return list(dict.fromkeys(ops)), "named on the inventory entry's Purpose line"
    if e["id"] in entries_gi:
        return list(entries_gi[e["id"]][1]), "listed for this entry in tools/inventory_counts.py"
    specs = specs_of(e)
    ops = sorted({op for s in specs for op in spec_ops.get(s, ())})
    ops = sorted(set(ops) | set(EXTRA_OPS.get(e["id"], [])))
    if ops:
        return ops, "every operation whose name-map spec is the model's spec (shared specs give shared counts)"
    suites = re.findall(r"`([a-z0-9_]+_[a-z0-9]+)`", e["fields"].get("Validation", ""))
    ops = sorted({op for s in suites for op in suite_ops.get(s, ())})
    if ops:
        return ops, "operations of the golden suites named on the inventory entry's Validation line"
    return [], "none found"


def symbols(op, names):
    v = names[op]
    out = {}
    for lang in LANG_TESTS:
        s = v.get(lang) or ""
        out[lang] = re.split(r"::|\.", s)[-1] if s else ""
    return out


def share_rows(ops, shares):
    per = {}
    for st, s in shares["stages"].items():
        for op, v in (s.get("per_operation") or {}).items():
            # A later stage with no value case of the operation (an error-only suite such as fuzzfix_j or
            # fuzzfix_k) does not hide the stage that holds its value cases.
            if v["cases"] or op not in per:
                per[op] = (st, v)
    return per


def worked_example(ops, cases):
    cands = [(len(json.dumps(c, sort_keys=True)), suite, path, c) for op in ops for suite, path, c in cases.get(op, [])
             if c.get("expected", {}).get("status") == "ok"]
    if not cands:
        cands = [(len(json.dumps(c, sort_keys=True)), suite, path, c) for op in ops for suite, path, c in cases.get(op, [])]
    if not cands:
        return None
    cands.sort(key=lambda t: (t[0], t[3]["case_id"]))
    _, suite, path, c = cands[0]
    return suite, path, c


def md_cell(s):
    return s.replace("|", "\\|")


def render(e, ctx):
    names, cases, tests, per_op, mut, spec_ops, suite_ops, gi = ctx
    f = e["fields"]
    specs = specs_of(e)
    ops, how = ops_of(e, names, spec_ops, suite_ops, gi)
    status_text = e["index"][3] if e["index"] and len(e["index"]) > 3 else None
    total = Counter()
    suites = set()
    for op in ops:
        for suite, _, c in cases.get(op, []):
            total[c["expected"].get("status")] += 1
            suites.add(suite)
    value_suites = {s for op in ops for s, _, c in cases.get(op, []) if c["expected"].get("status") == "ok"}
    if sum(total.values()):
        rung = "Implemented"
    elif "PROPOSED" not in e["title"] and re.search(r"unit tests in", f.get("Validation", "")):
        rung = "Implemented (unit tests only; no golden suite)"
    else:
        rung = "Specified"
    up = "../../../"
    lines = [f"# Validation report: {e['id']} {e['title']}", "",
             "Generated by `tools/validation/model_reports.py` from `docs/model-inventory.md`, the goldens, "
             "`oracle/OUTSIDE_SHARES.json`, the test trees and `conformance/mutation/stages.json`; do not edit above the "
             "hand-filled line. Index: [all model reports](README.md). Validation is self-assessment; there is no second "
             "review (owner decision 2026-11-18).", "",
             "| | |", "|---|---|",
             f"| Status rung | **{rung}** ([status ladder](../status-ladder.md)); not Validated: no test on real data against an "
             "independent benchmark with a written report |"]
    if status_text:
        lines.append(f"| Inventory status | {md_cell(status_text)} (read) |")
    lines += [f"| Spec | {', '.join(f'[`{s}`]({up}{s})' for s in specs) or 'none named'} |",
              f"| Inventory entry | [`{e['id']}`]({up}docs/model-inventory.md) |",
              f"| Last review in the inventory | {md_cell(f.get('Review', 'not stated'))} |", "",
              "## Plain idea", "", f.get("Purpose", "Not stated in the inventory entry.") + " (Read from the inventory entry.)", "",
              "## Formal statement", "",
              "The model is defined by its spec" + (f" ({', '.join(f'`{s}`' for s in specs)})" if specs else "") +
              ". This report claims only what the files below show: each listed golden case states inputs, an expected "
              "status and, for value-checked cases, expected outputs within the case's tolerance class "
              "(`conformance/tolerances/policy.yaml`), and the neutral runner sends every case to all four builds. "
              "Whether the four builds pass them at a given commit is recorded by the conformance workflow, not here.", "",
              f"Inputs (read from the inventory entry): {f.get('Inputs', 'not stated')}", ""]
    ex = worked_example(ops, cases)
    lines += ["## Worked example", ""]
    if ex:
        suite, path, c = ex
        exp = c.get("expected", {})
        lines += [f"The shortest {'value-checked ' if exp.get('status') == 'ok' else ''}golden case of this model, "
                  f"`{c['case_id']}` in [`{path}`]({up}{path}) (tolerance class `{c.get('tolerance_class', 'not stated')}`; "
                  f"verified by: {md_cell('; '.join(c.get('verified_by', [])) or 'not stated')}). Send the request to any build's CLI "
                  "with `quantforge run`; the expected answer follows.", "",
                  "Request:", "", "```json",
                  json.dumps({"schema_version": "1.0", "case_id": c["case_id"], "operation": c["operation"],
                              "inputs": c.get("inputs", {})}, sort_keys=True), "```", "", "Expected:", "", "```json",
                  json.dumps(exp, sort_keys=True), "```", ""]
    else:
        lines += ["No golden case exists for this model's operations, so there is no worked example from the tree. "
                  "The spec's own examples are the only ones.", ""]
    lines += ["## Evidence counted from the tree", "",
              f"Operations ({len(ops)}; {how}): " + (", ".join(f"`{o}`" for o in ops) or "none") + ".", "",
              "| Operation | Value-checked | Error | Invariance | Invariance base | Suites | Outside-checked value cases | Unit-test files (Python, Java, C++, Rust) |",
              "|---|---:|---:|---:|---:|---|---|---|"]
    out_n = out_d = 0
    not_in_table = []
    test_tot = Counter()
    for op in ops:
        cnt = Counter(c["expected"].get("status") for _, _, c in cases.get(op, []))
        ss = sorted({s for s, _, _ in cases.get(op, [])})
        if op in per_op:
            st, v = per_op[op]
            out_n += v["counted_with_rederivation"]
            out_d += v["cases"]
            oc = f"{v['counted_with_rederivation']} of {v['cases']} (stage {st})"
        else:
            not_in_table.append(op)
            oc = "not in the share table"
        sy = symbols(op, names)
        tc = []
        for lang in ("python", "java", "cpp", "rust"):
            keys = {op} | ({sy[lang]} if len(sy[lang]) > 3 else set())
            n = sum(1 for _, toks in tests[lang] if keys & toks)
            test_tot[lang] += n
            tc.append(str(n))
        lines.append(f"| `{op}` | {cnt['ok']} | {cnt['error']} | {cnt['same_as']} | {cnt['any']} | "
                     f"{', '.join(f'`{s}`' for s in ss) or 'none'} | {oc} | {', '.join(tc)} |")
    lines += ["", f"Totals: {total['ok']} value-checked, {total['error']} error, {total['same_as'] + total['any']} invariance "
              f"cases (measured from `datasets/golden` at generation)."]
    if out_d:
        lines.append(f"Outside-checked: {out_n} of {out_d} value cases ({100 * out_n / out_d:.1f}%) under rule R6-13 / D6, "
                     "counting blind re-derivation where the rule allows it (from `oracle/OUTSIDE_SHARES.json`, written by "
                     "`tools/outside_shares.py`). The plan's floor is 60% per stage and, from stage H on, per plan item; "
                     "it is not a per-model rule.")
    if not_in_table:
        lines.append(f"Not in the share table ({len(not_in_table)} operations): the table covers stages D to K; stage A to C "
                     "operations and operations with no value case are outside it, so no outside share is stated here for them.")
    # A pattern that names a whole stage ("*", "*_d") runs every suite of the stage and says nothing about this model.
    specific = lambda pat: pat != "*" and not re.fullmatch(r"\*_[a-z]+", pat)  # noqa: E731
    mods = sorted({f"{st}/{m['module']}" for st, ms in mut.items() for m in ms for pat in m.get("suite", "").split(",")
                   for s in value_suites if specific(pat) and fnmatch.fnmatch(s, pat)})
    lines += ["", "Mutation testing: " + (
        "modules " + ", ".join(f"`{m}`" for m in mods) + " of `conformance/mutation/stages.json` mutate code checked by "
        "this model's value-checked suites; the gate is 80% killed with a 95% Wilson lower bound of 65% per module and language, on a "
        "40-mutant sample (`.github/workflows/mutation-stage.yml`). Scores are those of the latest run, not stored in the tree."
        if mods else "no module of `conformance/mutation/stages.json` names one of this model's value-checked suites "
        "by a pattern narrower than the whole stage (patterns such as `*` or `*_d` run every suite of a stage), so no "
        "mutation result maps to this model alone."), "",
        "Unit-test counts are files that contain the operation name or the language's function name from "
        "`specifications/name-map.json` (string match; Rust counts only files under a `tests` folder, so in-module "
        "`#[cfg(test)]` tests are not counted).", "",
        "## What the inventory records (read)", ""]
    for k in ("Validation", "Challenger", "Monitoring thresholds", "Data lineage hash", "Tier", "Retirement trigger"):
        if k in f:
            lines.append(f"- **{k}:** {f[k]}")
    lines += ["", "## Limits", "", f.get("Limitations", "Not stated in the inventory entry.") + " (Read from the inventory entry.)", "",
              "Use restriction for every model (inventory): research, education and conformance testing only; not for trading, "
              "valuation of record, risk limits or regulatory capital.", "",
              "Limits of this report: the counts show what is checked, not that the checks are sufficient. Golden inputs are "
              "synthetic unless the case's `verified_by` says otherwise.", "", MARK, ""]
    return "\n".join(lines), {"id": e["id"], "title": e["title"], "rung": rung, "value": total["ok"],
                              "out": (out_n, out_d), "ops": len(ops)}


def readme(rows):
    lines = ["# Model validation reports", "",
             "Generated by `tools/validation/model_reports.py`; do not edit. One report per model entry of "
             "[`docs/model-inventory.md`](../../model-inventory.md) (plan 14.8 K-7; spec "
             "`specifications/12-platform/release-evidence.md`, check RE5, ruling KR-224, confirmed 2026-11-20). Each report counts its "
             "goldens, outside checks, unit-test files and mutation modules from the repository when it is built, and "
             "`repo-gates` fails if a report is stale or a model has none.", "",
             "No model is Validated in the ladder's sense (tested on real data against an independent benchmark, with a "
             "written report): these reports are evidence pages for the Implemented rung, and say so. Validation is "
             "self-assessment; there is no second review (owner decision 2026-11-18).", "",
             f"{len(rows)} models: {sum(r['rung'].startswith('Implemented') for r in rows)} Implemented, "
             f"{sum(r['rung'] == 'Specified' for r in rows)} Specified.", "",
             "| Model | Name | Rung | Operations | Value-checked cases | Outside-checked value cases |",
             "|---|---|---|---:|---:|---|"]
    for r in rows:
        n, d = r["out"]
        oc = f"{n} of {d} ({100 * n / d:.1f}%)" if d else "not in the share table"
        lines.append(f"| [{r['id']}]({slug(r['id'])}.md) | {md_cell(r['title'])} | {r['rung']} | {r['ops']} | {r['value']} | {oc} |")
    return "\n".join(lines) + "\n"


def build():
    import inventory_counts
    names = json.loads((ROOT / "specifications" / "name-map.json").read_text(encoding="utf-8"))["operations"]
    spec_ops = defaultdict(set)
    for op, v in names.items():
        if v.get("spec"):
            spec_ops[v["spec"]].add(op)
    cases, suite_ops = load_goldens()
    shares = json.loads((ROOT / "oracle" / "OUTSIDE_SHARES.json").read_text(encoding="utf-8"))
    mut = json.loads((ROOT / "conformance" / "mutation" / "stages.json").read_text(encoding="utf-8"))["stages"]
    ctx = (names, cases, load_tests(), share_rows(None, shares), mut, spec_ops, suite_ops, inventory_counts.ENTRIES)
    pages, rows = {}, []
    for e in parse_inventory(INVENTORY.read_text(encoding="utf-8")):
        text, row = render(e, ctx)
        pages[f"{slug(e['id'])}.md"] = text
        rows.append(row)
    pages["README.md"] = readme(rows)
    return pages


def generated(text):
    i = text.find(MARK)
    return text if i < 0 else text[:i + len(MARK)]


def stale(pages, on_disk):
    """Problems between freshly built pages and the files on disk ({name: text})."""
    out = []
    for name, text in pages.items():
        if name not in on_disk:
            out.append(f"{name}: missing (a model with no report)")
        elif generated(on_disk[name]) != generated(text):
            out.append(f"{name}: stale; run python tools/validation/model_reports.py")
    out += [f"{name}: not a model of the inventory" for name in on_disk if name not in pages]
    return out


def self_test():
    pages = {"m1.md": f"# a\ncount 5\n{MARK}\n", "README.md": "index\n"}
    good = dict(pages, **{"m1.md": pages["m1.md"] + "hand notes kept\n"})
    planted = {"a model with no report": {"README.md": "index\n"},
               "a stale count": {"m1.md": f"# a\ncount 4\n{MARK}\n", "README.md": "index\n"},
               "a report for no model": dict(pages, **{"m99.md": "x"})}
    bad = [k for k, v in planted.items() if not stale(pages, v)]
    if stale(pages, good) or bad:
        print(f"self-test FAILED: good={stale(pages, good)}, not caught: {bad}", file=sys.stderr)
        return 1
    print(f"self-test: a current set passes (hand notes kept) and {len(planted)} planted faults fail")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    pages = build()
    on_disk = {p.name: p.read_text(encoding="utf-8") for p in OUT.glob("*.md")} if OUT.is_dir() else {}
    if a.check:
        found = stale(pages, on_disk)
        for p in found:
            print(f"model reports: {p}", file=sys.stderr)
        if not found:
            print(f"model reports: {len(pages) - 1} reports and the index are current")
        return 1 if found else 0
    OUT.mkdir(parents=True, exist_ok=True)
    for name in on_disk:
        if name not in pages:
            (OUT / name).unlink()
    for name, text in pages.items():
        hand = ""
        if name in on_disk and MARK in on_disk[name]:
            hand = on_disk[name][on_disk[name].find(MARK) + len(MARK):]
        body = text if MARK not in text else generated(text) + (hand if hand else "\n")
        (OUT / name).write_text(body, encoding="utf-8", newline="\n")
    print(f"wrote {len(pages) - 1} model reports and the index to {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
