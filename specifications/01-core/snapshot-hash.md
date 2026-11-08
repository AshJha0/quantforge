# Snapshot hash

Spec version 1.0.0. Status: Specified.

A snapshot is a JSON document holding everything a calculation read. Its hash is its identity: same
content, same hash, in all four languages. Plain JSON text cannot do that, because languages format
numbers differently, so the hash is taken over a canonical byte form with one spelling per value.

## Canonical form

Parse the document, then write these UTF-8 bytes with no white space:

| JSON value | Canonical bytes |
|---|---|
| `null`, `true`, `false` | The literal |
| Number | `#` then 16 lower-case hex digits: the big-endian IEEE 754 binary64 bits of the nearest double. `-0` is written as `+0`, so `#0000000000000000`. `1`, `1.0` and `1e0` all give `#3ff0000000000000` |
| String | `"`, the content, `"`. Escape `"` as `\"` and `\` as `\\`. Escape U+0000 to U+001F as `\u00xx`, lower-case hex, even for tab and newline. Everything else, including U+007F and all non-ASCII, is raw UTF-8. Strings are not normalised |
| Array | `[`, elements joined by `,`, `]` |
| Object | `{`, then `key:value` joined by `,`, `}`. Keys are ordered by the bytes of their UTF-8 form, unsigned, shorter first on a tie |

Every number is treated as binary64. An integer that needs more than 53 bits, such as a large
quantity, must be stored as a string.

## Hash

`snapshot_id = "sha256:" + lower-case hex SHA-256 of the canonical bytes`, with one exclusion: a
top-level key `snapshot_id` is removed first, so that a snapshot can carry its own hash. Nested keys
of that name stay. Any SHA-256 library may be used.

## Operation `core.snapshot.hash`

Input: `document_text`, a string holding the JSON text. Text is used, not a parsed value, so that
tests reach the number and duplicate-key rules.

Outputs: `canonical` (the canonical form as a string) and `snapshot_id`.

Checks, in order:
1. Not valid JSON, or a duplicate key at any depth after unescaping: `E_PARSE`.
2. A number that overflows binary64: `E_SCHEMA`. A number that underflows parses to the nearest
   value, zero included.
3. A lone surrogate escape such as `\ud800`: `E_SCHEMA`.
4. The top level is not an object: `E_SCHEMA`.

Nesting up to 64 levels must work. Beyond that: `E_LIMIT`, as for text over the size in `limits.md`.

## Worked example

`{"b":1,"a":[true,null,"x\n"]}` has canonical form

`{"a":[true,null,"x\u000a"],"b":#3ff0000000000000}`

## Acceptance

Class `date_and_convention`, exact on both outputs. Oracle: `canon` in `oracle/python/gen_data.py`, with
the SHA-256 checked against the NIST `abc` vector and against the system `sha256sum`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] NIST FIPS PUB 180-4, *Secure Hash Standard (SHS)*, 2015, SHA-256 (not opened)
- [S2] IETF RFC 8259, *The JavaScript Object Notation (JSON) Data Interchange Format*, 2017 (opened 2026-11-07)
- [S3] IETF RFC 8785, *JSON Canonicalization Scheme (JCS)*, 2020: related prior art only; this spec's canonical form is its own and is not JCS (opened 2026-11-07)
