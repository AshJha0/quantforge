# Stage K audit C: response to KA-C18 (printed figures and the D6 counting rule), KA-C20, KA-C23

Written 2026-11-19 by the shares and gates lane (Claude Opus 5.5, branch `k-audit-shares`, off `origin/k-r1` at `0b5ca451`). Reading, writing and light Python only. Audit: `institutional-quant-engine-plan/STAGE_K_R1_AUDIT_C.md` (auditor Claude Fable 5.2). Every finding below was checked against the files before it was accepted.

## Part 1. KA-C18: does a printed regulator figure count on its own?

### Plain idea

A case counts as outside-checked only if something outside the project checked every output the golden compares, at the golden's tolerance. A Basel worked example prints a few rounded numbers (EAD 569, 8.11%). It shows we read the source the same way the Committee did. It does not check the other outputs, and it checks the printed ones only to the printed digits. The question is whether the rule, as written and as applied in earlier stages, nevertheless counts such a case. It does not.

### The rule text (evidence class: read, 2026-11-19)

- D6, plan `QUANTFORGE_PLAN.md` row R6-13: "Outside-check rule (D6): evidence classes `library-object`, `library-primitive` ..., `reimplementation` (does not count), `none`. A case counts only if every compared output is checked." The third owner decision of 2026-11-12 adds `independent-rederivation`: "agreement is judged at the golden's own tolerance".
- `tools/outside_shares.py` docstring: "A case counts towards the outside share only as `library-object` or `library-primitive`, and only if every compared output of the case is checked: ... `none`: no outside check, or a published worked example only (does not count)."
- `oracle/OUTSIDE_SHARES.md` header (generated): "A case counts only ... if every compared output is checked."
- `docs/validation/status-ladder.md`:24: "A formula written again around a library call (`reimplementation`) and a published worked example alone (`none`, under D6 for stages D to J) do not count."
- Stage K's own ruling KR-11 as carried into the tool: a case counts "only where every compared output was checked blind at the golden's tolerance"; idr_k cases blind-checked "only to 6 decimals" do not count.

Older text that pointed the other way, superseded: stage F ruling F-23 (`specifications/stage-f-rulings.md`:42, before D6) said a methodology owner's published worked example "counts as outside when every compared output matches its printed digits". D6 (2026-11-12) replaced it, and the tool applies D6, not F-23 (precedent 1 below). Wave 2 ruling KR-68 (P) ("its expected output is a number printed in a read source") is in a file still marked PROPOSED, covers the wave 2 gate only, and nothing of wave 2 is counted in `OUTSIDE_SHARES.md`; it is not a precedent for wave 1b.

### Precedent, every earlier stage that has a published example (read, 2026-11-19)

| Stage | Register | Published-example cases | How counted |
|---|---|---|---|
| D | `oracle/outside_register.json` | none: every entry names a library | not applicable |
| E | `oracle/outside_register_e_a.json`, `_e_b.json` | none with a published source; but `partly_outside_not_counted` (surf_e-0001..0004, outputs `arbitrage_free`, `wing_violations` self-checked; creditopt_e-0147..0150) | a case with any compared output not outside-checked is not counted |
| F | `oracle/outside_register_f.json` | vix_f-0001, 0002, 0003, source "Cboe Volatility Index Methodology v6.0, Appendix 3", no library | `none` (`classify_case_register`: `library is None` gives `none`); `vol.vix.term_variance` and `vol.vix.index` show 0% in `OUTSIDE_SHARES.md` |
| G, I, J | suite registers, `OUTSIDE_G_R6.json`, `OUTSIDE_J.json` | none counted from a published example; J-C-9 and J-W2-16 record "no free published worked example" | not applicable |
| H | per-case `verified_by`, `load_stage_h` | as_h-0005, 0006, 0007 ("[AS08] printed average spread 1.49 (extra check 0.005)"), ac_h-0005 ("[AC00] p. 24 printed: kappa about 0.6/day (extra check 0.05)"), ob_h-0001 ("outside: [KR-CRC] printed checksum") | the four AS/AC cases count only through their line "blind re-derivation DR-H2 2026-11-15 ...: MATCH", judged at `simple_analytic` on every output; the printed figure is labelled "extra check" at print precision. ob_h-0001 has a printed figure and no DR-H2 line and is not counted |

Three concrete precedents, one line each:
1. vix_f-0001..0003 (stage F): a methodology owner's printed worked example, the case F-23 had named, is classed `none` under D6 and not counted.
2. as_h-0005..0007 and ac_h-0005 (stage H): printed paper figures are recorded as an extra check at print precision; the case counts because a blind lane matched every output at the golden's tolerance.
3. ob_h-0001 (stage H): a printed figure with no blind match is not counted.

`STAGE_H_START.md`:58 describes the four stage H cases as "printed paper figures (4)" in a narrative count; the tool never counted them on that basis, and their goldens carry the blind MATCH. The 2026-11-19 wave 1b integration comment in `outside_shares.py` ("as stage H counts printed paper figures") rested on that narrative line, not on how stage H was counted.

### Verdict: (b)

