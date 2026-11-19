# Infrastructure adapters and simulated feed formats (K-3)

Spec version 0.1.0-proposed (stage K wave 3, lane k-w3-spec, 2026-11-19). Status: PROPOSED; nothing here is built or run. Rulings KR-180 to KR-189 (`stage-k-rulings-w3.md`, proposed; not normative until the stage K coordinator confirms them). Plan items: 14.8 K-3; 14.10 rules 1 and 2; ADR-0006 (`architecture/decisions/ADR-0006-modular-monolith-first.md`: libraries first, services only for a concrete need). Builds on `01-core/snapshot-hash.md` (canonical bytes), `cli-contract.md` (`quantforge batch`) and the stage H simulators.

**Every feed fixture and every feed adapter output is labelled "simulated; format only; no venue connectivity".** No adapter connects to a venue, a broker or a data vendor. No byte of any fixture comes from recorded market data; every value is invented and the invented symbol is `QFSIM`.

**Plain idea.** The libraries already compute; an adapter only moves their inputs and outputs through a common piece of infrastructure (a message bus, a database, a metrics store). The test of an adapter is therefore not a number but a round trip: write 10,000 known records in, read them back out, and show that the bytes are the same on both sides by comparing one hash. The feed formats are tested the same way at the byte level: we build a message by hand from the published layout, decode it, encode it again, and require the same bytes. And because ADR-0006 puts services last, the numerical libraries must still build on a machine where none of this is installed.

## Sources

| Ref | What | Evidence class |
|---|---|---|
| [ADR6] | `architecture/decisions/ADR-0006-modular-monolith-first.md`; `STAGE_K_START.md` scope line "the K-3 adapters are Docker Compose wrappers and the numerical libraries build with none of them installed" | read (repository) |
| [SH] | `01-core/snapshot-hash.md`: canonical form and `snapshot_id` | read (repository) |
| [ITCH] | Nasdaq TotalView-ITCH 5.0 specification, `https://www.nasdaqtrader.com/content/technicalsupport/specifications/dataproducts/NQTVITCHspecification.pdf`, fetched 2026-11-19 by the web-fetch agent (no login), text extracted locally with `pdftotext`. Read: "All integer fields are bigendian (network byte order)"; alpha fields left justified, space padded; Price(4) has 4 implied decimals; timestamps are nanoseconds since midnight; Add Order "A" layout: type 0/1, stock locate 1/2, tracking number 3/2, timestamp 5/6, order reference 11/8, buy/sell 19/1, shares 20/4, stock 24/8, price 32/4 (36 bytes) | read |
| [OUCH] | Nasdaq OUCH 4.2, "Updated October, 2025", `https://www.nasdaqtrader.com/content/technicalsupport/specifications/TradingProducts/OUCH4.2.pdf`, same route. Read: integers "unsigned big-endian (network byte order)"; prices fixed point with 4 decimals; Enter Order "O": type 0/1, order token 1/14, buy/sell 15/1, shares 16/4, stock 20/8, price 28/4, time in force 32/4, firm 36/4, display 40/1, capacity 41/1, intermarket sweep 42/1, minimum quantity 43/4, cross type 47/1, customer type 48/1 (49 bytes). The document carries a Nasdaq copyright line. The text extraction scrambled the value-type column of this table; the build lane re-reads the PDF page before freezing the fixture (KR-184) | read (offsets); type column to re-read |
| [MOLD] | MoldUDP64 Protocol Specification V 1.00, `https://www.nasdaqtrader.com/content/technicalsupport/specifications/dataproducts/moldudp64.pdf`, same route. Read: numbers "Big Endian"; downstream header session 0/10 (alphanumeric), sequence number 10/8, message count 18/2, header 20 bytes; message count 0 is a heartbeat and 0xFFFF end of session; each message block is a 2-byte length then the data | read |
| [SOUP] | SoupBinTCP Version 3.00, `https://www.nasdaqtrader.com/content/technicalsupport/specifications/dataproducts/soupbintcp.pdf`, same route. Read: each logical packet is a 2-byte big-endian length (payload plus the 1-byte type), a 1-byte type, a payload; Sequenced Data packet type "S"; sequence numbers implied, first is 1 | read |
| [FIXW] | `https://fixtrading.org/packages/fix-tagvalue-encoding/` ("FIX Tagvalue Encoding Standard", page says it became ISO 3531-1:2022) and `https://fixtrading.org/packages/fast-specification-version-1-1/` ("FAST Specification Version 1.1"), read 2026-11-19 by the web-fetch agent. Both pages show the documents but their download controls did not resolve to a file; whether a login or an IPR agreement is needed was not established. `https://www.fixtrading.org/standards/tagvalue-online/` returned 404. Site footer: "All Rights Reserved"; no open licence stated | read (pages only; the specifications themselves NOT read) |
| [IMG] | Image and licence pages read 2026-11-19 by the web-fetch agent; listed per image in the table below | read |
| [DD] | Docker Desktop licence, `https://docs.docker.com/subscription/desktop-license/`, read 2026-11-19: free for personal use, education, non-commercial open source projects and small businesses | read |
| [POD] | Podman, `https://github.com/containers/podman/blob/main/LICENSE`, read 2026-11-19: Apache License 2.0 | read |
| [R1I] | `docs/developer-guides/r1-infra.md`: "No Docker or Podman is installed" on the laptop (stated in stage R1) | read (repository); current state UNVERIFIED |

