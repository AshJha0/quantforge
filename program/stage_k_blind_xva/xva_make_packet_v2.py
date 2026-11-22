"""Build the xVA blind packet, version 2 (DR-H2), from spec text and case INPUTS only.

Version 1 (xva_make_packet.py, frozen results in stage_k_blind/xva_v1/) is kept unchanged as a record.
Version 2 adds what v1 lacked (KR-298): the G-40 and G-41 formal statements (xva-framework.md, worked examples
removed), the portfolio CVA formula, the WWR and shock-library specs, and an inputs.json that holds every case's
inputs exactly as the candidate goldens use them (oracle/xva_k8b_candidates/; only `inputs` are read, never
`expected`). The template lists the requested output names with null leaves.

Usage: python -I xva_make_packet_v2.py <repo> <out_dir>
"""
import hashlib
import json
import pathlib
import re
import sys

SPECS = ["xva-aad-sensitivities", "xva-colva", "xva-mva-im", "xva-stressed-exposure", "xva-mpor-closeout",
         "xva-funding-asymmetric", "xva-wwr-copula", "xva-stress-shocks"]
B = (["aadx_k-%04d" % i for i in range(1, 9)] + ["colva_k-%04d" % i for i in range(1, 7)]
     + ["mva_k-%04d" % i for i in range(1, 6)] + ["str_k-%04d" % i for i in range(1, 7)]
     + ["mpor_k-%04d" % i for i in range(1, 7)] + ["clp_k-0001"] + ["fva_k-%04d" % i for i in range(1, 7)]
     + ["shk_k-0001", "shk_k-0002", "wwr_k-0010"])
SUITES = ["aadx_k", "colva_k", "mva_k", "str_k", "mpor_k", "clp_k", "fva_k", "shk_k", "wwr_k"]


def strip(text):
    text = re.sub(r"<!-- strip:begin -->.*?<!-- strip:end -->", "", text, flags=re.S)
    text = re.sub(r"## Outside-check design.*?(?=\n## |\Z)", "", text, flags=re.S)
    return text


def nulls(x):
    if isinstance(x, dict):
        return {k: nulls(v) for k, v in x.items()}
    if isinstance(x, list):
        return [nulls(v) for v in x]
    return None


def framework_excerpt(repo):
    fw = (repo / "specifications/06-risk/xva-framework.md").read_text(encoding="utf-8").splitlines()
    keep = [l for l in fw if l.startswith(("Formal statement. Per set", "Outputs per set", "Formal statement, buckets",
                                           "- `CVA = (1 - R_c)", "- `FCA = s_b", "- `MVA = s_IM"))]
    port = [l for l in (repo / "specifications/06-risk/xva-exposure-portfolio.md").read_text(encoding="utf-8").splitlines()
            if l.startswith("- `cva = (1 - R) sum_i discounted_ee")]
    assert len(keep) == 6 and len(port) == 1, (len(keep), len(port))
    return ("# Excerpt: stage G formal statements used by the K-8b cases\n\n"
            "From `xva-framework.md` (G-40 `xva.exposure.collateralised`, G-41 `xva.adjustments.value`; worked examples "
            "removed) and `xva-exposure-portfolio.md` (the CVA of `xva.exposure.portfolio_hw`). In G-41, `S_c S_b` "
            "without an argument means both survivals at the bucket start `t_(i-1)`, as for FCA and FBA.\n\n"
            "## G-40\n\n" + keep[0] + "\n\n" + keep[1] + "\n\n## G-41\n\n" + "\n".join(keep[2:]) +
            "\n\n## Portfolio CVA (G-42b)\n\n" + port[0] + "\n")


def main(repo, out):
    repo, out = pathlib.Path(repo), pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for s in SPECS:
        t = strip((repo / "specifications/06-risk" / f"{s}.md").read_text(encoding="utf-8"))
        (out / f"{s}.md").write_text(t, encoding="utf-8", newline="\n")
    (out / "stage-g-excerpt.md").write_text(framework_excerpt(repo), encoding="utf-8", newline="\n")
    rulings = (repo / "specifications/stage-k-rulings-xva.md").read_text(encoding="utf-8")
    rows = [l for l in rulings.splitlines() if re.match(r"\| KR-(16[0-9]|17[0-6]|29[6-9]) \|", l)]
    # numbers that would leak answers are removed from the rulings: KR-296 and KR-297 effect sentences
    rows = [re.sub(r"\*\*Numerical effect\*\*.*?\|", "(numerical effect omitted in the packet) |", r) if "KR-296" in r else r
            for r in rows]
    rows = [re.sub(r"Effect: colva_k-0002.*?\. No released golden\.", "(effect omitted in the packet)", r) for r in rows]
    (out / "rulings.md").write_text("# K-8b rulings (table rows only)\n\n| # | Point | Ruling |\n|---|---|---|\n"
                                    + "\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    inputs, template = {}, {}
    cand = repo / "oracle" / "xva_k8b_candidates"
    for s in SUITES:
        for c in json.loads((cand / f"{s}.json").read_text(encoding="utf-8"))["cases"]:
            if c["case_id"] in B:
                inputs[c["case_id"]] = {"operation": c["operation"], "inputs": c["inputs"]}
                template[c["case_id"]] = nulls(c["expected"]["outputs"])
    assert sorted(inputs) == sorted(B), set(B) - set(inputs)
    es = json.loads((repo / "datasets/golden/stage_g/expsim_g.json").read_text(encoding="utf-8"))["cases"]
    e3 = [c for c in es if c["case_id"] == "expsim_g-0003"][0]
    fixed = {"expsim_g-0003": {"inputs": e3["inputs"],
                               "discounted_ee": e3["expected"]["outputs"]["discounted_ee"],
                               "note": "exact one-factor discounted EE (released stage G golden); held fixed for aadx_k-0008"}}
    for name, obj in (("inputs.json", inputs), ("template.json", template), ("fixed_inputs.json", fixed)):
        (out / name).write_text(json.dumps(obj, indent=1) + "\n", encoding="utf-8", newline="\n")
    (out / "README.md").write_text(
        "Compute every output in template.json for the case inputs in inputs.json, from the rules in the spec files,\n"
        "stage-g-excerpt.md and rulings.md. Use your own independent method and precision. Inputs are binary64\n"
        "numbers; give outputs as binary64 (17 significant digits), strings and booleans as such. Gradients are\n"
        "d output / d input per unit absolute change, for the paths listed in each case's `wrt`.\n"
        "aadx_k-0008 uses the exact EE in fixed_inputs.json (held fixed). Write blind_results.json in the shape of\n"
        "template.json. Record every ambiguity you meet and how you resolved it in notes.md.\n",
        encoding="utf-8", newline="\n")
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}"
             for p in sorted(out.iterdir()) if p.name != "MANIFEST.sha256"]
    (out / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(hashlib.sha256((out / "MANIFEST.sha256").read_bytes()).hexdigest())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
