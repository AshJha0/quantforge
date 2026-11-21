# Stage K item K-8b (xVA extras and AAD xVA sensitivities): outside-check gate per item (plan section 15)

Written 2026-11-19 by the K-8b xVA spec lane, before any implementation or ORE run (reading and writing only; scratch arithmetic under 20 seconds, no WSL). Rule (plan 15): every item needs a source actually read, an acceptance test fixed before the run, and outside checks on at least 60% of its value cases, or it moves to a point release. Sources: `program/STAGE_K_SOURCES_XVA.md`. Rulings: `specifications/stage-k-rulings-xva.md` KR-160 to KR-176 (PROPOSED). Specs: `specifications/06-risk/xva-*.md` named below. This file counts the third condition as strictly as `STAGE_K_W2_GATE.md` did.

## 1. How a case is counted (KR-173)

- **P**: expected output printed in a read source (page cited).
- **L**: an independent library computes the expected output on a **different formulation** (quadrature of the defining integral, a finite-difference PDE), values measured 2026-11-19 in a scratch folder and quoted in the spec. A library routine evaluating the same closed form does not count (D6). For a Monte Carlo golden the L value is the reference the estimate must fall within `3 stderr` of; the case counts only after the build's estimate passes.
- **O**: ORE 1.8.17.0 runs its own implementation of the same quantity on inputs we generate, tolerance registered in the spec before any run (KR-174). **Planned, not run**: no O case is counted below as done.
- **O-approx**: ORE runs an approximation of our quantity (regression DIM, AMC) or a different model. Reported, never counted.
- **B**: DR-H2 blind re-derivation (`program/STAGE_H_BLIND_LANE.md`). **No B is claimed: no blind lane has run.** Shown as candidates.
- Our own bump reference (AAD) and our own second implementation count as none.

## 2. Gate table

**Update 2026-11-20 (blind v2, `program/STAGE_K_BLIND_XVA.md` "Version 2"):** the DR-H2 blind lane matched all 41 B candidates (41 of 41, measured). Once implemented with those marks: AAD 8 of 12, ColVA 6 of 10, stressed 6 of 8, MPoR 12 of 14, funding 6 of 10, WWR 10 of 10 meet 60%; **MVA 5 of 10 and the shock library 2 of 6 do not** and still need ORE runs under WSL. The table below is the 2026-11-19 state, kept as written.

| Item | Spec | Value cases | P | L (measured) | Strict now | O planned | O-approx | B candidates | Needed for 60% | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| AAD xVA sensitivities | `xva-aad-sensitivities.md` | 12 | 0 | 0 | 0% | 5 (aadx 0008-0012) | 0 | 8 (0001-0008) | 8 | **Moves to a point release unless** a DR-H2 blind lane matches all 8 B candidates (8/12 = 67%), or the 5 ORE bump-and-revalue cases pass and the blind lane matches at least 3 of aadx 0001-0007 |
| ColVA | `xva-colva.md` | 10 | 0 | 0 | 0% | 4 | 0 | 6 | 6 | **Moves to a point release unless** the blind lane matches all 6 B candidates, or 4 O pass and 2 B match |
| MVA from projected IM | `xva-mva-im.md` | 10 | 0 | 0 | 0% | 2 (Flat DIM) | 3 (regression DIM) | 5 | 6 | **Moves to a point release unless** the blind lane matches all 5 B candidates **and** at least 1 ORE Flat case passes (B alone gives 50%) |
| WWR, Gaussian copula | `xva-wwr-copula.md` | 10 | 0 | 9 | **90%** | 0 (different model) | 0 | 1 | 6 | **Can meet 60%** on measured SciPy `dblquad` checks (9 of 10), subject to the coordinator accepting the D6 reading in section 3 |
| Stressed exposure | `xva-stressed-exposure.md` | 8 | 0 | 0 | 0% | 2 (precondition unread) | 0 | 6 | 5 | **Moves to a point release unless** the blind lane matches at least 5 of the 6 B candidates |
| MPoR with VM and IM | `xva-mpor-closeout.md` | 13 | 0 | 5 | 38% | 2 | 0 | 7 | 8 | **Moves to a point release unless** the blind lane matches at least 3 of the 7 B candidates (5 + 3 = 8 of 13 = 62%), or 2 O pass and 1 B matches |
| Asymmetric funding curves | `xva-funding-asymmetric.md` | 10 | 0 | 0 | 0% | 4 | 0 | 6 | 6 | **Moves to a point release unless** the blind lane matches all 6 B candidates, or 4 O pass and 2 B match |
| LSMC / AMC | `xva-amc-lsmc.md` | 10 | 1 | 6 (references) | 10% now; 70% if all six pass | 0 | 3 (amc 0001-0003) | 0 | 6 | **Can meet 60%** if the printed case passes and at least 5 of the 6 QuantLib comparisons pass at `3 stderr` (6 of 10); the AMC exposure operation has no strict check and moves to a point release |
| xVA under the shock library | `xva-stress-shocks.md` | 6 | 0 | 0 | 0% | 4 | 0 | 2 | 4 | **Moves to a point release unless** at least 2 ORE cases pass and both B candidates match (B alone gives 33%) |