No London Stock Exchange or LSEG document, format or convention is used anywhere in this spec.

## Formats dropped or held (KR-184)

| Format | Status | Why |
|---|---|---|
| FIX tag=value | **HELD; dropped from v1.0.0 unless the specification is read before the K-3 build starts** | The specification text was not read [FIXW]. A fixture written from memory would have no read source, so none is written. If a lane reads the standard without registration (owner or in-app browser, as for the BIS texts), the fixture section below is filled from it in its own commit before any code; if reading needs registration or an agreement, FIX is dropped and stays listed here |
| FAST 1.1 | **HELD; same rule** | Same [FIXW]; the stop-bit and presence-map rules were not read |
| ITCH 5.0, OUCH 4.2, MoldUDP64 (multicast framing), SoupBinTCP 3.00 | kept | read without login [ITCH], [OUCH], [MOLD], [SOUP] |

"Multicast" in K-3 is met by MoldUDP64 packets sent over UDP multicast inside the Compose network (one sender, two listeners); the payloads are ITCH messages.

## 1. Shared round-trip rule (KR-180, KR-181)

### 1.1 The 10,000 records
A record is a JSON object `{"seq": n, "kind": k, "body": b}` with `n` from 1 to 10,000. Bodies are generated, not recorded: `kind` cycles through `quote`, `trade`, `curve_point`, `risk_row` (`n mod 4`), and every number in `body` comes from `core.rng` with seed 20261109 (plan 12.10 common parameter), stream index `n`. The generator is `tools/adapters/gen_records.py` (to be written) and its output file is hashed and committed as `datasets/adapters/records-10000.jsonl` before any adapter run. Prices and quantities that need exact decimal meaning are decimal strings (HR-44 style), so no adapter can change them by re-parsing a float. One record per line at most 512 bytes canonical.

### 1.2 Canonical bytes and the content hash (defined once, used by every adapter)
- `canon(r)` = the canonical form of [SH] applied to record `r` (numbers as `#` plus 16 hex digits of binary64, keys in byte order, no white space).
- `H(R) = lower-case hex SHA-256 of canon(r_1) + 0x0A + canon(r_2) + 0x0A + ... + canon(r_N) + 0x0A`, records sorted by `seq` ascending first.
- The sender computes `H` over what it sent; the receiver computes `H` over what it read back, after mapping the store's native row or message back into the record object (the mapping per adapter is fixed below and is part of the test). **Pass: equal hashes, and N = 10,000 on both sides.** A duplicate `seq`, a missing `seq` or an extra record fails before hashing (`COUNT`).
- For the binary feed formats the hash is over raw bytes instead: `H_bytes = SHA-256` of the concatenated frames in send order.

Worked example (one record). `{"seq":1,"kind":"quote","body":{"bid":"101.25","ask":"101.26"}}` has canonical form `{"body":{"ask":"101.26","bid":"101.25"},"kind":"quote","seq":#3ff0000000000000}`; `H` of a one-record list is the SHA-256 of those 77 bytes plus `0x0A`. The value is to be computed by the oracle and cross-checked with `sha256sum` when the generator is written (not computed here, because nothing is run tonight).

