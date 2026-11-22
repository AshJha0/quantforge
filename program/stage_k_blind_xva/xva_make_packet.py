"""Build the xVA blind packet (DR-H2) from spec text and case inputs only.

Never reads xva_expected.json. Removes every <!-- strip:begin --> .. <!-- strip:end -->
block and the "Outside-check design" section (it names goldens and methods).
Usage: python -I xva_make_packet.py <repo> <out_dir>
"""
import hashlib, json, pathlib, re, sys

SPECS = ["xva-aad-sensitivities", "xva-colva", "xva-mva-im", "xva-stressed-exposure",
         "xva-mpor-closeout", "xva-funding-asymmetric"]
CASES = {  # case id -> outputs requested (no values)
    "aadx_k-0001": ["d_cva_d_h_c", "d_cva_d_r_c", "d_cva_d_h_b", "d_fca_d_s_b", "d_cva_d_ee[1]"],
    "colva_k-0001": ["colva"], "colva_k-0002": ["colva"],
    "colva_k-0003": ["colva", "collateral_floor"],
    "mva_k-0001": ["mva"], "mva_k-0002": ["mva"], "mva_k-0003": ["expected_im"],
    "str_k-0001": ["eepe_current_A", "eepe_stressed_A", "eepe_current_B", "eepe_stressed_B",
                   "ead_used_A", "ead_used_B", "k_current", "k_stressed", "calibration"],
    "str_k-0002": ["k_current", "k_stressed", "calibration", "ead_used_A", "ead_used_B"],
    "str_k-0003": ["calibration"], "str_k-0004": ["eepe_current", "eepe_stressed"],
    "mpor_k-0001": ["floor"], "mpor_k-0002": ["floor"], "mpor_k-0003": ["floor"],
    "mpor_k-0004": ["floor"], "mpor_k-0005": ["floor"],
    "mpor_k-0006": ["floor", "mpor_days", "binding"],
    "fva_k-0001": ["fca", "fba", "fva"], "fva_k-0002": ["fba"],
    "fva_k-0003": ["fca", "fba"], "fva_k-0006": ["fca"],
}

def strip(text):
    text = re.sub(r"<!-- strip:begin -->.*?<!-- strip:end -->", "", text, flags=re.S)
    text = re.sub(r"## Outside-check design.*?(?=\n## |\Z)", "", text, flags=re.S)
    return text

def main(repo, out):
    repo, out = pathlib.Path(repo), pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for s in SPECS:
        t = strip((repo / "specifications/06-risk" / f"{s}.md").read_text(encoding="utf-8"))
        (out / f"{s}.md").write_text(t, encoding="utf-8", newline="\n")
    (out / "template.json").write_text(json.dumps(
        {c: {o: None for o in outs} for c, outs in CASES.items()}, indent=1), newline="\n")
    (out / "README.md").write_text(
        "Compute every output in template.json from the rules and case inputs in the spec files.\n"
        "Use your own independent method. Numbers as binary64 (17 significant digits),\n"
        "calibration as a string, binding as a boolean. Write blind_results.json in the same shape.\n",
        newline="\n")
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}"
             for p in sorted(out.iterdir()) if p.name != "MANIFEST.sha256"]
    (out / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", newline="\n")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
