"""Build the aadadj_k blind packet (DR-H2) from spec text and case INPUTS only. Never reads `expected` values:
the output template is the expected object with every leaf replaced by null (shape only).

    python -I aadadj_make_packet.py <repo> <out_dir>
"""
import hashlib
import json
import pathlib
import re
import sys

SUITE = "datasets/golden/stage_k/aadadj_k.json"
SPEC = "specifications/06-risk/xva-aad-adjustments.md"
RULINGS = "specifications/stage-k-rulings-xva-aad.md"
B = ["aadadj_k-%04d" % i for i in range(1, 14)]
KEEP_SECTIONS = ("## `xva.sens.aad`", "## Tolerances and outside share")


def clean(text):
    text = re.sub(r"<!-- strip:begin -->.*?<!-- strip:end -->", "", text, flags=re.S)
    text = re.sub(r"\(?golden `?aadadj_k-\d{4}`?\)?", "", text)
    text = re.sub(r"`?aadadj_k-\d{4}`?", "", text)
    text = re.sub(r"Golden +sits on the kink and pins the convention; `-0007` and `-0010` sit on the zero branch\.", "", text)
    text = re.sub(r"`-00\d\d`", "", text)
    text = text.replace("a convention .", "a convention.")
    text = re.sub(r"`?[\w./-]+\.(py|md|json)`?", "(repo file)", text)
    text = re.sub(r" \(measured:[^)]*\)", "", text)
    return text


def spec_text(repo):
    t = (repo / SPEC).read_text(encoding="utf-8")
    parts = re.split(r"(?m)^(?=## )", clean(t))
    plain = parts[0].split("**Plain idea.**", 1)[1]
    keep = [p for p in parts[1:] if p.startswith(KEEP_SECTIONS)]
    keep = [re.sub(r"Outside: none.*", "", p, flags=re.S) if p.startswith("## Tolerances") else p for p in keep]
    return ("# AAD sensitivities of the valuation adjustments (stripped spec)\n\n**Plain idea.**" + plain
            + "\n".join(keep))


def rulings_text(repo):
    rows = [l for l in (repo / RULINGS).read_text(encoding="utf-8").splitlines() if re.match(r"\| KR-26[2-5] \|", l)]
    assert len(rows) == 4, len(rows)
    return "# Rulings KR-262 to KR-265 (table rows only)\n\n| # | Point | Ruling |\n|---|---|---|\n" + \
        "\n".join(clean(r) for r in rows) + "\n"


def nulls(x):
    if isinstance(x, dict):
        return {k: nulls(v) for k, v in x.items()}
    if isinstance(x, list):
        return [nulls(v) for v in x]
    return None


def main(repo, out):
    repo, out = pathlib.Path(repo), pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cases = {c["case_id"]: c for c in json.loads((repo / SUITE).read_text(encoding="utf-8"))["cases"]}
    inputs = {cid: cases[cid]["inputs"] for cid in B}
    template = {cid: nulls(cases[cid]["expected"]["outputs"]) for cid in B}
    files = {"spec.md": spec_text(repo), "rulings.md": rulings_text(repo),
             "inputs.json": json.dumps(inputs, indent=1) + "\n", "template.json": json.dumps(template, indent=1) + "\n"}
    files["README.md"] = (pathlib.Path(__file__).with_name("PACKET_README.md")).read_text(encoding="utf-8")
    for n, t in files.items():
        (out / n).write_text(t, encoding="utf-8", newline="\n")
    lines = [f"{hashlib.sha256((out / n).read_bytes()).hexdigest()}  {n}" for n in sorted(files)]
    (out / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("MANIFEST.sha256", hashlib.sha256((out / "MANIFEST.sha256").read_bytes()).hexdigest())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
