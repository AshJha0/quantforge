# Stage E handover

From the two stage E spec sessions to the four language sessions. Append-only: spec A writes under "Spec A slices", spec B under "Spec B slices". Each slice section says what a language session may read. Never read anything under `oracle/`: that is the oracle, and reading it breaks the clean room.

All stage E goldens are in `datasets/golden/stage_e/`, run through `conformance/runner/runner.py` (it finds them by suite name). Always read `specifications/cli-contract.md` and `specifications/stage-e-rulings.md` (spec A) with any spec A slice.

## Spec A slices

### E1 arbitrage-free surfaces (ready, 2026-11-08)

New operations: `vol.svi.surface_check`, `vol.ssvi.to_svi`, `vol.svi.fit_surface`, `vol.local.dupire`, `vol.forward.vol`, `vol.smile.dynamics`, `vol.volofvol.measure`. No new error code; `E_ARBITRAGE` gains uses (cli-contract, stage E spec A block).

Goldens: `datasets/golden/stage_e/surf_e.json` (28 cases), `datasets/golden/stage_e/lv_e.json` (39 cases).

Read:
- `specifications/cli-contract.md` (block "Stage E, spec A")
- `specifications/stage-e-rulings.md` (E-A1 to E-A8)
- `specifications/05-volatility/smile-and-surface.md` (stage C SVI, SSVI, `g`: E1 builds on it)
- `specifications/05-volatility/arb-free-surfaces.md`
- `specifications/05-volatility/local-and-forward-vol.md`
- `specifications/05-volatility/stage-e-targets-a.md` (E1 table)
- `specifications/edge-case-register.md` (rows EA1 to EA6)

Notes for builds: `vol.svi.fit_surface` is judged on parameters within 1e-6 from exact quotes, so any proven least-squares solver with several starts works; `vol.svi.surface_check` lists are exact, and the goldens keep every compared quantity well away from its threshold.
