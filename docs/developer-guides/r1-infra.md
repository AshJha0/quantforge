# R1 infrastructure: scheduled jobs, real-data checks and a local Linux path

Plan sections 11.1.4, 11.1.5, 11.2.7, 11.2.8 and 11.5. None of these jobs runs on a pull request, so PR time is unchanged. They use only free standard runners on the public repository and the built-in `GITHUB_TOKEN`.

| Piece | Where | Schedule |
|---|---|---|
| Recorder and gap monitor | `.github/workflows/recorder.yml`, `tools/recorder/gap_monitor.py` | Weekdays 14:30 and 23:30 UTC. See [recorder-actions.md](recorder-actions.md) |
| Cross-platform conformance | `.github/workflows/cross-platform.yml` | Sunday 04:17 UTC, manual |
| Daily workflows (a) and (c) | `.github/workflows/daily-workflows.yml`, `tools/workflows/` | Weekdays 15:00 UTC, manual |
| Sanity bands | `tools/workflows/sanity_bands.json`, `tools/workflows/sanity.py` | In workflow (a) and the gallery |
| Real-data gallery page | `tools/gallery_real.py`, [docs/curves/real-usd-treasury.md](../curves/real-usd-treasury.md) | Refreshed by hand |
| Per-stage mutation report | `.github/workflows/mutation-stage.yml`, `conformance/mutation/stage_report.py`, `stages.json` | First of the month, manual |
| Batch performance targets | [benchmarks/targets.md](../../benchmarks/targets.md) | Written before measuring |

## Cross-platform conformance

The matrix covers `ubuntu-24.04`, `windows-2025` and `macos-15`, each against Java, C++, Python and Rust. That is 12 cells, and `fail-fast` is off, so one bad cell does not hide the others. Each cell builds its CLI, runs the neutral runner on `datasets/golden`, and uploads its report. A summary job lists the cells.

| Language | Linux | Windows | macOS |
|---|---|---|---|
| Java | Temurin 25.0.5 | same | same |
| C++ | GCC 16.2 container (as `cpp26.yml`) | MSYS2 UCRT GCC, latest pacman package | Homebrew GCC, newest `g++-N` |
| Python | uv, `uv.lock` | same | same |
| Rust | `rust-toolchain.toml` (1.99.1) | same | same |

The Windows and macOS C++ compilers are not pinned, because neither package manager keeps old versions. The job prints the version it used. A failure there could come from the compiler rather than the code, so check the printed version first. This job exists to catch platform bugs like the stage D static-initialisation crash before a release. Run it by hand (Actions, then "Run workflow") before tagging.

## Local Linux C++ path (WSL)

Windows Application Control blocks freshly built unsigned executables on the owner's PC, so local C++ checks need Linux. WSL 2 with Ubuntu is already installed and costs nothing. Ubuntu 26.04 ships GCC 15.2 and CMake 4.2. `cpp26/` builds with C++26 on GCC 15. CI uses GCC 16.2, so a GCC 15 pass is a strong signal, not proof.

```bash
wsl -d Ubuntu -- bash -lc 'cd /mnt/c/Work/Claude/qf-wt/infra-r1 && cmake -S cpp26 -B /tmp/qf-cpp-build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=g++-15 && cmake --build /tmp/qf-cpp-build -j3 && ctest --test-dir /tmp/qf-cpp-build -j3'
```

```bash
wsl -d Ubuntu -- bash -lc 'cd /mnt/c/Work/Claude/qf-wt/infra-r1 && echo "{\"cpp\":{\"command\":[\"/tmp/qf-cpp-build/quantforge\"],\"cwd\":\".\"}}" > /tmp/qf-impl.json && python3 conformance/runner/runner.py --impl cpp --config /tmp/qf-impl.json --report /tmp/qf-report'
```

Rules learned the hard way:

- **Keep the build directory on the Linux filesystem (`/tmp`).** Building inside `/mnt/c` is slow, and it leaves Linux binaries in the Windows tree.
- **Limit parallelism to `-j3`.** WSL gets about 7 GB here. An unbounded `--parallel` on 12 cores ran the VM out of memory and hung the WSL service for every session. Recovery needed `wsl --shutdown`.
- **No Docker or Podman is installed, and none is needed.** If GCC 16 itself is wanted locally, the zero-cost route is the CI container image under a rootless Podman inside WSL. That is not set up.

Measured result: see the "Local Linux run" note at the end of this page.

## Daily workflows (a) and (c)

Both are standard-library Python in `tools/workflows/`. All the finance happens in the CLI: `common.batch` sends every case to a single `quantforge batch` process. The batch verb is one constant, `BATCH_ARGS` in `common.py`. When the spec session's `--batch` contract lands in `specifications/cli-contract.md` (branch `r1`), change that line and nothing else.

