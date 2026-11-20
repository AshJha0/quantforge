"""tlk_k v2 blind packet (DR-H2) for tlk_k-0012..0020 (risk.backtest.traffic_light after KR-253).

Pattern: trig_v2_make_packet.py. Writes into <packet dir> (outside every worktree, empty):
  README.md, specs/traffic-light.blind.md, rulings/kr237-kr253.blind.md, inputs/tlk_k.inputs.json,
  output_template.json, MANIFEST.sha256.
Source text: the `risk.backtest.traffic_light` section of specifications/06-risk/var-es-and-backtests.md and
rulings KR-237 and KR-253 (specifications/stage-k-rulings-w1b.md). Cuts (CUTS): the worked example value, the
sentences that state the n = 1 answers, case ids, golden lists, accuracy figures tied to the goldens.
Inputs are read from datasets/golden/stage_k/tlk_k.json, `inputs` only. Never reads tlk_v2_expected.json.

    python -I program/stage_h_blind_w2/tlk_v2_make_packet.py . C:/Work/Claude/qf-blind/tlk_k_v2_packet
"""
import hashlib
import json
import re
import sys
from pathlib import Path

CASES = [f"tlk_k-{i:04d}" for i in range(12, 21)]
SPEC = "specifications/06-risk/var-es-and-backtests.md"
RULINGS = "specifications/stage-k-rulings-w1b.md"
SPEC_CUTS = [
    (r", so at `n = 1` it is `c` itself and a confidence on a zone edge lands in the higher zone \(`n = 1, x = 0, c = 0\.95` is YELLOW\)", ""),
    (r" Worked example: `n = 250, x = 0, c = 0\.99` gives `0\.99\^250 = 0\.0810585\.\.\.`, GREEN\.", ""),
    (r" The earlier sum of log-gamma terms.*?before the run\)\.", ""),
]
KR237_CUTS = [
    (r" \*\*Accuracy\.\*\*.*?\(1e-10\)\.", ""),
    (r" New value goldens.*?listed for the coordinator", ""),
    (r" \(golden btk_k with n = 2, one exception: RED\)", ""),
]
KR253_CUTS = [
    (r"; status: proposed by lane k-r2-tl, 2026-11-20, for the coordinator", ""),
    (r", so it is `c` exactly at `n = 1`", ""),
    (r" Reason: the first version.*?, measured\)\.", ""),
    (r" The double-double power is within.*?was not used\.", ""),
    (r" Boundary goldens.*?four builds by the conformance runner", ""),
]

README = """# tlk_k blind re-derivation packet (DR-H2), version 2

You are the blind lane. From the rules in this folder alone, compute the outputs of the 9 cases in `inputs/`.
Nobody will tell you whether you are right until your results are frozen.

## Hard rules

1. Read nothing outside this folder and your own working folder. No repository, no web page.
2. Write your reference yourself: plain Python, standard library only. Compute the probability independently,
   preferably exactly with `fractions.Fraction` (the binary64 `confidence` converted exactly), rounded once to
   binary64 at the end. You need not copy the floating-point algorithm of the rulings; the target is the
   mathematical value of `P(X <= x)` with `q = c` exactly as given.
3. Report numbers as JSON numbers at full binary64 precision; `zone` as a string; `plus_factor` as a number or null.
4. Write `notes.md`: every ambiguity and assumption, with case ids and the file and section read.

## What to produce (in your own working folder)

1. `blind_results.json`: `output_template.json`'s `results_skeleton` with every null replaced (keep `plus_factor`
   null where the rules say null). Nesting: `{"cases": {"<case_id>": {field: value}}}`.
2. `blind_ref.py` and `notes.md`.
3. SHA-256 of `blind_results.json` into `blind_results.sha256`; report it as the first line of your hand-back.
   Never change `blind_results.json` after that.

## Files

- `specs/traffic-light.blind.md`: the operation's section of the spec.
- `rulings/kr237-kr253.blind.md`: rulings KR-237 (the binomial algorithm) and KR-253 (its use here, q = c).
- `inputs/tlk_k.inputs.json`, `output_template.json`, `MANIFEST.sha256`.
"""


def cut(text, cuts, what):
    for pat, rep in cuts:
        text, k = re.subn(pat, rep, text, flags=re.S)
        if k != 1:
            raise SystemExit(f"cut not applied once in {what}: {pat}")
    return text


def main(repo, out):
    repo, out = Path(repo), Path(out)
    if out.exists() and any(out.iterdir()):
        raise SystemExit("packet dir not empty")
    spec = (repo / SPEC).read_text(encoding="utf-8")
    sec = re.search(r"^## `risk\.backtest\.traffic_light`\n.*?(?=^## )", spec, re.S | re.M).group(0)
    sec = cut(sec, SPEC_CUTS, "spec")
    rul = (repo / RULINGS).read_text(encoding="utf-8").splitlines()
    r237 = next(l for l in rul if l.startswith("| KR-237 "))
    r253 = next(l for l in rul if l.startswith("| KR-253 "))
    r237 = cut(r237, KR237_CUTS, "KR-237")
    r253 = cut(r253, KR253_CUTS, "KR-253")
    golden = json.loads((repo / "datasets/golden/stage_k/tlk_k.json").read_text(encoding="utf-8"))
    cases = {c["case_id"]: c["inputs"] for c in golden["cases"] if c["case_id"] in CASES}
    assert sorted(cases) == CASES
    files = {
        "README.md": README,
        "specs/traffic-light.blind.md": "# Spec excerpt (stripped)\n\n" + sec,
        "rulings/kr237-kr253.blind.md": "# Rulings (stripped)\n\n| Id | Topic | Ruling | Evidence |\n|---|---|---|---|\n"
                                       + r237 + "\n" + r253 + "\n",
        "inputs/tlk_k.inputs.json": json.dumps({"operation": "risk.backtest.traffic_light", "cases": cases}, indent=1) + "\n",
        "output_template.json": json.dumps({"results_skeleton": {"cases": {k: {"cumulative_probability": None, "zone": None,
                                            "plus_factor": None} for k in CASES}}}, indent=1) + "\n",
    }
    lines = []
    for name, body in files.items():
        p = out / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body.encode("utf-8"))
        lines.append(f"{hashlib.sha256(body.encode('utf-8')).hexdigest()}  {name}")
    (out / "MANIFEST.sha256").write_bytes(("\n".join(lines) + "\n").encode())
    print(hashlib.sha256((out / "MANIFEST.sha256").read_bytes()).hexdigest())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
