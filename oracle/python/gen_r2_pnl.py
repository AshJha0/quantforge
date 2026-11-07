"""R2: P&L explain goldens. Suite r2/pnl_r2. Spec: specifications/06-risk/pnl-explain.md.

Values and par buckets come from the same own replay as gen_r2_risk.py and are re-priced in QuantLib. The run stops if any
case's unexplained P&L lies within 10% of its threshold, so the boolean `explained` is robust to solve noise.
"""
from qf_oracle import common
from qf_oracle.common import Suite, note
import gen_r2_risk as R
import gen_stage_d as D

G = "oracle/python/gen_r2_pnl.py"
BP = 1e-4


def moves(n):
    """Synthetic quote moves in decimal, one per quote of n."""
    lin = lambda a, b: [a + (b - a) * j / (n - 1) for j in range(n)]  # noqa: E731
    return [("parallel +1bp", [BP] * n), ("parallel -10bp", [-10 * BP] * n), ("steepener -5/+15bp", [x * BP for x in lin(-5, 15)]),
            ("flattener +20/-10bp", [x * BP for x in lin(20, -10)]), ("shock +150bp", [150 * BP] * n), ("belly +8bp", [8 * BP if 6 <= j <= 9 else 0.0 for j in range(n)])]


def main():
    D.estr()
    s = Suite("pnl_r2", "specifications/06-risk/pnl-explain.md", G)
    worst = 0.0
    lim = lambda N: {"absolute": 1e-8 * N, "relative": 1e-7, "reason": "difference of curve solves; solves stop below 1e-13 in rate"}  # noqa: E731
    for conv, prod, N in R.products():
        q0 = R.QUOTES[conv]
        cv0 = R.build(conv, q0)[0]
        v0 = R.value(prod, cv0)
        bk = [R.diff(lambda sh, j=j: R.value(prod, R.build(conv, [(t, r + (sh if k == j else 0.0)) for k, (t, r) in enumerate(q0)])[0]), BP, "CENTRAL", 1.0)
              for j in range(len(q0))]
        _, _, qbk = R.ql_par(conv, q0, prod, 1.0, "CENTRAL")
        for a, b in zip(qbk, bk):
            R.close(a, b, 1e-8 * N + 1e-7 * abs(sum(bk)))
        dv01 = sum(bk)
        for name, mv in moves(len(q0)):
            q1 = [(t, r + m) for (t, r), m in zip(q0, mv)]
            v1 = R.value(prod, R.build(conv, q1)[0])
            crv, sq, _ = R.ql_curve(conv, q1)
            import QuantLib as ql
            R.close(R.ql_value(prod, ql.YieldTermStructureHandle(crv)), v1, 1e-8 * N)
            full = v1 - v0
            rp = sum(b * m / BP for b, m in zip(bk, mv))
            un = full - rp
            th = max(.05 * abs(full), .05 * abs(dv01))
            assert abs(abs(un) - th) > .1 * th, (prod, name, un, th)
            worst = max(worst, abs(un) / th)
            s.add("risk.pnl.explain", {"as_of": str(R.AS_OF), "convention": conv, "interpolation": "LOG_LINEAR_DF",
                                       "quotes_start": [{"tenor": t, "rate": r} for t, r in q0], "quotes_end": [{"tenor": t, "rate": r} for t, r in q1],
                                       "product": prod, "bump_bp": 1.0},
                  {"value_start": v0, "value_end": v1, "full_pnl": full, "par_buckets": bk, "risk_pnl": rp, "unexplained": un, "threshold": th, "explained": abs(un) <= th},
                  cls="interpolation", verified=["independent-replay", D.QLV], tags=["r2", "pnl-explain", prod["kind"].lower(), name.split()[0]],
                  output_classes={"explained": "date_and_convention"}, limit=lim(N), description=name)
    b = s.cases[0]["inputs"]
    s.add("risk.pnl.explain", {**b, "quotes_end": b["quotes_end"][:-1]}, error="E_INPUT", cls="date_and_convention", tags=["r2", "invalid"], description="tenors differ")
    s.add("risk.pnl.explain", {**b, "bump_bp": -1.0}, error="E_DOMAIN", cls="date_and_convention", tags=["r2", "invalid"])
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "r2"
    for c in s.cases:
        c["tags"].append("synthetic")
    s.write()
    common.GOLDEN = keep
    fails = sum(1 for c in s.cases if c["expected"].get("outputs", {}).get("explained") is False)
    note(f"pnl_r2: {len(s.cases)} cases, {fails} not explained (large moves on long products); largest |unexplained|/threshold {worst:.2f}; no case within 0.9-1.1")


if __name__ == "__main__":
    main()
