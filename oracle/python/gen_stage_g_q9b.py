"""Stage G wave 3e, Q9 part 2: model-reserve dispersion statistic (ruling G-36).

`risk.model_reserve.dispersion` aggregates prices of one exotic under several models into the reserve figures of
`specifications/06-risk/model-reserve.md`. Values are exact decimal arithmetic (Python `fractions` on the binary64 inputs),
rounded once to binary64. No outside library: arithmetic on the inputs (not counted).

    cd oracle/python && uv run python -W ignore gen_stage_g_q9b.py
"""
from fractions import Fraction as Fr

from qf_oracle import common
from qf_oracle.common import Suite

OP = "risk.model_reserve.dispersion"


def disp(inp):
    p = {k: Fr(v) for k, v in inp["prices"].items()}
    ref = p[inp["reference_model"]]
    hi, lo = max(p.values()), min(p.values())
    dev = {k: abs(v - ref) for k, v in p.items()}
    res = max(dev.values())
    worst = sorted(k for k, v in dev.items() if v == res)[0]
    return {"mean": float(sum(p.values()) / len(p)), "range": float(hi - lo), "half_range": float((hi - lo) / 2),
            "reserve": float(res), "worst_model": worst, "relative_reserve": None if ref == 0 else float(res / abs(ref))}


def main():
    s = Suite("reserve_g", "specifications/06-risk/model-reserve.md", "oracle/python/gen_stage_g_q9b.py")
    rows = [
        (dict(prices={"HESTON": 4.1832, "LOCAL_VOL": 4.6021, "SLV": 4.3907}, reference_model="SLV"), "down-and-out call, three models"),
        (dict(prices={"HESTON": 0.5123, "LOCAL_VOL": 0.4987, "SLV": 0.5050}, reference_model="HESTON"), "digital, reference at the top"),
        (dict(prices={"HESTON": 2.0, "LOCAL_VOL": 2.0}, reference_model="LOCAL_VOL"), "two models agree: reserve 0"),
        (dict(prices={"HESTON": 0.0, "LOCAL_VOL": 0.012, "SLV": 0.004}, reference_model="HESTON"), "reference price 0: relative_reserve null"),
        (dict(prices={"A": 1.0, "B": 3.0, "C": -1.0}, reference_model="A"), "tie in deviation: worst_model is the first in code-point order"),
        (dict(prices={"HESTON": 1e6 + 0.1, "LOCAL_VOL": 1e6 + 0.3, "SLV": 1e6 + 0.2}, reference_model="SLV"), "large level: exact differences"),
    ]
    for inp, d in rows:
        s.add(OP, inp, disp(inp), verified=["exact-rational"], tags=["q9", "reserve", "synthetic"], description=d,
              limit={"absolute": 1e-12, "relative": 1e-15, "reason": "one rounding of exact arithmetic"})
    errs = [(dict(prices={"HESTON": 1.0}, reference_model="HESTON"), "E_INPUT", "one model"),
            (dict(prices={"HESTON": 1.0, "LOCAL_VOL": 1.1}, reference_model="SLV"), "E_INPUT", "reference model not in prices"),
            (dict(prices={}, reference_model="SLV"), "E_INPUT", "no prices")]
    for inp, code, d in errs:
        s.add(OP, inp, error=code, cls="date_and_convention", tags=["invalid", "q9", "synthetic"], description=d)
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_g"
    s.write()
    common.GOLDEN = keep


if __name__ == "__main__":
    main()