Totals: 89 value cases; strict now (P plus measured L, LSMC counted only for its printed case) 1 + 5 + 9 = 15 (17%); with the six LSMC references 21 (24%). O planned 23; O-approx 6 (never counted); B candidates 41.

Plain reading: only **WWR** meets the floor tonight on evidence in hand, and **LSMC pricing** can meet it once built because its references are printed or computed by a different method. Everything else needs either the blind lane (AAD, ColVA, funding, stressed exposure, MPoR) or ORE runs under WSL (MVA, shock library). AAD, the one item the plan names with a fixed acceptance (AAD = bump to 1e-8), meets that acceptance by construction of the test but has no outside check without the blind lane.

Rule 14.10-3 (with and without added cases): every case above is new in K-8b; none was added to lift a share. The L cases of WWR and MPoR test distinct behaviour (signs and sizes of `rho`, mean shifts, two buckets; threshold, IM, deep tail) rather than repeats of one line.

## 3. Points for the coordinator to rule on

1. **WWR L under D6.** The goldens come from a closed form using the bivariate normal CDF; the L values come from `scipy.integrate.dblquad` of the defining integral with the bivariate density written out, which never calls `Phi_2` or the closed-form identity. I read D6 ("a library primitive computing the same quantity does not count") as excluding a library `Phi_2` call and admitting a quadrature of the definition, as R6-13's `library-primitive` class does ("numpy or scipy numerics on a different formulation"). If the coordinator reads D6 more strictly, WWR falls to 0 strict and moves to a point release unless the blind lane matches 6 of 10.
2. **MPoR L** has the same structure (SciPy `quad` of `E[max(m + sZ, 0)]` against the Bachelier closed form); same ruling applies.
3. **LSMC L** is a different method (finite-difference PDE against simulation) and is not in question; but the pass rule is `3 stderr` with no method allowance (A2 of the spec). [LS01]'s own differences on the chosen rows are 0.001 to 0.019 against standard errors of 0.007 to 0.012, so a miss is possible; it is recorded, not re-seeded.
4. **ORE's licence wording** in two specs ("Apache 2.0") conflicts with `license.txt` at the tag (Modified BSD) as read by the survey; for the docs lane.
5. **MVA rename dependency**: the `PLACEHOLDER_MODEL` method waits for the final operation id of the project's placeholder initial margin model (KR-160 TODO); no golden uses it.

## 4. ORE: per item, which analytic and whether the wheel exposes it

