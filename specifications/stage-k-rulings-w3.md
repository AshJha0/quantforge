# Stage K wave 3 rulings (services last): PROPOSED

Status: PROPOSED by lane k-w3-spec on 2026-11-19. Not normative until the stage K coordinator confirms each row. Reviewer: none: self-assessment; no second review (owner decision 2026-11-18). Specs: `12-platform/adapters.md`, `lock-free-snapshots.md`, `mcp-server.md`, `dashboard.md`, `soak-eod-capacity.md`, `release-evidence.md`; plan `program/STAGE_K_W3_PLAN.md`.

| ID | Topic | Ruling |
|---|---|---|
| KR-180 | Round-trip records | 10,000 generated records `{seq, kind, body}`, numbers from `core.rng` seed 20261109 stream `seq`, decimals as strings; file hashed and committed before any adapter run. No recorded market data |
| KR-181 | One content hash for all adapters | SHA-256 over the `01-core/snapshot-hash.md` canonical form of each record, sorted by `seq`, each followed by LF. Feed formats hash raw frames in send order. Count check before hash |
| KR-182 | Images | Free images only, licence read on the image's or project's own page and recorded with URL and date; every compose reference pinned by digest in `platform/compose/images.lock`, committed before the first run; the driver refuses tag-only references |
| KR-183 | Grafana (AGPLv3) | Kept: used unmodified, locally and in CI, not offered as a network service to others, not redistributed. If the coordinator reads AGPL as not clearly free for this use, Grafana is dropped and listed, and Prometheus alone meets the metrics row |
| KR-184 | Feed specifications | A feed fixture is built only from a specification read without registration, cited with URL, version and evidence class. FIX tag=value and FAST 1.1 are HELD (pages read, documents not); they are dropped from v1.0.0 if not read before the K-3 build. ITCH 5.0, OUCH 4.2, MoldUDP64 1.00, SoupBinTCP 3.00 kept. OUCH fixture PROPOSED until the type column is re-read. Never any London Stock Exchange or LSEG format |
| KR-185 | Feed label | Every fixture sidecar and adapter output: "simulated; format only; no venue connectivity". Symbol `QFSIM`, all values invented |
| KR-186 | Libraries without services | CI job `libraries-without-services` plus `tools/check_adapter_deps.py` forbidden-import and manifest check; red on two planted branches before it counts (14.10 rule 1) |
| KR-187 | Multicast | Met by MoldUDP64 over UDP multicast with ITCH payloads, two listeners, gap detection by sequence number |
| KR-188 | Codecs | Python codec is the K-3 deliverable; other languages only by a later ruling |
| KR-189 | Where adapters live | `platform/` and optional per-language modules that depend on the libraries; never the reverse |
| KR-190 | Snapshot publication | Single writer, many readers, immutable fixed-size snapshot (at most 4 KiB). Java: release store and acquire load of a record with final fields; GC reclaims. C++ and Rust: single-writer hazard pointers [Michael 2004, recalled] over a fixed pool of R + 2 slots, R <= 64 registered readers |
| KR-191 | Rejected designs | `std::atomic<std::shared_ptr>` (not required lock-free, cppreference read), epoch-based reclamation (stalled reader blocks reclamation), `arc-swap` as a library dependency (third-party crate in the numerical library; reference only), seqlock (readers block on a stalled writer) |
| KR-192 | Progress claimed | Writer wait-free (bounded scan of R hazards); reader lock-free, not wait-free; Java single-access wait-free on the JVM's terms, safepoints reported in p99.9. No heap allocation after start-up in C++ and Rust |
| KR-193 | Risk and hedge content | Writer per publish: `risk.curve.key_rate`, `hedge.greeks.neutralise` (or `hedge.solve`); reader per move: `risk.intraday.delta_gamma_bound`. No new operation |
| KR-194 | Exactness | A number read through a snapshot is bit-identical to the direct call, 1,000 publishes per language |
| KR-195 | Race tests | C++ TSan; Rust loom (R = 2, 3 publishes) and Miri (64 seeds), TSan if the toolchain allows; Java jcstress. Four planted faults (relaxed ordering, skipped hazard scan, in-place mutation, corrupted field) each shown failing first |
| KR-196 | Targets | Table S1 to S5 of `lock-free-snapshots.md`, fixed in the confirming commit before any K-5b code, H-9 method: first measurement published as it is, a miss stays a miss. Label "latency-aware analytics on simulated data" |