### 1.3 Smoke harness
Each adapter has `platform/compose/<adapter>/compose.yaml` and one driver `tools/adapters/smoke.py <adapter>`: `compose up --wait`, send, read back, hash both sides, write `benchmarks/results/k3/<adapter>.json` (`n_sent`, `n_read`, `h_sent`, `h_read`, image digests, wall time, host label "local laptop, not the acceptance machine" or "GitHub Actions runner"), `compose down -v`. Exit 0 only if both hashes match. Every compose file names images by digest (`image: name@sha256:...`); the driver refuses a file with a tag-only reference (`UNPINNED`).

### 1.4 Planted faults (plan 14.10 rule 1; each must be shown failing before an adapter counts as built)
| Fault | Expected failure |
|---|---|
| receiver drops one record | `COUNT` |
| receiver changes one byte of one body string | `HASH` |
| receiver reorders two records but keeps the set | passes (hash is over `seq`-sorted records; this is the intended behaviour and is tested as a pass) |
| a number in one body read back as a float that is not the same binary64 | `HASH` |
| compose file with a tag-only image | `UNPINNED` |
| adapter returns 10,000 records from the sender's memory instead of the store (driver stub that bypasses the service) | `BYPASS`: the driver restarts the service container between write and read for the stores (PostgreSQL, ClickHouse, Kafka with retention) and compares; a bypass stub that returns the sent list without connecting is caught by requiring the store's own row count query to equal 10,000 |

## 2. Per adapter

Images: licence as stated on the page read [IMG]. Digest column: only the PostgreSQL index digest was read tonight; every other digest is recorded by the build lane with `docker buildx imagetools inspect <name>:<tag>` (or `podman manifest inspect`) into `platform/compose/images.lock` in its own commit **before the first smoke run** (KR-182). An image whose licence page cannot be read at that time is not used.

| Adapter | Image(s) | Licence (page read 2026-11-19) | Pin |
|---|---|---|---|
| gRPC / REST | `python` official (server wrapping `quantforge batch`) | Hub page links to the Python licence pages; that licence text was not fetched: **read it before use** | to record |
| Arrow (IPC file and Flight) | same `python` image with `pyarrow` | Apache Arrow licence not read tonight: **read it before use** | to record |
| Aeron | `eclipse-temurin` 25 JRE; Aeron jar from Maven Central | Temurin: Dockerfiles Apache 2.0, OpenJDK "GNU GPL v2 with Classpath Exception" (`hub.docker.com/_/eclipse-temurin`); Aeron: Apache 2.0 (`github.com/real-logic/aeron`). No official Aeron image exists (Hub search, first 25 results), so none is used | to record |
| Kafka | `apache/kafka` | Apache 2.0 (`github.com/apache/kafka/blob/trunk/LICENSE`) | to record |
| PostgreSQL | `postgres` official, tag 17 | PostgreSQL Licence (`postgresql.org/about/licence/`) | `postgres:17@sha256:b60e90042aa6b8dbecd58e224b3e36114dbf8ad754465264c2476ad58a86e45c` (Hub API, last updated 2026-11-19T01:08:53Z) |
| ClickHouse | `clickhouse/clickhouse-server` | Apache 2.0 (`github.com/ClickHouse/ClickHouse/blob/master/LICENSE`) | to record |
| Prometheus | `prom/prometheus` | Apache 2.0 (Hub page and repo LICENSE) | to record |
| Grafana | `grafana/grafana-oss` | AGPLv3 (`grafana.com/licensing/`); used unmodified, locally, not offered to anyone as a service; see KR-183 | to record |

Dropped images: none on licence grounds. Not used: any unofficial Aeron image (no publisher we can verify).

