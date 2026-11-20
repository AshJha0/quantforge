#!/usr/bin/env python3
"""Golden case counts by class, from one place (R6-12). Standard library only.

The headline is the value-checked count. A golden case is in one class by its `expected.status`:

- `ok`: value-checked, the build must return the expected numbers within the stated tolerance;
- `error`: error cases, the build must return the stated error code;
- `same_as`: invariance cases, the build's answer must equal its own answer to a paired case;
- `any`: the paired base case of an invariance case; any finite answer passes, so it checks no value alone.

`python tools/case_figures.py` prints the table; `--write` rewrites docs/case-figures.md; `--check` fails if that
page differs from the tree. tools/site_figures.py reads `figures()` for the site home, so the site and the page
cannot disagree.

K-9 review findings 4, 5, 9 and 14 (2026-11-20) added three things, each written by `--write` and compared by
`--check`:

- the value-checked count without the stage A convention sweeps (`core/daycount`, `core/calendar`,
  `core/compounding`: generated grids of dates and conventions, about half of the headline);
- a per-stage table of evidence classes, read from each value-checked case's `verified_by` labels (`evidence()`);
  a case is put in the first class of EVIDENCE_ORDER that one of its labels matches, so each case counts once;
- the outside-checked share per stage, from oracle/OUTSIDE_SHARES.json through `outside_pair()`, the one
  definition that docs/results.md also uses; and generated blocks in README.md and datasets/golden/README.md
  between `<!-- case-figures:begin -->` and `<!-- case-figures:end -->` (`golden-counts` in the golden README).
"""
import re
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = Path("docs") / "case-figures.md"
HEADLINE_PAGES = ("README.md", "LEARN.md")
README_BEGIN, README_END = "<!-- case-figures:begin -->", "<!-- case-figures:end -->"
GOLDEN_README = Path("datasets") / "golden" / "README.md"
GOLDEN_BEGIN, GOLDEN_END = "<!-- golden-counts:begin -->", "<!-- golden-counts:end -->"
STAGE_A_SWEEPS = ("daycount", "calendar", "compounding")
DIR_STAGE = {"core": "A", "stage_b": "B", "stage_c": "C", "r2": "R2", "stage_d": "D", "stage_e": "E", "stage_e_b": "E",
             "stage_f": "F", "r6": "R6", "stage_g": "G", "stage_g_e1": "G", "stage_i": "I", "stage_j": "J",
             "stage_h": "H", "stage_k": "K"}
STAGE_ORDER = ["A", "B", "C", "D", "R2", "E", "F", "G", "I", "R6", "J", "H", "K"]
# Evidence classes, strongest first; a value-checked case goes in the first class one of its labels matches.
# "impl": the expected values are a build's own output (an exception to design principle 5; listed first so the
# exception is never hidden behind a later agreement). The other patterns read the free-text labels in use on
# 2026-11-20; a label that matches nothing falls in "own".
EVIDENCE_ORDER = (
    ("impl", "implementation-sourced (expected values are a build's own output)",
     r"build's own output|^python build; agreement check"),
    ("library", "outside library (QuantLib, Strata, ORE, NumPy, SciPy, HiGHS, Python zoneinfo or hashlib)",
     r"quantlib|strata|^ore-|numpy|scipy|highspy|zoneinfo|hashlib|sha256sum|library-object"),
    ("printed", "figure printed in a published source (regulator text, paper, standard test vector)",
     r"^published|printed|^\[A[CS]\d\d\]|^MAR\d|^Basel 1996|sha256-nist|cboe-vix-methodology|isda-2021-fixed|psa-standard|^textbook"),
    ("blind", "blind re-derivation by a second AI lane (DR-H2), matched",
     r"^blind[ -]re-?derivation(?!.*MISMATCH)(?!.*SHAPE-ONLY).*MATCH"),
    ("mpmath", "own high-precision oracle (mpmath, 25 to 50 digits)", r"mpmath"),
    ("own", "own independent oracle in float64 or exact arithmetic (exact rationals, closed forms, replays, parity, rules)", None),
    ("reference", "reference-computed (the spec's reference scheme, stored reference values)", r"^reference"),
    ("hand", "hand-derived only", r"^hand"),
)
CLASSES = (("ok", "value-checked"), ("error", "error"), ("same_as", "invariance (`same_as`)"), ("any", "base case of an invariance pair (`any`)"))


