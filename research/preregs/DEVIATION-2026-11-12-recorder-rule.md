# Deviation note: the recorder keeps writing holdout-window SOFR checks daily

Status: follow-up to `DEVIATION-2026-11-12.md`, which is signed and hash-pinned by the three R3 amendments 2 and so is not edited. This note is not a prereg.

Date: 2026-11-12.

## What happens

The daily recorder on `forward-log` writes `reports/<date>/sofr-check.json` and `reports/<date>/sofr-check.md` every business day. Each publishes the NY Fed 30, 90 and 180-day SOFR averages. The 180-day window of a report dated `d` starts about 180 calendar days before `d`, so it starts inside the R3-02 holdout (ends 2026-10-30) for every report dated up to 2027-04-28. `DEVIATION-2026-11-12.md` lists the reports of 2026-11-06, -09 and -10 one by one; a per-file list would break each day, so the later ones are covered by the rule below instead.

As before, nobody computes a study statistic, signal or position from these files. They are general market levels of the kind already disclosed under "Holdout knowledge".

## Rule (machine-checked)

`research/test_preregs.py` accepts a holdout-scan hit at `forward-log:reports/<date>/sofr-check.json` or `.md` only when `<date>` lies in the range of a rule line below. Any other unlisted holdout observation still fails the test.

- rule `forward-log:reports/*/sofr-check.json` | R3-02 | H | 2026-11-11 to 2027-04-30
- rule `forward-log:reports/*/sofr-check.md` | R3-02 | H | 2026-11-11 to 2027-04-30