Each run writes `reports/workflows/<as-of>/<name>.md`, plus a `.json` twin holding every number. CI pushes them to branch `forward-log` under `reports/`. Locally, `reports/workflows/` is ignored by git. A failed fail-level check fails the job after the report is pushed. Warnings are only reported.

**(a) EOD curves, `eod_curves.py`.**

- **USD.** The latest US Treasury par curve (13 tenors, 1M to 30Y) is bootstrapped with `rates.ois.bootstrap` under SOFR conventions. Bands are checked on the quotes, the SOFR fixing, the curve and the front end. Key-rate risk comes from `risk.ois.dv01`, run on a 50-trade seeded book from `sample_book.py`; fixed rates are par from `rates.ois.pv`, plus an offset. The report says plainly that this is a **proxy curve**: Treasury par yields are not SOFR swap rates, and free data has no SOFR swap quotes.
- **GBP.** Only the SONIA fixings are band-checked, and their values are withheld from the report. Raw SONIA may not be redistributed until the Bank of England answers (`tools/recorder/sources.json`). **No GBP curve is built.** No free GBP term source is licensed in `sources.json` yet. The candidate is the BoE OIS spot curve, after a licence check. This part of 11.2.7 (a) is open.

**(c) SOFR check, `sofr_check.py`.**

- **Averages.** For the last 5 publications it recomputes the NY Fed 30-, 90- and 180-day averages from published SOFR, and requires each to match within 1e-7. The published figures have 5 decimals in percent, so half a unit is 5e-8.
- **Window method.** The window is [T - n, T) at actual/360. If the window starts on a business day, the run uses `rates.ois.compound_dated`. Otherwise it uses `rates.ois.compound`, with calendar-day weights counted in the script.
- **Index and fallback.** It checks each SOFR Index step (warn level). It also checks the USD-LIBOR-3M fallback: the ISDA spread must be 0.26161%, and fallback must equal compounded plus spread.

First live runs, 2026-11-07, Python CLI:

| Workflow | Result | Run time |
|---|---|---|
| (a) | PASS, 27 checks. 1M to 30Y zero rates 4.07% to 5.39% | 2 min 48 s (Python key-rate risk is slow; CI uses Rust) |
| (c) | PASS, 25 checks. All 15 averages within 4.6e-8 of the NY Fed figure | 4 s |

Offline reruns: `--data DIR` reads saved source files instead of fetching them. The file names are listed in each script.

## Sanity bands

`sanity_bands.json` holds the bands, and `sanity.py` compares against them, with no financial logic. The bands are wide on purpose: they catch a broken feed, a wrong unit or a failed build, not a market move.

| Group | Fail | Warn |
|---|---|---|
| Fixing | Level outside -1% to 15%; day change over 100 bp | Day change over 25 bp |
| Par quotes | Level outside -1% to 15%; day change over 100 bp | Day change over 30 bp; adjacent tenors more than 150 bp apart |
| Curve | DF outside (0, 1.02]; zero rate outside -1% to 15%; pillar forward outside -2% to 20% | DF rising (a negative forward) |
| Front end | — | Fixing more than 75 bp from the shortest quote |
| SOFR averages | Library more than 1e-7 from the published figure | Index step more than 5e-6 off |

A band changes only in its own commit, with the reason. The gallery page [real-usd-treasury.md](../curves/real-usd-treasury.md) shows them on a committed snapshot, with all four CLIs agreeing to 1.1e-14. `python tools/build_gallery.py --real-only --refresh-real` fetches a new snapshot and rewrites only that page and the index. `--check` reruns the Python CLI against the snapshot, offline.

## Per-stage mutation report

`conformance/mutation/stages.json` maps each stage D module to its file or class in each language, and to the golden suite its mutants are checked against. `mutation-stage.yml` runs one job per mapped (module, language) pair; for stage D that is 31 jobs, at most 8 at a time.

| Language | Tool | Which tests count |
|---|---|---|
| Java | PIT, XML report | Unit tests |
| C++ | `cpp_mutants.py --out` | Golden cases |
| Python, Rust | `golden_mutants.py --out` | Unit tests or golden cases, on a sample of 40 mutants |

`stage_report.py` then writes one table and a pooled score. The stage D target is **80%** per module and language (where at least 10 mutants were scored) and pooled. Use `--gate` to fail the run when a mapped result is missing or a score is below target. Survivors are not yet sorted into equivalent mutants and real gaps, so the score is a lower bound.

**Status.** The job and report are built and linted, but **no stage D score has been measured yet**. Local runs are not possible here: Windows blocks freshly built Rust and C++ executables, and mutmut needs Linux. The first figure comes from a manual run of `mutation-stage.yml` once this branch is on GitHub. Some modules are not mapped in some languages, for example C++ `curve_fits` and `xccy`, and Python `compounding_d`. The report lists them as "not mapped" rather than hiding them.
