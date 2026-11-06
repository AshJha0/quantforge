"""Regenerates every golden file and oracle/REPORT.md. Needs JDK 25 and a compiled oracle/strata."""
import check_invariants
import gen_data
import gen_dates
import gen_limits
import gen_numerics
import gen_rulings_store
import gen_random
import gen_stats_engines
from qf_oracle.common import REPORT, ROOT

for g in (gen_dates, gen_random, gen_numerics, gen_stats_engines, gen_data, gen_rulings_store, gen_limits):
    g.main()
check_invariants.main()
head = ["# Oracle run report", "", "Written by `oracle/python/run_all.py`. Every line comes from that run.", "", "```"]
(ROOT / "oracle" / "REPORT.md").write_text("\n".join(head + [r[:300] for r in REPORT] + ["```", ""]), encoding="utf-8", newline="\n")