def counts(root=ROOT):
    """{suite directory: Counter(status)} over datasets/golden."""
    per = defaultdict(Counter)
    for p in sorted((root / "datasets" / "golden").rglob("*.json")):
        for case in json.loads(p.read_text(encoding="utf-8"))["cases"]:
            per[p.relative_to(root / "datasets" / "golden").parts[0]][case["expected"].get("status")] += 1
    return per


def figures(root=ROOT):
    """Formatted totals for pages: value_checked, error_cases, invariance_cases, any_cases, total_cases."""
    total = Counter()
    for c in counts(root).values():
        total.update(c)
    f = lambda n: f"{n:,}"  # noqa: E731
    return {"value_checked": f(total["ok"]), "error_cases": f(total["error"]), "invariance_cases": f(total["same_as"] + total["any"]), "invariance_pairs": f(total["same_as"]),
            "any_cases": f(total["any"]), "total_cases": f(sum(total.values())),
            "stage_a_sweeps": f(sweeps(root)), "value_checked_without_sweeps": f(total["ok"] - sweeps(root)),
            "outside_shares": shares_text(root)}


def case_class(labels):
    """The evidence class key of one value-checked case from its verified_by labels (see EVIDENCE_ORDER)."""
    labels = [str(x) for x in labels]
    hits = {key for key, _, rx in EVIDENCE_ORDER if rx and any(re.search(rx, x, re.I) for x in labels)}
    if not hits - {"reference", "hand"} and labels and not all(re.search(r"^reference|^hand", x, re.I) for x in labels):
        hits.add("own")
    for key, _, _ in EVIDENCE_ORDER:
        if key in hits:
            return key
    return "own"


def evidence(root=ROOT):
    """({stage: Counter(class)}, [case ids whose expected values are a build's output]) over value-checked cases."""
    per, impl = defaultdict(Counter), []
    for p in sorted((root / "datasets" / "golden").rglob("*.json")):
        st = DIR_STAGE.get(p.relative_to(root / "datasets" / "golden").parts[0], p.parent.name)
        for case in json.loads(p.read_text(encoding="utf-8"))["cases"]:
            if case["expected"].get("status") != "ok":
                continue
            k = case_class(case.get("verified_by", []))
            per[st][k] += 1
            if k == "impl":
                impl.append(case["case_id"])
    return per, impl


def outside_pair(entry):
    """(counted, cases, share) of one stage of oracle/OUTSIDE_SHARES.json: value-checked cases counted under rule D6
    (outside library, or blind re-derivation where the rule allows it), over the share table's value-checked cases
    without generated sweeps. The one definition used by every page."""
    w = entry["without_sweeps"]
    return w["counted_with_rederivation"], w["cases"], w["share_with_rederivation"]


def shares_text(root=ROOT):
    sh = json.loads((root / "oracle" / "OUTSIDE_SHARES.json").read_text(encoding="utf-8"))["stages"]
    return ", ".join(f"{st} {c} of {n} ({100 * s:.1f}%)" for st in STAGE_ORDER if st in sh for c, n, s in [outside_pair(sh[st])])


def sweeps(root=ROOT):
    """Value-checked cases in the stage A convention sweeps (core/daycount, core/calendar, core/compounding)."""
    return sum(1 for n in STAGE_A_SWEEPS
               for k in json.loads((root / "datasets" / "golden" / "core" / f"{n}.json").read_text(encoding="utf-8"))["cases"]
               if k["expected"].get("status") == "ok")


def evidence_table(root=ROOT):
    per, impl = evidence(root)
    keys = [k for k, _, _ in EVIDENCE_ORDER]
    head = ["| Stage | " + " | ".join(f"`{k}`" for k in keys) + " | All |", "|---|" + "---:|" * (len(keys) + 1)]
    rows, tot = [], Counter()
    for st in STAGE_ORDER:
        c = per.get(st, Counter())
        tot.update(c)
        rows.append(f"| {st} | " + " | ".join(f"{c[k]:,}" for k in keys) + f" | {sum(c.values()):,} |")
    rows.append("| all | " + " | ".join(f"{tot[k]:,}" for k in keys) + f" | {sum(tot.values()):,} |")
    return head + rows, tot, impl