| Adapter | What is sent | What is read back and how it maps to the record | Pass |
|---|---|---|---|
| gRPC | 10,000 unary calls `Run(case)` where `case` is a `core.snapshot.hash` CLI case whose `document_text` is `canon(r)` | the result's `canonical` field, parsed back to `r` | §1.2 equal hash; plus every returned `snapshot_id` equals the library's |
| REST | same as gRPC over `POST /v1/run` (JSON) | same | same |
| Arrow IPC | one record batch of 10,000 rows (`seq` int64, `kind` utf8, `body` utf8 holding `canon(body)`) written to a file and read back | rows to records | equal hash |
| Arrow Flight | same batch via `do_put`, then `do_get` | same | equal hash |
| Aeron | 10,000 messages on one IPC or UDP publication, payload `canon(r)` | subscriber fragments to records | equal hash; no fragment lost (Aeron reliable stream) |
| Kafka | 10,000 messages to topic `k3`, one partition, key `seq`, value `canon(r)` | consumer from offset 0 | equal hash |
| PostgreSQL | `COPY` into `k3(seq bigint primary key, kind text, body jsonb)` | `SELECT ... ORDER BY seq`, body re-canonicalised | equal hash; `count(*) = 10000` |
| ClickHouse | `INSERT` into a `MergeTree` table of the same columns (body as `String`) | `SELECT ... ORDER BY seq` | equal hash; `count() = 10000` |
| Prometheus | an exporter exposes 10,000 gauge series `k3_value{seq="n"}` whose value is a binary64 from the record body | HTTP API instant query at the scrape time | equal hash over records `{seq, value}` (a reduced record, stated as such) |
| Grafana | a provisioned Prometheus data source; the same query through Grafana's data source proxy | same | equal hash to the Prometheus read |

For jsonb (PostgreSQL) the store does not keep key order or white space, which is why the hash is over the canonical form and not over the stored text.

## 3. Feed fixtures (KR-184, KR-185)

Fixtures live in `datasets/feeds/<format>/*.bin` with a sidecar `*.json` stating every field value, the source section, and `label: "simulated; format only; no venue connectivity"`. Each language that implements a codec (Python first; the others only if the coordinator wants four-language parity for codecs, which is not a K-3 acceptance item) must: decode the bytes to the sidecar fields; encode the sidecar fields to the same bytes; reject a truncated frame and a wrong type byte with `E_PARSE`.

Hand-built fixtures (bytes computed by hand from the layouts in the sources table and checked with a short script on 2026-11-19; to be re-checked with `xxd` and `sha256sum` when the files are written):

| Fixture | Fields | Bytes (hex) | SHA-256 |
|---|---|---|---|
| `itch/add_order_1` | "A", locate 1, tracking 0, timestamp 34,200,000,000,000 ns (09:30:00), order ref 1, "B", 100 shares, "QFSIM   ", price 1012500 (101.2500) | `41000100001f1aced9f00000000000000000014200000064514653494d202020000f7314` (36 bytes) | `e6b2df55aa2cb8bc1901e2a90e67ab97d7b44f4547a2f52792dd0c2df3a0166a` |
| `mold/one_block` | session "QFSIM00001", sequence 1, count 1, one block of length 36 holding `itch/add_order_1` | `514653494d303030303100000000000000010001002441000100001f1aced9f00000000000000000014200000064514653494d202020000f7314` (58 bytes) | `b05977dad951cc16a353128148917e087ba7a63056e7550b15e5f5a55ca3f235` |
| `mold/heartbeat` | session "QFSIM00001", next sequence 2, count 0 | `514653494d303030303100000000000000020000` | to compute |
| `mold/end_of_session` | same, count 0xFFFF | `514653494d30303030310000000000000002ffff` | to compute |
| `soup/sequenced_1` | length 37, type "S", payload `itch/add_order_1` | `00255341000100001f1aced9f00000000000000000014200000064514653494d202020000f7314` (39 bytes) | `9adf959a27445244a0822e6a3dfd3d70ae5f7c560f41e8aba43cbf9269431328` |
| `ouch/enter_order_1` | "O", token "QF0000000001  ", "B", 100, "QFSIM   ", 1012500, time in force 0, firm 4 spaces, display "Y", capacity "P", sweep "N", minimum quantity 0, cross type "N", customer type " " | `4f51463030303030303030303120204200000064514653494d202020000f7314000000002020202059504e000000004e20` (49 bytes) | `803121fc62851782e9a1c2cbccd7b57f779cb8554d654b80c779d1c01b722d53` | 

The OUCH row is PROPOSED until the type column of [OUCH] is re-read (KR-184): if a field there is an integer where this row uses a letter, the row is corrected in its own commit before any codec exists. Further fixtures to build from the same tables: ITCH System Event "S", Order Executed, Order Cancel, Order Delete; a MoldUDP64 packet with three blocks; a SoupBinTCP Login Request and Server Heartbeat; OUCH Accepted and Canceled. Each new fixture cites the page and table it came from.