| Item | ORE analytic and flags | Inputs we generate | Tolerance (fixed in the spec) | Route (survey terms) | Wheel exposes it? |
|---|---|---|---|---|---|
| AAD | `xva` (CVA), run twice with bumped hazard / recovery, common seeds | G-42b sets, credit curve as hazard | reconstruct ORE quotient from cube to 1e-6; `max(3, z) SE` plus a registered truncation bound | stage G route | `xva` with CVA: **yes in practice** (stage G ran `npv`, `simulation`, `xva`), though CVA flags were N in G-42; CVA output unverified |
| ColVA | `xva` with `colva = Y` | G-42b sets with full-VM CSA, compounding spread 10 bp | cube reconstruction 1e-6; `max(3, z) SE`; fallback MPoR one step | stage G route | **unverified** |
| Funding | `xva` with `fva = Y`, `fvaBorrowingCurve`, `fvaLendingCurve` | G-42b sets, two spread curves on every grid date | cube reconstruction 1e-6; `max(3, z) SE` | stage G route | **unverified** |
| MPoR | `xva` with VM CSA, close-out grid, `MporMode StickyDate`, `NoLag`, `mporCashFlowMode NonePay` | two G-42b swaps, threshold 0, MTA 0, MPoR 2W | `max(3, z) SE`; sticky/actual chosen in the debug run | stage G route (VM, MPoR) | close-out grid **unverified** |
| MVA | `xva` with `dim = Y`, `mva = Y`, `dimModel Flat` (O) and `Regression` (O-approx) | G-42b sets, IM in collateral balances | `max(3, z) SE` (Flat); plus 3% (Regression, not counted) | needs a local run (heavy for Regression) | **unverified** |
| Stressed | `xva`, `BaselEEPE` column | one swap, two `sigma` | `max(3, z) SE` after the ORE definition is read | stage G route | column exists in shipped examples; definition **unread** |
| Shocks | `simulation` + `xva` on a shocked market (not `xvaStress`) | shocked curve via `build_case.py` | as G-42b means | stage G route | **yes in practice** (same analytics as G-42b) |
| LSMC / AMC | `simulation` + `xva` with `amc` engine, `McLgmSwaptionEngine` | three Bermudan swaptions, LGM `a = 0` | O-approx only | needs a local run (heavy) | **unverified** |
| WWR | none (different model) | none | none | no route | not needed |

**Can the PyPI wheel's `OREApp` run these analytics?** Not settled by reading. The PyPI page says only "Python bindings for the OREAnalytics library"; the ORE-SWIG README (master branch) says the bindings wrap "a limited number of wrapped classes ... to demonstrate the principle" and does not mention `OREApp`; the ORE examples chapter says `ore.py` "demonstrates the Python-wrapped version of the ORE application that is also used in the command line application", which suggests full analytic dispatch but is a statement about an example, not the wheel ([ORE-E], [PyPI], [SWIG], read 2026-11-19). The stage G runs prove `npv`, `simulation` and `xva` (exposure only, CVA/DVA/FVA flags N) work through `OREApp`. Verdict: **unverified, needs a 10-minute install-and-list test.**

The test, exactly (one WSL job; take the WSL lock; check `QUIET` first; about 10 minutes with 500 samples):

```bash
exec 9>~/qf-wsl.lock; flock 9
test -e /mnt/c/Work/Claude/qf-wt/_h4ci/QUIET && { echo "QUIET set: stop"; exit 1; }
R=/mnt/c/Work/Claude/qf-wt/k-xva-spec; W=$(mktemp -d)
uv venv --python 3.12 "$W/v"
uv pip install --python "$W/v/bin/python" --require-hashes -r "$R/oracle/ore/requirements-ore.txt"
"$W/v/bin/python" -I -c "import ORE; print([n for n in dir(ORE) if n.endswith(('App','Parameters','Analytic'))])" | tee "$W/names.txt"
cp -r "$R/oracle/ore/runb2" "$W/case"
cd "$W/case"
# 500 samples; turn on cva, fva, colva, dim (Flat), mva; keep everything else as G-42b
sed -i -e 's/<Samples>5000</<Samples>500</' Input/simulation.xml
python3 - <<'EOF'
import re
p = "ore.xml"; s = open(p).read()
for k, v in {"cva": "Y", "fva": "Y", "colva": "Y", "dim": "Y", "mva": "Y"}.items():
    s = re.sub(rf'(<Parameter name="{k}">)[^<]*(<)', rf"\g<1>{v}\g<2>", s)
s = s.replace('<Parameter name="outputPath">', '<Parameter name="dimModel">Flat</Parameter><Parameter name="outputPath">', 1)
s = re.sub(r'(name="outputPath">)[^<]*(<)', r"\1Output\2", s)
open(p, "w").write(s)
EOF
mkdir -p Output
"$W/v/bin/python" -I -c "import ORE; p = ORE.Parameters(); p.fromFile('ore.xml'); a = ORE.OREApp(p); a.run(); print('errors:', list(a.getErrors()))" | tee "$W/run.txt"
head -1 Output/xva.csv | tee "$W/xva_header.txt"
grep -i -E "not supported|unknown analytic|no.*engine|error" Output/log.txt | head -20 | tee "$W/log_errors.txt"
```