def readme_block(root=ROOT):
    fig = figures(root)
    _, tot, impl = evidence_table(root)
    return "\n".join([
        README_BEGIN, "",
        "Generated by `tools/case_figures.py --write` from the golden files and `oracle/OUTSIDE_SHARES.json`; do not edit; "
        "`repo-gates` runs `--check`.", "",
        f"**{fig['value_checked']} value-checked golden cases**: each build must return the oracle's numbers within a stated "
        f"tolerance. {fig['stage_a_sweeps']} of them are the stage A convention sweeps (generated grids of day counts, "
        f"calendars and compounding), so **{fig['value_checked_without_sweeps']} without those sweeps**.", "",
        "Besides them, "
        f"{fig['error_cases']} error cases check only that a bad input is refused with the right code, and "
        f"{fig['invariance_cases']} invariance cases ({fig['invariance_pairs']} pairs) check that two related inputs get "
        f"the same answer, with no expected number: {fig['total_cases']} cases of every class in all. The value-checked "
        "count leads because a build that refused every input would pass all the error cases and none of the value-checked ones.", "",
        "**Outside-checked share per stage** (value-checked cases counted under rule D6, over the share table's value-checked "
        "cases without generated sweeps; the same figures as [docs/results.md](docs/results.md)): "
        f"{fig['outside_shares']}. Stages A to C, R2 and R6 are not in the share table.", "",
        "**Evidence classes of the value-checked cases**, read from their `verified_by` labels, each case in its strongest "
        f"class: outside library {tot['library']:,}, printed published figure {tot['printed']:,}, blind re-derivation by a "
        f"second AI lane {tot['blind']:,}, own mpmath oracle {tot['mpmath']:,}, own float64 or exact oracle {tot['own']:,}, "
        f"reference-computed {tot['reference']:,}, hand-derived only {tot['hand']:,}, and {len(impl)} whose expected values "
        "are a build's own output (" + ", ".join(f"`{x}`" for x in impl) + "). Per stage in "
        "[docs/case-figures.md](docs/case-figures.md#evidence-classes-per-stage).", "",
        README_END])


def golden_block(root=ROOT):
    per = counts(root)
    lines = [GOLDEN_BEGIN, "", "Generated by `tools/case_figures.py --write`; do not edit. Per suite directory: suite "
             "files, then value-checked / error / invariance / all cases.", ""]
    for d in sorted(per):
        c = per[d]
        n_files = len(list((root / "datasets" / "golden" / d).glob("*.json")))
        lines.append(f"- `{d}/`: {n_files} files; {c['ok']:,} / {c['error']:,} / {c['same_as'] + c['any']:,} / {sum(c.values()):,}")
    return "\n".join(lines + ["", GOLDEN_END])


def replace_block(text, begin, end, block):
    if begin not in text or end not in text:
        return None
    return text[:text.index(begin)] + block + text[text.index(end) + len(end):]


