# Calendar provenance

Version 1.0.0, 2026-11-07. Plan 11.2.3. Normative for `calendars.md`.

The rules in `calendars.md` run from 2000 to 2099, but a rule is only as good as its official source. A government can add a one-off holiday at any time. So each calendar names its source, the date the source was last read, and the last date the source confirms. The data is in `datasets/calendar_provenance.json`.

| Calendar | Official source | Checked | Confirmed through | Note |
|---|---|---|---|---|
| `GBLO` | UK Government, England and Wales bank holidays, `gov.uk/bank-holidays.json` | 2026-11-07 | 2028-12-31 | No one-offs 2026 to 2028 for England and Wales (2026-06-15 is Scotland only) |
| `EUTA` | ECB, T2 closing days | 2026-11-07 | standing rule (2099) | Read through a page summary, not verbatim; recheck the wording at the next refresh |
| `USGS` | SIFMA US fixed income holiday recommendations, 17 Dec 2025 release | 2026-11-07 | 2027-01-01 | **Fails the 12-month test now.** SIFMA usually publishes the next year in December. Good Fridays with a SIFMA early close (2007, 2010, 2012, 2015, 2021, 2023, 2026) are business days, each with its SIFMA source in the JSON (ruling R1-6) |

## Test

`python oracle/python/check_calendar_provenance.py` fails when a calendar's confirmed coverage ends within 12 months of today, or when a source was last read more than a year ago. `--today` sets the date, for tests. On 2026-11-07 it fails on `USGS`, as it should.

## Annual refresh

Each December, after SIFMA's release:
1. Read the three sources.
2. Update `datasets/calendar_provenance.json`.
3. If a source adds a one-off holiday, change `calendars.md` (a new spec version) and regenerate the goldens.
4. Run the test.
