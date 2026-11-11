"""Self-check of hand-set error goldens (ruling G-50).

For every error case other than E_SCHEMA, re-derives the schema step of the validation order from the operation's own ok
cases: each key the case carries must have the JSON type (string, integer, real, boolean, list, object) it has in the ok
cases, and each key present in every ok case of that operation must be present (unless the spec lists it as optional:
OPTIONAL below). A failure means the case would stop at E_SCHEMA before its intended code. For E_LIMIT cases it also checks
that the case is otherwise schema-valid. Exit code 1 on any mismatch.

    uv run python check_error_cases.py [folder ...]    (default: stage_i stage_g stage_f)
"""
import json
import sys
from pathlib import Path

GOLD = Path(__file__).resolve().parents[2] / "datasets" / "golden"
OPTIONAL = {"monitoring", "monitoring_per_year", "model", "independent_amount", "csa", "specified_pairs", "im", "im_spread",
            "capital", "hurdle_rate", "hazard_rate", "recovery", "reporting_currency", "specified_currency_reduction",
            "smoothing_width", "bump_relative", "grid",
            "ridge", "eq_matrix", "eq_rhs", "lower", "upper", "singular", "lower_lots", "upper_lots",  # stage I hedge solvers
            "covariance", "exposure_changes", "hedge_changes", "rounding",
            "half_spreads", "impact", "cost_weight", "margin_rates", "margin_limit", "max_instruments"}


UNION = {"initial_variance": {"str", "real", "int"}}  # spec: "SAMPLE" or a number (05-volatility/garch.md)


def jtype(v):
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "real"
    if v in ("NaN", "Infinity", "-Infinity"):  # F-1: the non-finite tokens are Real values on the wire
        return "real"
    return type(v).__name__


def main(folders):
    bad = 0
    for folder in folders:
        for p in sorted((GOLD / folder).glob("*.json")):
            if p.name.startswith("e1"):
                continue
            cases = json.loads(p.read_text(encoding="utf-8")).get("cases", [])
            ok = {}
            for c in cases:
                if c["expected"]["status"] == "ok" and isinstance(c["inputs"], dict):
                    ok.setdefault(c["operation"], []).append(c["inputs"])
            for c in cases:
                e = c["expected"]
                if e["status"] != "error" or e["error_code"] == "E_SCHEMA" or c["operation"] not in ok:
                    continue
                types = {}
                for o in ok[c["operation"]]:
                    for k, v in o.items():
                        types.setdefault(k, set()).add(jtype(v))
                same = [o for o in ok[c["operation"]] if o.get("model") == c["inputs"].get("model")] or ok[c["operation"]]
                common = set.intersection(*(set(o) for o in same))  # required keys judged per model (G-5 short_rate rule)
                msgs = []
                for k, v in c["inputs"].items():
                    t = jtype(v)
                    if k in types and t not in (types[k] | UNION.get(k, set())) and not (t == "int" and "real" in types[k]):
                        msgs.append(f"{k}: {t}, ok cases use {sorted(types[k])}")
                for k in sorted(common - set(c["inputs"]) - OPTIONAL):
                    msgs.append(f"{k} missing (present in every ok case)")
                if msgs:
                    bad += 1
                    print(f"{c['case_id']} ({e['error_code']}, {c.get('description', '')}): " + "; ".join(msgs))
    print(f"error cases with a schema mismatch: {bad}")
    return bad


if __name__ == "__main__":
    sys.exit(1 if main(sys.argv[1:] or ["stage_i", "stage_g", "stage_f"]) else 0)
