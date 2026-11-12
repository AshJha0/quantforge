"""E9 (R6-15, review finding 16): fixed-seed Monte Carlo hash golden.

Writes datasets/golden/core/mc_hash.json: 4,096 xoshiro256** integer draws and the matching uniforms for a fixed
seed on three streams, every case `bit_exact`, and oracle/MC_HASH_E9.json with the SHA-256 of each case's
values (integers as decimal strings, uniforms as float.hex, one per line, LF). Because the cases are bit_exact
and cross-platform.yml runs every golden on Linux, Windows and macOS, a green cross-platform run proves the
hash is identical on all three. tools/check_mc_hash.py recomputes the hashes from the golden.
"""
import hashlib
import json
from pathlib import Path

from qf_oracle.common import Suite, note
from qf_oracle.rng import Xo

HERE = Path(__file__).resolve().parent
SEED, COUNT, STREAMS = 20261112, 4096, (0, 1, 7)


def digest(values):
    lines = [v if isinstance(v, str) else float(v).hex() for v in values]
    return hashlib.sha256(("\n".join(lines) + "\n").encode("ascii")).hexdigest()


def main():
    s = Suite("mc_hash", "specifications/01-core/rng.md", "oracle/python/gen_mc_hash.py")
    hashes = {}
    for stream in STREAMS:
        inp = {"seed": str(SEED), "stream": stream, "count": COUNT}
        a = Xo(seed=SEED, stream=stream)
        ints = [str(a.next()) for _ in range(COUNT)]
        b = Xo(seed=SEED, stream=stream)
        us = [b.uniform() for _ in range(COUNT)]
        s.add("core.rng.next_u64", inp, {"values": ints}, cls="bit_exact", verified=["pure-integer-replay"], tags=["E9"])
        s.add("core.rng.uniforms", inp, {"values": us}, cls="bit_exact", verified=["pure-integer-replay"], tags=["E9"])
        hashes[f"stream {stream} next_u64"] = digest(ints)
        hashes[f"stream {stream} uniforms"] = digest(us)
    s.write()
    out = {"item": "E9", "seed": str(SEED), "count": COUNT, "streams": list(STREAMS),
           "serialisation": "integers as decimal strings, uniforms as Python float.hex(), one per line, LF, trailing LF",
           "golden": "datasets/golden/core/mc_hash.json", "sha256": hashes}
    (HERE.parent / "MC_HASH_E9.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    note(f"mc_hash: {len(STREAMS) * 2} cases, {COUNT} draws each")


if __name__ == "__main__":
    main()
