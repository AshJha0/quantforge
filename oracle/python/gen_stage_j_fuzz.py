#!/usr/bin/env python3
"""Stage J lane J-0b: golden cases for three fuzz findings (main run 43390662426, seed 3).

    cd oracle/python && uv run python gen_stage_j_fuzz.py

Rulings J-0b.1 to J-0b.3 (specifications/stage-j-rulings.md). Each case is an error case whose code follows from the
rulings alone, so no numerical oracle is involved. Standard library only; the returns are a fixed deterministic series.

Cases 0007 onward are the J-0b.3 audit: every operation that reads a matrix, given a valid golden case's inputs with the
first row of one matrix one entry short. All four languages already answer E_INPUT (row lengths are checked before any
index access), so these cases pin that behaviour; no ruling changed.
"""
import copy
import json
import math
from pathlib import Path

GOLDEN = Path(__file__).resolve().parents[2] / "datasets" / "golden"
OUT = Path(__file__).resolve().parents[2] / "datasets" / "golden" / "stage_j" / "fuzzfix_j.json"


def returns(n: int, big_at: int) -> list[float]:
    r = [round(0.01 * math.sin(1.7 * k + 0.3), 10) for k in range(n)]
    r[big_at] = -2.6755826e297  # finite, but its square overflows binary64 (the fuzz input's value)
    return r


def case(k, op, inputs, code, tags, description):
    return {"case_id": f"fuzzfix_j-{k:04d}", "operation": op, "inputs": inputs,
            "expected": {"status": "error", "error_code": code}, "tolerance_class": "date_and_convention",
            "verified_by": ["reference-computed"], "tags": ["invalid", "fuzz", *tags, "synthetic"],
            "description": description}


CASES = [
    case(1, "vol.garch.forecast", {"omega": 5e-06, "alpha": 0.12, "beta": 0.82, "next_variance": 0.0003,
                                   "horizon": 2147483648, "periods_per_year": 252.0},
         "E_LIMIT", ["garch", "limit"], "horizon 2^31 is above the 100,000 limit (J-0b.1; fuzz garch_e-0020)"),
    case(2, "vol.garch.forecast", {"omega": 5e-06, "alpha": 0.12, "beta": 0.82, "next_variance": 0.0003,
                                   "horizon": 100001, "periods_per_year": 252.0},
         "E_LIMIT", ["garch", "limit"], "horizon one above the limit (J-0b.1)"),
    case(3, "vol.garch.estimate", {"returns": returns(120, 37), "initial_variance": "SAMPLE",
                                   "distribution": "STUDENT_T", "demean": False},
         "E_NON_FINITE", ["garch"], "a finite return whose square overflows: E_NON_FINITE before any search "
         "(R6-8.1, J-0b.2; fuzz garch_f-0010)"),
    case(4, "vol.garch.estimate", {"returns": returns(40, 5), "initial_variance": 1e-4,
                                   "distribution": "NORMAL", "demean": True},
         "E_NON_FINITE", ["garch"], "as 0003 with a numeric initial variance and demeaning (J-0b.2)"),
    case(5, "exotic.basket.moment", {"forwards": [100.0, 100.0], "weights": [0.5, 0.5], "vols": [0.2, 0.2],
                                     "correlation": [[1.0, 1.0], []], "strike": 100.0, "expiry_years": 1.0,
                                     "rate": 0.03, "option_type": "CALL"},
         "E_INPUT", ["basket"], "ragged correlation, an empty second row (J-0b.3; fuzz e1_exotic-0211)"),
    case(6, "exotic.basket.moment", {"forwards": [100.0, 100.0], "weights": [0.5, 0.5], "vols": [0.2, 0.2],
                                     "correlation": [[1.0], [0.0, 1.0]], "strike": 100.0, "expiry_years": 1.0,
                                     "rate": 0.03, "option_type": "CALL"},
         "E_INPUT", ["basket"], "ragged correlation, a short first row (J-0b.3)"),
]

