#!/usr/bin/env python3
"""Stage J lane J-0b: golden cases for three fuzz findings (main run 43390662426, seed 3).

    cd oracle/python && uv run python gen_stage_j_fuzz.py

Rulings J-0b.1 to J-0b.3 (specifications/stage-j-rulings.md). Each case is an error case whose code follows from the
rulings alone, so no numerical oracle is involved. Standard library only; the returns are a fixed deterministic series.
"""
import json
import math
from pathlib import Path

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

DOC = {"schema_version": "1.0", "suite": "fuzzfix_j", "spec": "specifications/stage-j-rulings.md",
       "spec_version": "1.0.0", "generator": "oracle/python/gen_stage_j_fuzz.py",
       "reviewer": "none: self-assessment until the end-of-project human review", "cases": CASES}

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(DOC, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(CASES)} cases to {OUT}")