The rule as written and as applied excludes the 28 cases. The text (D6, the tool's docstring, KR-11) requires every compared output to be checked at the golden's tolerance and names "a published worked example only" as `none`. No earlier stage counted a printed figure on its own: stage F classed the Cboe example `none`, stage H counted printed-figure cases only through a blind match, and stage E refused cases with any output not outside-checked. The `published:` branch added to `load_stage_k` at integration is an unwritten exception. Ruling KR-210 (below) removes it.

### The 28 cases checked one by one against reading (a), for completeness

Reading (a) would need: the golden reproduces every printed figure of the example to its printed digits, and every compared output has a printed counterpart recorded in `verified_by`. Checked against the goldens, the generator `oracle/python/gen_stage_k_w1b.py` (`published_intermediates`, `gen_backtest`, `gen_traffic_light`) and the CRE99 / MAR99 pages (`basel-framework-full.pdf` pp.524-540, 758; text extracted and read 2026-11-19; formula images not extractable).

| Cases | Compared outputs | Printed counterpart | Under (a) |
|---|---|---|---|
| saccr_k-0001 to 0004 | `ead`, `rc`, `pfe`, `multiplier`, `addon_aggregate`, `addon` (5 classes), `v`, `c`, `margined`, `mpor_days`, `ead_unmargined`, `capped`, per hedging set `addon`, per trade `supervisory_duration`, `adjusted_notional`, `maturity_factor`, `delta`, `effective_notional`, `supervisory_factor` | EAD (all four), and in the generator: d, SD, swaption delta, D, hedging-set add-ons, AddOn, RC for Examples 1 to 3; Example 4 only RC 40 and AddOn 629. `verified_by` records the EAD only. `pfe` is printed nowhere as a number in the extracted text; `ead_unmargined` (null) and `capped` (false) are outputs of our KR-37 cap, which CRE99 does not compute | fail as recorded: `verified_by` names one output of about 30 compared. Example 4 prints no per-trade or hedging-set figure of its own |
| saccr_k-0005 | as above; `ead_unmargined` 5,779.72, `capped` false, `mpor_days` 14 | EAD 1,879, V 80, RC 0, MPOR 14, D per trade, add-ons, multiplier 0.958; the printed D of the Brent forward (-7,100) differs from the golden (-7,099.30) by a source rounding (KR-31), so not every printed figure is reproduced at its printed digits | fail: `ead_unmargined` has no printed counterpart, and one printed intermediate does not match at its digits |
| btk_k-0001 to 0011 | `exceptions`, `cumulative_probability`, `zone`, `amber_from`, `red_from`, `multiplier` | MAR99 Table 2: cumulative probability to 2 decimals of a percent, zone, number of exceptions; multiplier and zone bands in MAR32 Table 1. The generator's `check()` tests probability and zone only; the multiplier is tested in `python/tests/test_stage_k_w1b.py`:440 against the transcribed table, yet `verified_by` says "multiplier: MATCH" | every output has a printed counterpart, but `cumulative_probability` only to about 5e-5 absolute against a golden tolerance of 1e-12 + 1e-10 relative: would meet (a) if (a) were the rule; does not meet the rule as written |
| btk_k-0012 | as above, 12 exceptions | Table 2 stops at "10 or more": zone RED and multiplier 2.00 only; no printed probability | fail under either reading (the auditor is right) |
| tlk_k-0001 to 0011 | `cumulative_probability`, `zone`, `plus_factor` | probability and zone from MAR99 Table 2; `plus_factor` is the 1996 table, compared by the golden, and no `verified_by` line records it against a printed source (the spec says it "is not compared", but the golden compares it) | fail: `plus_factor` has no recorded printed check |

So even under (a) at most 11 of the 28 (btk_k-0001 to 0011) would count. Under (b), none count.

### Shares both ways (measured with the tool, 2026-11-19, local laptop)

`python tools/outside_shares.py` (rule as written, KR-210) and `python tools/outside_shares.py --count-printed` (withdrawn reading, print only, writes nothing):

| Item | Value cases | Rule as written (b) | Printed figure counted (withdrawn) |
|---|---:|---:|---:|
| Stage K | 87 | 50 (57.5%) NOT MET | 78 (89.7%) |
| K-8d SA-CCR `saccr_k` | 16 | 7 (43.8%) NOT MET | 12 (75.0%) |
| K-8e backtesting `btk_k` | 24 | 11 (45.8%) NOT MET | 23 (95.8%) |
| F (existing traffic_light) `tlk_k` | 11 | 0 (0.0%) NOT MET | 11 (100%) |
| K-4a, K-4b, K-4c, K-5a, K-8, K-8 guard | 36 | 32, unchanged | 32 |

The auditor's figures (50 of 87, 7 of 16, 11 of 24) are confirmed. Consequence: `tools/outside_shares.py --check` now exits 1 on "stage K: 57.5% ... under the 60% floor". That is the true state; it is not relaxed. It turns green only if the blind packet of Part 2 matches enough cases (record `program/STAGE_K_BLIND_PUB.md`).

### Changes on this branch

- `tools/outside_shares.py`: the `published:` branch of `load_stage_k` counts only under `--count-printed` (print only); the comment and the generated stage K paragraph state KR-210. `tools/test_outside_shares.py`: planted test 6 (a printed-only case is not counted; the switch is live).
- Regenerated: `oracle/OUTSIDE_SHARES.json`, `oracle/OUTSIDE_SHARES.md`, `docs/validation/status-ladder.md` (generated tables).
- Ruling KR-210 in `specifications/stage-k-rulings-audit-c.md`.

### Wording other lanes must change (not touched here)

README status block and headline facts (`tools/site_facts.json`), `docs/releases/v0.10.1.md`:23-24 and :73, `CHANGELOG.md` K-8d/K-8e bullets, `LEARN.md`:942 ("Every round 1 item meets the 60% outside-check rule"), `ROADMAP.md`:42, `docs/model-inventory.md`:1281, :1293, `specifications/06-risk/sa-ccr.md`:83, `specifications/06-risk/frtb-ima-backtest.md`:49 and :60, tutorials 56 (:111-112) and 57 (:92), `docs/question-bank/14-stage-k-risk-platform.md`:289 and its check `docs/question-bank/verify/v14_stage_k.py`:164 ("12 of 16 value cases, 75%"), `program/STAGE_K_BLIND_W1B.md`:31 and `STAGE_K_BLIND_BTK.md`:59, :81 (fixed here, Part 4). New figures: stage K 50 of 87 (57.5%), SA-CCR 7 of 16, backtesting 11 of 24, `tlk_k` 0 of 11, all under the floor until the PUB blind run; the printed figures stay as a stated check of the reading of the source, not counted. The generator's `verified_by` "multiplier: MATCH" for btk_k should cite the test that checks it (`gen_stage_k_w1b.py`:411 checks probability and zone only).

## Part 2, Part 3, Part 4

See `program/STAGE_K_BLIND_PUB.md` (packet), the KR-211 onward rulings in `specifications/stage-k-rulings-audit-c.md` (E1 gate) and the Part 4 notes below.

## Part 3. KA-C20 against the gate as it stands (`fc52df3a`, KR-112)

Self-tests (a) to (d) and F-2a were green at `0b5ca451`; the gate reported 336 of 368, 32 exempt, 0 problems. The three gaps the auditor lists, checked against that code:

| Gap | Still open at `0b5ca451`? | Planted-fault test | Tightening on this branch |
|---|---|---|---|
| (1) any Real in any `E_SCHEMA` golden of an exempt operation is ignored | yes: a golden `{"n": 250, "rate": 0.25}` expecting `E_SCHEMA` passes (measured with the `origin/k-r1` copy of the gate) | `KR-211` block in `--self-test` | KR-211: the Real must sit at an integer path of the value goldens |
| (2) `has_real` sees JSON floats only | yes | pinned as a known blind spot in `--self-test` (the planted case passes) | not closed: needs typed inputs in the name map (outside the two files this lane may touch) |
| (3) "a non-finite token is E_SCHEMA" asserted, not pinned | yes: no golden sends a non-finite token to `.zone` or `.desk` (checked: btk_k-0025 to 0034) | `KR-212` block in `--self-test` | KR-212: an exemption that uses the allowance or states the premise needs a non-finite `E_SCHEMA` golden at an integer path |

The (a) to (d) fixtures gained one golden each (the non-finite `E_SCHEMA` case for the integer operation) because KR-212 now requires it; each still tests what it tested. Self-test passes. **The gate is red on the real tree** (`python tools/check_e1_coverage.py`: 2 problems): `risk.frtb.backtest.zone` and `risk.frtb.backtest.desk`. That is a finding, not relaxed; the fix is one golden per operation in `btk_k` (generator `oracle/python/gen_stage_k_w1b.py`), run in all four builds. For information: 26 of the 32 exempt operations have no non-finite golden of any kind; KR-212 does not demand one of them because their exemption rests on "no Real input", not on the `E_SCHEMA` premise.

## Part 4. KA-C23, the blind-lane records

Checked each claim: right in every point but one. Fixed in the records only:
- `STAGE_K_BLIND_W1.md`: the blind lane's model is not named in the record, in `stage_k_blind/w1_blind/notes.md`, or in any commit read (e761b3b2 is the coordinator's commit), so I cannot name it from evidence; the record now says so instead of "a different model". **Disagreement with the auditor on this one point:** the fix asked for (name the W1 model) is not possible from the files; the coordinator should add it if known. Added the standard paragraph (own statement, not logged; what a match shows and does not; not independent or human review).
- `STAGE_K_BLIND_W1B.md`: the no-read sentence is now the deriver's own statement, with the unstripped-spec read cross-referenced; the standard paragraph added; a dated KR-210 note under the share (K-8d 7 of 16 until the PUB run).
- `STAGE_K_BLIND_BTK.md`: stale status and the empty "Results: Not run" block removed; standard paragraph added; dated KR-210 note (K-8e 11 of 24).
- `STAGE_K_BLIND_K8.md`, `STAGE_K_BLIND_W2.md`: stale status and "Not run" blocks removed. `STAGE_K_BLIND_K5A.md` had neither and is unchanged.
