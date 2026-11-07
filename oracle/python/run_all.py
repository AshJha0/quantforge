"""Regenerates every golden file and oracle/REPORT.md. Needs JDK 25 and a compiled oracle/strata."""
import check_fragility
import check_invariants
import gen_data
import gen_exercises
import gen_dates
import gen_limits
import gen_numerics
import gen_rulings_store
import gen_random
import gen_stage_b
import gen_stage_b_deep
import gen_stage_c
import gen_stage_d
import gen_stage_d_w2
import gen_stage_d_xccy
import gen_stage_d_credit
import gen_stage_d_equity
import gen_stage_d_w3
import gen_stage_d_vol
import gen_stats_engines
from qf_oracle.common import REPORT, ROOT

for g in (gen_dates, gen_random, gen_numerics, gen_stats_engines, gen_data, gen_rulings_store, gen_limits, gen_stage_b, gen_stage_b_deep, gen_stage_c, gen_stage_d, gen_stage_d_w2, gen_stage_d_xccy, gen_stage_d_credit, gen_stage_d_equity, gen_stage_d_w3, gen_stage_d_vol, gen_exercises):
    g.main()
check_invariants.main()
check_fragility.main()
head = ["# Oracle run report", "", "Written by `oracle/python/run_all.py`. Every line comes from that run.", "", "```"]
(ROOT / "oracle" / "REPORT.md").write_text("\n".join(head + [r[:300] for r in REPORT] + ["```", ""]), encoding="utf-8", newline="\n")