def page(root=ROOT):
    per = counts(root)
    fig = figures(root)
    lines = ["# Golden case figures", "",
             "Generated by `tools/case_figures.py --write`; do not edit. `repo-gates` runs `--check`.", "",
             "Headline: **" + fig["value_checked"] + " value-checked golden cases**, then " + fig["error_cases"]
             + " error cases and " + fig["invariance_cases"] + " invariance cases (" + fig["invariance_pairs"]
             + " pairs: a `same_as` case and its `any` base case, which check that two related inputs get the same answer and no expected number); "
             + fig["total_cases"] + " cases of every class in all.", "",
             "Classes: `ok` is value-checked (numbers within a stated tolerance); `error` checks the error code only; "
             "`same_as` checks that a build answers two related inputs the same way (invariance); `any` is the base of such a pair "
             "and passes on any finite answer. A build that answers every case with an error code would pass the error cases and "
             "none of the value-checked ones, which is why the value-checked count leads.", "",
             "| Suite directory | Value-checked | Error | Invariance | `any` base | All |", "|---|---:|---:|---:|---:|---:|"]
    for d in sorted(per):
        c = per[d]
        lines.append(f"| `{d}` | {c['ok']:,} | {c['error']:,} | {c['same_as']:,} | {c['any']:,} | {sum(c.values()):,} |")
    lines.append(f"| all | {fig['value_checked']} | {fig['error_cases']} | {fig['invariance_cases']} | {fig['any_cases']} | {fig['total_cases']} |")
    table, tot, impl = evidence_table(root)
    lines += ["", "## Without the stage A convention sweeps", "",
              "`core/daycount`, `core/calendar` and `core/compounding` are generated grids of dates and conventions: "
              f"{fig['stage_a_sweeps']} value-checked cases. Without them the headline is **{fig['value_checked_without_sweeps']}** "
              "value-checked cases.", "",
              "## Outside-checked share per stage", "",
              "One definition on every page: value-checked cases counted under rule D6 (an outside library, or a blind "
              "re-derivation by a second AI lane where the rule allows it; never a person), over the share table's "
              "value-checked cases without generated sweeps, read from `oracle/OUTSIDE_SHARES.json` by `outside_pair()`: "
              f"{fig['outside_shares']}. Stages A to C, R2 and R6 are not in the share table.", "",
              "## Evidence classes per stage", "",
              "Read from each value-checked case's `verified_by` labels; a case counts once, in the first class below "
              "that one of its labels matches. This is a reading of the labels, not rule D6, and the D6 share above is "
              "the figure to quote. They differ where a stage records its outside checks in a separate register rather "
              "than in the labels (stage F's re-derivation and library registers, stage J's `oracle/OUTSIDE_J.json`, "
              "stage K's blind packets), and where a label names a library check of single outputs that D6 does not "
              "count (some stage K SciPy cross-checks).", ""]
    lines += [f"- `{k}`: {desc}" for k, desc, _ in EVIDENCE_ORDER]
    lines += [""] + table
    lines += ["", "Exceptions to design principle 5 (expected results never come from an implementation): "
              + ", ".join(f"`{x}`" for x in impl) + ". The `k8_k` values are the Python build's output under the pinned "
              "reference scheme (`oracle/python/gen_stage_k_k8.py` imports the build); the `sorx_h` values are the Python "
              "build's output, kept as an agreement check across the builds and not counted as outside-checked. "
              f"{tot['hand']:,} value-checked cases rest on hand derivation only."]
    return "\n".join(lines) + "\n"


def main(argv):
    text = page()
    blocks = ((Path("README.md"), README_BEGIN, README_END, readme_block()),
              (GOLDEN_README, GOLDEN_BEGIN, GOLDEN_END, golden_block()))
    if "--write" in argv:
        (ROOT / PAGE).write_text(text, encoding="utf-8", newline="\n")
        for rel, b, e, block in blocks:
            new = replace_block((ROOT / rel).read_text(encoding="utf-8"), b, e, block)
            if new is None:
                print(f"{rel}: no {b} ... {e} markers; add them where the figures belong")
                return 1
            (ROOT / rel).write_text(new, encoding="utf-8", newline="\n")
        return 0
    if "--check" in argv:
        bad = []
        have = (ROOT / PAGE).read_text(encoding="utf-8") if (ROOT / PAGE).exists() else ""
        if have != text:
            bad.append(f"{PAGE} is stale: run python tools/case_figures.py --write")
        for rel, b, e, block in blocks:
            cur = (ROOT / rel).read_text(encoding="utf-8")
            if replace_block(cur, b, e, block) != cur:
                bad.append(f"{rel}: generated block missing or stale: run python tools/case_figures.py --write")
        fig = figures()
        bad += [f"{f}: headline does not give the current value-checked count {fig['value_checked']}"
                for f in HEADLINE_PAGES if f"{fig['value_checked']} value-checked" not in (ROOT / f).read_text(encoding="utf-8")]
        for b in bad:
            print(b)
        if bad:
            return 1
        print(f"{PAGE}: current; README and golden README blocks current; headline current in {', '.join(HEADLINE_PAGES)}")
        return 0
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
