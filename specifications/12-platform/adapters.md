# Infrastructure adapters and simulated feed formats (K-3)

Spec version 0.2.0 (stage K, lane `k-v1-k3`, 2026-11-20). Status: confirmed 2026-11-20 by the stage K coordinator under the owner's delegation. Rulings KR-270 to KR-283 (`specifications/stage-k-rulings-k3.md`, confirmed 2026-11-20). Plan items: 14.8 K-3; 14.10 rules 1 and 2; ADR-0006 (`architecture/decisions/ADR-0006-modular-monolith-first.md`: libraries first, services only for a concrete need). Builds on `01-core/snapshot-hash.md` (canonical form) and `01-core/rng.md` (the seeded generator). Version 0.1.0 of this page (branch `k-w3-spec`, lane k-w3-spec, 2026-11-19) is superseded; what changed and why is listed in "Changes from 0.1.0" at the end.

**Every feed fixture, every codec and every adapter output carries the label "simulated; not a certified implementation; not connected to any venue".** No adapter connects to a venue, a broker, an exchange gateway or a data vendor. No byte of any fixture comes from recorded market data; every value is invented and the only symbol is `QFSIM`. No London Stock Exchange or LSEG document, format or convention is used anywhere in this page.

**Plain idea.** The libraries already compute; an adapter only moves their inputs and outputs through a common piece of infrastructure (a message bus, a database, a metrics store). The test of an adapter is therefore not a number but a round trip: write 10,000 known records in, read them back out, and show that the bytes are the same on both sides by comparing one hash. The feed formats are tested at the byte level: a message is built by hand from the layout on this page, decoded, encoded again, and the bytes must match. Because ADR-0006 puts services last, the numerical libraries must still build on a machine where none of this is installed.

## Sources

| Ref | What | Evidence class |
|---|---|---|
| [ADR6] | `architecture/decisions/ADR-0006-modular-monolith-first.md`; `STAGE_K_START.md` scope line "the K-3 adapters are Docker Compose wrappers and the numerical libraries build with none of them installed" | read (repository) |
| [SH] | `specifications/01-core/snapshot-hash.md`: canonical form, `snapshot_id` | read (repository) |
| [RNG] | `python/quantforge_core/rng.py` `next_u64(seed, stream, count)` (xoshiro256** with jump streams) | read (repository) |
| [PUB] | General public knowledge of the shape of four protocol families: FIX tag=value (`tag=value` fields, SOH delimiter, BeginString, BodyLength, a modulo-256 byte-sum checksum in tag 10); ITCH-style and OUCH-style fixed-width big-endian binary messages with a one-letter type; MoldUDP64-style packets (session, sequence number, message count, length-prefixed blocks; count 0 is a heartbeat); FAST-style stop-bit integers, presence maps and copy, increment and delta field operators | recalled. **No exchange or standards document was downloaded or opened for this page (coordinator decision 2026-11-20).** The layouts below are this page's own simplified formats, written from that recalled shape; they are not any venue's or standard's format and no conformance to one is claimed |
| [IMG] | Image licence and digest table in section 2, each row with its URL and read date | read |
| [PSF] | `https://docs.python.org/3/license.html`, read 2026-11-20: Python is licensed under the Python Software Foundation License Version 2, a permissive licence | read |
| [AGPL] | `https://grafana.com/licensing/`, read by lane k-w3-spec 2026-11-19 (cited in version 0.1.0 of this page): Grafana OSS is AGPLv3 | read (by another lane; cited) |

## Recorded scope changes (coordinator decisions under the owner's delegation, 2026-11-20)

| Change | From | To | Why |
|---|---|---|---|
| SC-1 Grafana dropped | Prometheus and Grafana rows | **Prometheus only** | Grafana OSS is AGPLv3 [AGPL]; the coordinator ruled it is not a free image for this project's purposes. The metrics row is met by a Prometheus scrape and HTTP API read. Listed in `docs/known-issues.md` (KI-K3-GRAFANA) |
| SC-2 Containers on GitHub Actions only | local Compose runs allowed | Compose runs only on GitHub Actions `ubuntu-24.04` runners | there is no Docker on the development laptop and none is to be installed. Every container result in this page is "untested until CI" until a workflow run link is recorded |
| SC-3 FIX and FAST kept as simulated formats | HELD until the standards are read | kept, as this page's own simplified formats from public knowledge [PUB] | coordinator decision: no exchange or standards PDF is opened; all five formats are simulated and say so |
| SC-4 Formats are named "-style" | ITCH 5.0, OUCH 4.2, MoldUDP64 1.00, SoupBinTCP 3.00 | `QF-FIX-S`, `QF-ITCH-S`, `QF-OUCH-S`, `QF-FAST-S`, `QF-MOLD-S` | the fixtures no longer rest on a reading of a vendor document, so they must not claim to be that document's format |

## 1. Shared round-trip rule (KR-270, KR-271)