Multicast smoke: one sender container publishes 10,000 ITCH Add Order messages generated from §1.1 records (price and shares from the body, order reference = `seq`), packed in MoldUDP64 packets of up to 10 blocks, to a multicast group on the Compose bridge network; two listeners decode and re-encode; pass when both listeners' `H_bytes` over the re-encoded ITCH messages equal the sender's, with gap detection by MoldUDP64 sequence number (a planted dropped packet must be reported as a gap: rule 1). If the Compose bridge does not carry multicast on the host, the test runs on the host network inside WSL and the report says so.

## 4. Libraries build without the adapters (KR-186)

CI job `libraries-without-services` in `repo-gates.yml` (or its own workflow), on a fresh `ubuntu-latest` runner:
1. Assert that no adapter dependency is present: `docker`, `podman`, `kafka`, `psql`, `clickhouse`, `prometheus` not on `PATH` is not enough (the runner image has Docker), so the job instead runs each language build in a clean container-free step with **dependency manifests checked**: Python `pip install --no-deps` of `python/` then `uv sync --frozen` with the adapter extras absent; Rust `cargo build --locked -p quantforge` (the library crate has no adapter feature at all); Java `mvn -o` on `java25/` without the `adapters` module; C++ CMake with `-DQF_ADAPTERS=OFF`.
2. Static check `tools/check_adapter_deps.py`: no file under the four library source trees imports or links a module in the forbidden list (`grpc`, `pyarrow.flight`, `io.aeron`, `kafka`, `psycopg`, `clickhouse`, `prometheus_client`, `tonic`, `rdkafka`, `librdkafka`, `libpq`), and the library manifests (`pyproject.toml` main dependencies, `Cargo.toml` `[dependencies]`, `pom.xml` of the library modules, CMake `find_package` in the library targets) list none of them.
3. Run each language's existing golden suite after the build (the same `conformance` runner).
Planted fault (rule 1): a branch that adds `import grpc` to one library module and one that adds `psycopg` to the main dependencies; both must turn the job red, and the run links are recorded before the job counts as built.

Adapters live outside the library trees: `platform/` (compose files, drivers) and per-language optional modules (`python/quantforge_adapters/` as an optional extra, a separate Maven module, a separate Cargo crate, a separate CMake target), each depending on the library and never the other way round.

## Acceptance tests (PROPOSED; fixed when the coordinator confirms, before any run)

| ID | Plan | Test |
|---|---|---|
| AD1 | K-3 | For each of the 10 adapter rows of §2: the Compose smoke test passes §1.2 with N = 10,000 and equal hashes, from digest-pinned free images only; result file in `benchmarks/results/k3/` |
| AD2 | K-3 | Each kept feed format (ITCH, OUCH, MoldUDP64, SoupBinTCP): decode and encode of every fixture byte-exact, truncated and wrong-type frames rejected, label present |
| AD3 | K-3 | Multicast: 10,000 ITCH messages over MoldUDP64 multicast to two listeners, equal `H_bytes`; planted drop reported as a gap |
| AD4 | K-3, ADR-0006 | `libraries-without-services` green on main, and red on both planted branches |
| AD5 | 14.10 rule 1 | Every planted fault of §1.4 shown failing with its reason, run links recorded |
| AD6 | 14.10 rule 2 | The CHANGELOG line for K-3 names `benchmarks/results/k3/` and the AD4 run links |

## Out of scope

- Any connection to a real venue, broker, exchange gateway or data vendor; any recorded market data in a fixture.
- Throughput or latency claims for any adapter (wall time is recorded, not judged).
- Production hardening: authentication, TLS, high availability, schema registries, Kafka replication, backups.
- FIX and FAST unless their specifications are read without registration first (above).
- Four-language codecs (Python codec is the K-3 deliverable; others only by a later ruling).
- Grafana dashboards beyond the one data source query of §2.

## Limits

- The round trip proves the bytes survive the store; it says nothing about how the store behaves under load or failure (that is K-6).
- Prometheus and Grafana reduce each record to `{seq, value}`; their hash covers that reduction only.
- The reading of image and document terms is a reading, not legal advice.