# (golden file, source case, path to the matrix inside "inputs"): one per operation and matrix key.
RAGGED = [
    ("core/diff_linalg.json", "diff_linalg-0010", ["a"]),
    ("core/diff_linalg.json", "diff_linalg-0012", ["a"]),
    ("core/diff_linalg.json", "diff_linalg-0013", ["a"]),
    ("r6/hedgeqp_large_r6.json", "hedgeqp_large_r6-0001", ["a"]),
    ("r6/hedgeqp_large_r6.json", "hedgeqp_large_r6-0003", ["eq_matrix"]),
    ("stage_b/hedge.json", "hedge-0001", ["a"]),
    ("stage_c/smile.json", "smile-0045", ["total_variance"]),
    ("stage_c/surface.json", "surface-0001", ["surface", "vols"]),
    ("stage_c/surface.json", "surface-0003", ["surface", "vols"]),
    ("stage_c/surface.json", "surface-0011", ["surface", "vols"]),
    ("stage_e/exotic_e.json", "exotic_e-0115", ["correlation"]),
    ("stage_e/surf_e.json", "surf_e-0024", ["total_variance"]),
    ("stage_e_b/corr_e.json", "corr_e-0001", ["matrix"]),
    ("stage_e_b/corr_e.json", "corr_e-0002", ["matrix"]),
    ("stage_e_b/ratesvol_e.json", "ratesvol_e-0001", ["cube", "alpha"]),
    ("stage_e_b/ratesvol_e.json", "ratesvol_e-0001", ["cube", "beta"]),
    ("stage_e_b/ratesvol_e.json", "ratesvol_e-0001", ["cube", "rho"]),
    ("stage_e_b/ratesvol_e.json", "ratesvol_e-0001", ["cube", "nu"]),
    ("stage_f/e1_risk.json", "e1_risk-0372", ["covariance"]),
    ("stage_f/risk_f3.json", "risk_f3-0010", ["changes"]),
    ("stage_f/risk_f4b.json", "risk_f4b-0001", ["gamma"]),
    ("stage_f/uc4_f.json", "uc4_f-0001", ["factor_returns"]),
    ("stage_g/collexp_g.json", "collexp_g-0001", ["trades", 0, "values"]),
    ("stage_g/collexp_g.json", "collexp_g-0002", ["trades", 1, "values"]),
    ("stage_g/simm_g.json", "simm_g-0001", ["correlations"]),
    ("stage_g/wwr_g.json", "wwr_g-0001", ["values"]),
    ("stage_i/hedgefrontier_i.json", "hedgefrontier_i-0001", ["a"]),
    ("stage_i/hedgeint_i.json", "hedgeint_i-0001", ["a"]),
    ("stage_i/hedgemv5_i.json", "hedgemv5_i-0001", ["covariance"]),
    ("stage_i/hedgemv5_i.json", "hedgemv5_i-0002", ["hedge_changes"]),
    ("stage_i/hedgeres_i.json", "hedgeres_i-0001", ["a"]),
    ("stage_i/hedgeres_i.json", "hedgeres_i-0001", ["covariance"]),
    ("stage_i/hedgeselect_i.json", "hedgeselect_i-0001", ["a"]),
]


def ragged(k, file, source, path):
    src = next(c for c in json.loads((GOLDEN / file).read_text(encoding="utf-8"))["cases"] if c["case_id"] == source)
    inputs = copy.deepcopy(src["inputs"])
    holder = inputs
    for p in path[:-1]:
        holder = holder[p]
    m = holder[path[-1]]
    holder[path[-1]] = [m[0][:-1], *m[1:]]
    where = "/".join(map(str, path))
    return case(k, src["operation"], inputs, "E_INPUT", ["ragged"],
                f"{source} with the first row of {where} one entry short (J-0b.3 audit)")


CASES += [ragged(7 + i, *r) for i, r in enumerate(RAGGED)]

DOC = {"schema_version": "1.0", "suite": "fuzzfix_j", "spec": "specifications/stage-j-rulings.md",
       "spec_version": "1.0.0", "generator": "oracle/python/gen_stage_j_fuzz.py",
       "reviewer": "none: self-assessment until the end-of-project human review", "cases": CASES}

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(DOC, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(CASES)} cases to {OUT}")