### 1.1 The 10,000 records
A record is a JSON object `{"seq": n, "kind": k, "body": b}` with `n` from 1 to 10,000. Nothing is recorded; every number comes from [RNG]: `u = next_u64(20261109, n, 4)` (seed 20261109 is the plan 12.10 common parameter; the stream index is `n`), giving four unsigned 64-bit words `u0..u3`.

- `kind = ["quote", "trade", "curve_point", "risk_row"][n mod 4]`.
- Every body has `value = (u3 >> 11) * 2^-53`, a binary64 in [0, 1) that is exact (53 bits).
- `dec(x, d)`: the integer `x` written as a decimal string with `d` digits after the point, a leading `-` if negative, at least one digit before the point (`dec(1012500, 4) = "101.2500"`, `dec(-5, 2) = "-0.05"`).
- `quote`: `t = 1000000 + u0 mod 1000000`; `bid = dec(t, 4)`, `ask = dec(t + 1 + u1 mod 10, 4)`.
- `trade`: `price = dec(1000000 + u0 mod 1000000, 4)`, `qty = str(1 + u1 mod 10000)`, `side = "B"` if `u2` is odd else `"S"`.
- `curve_point`: `tenor = ["1M","3M","6M","1Y","2Y","5Y","10Y","30Y"][u0 mod 8]`, `rate = dec(u1 mod 100000 - 20000, 6)`.
- `risk_row`: `book = "B" + str(u0 mod 16)`, `dv01 = dec(u1 mod 10000000 - 5000000, 2)`.

Prices, quantities and rates are decimal strings (HR-44 style), so no adapter can change them by re-parsing a float; `value` is the one binary64 per record and is what the Prometheus row carries. The generator is `tools/adapters/gen_records.py`; its output `datasets/adapters/records-10000.jsonl` and its SHA-256 are committed before any adapter run (`datasets/adapters/records-10000.sha256`).

### 1.2 Canonical bytes and the content hash
- `canon(r)` = the canonical form of [SH] applied to record `r` (numbers as `#` plus 16 lower-case hex digits of binary64, keys ordered by UTF-8 bytes, no white space).
- `H(R)` = lower-case hex SHA-256 of `canon(r_1) LF canon(r_2) LF ... canon(r_N) LF`, records sorted by `seq` ascending first (LF = byte 0x0A).
- Count rule first: the read set must hold every `seq` from 1 to 10,000 exactly once. A missing, duplicated or extra `seq` fails with `COUNT` before any hash is computed.
- Pass: `COUNT` clean, and `H(sent) = H(read)`; else `HASH`.
- For the binary feed (section 3.5 multicast) the hash is over bytes: `H_bytes` = SHA-256 of the concatenated encoded messages in sequence-number order.

Worked example. The record `{"seq":1,"kind":"quote","body":{"bid":"101.25","ask":"101.26"}}` has the canonical form `{"body":{"ask":"101.26","bid":"101.25"},"kind":"quote","seq":#3ff0000000000000}` (79 bytes, measured; version 0.1.0 of this page said 77, which was a miscount; `1` is binary64 `0x3FF0000000000000`). `H` of the one-record list is the SHA-256 of those 79 bytes followed by 0x0A. The test `test_canon_worked_example` in `platform/python/tests/test_records.py` computes it and compares it with Python `hashlib` over the literal bytes (measured on the laptop; the value is printed in the test, not repeated here to avoid a second copy that can drift).

### 1.3 Smoke harness
Each adapter has `platform/compose/<adapter>/compose.yaml` and one driver `python -m quantforge_adapters.smoke <adapter> --phase write|read|all`. The workflow brings the stack up (`docker compose up --wait`), runs the write phase, restarts the store container for the stores (PostgreSQL, ClickHouse, Kafka), runs the read phase, and brings the stack down. The read phase writes `benchmarks/results/k3/<adapter>.json`: `adapter`, `n_sent`, `n_read`, `h_sent`, `h_read`, `store_count` (where the store has a count query), `image_digests`, `wall_s`, `host` ("GitHub Actions runner"), `label`, `verdict` (`PASS`, `COUNT`, `HASH`, `BYPASS`). Exit 0 only on `PASS`. The driver refuses any compose file whose `image:` lines are not `name:tag@sha256:<64 hex>` (`UNPINNED`).

### 1.4 Planted faults (plan 14.10 rule 1)
Each is applied by the driver to the read-back list of a real run (no second container run is needed) and must give its verdict, in the same workflow job, before the real verdict is accepted (`--plants` on by default):

