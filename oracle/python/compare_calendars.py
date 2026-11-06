"""Three-way holiday comparison: the rules in calendars.md, QuantLib, Strata. Prints differences."""
from datetime import date, timedelta
from pathlib import Path

import QuantLib as ql

from qf_oracle.dates import is_business

out = Path(__file__).parent.parent / "strata" / "out"
qlc = {"GBLO": ql.UnitedKingdom(ql.UnitedKingdom.Settlement),
       "USGS": ql.UnitedStates(ql.UnitedStates.GovernmentBond), "EUTA": ql.TARGET()}
for c, q in qlc.items():
    st = {date.fromisoformat(x) for x in (out / f"holidays-{c}.txt").read_text().split()}
    d, diffs = date(2000, 1, 1), []
    while d.year <= 2050:
        if d.weekday() < 5:
            me, qh, sh = not is_business(c, d), q.isHoliday(ql.Date(d.day, d.month, d.year)), d in st
            if not (me == qh == sh):
                diffs.append(f"{d} {d:%a} spec={int(me)} quantlib={int(qh)} strata={int(sh)}")
        d += timedelta(1)
    print(c, "differences:", len(diffs))
    for x in diffs:
        print("  ", x)
