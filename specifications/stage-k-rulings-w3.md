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