| Fault | Expected verdict |
|---|---|
| receiver drops one record | `COUNT` |
| receiver duplicates one record | `COUNT` |
| receiver changes one byte of one body string | `HASH` |
| a body `value` read back as a different binary64 (next float up) | `HASH` |
| receiver reorders two records but keeps the set | `PASS` (the hash is over `seq`-sorted records: intended) |
| compose file with a tag-only image | `UNPINNED` (unit test over a planted copy; no container) |
| store count query does not equal 10,000 while the read list is correct (a reader that returns the sender's list without reading the store) | `BYPASS` |

## 2. Per adapter (KR-272, KR-273)

### 2.1 Images
Free images only; each licence read on the project's own page. Digests read on 2026-11-20 from the Docker Hub tag API (`https://hub.docker.com/v2/repositories/<name>/tags/<tag>`, field `digest`: the multi-platform index digest), recorded in `platform/compose/images.lock` and used verbatim in every compose file.

| Image | Tag | Digest (index) | Licence (page; read) |
|---|---|---|---|
| `postgres` | 17.6 | `sha256:00bc86618629af00d2937fdc5a5d63db3ff8450acf52f0636ec813c7f4902929` | PostgreSQL Licence (`postgresql.org/about/licence/`; read by lane k-w3-spec 2026-11-19) |
| `apache/kafka` | 4.1.0 | `sha256:bff074a5d0051dbc0bbbcd25b045bb1fe84833ec0d3c7c965d1797dd289ec88f` | Apache 2.0 (`github.com/apache/kafka/blob/trunk/LICENSE`; k-w3-spec 2026-11-19) |
| `clickhouse/clickhouse-server` | 25.8 | `sha256:0152dd511befe6a2c2ef53e930726179669b08116da78500b37c51c96ff5ee77` | Apache 2.0 (`github.com/ClickHouse/ClickHouse/blob/master/LICENSE`; k-w3-spec 2026-11-19) |
| `prom/prometheus` | v3.7.3 | `sha256:49214755b6153f90a597adcbff0252cc61069f8ab69ce8411285cd4a560e8038` | Apache 2.0 (Hub page and repository LICENSE; k-w3-spec 2026-11-19) |
| `python` | 3.13-slim | `sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90` | PSF License Version 2 [PSF] (2026-11-20) |
| `eclipse-temurin` | 25-jre | `sha256:945247f9d092703e0c6be92243ef3c51640229e23ab34d353c8dcdc73e6cd4e6` | Dockerfiles Apache 2.0, OpenJDK GPLv2 with Classpath Exception (`hub.docker.com/_/eclipse-temurin`; k-w3-spec 2026-11-19) |

Client libraries (installed only in the adapter environment, never in a library build), versions read from the PyPI JSON API 2026-11-20: `pyarrow==26.0.1` (Apache-2.0), `grpcio==1.85.3` (Apache-2.0), `kafka-python==3.0.13` (Apache-2.0), `pg8000==1.31.6` (BSD 3-Clause). ClickHouse and Prometheus are read over their HTTP interfaces with the Python standard library. Aeron: `io.aeron:aeron-all` from Maven Central, Apache 2.0 (`github.com/real-logic/aeron`; k-w3-spec 2026-11-19). There is no official Aeron image, so none is used; the Aeron programs run on the `eclipse-temurin` image (KR-273).

### 2.2 What each adapter sends and reads

| Adapter | Sent | Read back, and mapping to the record | Pass |
|---|---|---|---|
| REST | 10,000 `POST /v1/run` with JSON `{"document_text": T(r)}` where `T(r)` is the JSON text of `r` (keys sorted, no white space; the canonical form itself is not JSON, so it cannot be the document) to a stdlib HTTP service in the `python` image | response `{"canonical", "snapshot_id"}`; `canonical` parsed back to `r` | §1.2, and every `snapshot_id` equals `"sha256:" + sha256(canon(r))` computed by the driver |
| gRPC | 10,000 unary calls `/qf.k3.Run/Run`, request bytes = UTF-8 `T(r)` (raw bytes; no `.proto`, a generic handler) to a `grpcio` service in the `python` image | response bytes = `snapshot_id` LF `canonical` | same as REST |
| Arrow IPC | one record batch of 10,000 rows (`seq` int64, `kind` utf8, `body` utf8 = `canon(body)`) written to an IPC file and read back | rows to records | §1.2 |
| Arrow Flight | the same batch by `do_put` to a `pyarrow.flight` server in the `python` image, then `do_get` | rows to records | §1.2 |
| Kafka | 10,000 messages to topic `k3`, one partition, key = decimal `seq`, value = `canon(r)`; broker restarted between write and read | consumer from offset 0 until 10,000 or 60 s | §1.2; end offset = 10,000 (`BYPASS` check) |
| PostgreSQL | `COPY` into `k3(seq bigint primary key, kind text, body jsonb)`; server restarted between write and read | `SELECT seq, kind, body::text ORDER BY seq`, body parsed and re-canonicalised | §1.2; `count(*) = 10000` |
| ClickHouse | `INSERT ... FORMAT JSONEachRow` over HTTP into `MergeTree` table `k3(seq UInt64, kind String, body String)`; server restarted | `SELECT ... ORDER BY seq FORMAT JSONEachRow` | §1.2; `count() = 10000` |
| Prometheus | an exporter in the `python` image exposes 10,000 gauge series `k3_value{seq="n"}` with value = record `value` written by Python `repr` (shortest round-trip form) | HTTP API instant query `k3_value` after the first complete scrape | §1.2 over the reduced record `{seq, value}` (stated: the hash covers the reduction only); `count(k3_value) = 10000` |
| Aeron | a Java subscriber container and a Java publisher container, each with an embedded media driver, UDP unicast `aeron:udp?endpoint=sub:40123`; payload = `canon(r)` | subscriber writes the payloads it received, one per line; the driver parses them | §1.2 |

For `jsonb` (PostgreSQL) the store does not keep key order or white space, which is why the hash is over the canonical form and not over stored text.

## 3. Simulated feed formats (KR-274 to KR-279)

All five are this page's own formats [PUB]. Common rules:
- Integers in the binary formats are unsigned big-endian (network byte order) unless stated.
- Alpha fields are ASCII, left-justified, padded with spaces (0x20); every byte must be 0x20 to 0x7E.
- Prices are unsigned integers with 4 implied decimals (`1012500` = 101.2500).
- Timestamps are nanoseconds since midnight, simulated.
- A decoder never raises anything except `FeedError(code, detail)`. The eight codes are below; when an input has several faults, the code reported is the first one met in the check order stated in each format's section (bytes are read front to back, so a fault near the start wins). Codes: `E_TRUNCATED` (input ends before a field or frame is complete), `E_LENGTH` (a length field, a fixed message length or a size limit disagrees with the bytes), `E_TYPE` (unknown message type or template), `E_CHECKSUM`, `E_OVERLONG` (a non-minimal stop-bit encoding), `E_OVERFLOW` (a stop-bit integer exceeds its width), `E_FIELD` (a field value outside its allowed set), `E_SESSION` (multicast session mismatch or data after end of session). Encoders validate their inputs with the same codes.
- Round-trip law for every format: for every valid message `m`, `decode(encode(m)) = m`, and for every byte string `b` that decodes without error, `encode(decode(b)) = b` (the encodings are canonical; KR-276).

### 3.1 QF-FIX-S: tag=value with checksum (KR-274)
A message is a sequence of fields `tag=value` each followed by SOH (0x01). Tags are decimal integers with no leading zero; values are 1 or more bytes in 0x20 to 0x7E. The field order is fixed:

| Position | Tag | Meaning | Rule |
|---|---|---|---|
| 1 | 8 | BeginString | exactly `QFSIM.1` (deliberately not a real FIX version) |
| 2 | 9 | BodyLength | decimal, no leading zero: the number of bytes after the SOH that ends field 9, up to and including the SOH before `10=` |
| 3 | 35 | MsgType | `0` heartbeat or `D` new order |
| 4 | 34 | MsgSeqNum | decimal 1 to 2^31 - 1, no leading zero |
| 5 | 49 | SenderCompID | 1 to 16 bytes |
| 6 | 56 | TargetCompID | 1 to 16 bytes |
| ... | body | per type | `0`: no body fields. `D`: exactly `11` ClOrdID (1 to 20 bytes), `55` Symbol (1 to 8), `54` Side (`1` buy, `2` sell), `38` OrderQty (decimal 1 to 999999999, no leading zero), `40` OrdType (`2` limit only), `44` Price (`digits[.digits]`, no leading zero unless the integer part is `0`, at most 4 decimals) |
| last | 10 | CheckSum | exactly 3 decimal digits: the sum of every byte from the `8` of field 1 up to and including the SOH before `10=`, modulo 256, zero-padded |

Size limit 4,096 bytes (`E_LENGTH`). Decode order: ends with SOH and contains `\x0110=` (else `E_TRUNCATED`); field 8, 9 present and well-formed (else `E_FIELD`); BodyLength equals the counted bytes (`E_LENGTH`); MsgType known (`E_TYPE`); checksum (`E_CHECKSUM`); then the remaining field rules (`E_FIELD`).

**Fixture `fix/heartbeat_1`** (46 bytes): MsgSeqNum 1, sender `QFA`, target `QFB`. Fields with their bytes and byte sums (field bytes plus the SOH, which adds 1):

| Field | Bytes (hex) | Sum |
|---|---|---|
| `8=QFSIM.1` | `38 3d 51 46 53 49 4d 2e 31 01` | 597 |
| `9=24` | `39 3d 32 34 01` | 221 |
| `35=0` | `33 35 3d 30 01` | 214 |
| `34=1` | `33 34 3d 31 01` | 214 |
| `49=QFA` | `34 39 3d 51 46 41 01` | 387 |
| `56=QFB` | `35 36 3d 51 46 42 01` | 386 |

BodyLength: fields 3 to 6 are 5 + 5 + 7 + 7 = 24 bytes, so `9=24`. Checksum: 597 + 221 + 214 + 214 + 387 + 386 = 2019; 2019 - 7 x 256 = 227, so `10=227` (`31 30 3d 32 32 37 01`). Whole message hex: `383d514653494d2e3101393d32340133353d300133343d310134393d5146410135363d5146420131303d32323701`.

**Fixture `fix/new_order_1`** (89 bytes): MsgSeqNum 2, `11=QF1`, `55=QFSIM`, `54=1`, `38=100`, `40=2`, `44=101.25`. Body bytes: `35=D` 5, `34=2` 5, `49=QFA` 7, `56=QFB` 7, `11=QF1` 7, `55=QFSIM` 9, `54=1` 5, `38=100` 7, `40=2` 5, `44=101.25` 10: total 67, so `9=67`. Field sums: 597, 228 (`9=67`), 234, 215, 387, 386, 360, 552, 216, 314, 212, 461: total 4162; 4162 - 16 x 256 = 66, so `10=066`.

### 3.2 QF-ITCH-S: binary market data messages (KR-275)
Every message starts with an 11-byte header: `type` (1, ASCII letter), `locate` (u16), `tracking` (u16), `timestamp` (u48). A message's length is fixed by its type; the decoder takes exactly one message (framing comes from QF-MOLD-S). Check order: empty input `E_TRUNCATED`; unknown type `E_TYPE`; input shorter than the type's length `E_TRUNCATED`, longer `E_LENGTH`; then each field in offset order (`E_FIELD`).

| Type | Name | Body after the header (offset from 11, width) | Length |
|---|---|---|---|
| `S` | System event | event code 11/1 in {`O` start of messages, `S` start of system hours, `Q` start of market hours, `M` end of market hours, `E` end of system hours, `C` end of messages} | 12 |
| `A` | Add order | order reference 11/8, side 19/1 in {`B`,`S`}, shares 20/4 (u32, at least 1), stock 24/8 (alpha), price 32/4 (u32) | 36 |
| `E` | Order executed | order reference 11/8, executed shares 19/4 (at least 1), match number 23/8 | 31 |
| `X` | Order cancel | order reference 11/8, cancelled shares 19/4 (at least 1) | 23 |
| `D` | Order delete | order reference 11/8 | 19 |

**Fixture `itch/add_order_1`** (36 bytes). Derivation: `41` (`A`); locate 1 = `00 01`; tracking 0 = `00 00`; timestamp 34,200,000,000,000 ns (09:30:00) = 0x1F1ACED9F000 = `1f 1a ce d9 f0 00`; order reference 1 = `00 00 00 00 00 00 00 01`; side `B` = `42`; shares 100 = 0x64 = `00 00 00 64`; stock `QFSIM` plus three spaces = `51 46 53 49 4d 20 20 20`; price 1,012,500 = 0x0F7314 = `00 0f 73 14`. Hex: `41000100001f1aced9f00000000000000000014200000064514653494d202020000f7314`.

Other ITCH fixtures (derivations in their sidecars): `itch/system_event_O` (`S`, locate 0, timestamp 14,400,000,000,000 = `0d 18 c2 e2 80 00`, code `O`; 12 bytes `53000000000d18c2e280004f`); `itch/order_executed_1` (ref 1, 40 shares, match 7, timestamp +1,000 ns); `itch/order_cancel_1` (ref 1, 10 shares, +2,000 ns); `itch/order_delete_1` (ref 1, +3,000 ns).

### 3.3 QF-OUCH-S: binary order entry with stream framing (KR-275)
Messages (no common header; byte 0 is the type):

| Type | Name | Fields (offset/width) | Length |
|---|---|---|---|
| `O` | Enter order | token 1/14 (alpha), side 15/1 {`B`,`S`}, shares 16/4 (at least 1), stock 20/8 (alpha), price 28/4, time in force 32/4 (u32 seconds; 0 = immediate), firm 36/4 (alpha), display 40/1 {`Y`,`N`}, capacity 41/1 {`A`,`P`,`R`,`O`}, sweep 42/1 {`Y`,`N`}, minimum quantity 43/4, cross type 47/1 {`N`,`O`,`C`}, customer type 48/1 {`R`,`N`,space} | 49 |
| `X` | Cancel order | token 1/14, shares 15/4 (new open quantity; 0 cancels all) | 19 |
| `A` | Accepted | timestamp 1/8 (u64), token 9/14, order reference 23/8 | 31 |
| `C` | Canceled | timestamp 1/8, token 9/14, decrement shares 23/4, reason 27/1 (`A` to `Z`) | 28 |

On a stream, each message is preceded by a u16 big-endian length equal to the message length (a simplified framing: no login, heartbeat or session packets). A single message is checked as QF-ITCH-S is (empty `E_TRUNCATED`, unknown type `E_TYPE`, short `E_TRUNCATED`, long `E_LENGTH`, fields `E_FIELD`). On a stream: fewer than 2 bytes left for a length, or fewer bytes left than the length, is `E_TRUNCATED`; a zero length is `E_LENGTH`; then the message is checked, and a length field that is not the length of the message's type is `E_LENGTH`.

**Fixture `ouch/enter_order_1`** (49 bytes): `4f` (`O`); token `QF0000000001` plus two spaces, 14 bytes = `51 46 30 30 30 30 30 30 30 30 30 31 20 20`; side `42`; shares 100 `00000064`; stock `514653494d202020`; price `000f7314`; time in force 0 `00000000`; firm four spaces `20202020`; display `59` (`Y`); capacity `50` (`P`); sweep `4e` (`N`); minimum quantity 0 `00000000`; cross type `4e` (`N`); customer type `20`. Hex: `4f51463030303030303030303120204200000064514653494d202020000f7314000000002020202059504e000000004e20`.

**Fixture `ouch/stream_two`** (72 bytes): `0031` (49) then `ouch/enter_order_1`, then `0013` (19) then `ouch/cancel_order_1` (`58`, the same token, shares `00000000`). Also `ouch/accepted_1` and `ouch/canceled_1` (sidecars).

### 3.4 QF-FAST-S: stop-bit compressed quotes (KR-276, KR-277)
**Plain idea.** Most fields of a quote repeat or change by a little from one message to the next. FAST-style coding sends a field only when it changed (a presence-map bit says whether it is there), sends prices as a difference from the last one, and writes every integer in 7-bit groups where the high bit of the last byte marks the end (the stop bit), so small numbers take one byte.

**Primitives.**
- *Unsigned integer* (u32): big-endian 7-bit groups, the minimum number of groups, bit 7 set on the last byte only. 0 is `80`; 100 is `e4`; 300 = 2 x 128 + 44 is `02 ac`. A first byte `00` followed by more bytes is `E_OVERLONG`; more than 5 bytes, or a value above 2^32 - 1, is `E_OVERFLOW`.
- *Signed integer* (i64): two's complement in 7-bit groups; bit 6 of the first byte is the sign. Minimum groups: a first group `00` followed by a group with bit 6 clear, or `7f` followed by a group with bit 6 set, is `E_OVERLONG`; more than 10 bytes or a value outside the i64 range is `E_OVERFLOW`. Because bit 6 is the sign, 100 (binary 1100100, bit 6 set) needs a leading zero group: `00 e4`; 1,012,500 = 61 x 128^2 + 102 x 128 + 20 is `3d 66 94` (61 = 0x3D has bit 6 clear, so no extra group).
- *ASCII string*: the characters, bit 7 set on the last byte. The strings used here are 1 to 8 bytes in 0x21 to 0x7E, so the empty encoding `80` is `E_FIELD`.
- *Presence map (PMAP)*: a stop-bit coded bit string, 7 bits per byte, most significant bit first; bits after the last byte are 0. The encoder writes the minimum number of bytes (at least one); a final byte whose 7 data bits are all 0 after the first byte is `E_OVERLONG`. Bits beyond those the template uses must be 0 (`E_FIELD`).

**Template 1, `Quote`** (the only template; a template id other than 1 is `E_TYPE`):

| Order | Field | Type | Operator | PMAP bit |
|---|---|---|---|---|
| 1 | template id | u32 | copy | 0 |
| 2 | seq | u32 | increment | 1 |
| 3 | symbol | ASCII | copy | 2 |
| 4 | bid price | i64 | delta | none (always present) |
| 5 | bid size | u32 | copy | 3 |
| 6 | ask price | i64 | delta | none |
| 7 | ask size | u32 | copy | 4 |

Operators. *copy*: present (bit 1) means the value follows and becomes the dictionary value; absent (bit 0) means the dictionary value is used; absent with an empty dictionary entry is `E_FIELD`. *increment*: present as copy; absent means dictionary + 1 (u32 overflow is `E_OVERFLOW`). *delta*: always present, a signed difference from the dictionary value, which starts at 0; prices must lie in [0, 2^62) (`E_FIELD`). The encoder omits a copy field exactly when it equals the dictionary value and an increment field exactly when it equals dictionary + 1, which makes the encoding canonical; for the same reason the decoder rejects a field that is present although its operator would have given the same value (`E_OVERLONG`, checked after the value is read). Check order when decoding: message by message, the PMAP, then the fields in template order. For one stop-bit item: input ends before a stop bit `E_TRUNCATED`; more bytes than the width allows (5 for u32, 10 for i64, 8 for a string, 2 for the PMAP) without a stop bit `E_OVERFLOW` (for a string and the PMAP, `E_FIELD` and `E_OVERLONG` respectively); then non-minimal `E_OVERLONG`; then the value range `E_OVERFLOW`; then the field's own rule `E_FIELD`. Every packet (one call of `encode_packet` or `decode_packet`) starts with an empty dictionary; a packet is the concatenation of its messages and must end on a message boundary (`E_TRUNCATED`).

**Fixture `fast/quote_two`** (24 bytes), two quotes for `QFSIM`: (seq 1, bid 1,012,500 x 100, ask 1,012,600 x 200) then (seq 2, bid 1,012,600 x 100, ask 1,012,700 x 300).

Message 1, dictionary empty, so every copy and increment field is present: PMAP bits 0 to 4 = 1, bits 5 and 6 = 0, data bits `1111100` with the stop bit: `fc`. Template id 1: `81`. Seq 1: `81`. Symbol `QFSIM`: `51 46 53 49 cd` (`M` = 0x4D, with the stop bit 0xCD). Bid delta +1,012,500: `3d 66 94`. Bid size 100: `e4`. Ask delta +1,012,600: 61 x 16,384 = 999,424 and 1,012,600 - 999,424 = 13,176 = 102 x 128 + 120, so the groups are 61, 102, 120 and the bytes `3d 66 f8` (0x78 = 120 with the stop bit is 0xF8). Ask size 200 = 1 x 128 + 72: `01 c8`. Message 1 is `fc 81 81 51 46 53 49 cd 3d 66 94 e4 3d 66 f8 01 c8` (17 bytes).

Message 2: template id equals the dictionary (omit, bit 0 = 0); seq 2 = 1 + 1 (omit, bit 1 = 0); symbol unchanged (bit 2 = 0); bid size 100 unchanged (bit 3 = 0); ask size 300 changed (bit 4 = 1): data bits `0000100`, byte `84`. Bid delta +100: `00 e4`. Ask delta +100: `00 e4`. Ask size 300: `02 ac`. Message 2 is `84 00 e4 00 e4 02 ac` (7 bytes).

Whole fixture hex: `fc818151465349cd3d6694e43d66f801c88400e400e402ac`.

### 3.5 QF-MOLD-S: multicast packets and gap detection (KR-278, KR-279)
A packet is a 20-byte header: `session` (10, alpha, printable, not all spaces), `sequence` (u64, the sequence number of the first message in the packet; the first message of a session is 1), `count` (u16); then `count` blocks, each a u16 length (1 to 65,535) followed by that many bytes. `count = 0` is a heartbeat whose `sequence` is the next expected number; `count = 0xFFFF` is end of session (no blocks follow) and its `sequence` is likewise the next number. Check order: fewer than 20 bytes `E_TRUNCATED`; session bytes outside 0x20 to 0x7E or all spaces `E_FIELD`; end of session followed by any byte `E_LENGTH`; then per block: fewer than 2 bytes left for the length `E_TRUNCATED`, length 0 `E_LENGTH`, fewer bytes left than the length `E_TRUNCATED`; finally, bytes after the last block `E_LENGTH`. In this project the block payloads are QF-ITCH-S messages; the framing does not look inside them.

**Gap detector** (receiver state: `session`, `expected` starting at 1, `ended`). For a packet `(s, n)`:
1. A different session than the first one seen: `E_SESSION`. Any packet after end of session: `E_SESSION`.
2. If `s > expected`: record the gap `[expected, s - 1]` (inclusive) and deliver from `s`.
3. If `s + n <= expected`: duplicate; deliver nothing.
4. If `s < expected < s + n`: deliver blocks `expected - s` onward (partial overlap).
5. Set `expected = max(expected, s + n)`. Heartbeat and end of session carry `n = 0`, so a heartbeat ahead of `expected` records a gap and moves `expected` to `s`.

No retransmission is simulated: a gap stays recorded and the receiver's result says so. Worked example: packets with first sequence 1 (3 blocks), 4 (2 blocks), 8 (1 block), a heartbeat at 9, and a duplicate of the first packet: delivered sequences 1 to 5 and 8; one gap `[6, 7]`; one duplicate packet; `expected = 9`.

**Fixture `mold/one_block`** (58 bytes): session `QFSIM00001` = `51 46 53 49 4d 30 30 30 30 31`; sequence 1 = `00 00 00 00 00 00 00 01`; count 1 = `00 01`; block length 36 = `00 24`; then the 36 bytes of `itch/add_order_1`. Also `mold/three_blocks` (sequence 2; executed, cancel, delete), `mold/heartbeat` (sequence 5, count 0: `...0000000000000005 0000`), `mold/end_of_session` (sequence 5, count `ffff`).

**Multicast smoke (K-3 "multicast feeds").** One sender container publishes the 10,000 records of §1.1 as QF-ITCH-S Add Order messages (order reference = `seq`; side `B` when `seq` is odd; shares = `qty` for trades, else 100; price = the ticks of `bid` or `price`, else 1,000,000; timestamp 34,200,000,000,000 + 1,000 x `seq`; locate 1), in QF-MOLD-S packets of up to 10 blocks, to group 239.192.0.1 port 30001 on the Compose bridge network, then three end-of-session packets. Two listener containers join the group, decode, run the gap detector, re-encode every delivered ITCH message and write `H_bytes` and the gap list. Pass: both listeners report no gap and an `H_bytes` equal to the sender's. Planted fault: a second run with `--drop-packet 37` must make both listeners report exactly one gap `[361, 370]`.

### 3.6 Fixture files and shared use
Fixtures live in `datasets/feeds/<format>/<name>.bin` (raw bytes) with a sidecar `<name>.json` holding: `format`, `label` ("simulated; not a certified implementation; not connected to any venue"), `fields` (the decoded values), `hex`, `sha256`, `derivation` (this page's section). `datasets/feeds/malformed.json` lists malformed inputs as hex with the expected error code. A language that implements the codecs must decode every fixture to its sidecar fields, encode the fields to the same bytes, and give the listed error code for every malformed entry. The fixtures were derived by hand above and the bytes cross-checked with a separate short `struct`-based script on 2026-11-20 (measured; the script's output matched every hex string on this page).

## 4. Where the code lives, and the libraries build without it (KR-280, KR-281)

- Python: a separate distribution `quantforge-adapters` in `platform/python/` (`quantforge_adapters.feeds` for the codecs, standard library only; `quantforge_adapters.adapters`, `.services`, `.smoke` for the round trips, client libraries as optional extras). It may read the library's committed outputs; the library never imports it.
- Java: `platform/java/aeron-smoke` (a separate Maven project; Aeron programs only).
- Compose files and the image lock: `platform/compose/`.
- `tools/check_adapter_deps.py` (repo gates, every pull request): no file in the four library source trees (`python/quantforge_core`, `python/quantforge_research`, `rust/`, `java25/src`, `cpp26/`) imports or links a forbidden module (`quantforge_adapters`, `grpc`, `pyarrow`, `kafka`, `psycopg`, `pg8000`, `clickhouse`, `prometheus_client`, `io.aeron`, `tonic`, `rdkafka`, `libpq`), and no library manifest (`python/pyproject.toml` dependencies, `rust/**/Cargo.toml` dependencies, `java25/pom.xml`, `cpp26/**/CMakeLists.txt`) names one. `--self-test` plants one forbidden import and one forbidden manifest dependency in a temporary copy and requires both to be reported.
- CI job `libraries-without-services` (in `adapters.yml`): on a fresh runner, `uv sync --frozen` in `python/` and import every `quantforge_core` module, then assert that no forbidden module is in `sys.modules` and that `quantforge_adapters` is not importable; and `mvn -B -q -DskipTests package` in `java25/` (its POM names no adapter). Rust and C++ are covered by the static check only (KR-281).

## Acceptance tests (confirmed 2026-11-20, before any container run)

| ID | Plan | Test |
|---|---|---|
| AD1 | K-3 | For each adapter row of §2.2 (REST, gRPC, Arrow IPC, Arrow Flight, Kafka, PostgreSQL, ClickHouse, Prometheus, Aeron): the Compose smoke test passes §1.2 with N = 10,000 and equal hashes, from digest-pinned free images only; result file uploaded as a workflow artefact |
| AD2 | K-3 | Each feed format (QF-FIX-S, QF-ITCH-S, QF-OUCH-S, QF-FAST-S, QF-MOLD-S): every fixture decodes to its sidecar and encodes to its bytes; every `malformed.json` entry gives its code; random-byte inputs give a result or `FeedError`, never another exception; round-trip property tests |
| AD3 | K-3 | Multicast: 10,000 ITCH-style messages over QF-MOLD-S multicast to two listeners, equal `H_bytes`, no gap; the planted drop reported as one gap |
| AD4 | K-3, ADR-0006 | `tools/check_adapter_deps.py` green with its self-test, and `libraries-without-services` green |
| AD5 | 14.10 rule 1 | Every planted fault of §1.4 gives its verdict in the same job |
| AD6 | 14.10 rule 2 | The CHANGELOG line for K-3 names the workflow and, once run, the run link |

## Out of scope

- Any connection to a real venue, broker, exchange gateway or data vendor; any recorded market data in a fixture; any claim of conformance to a vendor or standards document.
- Grafana (SC-1).
- Throughput or latency claims for any adapter (wall time is recorded, not judged).
- Production hardening: authentication, TLS, high availability, schema registries, replication, backups.
- Codecs in Java, Rust and C++ (KR-282: Python is the K-3 deliverable; the shared fixtures make a later port testable).

## Limits

- The round trip proves the bytes survive the store; it says nothing about behaviour under load or failure (that is K-6).
- Prometheus reduces each record to `{seq, value}`; its hash covers that reduction only.
- UDP multicast on a Compose bridge network can drop packets under load; the smoke paces the sender, and a drop is reported as a gap (a fail), never hidden.
- The REST and gRPC services compute the snapshot hash with the adapter package's own canonical-form function, not by importing the library, because the library requires Python 3.15 and the service image is Python 3.13 (KR-283). The function is checked byte for byte against `quantforge_core.snapshot.canonical` over all 10,000 records in the local tests.
- The reading of image and library licence terms is a reading, not legal advice.

## Changes from 0.1.0

- Grafana dropped (SC-1); containers on Actions only (SC-2); FIX and FAST kept as simulated formats (SC-3); all formats renamed "-style" and defined here, not by reference to vendor documents (SC-4).
- SoupBinTCP replaced by the simpler QF-OUCH-S stream framing (§3.3); the multicast row uses QF-MOLD-S.
- Rulings renumbered: version 0.1.0's KR-180 to KR-189 are KR-270 to KR-283 here (KR-180 to KR-189 in that draft were never confirmed; the block KR-270 onward was checked free on every remote branch on 2026-11-20).
