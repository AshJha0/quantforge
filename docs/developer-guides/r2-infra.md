# R2 infrastructure

Phase R2 (target v0.4.2). This builds on [r1-infra.md](r1-infra.md). Every job is standard-library Python in `tools/workflows/`, and every financial step is a `quantforge --batch` call.

| Piece | Tool | Runs | Spec |
|---|---|---|---|
| Calibration stability | `calib_stability.py` | Weekly (`calib-stability.yml`), before each tag | `03-calibration/stability.md` |
| Rich/cheap screen, workflow (b) | `rich_cheap.py` | Daily, in `daily-workflows.yml` | `04-pricing/workflow-b-rich-cheap.md` |
| P&L explain, spec harness | `pnl_explain.py` (from branch `r2`) | Wired in once a CLI implements `risk.pnl.explain` | `06-risk/pnl-explain.md` |
| Key-rate explain, interim | `keyrate_explain.py` | Daily, in `daily-workflows.yml` | Plan 11.2.1, using operations that exist today |
| Gallery pages | `tools/gallery_pnl.py`, `tools/gallery_r2.py` | `build_gallery.py` | — |
| Batch benchmarks | `benchmarks/batch_targets.py` | By hand | `benchmarks/targets.md` |

## Calibration stability

This covers seven calibrations, C1 to C7, under 200 seeded noise draws from `core.rng.normals` (seed 20261107, stream = calibration number), scored on metrics S1 to S7.

**First run, 2026-11-07, all four languages:** the gallery page is [calib-stability.md](../curves/calib-stability.md).

- **Agreement and determinism:** all four languages give identical figures. S1 and S2 pass everywhere.
- **Passing:** S3 noise amplification passes for every calibration, from 0.003 for C3 to 4.0 for C4. S6 is 1.00 for C5.
- **S7 fails for C3, C6 and C7:** a 3-to-5-parameter fit cannot reprice 7 to 9 independently perturbed points much better than the noise. The worst errors observed are 2.6e-3 per 100 (C3), 2.6e-4 in total variance (C6) and 2.8e-4 in vol (C7), against thresholds of 1e-6 to 1e-8. This needs a spec ruling.
- **C3 grid:** no operation evaluates a Nelson-Siegel curve from betas, so the tool evaluates the form stated in `curve-fits.md` on the grid. This is the one place a formula lives in the tool, and it is flagged in the code and on the page.
- **C6 noise:** the spec states the vol noise in vol points, but SVI takes total variance. The run uses 1e-4 in total variance.

## Rich/cheap: blocked on data

`rich_cheap.py` implements the whole spec: T+1 settlement, filters, the ex-dividend drop for gilts (E9), the Nelson-Siegel fit with `tau` 2.5, yield residuals in bp, a trailing 60-day z-score, buckets, ranks and marks. It never fetches, because both free sources refuse automated use (terms checked 2026-11-07):

- **TreasuryDirect FedInvest:** `robots.txt` says `User-agent: * / Disallow: /`. The terms allow non-commercial personal use only, and distribution needs Fiscal Service's written consent.
- **UK DMO gilt reference prices:** automated requests get an anti-bot challenge, so the terms could not be read by a script.

The daily run writes a BLOCKED report. With files a person has downloaded, `--data DIR` runs the screen (the layout is in the script's docstring), and reports show residuals and ranks only. Unblocking needs one of two things: Fiscal Service's written consent or a cleared API, or a person reading the DMO terms in a browser and recording them.

## P&L explain

Branch `r2` brought the spec-owned harness `pnl_explain.py`, which calls `risk.pnl.explain`. That operation is not implemented in any CLI yet. Until it is, the daily job runs `keyrate_explain.py` instead. It computes full revaluation (`rates.ois.pv`) against key-rate DV01 times the quote move (`risk.ois.dv01`), over 20 real Treasury moves and a 20-swap seeded book, with provisional thresholds in `keyrate_explain.json`. On the gallery snapshot, unexplained P&L is 0.2% to 1.7% of full P&L, and the four languages agree to 4e-7 USD.

**Switch-over:** replace the `keyrate_explain.py` step in `daily-workflows.yml` with `pnl_explain.py` once the r2-lang branches have merged. Keep the gallery page or move it to the spec harness's output.

## Batch benchmarks

`benchmarks/batch_targets.py` measures T1 to T5 from `benchmarks/targets.md`, through `--batch`. Results are in that file and in `benchmarks/results/`. On the owner's laptop:

- Rust and C++ are measured inside WSL, pinned to one core, because Windows blocks fresh native executables.
- Java and Python are measured on Windows, not pinned.
- T1's p99 inside WSL is dominated by VM scheduling jitter, about 16 ms, while the median gap is 0.5 to 0.9 ms. Rerun on a native Linux runner for a clean p99.

## WSL builds for local four-language runs

```bash
wsl -d Ubuntu -- bash -lc 'cd /mnt/c/Work/Claude/qf-wt/infra-r1 && cmake -S cpp26 -B ~/qf-build/cpp -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCMAKE_CXX_COMPILER=g++-15 && cmake --build ~/qf-build/cpp -j3 && CARGO_TARGET_DIR=~/qf-build/rust cargo build --release -j3 -p quantforge-cli --manifest-path rust/Cargo.toml'
```

- **Build under `~`, not `/tmp`:** on Ubuntu 26.04, `/tmp` is cleared when the idle VM stops.
- **Point the tools at those builds:** set `QF_IMPLEMENTATIONS` to a JSON file whose `cpp` and `rust` commands are `["wsl", "-d", "Ubuntu", "--", "/home/<user>/qf-build/..."]`. Both `tools/workflows/common.py` and `tools/build_gallery.py` read it.
