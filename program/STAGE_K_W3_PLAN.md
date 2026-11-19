# Stage K wave 3 (services last) and wave 4 service items: plan

Drafted 2026-11-19 by lane k-w3-spec (writing only: no builds, no Docker, no WSL, no Maven). All specs PROPOSED; rulings KR-180 to KR-227 in `specifications/stage-k-rulings-w3.md` need the coordinator's confirmation. Reviewer: none: self-assessment; no second review (owner decision 2026-11-18). ADR-0006: libraries first, services last; nothing below adds or changes a library operation.

## Specs

| Item | Spec | Acceptance IDs |
|---|---|---|
| K-3 adapters and simulated feeds | `specifications/12-platform/adapters.md` | AD1 to AD6 |
| K-5b lock-free snapshots, low-latency risk, real-time hedge | `specifications/12-platform/lock-free-snapshots.md` | LF1 to LF5, targets S1 to S5 |
| A7 read-only MCP server | `specifications/12-platform/mcp-server.md` | M1 to M3 (CI), eval and red-team (manual) |
| K-1/K-2/Q8k, K-11 and model-reserve dashboards | `specifications/12-platform/dashboard.md` | DB1 to DB7 |
| K-6 soak, load, EOD, capacity | `specifications/12-platform/soak-eod-capacity.md` | SK1 to SK5 |
| K-7 release evidence, G1k, G3b, G10 | `specifications/12-platform/release-evidence.md` | RE1 to RE9 |

## Machine facts and how to check them