Pass criteria, fixed now: `errors: []`; `xva.csv` header contains `CVA`, `FBA`, `FCA`, `COLVA`, `MVA`; and the CVA, COLVA and MVA cells of the netting-set row are non-empty. Any FVA field needs the borrowing and lending curves; if `fva = Y` without them fails, rerun with `fva = N` and record that FVA's wheel support is still open. Not covered by this test (each needs its own short run before its O cases are registered): the close-out grid, `dimModel Regression`, the `amc` engine. Where `ore.xml` keeps the flags (the `xva` analytic block, as in `runb2/ore.xml`) and whether `dimModel` belongs in it was read from `ore.tex` but not checked against `runb2/ore.xml` line by line; the lane running the test adapts the two `sed`/Python edits to the file's actual parameter names and records the edit.

## 5. Hand cases for a blind lane

Every spec puts expected values only inside `<!-- strip:begin -->` ... `<!-- strip:end -->` blocks (sections "Worked examples", "Golden cases", "Acceptance") and lists inputs in a separate "Case inputs (kept for the blind packet)" table. A stripping script removes the marked blocks. Leak warnings, so the packet builder can check: (1) `program/STAGE_K_SOURCES_XVA.md` prints the LSMC printed-example values and the QuantLib references (finding 1 and 2): **exclude it from the packet**; (2) the L-method paragraphs after `strip:end` in `xva-wwr-copula.md`, `xva-mpor-closeout.md` and `xva-amc-lsmc.md` give only relative agreements, no case values, except `xva-amc-lsmc.md`'s note that the American value at the first row is 4.486, which is not an expected output; (3) `xva-aad-sensitivities.md` states the closed forms `d cva / d R = -cva / (1 - R)` and `d ee / d im = -Phi(m/s)` in its formal statement: those are rules, and the blind lane derives the numbers itself; (4) the closed-form hand parts asked for (ColVA on a deterministic profile: colva_k-0001 to 0003; FBA/FCA on a two-date profile: fva_k-0001, 0002; MPoR close-out for one normal factor: cln_k-0001 to 0005; Gaussian-copula wrong-way factor: wwr_k-0001 to 0005) have their arithmetic written out inside the strip blocks.

## 6. Recommended ordering

| Item | Recommendation | Reason |
|---|---|---|
| WWR, Gaussian copula | **v1.0.0** | 9 of 10 L measured tonight; small (one closed form); no ORE or margin-model dependency |
| LSMC pricing (`pricing.american.lsmc`) | **v1.0.0** | P (the [LS01] example, reproduced in scratch) plus six QuantLib PDE references measured tonight; moderate size; risk: the `3 stderr` rule may miss on one or two rows |
| AAD xVA sensitivities | **v1.0.0, with the blind lane** | plan-named acceptance; closed forms are small; the 8 B candidates alone meet 60%; ORE bump runs optional |
| MPoR with VM and IM | **v1.0.0, with the blind lane** | 5 L measured; 3 B needed from CRE53 rules a blind lane re-derives in minutes; ORE VM route exists |
| Asymmetric funding curves | **v1.0.0, with the blind lane** | a small extension of G-41; 6 B suffice; ORE `fva` on the stage G route as a second line |
| ColVA | **v1.0.0, with the blind lane** | small; 6 B suffice; ORE `colva` support unverified |
| Stressed exposure | **v1.0.0, with the blind lane** | small, CRE53 rules only; 5 of 6 B suffice; ORE `BaselEEPE` definition unread, so do not plan on O |
| MVA from projected IM | **point release (v1.0.1)** | needs both a blind lane and an ORE run under WSL (busy); the regression method has only an approximate check; the placeholder-model variant waits for the rename; keep `xva.adjustments.value`'s G-41 MVA as the v1.0.0 MVA |
| xVA under the shock library | **point release unless a WSL slot is granted** | needs at least 2 ORE runs (about 8 minutes each at stage G scale, one WSL job at a time); B alone is 33% |
| AMC exposure (`xva.exposure.amc`) | **point release** | no strict outside check; ORE AMC is O-approx and heavy; a deterministic lattice exposure reference must be specified first |

Everything above depends on one decision: **whether a DR-H2 blind lane runs over the 41 B candidates** (as for wave 2). Without it, only WWR and LSMC pricing can ship in v1.0.0 under the gate rule.
