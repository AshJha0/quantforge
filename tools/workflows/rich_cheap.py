#!/usr/bin/env python3
"""Workflow (b), plan 11.2.7: Treasury and gilt rich/cheap screen against the fitted curve. SCAFFOLD.

  python tools/workflows/rich_cheap.py [--impl rust] [--out reports/workflows] [--data DIR]

Status: waits on (1) the R2 spec on branch r2, which defines the screen, and (2) a licensed source of bond
prices. Until both land, this writes a dated report saying so and exits 0, so the daily job stays green.

Intended pipeline, using operations that exist today:
  1. Bond prices per line (CUSIP or ISIN, coupon, maturity, clean price) for one date.
  2. bond.fit.nelson_siegel on those prices          -> fitted curve (betas)
  3. bond.price.from_curve per bond on the fitted curve -> model price
  4. bond.yield.from_price on market and model prices -> yield spread, in bp: positive is cheap, negative is rich
  5. Report: lines sorted by spread, with the fit residuals and a sanity band on the fit.
Every result is labelled "signal on a fitted curve; tradability not established" (plan 11.1.3).

Candidate sources (terms NOT yet checked; check each before enabling, and record it in tools/recorder/sources.json):
  - US: TreasuryDirect FedInvest end-of-day security prices (treasurydirect.gov, "Price of Securities"), a US
    government publication.
  - UK: UK DMO daily gilt reference prices (dmo.gov.uk, "Gilt reference prices"). Check its reuse terms;
    some DMO price data is published with restrictions.
Par and fitted yields (Treasury par curve, BoE fitted curves) are not usable here: they carry no per-bond prices.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402

LABEL = "Signal on a fitted curve; tradability not established."
PENDING = [
    "R2 spec for the screen (branch r2): definitions of the spread, the bond universe and exclusions (e.g. on-the-run, short stubs)",
    "Licensed bond price source for US Treasuries (candidate: TreasuryDirect FedInvest prices), terms check",
    "Licensed bond price source for gilts (candidate: DMO gilt reference prices), terms check",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", default="python")
    ap.add_argument("--out", default=str(c.ROOT / "reports" / "workflows"))
    ap.add_argument("--data")
    a = ap.parse_args()
    import datetime as dt
    r = c.Report("Rich cheap", dt.date.today().isoformat(), a.out)
    r.h("Status")
    r.p(f"Scaffold only: no screen is computed yet. {LABEL}")
    r.table(["Waiting on", "State"], [(p, "open") for p in PENDING])
    r.check("screen implemented", "warn", False, "waits on the R2 spec and a licensed price source")
    return r.write([])


if __name__ == "__main__":
    sys.exit(main())