- Laptop: 15.6 GB RAM, WSL 7 GB, one heavy WSL job at a time (lane rules), QUIET flag honoured before any job over about 20 s.
- **Docker: UNVERIFIED, probably absent.** Checked 2026-11-19 without running anything heavy: `docker` and `podman` are not on the Windows `PATH`, and `C:\Program Files\Docker` does not exist; `docs/developer-guides/r1-infra.md` says none is installed. Not checked: inside WSL. To check (a few seconds, not a heavy job): `wsl -e sh -c 'command -v docker podman; docker version 2>&1 | head -3'`. Installing Docker Desktop is free for personal and non-commercial open source use (licence page read 2026-11-19) but it is a system change for the owner to make; Podman (Apache 2.0) inside WSL is the zero-cost alternative. Either way, running Kafka, ClickHouse and Grafana together in 7 GB is not realistic; one adapter stack at a time.
- **Recommended route for containers: GitHub Actions `ubuntu-latest` runners**, which ship with Docker (recalled; to confirm from the runner image's published software list before relying on it). Free for a public repository (recalled). Locally only the Python codecs and fixtures.
- **Ollama is installed on Windows** (`C:\Users\ashis\AppData\Local\Programs\Ollama\ollama.exe` on `PATH`, seen 2026-11-19); no model was listed or pulled. The A7 manual check can run locally without WSL.

## Lane split and dependencies

| Lane | Work | Depends on | Where it runs |
|---|---|---|---|
| W3-A adapters | generator and canonical hash (KR-180, KR-181); feed codecs and fixtures (Python); compose files; smoke driver; `libraries-without-services` job and its two planted branches | coordinator confirms KR-180 to KR-189; image digests recorded first | Python on Windows; compose on Actions |
| W3-F feed specs | read FIX tag=value and FAST 1.1 documents by hand in the in-app browser if no registration is needed (as for the BIS texts); else record them as dropped | none | browser lane |
| W3-L lock-free | C++, Rust, Java pool and publisher; race tests; planted faults; then timing | KR-190 to KR-196 confirmed and targets committed before code | WSL (C++, Rust; TSan heavy: alone), Windows (Java, jcstress), Actions for TSan if WSL is busy |
| W3-M MCP | schema generator, server, checker, recorded malformed and planted transcripts, stub CI; eval set (300) and its hash | KR-200 to KR-210 confirmed; MCP version pinned | Python on Windows |
| W3-R red team | writes the 50+ red-team items with no view of the server code | a different-model session; coordinator ruling KR-209 | separate session |
| W3-D dashboards | `render.py`, `build_site --dashboards`, labels, counter, claim lint, holdout scan, planted faults | ledgers exist (branches created by the first scheduled runs); synthetic ledgers suffice for tests | Python on Windows |
| W4-S soak/EOD/capacity | soak harness and leak flag, capacity script, EOD rehearsal | K-5b built (for the publisher in the soak); dashboards built (E6) | Actions for soak (parallel, about 2.5 h); EOD locally |
| W4-E release evidence | RE1 to RE9 scripts and jobs | everything else; G1k and G3b need the owner | Actions; owner for settings and accounts |

Order: confirm rulings, then W3-A, W3-L, W3-M, W3-D in parallel (they share nothing but the canonical hash, which W3-A writes first); W3-F and W3-R in parallel from the start; W4 after.

## Wall-clock estimates (calibrated on stage H wave 2: about one wall-clock day with 6 to 12 lanes)

| Lane | Estimate | Main risk |
|---|---|---|
| W3-A | 1 to 1.5 days | no local Docker: every compose iteration is an Actions round trip (5 to 10 min each) |
| W3-F | 0.5 day | documents may need registration, then FIX and FAST are dropped |
| W3-L | 1.5 to 2 days | TSan and loom runs in WSL one at a time; a race found means redesign; timing must wait for the QUIET flag |
| W3-M | 1 to 1.5 days for CI parts; the manual eval about 3 to 5 hours of model time for 300 items plus 50 red-team on a laptop CPU or GPU (inferred, not measured) | eval pass mark is strict (293 of 300); a miss is a miss |
| W3-R | 0.5 day | authorship ruling KR-209 |
| W3-D | 0.5 to 1 day | none large |
| W4-S | 1 day plus about 2.5 h of Actions soak | soak result could miss |
| W4-E | 1 day plus owner time | owner settings and accounts |

Total: about 4 to 6 wall-clock days of active work with 4 to 6 parallel lanes, plus owner steps. Not on the critical path: the tag waits for 20 recorded ledger days (K-2), which on 2026-11-19 stands at 0 and needs about 4 calendar weeks after the paper workflow reaches `main`. Estimate against actual to be shown at each status.

## Recommended for a point release now (v1.0.1), with reasons

| Item | Recommendation | Reason |
|---|---|---|
| K-3 FIX and FAST fixtures | move to v1.0.1 unless the documents are read without registration before W3-A starts | no read source today (KR-184); fixtures from memory are not allowed |
| K-3 Aeron, ClickHouse, Grafana adapters | keep in v1.0.0 only if Actions runs work in the first day; else move to v1.0.1 | each needs containers that cannot run locally; Kafka, PostgreSQL and Prometheus cover a bus, a store and metrics |
| A7 manual eval and red team | keep the CI parts (M1 to M3) in v1.0.0; move the real-model release check to v1.0.1 if KR-209 is not confirmed or the eval misses | plan 15 gate rule: an item that cannot meet its test moves; the CI parts can be met now. A7 is "optional" in 12.7 |
| G3b registry publishing | v1.0.1 unless the owner has made the accounts by tag time | owner decision K-QF |
| K-5b timing (S1 to S5) | keep; publish as measured, a miss stays a miss | targets need no outside data |
| K-6 soak | keep | Actions makes it cheap |

Nothing here loosens a threshold: a moved item keeps its test unchanged for the point release.

## Decisions the coordinator must take

1. Confirm or amend KR-180 to KR-227.
2. KR-183: Grafana under AGPLv3 kept for local, unmodified use, or dropped.
3. KR-209: red-team authorship by a different-model session counts as test authorship, not a second review.
4. Whether the owner installs Docker or Podman locally, or all container work runs on Actions (recommended).
5. Whether any FIX or FAST reading lane is worth running (KR-184).
